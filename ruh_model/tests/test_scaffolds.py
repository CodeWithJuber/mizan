"""Tests for the later-gated scaffolds (studies #8, #9, #13, #10).

Torch-free by construction: scaffold modules are loaded directly by file
path (importlib), bypassing ``ruh_model/__init__.py`` which unconditionally
imports torch. This is the sanctioned pattern for torch-less envs — it does
not hide the dependency, it routes around the package __init__.

NOTE: running this file with plain ``pytest ruh_model/tests/test_scaffolds.py``
also loads ``ruh_model/tests/conftest.py``, which needs torch. In torch-less
envs run with ``pytest --noconftest`` (the default ``pytest`` run from the
repo root only collects ``tests/`` anyway, per pyproject testpaths).
"""

import importlib.util
import math
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]  # ruh_model/tests/ -> repo root


def load_by_path(name: str, relpath: str):
    """Load a module from its file path, bypassing package __init__.

    Registered in sys.modules under the given name so dataclasses can
    resolve annotations (required by spec_from_file_location modules).
    """
    path = REPO / relpath
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def tajwid():
    return load_by_path("tajwid_scaffold", "ruh_model/tajwid/scaffold.py")


@pytest.fixture(scope="module")
def onnx():
    return load_by_path("export_onnx", "ruh_model/export/onnx.py")


@pytest.fixture(scope="module")
def bench():
    return load_by_path("qcsmp_adjudicated", "ruh_model/benchmarks/qcsmp_adjudicated.py")


@pytest.fixture(scope="module")
def embeddings():
    return load_by_path("ruh_embeddings", "backend/api/ruh_embeddings.py")


# ---------------------------------------------------------------------------
# #8 — Tajwid Buddy scaffold: interface only, unproven
# ---------------------------------------------------------------------------


def test_tajwid_rescore_raises_not_implemented(tajwid):
    hyp = tajwid.ASRHypothesis(transcript="test", confidence=0.9)
    lat = tajwid.RootLattice(allowed_roots=["ك-ت-ب"], verse_ref="2:255")
    with pytest.raises(NotImplementedError, match="UNPROVEN"):
        tajwid.rescore_hypothesis(hyp, lat)


def test_tajwid_meaning_drift_raises_not_implemented(tajwid):
    with pytest.raises(NotImplementedError):
        tajwid.meaning_drift("ك-ت-ب", "ق-ر-أ")


def test_tajwid_status_is_unproven(tajwid):
    assert tajwid.SCAFFOLD_STATUS["status"] == "unproven-scaffold"
    assert tajwid.SCAFFOLD_STATUS["trained"] is False
    assert tajwid.SCAFFOLD_STATUS["accuracy_claims"] is None


def test_tajwid_dataclasses_construct(tajwid):
    tok = tajwid.ASRToken(surface="ٱقْرَأْ", start_ms=0, end_ms=500, confidence=0.8)
    hyp = tajwid.ASRHypothesis(transcript="ٱقْرَأْ", tokens=[tok], confidence=0.8)
    assert hyp.tokens[0].surface == "ٱقْرَأْ"


# ---------------------------------------------------------------------------
# #9 — ONNX/int8 export scaffold: clear skip without torch/onnx
# ---------------------------------------------------------------------------


def test_export_onnx_skips_without_torch(onnx, monkeypatch):
    original = onnx._require

    def missing(name, message):
        if name == "torch":
            raise onnx.ExportDependencyMissing("torch not installed")
        return original(name, message)

    monkeypatch.setattr(onnx, "_require", missing)
    result = onnx.export_onnx(model=None, path="/tmp/x.onnx")
    assert result.status == "skipped"
    assert "torch" in result.message.lower()
    assert "not installed" in result.message.lower()


def test_quantize_int8_skips_without_onnxruntime(onnx):
    result = onnx.quantize_int8("/tmp/x.onnx")
    assert result.status == "skipped"
    assert "onnxruntime" in result.message.lower()


