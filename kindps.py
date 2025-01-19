#!/usr/bin/env python3
#
# Copyright Tero Saarni - https://github.com/tsaarni/kind-ps/
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

"""Find host PIDs for processes in Kind cluster"""

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import textwrap
from datetime import datetime
from typing import Dict, List

__version__ = "0.1.0"


logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)


def get_docker_containers(filter: str) -> List[dict]:
    """Get Docker containers that match the filter."""
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
        raise subprocess.CalledProcessError(result.returncode, result.args, output=result.stdout, stderr=result.stderr)

    containers = [json.loads(line) for line in result.stdout.splitlines()]
    logging.debug(json.dumps(containers))

    if not containers:
        raise ValueError(f"No containers found for filter: {filter}")

    return containers


def exec_in_docker(container_id: str, command: List[str]) -> str:
    """Execute a command in a Docker container."""
    cmd = ["docker", "exec", container_id, *command]

    logging.debug(f"Executing: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, result.args, output=result.stdout, stderr=result.stderr)

    return result.stdout


def get_cri_containers(container_id: str) -> List[dict]:
    """Use crictl to get containers in the Kind container."""
    result = exec_in_docker(container_id, ["crictl", "ps", "--output", "json"])

    doc = json.loads(result)

    containers = [container for container in doc["containers"]]
    logging.debug(json.dumps(containers))

    return containers


def get_cri_pods(container_id: str, pod_filter: str) -> List[dict]:
    """Use crictl to get pods in the Kind container that match the filter."""
    result = exec_in_docker(container_id, ["crictl", "pods", "--output", "json", "--name", pod_filter])

    doc = json.loads(result)

    pods = [pod for pod in doc["items"] if pod["state"] == "SANDBOX_READY"]
    logging.debug(json.dumps(pods))

    return pods


def get_cri_images(container_id: str) -> dict:
    """Use crictl to get container images in the Kind container."""
    stdout = exec_in_docker(container_id, ["crictl", "images", "--output", "json"])

    doc = json.loads(stdout)
    logging.debug(json.dumps(doc, separators=(",", ":")))

    images = {}
    for image in doc["images"]:
        images[image["id"]] = {
            "tags": image["repoTags"] + image["repoDigests"],
        }

    return images


def get_host_pids(container_id: str, pod_container_id: str) -> List[dict]:
    """Uses the cgroup filesystem to find container PIDs on the host."""
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


def tabular_print(containers: List[dict]) -> None:
    """Print containers and processes in a tabular format."""
    if not containers:
        print("No processes found")
        return

    terminal_width = shutil.get_terminal_size().columns
    wrap_width = terminal_width - 16

    containers_formatted = [tabular_format_container(process, wrap_width) for process in containers]

    num_processes = sum(len(process["pids"]) for process in containers)

    print("Containers:")
    print("\n\n".join(containers_formatted))
    print(f"\nSummary:\n  Containers: {len(containers)}\n  Processes:  {num_processes}")


def tabular_format_processes(pids: List[Dict], wrap_width: int) -> str:
    """Format processes in a tabular format."""
    return "\n".join(
        f"""    Process:
      pid:    {pid_info["pid"]}
      cmd:    {textwrap.fill(pid_info["cmd"], width=wrap_width, subsequent_indent=" " * 14)}"""
        for pid_info in pids
    )


def tabular_format_labels(labels: Dict[str, str]) -> str:
    """Format labels in a tabular format."""
    return "\n".join([f"      {key}: {value}" for key, value in labels.items()])


def tabular_format_container(process: Dict, wrap_width: int) -> str:
    """Format a container and its processes in a tabular format."""
    return f"""  {process["container"]}:
    Pod:      {process["pod"]}
    Node:     {process["node"]}
{tabular_format_processes(process["pids"], wrap_width)}
    Image:    {process["image"]}
    Created:  {process["created"]}
    Labels:
{tabular_format_labels(process["labels"])}"""


def get_containers(kind_container: Dict, pod_filter: str) -> List[Dict]:
    """Get info about containers and their processes within pods in the Kind cluster."""
    try:
        images = get_cri_images(kind_container["ID"])
        pods = get_cri_pods(kind_container["ID"], pod_filter)
        pod_containers = get_cri_containers(kind_container["ID"])
    except Exception as e:
        print(f"Failed to get info from Kind container {kind_container['ID']}: {e}", file=sys.stderr)
        sys.exit(1)

    containers = []
    for pod in pods:
        for pod_container in pod_containers:
            if pod_container["podSandboxId"] != pod["id"]:
                continue
            containers.append(
                {
                    "node": kind_container["Names"],
                    "pod": pod["metadata"]["name"],
                    "container": pod_container["metadata"]["name"],
                    "image": images[pod_container["imageRef"]]["tags"][0],
                    "created": datetime.fromtimestamp(int(pod_container["createdAt"]) / 1_000_000_000).isoformat(),
                    "pids": get_host_pids(kind_container["ID"], pod_container["id"]),
                    "labels": {k: v for k, v in pod["labels"].items() if not k.startswith("io.kubernetes.pod.")},
                }
            )

    return containers


def main() -> None:
    parser = argparse.ArgumentParser(description="Find host PIDs for processes in Kind cluster")
    parser.add_argument("docker_filter", help="filter for Kind Docker container names")
    parser.add_argument("pod_filter", nargs="?", default="", help="optional filter for pod names")
    parser.add_argument(
        "-o", "--output", choices=["tabular", "json"], default="tabular", help="output format (default: tabular)"
    )
    parser.add_argument("--debug", action="store_true", help="activate debug logging")
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Get Docker containers for Kind.
    try:
        kind_containers = get_docker_containers(args.docker_filter)
    except Exception as e:
        print(f"Failed to get Kind containers: {e}", file=sys.stderr)
        sys.exit(1)

    # Get processes running in containers within pods in the Kind cluster.
    containers = []
    for kind_container in kind_containers:
        containers.extend(get_containers(kind_container, args.pod_filter))

    if args.output == "json":
        print(json.dumps(containers, indent=2))
    else:
        tabular_print(containers)


if __name__ == "__main__":
    main()
