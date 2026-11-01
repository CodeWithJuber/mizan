"""Scripture is an input, never a training target.

The Quran (and hadith text) is never a training target of Ruh or any model in
this repository. It may be an input, a retrieval source or an evaluation set.
This module is the one place that rule is written down for the data code; it
has no Torch dependency so the rule can be tested anywhere.

A record states where scripture is in one of three ways:

* ``domain`` in :data:`SCRIPTURE_DOMAINS`: the whole record is scripture. It is
  refused as a training record (:func:`check_trainable`), and a positive mixing
  weight for such a domain is refused (:func:`check_mixing_ratios`).
* ``evaluation_only: True``: an evaluation set, such as the Quran canary (the
  ayahs the model must fail to reproduce). Refused as a training record.
* ``scripture``: a list of exact strings the record quotes (an ayah, a
  translation of one, a hadith). Every occurrence of each string in the
  record's serialized text is a scripture span; :func:`scripture_byte_mask`
  marks its bytes, ``sequence.tokenize_record`` removes them from the target
  mask, and ``RuhCollator`` ignores any label that would predict one of them.

Only declared spans are known. A quotation inside a general corpus row (an
Arabic Wikipedia article quoting an ayah) is not detected by this module.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

SCRIPTURE_DOMAINS = frozenset({"quran", "hadith"})
# Source kinds that hold scripture whatever the domain is called.
SCRIPTURE_KINDS = frozenset({"verified_quran", "quran", "hadith"})

RULE = (
    "the Quran and hadith text are never a training target of Ruh or any model in this "
    "repository; they may be an input, a retrieval source or an evaluation set "
    "(docs/quranic_training_paths.md)"
)


def is_scripture_source(domain: str, spec: object = None) -> bool:
    """A domain is scripture by name, by ``kind``, or by carrying verse columns."""
    if domain in SCRIPTURE_DOMAINS:
        return True
    if isinstance(spec, Mapping):
        return spec.get("kind") in SCRIPTURE_KINDS or "verse_columns" in spec
    return False


def check_mixing_ratios(
    ratios: Mapping[str, float], sources: Mapping[str, object] | None = None
) -> None:
    """Refuse any positive weight on a scripture domain or source."""
    sources = sources or {}
    refused = sorted(
        domain
        for domain, weight in ratios.items()
        if weight and weight > 0 and is_scripture_source(domain, sources.get(domain))
    )
    if refused:
        raise ValueError(
            f"Refusing a positive training weight for {', '.join(refused)}: {RULE}. "
            "Set the weight to 0."
        )


def check_trainable(row: Mapping) -> None:
    """Refuse a record that is wholly scripture or an evaluation-only set."""
    if row.get("evaluation_only"):
        name = " ".join(str(row[key]) for key in ("task", "verse_id") if row.get(key))
        raise ValueError(
            f"Record {name or '(unnamed)'} is evaluation-only and cannot be a training "
            f"target: {RULE}"
        )
    if row.get("domain") in SCRIPTURE_DOMAINS:
        raise ValueError(f"A {row['domain']} record cannot be a training target: {RULE}")


def scripture_byte_mask(text: str, quoted: Iterable[str]) -> list[bool]:
    """True for every UTF-8 byte of ``text`` inside an occurrence of a quoted string.

    Each declared string must occur at least once: a quote that was altered on
    its way into the record would otherwise leave its bytes unprotected.
    """
    if isinstance(quoted, str):
        raise ValueError("Declared scripture is a list of exact strings, not one string")
    data = text.encode("utf-8")
    mask = [False] * len(data)
    for quote in quoted:
        if not isinstance(quote, str) or not quote.strip():
            raise ValueError("Declared scripture spans must be non-empty strings")
        needle = quote.encode("utf-8")
        start = data.find(needle)
        if start < 0:
            raise ValueError(
                "Declared scripture does not occur verbatim in the record; "
                "spans are exact substrings and are never normalized"
            )
        while start >= 0:
            mask[start : start + len(needle)] = [True] * len(needle)
            start = data.find(needle, start + 1)
    return mask
