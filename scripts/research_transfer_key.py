#!/usr/bin/env python3
"""Prepare a one-hour server-only research transfer key; never change the backend."""

from __future__ import annotations

import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import secrets
import shutil
import stat
import subprocess
import time
from pathlib import Path

STATE = Path("/var/lib/mizan-deploy")
KEYS = Path("/run/mizan-research-transfer")
CONTAINER = "mizan-backend"
BUNDLE_SHA256 = "0fda16988214d7949592d018b9edab5157d6e7a0b437d74f1d155d164e6531f6"
BUNDLE_BYTES = 241577161
KEY_TTL = 3600
SAFE_ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8"}


class TransferError(RuntimeError):
    """Only deliberately redacted messages cross the workflow log boundary."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise TransferError(message)


def run(args: list[str], *, data: bytes | None = None, timeout: int = 60) -> bytes:
    try:
        result = subprocess.run(
            args,
            input=data,
            capture_output=True,
            timeout=timeout,
            env=SAFE_ENV,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TransferError("A required server operation failed or timed out") from exc
    require(result.returncode == 0, "A required server operation failed (output withheld)")
    return result.stdout


def secure_directory(path: Path, *, create: bool = False) -> None:
    if create:
        path.mkdir(mode=0o700, exist_ok=True)
    info = path.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0, "Unsafe transfer state directory")
    require(not info.st_mode & 0o022, "Transfer state must not be group/world writable")


def protected_write(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)


@contextlib.contextmanager
def deployment_lock():
    secure_directory(STATE)
    descriptor = os.open(STATE / "deploy.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        deadline = time.monotonic() + 120
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                require(
                    time.monotonic() < deadline, "Timed out waiting for production deployment lock"
                )
                time.sleep(1)
        yield
    finally:
        os.close(descriptor)


PROBE = r"""
import json, os, stat
from pathlib import Path
from mizan_owned.research import BUNDLE_SHA256
configured = os.environ.get("MIZAN_RESEARCH_DIR") or "data/research"
target = Path(os.path.abspath(configured))
parent = target.parent.resolve()
target = parent / target.name
def info(path):
    try:
        item = path.lstat()
    except FileNotFoundError:
        return {"exists": False}
    return {"exists": True, "uid": item.st_uid, "gid": item.st_gid,
            "mode": oct(stat.S_IMODE(item.st_mode)), "symlink": stat.S_ISLNK(item.st_mode),
            "directory": stat.S_ISDIR(item.st_mode)}
print(json.dumps({"research_dir": str(target), "configured_explicitly": bool(os.environ.get("MIZAN_RESEARCH_DIR")),
                  "backend_uid": os.geteuid(), "backend_gid": os.getegid(),
                  "parent": info(parent), "target": info(target),
                  "parent_writable_by_backend": os.access(parent, os.W_OK),
                  "importer_bundle_sha256": BUNDLE_SHA256}))
"""


def inspect_target() -> dict:
    template = (
        '{"container_id":{{json .Id}},"image_id":{{json .Image}},'
        '"image_ref":{{json .Config.Image}},"mounts":{{json .Mounts}}}'
    )
    container = json.loads(run(["docker", "inspect", "--format", template, CONTAINER]))
    target = json.loads(run(["docker", "exec", CONTAINER, "python", "-c", PROBE]))
    require(
        target["importer_bundle_sha256"] == BUNDLE_SHA256,
        "Running importer has a different bundle pin",
    )
    directory = Path(target["research_dir"])
    candidates = []
    for mount in container["mounts"]:
        destination = Path(mount["Destination"])
        if directory == destination or destination in directory.parents:
            candidates.append(mount)
    mount = max(candidates, key=lambda item: len(item["Destination"]), default=None)
    target.update({key: container[key] for key in ("container_id", "image_id", "image_ref")})
    target["persistent"] = bool(
        mount
        and directory != Path(mount["Destination"])
        and mount.get("RW")
        and mount.get("Type") in {"bind", "volume"}
        and (mount["Destination"] == "/data" or mount["Destination"].startswith("/data/"))
    )
    if mount:
        target["mount"] = {
            key: mount.get(key) for key in ("Type", "Name", "Source", "Destination", "RW")
        }
    return target


def prepare_key() -> dict:
    require(os.geteuid() == 0, "Key preparation requires the existing root deployment account")
    with deployment_lock():
        target = inspect_target()
        # This safe inventory is useful even when the current path is ephemeral.
        print(json.dumps({"status": "preflight", "target": target}), flush=True)
        require(
            target["persistent"],
            "Research directory is not inside a writable persistent /data mount; review configuration first",
        )
        require(
            target["parent_writable_by_backend"],
            "Research parent is not writable by the backend user",
        )
        require(
            not target["target"].get("exists"),
            "An existing research target needs explicit adoption review; it will not be replaced",
        )
        secure_directory(KEYS, create=True)
        require(stat.S_IMODE(KEYS.stat().st_mode) == 0o700, "Key root must have mode 0700")
        key_id = secrets.token_hex(16)
        directory = KEYS / key_id
        directory.mkdir(mode=0o700)
        try:
            # Schedule erasure before creating key material. /run also removes it
            # across reboot, when a transient systemd timer would disappear.
            run(
                [
                    "systemd-run",
                    "--quiet",
                    f"--unit=mizan-research-key-{key_id}",
                    f"--on-active={KEY_TTL}s",
                    "--timer-property=AccuracySec=1s",
                    "/usr/bin/rm",
                    "-rf",
                    "--",
                    str(directory),
                ]
            )
            private = directory / "private.pem"
            certificate = directory / "certificate.pem"
            run(
                [
                    "openssl",
                    "req",
                    "-x509",
                    "-newkey",
                    "rsa:3072",
                    "-nodes",
                    "-sha256",
                    "-days",
                    "1",
                    "-subj",
                    f"/CN=mizan-research-{key_id}",
                    "-keyout",
                    str(private),
                    "-out",
                    str(certificate),
                ]
            )
            private.chmod(0o600)
            certificate.chmod(0o600)
            public = run(["openssl", "pkey", "-in", str(private), "-pubout"])
            public_der = run(["openssl", "pkey", "-in", str(private), "-pubout", "-outform", "DER"])
            now = int(time.time())
            document = {
                "schema": "mizan-research-key-v1",
                "key_id": key_id,
                "created_unix": now,
                "expires_unix": now + KEY_TTL,
                "expires_at": dt.datetime.fromtimestamp(now + KEY_TTL, dt.UTC).isoformat(),
                "public_key_sha256": hashlib.sha256(public_der).hexdigest(),
                "public_key_pem": public.decode(),
                "certificate_pem": certificate.read_text(),
                "bundle_sha256": BUNDLE_SHA256,
                "bundle_bytes": BUNDLE_BYTES,
                "target": target,
            }
            protected_write(
                directory / "key.json", (json.dumps(document, indent=2) + "\n").encode()
            )
            return document
        except BaseException:
            shutil.rmtree(directory)
            raise


def main() -> int:
    os.umask(0o077)
    try:
        document = prepare_key()
        print(json.dumps({"status": "key_ready", "public": document}))
        return 0
    except TransferError as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}))
        return 1
    except Exception:
        print(
            json.dumps(
                {"status": "failed", "reason": "Key preparation failed; private details withheld"}
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
