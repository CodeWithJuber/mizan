"""Build Gharib, the word frequencies behind MIZAN's word information
(backend/tadbir/gharib.py), from wordfreq 3.1.1 and Lughah's Roman Hindi corpus.

wordfreq (Robyn Speer; code Apache-2.0, data CC BY-SA 4.0) ships word
frequencies for many languages in its wheel. The builder reads the wheel as a
zip archive, pinned by SHA-256, and imports none of its code: each list is a
gzipped msgpack ("cBpack": a header, then the words of each frequency, one
list per centibel). Give the wheel's path in a new folder outside the
repository and run with ``python -I``:

    pip download wordfreq==3.1.1 --no-deps -d /tmp/wordfreq_wheel
    python -I scripts/build_gharib.py --wheel /tmp/wordfreq_wheel/wordfreq-3.1.1-py3-none-any.whl
    python -I scripts/build_gharib.py --wheel ... --check   # fails if a rebuild differs

For English, Arabic, Hindi, Urdu and Tamil, the "small" list (every word at
least once per million running words) is read. Each listed word is cut into
words as MIZAN cuts text (``core.adaptive.tokenize``: "don't" is "don" and
"t"), each digit written 0, and each piece given its entry's frequency; the
pieces' frequencies are divided by their total plus the share of running words
the list leaves out (each taken as one word), and rounded to the centibel as
wordfreq rounds.

Roman Hindi/Urdu (``hi-latn``) has no wordfreq list. Its words are Lughah's
982 Roman Hindi sentences (Hinglish-Everyday-Conversations-1M, MIT; already
shipped in ``backend/tadbir/data/lughah``). Roman Hindi mixes English words
in, so each running word is a Roman Hindi word with probability λ or an
English one:

    P(w | hi-latn) = λ · P_roman(w) + (1 − λ) · P(w | en)

EM fits λ and P_roman, with each occurrence left out of its own word's
estimate (a word seen once is then no evidence of Roman Hindi: it is English
or unknown). Only the words Roman Hindi writes more often than English are
stored; the others are read from English.

Each language's floor is the information of its average running word,
Σ_w P(w | L) · information(w), with the words no list holds at −log 10^−6.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from core.adaptive import tokenize  # noqa: E402
from tadbir import gharib  # noqa: E402

WHEEL = "wordfreq-3.1.1-py3-none-any.whl"
WHEEL_SHA256 = "4b1c6ecffc6198be3396d5cf871c4423ca71c907c231348d352dd54d62b97473"
LISTS = {"en": "small_en", "ar": "small_ar", "hi": "small_hi", "ur": "small_ur", "ta": "small_ta"}
ROMAN = ROOT / "backend" / "tadbir" / "data" / "lughah" / "hi-latn.tsv"
CUT = round(-100 * math.log10(gharib.LEAST))  # 600 centibels: once per million


# ── reading wordfreq's lists ──────────────────────────────────────────────


def _unpack(data: bytes, at: int = 0) -> tuple[object, int]:
    """One msgpack value: the types a cBpack holds (maps, arrays, strings and
    small integers)."""
    kind = data[at]
    if kind <= 0x7F:
        return kind, at + 1
    if 0x80 <= kind <= 0x8F or kind in (0xDE, 0xDF):
        if kind <= 0x8F:
            size, at = kind & 0x0F, at + 1
        else:
            width = 2 if kind == 0xDE else 4
            size, at = int.from_bytes(data[at + 1 : at + 1 + width], "big"), at + 1 + width
        mapping = {}
        for _ in range(size):
            key, at = _unpack(data, at)
            value, at = _unpack(data, at)
            mapping[key] = value
        return mapping, at
    if 0x90 <= kind <= 0x9F or kind in (0xDC, 0xDD):
        if kind <= 0x9F:
            size, at = kind & 0x0F, at + 1
        else:
            width = 2 if kind == 0xDC else 4
            size, at = int.from_bytes(data[at + 1 : at + 1 + width], "big"), at + 1 + width
        items = []
        for _ in range(size):
            item, at = _unpack(data, at)
            items.append(item)
        return items, at
    if 0xA0 <= kind <= 0xBF or kind in (0xD9, 0xDA, 0xDB):
        if kind <= 0xBF:
            size, at = kind & 0x1F, at + 1
        else:
            width = {0xD9: 1, 0xDA: 2, 0xDB: 4}[kind]
            size, at = int.from_bytes(data[at + 1 : at + 1 + width], "big"), at + 1 + width
        return data[at : at + size].decode("utf-8"), at + size
    raise ValueError(f"unexpected msgpack type 0x{kind:02x} at {at}")


def read_list(archive: zipfile.ZipFile, name: str) -> tuple[list[list[str]], str]:
    raw = archive.read(f"wordfreq/data/{name}.msgpack.gz")
    data, _end = _unpack(gzip.decompress(raw))
    assert isinstance(data, list)
    header, bins = data[0], data[1:]
    if header != {"format": "cB", "version": 1}:
        raise ValueError(f"{name}: unexpected header {header!r}")
    return [list(words) for words in bins], hashlib.sha256(raw).hexdigest()


# ── words as MIZAN reads them ─────────────────────────────────────────────


def key(word: str, language: str) -> str:
    return gharib.shape(gharib.fold(word, language))[0]


def pieces(entry: str, language: str) -> list[str]:
    return [key(word, language) for word in tokenize(gharib.fold(entry, language))]


def frequencies(bins: list[list[str]], language: str) -> dict[str, float]:
    """Each MIZAN word's share of running words, from a list's entries."""
    mass: dict[str, float] = {}
    listed = 0.0
    produced = 0.0
    for centibels, words in enumerate(bins):
        p = 10 ** (-centibels / 100)
        for entry in words:
            listed += p
            cut = pieces(entry, language)
            produced += p * len(cut)
            for piece in cut:
                mass[piece] = mass.get(piece, 0.0) + p
    total = produced + max(0.0, 1.0 - listed)
    return {word: value / total for word, value in mass.items()}


def quantise(table: dict[str, float]) -> dict[str, int]:
    """Frequencies to the centibel, as wordfreq stores them, down to the cut."""
    found = {}
    for word, p in table.items():
        centibels = round(-100 * math.log10(p))
        if centibels <= CUT:
            found[word] = centibels
    return found


def as_read(stored: dict[str, dict[str, int]]) -> dict[str, dict[str, float]]:
    """The stored lists as ``gharib`` reads them."""
    return {
        language: {word: 10 ** (-centibels / 100) for word, centibels in table.items()}
        for language, table in stored.items()
    }


# ── Roman Hindi: a mixture with English, by EM ────────────────────────────


def roman(english: dict[str, float]) -> tuple[dict[str, float], float, dict]:
    """P_roman over words and λ, fitted on Lughah's Roman Hindi sentences."""
    counts: dict[str, int] = {}
    sentences = 0
    for line in ROMAN.read_text(encoding="utf-8").splitlines():
        words = [key(word, "hi-latn") for word in tokenize(line.partition("\t")[2])]
        if words:
            sentences += 1
            for word in words:
                counts[word] = counts.get(word, 0) + 1
    tokens = sum(counts.values())
    p_en = {word: gharib.chance({"en": english}, {}, word, "en") for word in counts}
    share = {word: 0.5 for word in counts}  # P(Roman Hindi | an occurrence of the word)
    weight = 0.5
    iterations = 0
    while iterations < 500:
        iterations += 1
        held = sum(counts[word] * share[word] for word in counts)
        updated = {}
        for word, count in counts.items():
            # P_roman of this occurrence from the other occurrences only.
            rest = held - share[word]
            left_out = (count - 1) * share[word] / rest if rest > 0 else 0.0
            left_out *= 10.0 ** -gharib.shape(word)[1]
            either = weight * left_out + (1 - weight) * p_en[word]
            updated[word] = weight * left_out / either if either > 0 else 0.0
        share = updated
        before, weight = weight, sum(counts[w] * share[w] for w in counts) / tokens
        if abs(weight - before) < 1e-10:
            break
    held = sum(counts[word] * share[word] for word in counts)
    p_roman = {word: counts[word] * share[word] / held for word in counts if share[word] > 0}
    fit = {
        "sentences": sentences,
        "tokens": tokens,
        "words": len(counts),
        "lambda": round(weight, 6),
        "iterations": iterations,
        "roman_words": len(p_roman),
        "source_sha256": hashlib.sha256(ROMAN.read_bytes()).hexdigest(),
    }
    return p_roman, weight, fit


