#!/usr/bin/env python3
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from typing import List

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)


def get_docker_containers(filter: str) -> List[dict]:
    cmd = [
        "docker",
        "ps",
        "--no-trunc",
        "--format",
        "json",
        "--filter",
        f"name={filter}",
    ]

    logging.debug(f"Executing: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        logging.error(f"Command failed ({result.returncode}): {result.stderr}")
        raise subprocess.CalledProcessError(result.returncode, result.args, output=result.stdout, stderr=result.stderr)

    containers = []
    for line in result.stdout.splitlines():
        doc = json.loads(line)
        containers.append(doc)
    logging.debug(f"Found {len(containers)} containers")

    return containers


def exec_in_docker(container_id: str, command: List[str]) -> str:
    cmd = ["docker", "exec", container_id, *command]

    logging.debug(f"Executing: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        logging.error(f"Command failed ({result.returncode}): {result.stderr}")
        raise subprocess.CalledProcessError(result.returncode, result.args, output=result.stdout, stderr=result.stderr)

    return result.stdout


def get_cri_containers(container_id: str) -> List[dict]:
    result = exec_in_docker(container_id, ["crictl", "ps", "--output", "json"])

    doc = json.loads(result)

    containers = []
    for container in doc["containers"]:
        containers.append(container)

    logging.debug(containers)

    return containers


def get_cri_pods(container_id: str, pod_filter: str) -> List[dict]:
    result = exec_in_docker(container_id, ["crictl", "pods", "--output", "json", "--name", pod_filter])

    doc = json.loads(result)

    pods = []
    for pod in doc["items"]:
        if pod["state"] == "SANDBOX_READY":
            pods.append(pod)

    logging.debug(pods)

    return pods


def get_host_pids(container_id: str, pod_container_id: str) -> List[dict]:
    docker_cgroup_path = f"/sys/fs/cgroup/system.slice/docker-{container_id}.scope"
    kubelet_cgroup_path = f"{docker_cgroup_path}/kubelet.slice/kubelet-kubepods.slice"

    logging.debug(f"Reading cgroup {kubelet_cgroup_path} for pod container {pod_container_id}")
    pids = []
    for root, _, files in os.walk(kubelet_cgroup_path):
        for file in files:
            if pod_container_id in root and file == "cgroup.procs":
                cgroup_procs_path = os.path.join(root, file)
                with open(cgroup_procs_path, "r") as f:
                    for pid in f.read().splitlines():
                        with open(f"/proc/{pid}/cmdline", "r") as f:
                            cmdline = f.read().replace("\x00", " ").strip()
                            pids.append({"pid": pid, "cmd": cmdline})

    return pids


def get_images_on_kind_container(container_id: str) -> dict:
    stdout = exec_in_docker(container_id, ["crictl", "images", "--output", "json"])

    doc = json.loads(stdout)

    images = {}
    for image in doc["images"]:
        images[image["id"]] = {
            "tags": image["repoTags"],
        }

    return images


def main(args):

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    kind_containers = get_docker_containers(args.docker_filter)

    processes = []
    for kind_container in kind_containers:
        images = get_images_on_kind_container(kind_container["ID"])

        pods = get_cri_pods(kind_container["ID"], args.pod_filter)
        pod_containers = get_cri_containers(kind_container["ID"])
        for pod in pods:
            for pod_container in [c for c in pod_containers if c["podSandboxId"] == pod["id"]]:
                processes.append(
                    {
                        "node": kind_container["Names"],
                        "pod": pod["metadata"]["name"],
                        "container": pod_container["metadata"]["name"],
                        "image": images[pod_container["imageRef"]],
                        "created": datetime.fromtimestamp(int(pod_container["createdAt"]) / 1_000_000_000).isoformat(),
                        "pids": get_host_pids(kind_container["ID"], pod_container["id"]),
                        "labels": {k: v for k, v in pod["labels"].items() if not k.startswith("io.kubernetes.pod.")},
                    }
                )

    print(json.dumps(processes, indent=2))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Get host PIDs for processes within a Kind cluster")
    parser.add_argument("docker_filter", help="Filter to include specific Kind Docker containers")
    parser.add_argument("pod_filter", nargs="?", default="", help="Optional filter to include specific Pods")
    parser.add_argument("--debug", action="store_true", help="Activate debug logging")

    args = parser.parse_args()
    main(args)
