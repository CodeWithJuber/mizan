"""
mizan.nlp — artifact contract for the training track.

This file is the HANDOFF: everything the training track must produce so
the loader (`wsd.py`) can load it. `wsd._load_artifact()` reads exactly
this layout; anything else is a contract violation.

Format history
--------------
* Schema v1 (DESIGN.md §4, Phase 1): assumed a neural model — required
  ``model.safetensors`` + ``tokenizer.json`` (safetensors ONLY, no pickle).
* Schema v1 revised (2026-09-29, JEV choice decision, conf 0.89 — see
  ``backend/nlp/artifacts/DECISIONS.md``): Track 1 actually trained a
  **per-lemma sklearn LogisticRegression** artifact. safetensors cannot
  hold sklearn estimator objects, and joblib is the honest standard for
  them, so the contract now requires ``model.joblib``. ``tokenizer.json``
  is dropped: the feature extractor is a frozen char n-gram function in
  ``wsd.py`` (no learned tokenizer exists for this architecture).

Trust boundary (pickle-family artifact)
---------------------------------------
``model.joblib`` is a pickle-family file. Pickles can execute code on
load, so the loader:

1. loads ONLY from directories it resolves itself: the packaged
   ``artifacts/default/`` next to this file, or the operator-set
   ``MIZAN_NLP_ARTIFACT`` env dir — never from user input, network, or
   any other caller-supplied path;
2. validates ``manifest.json`` (schema v1, sha256 checksums of every
   shipped file) BEFORE unpickling the model.

The artifact ships in-repo (first-party, built by Track 1 on this
project). Loading it is as trusted as importing this package's own code.
"""

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

#: Env var pointing at a directory holding the trained artifact.
ARTIFACT_ENV_VAR = "MIZAN_NLP_ARTIFACT"

#: Directory (relative to backend/nlp/) where the packaged default
#: artifact ships with the wheel. Delivered by Track 1 (2026-09-29).
PACKAGED_ARTIFACT_DIR = "artifacts/default"

#: Manifest schema version. Bump when the manifest format changes.
MANIFEST_SCHEMA_VERSION = "1"

#: Required files inside an artifact directory.
REQUIRED_FILES = (
    "manifest.json",  # ArtifactManifest below, serialized
    "model.joblib",  # per-lemma sklearn classifiers (joblib; see trust boundary)
    "sense_inventory.json",  # sense_id -> {lemma, sense}
)

#: Size budget (training-track requirement). The model must run native
#: inference on a single modest CPU box alongside the FastAPI backend —
#: no GPU assumption, cold-start < 10s, single-call p95 < 300ms.
#: Track 1 shipped 5.9 MB — two orders of magnitude under budget.
SIZE_BUDGET_BYTES = 250 * 1024 * 1024

#: License requirement for the artifact (weights + inventory). Must stay
#: compatible with the repo's Apache-2.0 license; the dataset itself
#: (Q-CSMP v2, Zenodo 10.5281/zenodo.23024527) keeps its own license and
#: is NOT redistributed — only derived weights + sense inventory ship.
REQUIRED_LICENSE = "Apache-2.0"

