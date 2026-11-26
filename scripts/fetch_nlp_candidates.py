#!/usr/bin/env python3
"""Download the candidate sense models (nlp/artifacts/candidate_*/model.joblib).

    python3 scripts/fetch_nlp_candidates.py [--check] [NAME ...]

The default artifact (nlp/artifacts/default/) ships in the repository. The candidates are
research comparisons that nothing loads at run time, so their pickles are release assets
instead: each candidate's manifest.json, which is committed, pins the SHA-256 of its
model.joblib, and a download is kept only when it matches (docs/nlp.md, Candidate artifacts).
A pickle can run code when it is loaded, so the digest is checked before the file is written.

Standard library only. --check reports which candidates are present and fetches nothing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

ARTIFACTS = Path(__file__).resolve().parents[1] / "nlp" / "artifacts"
RELEASE = "https://github.com/CodeWithJuber/mizan/releases/download/nlp-candidates-v1"
SIZE_LIMIT = 64 * 1024 * 1024


def candidates() -> dict[str, str]:
    """Each candidate directory's name and the model SHA-256 its manifest pins."""
    pinned = {}
    for manifest in sorted(ARTIFACTS.glob("candidate_*/manifest.json")):
        digest = json.loads(manifest.read_text(encoding="utf-8")).get("model_sha256", "")
        if len(digest) != 64 or not all(c in "0123456789abcdef" for c in digest):
            raise SystemExit(f"{manifest}: model_sha256 is not a SHA-256")
        pinned[manifest.parent.name] = digest
    return pinned


def present(name: str, digest: str) -> bool:
    path = ARTIFACTS / name / "model.joblib"
    return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == digest


def fetch(name: str, digest: str) -> None:
    url = f"{RELEASE}/{name}.model.joblib"
    # The URL is the fixed https release above: S310 is a false positive.
    request = urllib.request.Request(url, headers={"User-Agent": "mizan-fetch"})  # noqa: S310
    with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
        data = response.read(SIZE_LIMIT + 1)
    if len(data) > SIZE_LIMIT:
        raise SystemExit(f"{url}: larger than {SIZE_LIMIT} bytes")
    if hashlib.sha256(data).hexdigest() != digest:
        raise SystemExit(f"{url}: SHA-256 does not match {name}/manifest.json; nothing written")
    target = ARTIFACTS / name / "model.joblib"
    partial = target.with_suffix(".part")
    partial.write_bytes(data)
    partial.replace(target)
    print(f"{name}: model.joblib written ({len(data)} bytes, SHA-256 verified)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("names", nargs="*", help="candidate directories (default: all)")
    parser.add_argument("--check", action="store_true", help="report only, download nothing")
    args = parser.parse_args()
    pinned = candidates()
    unknown = set(args.names) - set(pinned)
    if unknown:
        parser.error(f"unknown candidate(s): {', '.join(sorted(unknown))}")
    missing = 0
    for name in args.names or sorted(pinned):
        if present(name, pinned[name]):
            print(f"{name}: present")
        elif args.check:
            print(f"{name}: missing")
            missing += 1
        else:
            fetch(name, pinned[name])
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