# ── floors ────────────────────────────────────────────────────────────────


def floor(tables: dict, mixed: dict, language: str) -> float:
    """The information of an average running word of the language, as
    ``gharib`` reads words: Σ P(w) · information(w), the words no list holds
    at the most. A number's shape stands for 10^digits numbers, each with its
    share."""
    own = tables.get(language, {})
    base, share = mixed.get(language, ("", 0.0))
    words = set(own) | set(tables.get(base, {}))
    total = 0.0
    held = 0.0
    for word in sorted(words):
        mass = own.get(word, share * tables.get(base, {}).get(word, 0.0))
        held += mass
        total += mass * -math.log(gharib.chance(tables, mixed, word, language))
    return total + max(0.0, 1.0 - held) * gharib.MOST_INFORMATION


def build(wheel: Path) -> dict:
    archive = zipfile.ZipFile(wheel)
    stored: dict[str, dict[str, int]] = {}
    files = {}
    for language, name in LISTS.items():
        bins, digest = read_list(archive, name)
        files[f"wordfreq/data/{name}.msgpack.gz"] = digest
        stored[language] = quantise(frequencies(bins, language))
    english = as_read(stored)["en"]
    p_roman, weight, fit = roman(english)
    stored["hi-latn"] = quantise(
        {word: weight * p + (1 - weight) * english.get(word, 0.0) for word, p in p_roman.items()}
    )
    mixed = {"hi-latn": ("en", round(1 - weight, 6))}
    tables = as_read(stored)
    languages = {}
    for language in gharib.LANGUAGES:
        bins: dict[str, list[str]] = {}
        for word, centibels in stored[language].items():
            bins.setdefault(str(centibels), []).append(word)
        languages[language] = {
            "floor": round(floor(tables, mixed, language), 6),
            "words": len(stored[language]),
            "bins": {c: sorted(bins[c]) for c in sorted(bins, key=int)},
        }
    return {
        "format": gharib.FORMAT,
        "source": {
            "wordfreq": {
                "wheel": WHEEL,
                "sha256": WHEEL_SHA256,
                "files": files,
                "licence": "data CC BY-SA 4.0 (code Apache-2.0)",
            },
            "hi-latn": {
                "file": "backend/tadbir/data/lughah/hi-latn.tsv",
                "licence": "MIT (Hinglish-Everyday-Conversations-1M)",
            },
        },
        "least": gharib.LEAST,
        "fit": {"hi-latn": fit},
        "mixed": {code: {"base": base, "share": share} for code, (base, share) in mixed.items()},
        "languages": languages,
    }


