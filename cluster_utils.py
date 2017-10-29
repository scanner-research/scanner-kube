import time
import subprocess as sp
import tempfile
import yaml
import os
import sys
import json
from pprint import pprint
import threading
import toml
import atexit
import multiprocessing as mp
import shlex
import signal

config = toml.loads(open('.scanner.toml').read())
PROJECT_ID = config['cluster']['project']
ZONE = config['cluster']['zone']
CLUSTER_ID = config['cluster']['cluster']
CONTAINER_REPO = config['cluster']['container_repo']
ARGS = {'projectId': PROJECT_ID, 'zone': ZONE, 'clusterId': CLUSTER_ID}


def run(s):
    return sp.check_call(shlex.split(s))


def make_container(name):
    template = {
        'name': name,
        'image': '{}:{}'.format(CONTAINER_REPO, name),
        'imagePullPolicy': 'Always',
        'volumeMounts': [{
            'name': 'google-key',
            'mountPath': '/secret'
        }],
        'env': [
            {'name': 'GOOGLE_APPLICATION_CREDENTIALS',
             'value': '/secret/google-key.json'},
            {'name': 'AWS_ACCESS_KEY_ID',
             'valueFrom': {'secretKeyRef': {
                 'name': 'aws-storage-key',
                 'key': 'AWS_ACCESS_KEY_ID'
             }}},
            {'name': 'AWS_SECRET_ACCESS_KEY',
             'valueFrom': {'secretKeyRef': {
                 'name': 'aws-storage-key',
                 'key': 'AWS_SECRET_ACCESS_KEY'
             }}},
            {'name': 'GLOG_minloglevel',
             'value': '0'},
            {'name': 'GLOG_logtostderr',
             'value': '1'},
            {'name': 'GLOG_v',
             'value': '1'}
        ]
    }  # yapf: disable
    if name == 'master':
        template['ports'] = [{
            'containerPort': 8080,
        }]
    elif name == 'worker':
        rs = get_by_owner('rs', 'scanner-master')
        pod_name = get_by_owner('pod', rs)
        while True:
            pod = get_object(get_kube_info('pod'), pod_name)
            if pod is None:
                time.sleep(1)
            else:
                break

        template['env'] += [{
            'name': 'SCANNER_MASTER_SERVICE_HOST',
            'value': pod['status']['podIP']
        }, {
            'name': 'SCANNER_MASTER_SERVICE_PORT',
            'value': '8080'
        }]

    return template


def make_deployment(name):
    template = {
        'apiVersion': 'apps/v1beta1',
        'kind': 'Deployment',
        'metadata': {'name': 'scanner-{}'.format(name)},
        'spec': {
            'replicas': 1,
            'template': {
                'metadata': {'labels': {'app': 'scanner-{}'.format(name)}},
                'spec': {
                    'containers': [make_container(name)],
                    'volumes': [{
                        'name': 'google-key',
                        'secret': {
                            'secretName': 'google-key',
                            'items': [{
                                'key': 'google-key.json',
                                'path': 'google-key.json'
                            }]
                        }
                    }],
                    'nodeSelector': {
                        'cloud.google.com/gke-nodepool':
                        'master' if name == 'master' else 'workers'
                    }
                }
            }
        }
    }  # yapf: disable

    if name == 'worker':
        template['spec']['template']['spec']['resources'] = {
            'requests': {
                'cpu': 4,
                'memory': '16Gi'
            }
        }

    return template


def create_object(template):
    with tempfile.NamedTemporaryFile() as f:
        f.write(yaml.dump(template))
        f.flush()

        sp.check_call(['kubectl', 'create', '-f', f.name])


def cluster_running():
    return sp.check_output('gcloud container clusters list --format=json | jq -e \'.[] | select(.name == "{}")\''.format(CLUSTER_ID), shell=True) != ''


def get_credentials(args):
    run('gcloud container clusters get-credentials ' + CLUSTER_ID)


def delete(args):
    run('gcloud container clusters delete ' + CLUSTER_ID)


def get_kube_info(kind):
    return json.loads(sp.check_output(shlex.split('kubectl get {} -o json'.format(kind))))


def get_object(info, name):
    for item in info['items']:
        if item['metadata']['name'] == name:
            return item
    return None


