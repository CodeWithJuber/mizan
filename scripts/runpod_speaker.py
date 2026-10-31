#!/usr/bin/env python3
"""Launch the Ruh speaker pilot on RunPod: one pod, one run, a spending cap.

The default is a dry run: it prints the requests it would send, with the API
key and any token redacted, and sends nothing. ``--launch`` sends them, and
only after a smoke launch has shown the pod can end itself (``--smoke``).
The pre-registered plan is ``docs/ruh-speaker.md``.

    python scripts/runpod_speaker.py --revision <40-hex commit> \\
        --confirm-budget 25 --return volume --network-volume <id> --data-center <id>
    python scripts/runpod_speaker.py ... --return hf --hf-repo <owner>/<private repo>

**The budget.** ``--confirm-budget USD`` is required and at most $25 for this
first run. The pod's whole life is bounded by it: lifetime = (budget − a
safety margin) / (the GPU's hourly price + its container disk's) in seconds,
counted from before the pod is created. Three things end the pod by then:

1. this launcher deletes it at the deadline (or as soon as it exits, fails,
   or this process is interrupted), and checks it is gone;
2. a watchdog inside the pod deletes it at the same deadline with the
   pod-scoped key RunPod gives every pod (``RUNPOD_API_KEY`` there; this
   launcher never sends the owner's key into the pod);
3. the training itself stops early enough to write its final weights.

RunPod does not document what the pod-scoped key may do ("Pod-scoped API
key"), so ``--smoke`` first runs a 10-minute pod that only tries to delete
itself, and ``--launch`` refuses until a smoke record says it could.

**The API** (read 31 Oct 2026). RunPod's REST API v1 (``rest.runpod.io/v1``)
is deprecated and retired on 15 November 2026
(https://docs.runpod.io/api-reference/overview), so this uses v2
(https://docs.runpod.io/api-reference-v2/overview, OpenAPI at
https://api.runpod.io/v2/openapi.json, version 2.0.0), not the v1/GraphQL
calls of ``scripts/launch_runpod_training.py``:

- ``POST /v2/pods`` creates a pod; ``name`` required, ``gpu`` {``id``,
  ``count``, ``minCudaVersion``, ``minVcpuCountPerGpu``, ``minRamPerGpu``},
  ``image``, ``entrypoint``, ``disk``, ``env``, ``ports``, ``cloud``,
  ``dataCenterIds``, ``mounts.network`` [{``volumeId``, ``path``}]; it places
  one GPU type and never falls back
  (https://docs.runpod.io/api-reference-v2/pods/create-a-pod);
- ``GET /v2/pods/{id}``: ``status`` (PROVISIONING, STARTING, RUNNING, EXITED,
  ERROR, TERMINATED) and ``cost``, the hourly compute rate in USD
  (https://docs.runpod.io/api-reference-v2/pods/get-a-pod);
- ``DELETE /v2/pods/{id}`` terminates it, 204
  (https://docs.runpod.io/api-reference-v2/pods/terminate-a-pod);
- ``POST /v2/pods/{id}/action`` {``action``: stop | terminate | …}
  (https://docs.runpod.io/api-reference-v2/pods/trigger-a-pod-state-transition);
- ``GET /v2/catalog/gpus``: GPU types with ``price.secure``
  (https://docs.runpod.io/api-reference-v2/catalog/list-gpu-types);
- inside a pod: ``RUNPOD_POD_ID`` and ``RUNPOD_API_KEY``, "Pod-scoped API key"
  (https://docs.runpod.io/pods/references/environment-variables);
- billing by the second; container disk $0.10/GB/month while running, network
  volume $0.07/GB/month (https://docs.runpod.io/pods/pricing). Secure Cloud
  prices from https://www.runpod.io/pricing ("Updated October 8, 2026") are
  used for the dry run only; a launch reads the catalog and the pod's ``cost``.

``RUNPOD_API_KEY`` and ``HF_TOKEN`` are read from the environment and never
printed, logged or written. Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import secrets
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

API = "https://api.runpod.io/v2"
REPOSITORY = "CodeWithJuber/mizan"
# pytorch/pytorch:2.14.1-cuda12.6-cudnn9-runtime, pushed 30 Sep 2026 (Docker
# Hub); torch 2.14.1 is the version pyproject.toml pins.
IMAGE = "pytorch/pytorch@sha256:1262abc856a428933c0477b4be87079173a0b087b7691c47fcb396b7b5775c56"
CUDA = "12.6"
GPUS = (
    "NVIDIA A100 80GB PCIe",
    "NVIDIA A100-SXM4-80GB",
    "NVIDIA H100 PCIe",
    "NVIDIA H100 80GB HBM3",
)
DRY_RUN_PRICES = {  # Secure Cloud, runpod.io/pricing, updated 8 Oct 2026
    "NVIDIA A100 80GB PCIe": 1.79,
    "NVIDIA A100-SXM4-80GB": 1.79,
    "NVIDIA H100 PCIe": 2.89,
    "NVIDIA H100 80GB HBM3": 3.99,
    "NVIDIA GeForce RTX 4090": 0.89,
}
FIRST_RUN_CAP = 25.0
DISK_GB = 200  # sources (~22 GB of parquet), selected text, shards, checkpoints
DISK_USD_PER_GB_MONTH = 0.10
HOURS_PER_MONTH = 730.0
MIN_HOURS = 2.0  # less is not worth a pilot
PREP_SHARE = 0.30  # of the pod's life, at most, for selecting and tokenising
WRAP_SECONDS = 1200  # final evaluation, weights, upload, before the deadline
SMOKE_SECONDS = 600
PINS = ("tokenizers==0.23.3", "huggingface_hub==2.3.0", "pyarrow==25.0.1")
SMOKE_RECORD = Path.home() / ".mizan" / "ruh-speaker-smoke.json"


def safety(budget: float) -> float:
    """Dollars kept back: the seconds between a deadline and a confirmed
    deletion, and per-second rounding."""
    return max(0.25, 0.02 * budget)


def disk_hourly(gigabytes: int = DISK_GB) -> float:
    return gigabytes * DISK_USD_PER_GB_MONTH / HOURS_PER_MONTH


def lifetime(budget: float, hourly: float, gigabytes: int = DISK_GB) -> int:
    """Seconds the pod may live so that its compute and disk stay within the
    budget less the safety margin."""
    return max(0, math.floor((budget - safety(budget)) / (hourly + disk_hourly(gigabytes)) * 3600))


# ── HTTP ─────────────────────────────────────────────────────────────────


class Refused(RuntimeError):
    pass


def _request(method: str, url: str, key: str, body: dict | None = None) -> tuple[int, Any]:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)  # noqa: S310 - https constants
    request.add_header("Authorization", "Bearer " + key)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        # Error bodies may echo what was sent (the env holds a token): not shown.
        return error.code, None


def redacted(request: dict) -> dict:
    shown = json.loads(json.dumps(request))
    shown["headers"] = {"Authorization": "Bearer <redacted>"}
    env = (shown.get("body") or {}).get("env") or {}
    for name in env:
        if name in {"HF_TOKEN", "RUNPOD_API_KEY"}:
            env[name] = "<redacted>"
    return shown


# ── what runs inside the pod ─────────────────────────────────────────────

# The pod's first command: fetch the reviewed commit's source, check its
# SHA-256, and hand over to this file's ``pod`` command. On any failure it
# deletes its own pod rather than exit (an exited container may be restarted).
BOOTSTRAP = r"""
import hashlib, json, os, pathlib, sys, time, urllib.request, zipfile
def end():
    for method, path, body in (("DELETE", "", None), ("POST", "/action", {"action": "stop"})):
        try:
            data = json.dumps(body).encode() if body else None
            r = urllib.request.Request("https://api.runpod.io/v2/pods/" + os.environ["RUNPOD_POD_ID"] + path, data=data, method=method)
            r.add_header("Authorization", "Bearer " + os.environ["RUNPOD_API_KEY"])
            if data: r.add_header("Content-Type", "application/json")
            urllib.request.urlopen(r, timeout=60)
            return
        except Exception:
            pass
