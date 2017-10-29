# Kubernetes support for Scanner

Files needed:
- `.scanner.toml` with your configuration
- `google-key.json` service account key ([Credentials](https://console.cloud.google.com/apis/credentials) > Create credentials > Service account key > JSON)

Environment variables needed:
- `AWS_SECRET_ACCESS_KEY` and `AWS_ACCESS_KEY_ID` (see [GCS Settings](https://console.cloud.google.com/storage/settings) > Interoperability)

First, set up your local Docker containers:
```
python cluster.py build
docker-compose build
docker-compose up -d
```

After this, all commands (except `python cluster.py build`) will run a local Docker container, which you can enter by doing `./run.sh`.

Start a Kubernetes cluster:
```
python cluster.py create
```

Run an example computation on the cluster:
```
python client.py
```

## Commands

Update existing containers:
```
kubectl delete deploy --all
python cluster.py create
```

Resize the cluster:
```
gcloud container clusters
```

Delete the Kubernetes cluster:
```
python cluster.py delete
```

## Dashboard

First, if your local Docker container is not on your laptop, you'll need to setup an SSH tunnel:
```
ssh -L 8001:localhost:8001 <your server>
```

Then visit [http://localhost:8001/ui](http://localhost:8001/ui).

**Note**: this is broken until I can figure out how to fix the permissions issue changed in k8s 1.8 (see [here](https://github.com/kubernetes/dashboard/wiki/Access-control) and [here](https://cloud.google.com/container-engine/docs/role-based-access-control#setting_up_role-based_access_control)).
