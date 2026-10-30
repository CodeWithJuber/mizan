"""Build Qāmūs, MIZAN's cross-lingual lexicon (backend/tadbir/qamus.py), from MASSIVE.

MASSIVE 1.1 (Amazon, CC BY 4.0) holds the same utterances in 52 languages,
aligned by id. It is read from its Hugging Face parquet conversion, pinned by
commit, downloaded into ``--data``: a new, empty folder outside the repository.
Each lexicon records the SHA-256 of the files it was built from. Run it with
``python -I`` so that nothing in the data folder or the current folder can be
imported:

    python -I scripts/build_qamus.py --data /tmp/qamus_data          # writes backend/tadbir/data/qamus/<x>-en.json.gz
    python -I scripts/build_qamus.py --data /tmp/qamus_data --check  # fails if a rebuild differs

For English with each of Hindi, Urdu, Arabic and Tamil: IBM Model 1 by EM in
both directions on the train split, stopped by the validation split's
log-likelihood; the directions multiplied; each translation scored by the
Wilson lower bound of its probability over the sentences that hold the word;
the cut-off on that score chosen per direction by F1 against the validation
split's slot dictionary; precision@1 measured on the test split's. Needs
``pyarrow`` to read parquet.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from core.adaptive import wilson_bounds  # noqa: E402
from tadbir import qamus  # noqa: E402

DATASET = "AmazonScience/massive"
REVISION = "ed58ac423a2f4121720918bf5301577edce4ffd3"  # refs/convert/parquet
LICENCE = "CC BY 4.0"
ENGLISH = "en-US"
LOCALES = {"hi": "hi-IN", "ur": "ur-PK", "ar": "ar-SA", "ta": "ta-IN"}
SPLITS = ("train", "validation", "test")
_SLOT = re.compile(r"\[\s*([^\]:]+?)\s*:\s*([^\]]*?)\s*\]")


def fetch(data: Path, locale: str) -> dict[str, Path]:
    from huggingface_hub import hf_hub_download

    return {
        split: Path(
            hf_hub_download(
                DATASET,
                f"{locale}/{split}/0000.parquet",
                repo_type="dataset",
                revision=REVISION,
                local_dir=str(data),
            )
        )
        for split in SPLITS
    }


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict[str, dict]:
    import pyarrow.parquet as pq

    table = pq.read_table(path, columns=["id", "intent", "utt", "annot_utt", "slot_method"])
    return {str(row["id"]): row for row in table.to_pylist()}


def methods(row: dict) -> dict[str, set[str]]:
    """How the translator wrote each slot type: "translation", "localization"
    (another entity of the same kind put in its place) or "unchanged"."""
    method = row.get("slot_method") or {}
    found: dict[str, set[str]] = {}
    for kind, how in zip(method.get("slot") or [], method.get("method") or [], strict=False):
        found.setdefault(kind, set()).add(how)
    return found


def words(row: dict, dropped: set[str]) -> list[str]:
    """An utterance's words, without the values of the dropped slot types."""
    text = _SLOT.sub(lambda m: "" if m.group(1) in dropped else m.group(2), row["annot_utt"])
    return qamus.tokens(text)


def parallel(english: dict[str, dict], other: dict[str, dict]) -> list[tuple[list[str], list[str]]]:
    """(English words, other words) of each utterance both hold, in id order. A
    slot the translator localised ("the time in London" became "the time in
    Delhi") is not a translation, so its values are left out on both sides."""
    pairs = []
    for i in sorted(set(english) & set(other), key=int):
        localised = {
            kind for kind, how in methods(other[i]).items() if any("localization" in h for h in how)
        }
        pairs.append((words(english[i], localised), words(other[i], localised)))
    return pairs


def slots(annotation: str) -> Counter:
    return Counter((kind, value) for kind, value in _SLOT.findall(annotation or ""))


