#!/usr/bin/env python3
"""Bounded temporary secure-GPU continuation with private downloads and deletion.

Default is a read-only quote. --launch uses only this invocation's pod; its ID
and non-secret recovery metadata are saved before polling. No network volume,
production endpoint, account webhook or other pod is modified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shlex
import signal
import time
from pathlib import Path

import requests

IMAGE = "pytorch/pytorch@sha256:b574d4ccf6d8856a5d87dcadc667aa4f95dc18d337ef3a28d02b7b01897d7081"
GPUS = ["NVIDIA A100 80GB PCIe", "NVIDIA A100-SXM4-80GB", "NVIDIA GeForce RTX 4090"]
LIFECYCLE_SECONDS = 7200
MAX_HOURLY = 1.65  # Advertised A100 plus disposable disk; retains $1.70 reserve.


def graphql(session, query):
    response = session.post("https://api.runpod.io/graphql", json={"query": query}, timeout=40)
    response.raise_for_status()
    result = response.json()
    if result.get("errors"):
        # API response bodies may echo submitted environment variables.
        raise RuntimeError("RunPod GraphQL operation rejected")
    return result["data"]


def deploy_query(name, gpu, revision, job_token):
    bootstrap = (
        "import urllib.request,runpy;"
        f"urllib.request.urlretrieve('https://raw.githubusercontent.com/CodeWithJuber/mizan/{revision}/scripts/runpod_training_job.py','/tmp/ruh-job.py');"
        "runpy.run_path('/tmp/ruh-job.py',run_name='__main__')"
    )
    command = "python -u -c " + shlex.quote(bootstrap)
    environment = {
        "RUH_JOB_TOKEN": job_token,
        "RUH_REVISION": revision,
        "KAGGLE_API_TOKEN": os.environ["KAGGLE_API_TOKEN"],
    }
    env_text = ",".join(
        "{key:" + json.dumps(key) + ",value:" + json.dumps(value) + "}"
        for key, value in environment.items()
    )
    return f"""mutation {{ podFindAndDeployOnDemand(input:{{
      name:{json.dumps(name)},imageName:{json.dumps(IMAGE)},cloudType:SECURE,
      gpuTypeId:{json.dumps(gpu)},gpuCount:1,
      volumeInGb:0,containerDiskInGb:40,minVcpuCount:8,minMemoryInGb:32,
      supportPublicIp:false,startSsh:false,ports:"8080/http",dockerArgs:{json.dumps(command)},
      env:[{env_text}]
    }}) {{ id name costPerHr gpuCount containerDiskInGb desiredStatus }} }}"""


def own_pod(session, pod_id):
    pods = graphql(session, "query { myself { pods { id name costPerHr desiredStatus } } }")[
        "myself"
    ]["pods"]
    return next((pod for pod in pods if pod["id"] == pod_id), None)


def delete_and_verify(session, pod_id):
    for attempt in range(6):
        if own_pod(session, pod_id) is None:
            return
        try:
            graphql(session, "mutation { podTerminate(input:{podId:" + json.dumps(pod_id) + "}) }")
        except (requests.RequestException, RuntimeError):
            if attempt == 5:
                raise
        time.sleep(5)
    if own_pod(session, pod_id) is not None:
        raise RuntimeError("Temporary pod deletion not verified; use the saved pod ID")


def download_artifacts(session, url, output, artifacts, deadline):
    for name, expected in artifacts.items():
        destination = (output / name).resolve()
        if not destination.is_relative_to(output.resolve()):
            raise ValueError("Unsafe artifact path")
        destination.parent.mkdir(parents=True, exist_ok=True)
        hasher, count = hashlib.sha256(), 0
        with session.get(url + "/artifact/" + name, stream=True, timeout=(30, 60)) as response:
            response.raise_for_status()
            with destination.open("wb") as handle:
                for block in response.iter_content(1024 * 1024):
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Artifact download reached the pod lifecycle limit")
                    handle.write(block)
                    hasher.update(block)
                    count += len(block)
        if count != expected["bytes"] or hasher.hexdigest() != expected["sha256"]:
            raise ValueError("Downloaded artifact digest mismatch")


def launch(session, revision, output):
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    deadline = started + LIFECYCLE_SECONDS
    pod_id, recovery = None, {"revision": revision, "image": IMAGE, "promotion_approved": False}
    job_session = requests.Session()
    token = secrets.token_urlsafe(32)
    job_session.headers["Authorization"] = "Bearer " + token

    def interrupted(signum, frame):
        raise KeyboardInterrupt("Termination requested")

    previous_handler = signal.signal(signal.SIGTERM, interrupted)
    try:
        for gpu in GPUS:
            try:
                pod = graphql(
                    session,
                    deploy_query(
                        "ruh-v2-continuation-" + secrets.token_hex(4), gpu, revision, token
                    ),
                )["podFindAndDeployOnDemand"]
            except RuntimeError:
                print(json.dumps({"gpu": gpu, "placement": "unavailable"}), flush=True)
                continue
            pod_id = pod["id"]
            recovery.update(
                pod_id=pod_id, gpu_type=gpu, hourly_usd=float(pod["costPerHr"]), pod_deleted=False
            )
            (output / "pod-recovery.json").write_text(json.dumps(recovery, indent=2))
            print(json.dumps(recovery), flush=True)
            break
        if pod_id is None:
            raise RuntimeError("No approved secure GPU available")
        if recovery["hourly_usd"] > MAX_HOURLY or recovery["hourly_usd"] * 2 > 5:
            raise ValueError("Actual allocated rate exceeds the approved spending guard")
        url = f"https://{pod_id}-8080.proxy.runpod.net"
        previous = None
        while time.monotonic() < deadline - 240:
            try:
                response = job_session.get(url + "/status", timeout=30)
                response.raise_for_status()
                status = response.json()
            except (requests.RequestException, ValueError):
                time.sleep(15)
                continue
            (output / "latest-status.json").write_text(json.dumps(status, indent=2))
            summary = {key: status[key] for key in ("phase", "gpu", "torch") if key in status}
            if status.get("log_tail"):
                summary["log_tail"] = status["log_tail"][-500:]
            serialized = json.dumps(summary)
            if serialized != previous:
                print(serialized, flush=True)
                previous = serialized
            if status["phase"] == "failed":
                raise RuntimeError(
                    "Private training job failed: " + status.get("error_type", "unknown")
                )
            if status["phase"] == "complete":
                download_artifacts(job_session, url, output, status["artifacts"], deadline - 30)
                recovery["artifacts_verified"] = True
                break
            time.sleep(15)
        else:
            raise TimeoutError("Training did not finish within the lifecycle budget")
    finally:
        try:
            if pod_id is not None:
                delete_and_verify(session, pod_id)
                recovery.update(pod_deleted=True, lifecycle_seconds=time.monotonic() - started)
                recovery["maximum_compute_cost_usd"] = (
                    recovery["hourly_usd"] * recovery["lifecycle_seconds"] / 3600
                )
                (output / "pod-recovery.json").write_text(json.dumps(recovery, indent=2))
                print(
                    json.dumps(
                        {
                            "pod_id": pod_id,
                            "deleted_verified": True,
                            "maximum_compute_cost_usd": recovery["maximum_compute_cost_usd"],
                        }
                    ),
                    flush=True,
                )
        finally:
            signal.signal(signal.SIGTERM, previous_handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--launch", action="store_true")
    args = parser.parse_args()
    if len(args.revision) != 40 or any(char not in "0123456789abcdef" for char in args.revision):
        raise ValueError("An exact reviewed commit is required")
    from runpod.user_agent import USER_AGENT

    session = requests.Session()
    session.headers.update(
        {
            "Authorization": "Bearer "
            + (os.getenv("RUNPOD_API_KEY") or os.environ["RUNPOD_API_TOKEN"]),
            "User-Agent": USER_AGENT,
        }
    )
    if not args.launch:
        prices = graphql(session, "query { gpuTypes { id securePrice } }")["gpuTypes"]
        print(
            json.dumps(
                {
                    "launch": False,
                    "gpu_prices": [row for row in prices if row["id"] in GPUS],
                    "lifecycle_seconds": LIFECYCLE_SECONDS,
                    "maximum_hourly_usd": MAX_HOURLY,
                    "spending_cap_usd": 5,
                    "private": True,
                    "promotion_approved": False,
                },
                indent=2,
            )
        )
        return
    launch(session, args.revision, args.output)


if __name__ == "__main__":
    main()
