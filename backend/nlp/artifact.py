"""
mizan.nlp — artifact contract for the training track.

This file is the HANDOFF: everything the training track must produce so
Phase 2 can load it. The inference-side loader (`wsd.py`) will read
exactly this layout; anything else is a contract violation.
"""

from dataclasses import dataclass, field
from pathlib import Path

#: Env var pointing at a directory holding the trained artifact.
ARTIFACT_ENV_VAR = "MIZAN_NLP_ARTIFACT"

#: Directory (relative to backend/nlp/) where a packaged default artifact
#: may ship with the wheel. Empty until the training track delivers.
PACKAGED_ARTIFACT_DIR = "artifacts/default"

#: Manifest schema version. Bump when the manifest format changes.
MANIFEST_SCHEMA_VERSION = "1"

#: Required files inside an artifact directory.
REQUIRED_FILES = (
    "manifest.json",  # ArtifactManifest below, serialized
    "model.safetensors",  # model weights — safetensors ONLY (no pickle)
    "tokenizer.json",  # HF tokenizers format
    "sense_inventory.json",  # sense_id -> {lemma, gloss, examples}
)

#: Size budget (training-track requirement). The model must run native
#: inference on a single modest CPU box alongside the FastAPI backend —
#: no GPU assumption, cold-start < 10s, single-call p95 < 300ms.
SIZE_BUDGET_BYTES = 250 * 1024 * 1024

#: License requirement for the artifact (weights + inventory). Must stay
#: compatible with the repo's Apache-2.0 license; the dataset itself
#: (Q-CSMP v2, Zenodo 10.5281/zenodo.23024527) keeps its own license and
#: is NOT redistributed — only derived weights + sense inventory ship.
REQUIRED_LICENSE = "Apache-2.0"


@dataclass(frozen=True)
class ArtifactManifest:
    """What manifest.json must contain. The loader validates all of it."""

    schema_version: str = MANIFEST_SCHEMA_VERSION
    name: str = ""  # e.g. "qcsmp2-wsd"
    version: str = ""  # semver, e.g. "0.1.0"
    dataset: str = "Q-CSMP v2"
    dataset_doi: str = "10.5281/zenodo.23024527"
    architecture: str = ""  # e.g. "tiny-arabic-bert + linear WSD head"
    license: str = REQUIRED_LICENSE
    num_senses: int = 0
    eval_accuracy: float = 0.0  # held-out WSD accuracy, honest number
    files: tuple = field(default_factory=tuple)

    def validate(self) -> list[str]:
        """Return a list of problems; empty list means valid."""
        problems = []
        if self.schema_version != MANIFEST_SCHEMA_VERSION:
            problems.append(f"schema_version must be {MANIFEST_SCHEMA_VERSION!r}")
        if self.license != REQUIRED_LICENSE:
            problems.append(f"license must be {REQUIRED_LICENSE!r}")
        if self.num_senses <= 0:
            problems.append("num_senses must be positive")
        if not 0.0 <= self.eval_accuracy <= 1.0:
            problems.append("eval_accuracy must be in [0.0, 1.0]")
        return problems


def find_artifact() -> Path | None:
    """Locate a valid artifact directory. Phase 1: always None.

    Phase 2 order: (1) ARTIFACT_ENV_VAR dir, (2) PACKAGED_ARTIFACT_DIR
    next to this file. Validates REQUIRED_FILES + manifest before
    returning the path.
    """
    return None
