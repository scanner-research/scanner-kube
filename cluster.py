from apiclient.discovery import build
from googleapiclient.errors import HttpError
import time
import subprocess as sp
import argparse
import tempfile
import yaml
import os
import sys

PROJECT_ID = 'visualdb-1046'
ZONE = 'us-east1-d'
CLUSTER_ID = 'cluster-1'
ARGS = {'projectId': PROJECT_ID, 'zone': ZONE, 'clusterId': CLUSTER_ID}
CONTAINER_REPO = 'wcrichto/scanner-kube'

service = build('container', 'v1')
clusters = service.projects().zones().clusters()


def make_container(name):
    return {
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


def create_deployment(name):
    template = make_deployment(name)
    with tempfile.NamedTemporaryFile() as f:
        f.write(yaml.dump(template))
        f.flush()

        sp.check_call(['kubectl', 'create', '-f', f.name])


def get_info():
    req = clusters.get(**ARGS)
    return req.execute()


def get_credentials():
    sp.check_call(
        ['gcloud', 'container', 'clusters', 'get-credentials', CLUSTER_ID])


def delete():
    req = clusters.delete(**ARGS)
    req.execute()
    print 'Sent delete request. Waiting for deletion...'
    while True:
        try:
            get_info()
            time.sleep(5)
        except HttpError:
            print 'Done!'
            return


def create():
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
                        "maxNodeCount": 10
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
        info = get_info()
        if info['status'] == 'RUNNING':
            break
        time.sleep(5)

    print 'Cluster created. Setting up kubernetes...'
    get_credentials()

    print 'Making secrets...'
    sp.check_call([
        'kubectl', 'create', 'secret', 'generic', 'google-key',
        '--from-file=google-key.json'
    ])
    sp.check_call([
        'kubectl', 'create', 'secret', 'generic', 'aws-storage-key',
        '--from-literal=AWS_ACCESS_KEY_ID=' + os.environ['AWS_ACCESS_KEY_ID'],
        '--from-literal=AWS_SECRET_ACCESS_KEY=' +
        os.environ['AWS_SECRET_ACCESS_KEY']
    ])

    print 'Creating deployments...'
    create_deployment('master')
    sp.check_call(
        ['kubectl', 'expose', 'deploy/scanner-master', '--port', '8080'])
    create_deployment('worker')

    print 'Done!'


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    command = parser.add_subparsers(dest='command')
    command.add_parser('create')
    command.add_parser('delete')
    command.add_parser('get-credentials')
    args = parser.parse_args()

    if args.command == 'create':
        create()
    elif args.command == 'delete':
        delete()
    elif args.command == 'get-credentials':
        get_credentials()
