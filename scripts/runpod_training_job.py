#!/usr/bin/env python3
"""Private disposable-pod continuation job; authenticated read-only artifact API."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path("/tmp/ruh-continuation")
STATE = {"phase": "starting", "promotion_approved": False}
ARTIFACTS: dict[str, Path] = {}
RECOVERY_MANIFEST = {}


def digest(path):
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def recovery_artifacts():
    """Hard-link a complete snapshot so rotating training cannot remove it."""
    if RECOVERY_MANIFEST:
        return RECOVERY_MANIFEST
    pointer = ROOT / "run/latest-continuation.json"
    if not pointer.is_file():
        return {}
    snapshot = ROOT / "run" / json.loads(pointer.read_text())["path"]
    files = [*snapshot.joinpath("candidate").iterdir(), snapshot / "training_state.pt"]
    manifest, artifacts = {}, {}
    for source in files:
        relative = source.relative_to(snapshot)
        destination = ROOT / "recovery" / snapshot.name / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            os.link(source, destination)
        key = "recovery/" + relative.as_posix()
        artifacts[key] = destination
        manifest[key] = {
            "bytes": destination.stat().st_size,
            "sha256": digest(destination),
        }
    ARTIFACTS.update(artifacts)
    RECOVERY_MANIFEST.update(manifest)
    return RECOVERY_MANIFEST


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        expected = "Bearer " + os.environ["RUH_JOB_TOKEN"]
        if not hmac.compare_digest(self.headers.get("Authorization", ""), expected):
            self.send_error(401)
            return
        if self.path == "/status":
            value = dict(STATE)
            if time.time() > float(os.environ["RUH_DEADLINE_UTC"]) - 400:
                try:
                    value["recovery_artifacts"] = recovery_artifacts()
                except FileNotFoundError:
                    # The next request reads the new complete pointer if normal
                    # rotation removed a source before its hard-link was made.
                    value["recovery_artifacts"] = {}
            log = ROOT / "job.log"
            if log.is_file():
                value["log_tail"] = log.read_text(errors="replace")[-2000:]
            payload = json.dumps(value).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        key = self.path.removeprefix("/artifact/")
        path = ARTIFACTS.get(key)
        if not self.path.startswith("/artifact/") or path is None:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(path.stat().st_size))
        self.end_headers()
        with path.open("rb") as handle:
            shutil.copyfileobj(handle, self.wfile, 1024 * 1024)


def run(command, *, cwd, timeout, log):
    subprocess.run(
        command, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=timeout
    )


def main():
    ROOT.mkdir(exist_ok=True)
    server = ThreadingHTTPServer(("0.0.0.0", 8080), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    started = time.monotonic()
    try:
        revision = os.environ["RUH_REVISION"]
        if len(revision) != 40 or any(
            character not in "0123456789abcdef" for character in revision
        ):
            raise ValueError("Full reviewed commit required")
        archive = ROOT / "source.zip"
        urllib.request.urlretrieve(
            f"https://codeload.github.com/CodeWithJuber/mizan/zip/{revision}", archive
        )
        with zipfile.ZipFile(archive) as bundle:
            for name in bundle.namelist():
                if not (ROOT / name).resolve().is_relative_to(ROOT):
                    raise ValueError("Unsafe source archive path")
            bundle.extractall(ROOT)
        source = ROOT / f"mizan-{revision}"
        with (ROOT / "job.log").open("w", buffering=1) as log:
            import torch

            if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
                raise ValueError("A supported BF16 CUDA accelerator is required")
            STATE.update(gpu=torch.cuda.get_device_name(0), torch=torch.__version__)
            STATE["phase"] = "dependencies"
            dependencies = ROOT / "dependencies"
            run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--target",
                    str(dependencies),
                    "kagglehub==1.0.2",
                    "huggingface_hub==1.33.0",
                    "pyarrow==25.0.1",
                    "numpy",
                    "pyyaml",
                ],
                cwd=source,
                timeout=240,
                log=log,
            )
            sys.path.insert(0, str(dependencies))
            os.environ["PYTHONPATH"] = str(dependencies) + os.pathsep + os.getenv("PYTHONPATH", "")
            import kagglehub

            STATE["phase"] = "private_checkpoint_download"
            os.environ["KAGGLEHUB_CACHE"] = str(ROOT / "kaggle-cache")
            resume = ROOT / "resume"
            (resume / "candidate").mkdir(parents=True)
            ref = "zubairshaikh/ruh-full-training-repair/versions/1"

            def download(relative, destination):
                downloaded = Path(kagglehub.notebook_output_download(ref, path=relative))
                if downloaded.is_dir():
                    downloaded /= relative
                shutil.copyfile(downloaded, destination)

            baseline = ROOT / "baseline-evaluation.json"
            download("full-training-run/evaluation.json", baseline)
            manifest = json.loads(baseline.read_text())["checkpoint_manifest"]
            if (
                manifest["model.pt"]["sha256"]
                != "fcbd2dac0a95513b5cfd7da665b178d2ec3bfd032d49cfcbf062061ed5712fac"
            ):
                raise ValueError("Unexpected private continuation checkpoint")
            for name, item in manifest.items():
                if name not in {"config.json", "model.pt", "tokenizer.json", "vocab.json"}:
                    raise ValueError("Unexpected checkpoint manifest member")
                destination = resume / "candidate" / name
                download("full-training-run/candidate/" + name, destination)
                if (
                    destination.stat().st_size != item["bytes"]
                    or digest(destination) != item["sha256"]
                ):
                    raise ValueError("Private checkpoint digest mismatch")
            download("full-training-run/training_state.pt", resume / "training_state.pt")
            # The token is needed only for the authenticated private download.
            os.environ.pop("KAGGLE_API_TOKEN", None)
            STATE["phase"] = "data_preparation"
            data = ROOT / "data"
            run(
                [
                    sys.executable,
                    "-m",
                    "scripts.prepare_sequence_data",
                    "--output-dir",
                    str(data),
                    "--dialogues",
                    "3000",
                    "--sentences",
                    "1000",
                    "--aya-arabic",
                    "5000",
                    "--aya-english",
                    "1500",
                ],
                cwd=source,
                timeout=360,
                log=log,
            )
            output = ROOT / "run"
            training_budget = min(
                6000, int(float(os.environ["RUH_DEADLINE_UTC"]) - time.time() - 600)
            )
            if training_budget < 60:
                raise TimeoutError("Setup consumed the bounded training lifecycle")
            command = [
                sys.executable,
                "-m",
                "ruh_model.train_sequence",
                "--production-architecture",
                "--data",
                str(data / "training.jsonl"),
                "--source-metadata",
                str(data / "sources.json"),
                "--resume-from",
                str(resume / "candidate"),
                "--output",
                str(output),
                "--device",
                "cuda",
                "--precision",
                "bfloat16",
                "--steps",
                "100000",
                "--max-seconds",
                str(training_budget),
                "--batch-size",
                "8",
                "--lr",
                "1e-4",
                "--checkpoint-every-seconds",
                "600",
                "--mixing-weights",
                '{"ar:dialogue":0.55,"en:dialogue":0.25,"ar:text":0.20}',
            ]
            STATE.update(phase="training", command=command, revision=revision)
            run(command, cwd=source, timeout=training_budget + 400, log=log)
            STATE["phase"] = "artifact_manifest"
            ARTIFACTS.update(
                {"candidate/" + name: output / "candidate" / name for name in manifest}
            )
            ARTIFACTS.update(
                {
                    "training_state.pt": output / "training_state.pt",
                    "evaluation.json": output / "evaluation.json",
                    "sources.json": data / "sources.json",
                    "baseline-evaluation.json": baseline,
                    "job.log": ROOT / "job.log",
                }
            )
            run_metadata = ROOT / "run-metadata.json"
            run_metadata.write_text(
                json.dumps(
                    {
                        "revision": revision,
                        "source_archive_sha256": digest(archive),
                        "baseline_optimizer_sha256": digest(resume / "training_state.pt"),
                        "gpu": STATE["gpu"],
                        "torch": STATE["torch"],
                        "command": command,
                        "seconds": time.monotonic() - started,
                        "promotion_approved": False,
                    },
                    indent=2,
                )
            )
            ARTIFACTS["run-metadata.json"] = run_metadata
            STATE.update(
                phase="complete",
                artifacts={
                    key: {"bytes": path.stat().st_size, "sha256": digest(path)}
                    for key, path in ARTIFACTS.items()
                },
            )
    except Exception as error:
        STATE.update(phase="failed", error_type=type(error).__name__)
    # The external controller downloads artifacts and deletes this disposable pod.
    while time.monotonic() - started < 7200:
        time.sleep(15)
    server.shutdown()


if __name__ == "__main__":
    main()
