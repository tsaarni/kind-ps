# Fetch Host PIDs for Processes in Kind Cluster

## Introduction

This Python script identifies the host PID for a process running inside a container in a Kind cluster.
It uses `docker exec` to run `crictl` on the Kind node to list the Pods and containers running on the node.
It then utilizes `/sys/fs/cgroup/` to find the host PIDs and `/proc/` to retrieve process details.


## Usage

```
usage: kind-ps.py [-h] [--debug] docker_filter [pod_filter]

Get host PIDs for processes within a Kind cluster

positional arguments:
  docker_filter  Filter to include specific Kind Docker containers
  pod_filter     Optional filter to include specific Pods

options:
  -h, --help     show this help message and exit
  --debug        Activate debug logging
```

## Example

First, list the nodes in the Kind cluster:

```console
$ kubectl get nodes
NAME                    STATUS   ROLES           AGE   VERSION
contour-control-plane   Ready    control-plane   11h   v1.32.0
contour-worker          Ready    <none>          11h   v1.32.0
```

These nodes correspond to the Docker containers that are running:

```console
$ docker ps
CONTAINER ID   IMAGE                  COMMAND                  CREATED        STATUS        PORTS                                              NAMES
992ec6ccbeed   kindest/node:v1.32.0   "/usr/local/bin/entr…"   15 hours ago   Up 15 hours   127.0.0.1:36409->6443/tcp                          contour-control-plane
22c9d82b69f2   kindest/node:v1.32.0   "/usr/local/bin/entr…"   15 hours ago   Up 15 hours   127.0.0.101:80->80/tcp, 127.0.0.101:443->443/tcp   contour-worker
```

To list the pods that match `contour` and are running on the `contour-worker` node, run:

```console
$ ./kind-ps.py contour-worker envoy
```

Result is a JSON document

```json
[
  {
    "node": "contour-worker",
    "pod": "envoy-hgf2d",
    "container": "envoy",
    "image": {
      "tags": [
        "docker.io/envoyproxy/envoy:v1.31.5"
      ]
    },
    "created": "2025-01-17T09:01:26.668859",
    "pids": [
      {
        "pid": "1123824",
        "cmd": "envoy -c /config/envoy.json --service-cluster projectcontour --service-node envoy-hgf2d --log-level info"
      }
    ],
    "labels": {
      "app": "envoy",
      "controller-revision-hash": "dd8c68b4b",
      "pod-template-generation": "1"
    }
  },
  {
    "node": "contour-worker",
    "pod": "envoy-hgf2d",
    "container": "shutdown-manager",
    "image": {
      "tags": []
    },
    "created": "2025-01-17T09:01:22.363198",
    "pids": [
      {
        "pid": "1123597",
        "cmd": "/bin/contour envoy shutdown-manager"
      }
    ],
    "labels": {
      "app": "envoy",
      "controller-revision-hash": "dd8c68b4b",
      "pod-template-generation": "1"
    }
  }
]
```

The PIDs listed are the host PIDs for the processes running inside the container.
You can use these PIDs to inspect the processes on the host:

```console
$ ps 1123824
    PID TTY      STAT   TIME COMMAND
1123824 ?        Ssl   16:50 envoy -c /config/envoy.json --service-cluster projectcontour --service-node envoy-hgf2d --log-level info
```

Now, you can use the PID to access the root filesystem of the container from the host.

```console
$ sudo ls /proc/1123824/root/
admin  config                home   libx32  proc          run   tmp
bin    dev                   lib    media   product_name  sbin  usr
boot   docker-entrypoint.sh  lib32  mnt     product_uuid  srv   var
certs  etc                   lib64  opt     root          sys
```

Or you can send signals to the process even if the container does not have the `kill` command:

```console
$ sudo kill -STOP 1123824
```

Or you can use `nsenter` to enter the network namespace of the process to run `wireshark`:

```console
$ sudo nsenter --target $(./kind-ps.py contour-worker envoy | jq -r '.[0].pids[0].pid') --net wireshark -i any -k
```