def create(args):
    if not cluster_running():
        print 'Creating cluster...'
        clusters = build_service()
        scopes = [
            "https://www.googleapis.com/auth/compute",
            "https://www.googleapis.com/auth/devstorage.read_only",
            "https://www.googleapis.com/auth/logging.write",
            "https://www.googleapis.com/auth/monitoring.write",
            "https://www.googleapis.com/auth/servicecontrol",
            "https://www.googleapis.com/auth/service.management.readonly",
            "https://www.googleapis.com/auth/trace.append"
        ]
        req = clusters.create(
            body={
                "cluster": {
                    "name": CLUSTER_ID,
                    "zone": ZONE,
                    "nodePools": [{
                        "name": "master",
                        "initialNodeCount": 1,
                        "config": {
                            "machineType": "n1-standard-4",
                            "imageType": "COS",
                            "diskSizeGb": 100,
                            "oauthScopes": scopes
                        },
                    }, {
                        "name": "workers",
                        "initialNodeCount": 1,
                        "config": {
                            "machineType": "n1-standard-4",
                            "imageType": "COS",
                            "diskSizeGb": 100,
                            "oauthScopes": scopes,
                        },

                    }],
                    "initialClusterVersion": "1.8.1-gke.0",
                }
             },
            projectId=PROJECT_ID,
            zone=ZONE)  # yapf: disable
        req.execute()

        print 'Request submitted. Waiting for cluster startup...'
        while True:
            info = get_cluster_info()
            assert info is not None
            if info['status'] == 'RUNNING':
                break
            time.sleep(5)

    print 'Cluster created. Setting up kubernetes...'
    get_credentials(args)

    if args.reset:
        run('kubectl delete deploy --all')

    secrets = get_kube_info('secrets')
    print 'Making secrets...'
    if get_object(secrets, 'google-key') is None:
        run('kubectl create secret generic google-key --from-file=google-key.json')

    if get_object(secrets, 'aws-storage-key') is None:
        run('kubectl create secret generic aws-storage-key' +
            ' --from-literal=AWS_ACCESS_KEY_ID=' +
            os.environ['AWS_ACCESS_KEY_ID'],
            ' --from-literal=AWS_SECRET_ACCESS_KEY=' +
            os.environ['AWS_SECRET_ACCESS_KEY'])

    deployments = get_kube_info('deployments')
    print 'Creating deployments...'
    if get_object(deployments, 'scanner-master') is None:
        create_object(make_deployment('master'))
        print 'Waiting for master to start...'
        while True:
            deploy = get_object(get_kube_info('deployments'), 'scanner-master')
            if 'unavailableReplicas' not in deploy['status']:
                break
        serve()

    if get_object(deployments, 'scanner-worker') is None:
        create_object(make_deployment('worker'))

    print 'Done!'


def get_by_owner(ty, owner):
    return sp.check_output(
        'kubectl get {} -o json | jq \'.items[] | select(.metadata.ownerReferences[0].name == "{}") | .metadata.name\''.
        format(ty, owner),
        shell=True).strip()[1:-1]


PID_FILE = '/tmp/serving_process.pid'


def serve(args):
    if os.path.isfile(PID_FILE):
        try:
            sp.check_call(['kill', open(PID_FILE).read()])
        except sp.CalledProcessError:
            pass

    p = sp.Popen(
        shlex.split(
            'python -c "import cluster_utils as cu; cu.serve_process()"'))

    with open(PID_FILE, 'w') as f:
        f.write(str(p.pid))


def serve_process(args):
    if get_cluster_info() is None:
        return

    get_credentials(args)

    rs = get_by_owner('rs', 'scanner-master')
    pod_name = get_by_owner('pod', rs)
    print 'Forwarding ' + pod_name
    forward_process = sp.Popen(
        ['kubectl', 'port-forward', pod_name, '8080:8080'])
    proxy_process = sp.Popen(['kubectl', 'proxy', '--address=0.0.0.0'])

    def cleanup_processes(signum, frame):
        proxy_process.terminate()
        forward_process.terminate()
        proxy_process.wait()
        forward_process.wait()
        exit()

    signal.signal(signal.SIGINT, cleanup_processes)
    signal.signal(signal.SIGTERM, cleanup_processes)
    signal.pause()


def auth(args):
    run('gcloud auth activate-service-account --key-file=google-key.json')
    run('gcloud config set project ' + PROJECT_ID)
    run('gcloud config set compute/zone ' + ZONE)
    run('gcloud config set container/cluster ' + CLUSTER_ID)


def resize(args):
    run('gcloud -q container clusters resize {} --node-pool=workers --size={}'.format(
        CLUSTER_ID, args.size))
    run('kubectl scale deploy/scanner-worker --replicas={}'.format(args.size))
