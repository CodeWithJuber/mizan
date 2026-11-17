"""Write or read a verified deployment receipt on the compute host over pinned SSH."""

import hashlib
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

RECEIPTS = Path("/var/lib/mizan-deploy/receipts")
RETENTION = 30 * 24 * 60 * 60


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
                        raise ValueError("a different receipt exists for this run attempt") from None
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


if __name__ == "__main__":
    os.umask(0o077)
    result = receipt(RECEIPTS, *sys.argv[1:])
    if result:
        print(result)
