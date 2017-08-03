from apiclient.discovery import build
from googleapiclient.errors import HttpError
from constants import *
import time
import subprocess as sp
import tempfile
import yaml
import os
import sys
import json
from pprint import pprint
import threading

service = build('container', 'v1')
clusters = service.projects().zones().clusters()

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
             }}}
        ]
    }  # yapf: disable
    if name == 'master':
        template['ports'] = [{
            'containerPort': 8080,
        }]
    return template


def make_deployment(name):
    return {
        'apiVersion': 'apps/v1beta1',
        'kind': 'Deployment',
        'metadata': {'name': 'scanner-{}'.format(name)},
        'spec': { 'template': {
            'metadata': { 'labels': { 'app': 'scanner' }},
            'spec': {
                'containers': [make_container(name)],
                'volumes': [{
                    'name': 'google-key',
                    'secret': {
                        'secretName': 'google-key',
                        'items': [{'key': 'google-key.json', 'path': 'google-key.json'}]
                    }
                }]
            }
        }}
    }  # yapf: disable


def create_object(template):
    with tempfile.NamedTemporaryFile() as f:
        f.write(yaml.dump(template))
        f.flush()

        sp.check_call(['kubectl', 'create', '-f', f.name])


def get_cluster_info():
    req = clusters.get(**ARGS)
    try:
        return req.execute()
    except HttpError:
        return None


def get_credentials():
    sp.check_call(
        ['gcloud', 'container', 'clusters', 'get-credentials', CLUSTER_ID])


def delete():
    req = clusters.delete(**ARGS)
    req.execute()
    print 'Sent delete request. Waiting for deletion...'
    while True:
        if get_cluster_info() is None:
            print 'Done!'
            return
        time.sleep(5)


def get_kube_info(kind):
    return json.loads(sp.check_output(['kubectl', 'get', kind, '-o', 'json']))


def get_object(info, name):
    for item in info['items']:
        if item['metadata']['name'] == name:
            return item
    return None


def create():
    if get_cluster_info() is None:
        print 'Creating cluster...'
        req = clusters.create(
            body={
                "cluster": {
                    "name": CLUSTER_ID,
                    "zone": ZONE,
                    "network": "default",
                    "loggingService": "logging.googleapis.com",
                    "monitoringService": "none",
                    "nodePools": [{
                        "name": "default-pool",
                        "initialNodeCount": 1,
                        "config": {
                            "machineType": "n1-standard-4",
                            "imageType": "COS",
                            "diskSizeGb": 100,
                            "preemptible": False,
                            "oauthScopes": [
                                "https://www.googleapis.com/auth/compute",
                                "https://www.googleapis.com/auth/devstorage.read_only",
                                "https://www.googleapis.com/auth/logging.write",
                                "https://www.googleapis.com/auth/monitoring.write",
                                "https://www.googleapis.com/auth/servicecontrol",
                                "https://www.googleapis.com/auth/service.management.readonly",
                                "https://www.googleapis.com/auth/trace.append"
                            ]
                        },
                        "autoscaling": {
                            "enabled": True,
                            "minNodeCount": 1,
                            "maxNodeCount": 1
                        },
                    }],
                    "initialClusterVersion": "1.7.2",
                    "enableKubernetesAlpha": True,
                    "masterAuth": {
                        "username": "admin",
                        "clientCertificateConfig": {
                            "issueClientCertificate": True
                        }
                    },
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
    get_credentials()

    secrets = get_kube_info('secrets')
    print 'Making secrets...'
    if get_object(secrets, 'google-key') is None:
        sp.check_call([
            'kubectl', 'create', 'secret', 'generic', 'google-key',
            '--from-file=google-key.json'
        ])
    if get_object(secrets, 'aws-storage-key') is None:
        sp.check_call([
            'kubectl', 'create', 'secret', 'generic', 'aws-storage-key',
            '--from-literal=AWS_ACCESS_KEY_ID=' +
            os.environ['AWS_ACCESS_KEY_ID'],
            '--from-literal=AWS_SECRET_ACCESS_KEY=' +
            os.environ['AWS_SECRET_ACCESS_KEY']
        ])

    deployments = get_kube_info('deployments')
    print 'Creating deployments...'
    if get_object(deployments, 'scanner-master') is None:
        create_object(make_deployment('master'))
        print 'Waiting for master to start...'
        while True:
            deploy = get_object(get_kube_info('deployments'), 'scanner-master')
            if 'unavailableReplicas' not in deploy['status']:
                break
        port_forward()

    # TODO(wcrichto): is it possible to use NodePort instead of LoadBalancer?
    services = get_kube_info('services')
    if get_object(services, 'scanner-master') is None:
        sp.check_call(['kubectl', 'expose', 'deploy/scanner-master'])

    if get_object(deployments, 'scanner-worker') is None:
        create_object(make_deployment('worker'))

    print 'Done!'


PID_FILE = '/tmp/forwarding_process.pid'
def port_forward():
    if os.path.isfile(PID_FILE):
        sp.check_call(['kill', '-9', open(PID_FILE).read()])

    for pod in get_kube_info('pods')['items']:
        if pod['status']['containerStatuses'][0]['name'] == 'master':
            pod_name = pod['metadata']['name']
            print 'Forwarding ' + pod_name
            forward_process = sp.Popen(['kubectl', 'port-forward', pod_name, '8080:8080'])
            with open(PID_FILE, 'w') as f:
                f.write(str(forward_process.pid))
            return forward_process


# We have to make sure to .wait() on the port forwarding process in serve, since
# otherwise when it gets killed on a later invocation to port_forward, the process
# becomes a zombie and the port remains blocked.
def watch_process(p):
    p.wait()


def serve():
    get_credentials()
    p = port_forward()
    t = threading.Thread(target=watch_process, args=(p,))
    t.daemon = True
    t.start()
    sp.check_call(['kubectl', 'proxy', '--address=0.0.0.0'])
