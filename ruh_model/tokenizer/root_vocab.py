"""
Root Vocabulary (مفردات الجذور)
================================

Maps Arabic roots and morphological patterns to integer IDs.
This replaces BPE token vocabularies with linguistically-grounded
root+pattern pairs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


# Special token IDs
PAD_ID = 0
BOS_ID = 1
EOS_ID = 2
UNK_ID = 3
FIRST_ROOT_ID = 4

# Pattern IDs -- morphological categories
PATTERN_NONE = 0
PATTERN_VERB_PAST = 1
PATTERN_VERB_PRESENT = 2
PATTERN_VERB_COMMAND = 3
PATTERN_ACTIVE_PARTICIPLE = 4
PATTERN_PASSIVE_PARTICIPLE = 5
PATTERN_VERBAL_NOUN = 6
PATTERN_NOUN = 7
PATTERN_ADJECTIVE = 8
PATTERN_PLACE_NOUN = 9
PATTERN_INSTRUMENT_NOUN = 10
PATTERN_DIMINUTIVE = 11
PATTERN_ABSTRACT_NOUN = 12
PATTERN_AGENT = 13
PATTERN_PATIENT = 14
PATTERN_STOPWORD = 15
PATTERN_UNKNOWN = 16

PATTERN_NAMES: dict[int, str] = {
    PATTERN_NONE: "NONE",
    PATTERN_VERB_PAST: "VERB_PAST",
    PATTERN_VERB_PRESENT: "VERB_PRESENT",
    PATTERN_VERB_COMMAND: "VERB_COMMAND",
    PATTERN_ACTIVE_PARTICIPLE: "ACTIVE_PARTICIPLE",
    PATTERN_PASSIVE_PARTICIPLE: "PASSIVE_PARTICIPLE",
    PATTERN_VERBAL_NOUN: "VERBAL_NOUN",
    PATTERN_NOUN: "NOUN",
    PATTERN_ADJECTIVE: "ADJECTIVE",
    PATTERN_PLACE_NOUN: "PLACE_NOUN",
    PATTERN_INSTRUMENT_NOUN: "INSTRUMENT_NOUN",
    PATTERN_DIMINUTIVE: "DIMINUTIVE",
    PATTERN_ABSTRACT_NOUN: "ABSTRACT_NOUN",
    PATTERN_AGENT: "AGENT",
    PATTERN_PATIENT: "PATIENT",
    PATTERN_STOPWORD: "STOPWORD",
    PATTERN_UNKNOWN: "UNKNOWN",
}

SPECIAL_TOKENS: dict[int, str] = {
    PAD_ID: "<PAD>",
    BOS_ID: "<BOS>",
    EOS_ID: "<EOS>",
    UNK_ID: "<UNK>",
}


class RootVocab:
    """Vocabulary mapping Arabic roots and patterns to integer IDs."""

    def __init__(self) -> None:
        self.root_to_id: dict[str, int] = {}
        self.id_to_root: dict[int, str] = {}
        self.pattern_to_id: dict[str, int] = {}
        self.id_to_pattern: dict[int, str] = {}
        self._initialize_special_tokens()
        self._initialize_patterns()

    def _initialize_special_tokens(self) -> None:
        """Register PAD, BOS, EOS, UNK as root entries."""
        for token_id, token_name in SPECIAL_TOKENS.items():
            self.root_to_id[token_name] = token_id
            self.id_to_root[token_id] = token_name

    def _initialize_patterns(self) -> None:
        """Register all morphological pattern IDs."""
        for pattern_id, pattern_name in PATTERN_NAMES.items():
            self.pattern_to_id[pattern_name] = pattern_id
            self.id_to_pattern[pattern_id] = pattern_name

    def build_from_roots(
        self,
        arabic_roots: dict[str, dict[str, Any]],
        concept_map: dict[str, str],
    ) -> None:
        """Build vocabulary from ARABIC_ROOTS and CONCEPT_MAP data.

        Assigns integer IDs starting at FIRST_ROOT_ID to each unique
        Arabic root found in both sources.
        """
        all_roots = set(arabic_roots.keys())
        all_roots.update(concept_map.values())

        next_id = FIRST_ROOT_ID
        for root in sorted(all_roots):
            if root not in self.root_to_id:
                self.root_to_id[root] = next_id
                self.id_to_root[next_id] = root
                next_id += 1

    def get_root_id(self, root: str) -> int:
        """Return integer ID for a root string, or UNK_ID if unknown."""
        return self.root_to_id.get(root, UNK_ID)

    def get_pattern_id(self, pattern: str) -> int:
        """Return integer ID for a pattern name, or PATTERN_UNKNOWN if unknown."""
        return self.pattern_to_id.get(pattern, PATTERN_UNKNOWN)

    @property
    def n_roots(self) -> int:
        """Total number of root entries including special tokens."""
        return len(self.root_to_id)

    @property
    def n_patterns(self) -> int:
        """Total number of morphological patterns."""
        return len(self.pattern_to_id)

    def save(self, path: str) -> None:
        """Serialize vocabulary to JSON file."""
        data = {
            "root_to_id": self.root_to_id,
            "pattern_to_id": self.pattern_to_id,
        }
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2))

    def load(self, path: str) -> None:
        """Deserialize vocabulary from JSON file."""
        data = json.loads(Path(path).read_text())
        self.root_to_id = data["root_to_id"]
        self.id_to_root = {int(v): k for k, v in self.root_to_id.items()}
        self.pattern_to_id = data["pattern_to_id"]
        self.id_to_pattern = {int(v): k for k, v in self.pattern_to_id.items()}


def _load_roots_module() -> Any:
    """Import backend.qca.roots directly, bypassing __init__.py chains."""
    import importlib.util
    from pathlib import Path as _Path

    project_root = _Path(__file__).resolve().parents[2]
    candidate_paths = [
        project_root / "backend" / "qca" / "roots.py",
        project_root / "qca" / "roots.py",
    ]

    roots_path = next((path for path in candidate_paths if path.exists()), None)
    if roots_path is None:
        paths_text = ", ".join(str(path) for path in candidate_paths)
        raise ImportError(f"Cannot locate roots module. Tried: {paths_text}")

    spec = importlib.util.spec_from_file_location("backend.qca.roots", roots_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load roots module from {roots_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_default_vocab() -> RootVocab:
    """Build a RootVocab from the project's ARABIC_ROOTS and CONCEPT_MAP."""
    roots_mod = _load_roots_module()

    vocab = RootVocab()
    vocab.build_from_roots(roots_mod.ARABIC_ROOTS, roots_mod.CONCEPT_MAP)
    return vocab
