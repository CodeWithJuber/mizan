"""
Contract tests for mizan.nlp (Phase 1 — stub).

These tests lock the public interface. The training track and the
Phase-2 wiring must keep them green: if any test here fails after the
artifact lands, the contract broke.
"""

import pytest

import nlp
from nlp import (
    DisambiguationResult,
    ModelNotReadyError,
    SenseCandidate,
    disambiguate,
    is_ready,
)
from nlp.artifact import (
    MANIFEST_SCHEMA_VERSION,
    REQUIRED_FILES,
    REQUIRED_LICENSE,
    SIZE_BUDGET_BYTES,
    ArtifactManifest,
    find_artifact,
)


def test_public_interface_exports():
    for name in nlp.__all__:
        assert hasattr(nlp, name), f"nlp.{name} missing from public interface"


def test_disambiguate_raises_model_not_ready():
    with pytest.raises(ModelNotReadyError):
        disambiguate("إِنَّمَا الْأَعْمَالُ بِالنِّيَّاتِ", "عمل")


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


def test_is_ready_false_without_artifact():
    assert is_ready() is False


def test_sense_candidate_tuple_unpacking():
    # The contract is "list of (sense_id, confidence)".
    sid, confidence = SenseCandidate(sense_id="qcsmp2:ktb:v3", confidence=0.82)
    assert sid == "qcsmp2:ktb:v3"
    assert confidence == pytest.approx(0.82)


def test_sense_candidate_fields():
    c = SenseCandidate(sense_id="qcsmp2:ktb:v3", confidence=0.82, lemma="كتب", gloss="to write")
    assert c.lemma == "كتب"
    assert c.gloss == "to write"


def test_disambiguation_result_best():
    r = DisambiguationResult(
        text="نص",
        lemma="عمل",
        candidates=(
            SenseCandidate(sense_id="qcsmp2:aml:v1", confidence=0.3),
            SenseCandidate(sense_id="qcsmp2:aml:v2", confidence=0.7),
        ),
    )
    assert r.best.sense_id == "qcsmp2:aml:v2"
    assert DisambiguationResult(text="نص", lemma="عمل").best is None


def test_artifact_contract_constants():
    assert REQUIRED_LICENSE == "Apache-2.0"
    assert MANIFEST_SCHEMA_VERSION == "1"
    assert SIZE_BUDGET_BYTES == 250 * 1024 * 1024
    for f in ("manifest.json", "model.safetensors", "tokenizer.json", "sense_inventory.json"):
        assert f in REQUIRED_FILES


def test_artifact_manifest_validation():
    ok = ArtifactManifest(
        name="qcsmp2-wsd",
        version="0.1.0",
        architecture="tiny-arabic-bert + linear WSD head",
        num_senses=120,
        eval_accuracy=0.87,
    )
    assert ok.validate() == []

    bad = ArtifactManifest(
        license="GPL-3.0",
        num_senses=0,
        eval_accuracy=1.5,
        schema_version="99",
    )
    problems = bad.validate()
    assert len(problems) == 4


def test_find_artifact_none_in_phase1():
    assert find_artifact() is None