#: Sense-ID scheme used by this artifact version.
#: "<dataset>:<lemma>:<sense-slug>", e.g. "qcsmp2:يَوْم:judgment-day".
#: Track 1 labels are lemma-keyed sense slugs (no root field carried),
#: so the lemma stands in for the root in the DESIGN.md triple.
#: IDs are immutable across artifact versions.
SENSE_ID_SCHEME = "qcsmp2:<lemma>:<sense-slug>"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True)
class ArtifactManifest:
    """What manifest.json must contain. The loader validates all of it."""

    schema_version: str = MANIFEST_SCHEMA_VERSION
    name: str = ""  # e.g. "mizan-sense-wsd"
    version: str = ""  # semver, e.g. "1.0.0"
    dataset: str = "Q-CSMP v2"
    dataset_doi: str = "10.5281/zenodo.23024527"
    architecture: str = ""  # e.g. "per-lemma sklearn LogisticRegression (lbfgs, C=1.0)"
    model_file: str = "model.joblib"
    model_type: str = ""  # e.g. "sklearn-pipeline-dict"
    sklearn_version: str = ""  # version the artifact was trained with
    trained_at: str = ""  # ISO date, e.g. "2026-09-29"
    variant: str = ""  # which model variant is primary, e.g. "a (surface+context)"
    license: str = REQUIRED_LICENSE
    num_lemmas: int = 0
    num_senses: int = 0
    eval_accuracy: float = 0.0  # held-out WSD accuracy, honest number
    eval_macro_f1: float = 0.0
    eval_n: int = 0  # test-set size
    sense_id_scheme: str = SENSE_ID_SCHEME
    sense_inventory_sha256: str = ""
    model_sha256: str = ""
    files: tuple = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, d: dict) -> "ArtifactManifest":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in known})

    def validate(self, artifact_dir: "Path | None" = None) -> list:
        """Return a list of problems; empty list means valid.

        If ``artifact_dir`` is given, also checks required files exist and
        sha256 checksums match the manifest (checked BEFORE unpickling).
        """
        problems = []
        if self.schema_version != MANIFEST_SCHEMA_VERSION:
            problems.append(f"schema_version must be {MANIFEST_SCHEMA_VERSION!r}")
        if self.license != REQUIRED_LICENSE:
            problems.append(f"license must be {REQUIRED_LICENSE!r}")
        if self.num_lemmas <= 0:
            problems.append("num_lemmas must be positive")
        if self.num_senses <= 0:
            problems.append("num_senses must be positive")
        if not 0.0 <= self.eval_accuracy <= 1.0:
            problems.append("eval_accuracy must be in [0.0, 1.0]")
        if not self.sklearn_version:
            problems.append("sklearn_version must be recorded")
        if not self.model_sha256 or not self.sense_inventory_sha256:
            problems.append("sha256 checksums must be recorded")
        if artifact_dir is not None:
            for f in REQUIRED_FILES:
                if not (artifact_dir / f).is_file():
                    problems.append(f"missing required file: {f}")
            if not problems:
                actual_model = _sha256(artifact_dir / self.model_file)
                if actual_model != self.model_sha256:
                    problems.append(
                        "model.joblib sha256 mismatch — artifact tampered or stale manifest"
                    )
                actual_inv = _sha256(artifact_dir / "sense_inventory.json")
                if actual_inv != self.sense_inventory_sha256:
                    problems.append("sense_inventory.json sha256 mismatch")
                size = (artifact_dir / self.model_file).stat().st_size
                if size > SIZE_BUDGET_BYTES:
                    problems.append(f"model.joblib {size} bytes exceeds size budget")
        return problems


def _manifest_ok(artifact_dir: Path) -> bool:
    try:
        with open(artifact_dir / "manifest.json", encoding="utf-8") as f:
            manifest = ArtifactManifest.from_dict(json.load(f))
    except (OSError, json.JSONDecodeError):
        return False
    return manifest.validate(artifact_dir) == []


def find_artifact() -> Path | None:
    """Locate a valid artifact directory, or None.

    Order: (1) ``MIZAN_NLP_ARTIFACT`` env dir (operator-controlled only —
    see trust boundary above), (2) packaged ``artifacts/default/`` next to
    this file. A directory is only returned if its manifest validates
    (schema + required files + sha256 checksums).
    """
    env_dir = os.environ.get(ARTIFACT_ENV_VAR)
    if env_dir:
        p = Path(env_dir)
        if p.is_dir() and _manifest_ok(p):
            return p
    packaged = Path(__file__).resolve().parent / PACKAGED_ARTIFACT_DIR
    if packaged.is_dir() and _manifest_ok(packaged):
        return packaged
    return None