try:
    rev, want = os.environ["RUH_REVISION"], os.environ["RUH_SOURCE_SHA256"]
    root = pathlib.Path("/root/ruh-source"); root.mkdir(exist_ok=True)
    archive = root / (rev + ".zip")
    if not archive.exists():
        urllib.request.urlretrieve("https://codeload.github.com/__REPOSITORY__/zip/" + rev, archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != want:
        archive.unlink(); raise SystemExit("the source archive is not the pinned one")
    with zipfile.ZipFile(archive) as bundle:
        for name in bundle.namelist():
            if not (root / name).resolve().is_relative_to(root.resolve()):
                raise SystemExit("unsafe path in the source archive")
        bundle.extractall(root)
    script = next(root.glob("*-" + rev)) / "scripts" / "runpod_speaker.py"
    os.execv(sys.executable, [sys.executable, str(script), "pod"])
except BaseException as error:
    print("bootstrap failed:", type(error).__name__, error, flush=True)
    end(); time.sleep(3600)
""".replace("__REPOSITORY__", REPOSITORY)

# The smoke pod: wait, then try to delete itself, as the real pod's watchdog will.
SMOKE = BOOTSTRAP.split("\ntry:\n", 1)[0] + "\ntime.sleep(90); end(); time.sleep(3600)\n"


def end_this_pod() -> bool:
    """Delete this pod with its own pod-scoped key, or at least stop it."""
    pod, key = os.environ.get("RUNPOD_POD_ID"), os.environ.get("RUNPOD_API_KEY")
    if not pod or not key:
        return False
    status, _ = _request("DELETE", f"{API}/pods/{pod}", key)
    if status in (200, 202, 204):
        return True
    status, _ = _request("POST", f"{API}/pods/{pod}/action", key, {"action": "stop"})
    return status in (200, 202, 204)


def _status(work: Path, phase: str, **extra: Any) -> None:
    value = {"phase": phase, "at": time.time(), **extra}
    (work / "status.json").write_text(json.dumps(value, indent=1), encoding="utf-8")
    print(json.dumps(value), flush=True)


def _run(command: list[str], *, cwd: Path, deadline: float, env: dict | None = None) -> None:
    left = deadline - time.time()
    if left <= 60:
        raise TimeoutError("no time left for: " + " ".join(command[:4]))
    subprocess.run(command, cwd=cwd, env=env, check=True, timeout=left)


def upload_to_hf(repo: str, folders: list[Path]) -> None:
    """The final weights and reports to the owner's private repository; a
    repository that is not private is refused."""
    from huggingface_hub import HfApi

    api = HfApi(token=os.environ["HF_TOKEN"])
    api.create_repo(repo, repo_type="model", private=True, exist_ok=True)
    if not api.repo_info(repo, repo_type="model").private:
        raise Refused(f"{repo} is not private; nothing was uploaded")
    for folder in folders:
        api.upload_folder(folder_path=str(folder), repo_id=repo, path_in_repo=folder.name)


def pod_main() -> int:
    """Inside the pod: install, prepare the shards (at most ``PREP_SHARE`` of
    the life), train until ``WRAP_SECONDS`` before the deadline, return the
    weights, then delete the pod. A restarted container resumes: shards that
    verify are kept, and training continues from its last whole checkpoint."""
    deadline = float(os.environ["RUH_DEADLINE_EPOCH"])
    work = Path(os.environ.get("RUH_WORK", "/root/ruh-speaker"))
    work.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).resolve().parent.parent
    backend = source / "backend"

    def watchdog() -> None:
        time.sleep(max(0.0, deadline - time.time()))
        _status(work, "deadline")
        end_this_pod()
        os._exit(3)

    threading.Thread(target=watchdog, daemon=True).start()
    python = sys.executable
    env = dict(os.environ, MIZAN_DATA_DIR=str(work / "data"), PYTHONUNBUFFERED="1")
    env.pop("HF_TOKEN", None)  # only the upload needs it
    try:
        _status(work, "install")
        _run(
            [python, "-m", "pip", "install", "--no-cache-dir", "-e", f"{source}[ml]", *PINS],
            cwd=source,
            deadline=deadline,
            env=env,
        )
        shards, run = work / "shards", work / "run"
        verify = subprocess.run(
            [python, "-m", "tadbir.ruh_reader.speaker", "verify", "--shards", str(shards)],
            cwd=backend,
            env=env,
            capture_output=True,
        )
        if verify.returncode != 0:
            _status(work, "prepare")
            _run(
                [
                    python,
                    "-m",
                    "tadbir.ruh_reader.speaker",
                    "prepare",
                    "--plan",
                    "pilot",
                    "--out",
                    str(shards),
                    "--workers",
                    str(os.cpu_count() or 1),
                    "--seconds",
                    str(int(PREP_SHARE * (deadline - time.time()))),
                ],
                cwd=backend,
                deadline=deadline,
                env=env,
            )
        seconds = int(deadline - time.time() - WRAP_SECONDS)
        _status(work, "train", seconds=seconds)
        if seconds > 600:
            _run(
                [
                    python,
                    "-m",
                    "tadbir.ruh_reader.speaker",
                    "train",
                    "--shards",
                    str(shards),
                    "--out",
                    str(run),
                    "--seconds",
                    str(seconds),
                ],
                cwd=backend,
                deadline=deadline - 300,
                env=env,
            )
        if os.environ.get("RUH_RETURN") == "hf":
            _status(work, "upload")
            (run / "final" / "shards.json").write_bytes((shards / "shards.json").read_bytes())
            upload_to_hf(os.environ["RUH_HF_REPO"], [run / "final"])
        _status(work, "done")
    except BaseException as error:  # the pod is ended whatever went wrong
        _status(work, "failed", error=type(error).__name__)
    end_this_pod()
    time.sleep(max(60.0, deadline - time.time()))
    return 0


# ── the launcher ─────────────────────────────────────────────────────────


def pod_request(args: argparse.Namespace, source_sha256: str, deadline: str) -> dict:
    """The create request. The smoke pod asks for no volume, no token and no
    placement filters: it only has to start and end itself."""
    body: dict[str, Any] = {
        "name": f"ruh-speaker-{'smoke' if args.smoke else 'pilot'}-{secrets.token_hex(4)}",
        "cloud": "SECURE",
        "gpu": {"id": args.gpu, "count": 1},
        "image": IMAGE,
        "entrypoint": ["python", "-c", SMOKE if args.smoke else BOOTSTRAP],
        "disk": 20 if args.smoke else DISK_GB,
        "ports": [],
    }
    if args.smoke:
        return {"method": "POST", "url": f"{API}/pods", "body": body}
    body["gpu"].update(minCudaVersion=CUDA, minVcpuCountPerGpu=16, minRamPerGpu=64)
    env = {
        "RUH_REVISION": args.revision,
        "RUH_SOURCE_SHA256": source_sha256,
        "RUH_DEADLINE_EPOCH": deadline,
        "RUH_RETURN": args.ret,
        "RUH_PLAN": "pilot",
        "RUH_WORK": "/workspace/ruh-speaker" if args.ret == "volume" else "/root/ruh-speaker",
    }
    body["env"] = env
    if args.ret == "hf":
        env["RUH_HF_REPO"] = args.hf_repo
        env["HF_TOKEN"] = os.environ.get("HF_TOKEN", "")
    else:
        body["mounts"] = {"network": [{"volumeId": args.network_volume, "path": "/workspace"}]}
        body["dataCenterIds"] = [args.data_center]
    return {"method": "POST", "url": f"{API}/pods", "body": body}


def parser() -> argparse.ArgumentParser:
    found = argparse.ArgumentParser(description="Launch the Ruh speaker pilot on RunPod")
    found.add_argument("--revision", required=True, help="the reviewed commit, 40 hex digits")
    found.add_argument("--confirm-budget", type=float, required=True, metavar="USD")
    found.add_argument("--return", dest="ret", choices=("hf", "volume"), help="required")
    found.add_argument("--hf-repo", help="<owner>/<name>, private (with --return hf)")
    found.add_argument("--network-volume", help="network volume id (with --return volume)")
    found.add_argument("--data-center", help="the network volume's data center id")
    found.add_argument("--gpu", default=GPUS[0], help=f"one of {', '.join(GPUS)}")
    found.add_argument("--launch", action="store_true", help="send the requests (spends money)")
    found.add_argument("--smoke", action="store_true", help="10-minute pod that ends itself")
    found.add_argument("--smoke-record", type=Path, default=SMOKE_RECORD)
    found.add_argument("--output", type=Path, default=Path("ruh-speaker-launch"))
    return found


def check(args: argparse.Namespace) -> None:
    if len(args.revision) != 40 or any(c not in "0123456789abcdef" for c in args.revision):
        raise Refused("--revision must be a full 40-hex commit")
    cap = 1.0 if args.smoke else FIRST_RUN_CAP
    if not 0 < args.confirm_budget <= cap:
        raise Refused(f"--confirm-budget must be above 0 and at most ${cap:g} for this run")
    if args.smoke:
        args.gpu = "NVIDIA GeForce RTX 4090" if args.gpu == GPUS[0] else args.gpu
    elif args.gpu not in GPUS:
        raise Refused(f"--gpu must be one of {', '.join(GPUS)}")
    if args.smoke:
        return
    if args.ret is None:
        raise Refused("--return hf or --return volume is required: the owner chooses")
    if args.ret == "hf" and not (args.hf_repo and "/" in args.hf_repo):
        raise Refused("--return hf needs --hf-repo <owner>/<name>")
    if args.ret == "volume" and not (args.network_volume and args.data_center):
        raise Refused("--return volume needs --network-volume and --data-center")


def plan(args: argparse.Namespace, hourly: float) -> dict:
    seconds = SMOKE_SECONDS if args.smoke else lifetime(args.confirm_budget, hourly)
    if not args.smoke and seconds < MIN_HOURS * 3600:
        raise Refused(
            f"${args.confirm_budget:g} buys {seconds / 3600:.1f} h; at least {MIN_HOURS:g} h"
        )
    worst = (hourly + disk_hourly()) * seconds / 3600
    return {
        "usd": args.confirm_budget,
        "gpu": args.gpu,
        "gpu_hourly_usd": hourly,
        "disk_hourly_usd": round(disk_hourly(), 4),
        "safety_usd": safety(args.confirm_budget),
        "lifetime_seconds": seconds,
        "worst_case_usd": round(worst, 2),
        "prepare_seconds_at_most": int(PREP_SHARE * seconds),
        "train_seconds_about": int(seconds * (1 - PREP_SHARE) - WRAP_SECONDS),
        "network_volume": "billed apart: $0.07/GB/month" if args.ret == "volume" else None,
    }


def dry_run(args: argparse.Namespace) -> dict:
    hourly = DRY_RUN_PRICES[args.gpu]
    budget = plan(args, hourly)
    create = pod_request(
        args, "<SHA-256 of the archive, at launch>", "<now + lifetime_seconds, at launch>"
    )
    requests = [
        {"method": "GET", "url": f"{API}/catalog/gpus", "why": "the GPU's price.secure"},
        create,
        {"method": "GET", "url": f"{API}/pods/<id>", "why": "status and cost, every 30 s"},
        {
            "method": "DELETE",
            "url": f"{API}/pods/<id>",
            "why": "at the deadline, or when the pod has exited, failed or this is stopped",
        },
    ]
    for request in requests:
        request.setdefault("headers", {})
    return {
        "dry_run": True,
        "budget": budget,
        "requests": [redacted(r) for r in requests],
        "key_present": bool(os.environ.get("RUNPOD_API_KEY")),
        "note": "nothing was sent; --launch sends these (and needs a passed --smoke first)",
    }


def _source_sha256(revision: str) -> str:
    url = f"https://codeload.github.com/{REPOSITORY}/zip/{revision}"
    with urllib.request.urlopen(url, timeout=120) as response:
        return hashlib.sha256(response.read()).hexdigest()


def _price(key: str, gpu: str) -> float:
    status, found = _request("GET", f"{API}/catalog/gpus", key)
    if status != 200 or not isinstance(found, dict):
        raise Refused("the GPU catalog could not be read")
    for item in found.get("gpus", []):
        if item.get("id") == gpu and (item.get("price") or {}).get("secure"):
            return float(item["price"]["secure"])
    raise Refused(f"{gpu} has no Secure Cloud price in the catalog")


def launch(args: argparse.Namespace, key: str) -> dict:
    if not args.smoke:
        try:
            record = json.loads(args.smoke_record.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            record = {}
        if not record.get("self_terminated"):
            raise Refused("no passed smoke launch on record: run with --smoke first")
    hourly = _price(key, args.gpu)
    budget = plan(args, hourly)
    source = "-" if args.smoke else _source_sha256(args.revision)
    args.output.mkdir(parents=True, exist_ok=True)
    recovery = args.output / "pod-recovery.json"
    started = time.time()
    deadline = started + budget["lifetime_seconds"]
    request = pod_request(args, source, str(int(deadline)))
    note = {"name": request["body"]["name"], "deadline_epoch": deadline, "budget": budget}
    recovery.write_text(json.dumps(note, indent=1), encoding="utf-8")
    pod_id = None
    ended = False

    def interrupted(_signum: int, _frame: Any) -> None:
        raise KeyboardInterrupt

    previous = signal.signal(signal.SIGTERM, interrupted)
    try:
        status, created = _request("POST", request["url"], key, request["body"])
        if status not in (200, 201) or not isinstance(created, dict) or "id" not in created:
            raise Refused(f"the pod was not created (HTTP {status})")
        pod_id = created["id"]
        note["pod_id"] = pod_id
        recovery.write_text(json.dumps(note, indent=1), encoding="utf-8")
        print(json.dumps({"pod": pod_id, "deadline_epoch": int(deadline)}), file=sys.stderr)
        while time.time() < deadline:
            status, pod = _request("GET", f"{API}/pods/{pod_id}", key)
            if status == 404 or (isinstance(pod, dict) and pod.get("status") == "TERMINATED"):
                ended = True
                note["ended_by"] = "the pod"
                break
            if isinstance(pod, dict):
                cost = float(pod.get("cost") or 0.0)
                if cost > hourly + 1e-6:
                    raise Refused(
                        f"the pod costs ${cost}/h, above the ${hourly}/h it was planned at"
                    )
                if pod.get("status") in ("EXITED", "ERROR"):
                    note["ended_by"] = f"launcher ({pod['status']})"
                    break
                print(
                    json.dumps(
                        {
                            "status": pod.get("status"),
                            "elapsed_s": int(time.time() - started),
                            "usd_so_far": round(cost * (time.time() - started) / 3600, 2),
                        }
                    ),
                    file=sys.stderr,
                )
            if args.smoke and time.time() - started > SMOKE_SECONDS / 2:
                break
            time.sleep(30)
    finally:
        try:
            if pod_id is not None and not ended:
                for _attempt in range(6):
                    status, _ = _request("DELETE", f"{API}/pods/{pod_id}", key)
                    check_status, pod = _request("GET", f"{API}/pods/{pod_id}", key)
                    if check_status == 404 or (
                        isinstance(pod, dict) and pod.get("status") == "TERMINATED"
                    ):
                        ended = True
                        break
                    time.sleep(10)
            note.update(
                terminated=ended,
                seconds=round(time.time() - started),
                worst_case_usd=round((hourly + disk_hourly()) * (time.time() - started) / 3600, 2),
            )
            recovery.write_text(json.dumps(note, indent=1), encoding="utf-8")
        finally:
            signal.signal(signal.SIGTERM, previous)
    if args.smoke:
        record = {
            "self_terminated": note.get("ended_by") == "the pod",
            "at": time.time(),
            "gpu": args.gpu,
            "seconds": note["seconds"],
        }
        args.smoke_record.parent.mkdir(parents=True, exist_ok=True)
        args.smoke_record.write_text(json.dumps(record, indent=1), encoding="utf-8")
    if not ended:
        raise Refused(f"pod {pod_id} was not confirmed terminated: delete it by hand")
    return note


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["pod"]:
        return pod_main()
    args = parser().parse_args(argv)
    try:
        check(args)
        if not args.launch:
            print(json.dumps(dry_run(args), indent=1))
            return 0
        key = os.environ.get("RUNPOD_API_KEY")
        if not key:
            raise Refused("RUNPOD_API_KEY is not set")
        print(json.dumps(launch(args, key), indent=1))
        return 0
    except Refused as error:
        print(f"refused: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
