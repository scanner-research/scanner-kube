docker build -t scannerresearch/scanner:master -f Dockerfile-master . && \
    docker push scannerresearch/scanner:master

docker build -t scannerresearch/scanner:worker -f Dockerfile-worker . && \
    docker push scannerresearch/scanner:worker
