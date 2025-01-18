# Get host PIDs for processes within a Kind cluster

## Introduction

This Python script identifies the host PID for a process running inside a pod in a [Kind](https://kind.sigs.k8s.io/) Kubernetes cluster.
It uses `docker exec` to run [`crictl`](https://kubernetes.io/docs/tasks/debug/debug-cluster/crictl/) on the Kind node to list the pods and containers running on the node.
It then navigates through `/sys/fs/cgroup/` and the nested cgroups to find the host PIDs.
Finally `/proc/` is used to retrieve the process details.

The script requires only Python and does not depend on any external packages.
Since it directly accesses the `cgroup` and `proc` filesystems, it works only on Linux hosts where `kind` is executed and is not compatible with MacOS.

## Usage

```
usage: kindps [-h] [--debug] [--version] docker_filter [pod_filter]

get host PIDs for processes within a Kind cluster

positional arguments:
  docker_filter  filter which Kind Docker containers are queried
  pod_filter     optional filter for pods

options:
  -h, --help     show this help message and exit
  --debug        activate debug logging
  --version      show program's version number and exit
```

## Installation

The script can either downloaded and executed directly or installed as a Python package

```
pip install kindps
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
$ docker ps --format "table {{.ID}}\t{{.Names}}"
CONTAINER ID   NAMES
992ec6ccbeed   contour-control-plane
22c9d82b69f2   contour-worker
```

To list the pods that match `envoy` and are running on the `contour-worker` node, run:

```console
$ kindps contour-worker envoy
```

Result is a JSON document

```json
[
  {
    "node": "contour-worker",
    "pod": "envoy-z5lp9",
    "container": "envoy",
    "image": "docker.io/envoyproxy/envoy:v1.31.5",
    "created": "2025-01-18T10:37:07.655928",
    "pids": [
      {
        "pid": "2367787",
        "cmd": "envoy -c /config/envoy.json --service-cluster projectcontour --service-node envoy-z5lp9 --log-level info"
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
    "pod": "envoy-z5lp9",
    "container": "shutdown-manager",
    "image": "ghcr.io/projectcontour/contour:v1.30.2",
    "created": "2025-01-18T10:37:07.511818",
    "pids": [
      {
        "pid": "2367735",
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
You can use these PIDs on the host:

```console
$ ps 2367787
    PID TTY      STAT   TIME COMMAND
2367787 ?        Ssl    0:00 envoy -c /config/envoy.json --service-cluster projectcontour --service-node envoy-z5lp9 --log-level info
```

Now, you can use the PID to access the root filesystem of the container from the host.

```console
$ sudo ls /proc/2367787/root/
admin  config                home   libx32  proc          run   tmp
bin    dev                   lib    media   product_name  sbin  usr
boot   docker-entrypoint.sh  lib32  mnt     product_uuid  srv   var
certs  etc                   lib64  opt     root          sys
```

Or you can send signals to the process even if the container does not have the `kill` command:

```console
$ sudo kill -STOP 2367787
```

Or you can use `nsenter` to enter the network namespace of the process to run `wireshark`:

```console
$ sudo nsenter --target $(kindps contour-worker envoy | jq -r '.[0].pids[0].pid') --net wireshark -i any -k
```
