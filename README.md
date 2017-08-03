# Kubernetes support for Scanner

Files needed:
- `.scanner.toml` with your configuration
- `google-key.json` service account JSON

Environment variables needed:
- `AWS_SECRET_ACCESS_KEY` and `AWS_ACCESS_KEY_ID` (see [GCS Settings](https://console.cloud.google.com/storage/settings?project=visualdb-1046) > Interoperability)

First, set up your local Docker containers:
```
python cluster.py build
docker-compose build
docker-compose up -d
```

Then enter your local container and start up a Kubernetes cluster:
```
./run.sh
python cluster.py create
```
