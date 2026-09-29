"""
Contract + integration tests for mizan.nlp (artifact landed).

These tests lock the public interface. The Phase-2 agent-loop wiring and
the training track must keep them green: if any test here fails, the
contract broke.

Section A — public interface contract (stable across artifact versions).
Section B — artifact contract (manifest schema v1, joblib format).
Section C — real-artifact integration (Track 1, mizan-sense-wsd v1.0.0):
    smoke case + unknown-lemma graceful path + distribution sanity.
"""

import os
from pathlib import Path

import pytest

import nlp
from nlp import (
    DisambiguationResult,
    ModelNotReadyError,
    SenseCandidate,
    disambiguate,
    is_ready,
    wsd,
)
from nlp.artifact import (
    MANIFEST_SCHEMA_VERSION,
    REQUIRED_FILES,
    REQUIRED_LICENSE,
    SENSE_ID_SCHEME,
    SIZE_BUDGET_BYTES,
    ArtifactManifest,
    find_artifact,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("MIZAN_NLP_SKIP_ARTIFACT_TESTS") == "1",
    reason="artifact tests skipped via MIZAN_NLP_SKIP_ARTIFACT_TESTS=1",
)

ARTIFACT_DIR = Path(wsd.__file__).resolve().parent / "artifacts" / "default"


# ── A. Public interface contract ──────────────────────────────────────────


def test_public_interface_exports():
    for name in nlp.__all__:
        assert hasattr(nlp, name), f"nlp.{name} missing from public interface"


def test_model_not_ready_is_not_implemented_error():
    # Agent-loop fallback code may catch either type.
    assert issubclass(ModelNotReadyError, NotImplementedError)


def test_disambiguate_type_validation():
    with pytest.raises(TypeError):
        disambiguate(123, "عمل")
    with pytest.raises(TypeError):
        disambiguate("نص", None)


def test_disambiguate_empty_validation():
    with pytest.raises(ValueError):
        disambiguate("", "عمل")
    with pytest.raises(ValueError):
        disambiguate("نص", "   ")


def test_sense_candidate_tuple_unpacking():
    # The contract is "list of (sense_id, confidence)".
    sid, confidence = SenseCandidate(sense_id="qcsmp2:يَوْم:judgment-day", confidence=0.82)
    assert sid == "qcsmp2:يَوْم:judgment-day"
    assert confidence == pytest.approx(0.82)


def test_sense_candidate_fields():
    c = SenseCandidate(
        sense_id="qcsmp2:يَوْم:judgment-day",
        confidence=0.82,
        lemma="يَوْم",
    )
    assert c.lemma == "يَوْم"


def test_disambiguation_result_best():
    r = DisambiguationResult(
        text="نص",
        lemma="عمل",
        candidates=(
            SenseCandidate(sense_id="qcsmp2:عمل:v1", confidence=0.3),
            SenseCandidate(sense_id="qcsmp2:عمل:v2", confidence=0.7),
        ),
    )
    assert r.best.sense_id == "qcsmp2:عمل:v2"
    assert DisambiguationResult(text="نص", lemma="عمل").best is None


# ── B. Artifact contract (schema v1, joblib) ─────────────────────────────


def test_artifact_contract_constants():
    assert REQUIRED_LICENSE == "Apache-2.0"
    assert MANIFEST_SCHEMA_VERSION == "1"
    assert SIZE_BUDGET_BYTES == 250 * 1024 * 1024
    # JEV decision 2026-09-29 (conf 0.89): Track 1 shipped per-lemma
    # sklearn classifiers — joblib is the honest standard; safetensors
    # cannot hold sklearn estimator objects. See artifacts/DECISIONS.md.
    assert REQUIRED_FILES == ("manifest.json", "model.joblib", "sense_inventory.json")
    assert SENSE_ID_SCHEME == "qcsmp2:<lemma>:<sense-slug>"


