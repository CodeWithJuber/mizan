"""Build a RootSpace Reader annotation DB from a text file.

Usage:
    python scripts/build_annotations.py --input verses.tsv --out data/ruh_reader.sqlite
    python scripts/build_annotations.py --input verses.txt --out annotations.jsonl

Input formats:
* ``lines`` (default): one document per non-empty line; ref_id is
  ``line:<n>`` (1-based), or ``<ref_prefix><n>`` with --ref-prefix.
* ``tsv``: ``ref<TAB>text`` per line.

Output is chosen by --out suffix: ``.sqlite`` / ``.db`` / ``.sqlite3``
-> SQLite annotation DB (``AnnotationStore``); ``.jsonl`` -> one JSON
object per annotation line (each carries its ``ref_id``).

Optional ``--sense-inventory``: JSON file mapping
``{root: [{"sense_id": ...}, ...]}``. Single-sense roots get their
sense assigned; ambiguous roots stay ``sense_pending: true`` -- senses
are never invented (see ruh_model/reader/annotator.py).

BETA / UNVERIFIED: annotations are rule-based heuristics; per-occurrence
senses are scholar-eval pending. For corpus-scale Quran annotation, the
gold-eval gate from the study applies before any user-facing launch.

Torch-free: reader modules are loaded by file path (the repo's
``ruh_model/__init__.py`` needs torch, which CI does not install).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path
from types import ModuleType

_SQLITE_SUFFIXES = {".sqlite", ".db", ".sqlite3"}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load(relpath: str, name: str) -> ModuleType:
    full_path = _repo_root() / relpath
    spec = importlib.util.spec_from_file_location(name, full_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {full_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_documents(path: Path, format: str, ref_prefix: str) -> list[tuple[str, str]]:
    """Return [(ref_id, text)] pairs from the input file."""
    docs: list[tuple[str, str]] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        if format == "tsv":
            ref, _, text = line.partition("\t")
            ref, text = ref.strip(), text.strip()
            if not ref or not text:
                print(
                    f"warning: skipping malformed tsv line {lineno}",
                    file=sys.stderr,
                )
                continue
            docs.append((ref, text))
        else:
            docs.append((f"{ref_prefix}{lineno}", line))
    return docs


def _load_inventory(path: Path | None) -> dict | None:
    if path is None:
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("sense inventory JSON must be an object {root: [{sense_id}]}")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a RootSpace Reader annotation DB (beta).")
    parser.add_argument("--input", required=True, help="Input text file")
    parser.add_argument("--out", required=True, help="Output .sqlite/.db or .jsonl")
    parser.add_argument(
        "--format",
        choices=["lines", "tsv"],
        default="lines",
        help="Input layout (default: lines)",
    )
    parser.add_argument(
        "--ref-prefix",
        default="line:",
        help="Ref id prefix for --format lines (default: 'line:')",
    )
    parser.add_argument(
        "--sense-inventory",
        default=None,
        help="Optional JSON sense inventory {root: [{sense_id}]}",
    )
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    out_path = Path(args.out)
    if not input_path.is_file():
        print(f"error: input not found: {input_path}", file=sys.stderr)
        return 2

    annotator = _load("ruh_model/reader/annotator.py", "build_reader_annotator")
    store_mod = _load("ruh_model/reader/store.py", "build_reader_store")

    started = time.monotonic()
    docs = _read_documents(input_path, args.format, args.ref_prefix)
    inventory = _load_inventory(Path(args.sense_inventory) if args.sense_inventory else None)

    total_words = 0
    if out_path.suffix.lower() in _SQLITE_SUFFIXES:
        with store_mod.AnnotationStore(out_path) as store:
            for ref_id, text in docs:
                annotations = annotator.annotate_text(
                    text, ref_id=ref_id, sense_inventory=inventory
                )
                total_words += store.put_many(ref_id, annotations)
        try:
            out_bytes = out_path.stat().st_size
        except OSError:
            out_bytes = -1
    elif out_path.suffix.lower() == ".jsonl":
        with out_path.open("w", encoding="utf-8") as fh:
            for ref_id, text in docs:
                annotations = annotator.annotate_text(
                    text, ref_id=ref_id, sense_inventory=inventory
                )
                for annotation in annotations:
                    record = {"ref_id": ref_id, **annotation}
                    fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                    total_words += 1
        out_bytes = out_path.stat().st_size
    else:
        print(
            f"error: --out suffix must be one of {sorted(_SQLITE_SUFFIXES)} or .jsonl",
            file=sys.stderr,
        )
        return 2

    elapsed = time.monotonic() - started
    print(f"documents : {len(docs)}")
    print(f"words     : {total_words}")
    print(f"output    : {out_path} ({out_bytes} bytes)")
    print(f"elapsed   : {elapsed:.2f}s")
    print(f"annotator : {annotator.annotator_version()} (beta/unverified)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
