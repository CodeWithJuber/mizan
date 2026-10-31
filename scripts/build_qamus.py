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
split's slot dictionary; precision@1 measured on the test split's.

Names are written, not translated. A word is a name when more than half of
its occurrences lie inside slots a translator did not translate (localised, or
copied unchanged): for English in any of the four locales, for the other
language in its own. A word is an entity when more than half of its
occurrences lie inside annotated slots. A pair with a name on either side is
kept only when both words are entities and sound alike: the other script's word
is romanised (anyascii 0.3.2, ISC) and the consonant skeletons compared
(``qamus.sounds_alike``) against a cut-off σ fitted per pair on the validation
split by Youden's J, with the one-standard-error rule: the translated slots of
the name types (types the translators did not translate in more than half of
their slots, over the four locales) against the same names shuffled within
their slot type. Tokens that are pieces of a word written apart
(``qamus.pieces``) are dropped. Needs ``pyarrow`` and ``anyascii==0.3.2``.

With ``--extra``, Hindi also learns from **PMIndia** v1 (Haddow and Kirefu,
2020; CC BY 4.0), the news updates of the Prime Minister of India's website in
English and Hindi, pinned by SHA-256 and downloaded into ``--data``: its pairs
are added to MASSIVE's train pairs (``EXTRA``), every pair with at most
``LONGEST`` words a side, exact duplicates dropped. Everything else is fitted
and measured on MASSIVE as above; pieces are judged over all the training
text. Measured and not adopted (``docs/qamus.md``): the shipped lexicons are
built without it.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import shutil
import sys
import urllib.request
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
ROMANISER = ("anyascii", "0.3.2")  # ISC licence
_SLOT = re.compile(r"\[\s*([^\]:]+?)\s*:\s*([^\]]*?)\s*\]")
# Parallel text learned from besides MASSIVE's train split with ``--extra``, per
# language: a tab-separated file of (English, the language) sentence pairs,
# pinned by SHA-256. Measured, not adopted (docs/qamus.md).
EXTRA = {
    "hi": {
        "dataset": "PMIndia v1",
        "url": "https://data.statmt.org/pmindia/v1/parallel/pmindia.v1.hi-en.tsv",
        "file": "pmindia.v1.hi-en.tsv",
        "sha256": "bfa9fe6c994f492a79c288cbd8ba95a3b0c9407997f453b59e6dc4b13bd2029f",
        "licence": "CC BY 4.0",
    },
}
LONGEST = 40  # words a side: IndicTrans2's cut-off for mined pairs; IBM Model 1 is quadratic


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


def download(data: Path, source: dict) -> Path:
    """A pinned file, downloaded once into ``data``; a file whose SHA-256 is not
    the pinned one is refused."""
    path = data / source["file"]
    if not path.exists():
        if not source["url"].startswith("https://"):
            raise SystemExit(f"{source['url']}: only https is fetched")
        data.mkdir(parents=True, exist_ok=True)
        partial = path.with_name(path.name + ".part")
        with urllib.request.urlopen(source["url"], timeout=300) as response:  # noqa: S310 - https only
            with partial.open("wb") as out:
                shutil.copyfileobj(response, out)
        partial.replace(path)
    if sha256(path) != source["sha256"]:
        raise SystemExit(f"{path.name}: its SHA-256 is not the pinned {source['sha256'][:16]}")
    return path


def extra_pairs(data: Path, language: str) -> tuple[list[tuple[list[str], list[str]]], dict]:
    """The language's extra (English words, its words) pairs (``EXTRA``), in
    the file's order: both sides with words, at most ``LONGEST`` words a side,
    each pair once; and what was read."""
    source = EXTRA.get(language)
    if source is None:
        return [], {}
    path = download(data, source)
    pairs: list[tuple[list[str], list[str]]] = []
    seen: set[tuple[tuple[str, ...], tuple[str, ...]]] = set()
    for line in path.read_text(encoding="utf-8").split("\n"):
        english, _, other = line.rstrip("\r").partition("\t")
        e, x = qamus.tokens(english), qamus.tokens(other)
        key = (tuple(e), tuple(x))
        if not e or not x or max(len(e), len(x)) > LONGEST or key in seen:
            continue
        seen.add(key)
        pairs.append((e, x))
    read = {key: source[key] for key in ("dataset", "url", "sha256", "licence")}
    return pairs, {**read, "pairs": len(pairs), "longest": LONGEST}