def test_artifact_manifest_validation():
    ok = ArtifactManifest(
        name="mizan-sense-wsd",
        version="1.0.0",
        architecture="per-lemma sklearn LogisticRegression (lbfgs, C=1.0)",
        model_type="sklearn-pipeline-dict",
        sklearn_version="1.9.1",
        trained_at="2026-09-29",
        num_lemmas=48,
        num_senses=115,
        eval_accuracy=0.7592,
        model_sha256="a" * 64,
        sense_inventory_sha256="b" * 64,
    )
    assert ok.validate() == []

    bad = ArtifactManifest(
        license="GPL-3.0",
        num_lemmas=0,
        num_senses=0,
        eval_accuracy=1.5,
        schema_version="99",
    )
    problems = bad.validate()
    assert len(problems) == 7


def test_packaged_manifest_validates_with_checksums():
    """The shipped manifest must validate against the shipped files,
    including sha256 checksums (checked before any unpickling)."""
    assert ARTIFACT_DIR.is_dir(), "packaged artifact dir missing"
    found = find_artifact()
    assert found is not None
    assert found == ARTIFACT_DIR
    import json

    with open(ARTIFACT_DIR / "manifest.json", encoding="utf-8") as f:
        manifest = ArtifactManifest.from_dict(json.load(f))
    assert manifest.validate(ARTIFACT_DIR) == []
    assert manifest.eval_accuracy == pytest.approx(0.8038)
    assert manifest.num_lemmas == 48
    assert manifest.num_senses == 106


def test_is_ready_true_with_packaged_artifact():
    assert is_ready() is True


def test_model_not_ready_when_no_artifact(monkeypatch, tmp_path):
    """With an empty env dir and no packaged artifact, fail closed.

    (Simulated: point the packaged dir away via monkeypatched module
    state — the real packaged dir is always valid in-repo.)
    """
    monkeypatch.setenv("MIZAN_NLP_ARTIFACT", str(tmp_path))
    wsd.reset_for_tests()
    from nlp import artifact as artifact_mod

    monkeypatch.setattr(artifact_mod, "PACKAGED_ARTIFACT_DIR", "artifacts/nonexistent")
    try:
        assert wsd.is_ready() is False
        with pytest.raises(ModelNotReadyError):
            wsd.disambiguate("مَٰلِكِ يَوْمِ ٱلدِّينِ", "يَوْم")
    finally:
        monkeypatch.undo()
        wsd.reset_for_tests()


# ── C. Real-artifact integration (Track 1) ────────────────────────────────


def test_smoke_yawm_judgment_day():
    """Track-1 smoke case: مَٰلِكِ يَوْمِ ٱلدِّينِ → judgment-day, conf > 0.5."""
    cands = disambiguate("مَٰلِكِ يَوْمِ ٱلدِّينِ", "يَوْم")
    assert cands, "expected candidates for a trained lemma"
    best = cands[0]
    assert best.sense_id == "qcsmp2:يَوْم:judgment-day"
    assert best.confidence > 0.5
    # sorted by confidence, descending
    confs = [c.confidence for c in cands]
    assert confs == sorted(confs, reverse=True)
    # tuple unpacking per the public contract
    sid, conf = best
    assert sid == best.sense_id and conf == best.confidence


def test_smoke_yawm_undiacritized_lemma():
    """Undiacritized lemmas must also resolve (stripped-key index)."""
    cands = disambiguate("مَٰلِكِ يَوْمِ ٱلدِّينِ", "يوم")
    assert cands
    assert cands[0].sense_id == "qcsmp2:يَوْم:judgment-day"


def test_unknown_lemma_graceful_empty_list():
    """A lemma the model never saw → empty list, no exception, no guess."""
    assert disambiguate("هذا نص عربي للاختبار", "زقزقة") == []


def test_confidence_distribution_sums_to_one():
    cands = disambiguate("مَٰلِكِ يَوْمِ ٱلدِّينِ", "يَوْم")
    total = sum(c.confidence for c in cands)
    assert total == pytest.approx(1.0, abs=1e-6)
    assert all(0.0 <= c.confidence <= 1.0 for c in cands)
    assert len(cands) == 2  # judgment-day + ordinary-day


def test_sense_ids_follow_scheme():
    cands = disambiguate("مَٰلِكِ يَوْمِ ٱلدِّينِ", "يَوْم")
    for c in cands:
        assert c.sense_id.startswith("qcsmp2:يَوْم:")


def test_artifact_version_reported():
    assert wsd.artifact_version() == "1.1.0"
