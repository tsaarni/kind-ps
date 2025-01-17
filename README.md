List what Kind clusters are running currently

```console
$ kind get clusters
contour
```

List nodes that the cluster has

```console
$ kubectl get nodes
NAME                    STATUS   ROLES           AGE   VERSION
contour-control-plane   Ready    control-plane   11h   v1.32.0
contour-worker          Ready    <none>          11h   v1.32.0
```

These reflect the docker containers that are running

```console
$ docker ps
CONTAINER ID   IMAGE                  COMMAND                  CREATED        STATUS        PORTS                                              NAMES
992ec6ccbeed   kindest/node:v1.32.0   "/usr/local/bin/entr…"   11 hours ago   Up 11 hours   127.0.0.1:36409->6443/tcp                          contour-control-plane
22c9d82b69f2   kindest/node:v1.32.0   "/usr/local/bin/entr…"   11 hours ago   Up 11 hours   127.0.0.101:80->80/tcp, 127.0.0.101:443->443/tcp   contour-worker
```

List the pods that are running in `contour-worker` container

```console
$ ./kind-ps.py contour-worker contour
```

Result is JSON document

```json
{
  "contour-worker": [
    {
      "name": "contour",
      "image": {
        "tags": [
          [
            "ghcr.io/projectcontour/contour:v1.30.2"
          ]
        ]
      },
      "state": "CONTAINER_RUNNING",
      "created": "2025-01-17T10:32:45.674421",
      "pids": [
        {
          "pid": "1345826",
          "cmd": "contour serve --incluster --xds-address=0.0.0.0 --xds-port=8001 --contour-cafile=/certs/ca.crt --contour-cert-file=/certs/tls.crt --contour-key-file=/certs/tls.key --config-path=/config/contour.yaml "
        }
      ]
    },
    {
      "name": "contour",
      "image": {
        "tags": [
          [
            "ghcr.io/projectcontour/contour:v1.30.2"
          ]
        ]
      },
      "state": "CONTAINER_RUNNING",
      "created": "2025-01-17T10:32:24.069099",
      "pids": [
        {
          "pid": "1344974",
          "cmd": "contour serve --incluster --xds-address=0.0.0.0 --xds-port=8001 --contour-cafile=/certs/ca.crt --contour-cert-file=/certs/tls.crt --contour-key-file=/certs/tls.key --config-path=/config/contour.yaml "
        }
      ]
    }
  ]
}
```

We can see that the PIDs are processes on host

```console
$ ps 1345826
    PID TTY      STAT   TIME COMMAND
1345826 ?        Ssl    0:38 contour serve --incluster --xds-address=0.0.0.0 --xds-port=8001 --contour-cafile=/certs/ca.crt --contour-cert-file=/certs/tls.crt --contour-key-f
```


Now we can use the PID to get access to the root filesytem of the container from the host

```console
$ sudo ls /proc/1345826/root/
bin  certs  config  dev  etc  proc  product_name  product_uuid  sys  var
```

Or e.g. send signal to stop the process

```console
$ sudo kill -STOP 1345826
```
