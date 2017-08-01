docker build -t wcrichto/scanner-kube:master -f Dockerfile-master . && \
    docker push wcrichto/scanner-kube:master

docker build -t wcrichto/scanner-kube:worker -f Dockerfile-worker . && \
    docker push wcrichto/scanner-kube:worker