def test_parity_report_is_stub_with_calibration_gate(onnx):
    report = onnx.parity_report("/tmp/fp32.onnx", "/tmp/int8.onnx")
    assert report["status"] == "not-implemented"
    assert "calibration" in report["gate"].lower()
    assert "ECE_delta" in report["required_metrics"]
    assert "MANDATORY" in report["gate"]


def test_export_dependency_missing_is_runtime_error(onnx):
    assert issubclass(onnx.ExportDependencyMissing, RuntimeError)


# ---------------------------------------------------------------------------
# #10 — adjudicated benchmark harness: kappa math + graceful degradation
# ---------------------------------------------------------------------------


def test_cohens_kappa_perfect_agreement(bench):
    assert bench.cohens_kappa(["a", "b", "a"], ["a", "b", "a"]) == pytest.approx(1.0)


def test_cohens_kappa_known_value(bench):
    # Hand-computed: po=0.75, pe=0.5 → κ=0.5
    assert bench.cohens_kappa(["a", "a", "b", "b"], ["a", "b", "b", "b"]) == pytest.approx(0.5)


def test_cohens_kappa_rejects_bad_input(bench):
    with pytest.raises(ValueError):
        bench.cohens_kappa([], [])
    with pytest.raises(ValueError):
        bench.cohens_kappa(["a"], ["a", "b"])


def test_run_protocol_graceful_without_phase0(bench):
    # ruh_model/eval/adjudication.py (phase-0 track) is not merged yet.
    out = bench.run_adjudication_protocol([{"id": "x"}])
    assert out["status"] == "unavailable"
    assert "not merged yet" in out["message"]


def test_summarize_checks_kappa_gate(bench):
    R = bench.AdjudicationResult
    good = [
        R(item_id=str(i), annotator_a="s1", annotator_b="s1", adjudicated_label="s1")
        for i in range(10)
    ]
    s = bench.summarize_adjudication(good)
    assert s["meets_prerequisite"] is True
    assert s["kappa_target"] == 0.61

    mixed = [
        R(item_id="1", annotator_a="s1", annotator_b="s1", adjudicated_label="s1"),
        R(item_id="2", annotator_a="s1", annotator_b="s2", adjudicated_label="s1"),
        R(item_id="3", annotator_a="s2", annotator_b="s1", adjudicated_label="s2"),
        R(item_id="4", annotator_a="s2", annotator_b="s2", adjudicated_label="s2"),
    ]
    s2 = bench.summarize_adjudication(mixed)
    assert s2["meets_prerequisite"] is False
    assert "BELOW" in s2["verdict"]


# ---------------------------------------------------------------------------
# #13 — embeddings API: deterministic fallback contract
# ---------------------------------------------------------------------------


def test_embeddings_deterministic(embeddings):
    a = embeddings.embed_texts(["السلام عليكم"])
    b = embeddings.embed_texts(["السلام عليكم"])
    assert a["vectors"][0]["vector"] == b["vectors"][0]["vector"]


def test_embeddings_beta_note_and_dims(embeddings):
    out = embeddings.embed_texts(["hello world", ""], dims=64)
    assert out["note"] == "beta/unverified"
    assert out["dims"] == 64
    for v in out["vectors"]:
        assert v["dims"] == 64
        assert len(v["vector"]) == 64
        assert "NOT a trained embedding" in v["source"]


def test_embeddings_unit_norm(embeddings):
    out = embeddings.embed_texts(["نص تجريبي"])
    vec = out["vectors"][0]["vector"]
    assert math.sqrt(sum(x * x for x in vec)) == pytest.approx(1.0)


def test_embeddings_differ_across_texts(embeddings):
    a = embeddings.embed_texts(["نص أول"])["vectors"][0]["vector"]
    b = embeddings.embed_texts(["نص ثان مختلف"])["vectors"][0]["vector"]
    assert a != b


def test_embeddings_rejects_bad_dims(embeddings):
    with pytest.raises(ValueError):
        embeddings.embed_texts(["x"], dims=0)
