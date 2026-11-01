#!/usr/bin/env python3
"""Check a MIZAN Sakk export on your own machine, without trusting MIZAN.

    python scripts/verify_sakk.py mizan-sakk.json [--public-key KEY]

Recomputes every receipt's SHA-256 over its RFC 8785 JSON and each link to the
receipt before it, checks that the chain's head is in the Merkle root MIZAN
signed for that day, and checks the Ed25519 signature on that root. Pass the
public key you saw on MIZAN's public reliability page (or /api/public/sakk) to
make sure the export's own key is MIZAN's.

Needs: pip install rfc8785 cryptography
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from security.sakk import verify_export  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("export", type=Path)
    parser.add_argument("--public-key", help="MIZAN's public key, from its public page")
    args = parser.parse_args()
    data = json.loads(args.export.read_text(encoding="utf-8"))
    if data.get("format") != "mizan-sakk/1":
        print("Not a MIZAN Sakk export (format mizan-sakk/1)")
        return 2
    if args.public_key and args.public_key != data.get("public_key"):
        print("FAIL: the export's public key is not the one you gave")
        return 1
    found = verify_export(data)
    print(f"receipts: {found['receipts']}")
    print(f"chain: {'intact' if not found['problems'] else 'BROKEN'}")
    if found["included"] is not None:
        print(f"in the signed root: {'yes' if found['included'] else 'NO'}")
        print(f"root signature: {'valid' if found['signed'] else 'INVALID'}")
    else:
        print("signed root: none yet (MIZAN signs once a day)")
    for problem in found["problems"]:
        print(f"FAIL: {problem}")
    return 0 if found["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
