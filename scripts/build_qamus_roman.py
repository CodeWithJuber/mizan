"""Build Qāmūs's reading of Roman Hindi and Urdu (backend/tadbir/qamus.py, ``read_roman``).

A word of Hindi or Urdu written in Latin letters ("duniya", "banwaya") is read
as the Devanagari or Urdu word it most probably spells, so the lexicon can
translate it. How native words are written in Latin letters is learned from
**Aksharantar** (AI4Bharat; manually collected pairs CC BY 4.0, mined pairs and
existing sources CC0), read at a pinned commit; its rows taken from Dakshina
(CC BY-SA 4.0 upstream) are left out. Which words there are, and how common,
is read from **MASSIVE 1.1** (Amazon, CC BY 4.0), the corpus Qāmūs's lexicons
were learned from. Both are downloaded into ``--data``, a new folder outside
the repository; run with ``python -I`` so nothing in it can be imported:

    python -I scripts/build_qamus_roman.py --data /tmp/qamus_roman_data          # writes backend/tadbir/data/qamus/hi-latn.json.gz
    python -I scripts/build_qamus_roman.py --data /tmp/qamus_roman_data --check  # fails if a rebuild differs

For Hindi and Urdu each:

1. A noisy channel P(roman | native) (``qamus.channel``): each native letter,
   with the marks written on it and in its context (what follows it; for Urdu,
   whose short vowels are not written, the next letter itself), writes 0 to 4
   Roman letters. Fitted by EM on 100,000 training pairs drawn with a fixed
   seed, stopped by the log-likelihood of the validation pairs (at most 30
   iterations).
2. The vocabulary: the native words of MASSIVE's train split for the locale,
   with their counts.
3. Each vocabulary word's 30 most probable spellings; each spelling is read
   as the word it most probably spells, P(d | r) ∝ P(r | d) · P(d), with
   P(d) = (count + 1) / (N + |V|) (``qamus.readings``). A reading is kept when
   it is decisive, P(d | r) > ½, and the spelling is no English word (a word
   of MASSIVE's English train split outside its slots, or of Lughah's English
   corpus: "main", "the"), unless English writes that very word so (the
   lexicon translates "राजधानी" as "rajdhani"). For Urdu only words the lexicon translates are kept; for
   Hindi every word, since a Roman claim is read by the NLI model in
   Devanagari (``qamus.devanagari``).

Measured on Aksharantar's test split (Dakshina's rows included: nothing is
learned from it): the share of pairs whose gold spelling is among the native
word's 1, 5, 10 and 30 most probable spellings, and, of the pairs whose native
word is in the vocabulary, how often the gold spelling is read as that word.
Needs ``pyarrow`` and ``huggingface_hub``.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import random
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from tadbir import qamus  # noqa: E402

DATASET = "ai4bharat/Aksharantar"
REVISION = "e418c1fc928d9f5393af33268472cf20c1891be8"
LICENCE = "manually collected pairs CC BY 4.0; mined pairs and existing sources CC0"
LEFT_OUT = ("Dakshina",)  # CC BY-SA 4.0 upstream
MASSIVE = "AmazonScience/massive"
MASSIVE_REVISION = "ed58ac423a2f4121720918bf5301577edce4ffd3"  # refs/convert/parquet
LANGUAGES = {
    # language: (Aksharantar name, MASSIVE locale, script, what a unit's context is)
    "hi": ("hin", "hi-IN", "DEVANAGARI", "kind"),
    "ur": ("urd", "ur-PK", "ARABIC", "letter"),
}
PAIRS = 100_000
SEED = 0
ITERATIONS = 30  # a bound only: EM stops when the held-out pairs stop improving
SLOT = re.compile(r"\[[^\]]*\]")
SPELLINGS = 30
LONGEST = 20  # native letters: longer rows are run-together words


def fetch(data: Path, repo: str, name: str, revision: str) -> Path:
    from huggingface_hub import hf_hub_download

    return Path(
        hf_hub_download(repo, name, repo_type="dataset", revision=revision, local_dir=str(data))
    )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


Row = tuple[str, str, str]  # native word, Roman spelling, source


def rows(archive: Path, name: str, split: str) -> list[Row]:
    with zipfile.ZipFile(archive) as opened:
        text = opened.read(f"{name}_{split}.json").decode("utf-8")
    found = []
    for line in text.splitlines():
        if line.strip():
            row = json.loads(line)
            found.append((row["native word"], row["english word"], row["source"]))
    return found


def pairs(found: list[Row], follow: str) -> list[tuple[list[str], str]]:
    """(native contexts, Roman letters) of the rows a channel can write."""
    kept = []
    for native, spelled, _source in found:
        letters = qamus.contexts(native, follow)
        roman = qamus.roman_letters(spelled)
        if roman and 0 < len(letters) <= LONGEST and len(roman) <= qamus.CHUNK * len(letters):
            kept.append((letters, roman))
    return kept


def words(parquet: Path, written: str | None = None) -> Counter:
    import pyarrow.parquet as pq

    counts: Counter = Counter()
    for utterance in pq.read_table(parquet, columns=["utt"]).column("utt").to_pylist():
        counts.update(
            word
            for word in qamus.tokens(utterance)
            if written is None or qamus.script(word) == written
        )
    return counts


def english(data: Path) -> set[str]:
    """English words: those of MASSIVE's English train split outside its
    annotated slots, and Lughah's English corpus. A slot's value may be a name
    or a word of India in Latin letters ("rajdhani express", "biryani"), which
    is Roman Hindi as well."""
    import pyarrow.parquet as pq

    parquet = fetch(data, MASSIVE, "en-US/train/0000.parquet", MASSIVE_REVISION)
    found: set[str] = set()
    for annotated in pq.read_table(parquet, columns=["annot_utt"]).column("annot_utt").to_pylist():
        found.update(qamus.tokens(SLOT.sub(" ", annotated)))
    corpus = ROOT / "backend" / "tadbir" / "data" / "lughah" / "en.tsv"
    for line in corpus.read_text(encoding="utf-8").splitlines():
        found.update(qamus.tokens(line.partition("\t")[2]))
    return found


def rate(hits: int, total: int) -> float:
    return round(hits / total, 4) if total else 0.0


def build(language: str, data: Path, known_english: set[str]) -> tuple[dict, dict, dict]:
    name, locale, written, follow = LANGUAGES[language]
    archive = fetch(data, DATASET, f"{name}.zip", REVISION)
    massive = fetch(data, MASSIVE, f"{locale}/train/0000.parquet", MASSIVE_REVISION)
    train = [row for row in rows(archive, name, "train") if row[2] not in LEFT_OUT]
    random.Random(SEED).shuffle(train)
    learned = pairs(train, follow)[:PAIRS]
    heldout = pairs([row for row in rows(archive, name, "valid") if row[2] not in LEFT_OUT], follow)
    table, trace = qamus.channel(learned, heldout, limit=ITERATIONS)

    vocabulary = words(massive, written)
    found = qamus.readings(vocabulary, table, follow, keep=SPELLINGS)
    read = {
        roman: word
        for roman, (word, p) in sorted(found.items())
        if 2 * p > 1
        and len(roman) > 1
        # An English word is not read, unless English writes this very word so
        # (the lexicon gives "rajdhani" as a translation of "राजधानी").
        and (roman not in known_english or roman in qamus.translate(word, "en"))
        and (language == "hi" or qamus.translate(word, "en"))
    }

    # Held out: Aksharantar's test split.
    test = rows(archive, name, "test")
    ranks = Counter()
    in_vocabulary = right = 0
    for written_word, spelled_word, _source in test:
        roman = qamus.roman_letters(spelled_word)
        spelled = [r for r, _p in qamus.spellings(qamus.contexts(written_word, follow), table)]
        for k in (1, 5, 10, SPELLINGS):
            ranks[k] += roman in spelled[:k]
        native = qamus._visible(written_word)
        if native in vocabulary:
            in_vocabulary += 1
            right += found.get(roman, ("", 0.0))[0] == native
    measured = {
        "test_pairs": len(test),
        "spelling_recall_at": {str(k): rate(ranks[k], len(test)) for k in sorted(ranks)},
        "in_vocabulary": in_vocabulary,
        "read_right": right,
        "read_accuracy": rate(right, in_vocabulary),
    }
    fit = {
        "follow": follow,
        "training_pairs": len(learned),
        "heldout_pairs": len(heldout),
        "iterations": len(trace),
        "heldout_log_likelihood": [round(value, 2) for value in trace],
        "units": sum(1 for unit in table if not unit.endswith("\t*")),
        "vocabulary": len(vocabulary),
        "readings": len(read),
    }
    files = {f"{name}.zip": sha256(archive), f"{locale}/train/0000.parquet": sha256(massive)}
    return {"fit": fit, "measured": measured, "files": files}, read, files


def render(built: dict) -> bytes:
    return json.dumps(built, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", required=True, help="a folder outside the repository")
    parser.add_argument(
        "--check", action="store_true", help="fail if the shipped file differs from a rebuild"
    )
    args = parser.parse_args()
    data = Path(args.data).resolve()
    if ROOT in data.parents or data == ROOT:
        parser.error("--data must be outside the repository")
    known_english = english(data)
    built: dict = {
        "format": qamus.ROMAN_FORMAT,
        "source": {
            "dataset": DATASET,
            "revision": REVISION,
            "licence": LICENCE,
            "left_out": list(LEFT_OUT),
            "vocabulary": {
                "dataset": MASSIVE,
                "revision": MASSIVE_REVISION,
                "licence": "CC BY 4.0",
            },
            "files": {},
        },
        "fit": {},
        "measured": {},
        "read": {},
    }
    for language in LANGUAGES:
        report, read, files = build(language, data, known_english)
        built["fit"][language] = report["fit"]
        built["measured"][language] = report["measured"]
        built["source"]["files"].update(files)
        built["read"][language] = read
        print(f"{language}: {report['fit']} {report['measured']}", flush=True)
    text = render(built)
    digest = hashlib.sha256(text).hexdigest()
    path = qamus.DATA / qamus.ROMAN
    if args.check:
        shipped = gzip.decompress(path.read_bytes()) if path.exists() else b""
        same = hashlib.sha256(shipped).hexdigest() == digest
        print(f"{path.name}: {'same' if same else 'differs'} (sha256 {digest[:16]})")
        return 0 if same else 1
    path.write_bytes(gzip.compress(text, compresslevel=9, mtime=0))
    print(f"{path.name}: {path.stat().st_size} bytes, sha256 {digest[:16]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
