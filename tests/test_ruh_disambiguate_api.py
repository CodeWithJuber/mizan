"""Tests for the Ruh sense-disambiguation API router (torch-free).

Covers: response schema, abstention behavior, unknown lemmas, threshold
override, top_k, determinism, and the honest OpenAPI note.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.ruh_disambiguate import get_inventory, router


@pytest.fixture(scope="module")
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture(scope="module")
def inventory():
    return get_inventory()


class TestInventoryLoaded:
    def test_inventory_version(self, inventory):
        assert inventory.version == "1.0.0"
        assert len(inventory) == 96
        assert len(inventory.lemmas()) == 48

    def test_inventory_version_in_every_response(self, client):
        resp = client.post(
            "/v1/disambiguate",
            json={"word": "آية", "context": "they recited the verse loudly"},
        )
        assert resp.status_code == 200
        assert resp.json()["inventory_version"] == "1.0.0"


class TestDisambiguateOk:
    def test_positive_case_real_inventory(self, client):
        # 'verse' sense keywords overlap the English context; 'sign' gets none.
        resp = client.post(
            "/v1/disambiguate",
            json={"word": "آية", "context": "they recited the verse loudly"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["sense_id"] == "qcsmp2:آيَة:verse"
        assert data["confidence"] == pytest.approx(1.0)
        assert data["gloss_en"] == "verse"
        assert data["abstained"] is False
        # Religious-flagged senses abstain at the stricter bar.
        assert data["threshold_used"] == pytest.approx(0.8)

    def test_response_schema_complete(self, client):
        resp = client.post("/v1/disambiguate", json={"word": "آية", "context": "verse"})
        data = resp.json()
        for key in (
            "word",
            "lemma",
            "status",
            "sense_id",
            "confidence",
            "gloss_ar",
            "gloss_en",
            "alternatives",
            "provenance",
            "inventory_version",
            "threshold_used",
            "abstained",
        ):
            assert key in data, f"missing response key: {key}"
        for alt in data["alternatives"]:
            assert set(alt) >= {"sense_id", "gloss_ar", "gloss_en", "confidence"}

    def test_provenance_receipt_shape(self, client):
        resp = client.post("/v1/disambiguate", json={"word": "آية", "context": "verse"})
        prov = resp.json()["provenance"]
        assert isinstance(prov, list) and prov
        signals = {p["signal"] for p in prov}
        assert "inventory" in signals
        assert "context_overlap" in signals
        # No model was wired into this call — so no "model" signal is invented.
        assert "model" not in signals
        for p in prov:
            assert p["source"] and isinstance(p["source"], str)
            assert 0.0 <= p["weight"] <= 1.0


class TestAbstention:
    def test_no_signal_abstains(self, client):
        # Arabic context, English-only glosses: the provisional scorer has no
        # evidence and must abstain rather than guess (amāna).
        resp = client.post(
            "/v1/disambiguate",
            json={"word": "آية", "context": "قرأ الإمام الآية بصوت جميل"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "uncertain"
        assert data["sense_id"] is None
        assert data["abstained"] is True
        assert len(data["alternatives"]) > 0
        # The receipt still shows the evidence that WAS computed.
        assert {p["signal"] for p in data["provenance"]} == {
            "inventory",
            "context_overlap",
        }

    def test_unknown_lemma(self, client):
        resp = client.post(
            "/v1/disambiguate",
            json={"word": "xyzzy", "context": "some context here"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "unknown_lemma"
        assert data["sense_id"] is None
        assert data["confidence"] is None
        assert data["alternatives"] == []
        assert data["provenance"] == []  # no decision made — nothing to support

    def test_threshold_override(self, client):
        # "verse sign" splits evidence 0.5/0.5 -> below the 0.8 religious bar.
        # An explicit threshold=0.4 overrides the tier for this call.
        # (Zero-evidence abstention still holds at any threshold: no signal
        # at all is not a confidence question.)
        resp = client.post(
            "/v1/disambiguate",
            json={"word": "آية", "context": "verse sign"},
        )
        assert resp.json()["status"] == "uncertain"
        resp = client.post(
            "/v1/disambiguate",
            json={"word": "آية", "context": "verse sign", "threshold": 0.4},
        )
        data = resp.json()
        assert data["status"] == "ok"
        assert data["threshold_used"] == pytest.approx(0.4)

    def test_top_k_respected(self, client):
        resp = client.post(
            "/v1/disambiguate",
            json={"word": "آية", "context": "verse sign", "top_k": 1},
        )
        assert len(resp.json()["alternatives"]) == 1


class TestValidation:
    def test_empty_word_rejected(self, client):
        resp = client.post("/v1/disambiguate", json={"word": "", "context": "x"})
        assert resp.status_code == 422

    def test_missing_context_rejected(self, client):
        resp = client.post("/v1/disambiguate", json={"word": "آية"})
        assert resp.status_code == 422

    def test_top_k_bounds(self, client):
        resp = client.post("/v1/disambiguate", json={"word": "آية", "context": "x", "top_k": 0})
        assert resp.status_code == 422

    def test_threshold_bounds(self, client):
        resp = client.post(
            "/v1/disambiguate",
            json={"word": "آية", "context": "x", "threshold": 1.5},
        )
        assert resp.status_code == 422


class TestDeterminism:
    def test_identical_calls_identical_output(self, client):
        body = {"word": "آية", "context": "they recited the verse loudly"}
        first = client.post("/v1/disambiguate", json=body).json()
        second = client.post("/v1/disambiguate", json=body).json()
        assert first == second


class TestHonestOpenAPI:
    def test_honest_note_in_openapi(self, client):
        spec = client.get("/openapi.json").json()
        desc = spec["paths"]["/v1/disambiguate"]["post"]["description"]
        assert "0.7592" in desc  # pilot accuracy, minimal-pair data
        assert "uncertain" in desc  # abstention documented
        assert "pending" in desc.lower()  # eval pending
        assert "provisional" in desc.lower()
