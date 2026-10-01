"""Tests for backend/api/modes.py — deep_research pipeline + model compare.

The LLM layer is stubbed; no real provider calls happen.
"""

import asyncio
import json
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from api import modes
from api.modes import (
    BudgetTracker,
    _extract_claims,
    _merge_answer,
    _verify_claims,
    emit_progress,
    run_deep_research,
)


def _app():
    app = FastAPI()
    app.include_router(modes.router)
    return app


# ── deep_research gating ─────────────────────────────────────────────────────


def test_deep_research_requires_confirmation():
    client = TestClient(_app(), raise_server_exceptions=False)
    resp = client.post(
        "/api/modes/deep-research",
        json={"query": "explain quantum error correction", "confirmed": False},
    )
    assert resp.status_code == 409
    assert "confirmed" in resp.json()["detail"]


def test_list_modes():
    client = TestClient(_app(), raise_server_exceptions=False)
    assert client.get("/api/modes").json() == ["single", "deep_research"]


# ── pipeline with stubbed LLM ────────────────────────────────────────────────


def _stub_llm_factory():
    """Returns an async stub for modes._chat_completion keyed by system text."""

    async def stub(model, system, messages, max_tokens):
        user_text = messages[-1]["content"] if messages else ""
        if "research planner" in system:
            payload = json.dumps(["What is quantum error correction?", "Who invented Shor code?"])
            return payload, 50, 30
        if "research worker" in system:
            if "Shor" in user_text:
                return (
                    "- Peter Shor invented the 9-qubit Shor code in 1995.\n"
                    "- It protects against bit-flip and phase-flip errors.",
                    40,
                    30,
                )
            return (
                "- Quantum error correction protects qubits from decoherence.\n"
                "- The threshold theorem says fault-tolerant computation is possible.",
                40,
                30,
            )
        if "research synthesizer" in system:
            return (
                (
                    "- Quantum error correction protects qubits from decoherence.\n"
                    "- Peter Shor invented the 9-qubit Shor code in 1995.\n"
                    "- It runs on ordinary laptops without any quantum hardware."
                ),
                200,
                60,
            )
        # judge
        return (
            json.dumps(
                {
                    "scores": {"A": {"factual_accuracy": 8, "total": 30}},
                    "consensus": ["qec protects qubits"],
                    "contested": ["laptop claim"],
                    "winner": "A",
                    "reason": "A is more accurate",
                }
            ),
            100,
            50,
        )

    return stub


def test_deep_research_pipeline(monkeypatch):
    monkeypatch.setattr(modes, "_chat_completion", _stub_llm_factory())
    result = asyncio.run(run_deep_research("explain quantum error correction", max_subquestions=2))
    assert len(result.subquestions) == 2
    assert len(result.worker_outputs) == 2
    assert all(w["ok"] for w in result.worker_outputs)
    # The fabricated "laptops" claim has no keyword support in worker outputs.
    assert any("laptops" in c for c in result.unsupported_claims)
    assert result.tokens_used > 0
    assert result.cost_usd >= 0


def test_deep_research_emits_progress_events(monkeypatch):
    monkeypatch.setattr(modes, "_chat_completion", _stub_llm_factory())
    events = []

    async def sink(event):
        events.append(event)

    monkeypatch.setattr(modes, "_progress_sink", sink)
    modes.set_progress_sink(sink)
    try:
        asyncio.run(run_deep_research("q", max_subquestions=2))
    finally:
        modes.set_progress_sink(None)
    stages = [e["stage"] for e in events]
    assert stages == ["planning", "researching", "aggregating", "verifying", "done"]
    assert all(e["type"] == "mode_progress" for e in events)
    assert events[-1]["cost_so_far"] >= 0


def test_deep_research_budget_enforced(monkeypatch):
    monkeypatch.setattr(modes, "_chat_completion", _stub_llm_factory())
    monkeypatch.setenv("DEEP_RESEARCH_MAX_TOKENS", "1")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(run_deep_research("q", max_subquestions=2))
    assert exc.value.status_code == 402
    assert "budget exceeded" in exc.value.detail