def read(path: Path) -> dict[str, dict]:
    import pyarrow.parquet as pq

    table = pq.read_table(path, columns=["id", "intent", "utt", "annot_utt", "slot_method"])
    return {str(row["id"]): row for row in table.to_pylist()}


def romaniser():
    """anyascii at the pinned version: another version may romanise differently."""
    from importlib.metadata import PackageNotFoundError, version

    try:
        installed = version(ROMANISER[0])
    except PackageNotFoundError:
        installed = ""
    if installed != ROMANISER[1]:
        raise SystemExit(
            f"needs {ROMANISER[0]}=={ROMANISER[1]} (pip install it), found {installed!r}"
        )
    from anyascii import anyascii

    return anyascii


def slot_methods(row: dict) -> list[tuple[str, str]]:
    method = row.get("slot_method") or {}
    return list(zip(method.get("slot") or [], method.get("method") or [], strict=False))


def name_types(data: Path) -> list[str]:
    """Slot types the translators did not translate (localised, or copied
    unchanged) in more than half of their slots, over the four locales' train
    splits: the values of these slots are names (a person, a place, a shop)."""
    total: Counter = Counter()
    kept: Counter = Counter()
    for locale in LOCALES.values():
        for row in read(fetch(data, locale)["train"]).values():
            for kind, how in slot_methods(row):
                total[kind] += 1
                kept[kind] += how != "translation"
    return sorted(kind for kind in total if 2 * kept[kind] > total[kind])


def name_words(rows: dict[str, dict], judges: list[dict[str, dict]]) -> tuple[set[str], set[str]]:
    """The names, and the entities, among a side's words.

    A word is a name, a value localisation swaps, when more than half of its
    occurrences lie inside a slot that a translator did not translate
    (localised it, or copied it unchanged). An English slot was handled by the
    translator of each locale (``judges``), another language's by its own.
    "pakistan" (1 of 1), "london" (22 of 24) and "mumbai" (12 of 12) are names;
    "friday" (22 of 94), "airport" (2 of 12) and "accept" (0 of 1) are not.
    A word is an entity when more than half of its occurrences lie inside an
    annotated slot of any kind ("الهند", which Arabic translators translated)."""
    swapped: Counter = Counter()
    slotted: Counter = Counter()
    total: Counter = Counter()
    for i, row in rows.items():
        untranslated = {
            kind
            for judge in judges
            if i in judge
            for kind, how in slot_methods(judge[i])
            if how != "translation"
        }
        for kind, value in _SLOT.findall(row["annot_utt"] or ""):
            words = qamus.tokens(value)
            slotted.update(words)
            if kind in untranslated:
                swapped.update(words)
        total.update(qamus.tokens(row["utt"]))
    names = {word for word, count in total.items() if 2 * swapped[word] > count}
    entities = {word for word, count in total.items() if 2 * slotted[word] > count}
    return names, entities


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


def single_word_slots(
    english: dict[str, dict], other: dict[str, dict], scripts: dict[str, str], language: str
) -> list[tuple[str, str, str]]:
    """(slot type, other word, English word) of each slot type that occurs once
    on each side, that the translator marked as translated, and whose value is
    one word in its own script on each side."""
    found = []
    for i in sorted(set(english) & set(other), key=int):
        how = methods(other[i])
        ours = slots(english[i]["annot_utt"])
        theirs = slots(other[i]["annot_utt"])
        for kind in sorted({kind for kind, _ in ours}):
            mine = [value for k, value in ours.elements() if k == kind]
            yours = [value for k, value in theirs.elements() if k == kind]
            if len(mine) != 1 or len(yours) != 1 or how.get(kind) != {"translation"}:
                continue
            e, x = qamus.tokens(mine[0]), qamus.tokens(yours[0])
            if len(e) != 1 or len(x) != 1 or e == x:
                continue
            if qamus.script(e[0]) != scripts["en"] or qamus.script(x[0]) != scripts[language]:
                continue
            found.append((kind, x[0], e[0]))
    return found


