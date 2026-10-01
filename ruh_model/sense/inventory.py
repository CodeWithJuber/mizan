"""Versioned sense inventory for Ruh disambiguation (torch-free, stdlib only).

Data model (one entry per sense)::

    {
        "sense_id":  "qcsmp2:آيَة:verse",   # <dataset>:<lemma>:<sense-slug>, immutable
        "lemma":     "آيَة",
        "root":      None,                  # null when not established — never guessed
        "gloss_ar":  None,                  # null until scholar-reviewed; see GLOSS_AR_STATUS
        "gloss_en":  "verse",               # from the Q-CSMP v2 keyword-rule label
        "version":   "1.0.0",               # inventory version, present on every entry
        "religious": True,                  # Quranic senses abstain at the higher bar
        "source":    "qcsmp2",
        "gloss_ar_status": "pending_scholar_review",
    }

Quran-lens honesty (lā taqfu — no claim without knowledge): the Q-CSMP v2
labels are keyword-rules over *English* glosses. There is no scholar-reviewed
Arabic gloss in the repo, so ``gloss_ar`` stays ``None`` rather than being
invented. ``root`` is likewise ``None`` until a reviewed root assignment
exists.

Sense merges (``nlp/SENSE_MERGES*.json``) map retired sense IDs to their
surviving target, e.g. ``"qcsmp2:أَجْر:payment" -> "qcsmp2:أَجْر:reward"``.
:func:`normalize_sense_id` resolves these transitively; :func:`build_inventory`
applies them while seeding so the builder is deterministic and rerunnable.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

#: Current inventory version. Bumped whenever the seeded sense set changes.
#: Every disambiguation output carries this string.
INVENTORY_VERSION = "1.0.0"

#: Dataset tag embedded in sense IDs produced by the seed builder.
INVENTORY_SOURCE = "qcsmp2"

#: Why gloss_ar is null on seeded entries — surfaced, never silently omitted.
GLOSS_AR_STATUS = "pending_scholar_review"

_DIACRITICS = re.compile(r"[\u064b-\u0652\u0670\u06d6-\u06ed]")


def strip_diacritics(s: str) -> str:
    """Remove Arabic diacritics (NFC-normalized first)."""
    return _DIACRITICS.sub("", unicodedata.normalize("NFC", s or ""))


def humanize_slug(slug: str) -> str:
    """Turn a sense slug (``judgment-day``) into a readable gloss (``judgment day``)."""
    return slug.replace("-", " ").replace("_", " ").strip()


@dataclass(frozen=True)
class SenseEntry:
    """One sense in the versioned inventory."""

    sense_id: str
    lemma: str
    gloss_en: str
    version: str = INVENTORY_VERSION
    root: str | None = None
    gloss_ar: str | None = None
    religious: bool = False
    source: str = INVENTORY_SOURCE
    gloss_ar_status: str = GLOSS_AR_STATUS

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_sense_id(sense_id: str, merges: dict[str, str]) -> str:
    """Resolve a sense ID through the merge map, transitively.

    Retired IDs redirect to their surviving target; unknown IDs pass through
    unchanged. Raises ``ValueError`` on a merge cycle (fail-closed: a cyclic
    merge map is a data bug, never silently accepted).
    """
    seen = {sense_id}
    current = sense_id
    while current in merges:
        current = merges[current]
        if current in seen:
            raise ValueError(f"cycle in sense merge map at {current!r}")
        seen.add(current)
    return current


def build_inventory(
    seed_records: list[dict[str, Any]],
    merges: dict[str, str],
    version: str = INVENTORY_VERSION,
) -> SenseInventory:
    """Build a deterministic inventory from seed records + merge map.

    Args:
        seed_records: ``[{"lemma": ..., "sense": <slug>, ...}]`` — extra keys
            (``root``, ``gloss_ar``, ``religious``) are honored when present.
        merges: retired sense_id -> surviving sense_id (from SENSE_MERGES*.json).
        version: stamped on every entry.

    Determinism contract: same inputs -> byte-identical JSONL. Entries are
    sorted by ``sense_id``; retired IDs that still resolve to a missing target
    raise ``ValueError`` (fail-closed) instead of silently dropping senses.
    """
    entries: dict[str, SenseEntry] = {}
    for rec in seed_records:
        lemma = rec["lemma"]
        slug = rec["sense"]
        raw_id = f"{INVENTORY_SOURCE}:{lemma}:{slug}"
        sense_id = normalize_sense_id(raw_id, merges)
        if sense_id in entries:
            continue  # already seeded (e.g. duplicate seed rows)
        entries[sense_id] = SenseEntry(
            sense_id=sense_id,
            lemma=lemma,
            gloss_en=rec.get("gloss_en") or humanize_slug(slug),
            version=version,
            root=rec.get("root"),
            gloss_ar=rec.get("gloss_ar"),
            religious=bool(rec.get("religious", False)),
            source=rec.get("source", INVENTORY_SOURCE),
            gloss_ar_status=rec.get("gloss_ar_status", GLOSS_AR_STATUS),
        )

    # Fail closed: every merge target must exist in the final inventory.
    targets = set(merges.values())
    missing = sorted(t for t in targets if t not in entries)
    if missing:
        raise ValueError(
            f"{len(missing)} merge target(s) absent from the seeded inventory: "
            + ", ".join(missing[:5])
        )

    ordered = [entries[k] for k in sorted(entries)]
    return SenseInventory(entries=ordered, version=version)


class SenseInventory:
    """Immutable, versioned collection of :class:`SenseEntry`."""

    def __init__(self, entries: list[SenseEntry], version: str = INVENTORY_VERSION) -> None:
        self._entries = tuple(entries)
        self._version = version
        self._by_id = {e.sense_id: e for e in entries}
        self._by_lemma: dict[str, list[SenseEntry]] = {}
        for e in entries:
            self._by_lemma.setdefault(strip_diacritics(e.lemma), []).append(e)

    @property
    def version(self) -> str:
        return self._version

    @property
    def entries(self) -> tuple[SenseEntry, ...]:
        return self._entries

    def __len__(self) -> int:
        return len(self._entries)

    def get(self, sense_id: str) -> SenseEntry | None:
        """Fetch one entry by exact sense_id (None when absent)."""
        return self._by_id.get(sense_id)

    def senses_for(self, lemma: str) -> list[SenseEntry]:
        """All senses for a lemma (diacritic-insensitive match)."""
        return list(self._by_lemma.get(strip_diacritics(lemma), []))

    def lemmas(self) -> list[str]:
        """Sorted unique lemmas in the inventory."""
        return sorted({e.lemma for e in self._entries})


def dump_inventory_jsonl(inventory: SenseInventory, path: str | Path) -> Path:
    """Write the inventory as JSONL — one entry per line, sorted by sense_id.

    Byte-deterministic: fixed key order (dataclass field order), UTF-8,
    ``ensure_ascii=False``, LF endings. Rerunning produces identical bytes.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps(e.to_dict(), ensure_ascii=False)
        for e in sorted(inventory.entries, key=lambda x: x.sense_id)
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def load_inventory_jsonl(path: str | Path) -> SenseInventory:
    """Load a JSONL inventory written by :func:`dump_inventory_jsonl`.

    Validates the minimal schema (``sense_id``, ``lemma``, ``gloss_en``,
    ``version``); all entries must share one version string.
    """
    path = Path(path)
    entries: list[SenseEntry] = []
    versions: set[str] = set()
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{lineno}: invalid JSON: {exc}") from exc
        for key in ("sense_id", "lemma", "gloss_en", "version"):
            if key not in raw:
                raise ValueError(f"{path}:{lineno}: missing required key {key!r}")
        versions.add(raw["version"])
        entries.append(
            SenseEntry(
                sense_id=raw["sense_id"],
                lemma=raw["lemma"],
                gloss_en=raw["gloss_en"],
                version=raw["version"],
                root=raw.get("root"),
                gloss_ar=raw.get("gloss_ar"),
                religious=bool(raw.get("religious", False)),
                source=raw.get("source", INVENTORY_SOURCE),
                gloss_ar_status=raw.get("gloss_ar_status", GLOSS_AR_STATUS),
            )
        )
    if len(versions) > 1:
        raise ValueError(f"{path}: mixed inventory versions in one file: {sorted(versions)}")
    version = next(iter(versions), INVENTORY_VERSION)
    entries.sort(key=lambda e: e.sense_id)
    return SenseInventory(entries=entries, version=version)
