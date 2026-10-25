"""Import the pinned complete research archive and query its local source index.

No archive member is executed, unpickled, or automatically admitted as training gold.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

BUNDLE_SHA256 = "0fda16988214d7949592d018b9edab5157d6e7a0b437d74f1d155d164e6531f6"


def import_bundle(bundle: Path, destination: Path) -> dict:
    if destination.exists():
        raise ValueError(
            "Use a new destination; an existing research collection is never overwritten"
        )
    # Keep the same open file through verification and extraction.
    with bundle.open("rb") as source:
        if hashlib.file_digest(source, "sha256").hexdigest() != BUNDLE_SHA256:
            raise ValueError("Research bundle SHA256 mismatch")
        source.seek(0)
        with zipfile.ZipFile(source) as archive:
            entries = archive.infolist()
            if len(entries) > 50000 or sum(i.file_size for i in entries) > 1_000_000_000:
                raise ValueError("Research bundle exceeds extraction limits")
            names = set()
            for item in entries:
                member_path = PurePosixPath(item.filename)
                if (
                    member_path.is_absolute()
                    or ".." in member_path.parts
                    or "\\" in item.filename
                    or not member_path.parts
                    or ":" in member_path.parts[0]
                    or item.filename in names
                    or stat.S_ISLNK(item.external_attr >> 16)
                ):
                    raise ValueError("Unsafe or duplicate archive member")
                names.add(item.filename)
            destination.parent.mkdir(parents=True, exist_ok=True)
            stage = Path(tempfile.mkdtemp(prefix="mizan-import-", dir=destination.parent))
            try:
                for item in entries:
                    target = stage / item.filename
                    if item.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(item) as src, target.open("xb") as out:
                        shutil.copyfileobj(src, out)
                index = sqlite3.connect(stage / "research-index.sqlite3")
                try:
                    index.execute(
                        "CREATE VIRTUAL TABLE documents USING fts5(path UNINDEXED, sha256 UNINDEXED, text)"
                    )
                    indexed = 0
                    for item in entries:
                        if item.is_dir() or item.file_size > 2_000_000:
                            continue
                        path = stage / item.filename
                        if path.suffix.lower() not in {
                            ".md",
                            ".txt",
                            ".py",
                            ".json",
                            ".csv",
                            ".html",
                        }:
                            continue
                        raw = path.read_bytes()
                        try:
                            text = raw.decode("utf-8")
                        except UnicodeDecodeError:
                            continue
                        index.execute(
                            "INSERT INTO documents VALUES (?,?,?)",
                            (item.filename, hashlib.sha256(raw).hexdigest(), text),
                        )
                        indexed += 1
                    index.commit()
                finally:
                    index.close()
                result = {
                    "bundle_sha256": BUNDLE_SHA256,
                    "archive_members": len(entries),
                    "indexed_text_files": indexed,
                    "training_gold": False,
                }
                (stage / "IMPORT.json").write_text(json.dumps(result, indent=2) + "\n")
                stage.rename(destination)
                return result
            except BaseException:
                shutil.rmtree(stage)
                raise


def search(query: str, root: Path | None = None) -> list[dict]:
    root = root or Path(os.getenv("MIZAN_RESEARCH_DIR", "data/research"))
    if not (root / "IMPORT.json").is_file():
        raise ValueError("Import the pinned research bundle before searching")
    receipt = json.loads((root / "IMPORT.json").read_text())
    if receipt.get("bundle_sha256") != BUNDLE_SHA256:
        raise ValueError("Research import receipt does not match the pinned bundle")
    terms = re.findall(r"\w+", query, re.UNICODE)[:12]
    if not terms:
        return []
    match = " AND ".join('"' + term + '"' for term in terms)
    with sqlite3.connect(
        f"{(root / 'research-index.sqlite3').resolve().as_uri()}?mode=ro", uri=True
    ) as db:
        rows = db.execute(
            "SELECT path,sha256,snippet(documents,2,'[',']','…',40) FROM documents WHERE documents MATCH ? ORDER BY rank LIMIT 8",
            (match,),
        ).fetchall()
    return [
        {"path": p, "sha256": sha, "excerpt": excerpt, "verified_claim": False}
        for p, sha, excerpt in rows
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--destination", type=Path, default=Path("data/research"))
    args = parser.parse_args()
    print(json.dumps(import_bundle(args.bundle, args.destination), indent=2))


if __name__ == "__main__":
    main()
