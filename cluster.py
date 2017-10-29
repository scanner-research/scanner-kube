import argparse
import subprocess as sp
import sys
import signal
import toml

def build():
    config = toml.loads(open('.scanner.toml').read())
    repo = config['cluster']['container_repo']
    print repo

    def _build(ty):
        sp.check_call(
            """
docker build -t {repo}:{ty} -f docker/Dockerfile-{ty} . && \
    docker push {repo}:{ty}""".format(repo=repo, ty=ty),
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
    create = command.add_parser('create')
    create.add_argument('--reset', '-r', action='store_true', help='Delete current deployments')
    command.add_parser('delete')
    command.add_parser('get-credentials')
    command.add_parser('build')
    command.add_parser('serve')
    command.add_parser('auth')
    resize = command.add_parser('resize')
    resize.add_argument('size', type=int, help='Number of nodes')

    args = parser.parse_args()

    if args.command == 'build':
        build()
    else:
        # cluster_utils are separated into a standalone file so that cluster.py
        # can be called from outside the Docker container when used for build.
        import cluster_utils as cu
        getattr(cu, args.command.replace('-','_'))(args)
