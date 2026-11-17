"""Write or read a verified deployment receipt on the compute host over pinned SSH."""

import hashlib
import json
import os
import re
import sys
import tempfile
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path

RECEIPTS = Path("/var/lib/mizan-deploy/receipts")
RETENTION = 30 * 24 * 60 * 60
ARCHIVES = Path("/srv/github-actions-archive/CodeWithJuber/mizan")


def receipt(root, mode, repository_id, run_id, attempt, sha=None):
    identifiers = (repository_id, run_id, attempt)
    if not all(re.fullmatch(r"[1-9][0-9]*", value) for value in identifiers):
        raise ValueError("invalid deployment run identity")
    directory = root / repository_id
    path = directory / f"{run_id}-{attempt}.json"
    cutoff = time.time() - RETENTION
    if mode == "write" and sha and re.fullmatch(r"[0-9a-f]{40}", sha):
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        payload = " ".join((*identifiers, sha))
        digest = hashlib.sha256(payload.encode()).hexdigest()
        record = json.dumps({"payload": payload, "sha256": digest})
        with tempfile.NamedTemporaryFile(mode="w", dir=directory, delete=False) as temp:
            temporary = Path(temp.name)
            try:
                temp.write(record)
                temp.flush()
                os.fsync(temp.fileno())
                try:
                    os.link(temporary, path)
                except FileExistsError:
                    if path.read_text() != record:
                        raise ValueError(
                            "a different receipt exists for this run attempt"
                        ) from None
            finally:
                temporary.unlink()
        for candidate in directory.glob("*-*.json"):
            try:
                if candidate.stat().st_mtime < cutoff:
                    candidate.unlink(missing_ok=True)
            except FileNotFoundError:
                continue
        return None
    if mode != "read" or sha is not None:
        raise ValueError("invalid receipt operation or SHA")
    try:
        with path.open() as stream:
            if os.fstat(stream.fileno()).st_mtime < cutoff:
                return None
            record = json.load(stream)
    except FileNotFoundError:
        return None
    payload = record["payload"]
    if hashlib.sha256(payload.encode()).hexdigest() != record["sha256"]:
        raise ValueError("deployment receipt digest mismatch")
    prefix = " ".join(identifiers) + " "
    sha = payload.removeprefix(prefix)
    if sha == payload or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("invalid deployment receipt identity or SHA")
    return sha


def archived_receipt(root, run_id, started, now=None):
    """Read a pre-migration proof only from the triggering attempt's time window."""
    if not re.fullmatch(r"[1-9][0-9]*", run_id):
        raise ValueError("invalid archived deployment identity")
    timestamp = datetime.fromisoformat(started.replace("Z", "+00:00"))
    now = now or datetime.now(UTC)
    if timestamp.tzinfo is None or timestamp > now:
        raise ValueError("invalid deployment attempt start")
    candidates = []
    for path in (root / run_id).glob("[0-9]*/metadata.json"):
        if path.stat().st_size > 32768:
            raise ValueError("oversized deployment metadata")
        item = json.loads(path.read_text())
        if item["name"] != "production-deployment":
            continue
        if str(item["workflow_run"]["id"]) != run_id or str(item["id"]) != path.parent.name:
            raise ValueError("archived receipt identity mismatch")
        created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
        expires = datetime.fromisoformat(item["expires_at"].replace("Z", "+00:00"))
        if created < timestamp or expires <= now:
            continue
        candidates.append((created, path, item))
    if not candidates:
        return None
    _, metadata, item = max(candidates, key=lambda candidate: candidate[0])
    archive = metadata.with_name("artifact.zip")
    if not 0 < archive.stat().st_size <= 8192 or archive.stat().st_size != item["size_in_bytes"]:
        raise ValueError("invalid deployment archive size")
    data = archive.read_bytes()
    if "sha256:" + hashlib.sha256(data).hexdigest() != item["digest"]:
        raise ValueError("archived deployment digest mismatch")
    with zipfile.ZipFile(archive) as bundle:
        if bundle.namelist() != ["deployed-sha.txt"]:
            raise ValueError("unexpected deployment archive entries")
        info = bundle.getinfo("deployed-sha.txt")
        if info.file_size > 41:
            raise ValueError("oversized deployment proof")
        sha = bundle.read(info).decode("ascii").strip()
    if not re.fullmatch(r"[a-f0-9]{40}", sha):
        raise ValueError("invalid archived deployment SHA")
    return sha


if __name__ == "__main__":
    os.umask(0o077)
    mode, repository_id, run_id, attempt, *value = sys.argv[1:]
    if mode == "read":
        if repository_id != "1166364542" or len(value) != 1:
            raise ValueError("expected the Mizan run and its attempt start")
        result = receipt(RECEIPTS, mode, repository_id, run_id, attempt)
        if result is None:
            result = archived_receipt(ARCHIVES, run_id, value[0])
    else:
        result = receipt(RECEIPTS, mode, repository_id, run_id, attempt, *value)
    if result:
        print(result)
