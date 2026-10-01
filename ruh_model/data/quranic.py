"""Pinned Quranic editions and attributed training paths, without text rewriting.

Sources keep their own licences. Downloads are byte-identical snapshots; Unicode
folding is used only for edition comparison and never for training targets.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

REVISION = "6523a9ad3b73bb7e8cb3a9cdf0ea774b8bab3123"
BASE = f"https://raw.githubusercontent.com/risan/quran-json/{REVISION}/"
QAC_REVISION = "b5abd4d8fadd775f3329f34cbe10531fac71e391"
CHAPTER_LENGTHS = (
    7,
    286,
    200,
    176,
    120,
    165,
    206,
    75,
    129,
    109,
    123,
    111,
    43,
    52,
    99,
    128,
    111,
    110,
    98,
    135,
    112,
    78,
    118,
    64,
    77,
    227,
    93,
    88,
    69,
    60,
    34,
    30,
    73,
    54,
    45,
    83,
    182,
    88,
    75,
    85,
    54,
    53,
    89,
    59,
    37,
    35,
    38,
    29,
    18,
    45,
    60,
    49,
    62,
    55,
    78,
    96,
    29,
    22,
    24,
    13,
    14,
    11,
    11,
    18,
    12,
    12,
    30,
    52,
    52,
    44,
    28,
    28,
    20,
    56,
    40,
    31,
    50,
    40,
    46,
    42,
    29,
    19,
    36,
    25,
    22,
    17,
    19,
    26,
    30,
    20,
    15,
    21,
    11,
    8,
    8,
    19,
    5,
    8,
    8,
    11,
    11,
    8,
    3,
    9,
    5,
    4,
    7,
    3,
    6,
    3,
    5,
    4,
    5,
    6,
)
SOURCES = {
    "tanzil": {
        "url": BASE + "data/tanzil/uthmani.json",
        "sha256": "adaebb377c60eba1bab6ef652959c7a0b4ccb4d0ca42145945c14ecdbeb4b761",
        "attribution": "Tanzil Project, Uthmani Hafs text, via risan/quran-json",
        "license": "CC BY 3.0; verbatim text only; Copyright (C) 2007-2021 Tanzil Project",
        "license_url": "https://tanzil.net/docs/text_license",
        "revision": REVISION,
    },
    "qpc_hafs": {
        "url": BASE + "data/quranpedia/qpc-hafs.json",
        "sha256": "0136b913aeb5a6a0389681f988215791ddd848c4347f7cf5e9d2574db7f1da49",
        "attribution": "KFGQPC Hafs edition, Quranpedia.net dump 2026-09-30",
        "license": "Quranpedia Data License: credited redistribution with dump version",
        "license_url": "https://api.quranpedia.net/dumps/LICENSE.md",
        "revision": REVISION,
        "dump_version": "2026-09-30",
    },
    "pickthall": {
        "url": BASE + "data/extra/english_pickthall.json",
        "sha256": "f93ecb2a50578c9cc4e5b89630e79fa9bcdd1d289b1a858f2aedf5aa55e8194a",
        "attribution": "Marmaduke Pickthall, The Meaning of the Glorious Koran (1930)",
        "license": "Public domain original translation; snapshot terms in source_metadata",
        "license_url": "https://cdn.jsdelivr.net/gh/fawazahmed0/quran-api@1/editions/eng-mohammedmarmadu.json",
        "revision": REVISION,
    },
    "qac": {
        "url": (
            "https://raw.githubusercontent.com/cltk/arabic_morphology_quranic-corpus/"
            + QAC_REVISION
            + "/quranic-corpus-morphology-0.4.txt"
        ),
        "sha256": "a1d12923815341face765083805d2148ed2d9f5cc3f7d6665219d887675d8c46",
        "attribution": "Kais Dukes, Quranic Arabic Corpus morphology version 0.4 (2011)",
        "license": "GNU GPL with original verbatim-copy notice; embedded Tanzil BY-ND 3.0",
        "license_url": "https://corpus.quran.com/download/",
        "revision": QAC_REVISION,
    },
    "source_metadata": {
        "url": BASE + "data/meta/sources.json",
        "sha256": "117045528f8ab07e21f702d45437d1b7e8c9ed22ab580574df0b9b7db06c7723",
        "revision": REVISION,
    },
}

# Standard Buckwalter plus Quranic extensions documented by QAC. Unknown symbols
# fail closed rather than silently manufacturing an Arabic spelling.
BUCKWALTER = dict(
    zip(
        "'|>&<}AbptvjHxd*rzs$SDTZEg_fqklmnhwYyFNKaui~o`{:@\"[;,.!-+%]^# ",
        "ءآأؤإئابةتثجحخدذرزسشصضطظعغـفقكلمنهوىيًٌٍَُِّْٰٱۣۜ۟۠ۢۥۦ۪ۭۨ۫۬ٓٔ ",
        strict=True,
    )
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch_sources(cache: Path) -> dict[str, bytes]:
    """Download only known immutable URLs, validate existing files too."""
    cache.mkdir(parents=True, exist_ok=True)
    result = {}
    for name, source in SOURCES.items():
        path = cache / f"{name}.source"
        if path.exists():
            data = path.read_bytes()
        else:
            parsed = urllib.parse.urlsplit(source["url"])
            if parsed.scheme != "https" or parsed.netloc != "raw.githubusercontent.com":
                raise ValueError("Source URL is not an approved immutable HTTPS origin")
            request = urllib.request.Request(  # noqa: S310 -- scheme and host validated above
                source["url"], headers={"User-Agent": "Mizan-Quran-validation/1.0"}
            )
            with urllib.request.urlopen(request, timeout=45) as response:  # noqa: S310
                data = response.read(12 * 1024 * 1024 + 1)
        if len(data) > 12 * 1024 * 1024 or digest(data) != source["sha256"]:
            raise ValueError(f"Pinned source hash mismatch: {name}")
        if not path.exists():
            temporary = path.with_suffix(".pending")
            temporary.write_bytes(data)
            temporary.replace(path)
        result[name] = data
    return result


def read_verses(data: bytes, *, complete: bool = True) -> dict[str, str]:
    """Check canonical Hafs numbering; retain every character in the edition."""
    obj = json.loads(data.decode("utf-8", errors="strict"))
    verses = {}
    for chapter, rows in obj.items():
        if not chapter.isdecimal() or not 1 <= int(chapter) <= 114:
            raise ValueError("Invalid chapter identifier")
        for row in rows:
            surah, ayah = row["chapter"], row["verse"]
            if (
                type(surah) is not int
                or type(ayah) is not int
                or surah != int(chapter)
                or not 1 <= ayah <= CHAPTER_LENGTHS[surah - 1]
            ):
                raise ValueError("Invalid verse identifier")
            identity, text = f"{surah}:{ayah}", row["text"]
            if identity in verses or not isinstance(text, str) or not text.strip():
                raise ValueError("Duplicate or empty verse")
            if "\ufffd" in text or any(ord(char) < 32 and char not in "\n\t" for char in text):
                raise ValueError("Invalid source text encoding")
            verses[identity] = text
    expected = {f"{s}:{v}" for s, n in enumerate(CHAPTER_LENGTHS, 1) for v in range(1, n + 1)}
    if complete and set(verses) != expected:
        raise ValueError("Expected all 114 surahs and 6,236 numbered verses")
    return verses


def comparison_fold(text: str) -> str:
    """Orthography comparison ONLY, retaining unseated hamza and word boundaries.

    NFKD, combining-mark removal, wasla/alif and maqsura/ya folding, and removal
    of elongation/recitation signs do not establish semantic equivalence.
    """
    text = unicodedata.normalize("NFKD", text).replace("ٱ", "ا").replace("ى", "ي")
    return " ".join(
        "".join(
            char
            for char in text
            if not unicodedata.category(char).startswith("M")
            and char not in "\ufeff\u0640\u06e5\u06e6"
            and not "\u06d6" <= char <= "\u06ed"
        ).split()
    )


def compare_editions(primary: dict[str, str], secondary: dict[str, str]) -> dict:
    """Record differences; do not replace primary text with a normalized edition."""
    if set(primary) != set(secondary):
        raise ValueError("Edition verse identifiers disagree")
    basmala = comparison_fold(primary["1:1"])
    exact, folded, differences = 0, 0, []
    for identity, text in primary.items():
        other = secondary[identity]
        exact += text == other
        left, right = comparison_fold(text), comparison_fold(other)
        s, v = map(int, identity.split(":"))
        # Compare editions with/without the separately unnumbered opening.
        if v == 1 and s not in (1, 9):
            left = left.removeprefix(basmala + " ")
            right = right.removeprefix(basmala + " ")
        folded += left == right
        if left != right:
            differences.append({"verse_id": identity, "primary": text, "secondary": other})
    return {
        "verses": len(primary),
        "byte_identical": exact,
        "comparison_fold_agreement": folded,
        "differences": differences,
        "training_text_modified": False,
        "caution": "Orthographic agreement is not independent theological validation.",
    }


def from_buckwalter(text: str) -> str:
    try:
        return "".join(BUCKWALTER[char] for char in text)
    except KeyError as error:
        raise ValueError(f"Unknown QAC Buckwalter symbol: {error.args[0]!r}") from error


def read_morphology(data: bytes, verses: dict[str, str]) -> tuple[list[dict], str]:
    """Keep source locations, features and copyright; labels are never inferred."""
    text = data.decode("utf-8", errors="strict")
    header = text.split("LOCATION\tFORM\tTAG\tFEATURES", 1)[0]
    if "Copyright (C) 2011 Kais Dukes" not in header or "CHANGING IT IS NOT ALLOWED" not in header:
        raise ValueError("QAC original copyright notice missing")
    words: dict[str, list[dict]] = defaultdict(list)
    seen = set()
    for line in text.splitlines():
        if not line.startswith("("):
            continue
        location, form, tag, features = line.split("\t")
        if not re.fullmatch(r"\(\d+:\d+:\d+:\d+\)", location):
            raise ValueError("Malformed QAC location")
        s, v, w, segment = map(int, location[1:-1].split(":"))
        identity, word_id = f"{s}:{v}", f"{s}:{v}:{w}"
        if identity not in verses or w < 1 or segment < 1 or location in seen:
            raise ValueError("Invalid or duplicate QAC location")
        seen.add(location)
        attributes = {
            key: value
            for feature in features.split("|")
            if ":" in feature
            for key, value in [feature.split(":", 1)]
        }
        words[word_id].append(
            {
                "location": location,
                "form_bw": form,
                "form": from_buckwalter(form),
                "tag": tag,
                "features": features,
                "root_bw": attributes.get("ROOT"),
                "lemma_bw": attributes.get("LEM"),
            }
        )
    records = []
    for word_id, segments in words.items():
        numbers = [int(segment["location"][1:-1].split(":")[-1]) for segment in segments]
        if numbers != list(range(1, len(segments) + 1)):
            raise ValueError("QAC segment order is not contiguous")
        records.append(
            {
                "word_id": word_id,
                "verse_id": word_id.rsplit(":", 1)[0],
                "form": "".join(segment["form"] for segment in segments),
                "segments": segments,
            }
        )
    if {row["verse_id"] for row in records} != set(verses):
        raise ValueError("Morphology does not cover the same complete verse set")
    verse_words: dict[str, list[int]] = defaultdict(list)
    for row in records:
        verse_words[row["verse_id"]].append(int(row["word_id"].split(":")[-1]))
    if any(numbers != list(range(1, len(numbers) + 1)) for numbers in verse_words.values()):
        raise ValueError("QAC word order is not contiguous")
    return records, header


def surah_groups(verses: dict[str, str]) -> dict[str, str]:
    """Whole-surah components joined across repeated verse text.

    An identical verse in another surah must not turn held-out exact quotation
    scores into memorization scores. Folded copies also remain in one component.
    """
    parents = {int(identity.split(":")[0]): int(identity.split(":")[0]) for identity in verses}

    def find(surah):
        while parents[surah] != surah:
            parents[surah] = parents[parents[surah]]
            surah = parents[surah]
        return surah

    seen = {}
    for identity, text in verses.items():
        surah = int(identity.split(":")[0])
        key = comparison_fold(text)
        if key in seen:
            a, b = find(surah), find(seen[key])
            parents[max(a, b)] = min(a, b)
        seen[key] = surah
    return {
        identity: f"quran-surah-component-{find(int(identity.split(':')[0]))}"
        for identity in verses
    }


def build_paths(
    verses: dict[str, str], translation: dict[str, str], morphology: list[dict]
) -> dict:
    """Three actual objectives: original bytes, morphology labels, grounded QA."""
    if set(verses) != set(translation):
        raise ValueError("Translation verse identifiers do not match Quran edition")
    groups = surah_groups(verses)
    paths: dict[str, list[dict]] = {"continuation": [], "morphology": [], "grounded_qa": []}
    for identity, text in verses.items():
        common = {"verse_id": identity, "group_id": groups[identity], "lang": "ar"}
        paths["continuation"].append(dict(common, text=text, source="tanzil", task="continuation"))
        context = (
            f"Verse {identity}; edition: Tanzil Uthmani Hafs.\nArabic: {text}\n"
            f"Translation by Marmaduke Pickthall (1930): {translation[identity]}"
        )
        paths["grounded_qa"].append(
            dict(
                common,
                lang="en",
                task="grounded_translation",
                source="pickthall",
                messages=[
                    {
                        "role": "system",
                        "content": "Quote only the supplied source. Translation is an interpretation, not original Quran text. Include its verse and attribution.",
                    },
                    {
                        "role": "user",
                        "content": f"{context}\nQuote the supplied Pickthall translation of verse {identity}.",
                    },
                    {
                        "role": "assistant",
                        "content": f"{translation[identity]} [Quran {identity}; Pickthall, 1930 translation]",
                    },
                ],
            )
        )
    for word in morphology:
        identity = word["verse_id"]
        # QAC v0.4 rendering is explicitly a separate edition. No claim that its
        # spelling, word boundaries or unnumbered-basmala offsets match v1.1.
        labels = {
            "word_id": word["word_id"],
            "segments": word["segments"],
            "source": "QAC 0.4, Kais Dukes (2011)",
        }
        paths["morphology"].append(
            {
                "verse_id": identity,
                "group_id": groups[identity],
                "lang": "ar",
                "task": "morphology",
                "source": "qac",
                "word_id": word["word_id"],
                "messages": [
                    {
                        "role": "system",
                        "content": "Return attributed Quranic Arabic Corpus 0.4 morphology. ROOT/LEM describe annotation, not a translation or a theological interpretation.",
                    },
                    {
                        "role": "user",
                        "content": f"QAC 0.4 word {word['word_id']}: {word['form']}. Return its annotated segments, roots, lemmas and POS in JSON.",
                    },
                    {
                        "role": "assistant",
                        "content": json.dumps(labels, ensure_ascii=False, separators=(",", ":")),
                    },
                ],
            }
        )
    return paths


def build_tafsir_path(verses: dict[str, str], rows: list[dict], source: dict) -> list[dict]:
    """Optional separately licensed commentary; reject unattributed mixed text."""
    required = {"attribution", "license", "license_url", "revision", "sha256"}
    if not required <= source.keys() or any(not source[key] for key in required):
        raise ValueError("Tafsir requires attribution, licence, revision and snapshot hash")
    if source.get("training_permission") is not True:
        raise ValueError("Tafsir training permission must be established separately")
    groups, result, seen = surah_groups(verses), [], set()
    for row in rows:
        identity, text = row["verse_id"], row["text"]
        if (
            identity not in verses
            or identity in seen
            or not isinstance(text, str)
            or not text.strip()
        ):
            raise ValueError("Invalid, duplicate or empty tafsir record")
        seen.add(identity)
        result.append(
            {
                "verse_id": identity,
                "group_id": groups[identity],
                "lang": row.get("lang", "ar"),
                "task": "grounded_tafsir",
                "source": source["attribution"],
                "messages": [
                    {
                        "role": "system",
                        "content": "Commentary is distinct from original Quran. Quote the supplied commentary verbatim with verse and author; do not invent a religious ruling.",
                    },
                    {
                        "role": "user",
                        "content": f"Verse {identity}: {verses[identity]}\nCommentary source: {source['attribution']}\n{text}\nQuote this supplied commentary, with attribution.",
                    },
                    {
                        "role": "assistant",
                        "content": f"{text} [Quran {identity}; commentary: {source['attribution']}]",
                    },
                ],
            }
        )
    return result


def write_jsonl(path: Path, rows: list[dict]) -> dict:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    data = path.read_bytes()
    return {"file": path.name, "records": len(rows), "bytes": len(data), "sha256": digest(data)}


def prepare_quranic(cache: Path, output: Path) -> dict:
    if output.exists():
        raise ValueError("Choose a new output directory; existing corpus must not be overwritten")
    sources = fetch_sources(cache)
    verses = read_verses(sources["tanzil"])
    secondary = read_verses(sources["qpc_hafs"])
    translation = read_verses(sources["pickthall"])
    morphology, notice = read_morphology(sources["qac"], verses)
    comparison = compare_editions(verses, secondary)
    # All differences are retained for review, including detached/seated hamza
    # and joined/separate spelling at these four pinned-edition locations.
    if {row["verse_id"] for row in comparison["differences"]} != {"2:72", "15:7", "27:20", "36:22"}:
        raise ValueError("Unexpected pinned edition comparison; review before training")
    paths = build_paths(verses, translation, morphology)
    output.mkdir(parents=True)
    from ruh_model.data.sequence import split_records

    manifest = {
        "schema_version": 1,
        "status": "verified_corpus_not_a_trained_model",
        "edition": "Tanzil Uthmani Hafs, exact pinned source bytes",
        "coverage": {
            "surahs": 114,
            "verses": len(verses),
            "qac_words": len(morphology),
            "qac_segments": sum(len(row["segments"]) for row in morphology),
        },
        "source_snapshots": {
            name: dict(spec, bytes=len(sources[name])) for name, spec in SOURCES.items()
        },
        "source_metadata": json.loads(sources["source_metadata"]),
        "edition_comparison": comparison,
        "split_policy": "Whole surah, joining repeated folded verses; shared across all objectives. Seed 42; deterministic fraction 0.1.",
        "paths": {},
        "training_text_modified": False,
        "tafsir": "Optional separately licensed corpus; no unverified commentary in these three paths.",
        "promotion": {
            "approved": False,
            "reason": "Corpus integrity and training loss do not establish religious or conversational correctness.",
        },
    }
    for name, rows in paths.items():
        train, validation = split_records(rows, seed=42)
        train_surahs = {int(row["verse_id"].split(":")[0]) for row in train}
        validation_surahs = {int(row["verse_id"].split(":")[0]) for row in validation}
        if train_surahs & validation_surahs:
            raise ValueError("Whole-surah split leakage")
        manifest["paths"][name] = dict(
            write_jsonl(output / f"{name}.jsonl", rows),
            train_records=len(train),
            validation_records=len(validation),
            train_surahs=sorted(train_surahs),
            validation_surahs=sorted(validation_surahs),
        )
    (output / "QAC_ORIGINAL_NOTICE.txt").write_text(notice, encoding="utf-8")
    # Preserve complete exact source copies for provenance and future resumption.
    snapshot_dir = output / "sources"
    snapshot_dir.mkdir()
    for name, data in sources.items():
        (snapshot_dir / f"{name}.source").write_bytes(data)
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest
