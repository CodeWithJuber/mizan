"""Tests for the Qwen3 use-case wiring (HTTP client mocked, no network).

Covers each wiring: chat+SSE with the understanding layer, WSD rerank
(flag-gated, deterministic fallback), i'rab grounding with citation check,
and QG-B grounded Q&A attestation.
"""

import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.qwen3 as qwen3_mod
import api.ruh_disambiguate as rd_mod
from api.qwen3 import (
    _parse_rerank_order,
    _verify_draft,
    grounded_analysis,
    grounded_qa,
    maybe_rerank_disambiguation,
    rerank_senses,
    router,
)
from api.qwen3_client import Qwen3Result, Qwen3Unavailable

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeQwen3Client:
    """Stands in for Qwen3Client; patch api.qwen3.get_client to return it."""

    def __init__(self, draft="draft text", chunks=None):
        self._draft = draft
        self._chunks = chunks if chunks is not None else [draft]
        self.config = SimpleNamespace(model="qwen3-0.6b-quran")

    async def generate(self, messages, **opts):
        return Qwen3Result(
            text=self._draft, model="qwen3-0.6b-quran", usage={"total_tokens": 3}, raw={}
        )

    def generate_sync(self, messages, **opts):
        return Qwen3Result(
            text=self._draft, model="qwen3-0.6b-quran", usage={"total_tokens": 3}, raw={}
        )

    async def generate_stream(self, messages, **opts):
        for chunk in self._chunks:
            yield chunk

    async def health(self, probe=False):
        return {"enabled": True, "configured": True, "endpoint_host": "x", "model": "m"}


@pytest.fixture
def qwen3_env(monkeypatch):
    monkeypatch.setenv("QWEN3_ENABLED", "1")
    monkeypatch.setenv("QWEN3_ENDPOINT_URL", "https://qwen3-test.runpod.net")
    monkeypatch.setenv("QWEN3_API_KEY", "test-key-123")
    monkeypatch.setenv("QWEN3_BACKOFF_BASE", "0")


@pytest.fixture
def fake_client(monkeypatch):
    fake = FakeQwen3Client()
    monkeypatch.setattr(qwen3_mod, "get_client", lambda config=None: fake)
    return fake


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def parse_sse(text):
    """Parse 'event: KIND\\ndata: JSON' frames into (kind, payload) pairs."""
    frames = []
    for block in text.strip().split("\n\n"):
        kind, data = None, None
        for line in block.splitlines():
            if line.startswith("event:"):
                kind = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data = json.loads(line[len("data:") :].strip())
        if kind:
            frames.append((kind, data))
    return frames


# ---------------------------------------------------------------------------
# Use case 1 — Chat (+SSE) with the understanding layer
# ---------------------------------------------------------------------------


class TestChat:
    def test_chat_returns_text_and_understanding(self, qwen3_env, fake_client, client):
        fake_client._draft = "كتب الولد الدرس"
        resp = client.post(
            "/v1/qwen3/chat",
            json={"messages": [{"role": "user", "content": "explain"}], "max_tokens": 50},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["text"] == "كتب الولد الدرس"
        assert data["model"] == "qwen3-0.6b-quran"
        understanding = data["understanding"]
        assert understanding is not None
        assert understanding["status"] in ("ok", "degraded")
        assert len(understanding["tokens"]) == 3
        first = understanding["tokens"][0]
        assert first["surface"] == "كتب"
        assert first["root"] == "كتب"
        assert first["root_provenance"] == "verified"
        assert first["role"] == "verb"  # from the existing morphology service

    def test_chat_without_understanding(self, qwen3_env, fake_client, client):
        resp = client.post(
            "/v1/qwen3/chat",
            json={
                "messages": [{"role": "user", "content": "hi"}],
                "include_understanding": False,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["understanding"] is None

    def test_chat_503_when_disabled(self, monkeypatch, client):
        # No fake client here: the REAL client must raise qwen3_disabled.
        monkeypatch.delenv("QWEN3_ENABLED", raising=False)
        resp = client.post("/v1/qwen3/chat", json={"messages": [{"role": "user", "content": "hi"}]})
        assert resp.status_code == 503
        assert resp.json()["detail"]["code"] == "qwen3_disabled"

    def test_chat_503_when_endpoint_fails(self, qwen3_env, monkeypatch, client):
        class FailingClient(FakeQwen3Client):
            async def generate(self, messages, **opts):
                raise Qwen3Unavailable("qwen3_exhausted", "down")

        monkeypatch.setattr(qwen3_mod, "get_client", lambda config=None: FailingClient())
        resp = client.post("/v1/qwen3/chat", json={"messages": [{"role": "user", "content": "hi"}]})
        assert resp.status_code == 503
        assert resp.json()["detail"]["code"] == "qwen3_exhausted"

    def test_chat_stream_events(self, qwen3_env, client, monkeypatch):
        fake = FakeQwen3Client(draft="كتب الولد", chunks=["كتب ", "الولد"])
        monkeypatch.setattr(qwen3_mod, "get_client", lambda config=None: fake)
        resp = client.post(
            "/v1/qwen3/chat/stream",
            json={"messages": [{"role": "user", "content": "go"}]},
        )
        assert resp.status_code == 200
        frames = parse_sse(resp.text)
        kinds = [k for k, _ in frames]
        assert kinds[0] == "start"
        assert kinds.count("token") == 2
        assert "understanding" in kinds
        assert kinds[-1] == "done"
        deltas = [d["delta"] for k, d in frames if k == "token"]
        assert "".join(deltas) == "كتب الولد"
        understanding = next(d for k, d in frames if k == "understanding")
        assert len(understanding["tokens"]) == 2

    def test_chat_stream_503_when_disabled(self, monkeypatch, client):
        monkeypatch.delenv("QWEN3_ENABLED", raising=False)
        resp = client.post(
            "/v1/qwen3/chat/stream", json={"messages": [{"role": "user", "content": "go"}]}
        )
        assert resp.status_code == 503

    def test_chat_stream_error_event_on_failure(self, qwen3_env, monkeypatch, client):
        class FailingClient(FakeQwen3Client):
            async def generate_stream(self, messages, **opts):
                raise Qwen3Unavailable("qwen3_transport", "conn refused")
                yield  # pragma: no cover — makes this an async generator

        monkeypatch.setattr(qwen3_mod, "get_client", lambda config=None: FailingClient())
        resp = client.post(
            "/v1/qwen3/chat/stream", json={"messages": [{"role": "user", "content": "go"}]}
        )
        assert resp.status_code == 200  # headers already sent; error rides the stream
        frames = parse_sse(resp.text)
        kinds = [k for k, _ in frames]
        assert "error" in kinds
        err = next(d for k, d in frames if k == "error")
        assert err["code"] == "qwen3_transport"

    def test_health_no_probe(self, qwen3_env, client):
        resp = client.get("/v1/qwen3/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is True
        assert data["endpoint_host"] == "qwen3-test.runpod.net"
        assert "test-key-123" not in resp.text


# ---------------------------------------------------------------------------
# Use case 2 — WSD rerank
# ---------------------------------------------------------------------------

_CANDIDATES = [
    {"sense_id": "s1", "gloss_en": "eye"},
    {"sense_id": "s2", "gloss_en": "spring"},
]


class TestRerank:
    async def test_rerank_orders_candidates(self, qwen3_env, monkeypatch):
        fake = FakeQwen3Client(draft='{"order": ["s2", "s1"]}')
        monkeypatch.setattr(qwen3_mod, "get_client", lambda config=None: fake)
        order = await rerank_senses("عين", "some context", _CANDIDATES)
        assert order == ["s2", "s1"]

    async def test_rerank_invalid_json_falls_back(self, qwen3_env, monkeypatch):
        fake = FakeQwen3Client(draft="I cannot decide")
        monkeypatch.setattr(qwen3_mod, "get_client", lambda config=None: fake)
        assert await rerank_senses("عين", "ctx", _CANDIDATES) is None

    async def test_rerank_unavailable_falls_back(self, qwen3_env, monkeypatch):
        class FailingClient(FakeQwen3Client):
            async def generate(self, messages, **opts):
                raise Qwen3Unavailable("qwen3_exhausted", "down")

        monkeypatch.setattr(qwen3_mod, "get_client", lambda config=None: FailingClient())
        assert await rerank_senses("عين", "ctx", _CANDIDATES) is None

    def test_parse_rerank_order_validates(self):
        assert _parse_rerank_order('{"order": ["s2", "s1"]}', _CANDIDATES) == ["s2", "s1"]
        # unknown id / missing id / not a list → None (deterministic fallback)
        assert _parse_rerank_order('{"order": ["s9", "s1"]}', _CANDIDATES) is None
        assert _parse_rerank_order('{"order": ["s1"]}', _CANDIDATES) is None
        assert _parse_rerank_order('{"order": "s1"}', _CANDIDATES) is None
        assert _parse_rerank_order("no json here", _CANDIDATES) is None

    def test_maybe_rerank_disabled_returns_none(self, monkeypatch):
        monkeypatch.delenv("QWEN3_ENABLED", raising=False)
        assert maybe_rerank_disambiguation("عين", "ctx", _CANDIDATES) is None

    def test_maybe_rerank_applies_order(self, qwen3_env, monkeypatch):
        fake = FakeQwen3Client(draft='{"order": ["s2", "s1"]}')
        monkeypatch.setattr(qwen3_mod, "get_client", lambda config=None: fake)
        alternatives = [
            {"sense_id": "s1", "gloss_en": "eye", "confidence": 0.9},
            {"sense_id": "s2", "gloss_en": "spring", "confidence": 0.4},
        ]
        out = maybe_rerank_disambiguation("عين", "ctx", alternatives)
        assert out is not None
        assert [a["sense_id"] for a in out["alternatives"]] == ["s2", "s1"]
        assert out["info"]["applied"] is True


class _FakeDisResult:
    def __init__(self, d):
        self._d = d

    def to_dict(self):
        return self._d


def _dis_result_dict():
    return {
        "word": "عين",
        "lemma": "عين",
        "status": "ok",
        "sense_id": "s1",
        "confidence": 0.9,
        "gloss_ar": None,
        "gloss_en": "eye",
        "alternatives": [
            {"sense_id": "s1", "gloss_ar": None, "gloss_en": "eye", "confidence": 0.9},
            {"sense_id": "s2", "gloss_ar": None, "gloss_en": "spring", "confidence": 0.4},
        ],
        "provenance": [{"signal": "inventory", "source": "sense-inventory/v1.0.0", "weight": 1.0}],
        "inventory_version": "1.0.0",
        "threshold_used": 0.6,
        "abstained": False,
    }


@pytest.fixture
def disambiguate_app(monkeypatch):
    """The /v1/disambiguate router with inventory + sense module stubbed."""

    class FakeDisModule:
        def disambiguate(self, word, context, inventory, top_k=3, threshold=None):
            return _FakeDisResult(_dis_result_dict())

    monkeypatch.setattr(rd_mod, "get_inventory", lambda: object())
    monkeypatch.setattr(rd_mod, "_load_sense_module", lambda name: FakeDisModule())
    app = FastAPI()
    app.include_router(rd_mod.router)
    return TestClient(app)


class TestDisambiguateWiring:
    def test_rerank_applied_behind_flag(self, qwen3_env, disambiguate_app, monkeypatch):
        def fake_rerank(word, context, alternatives):
            return {
                "alternatives": list(reversed(alternatives)),
                "info": {
                    "applied": True,
                    "model": "qwen3-0.6b-quran",
                    "order": ["s2", "s1"],
                    "reason": None,
                },
            }

        # disambiguate_word imports maybe_rerank lazily; patch the source.
        monkeypatch.setattr(qwen3_mod, "maybe_rerank_disambiguation", fake_rerank)
        resp = disambiguate_app.post(
            "/v1/disambiguate", json={"word": "عين", "context": "some context"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert [a["sense_id"] for a in data["alternatives"]] == ["s2", "s1"]
        assert data["qwen3"]["applied"] is True
        assert data["qwen3"]["order"] == ["s2", "s1"]
        signals = [p["signal"] for p in data["provenance"]]
        assert "qwen3_rerank" in signals
        # Deterministic decision stays authoritative.
        assert data["sense_id"] == "s1"

    def test_flag_off_keeps_deterministic_result(self, monkeypatch, disambiguate_app):
        monkeypatch.delenv("QWEN3_ENABLED", raising=False)
        resp = disambiguate_app.post(
            "/v1/disambiguate", json={"word": "عين", "context": "some context"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert [a["sense_id"] for a in data["alternatives"]] == ["s1", "s2"]
        assert data["qwen3"] is None
        signals = [p["signal"] for p in data["provenance"]]
        assert "qwen3_rerank" not in signals


# ---------------------------------------------------------------------------
# Use case 3 — I'rab grounding with citation check
# ---------------------------------------------------------------------------


class TestGroundedAnalysis:
    async def test_citation_check(self, qwen3_env, monkeypatch):
        evidence = [
            {"i": 0, "surface": "كتب", "root": "كتب", "pattern": "VERB_PAST", "pos": "verb"},
            {"i": 1, "surface": "الولد", "root": None, "pattern": "NOUN", "pos": "noun"},
        ]
        monkeypatch.setattr(qwen3_mod, "_morphology_evidence", lambda text: evidence)
        fake = FakeQwen3Client(draft="The verb at [tok 0] governs [tok 1]; see also [tok 9].")
        monkeypatch.setattr(qwen3_mod, "get_client", lambda config=None: fake)
        out = await grounded_analysis("كتب الولد")
        assert out["draft"].startswith("The verb")
        assert out["evidence"] == evidence
        assert out["citation_check"]["valid_citations"] == [0, 1]
        assert out["citation_check"]["invalid_citations"] == [9]

    async def test_no_evidence_raises_unavailable(self, qwen3_env, monkeypatch):
        monkeypatch.setattr(qwen3_mod, "_morphology_evidence", lambda text: None)
        fake = FakeQwen3Client()
        monkeypatch.setattr(qwen3_mod, "get_client", lambda config=None: fake)
        with pytest.raises(Qwen3Unavailable) as exc_info:
            await grounded_analysis("كتب")
        assert exc_info.value.code == "qwen3_no_evidence"

    def test_endpoint(self, qwen3_env, fake_client, client, monkeypatch):
        evidence = [{"i": 0, "surface": "كتب"}]
        monkeypatch.setattr(qwen3_mod, "_morphology_evidence", lambda text: evidence)
        fake_client._draft = "analysis [tok 0]"
        resp = client.post("/v1/qwen3/grounded-analysis", json={"text": "كتب"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["citation_check"]["valid_citations"] == [0]
        assert data["evidence"] == evidence


# ---------------------------------------------------------------------------
# Use case 4 — QG-B grounded Q&A attestation
# ---------------------------------------------------------------------------


class TestGroundedQA:
    def test_verify_draft_attested_when_quotes_in_source(self):
        paragraph = "كتب الولد الدرس في المدرسة"
        draft = 'The boy wrote the lesson: "كتب الولد الدرس".'
        v = _verify_draft("What happened?", paragraph, draft)
        assert v["attested"] is True
        assert all(q["found_in_source"] for q in v["quotes"])
        assert v["yaqin"]["draft"] == "ilm_al_yaqin"
        assert v["yaqin"]["verified_quotes"] == "ayn_al_yaqin"
        assert len(v["roots"]) > 0
        assert v["roots"][0]["root_provenance"] in ("verified", "heuristic", "unavailable")

    def test_verify_draft_rejects_unverifiable_quotes(self):
        paragraph = "كتب الولد الدرس"
        draft = 'It says "غير موجود في النص" here.'
        v = _verify_draft("What?", paragraph, draft)
        assert v["attested"] is False
        assert any(not q["found_in_source"] for q in v["quotes"])

    def test_verify_draft_no_quotes_not_attested(self):
        v = _verify_draft("What?", "كتب الولد", "The text is about writing.")
        assert v["attested"] is False

    async def test_grounded_qa_end_to_end(self, qwen3_env, fake_client):
        fake_client._draft = 'Answer: "كتب الولد الدرس".'
        out = await grounded_qa("What did the boy do?", "كتب الولد الدرس في المدرسة")
        assert out["draft"].startswith("Answer:")
        assert out["verification"]["attested"] is True
        assert out["model"] == "qwen3-0.6b-quran"

    def test_endpoint(self, qwen3_env, fake_client, client):
        fake_client._draft = 'Answer: "كتب الولد".'
        resp = client.post(
            "/v1/qwen3/grounded-qa",
            json={"question": "Who wrote?", "paragraph": "كتب الولد الدرس"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["verification"]["attested"] is True

    def test_endpoint_503_when_disabled(self, monkeypatch, client):
        # No fake client here: the REAL client must raise qwen3_disabled.
        monkeypatch.delenv("QWEN3_ENABLED", raising=False)
        resp = client.post(
            "/v1/qwen3/grounded-qa",
            json={"question": "Who?", "paragraph": "كتب الولد"},
        )
        assert resp.status_code == 503
