"""Integration tests for the Ruh Morphology Analysis API (study use-case #2).

Torch-free: the router loads ``ruh_model/service/analyze.py`` by file path,
bypassing ``ruh_model/__init__.py`` (torch import). ``backend.api.main`` is
never imported here.
"""

import pytest

fastapi = pytest.importorskip("fastapi")
TestClient = pytest.importorskip("fastapi.testclient", reason="needs httpx").TestClient

from api.ruh_morphology import router  # noqa: E402

app = fastapi.FastAPI()
app.include_router(router)
client = TestClient(app)

REQUIRED_TOKEN_KEYS = {
    "surface",
    "root",
    "pattern",
    "lemma",
    "pos",
    "diac",
    "confidence",
    "confidence_source",
}


def _post(text: str, **kwargs):
    return client.post("/v1/analyze", json={"text": text, **kwargs})


def test_schema_shape():
    resp = _post("كتب الكاتب الكتاب")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "tokens" in body and "model_info" in body
    assert len(body["tokens"]) == 3
    for token in body["tokens"]:
        assert REQUIRED_TOKEN_KEYS.issubset(token.keys()), token.keys()
        assert token["confidence_source"] == "heuristic/unverified"
        assert token["confidence_source"] != "calibrated"
        assert 0.0 <= token["confidence"] <= 1.0
    assert body["model_info"]["mode"] == "deterministic"
    assert body["model_info"]["confidence_source"] == "heuristic/unverified"
    assert "backend_version" in body["model_info"]


def test_kataba_family_roots():
    """Deterministic fixture: كتاب، كاتب، مكتبة all resolve to root ك-ت-ب."""
    resp = _post("كتاب كاتب مكتبة")
    assert resp.status_code == 200, resp.text
    roots = {t["surface"]: t["root"] for t in resp.json()["tokens"]}
    assert roots["كتاب"] == "كتب", roots
    assert roots["كاتب"] == "كتب", roots
    assert roots["مكتبة"] == "كتب", roots
    by_surface = {t["surface"]: t for t in resp.json()["tokens"]}
    assert by_surface["كاتب"]["pattern"] == "ACTIVE_PARTICIPLE"
    assert by_surface["كاتب"]["lemma"] == "كاتب"
    assert by_surface["كاتب"]["pos"] == "noun"


def test_empty_text_rejected():
    assert _post("").status_code == 422
    assert _post("   ").status_code == 422


def test_invalid_mode_rejected():
    resp = _post("كتاب", mode="magic")
    assert resp.status_code == 422


def test_nbest_mode_returns_alternatives():
    resp = _post("مكتبة", mode="nbest")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["model_info"]["mode"] == "nbest"
    token = body["tokens"][0]
    assert token["root"] == "كتب"
    assert token["alternatives"], "nbest must include runner-up candidates"
    for alt in token["alternatives"]:
        assert alt["confidence_source"] == "heuristic/unverified"
        assert 0.0 <= alt["confidence"] <= 1.0


def test_health_endpoint():
    resp = client.get("/v1/analyze/health")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tables_loaded"] is True
    assert body["root_count"] > 0
    assert body["model_available"] is False
    assert body["mode"] == "deterministic"
    assert body["confidence_source"] == "heuristic/unverified"
    assert body["backend_version"]


def test_quranic_domain_is_conservative():
    resp = _post("كتاب", domain="quranic")
    assert resp.status_code == 200, resp.text
    token = resp.json()["tokens"][0]
    assert token["confidence"] <= 0.75
    assert any("quranic" in flag for flag in token["flags"]), token["flags"]


def test_diacritics_echoed_never_invented():
    resp = _post("كَتَبَ")
    assert resp.status_code == 200, resp.text
    token = resp.json()["tokens"][0]
    assert token["diac"] == "كَتَبَ"
    resp2 = _post("كتب")
    assert resp2.json()["tokens"][0]["diac"] is None


def test_non_arabic_and_stopwords_do_not_crash():
    resp = _post("hello في book")
    assert resp.status_code == 200, resp.text
    tokens = {t["surface"]: t for t in resp.json()["tokens"]}
    assert tokens["hello"]["pattern"] == "NON_ARABIC"
    assert tokens["hello"]["root"] is None
    assert tokens["في"]["pattern"] == "STOPWORD"


def test_model_hook_raises_clear_error():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "ruh_morph_service_test",
        "ruh_model/service/analyze.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(module.MorphologyModelUnavailable):
        module.analyze_with_model("كتاب")
