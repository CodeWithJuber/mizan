#!/usr/bin/env python3
"""Build the versioned Ruh sense inventory (deterministic, rerunnable).

Seeds from the shipped Q-CSMP v2 artifact inventory
(``nlp/artifacts/default/sense_inventory.json``) and applies the retired
sense merges (``nlp/SENSE_MERGES*.json``), then writes
``ruh_model/sense/data/sense_inventory.v<version>.jsonl``.

Determinism contract: same inputs -> byte-identical output. Rerunning is
always safe; the script prints a short summary and exits non-zero on any
data problem (fail-closed, never a half-written file).

Quran-lens note: every seeded sense comes from Q-CSMP v2 (Qur'anic Arabic),
so entries are flagged ``religious=True`` and abstain at the stricter bar.
``gloss_ar`` is left null — there is no scholar-reviewed Arabic gloss in the
repo, and inventing one would violate lā taqfu (no claim without knowledge).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SENSE_DIR = REPO_ROOT / "ruh_model" / "sense"

MERGE_FILES = [
    REPO_ROOT / "nlp" / "SENSE_MERGES.json",
    REPO_ROOT / "nlp" / "SENSE_MERGES_AYY.json",
    REPO_ROOT / "nlp" / "SENSE_MERGES_PHASEA.json",
]
SEED_FILE = REPO_ROOT / "nlp" / "artifacts" / "default" / "sense_inventory.json"


def _load_inventory_module():
    """Load ruh_model/sense/inventory.py by path (torch-free)."""
    path = SENSE_DIR / "inventory.py"
    spec = importlib.util.spec_from_file_location("ruh_model_sense_inventory", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"error: required file not found: {path}") from None
    except json.JSONDecodeError as exc:
        raise SystemExit(f"error: invalid JSON in {path}: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the versioned Ruh sense inventory (deterministic)."
    )
    parser.add_argument(
        "--version",
        default=None,
        help="inventory version to stamp (default: INVENTORY_VERSION from inventory.py)",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="output JSONL path (default: ruh_model/sense/data/sense_inventory.v<version>.jsonl)",
    )
    args = parser.parse_args()

    inv = _load_inventory_module()
    version = args.version or inv.INVENTORY_VERSION

    seed_raw = _read_json(SEED_FILE)
    seed_values = seed_raw.values() if isinstance(seed_raw, dict) else seed_raw
    seed_records = [
        {
            "lemma": r["lemma"],
            "sense": r["sense"],
            # Q-CSMP v2 is Qur'anic Arabic: every seeded sense is religious-flagged.
            "religious": True,
        }
        for r in seed_values
    ]

    merges: dict[str, str] = {}
    for mf in MERGE_FILES:
        data = _read_json(mf)
        data.pop("_note", None)
        for old_id, new_id in data.items():
            if old_id in merges and merges[old_id] != new_id:
                raise SystemExit(f"error: conflicting merge targets for {old_id}")
            merges[old_id] = new_id

    inventory = inv.build_inventory(seed_records, merges, version=version)

    out = Path(args.out) if args.out else SENSE_DIR / "data" / f"sense_inventory.v{version}.jsonl"
    inv.dump_inventory_jsonl(inventory, out)

    n_religious = sum(1 for e in inventory.entries if e.religious)
    print(f"inventory version : {inventory.version}")
    print(f"senses            : {len(inventory)}")
    print(f"lemmas            : {len(inventory.lemmas())}")
    print(f"religious-flagged : {n_religious}")
    print(f"merge entries     : {len(merges)}")
    print(f"wrote             : {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
