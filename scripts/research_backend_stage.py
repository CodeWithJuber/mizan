#!/usr/bin/env python3
"""Run only reviewed importer code as the existing backend user; archive code stays data."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import signal
import sqlite3
import sys
import time
from pathlib import Path

BUNDLE_SHA256 = "0fda16988214d7949592d018b9edab5157d6e7a0b437d74f1d155d164e6531f6"
BUNDLE_BYTES = 241577161
MEMBERS = 21486
INDEXED = 7665


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def operation_paths(config: dict) -> tuple[Path, Path, Path]:
    require(bool(re.fullmatch(r"[0-9a-f]{32}", config["key_id"])), "Invalid transfer identity")
    target = Path(config["research_dir"])
    actual = Path(os.path.abspath(os.environ.get("MIZAN_RESEARCH_DIR") or "data/research"))
    actual = actual.parent.resolve() / actual.name
    require(
        target == actual and target.parent.resolve() == target.parent, "Research target changed"
    )
    require(
        target.is_absolute() and Path("/data") in target.parents, "Research target is outside /data"
    )
    require(
        os.geteuid() == config["backend_uid"] and os.getegid() == config["backend_gid"],
        "Backend user changed",
    )
    stage = target.parent / (".mizan-research-transfer-" + config["key_id"])
    release = target.parent / (".mizan-research-" + config["key_id"])
    return target, stage, release


def validate_target(config: dict) -> tuple[Path, Path, Path]:
    target, stage, release = operation_paths(config)
    require(not os.path.lexists(target), "Existing research data must not be replaced")
    require(os.access(target.parent, os.W_OK), "Research parent is not writable")
    require(
        not os.path.lexists(stage)
        and not os.path.lexists(release)
        and not os.path.lexists(operation_receipt_path(target, config)),
        "Transfer paths already exist",
    )
    require(
        shutil.disk_usage(target.parent).free >= 2_000_000_000,
        "Research volume needs 2 GB free for bounded full import",
    )
    return target, stage, release


def process_start(pid: int) -> str:
    return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]


def operation_receipt_path(target: Path, config: dict) -> Path:
    return target.parent / (".mizan-research-operation-" + config["key_id"] + ".json")


def write_operation_receipt(target: Path, config: dict, receipt: dict) -> None:
    descriptor = os.open(
        operation_receipt_path(target, config),
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
    )
    with os.fdopen(descriptor, "w") as handle:
        handle.write(json.dumps({**receipt, "key_id": config["key_id"]}) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def operation_status(config: dict, *, cancel: bool = False) -> dict:
    target, temporary, release = operation_paths(config)
    marker = temporary / "PROCESS.json"
    if marker.is_file() and not marker.is_symlink():
        process = json.loads(marker.read_text())
        pid = process["pid"]
        require(
            isinstance(pid, int) and pid > 1 and process["key_id"] == config["key_id"],
            "Unexpected process marker",
        )
        process_fd = None
        try:
            require(
                hasattr(os, "pidfd_open") and hasattr(signal, "pidfd_send_signal"),
                "Stable process handles are unavailable",
            )
            process_fd = os.pidfd_open(pid)
            arguments = Path(f"/proc/{pid}/cmdline").read_bytes().rstrip(b"\0").split(b"\0")
            same = (
                Path(f"/proc/{pid}").stat().st_uid == os.geteuid()
                and process_start(pid) == process["start_ticks"]
                and len(arguments) >= 4
                and arguments[-2] == b"install"
                and json.loads(arguments[-1]) == config
            )
            require(same, "Research process identity is uncertain")
            if cancel:
                signal.pidfd_send_signal(process_fd, signal.SIGTERM)
            return {"status": "running", "key_id": config["key_id"], "cancel_requested": cancel}
        except (FileNotFoundError, ProcessLookupError):
            pass
        finally:
            if process_fd is not None:
                os.close(process_fd)
    if target.is_symlink() and os.readlink(target) == release.name:
        receipt = json.loads((release / "FULL_IMPORT.json").read_text())
        require(
            receipt.get("key_id") == config["key_id"]
            and receipt.get("bundle_sha256") == BUNDLE_SHA256,
            "Active research identity differs",
        )
        return {
            "status": "active",
            **verify_collection(target, use_default=True),
            **receipt,
            "release": str(release),
        }
    terminal = operation_receipt_path(target, config)
    if terminal.is_file() and not terminal.is_symlink():
        receipt = json.loads(terminal.read_text())
        if (
            receipt.get("key_id") == config["key_id"]
            and receipt.get("status") == "failed"
            and receipt.get("target_absent")
            and not os.path.lexists(target)
        ):
            return receipt
    # Docker can disconnect before the child creates PROCESS.json. Its absence
    # is never proof that the remote operation did not start or has finished.
    return {"status": "outcome_unknown", "key_id": config["key_id"]}


def verify_collection(root: Path, *, use_default: bool = False) -> dict:
    from mizan_owned.research import search

    receipt = json.loads((root / "IMPORT.json").read_text())
    require(receipt.get("bundle_sha256") == BUNDLE_SHA256, "Imported bundle pin differs")
    require(
        receipt.get("archive_members") == MEMBERS and receipt.get("indexed_text_files") == INDEXED,
        "Imported collection counts differ",
    )
    require(receipt.get("training_gold") is False, "Research import cannot authorize training gold")
    with sqlite3.connect(
        f"{(root / 'research-index.sqlite3').resolve().as_uri()}?mode=ro", uri=True
    ) as db:
        require(
            db.execute("PRAGMA quick_check").fetchone()[0] == "ok",
            "Research index verification failed",
        )
        require(
            db.execute("SELECT count(*) FROM documents").fetchone()[0] == INDEXED,
            "Research index row count differs",
        )
    results = search("Mizan", **({} if use_default else {"root": root}))
    require(
        bool(results) and all(item.get("verified_claim") is False for item in results),
        "Research retrieval verification failed",
    )
    return {
        **receipt,
        "fts_search_verified": True,
        "backend_uid": os.geteuid(),
        "backend_gid": os.getegid(),
    }


def install(config: dict, source) -> dict:
    from mizan_owned.research import BUNDLE_SHA256 as importer_pin
    from mizan_owned.research import import_bundle

    require(importer_pin == BUNDLE_SHA256, "Running importer pin differs")
    require_operation_deadline(config)
    target, stage, release = validate_target(config)
    stage.mkdir(mode=0o700)
    active = False
    created_release = False
    terminal_receipt = None
    try:
        process = {
            "pid": os.getpid(),
            "start_ticks": process_start(os.getpid()),
            "key_id": config["key_id"],
        }
        with (stage / "PROCESS.json").open("x") as handle:
            handle.write(json.dumps(process))
        bundle = stage / "bundle.zip"
        digest, total = hashlib.sha256(), 0
        descriptor = os.open(bundle, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            while block := source.read(min(1024 * 1024, BUNDLE_BYTES + 1 - total)):
                total += len(block)
                require(total <= BUNDLE_BYTES, "Research stream exceeded pinned size")
                digest.update(block)
                handle.write(block)
            handle.flush()
            os.fsync(handle.fileno())
        require(
            total == BUNDLE_BYTES and digest.hexdigest() == BUNDLE_SHA256,
            "Research stream identity differs",
        )
        import_bundle(bundle, release)
        created_release = True
        receipt = verify_collection(release)
        require(
            not os.path.lexists(release / "BUNDLE.source.zip")
            and not os.path.lexists(release / "FULL_IMPORT.json"),
            "Reserved provenance files are already present",
        )
        bundle.rename(release / "BUNDLE.source.zip")
        marker = {
            "schema": "mizan-managed-full-research-v1",
            "key_id": config["key_id"],
            "bundle_sha256": BUNDLE_SHA256,
            "bundle_bytes": BUNDLE_BYTES,
            "archive_files_included": True,
            "original_archive_preserved": True,
            "training_gold": False,
            "target": str(target),
        }
        with (release / "FULL_IMPORT.json").open("x") as handle:
            handle.write(json.dumps(marker) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        # symlink() creates the absent target atomically and refuses to overwrite
        # anything a concurrent actor may have placed there since preflight.
        require_operation_deadline(config)
        os.symlink(release.name, target)
        active = True
        verify_collection(target, use_default=True)
        directory_fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        terminal_receipt = {
            "status": "active",
            **receipt,
            **marker,
            "release": str(release),
            "target": str(target),
        }
        return terminal_receipt
    except BaseException:
        if active and target.is_symlink() and os.readlink(target) == release.name:
            target.unlink()
        if created_release and release.is_dir() and not release.is_symlink():
            shutil.rmtree(release)
        terminal_receipt = {"status": "failed", "target_absent": not os.path.lexists(target)}
        raise
    finally:
        shutil.rmtree(stage)
        if terminal_receipt is not None:
            write_operation_receipt(target, config, terminal_receipt)


def require_operation_deadline(config: dict) -> int:
    deadline = config.get("operation_deadline_unix")
    require(isinstance(deadline, int), "Research operation has no absolute deadline")
    remaining = deadline - int(time.time())
    require(0 < remaining <= 840, "Research operation deadline expired or differs")
    return remaining


def main() -> int:
    os.umask(0o077)

    def interrupted(signum, frame):
        raise TimeoutError("Research import interrupted or timed out")

    for signum in (signal.SIGALRM, signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(signum, interrupted)
    signal.alarm(840)
    try:
        action, raw = sys.argv[1:]
        config = json.loads(raw)
        if action == "check":
            target, _, _ = validate_target(config)
            print(
                json.dumps(
                    {
                        "status": "ready",
                        "target": str(target),
                        "backend_uid": os.geteuid(),
                        "backend_gid": os.getegid(),
                    }
                )
            )
        elif action in {"status", "cancel"}:
            print(json.dumps(operation_status(config, cancel=action == "cancel")))
        else:
            require(action == "install", "Unknown research stage")
            signal.alarm(require_operation_deadline(config))
            print(json.dumps(install(config, sys.stdin.buffer)))
        return 0
    except Exception:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "reason": "Backend operation failed; reconcile target and operation status",
                }
            )
        )
        return 1
    finally:
        signal.alarm(0)


if __name__ == "__main__":
    raise SystemExit(main())
