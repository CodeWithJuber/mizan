"""Build the Lughah language corpus (backend/tadbir/data/lughah/*.tsv).

Sources (licences in backend/tadbir/data/lughah/LICENSES.md):
- Tatoeba per-language exports (CC BY 2.0 FR): eng, ara, urd, hin
  https://downloads.tatoeba.org/exports/per_language/<lang>/<lang>_sentences.tsv.bz2
- Abhishekcr448/Hinglish-Everyday-Conversations-1M (MIT), rows read through the
  Hugging Face datasets-server, saved as a JSON list of lines
- The Quran, Uthmani text (Tanzil, via api.alquran.cloud /v1/quran/quran-uthmani),
  every seventh ayah verbatim, for the "quote" class (quoted, vowelled Quranic Arabic)
- authored.tsv: request-style lines written for MIZAN (label <TAB> text)

Sampling is seeded, so the same sources give the same corpus.

    python scripts/build_lughah_corpus.py <download-dir>
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "backend" / "tadbir" / "data" / "lughah"
PER_CLASS = 900
TATOEBA = {"en": "eng", "ar": "ara", "ur": "urd", "hi": "hin"}


def _tatoeba(path: Path) -> list[tuple[str, str]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and 12 <= len(parts[2]) <= 140:
            rows.append((f"tatoeba:{parts[0]}", parts[2].strip()))
    return sorted(rows)


def _sample(rows: list[tuple[str, str]], count: int, seed: str) -> list[tuple[str, str]]:
    rows = sorted(set(rows))
    return sorted(random.Random(seed).sample(rows, min(count, len(rows))))


def _names() -> list[tuple[str, str]]:
    """Names written in Latin letters, from MIZAN's own indexes: surahs, named ayahs,
    hadith collections and prayers. They appear the same in English and in Roman
    Hindi/Urdu, so they say nothing about the asker's language."""
    sys.path.insert(0, str(OUT.parents[2]))
    from tadbir import fahm, hadith, quran

    names: list[str] = []
    for latin, _arabic, _count in quran.SURAHS:
        spaced = latin.replace("-", " ")
        names += [latin, f"Surah {latin}", f"surah {spaced}", f"Surah {spaced} ayah"]
    names += [alias for alias in quran.ALIASES if alias.isascii()]
    names += [key for key in quran.NAMED_AYAHS if key.isascii()]
    for collection in hadith.COLLECTIONS:
        names += [collection.name, collection.key, f"{collection.name} hadith"]
    names += list(fahm._PRAYER_NAMES)
    unique = sorted(dict.fromkeys(name.strip() for name in names if name.strip()))
    return [(f"index:{number}", name) for number, name in enumerate(unique)]


def main(downloads: Path) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    authored: dict[str, list[tuple[str, str]]] = {}
    for number, line in enumerate((OUT / "authored.tsv").read_text(encoding="utf-8").splitlines()):
        if line.strip() and not line.startswith("#"):
            label, text = line.split("\t", 1)
            authored.setdefault(label, []).append((f"mizan:{number}", text.strip()))
    classes: dict[str, list[tuple[str, str]]] = {}
    for label, code in TATOEBA.items():
        rows = _tatoeba(downloads / f"{code}_sentences.tsv")
        classes[label] = _sample(rows, PER_CLASS, f"lughah-{label}")
    lines = json.loads((downloads / "hinglish_mit.json").read_text(encoding="utf-8"))
    hinglish = [(f"hinglish-1m:{i}", text.strip()) for i, text in enumerate(lines) if len(text) >= 10]
    classes["hi-latn"] = _sample(hinglish, PER_CLASS, "lughah-hi-latn")
    surahs = json.loads((downloads / "quran_uthmani.json").read_text(encoding="utf-8"))
    ayahs = [
        (f"quran:{surah['number']}:{ayah['numberInSurah']}", ayah["text"])
        for surah in surahs["data"]["surahs"]
        for ayah in surah["ayahs"]
    ]
    quoted = []
    for key, text in ayahs[::7]:
        words = text.split()
        while len(" ".join(words)) > 160 and len(words) > 4:
            words = words[:-1]
        quoted.append((key, " ".join(words)))
    classes["quote"] = quoted
    classes["name"] = _names()
    for label, rows in classes.items():
        rows = rows + authored.get(label, [])
        body = "".join(f"{source}\t{text}\n" for source, text in rows if "\t" not in text)
        (OUT / f"{label}.tsv").write_text(body, encoding="utf-8")
        print(label, len(rows))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