def name_pairs(
    found: list[tuple[str, str, str]], types: set[str]
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Held-out name pairs: the translated name slots (some of them in truth
    hold another name), and the same names shuffled within their slot type
    (each other word paired with the next pair's English word)."""
    by_kind: dict[str, list[tuple[str, str]]] = {}
    for kind, x, e in found:
        if kind in types and (x, e) not in by_kind.setdefault(kind, []):
            by_kind[kind].append((x, e))
    positives: list[tuple[str, str]] = []
    negatives: list[tuple[str, str]] = []
    for kind in sorted(by_kind):
        pairs = sorted(by_kind[kind])
        positives += pairs
        shifted = [e for _x, e in pairs[1:] + pairs[:1]]
        negatives += [
            (x, e) for (x, _e), e in zip(pairs, shifted, strict=True) if (x, e) not in pairs
        ]
    return positives, negatives


def dictionary(
    found: list[tuple[str, str, str]], types: set[str]
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """The held-out dictionary of one split, both ways: the translated slots of
    the types translators translate (dates, devices, numbers). Names are left
    out: a name slot marked as translated often holds another name, and names
    are measured by the name filter's own test."""
    other_to_english: dict[str, set[str]] = {}
    english_to_other: dict[str, set[str]] = {}
    for kind, x, e in found:
        if kind not in types:
            other_to_english.setdefault(x, set()).add(e)
            english_to_other.setdefault(e, set()).add(x)
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


def rate(hits: int, total: int) -> float:
    return round(hits / total, 4) if total else 0.0


def english_names(data: Path) -> tuple[set[str], set[str]]:
    """English names and entities, judged by all four locales' translators."""
    judges = [read(fetch(data, locale)["train"]) for locale in LOCALES.values()]
    return name_words(read(fetch(data, ENGLISH)["train"]), judges)


def build(
    language: str,
    data: Path,
    types: list[str],
    english: tuple[set[str], set[str]],
    with_extra: bool = False,
) -> dict:
    romanise = romaniser()
    name_kinds = set(types)
    locale = LOCALES[language]
    files = {name: fetch(data, name) for name in (ENGLISH, locale)}
    rows = {
        (name, split): read(path) for name, paths in files.items() for split, path in paths.items()
    }
    split = {s: parallel(rows[(ENGLISH, s)], rows[(locale, s)]) for s in SPLITS}
    scripts = {"en": written_in(split["train"], 0), language: written_in(split["train"], 1)}
    massive = {s: len(pairs) for s, pairs in split.items()}
    added, added_from = extra_pairs(data, language) if with_extra else ([], {})
    split["train"] = split["train"] + added
    found = {
        s: single_word_slots(rows[(ENGLISH, s)], rows[(locale, s)], scripts, language)
        for s in ("validation", "test")
    }
    gold = {s: dictionary(found[s], name_kinds) for s in found}

    # Names: which words are names, and how alike a name pair must sound.
    names = {
        "en": english,
        language: name_words(rows[(locale, "train")], [rows[(locale, "train")]]),
    }

    def alike(other: str, english: str) -> float:
        return qamus.sounds_alike(romanise(other), english)

    held_out = {s: name_pairs(found[s], name_kinds) for s in found}
    sigma, j = qamus.youden(
        [alike(x, e) for x, e in held_out["validation"][0]],
        [alike(x, e) for x, e in held_out["validation"][1]],
    )
    positives, negatives = held_out["test"]
    true_pass = sum(alike(x, e) >= sigma for x, e in positives)
    false_pass = sum(alike(x, e) >= sigma for x, e in negatives)
    name_filter = {
        "sigma": round(sigma, 4),
        "validation_j": round(j, 4),
        "validation_pairs": [len(held_out["validation"][0]), len(held_out["validation"][1])],
        "test": {
            "positives": len(positives),
            "negatives": len(negatives),
            "passed_positives": true_pass,
            "passed_negatives": false_pass,
            "recall": rate(true_pass, len(positives)),
            "false_pass": rate(false_pass, len(negatives)),
            "precision": rate(true_pass, true_pass + false_pass),
        },
    }
    # Pieces: tokens that are parts of a word written apart.
    pieces = {
        "en": qamus.pieces(
            [qamus.tokens(row["utt"]) for row in rows[(ENGLISH, "train")].values()]
            + [e for e, _x in added]
        ),
        language: qamus.pieces(
            [qamus.tokens(row["utt"]) for row in rows[(locale, "train")].values()]
            + [x for _e, x in added]
        ),
    }

    # t(e | x): English generated from the other language, and t(x | e) back.
    flipped = {s: [(x, e) for e, x in pairs] for s, pairs in split.items()}
    to_english, english_trace = qamus.ibm1(flipped["train"], flipped["validation"])
    to_other, other_trace = qamus.ibm1(split["train"], split["validation"])
    directions = {
        f"{language}>en": (
            qamus.symmetrise(to_english, to_other),
            language,
            "en",
            1,
            english_trace,
        ),
        f"en>{language}": (qamus.symmetrise(to_other, to_english), "en", language, 0, other_trace),
    }
    lexicon, fit, measured = {}, {}, {}
    for name, (shares, source, target, column, trace) in directions.items():
        side = 1 - column  # the dictionary keyed by this direction's source words
        held = Counter(word for pair in split["train"] for word in set(pair[column]))
        shares = own_script(shares, scripts[source])

        def piece(a: str, b: str, source: str = source, target: str = target) -> bool:
            return a in pieces[source] or b in pieces[target]

        def swap(a: str, b: str, source: str = source, target: str = target) -> bool:
            # A name is written as a name, by its sounds: a pair with a name
            # on either side is kept only when both words are entities and
            # they sound alike ("गाड़ी", a car, is no name for "london").
            (names_a, entities_a), (names_b, entities_b) = names[source], names[target]
            if a not in names_a and b not in names_b:
                return False
            if a not in entities_a or b not in entities_b:
                return True
            other, english = (a, b) if source == language else (b, a)
            return alike(other, english) < sigma

        # P is not shared again among what is left: when a name's candidates
        # were other names, what is left is words it was never written as
        # (measured: renormalising gave "بھارت" → about, "پاکستان" → post).
        filtered = {
            a: {b: p for b, p in row.items() if not piece(a, b) and not swap(a, b)}
            for a, row in shares.items()
        }
        bounds = qamus.lower_bounds(filtered, held)
        tau, f1 = qamus.cutoff(bounds, gold["validation"][side])
        lexicon[name] = qamus.keep(filtered, tau, by=bounds)
        # What each filter took out of what the cut-off would have kept.
        before = qamus.lower_bounds(shares, held)
        passing = [(a, b) for a, row in shares.items() for b in row if before[a][b] >= tau]
        fit[name] = {
            "iterations": len(trace) - 1,
            "heldout_log_likelihood": [round(value, 2) for value in trace],
            "cutoff": round(tau, 4),
            "validation_f1": round(f1, 4),
            "validation_words": len(gold["validation"][side]),
            "removed": {
                "pieces": sum(1 for a, b in passing if piece(a, b)),
                "names": sum(1 for a, b in passing if not piece(a, b) and swap(a, b)),
            },
        }
        score = qamus.precision_at_1(lexicon[name], gold["test"][side])
        low, high = wilson_bounds(score["correct"], score["held"])
        measured[name] = {
            **score,
            "precision_at_1": rate(score["correct"], score["held"]),
            "wilson95": [round(low, 4), round(high, 4)],
            "coverage": rate(score["held"], score["words"]),
            "entries": len(lexicon[name]),
        }
    measured["names"] = name_filter
    return {
        "format": qamus.FORMAT,
        "pair": [language, "en"],
        "scripts": scripts,
        "source": {
            "dataset": DATASET,
            "revision": REVISION,
            "licence": LICENCE,
            "romaniser": " ".join(ROMANISER),
            "files": {
                f"{name}/{s}/0000.parquet": sha256(path)
                for name, paths in files.items()
                for s, path in paths.items()
            },
            "pairs": massive,
            **({"extra": added_from} if added_from else {}),
        },
        "fit": {**fit, "name_types": types, "pieces": {k: len(v) for k, v in pieces.items()}},
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
    parser.add_argument(
        "--extra",
        action="store_true",
        help="also learn from EXTRA (PMIndia for Hindi): measured, not adopted",
    )
    args = parser.parse_args()
    data = Path(args.data).resolve()
    if ROOT in data.parents or data == ROOT:
        parser.error("--data must be outside the repository")
    changed = []
    types = name_types(data)
    english = english_names(data)
    for language in [item.strip() for item in args.languages.split(",") if item.strip()]:
        text = render(build(language, data, types, english, with_extra=args.extra))
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
        built = json.loads(text)
        measured = built["measured"]
        print(
            f"{path.name}: {path.stat().st_size} bytes, sha256 {digest[:16]}; "
            + "; ".join(
                f"{name} P@1 {m['precision_at_1']} ({m['correct']}/{m['held']}), "
                f"coverage {m['coverage']}, {m['entries']} words, "
                f"removed {built['fit'][name]['removed']}"
                for name, m in measured.items()
                if name != "names"
            )
            + f"; names {measured['names']}"
        )
    if changed:
        print("Out of date: " + ", ".join(changed), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