def test_verify_claims_unit():
    workers = [
        {"answer": "Quantum error correction protects qubits from decoherence."},
        {"answer": "Peter Shor invented the 9-qubit Shor code in 1995."},
    ]
    answer = (
        "- Quantum error correction protects qubits from decoherence.\n"
        "- It also cures baldness and predicts lottery numbers."
    )
    unsupported = _verify_claims(answer, workers)
    assert len(unsupported) == 1
    assert "lottery" in unsupported[0]


def test_extract_claims_unit():
    text = "intro line\n- claim one\n* claim two\nnot a claim\n• claim three"
    assert _extract_claims(text) == ["claim one", "claim two", "claim three"]


def test_budget_tracker_caps():
    tracker = BudgetTracker("r1")
    tracker.max_tokens = 100
    tracker.max_cost_usd = 0.000001
    from api.modes import BudgetExceeded

    with pytest.raises(BudgetExceeded):
        tracker.record(1000, 1000)


# ── compare ──────────────────────────────────────────────────────────────────


def test_compare_blind_labels_no_leak(monkeypatch):
    async def stub(model, system, messages, max_tokens):
        return "a generic blind answer", 10, 10

    monkeypatch.setattr(modes, "_chat_completion", stub)
    client = TestClient(_app(), raise_server_exceptions=False)
    resp = client.post(
        "/api/compare",
        json={"prompt": "say hi", "models": ["model-x", "model-y", "model-z"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert [r["label"] for r in body["results"]] == ["A", "B", "C"]
    joined = json.dumps(body)
    # The blind response must not leak which model produced which label.
    assert "model-x" not in joined and "model-y" not in joined


def test_compare_requires_distinct_models(monkeypatch):
    client = TestClient(_app(), raise_server_exceptions=False)
    resp = client.post("/api/compare", json={"prompt": "hi", "models": ["m", "m"]})
    assert resp.status_code == 400


def test_reveal_and_judge(monkeypatch):
    async def stub(model, system, messages, max_tokens):
        if "impartial judge" in system:
            return (
                json.dumps(
                    {
                        "scores": {
                            "A": {
                                "factual_accuracy": 9,
                                "relevance_completeness": 8,
                                "clarity_concision": 7,
                                "safety_honesty": 9,
                                "total": 33,
                            },
                            "B": {
                                "factual_accuracy": 5,
                                "relevance_completeness": 6,
                                "clarity_concision": 6,
                                "safety_honesty": 8,
                                "total": 25,
                            },
                        },
                        "consensus": ["both greet the user"],
                        "contested": ["B claims to be sentient"],
                        "winner": "A",
                        "reason": "A more accurate",
                    }
                ),
                100,
                60,
            )
        return f"answer from {model}", 10, 10

    monkeypatch.setattr(modes, "_chat_completion", stub)
    client = TestClient(_app(), raise_server_exceptions=False)
    cmp_id = client.post("/api/compare", json={"prompt": "say hi", "models": ["mx", "my"]}).json()[
        "compare_id"
    ]

    # reveal mapping
    rev = client.post(f"/api/compare/{cmp_id}/reveal", json={"choice": "A"})
    assert rev.status_code == 200
    assert rev.json()["mapping"] == {"A": "mx", "B": "my"}
    assert rev.json()["user_choice"] == "A"
    assert rev.json()["judge"] is None

    # bad choice rejected
    bad = client.post(f"/api/compare/{cmp_id}/reveal", json={"choice": "Z"})
    assert bad.status_code == 400

    # judge mode
    j = client.post(f"/api/compare/{cmp_id}/reveal", json={"judge": True})
    body = j.json()
    assert body["judge"]["winner"] == "A"
    merged = body["merged_answer"]
    assert "CONSENSUS" in merged and "CONTESTED" in merged
    assert "both greet the user" in merged
    assert "B claims to be sentient" in merged

    # unknown id → 404
    nf = client.post("/api/compare/nope/reveal", json={})
    assert nf.status_code == 404


def test_merge_answer_shape():
    merged = _merge_answer({"consensus": ["a"], "contested": []})
    assert "## CONSENSUS" in merged and "## CONTESTED" in merged


def test_emit_progress_without_sink():
    event = asyncio.run(emit_progress("r1", "done", "ok", 0.01, 10))
    assert event["type"] == "mode_progress"
    assert event["stage"] == "done"
