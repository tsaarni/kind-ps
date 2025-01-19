# Find host PIDs for processes in Kind cluster

## Introduction

This Python script identifies the host PID for a process running inside a pod in a [Kind](https://kind.sigs.k8s.io/) Kubernetes cluster.
It uses `docker exec` to execute [`crictl`](https://kubernetes.io/docs/tasks/debug/debug-cluster/crictl/) on the Kind node to list the pods and containers running on the node.
It then navigates through `/sys/fs/cgroup/` and the nested cgroups to find the host PIDs.
Finally `/proc/` is used to get the process details.

The script requires only Python and does not depend on any external packages.
Since it directly accesses the `cgroup` and `proc` filesystems, it works only on Linux hosts where `kind` is executed and is not compatible with MacOS.


```
usage: kindps [-h] [-o {tabular,json}] [--debug] [-v] docker_filter [pod_filter]

Find host PIDs for processes in Kind cluster

positional arguments:
  docker_filter         filter for Kind Docker container names
  pod_filter            optional filter for pod names

options:
  -h, --help            show this help message and exit
  -o {tabular,json}, --output {tabular,json}
                        output format (default: tabular)
  --debug               activate debug logging
  -v, --version         show program's version number and exit
```

## Installation

Either download [`kindps.py`](kindps.py) or install as a Python package:

```
pip install kindps
```

## Example usage

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

To list the containers running in pods that contain `envoy` in their names and are running on nodes that contain `contour` in their names, run:

```console
$ kindps contour envoy
```

Result is printed in tabular format by default:

```console
Containers:
  envoy:
    Pod:      envoy-z5lp9
    Node:     contour-worker
    Process:
      pid:    2367787
      cmd:    envoy -c /config/envoy.json --service-cluster projectcontour --service-node
              envoy-z5lp9 --log-level info
    Image:    docker.io/envoyproxy/envoy:v1.31.5
    Created:  2025-01-18T10:37:07.655928
    Labels:
      app: envoy
      controller-revision-hash: dd8c68b4b
      pod-template-generation: 1

  shutdown-manager:
    Pod:      envoy-z5lp9
    Node:     contour-worker
    Process:
      pid:    2367735
      cmd:    /bin/contour envoy shutdown-manager
    Image:    ghcr.io/projectcontour/contour:v1.30.2
    Created:  2025-01-18T10:37:07.511818
    Labels:
      app: envoy
      controller-revision-hash: dd8c68b4b
      pod-template-generation: 1

Summary:
  Containers: 2
  Processes:  2
```

To get JSON format output, include the `--output json` option:

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

The PIDs listed are the host PIDs for the processes running inside the containers.
These PIDs can be used on the host to access the process:

```console
$ ps 2367787
    PID TTY      STAT   TIME COMMAND
2367787 ?        Ssl    0:00 envoy -c /config/envoy.json --service-cluster projectcontour
                             --service-node envoy-z5lp9 --log-level info
```

For example, to access the root filesystem of the container:

```console
$ sudo ls /proc/2367787/root/
admin  config                home   libx32  proc          run   tmp
bin    dev                   lib    media   product_name  sbin  usr
boot   docker-entrypoint.sh  lib32  mnt     product_uuid  srv   var
certs  etc                   lib64  opt     root          sys
```

To send a signal to the process, even if the container lacks the `kill` command:

```console
$ sudo kill -STOP 2367787
```

Alternatively, `nsenter` can be used to enter the network namespace of the process to run `wireshark`:

```console
$ sudo nsenter \
    --target $(kindps contour-worker envoy --output json | jq -r '.[0].pids[0].pid') \
    --net wireshark -i any -k
```
