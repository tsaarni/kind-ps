#!/usr/bin/env python3

import json
import os
import subprocess
from typing import List
import logging
import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def find_kind_containers(filter: str) -> dict:
    logging.debug(f"Executing: docker ps --no-trunc --format json --filter name={filter}")
    result = subprocess.run(
        ["docker", "ps", "--no-trunc", "--format", "json", "--filter", f"name={filter}"],
        capture_output=True,
        text=True
    )

    containers = {}
    if result.returncode == 0:
        for line in result.stdout.splitlines():
            container = json.loads(line)
            containers[container["ID"]] = container
        logging.debug(f"Found {len(containers)} containers")
    else:
        logging.error(f"Failed to find containers: {result.stderr}")

    return containers

def exec_in_docker(container_id: str, command: List[str]) -> str:
    logging.debug(f"Executing: docker exec {container_id} {' '.join(command)}")
    result = subprocess.run(
        ["docker", "exec", container_id, *command],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        logging.error(f"Command failed: {result.stderr}")
        raise subprocess.CalledProcessError(result.returncode, result.args, output=result.stdout, stderr=result.stderr)

    return result.stdout

def get_pod_containers(container: str, filter: str) -> dict:
    stdout = exec_in_docker(container, ["crictl", "ps", "--output", "json", "--name", filter])

    doc = json.loads(stdout)
    containers = {}
    for container in doc["containers"]:
        containers[container["id"]] = container
    logging.debug(f"Found {len(containers)} pod containers")
    return containers

def get_pids(container_id: str, pod_container_id: str) -> List[dict]:
    docker_cgroup_path = f"/sys/fs/cgroup/system.slice/docker-{container_id}.scope"
    kubelet_cgroup_path = f"{docker_cgroup_path}/kubelet.slice/kubelet-kubepods.slice"

    logging.debug(f"Reading cgroup {kubelet_cgroup_path} for pod container {pod_container_id}")
    pids = []
    for root, dirs, files in os.walk(kubelet_cgroup_path):
        for file in files:
            if pod_container_id in root and file == "cgroup.procs":
                cgroup_file = os.path.join(root, file)
                with open(cgroup_file, "r") as f:
                    for pid in f.read().splitlines():
                        cmdline = open(f"/proc/{pid}/cmdline", "r").read().replace("\x00", " ")
                        pids.append({"pid": pid, "cmd": cmdline})

    return pids

def get_images(container_id: str) -> dict:
    stdout = exec_in_docker(container_id, ["crictl", "images", "--output", "json"])

    doc = json.loads(stdout)
    images = {}
    for image in doc["images"]:
        tags = []
        if "repoTags" in image:
            tags.append(image["repoTags"])
        elif "repoDigests" in image:
            tags.append(image["repoDigests"])

        images[image["id"]] = {
            "tags": tags,
        }
    return images



def main(args):

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    result = {}

    containers = find_kind_containers(args.filter)
    for container_id, container in containers.items():
        images = get_images(container_id)
        pods = []
        pod_containers = get_pod_containers(container_id, args.pod or "")
        for pod_container_id, pod_container in pod_containers.items():
            pod_container = {
                "name": pod_container["metadata"]["name"],
                "image": images[pod_container["imageRef"]],
                "state": pod_container["state"],
                "created": datetime.datetime.fromtimestamp(int(pod_container["createdAt"]) / 1_000_000_000).isoformat(),
                "pids": get_pids(container_id, pod_container_id)
            }
            pods.append(pod_container)
        result[container["Names"]] = pods

    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Find kind containers")
    parser.add_argument("filter", help="Filter for container names")
    parser.add_argument("pod", nargs="?", help="Optional filter for pod names")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()
    main(args)