def render(built: dict) -> bytes:
    return json.dumps(built, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--wheel", required=True, help=f"{WHEEL}, outside the repository")
    parser.add_argument(
        "--check", action="store_true", help="fail if the shipped file differs from a rebuild"
    )
    args = parser.parse_args()
    wheel = Path(args.wheel).resolve()
    if ROOT in wheel.parents:
        parser.error("--wheel must be outside the repository")
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    if digest != WHEEL_SHA256:
        parser.error(f"{wheel.name}: sha256 {digest} is not the pinned {WHEEL_SHA256}")
    text = render(build(wheel))
    built = hashlib.sha256(text).hexdigest()
    path = gharib.DATA / "words.json.gz"
    if args.check:
        shipped = gzip.decompress(path.read_bytes()) if path.exists() else b""
        same = hashlib.sha256(shipped).hexdigest() == built
        print(f"{path.name}: {'same' if same else 'differs'} (sha256 {built[:16]})")
        return 0 if same else 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(text, compresslevel=9, mtime=0))
    data = json.loads(text)
    print(
        f"{path.name}: {path.stat().st_size} bytes, sha256 {built[:16]}; "
        + "; ".join(
            f"{language} {entry['words']} words, floor {entry['floor']:.3f}"
            for language, entry in data["languages"].items()
        )
        + f"; hi-latn λ {data['fit']['hi-latn']['lambda']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