def dictionary(
    english: dict[str, dict], other: dict[str, dict], scripts: dict[str, str], language: str
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """The held-out dictionary of one split, both ways: a slot type that occurs
    once on each side and that the translator translated (not localised or left
    unchanged) pairs its two values, when each is one word in its own script."""
    other_to_english: dict[str, set[str]] = {}
    english_to_other: dict[str, set[str]] = {}
    for i in sorted(set(english) & set(other), key=int):
        how = methods(other[i])
        ours = slots(english[i]["annot_utt"])
        theirs = slots(other[i]["annot_utt"])
        for kind in {kind for kind, _ in ours}:
            mine = [value for k, value in ours.elements() if k == kind]
            yours = [value for k, value in theirs.elements() if k == kind]
            if len(mine) != 1 or len(yours) != 1 or how.get(kind) != {"translation"}:
                continue
            e, x = qamus.tokens(mine[0]), qamus.tokens(yours[0])
            if len(e) != 1 or len(x) != 1 or e == x:
                continue
            if qamus.script(e[0]) != scripts["en"] or qamus.script(x[0]) != scripts[language]:
                continue
            other_to_english.setdefault(x[0], set()).add(e[0])
            english_to_other.setdefault(e[0], set()).add(x[0])
    return other_to_english, english_to_other


def written_in(pairs: list[tuple[list[str], list[str]]], side: int) -> str:
    return Counter(
        qamus.script(word) for pair in pairs for word in pair[side] if qamus.script(word)
    ).most_common(1)[0][0]


def own_script(shares: qamus.Table, source: str) -> qamus.Table:
    """Keys written in the source's script, translations not in it: a word
    copied unchanged into the other side (a name left in Latin letters) is
    matched as it is, not translated."""
    return {
        a: {b: p for b, p in row.items() if qamus.script(b) != source}
        for a, row in shares.items()
        if qamus.script(a) == source
    }


def build(language: str, data: Path) -> dict:
    locale = LOCALES[language]
    files = {name: fetch(data, name) for name in (ENGLISH, locale)}
    rows = {
        (name, split): read(path) for name, paths in files.items() for split, path in paths.items()
    }
    split = {s: parallel(rows[(ENGLISH, s)], rows[(locale, s)]) for s in SPLITS}
    scripts = {"en": written_in(split["train"], 0), language: written_in(split["train"], 1)}
    gold = {
        s: dictionary(rows[(ENGLISH, s)], rows[(locale, s)], scripts, language)
        for s in ("validation", "test")
    }
    # t(e | x): English generated from the other language, and t(x | e) back.
    flipped = {s: [(x, e) for e, x in pairs] for s, pairs in split.items()}
    to_english, english_trace = qamus.ibm1(flipped["train"], flipped["validation"])
    to_other, other_trace = qamus.ibm1(split["train"], split["validation"])
    directions = {
        f"{language}>en": (qamus.symmetrise(to_english, to_other), language, 1, english_trace),
        f"en>{language}": (qamus.symmetrise(to_other, to_english), "en", 0, other_trace),
    }
    lexicon, fit, measured = {}, {}, {}
    for name, (shares, source, column, trace) in directions.items():
        side = 1 - column  # the dictionary keyed by this direction's source words
        held = Counter(word for pair in split["train"] for word in set(pair[column]))
        shares = own_script(shares, scripts[source])
        bounds = qamus.lower_bounds(shares, held)
        tau, f1 = qamus.cutoff(bounds, gold["validation"][side])
        lexicon[name] = qamus.keep(shares, tau, by=bounds)
        fit[name] = {
            "iterations": len(trace) - 1,
            "heldout_log_likelihood": [round(value, 2) for value in trace],
            "cutoff": round(tau, 4),
            "validation_f1": round(f1, 4),
            "validation_words": len(gold["validation"][side]),
        }
        score = qamus.precision_at_1(lexicon[name], gold["test"][side])
        low, high = wilson_bounds(score["correct"], score["held"])
        measured[name] = {
            **score,
            "precision_at_1": round(score["correct"] / score["held"], 4) if score["held"] else 0.0,
            "wilson95": [round(low, 4), round(high, 4)],
            "coverage": round(score["held"] / score["words"], 4) if score["words"] else 0.0,
            "entries": len(lexicon[name]),
        }
    return {
        "format": qamus.FORMAT,
        "pair": [language, "en"],
        "scripts": scripts,
        "source": {
            "dataset": DATASET,
            "revision": REVISION,
            "licence": LICENCE,
            "files": {
                f"{name}/{s}/0000.parquet": sha256(path)
                for name, paths in files.items()
                for s, path in paths.items()
            },
            "pairs": {s: len(pairs) for s, pairs in split.items()},
        },
        "fit": fit,
        "measured": measured,
        "lexicon": lexicon,
    }


def render(lexicon: dict) -> bytes:
    return json.dumps(lexicon, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", required=True, help="a folder outside the repository for MASSIVE")
    parser.add_argument(
        "--check", action="store_true", help="fail if a file differs from a rebuild"
    )
    parser.add_argument("--languages", default=",".join(LOCALES))
    args = parser.parse_args()
    data = Path(args.data).resolve()
    if ROOT in data.parents or data == ROOT:
        parser.error("--data must be outside the repository")
    changed = []
    for language in [item.strip() for item in args.languages.split(",") if item.strip()]:
        text = render(build(language, data))
        digest = hashlib.sha256(text).hexdigest()
        path = qamus.DATA / f"{language}-en.json.gz"
        if args.check:
            shipped = gzip.decompress(path.read_bytes()) if path.exists() else b""
            same = hashlib.sha256(shipped).hexdigest() == digest
            print(f"{path.name}: {'same' if same else 'differs'} (sha256 {digest[:16]})")
            if not same:
                changed.append(path.name)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(gzip.compress(text, compresslevel=9, mtime=0))
        measured = json.loads(text)["measured"]
        print(
            f"{path.name}: {path.stat().st_size} bytes, sha256 {digest[:16]}; "
            + "; ".join(
                f"{name} P@1 {m['precision_at_1']} ({m['correct']}/{m['held']}), "
                f"coverage {m['coverage']}, {m['entries']} words"
                for name, m in measured.items()
            )
        )
    if changed:
        print("Out of date: " + ", ".join(changed), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
