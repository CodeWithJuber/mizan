"""Seed training data generator for the Ruh model (nutfah stage).

Generates simple, linguistically grounded JSONL samples from the project's
ARABIC_ROOTS and CONCEPT_MAP so that ``python -m ruh_model.train --stage
nutfah --generate-data`` works out of the box.

Each output line is a JSON object: ``{"text": "<arabic/english phrase>"}``.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from ruh_model.tokenizer.root_vocab import _load_roots_module

# Simple Arabic sentence templates using a derivative word. The templates
# are intentionally basic: the nutfah stage only needs root exposure, not
# grammar.
_ARABIC_TEMPLATES = [
    "{w} نور",
    "{w} حق",
    "{w} علم",
    "هذا {w}",
    "{w} كبير",
    "طلب {w}",
    "{w} جميل",
    "في {w} خير",
]

_ENGLISH_TEMPLATES = [
    "{w} is light",
    "seek {w}",
    "this is {w}",
    "{w} is truth",
    "the {w} guides",
]


class SeedDataGenerator:
    """Generate seed JSONL training data from ARABIC_ROOTS / CONCEPT_MAP."""

    def __init__(self, seed: int = 42) -> None:
        self._rng = random.Random(seed)

    def generate(self, path: str, samples_per_root: int = 10) -> int:
        """Generate root-based seed samples.

        Args:
            path: Output JSONL path.
            samples_per_root: How many phrases to emit per root.

        Returns:
            Number of samples written.
        """
        roots_mod = _load_roots_module()
        arabic_roots: dict[str, dict[str, Any]] = roots_mod.ARABIC_ROOTS

        samples: list[dict[str, str]] = []
        for root, info in sorted(arabic_roots.items()):
            derivatives = list((info.get("derivatives") or {}).keys())
            words = [root, *derivatives]
            for _ in range(samples_per_root):
                word = self._rng.choice(words)
                if _contains_arabic(word):
                    template = self._rng.choice(_ARABIC_TEMPLATES)
                else:
                    template = self._rng.choice(_ENGLISH_TEMPLATES)
                samples.append({"text": template.format(w=word)})

        self._rng.shuffle(samples)
        _write_jsonl(path, samples)
        return len(samples)

    def generate_concept_map_data(self, path: str) -> int:
        """Generate concept-mapping seed samples from CONCEPT_MAP.

        Each sample pairs an English concept word with its Arabic root so the
        model learns the cross-lingual bridge.

        Returns:
            Number of samples written.
        """
        roots_mod = _load_roots_module()
        concept_map: dict[str, str] = roots_mod.CONCEPT_MAP

        samples = [
            {"text": f"{english} {arabic_root}"}
            for english, arabic_root in sorted(concept_map.items())
        ]
        self._rng.shuffle(samples)
        _write_jsonl(path, samples)
        return len(samples)


def _contains_arabic(text: str) -> bool:
    return any("\u0600" <= ch <= "\u06FF" for ch in text)


def _write_jsonl(path: str, samples: list[dict[str, str]]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for sample in samples:
            fh.write(json.dumps(sample, ensure_ascii=False) + "\n")
