import argparse
import subprocess as sp
from constants import *
import sys
import signal


def build():
    def _build(ty):
        sp.check_call(
            """
docker build -t {repo}:{ty} -f Dockerfile-{ty} . && \
    docker push {repo}:{ty}""".format(repo=CONTAINER_REPO, ty=ty),
            shell=True)

    _build('master')
    _build('worker')


# docker sends a sigterm to kill a container, this ensures Python dies when the
# signal is sent
def sigterm_handler(signum, frame):
    sys.exit(1)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, sigterm_handler)

    parser = argparse.ArgumentParser()
    command = parser.add_subparsers(dest='command')
    command.add_parser('create')
    command.add_parser('delete')
    command.add_parser('get-credentials')
    command.add_parser('build')
    command.add_parser('serve')
    args = parser.parse_args()

    if args.command == 'build':
        build()
    else:
        # cluster_utils are separated into a standalone file so that cluster.py
        # can be called from outside the Docker container when used for build.
        import cluster_utils as cu
        if args.command == 'create':
            cu.create()
        elif args.command == 'delete':
            cu.delete()
        elif args.command == 'get-credentials':
            cu.get_credentials()
        elif args.command == 'serve':
            cu.serve()
