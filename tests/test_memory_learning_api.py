"""End-to-end API boundaries for explicit preferences, review and training inputs."""

import asyncio
import json
from unittest.mock import AsyncMock

from learner.ruh_learner import RuhLearner
from memory.dhikr import DhikrMemorySystem
from tests.test_chat_sse import api as shared_chat_fixture
from tests.test_chat_sse import headers, message

api = shared_chat_fixture


def test_explicit_preferences_survive_restart_and_reach_only_owners_chat(api, monkeypatch):
    main, client, tokens, _, memory, agent, _ = api
    alice = headers(tokens["alice"])
    bob = headers(tokens["bob"])
    values = {"language": "Hinglish", "greeting": "Assalamu alaikum", "avoid_greetings": "Namaste"}
    for key, value in values.items():
        assert client.put(f"/api/chat/preferences/{key}", json={"value": value}).status_code == 401
        response = client.put(
            f"/api/chat/preferences/{key}",
            json={"value": value, "owner_id": "bob"},
            headers=alice,
        )
        assert response.status_code == 200
    monkeypatch.setattr(main, "memory", DhikrMemorySystem(memory.db_path))
    saved = client.get("/api/chat/preferences", headers=alice).json()["preferences"]
    assert {row["key"]: row["value"] for row in saved} == values
    assert client.get("/api/chat/preferences", headers=bob).json()["preferences"] == []
    assert client.post("/api/chat/stream", json=message("new-a"), headers=alice).status_code == 200
    assert agent.calls[-1][1]["user_preferences"] == saved
    assert client.post("/api/chat/stream", json=message("new-b"), headers=bob).status_code == 200
    assert agent.calls[-1][1]["user_preferences"] == []
    assert client.delete("/api/chat/preferences/greeting", headers=alice).json()["deleted"] is True
    monkeypatch.setattr(main, "memory", DhikrMemorySystem(memory.db_path))
    remaining = client.get("/api/chat/memory/summary", headers=alice).json()["preferences"]
    assert "greeting" not in {row["key"] for row in remaining}


def test_review_and_export_bind_owner_and_reviewer_with_model_provenance(
    api, monkeypatch, tmp_path
):
    _, client, tokens, users, _, _, _ = api
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    learner = RuhLearner.for_owner(users["alice"].id)
    asyncio.run(learner.initialize())
    asyncio.run(learner.capture("Prompt", "Model draft", "openrouter", "observed-model"))
    alice = headers(tokens["alice"])
    bob = headers(tokens["bob"])
    assert client.get("/api/learner/recent").status_code == 401
    assert client.post("/api/learner/export").status_code == 401
    assert client.post("/api/learner/export", headers=alice).text == ""
    row = client.get("/api/learner/recent", headers=alice).json()["interactions"][0]
    review = {
        "expected_hash": row["content_hash"],
        "accepted": True,
        "evidence": "User reviewed phrasing; no claim of original source authorship.",
        "quality_score": 0.95,
        "reviewer_id": "forged-reviewer",
        "owner_id": "alice",
    }
    path = f"/api/learner/review/{row['id']}"
    assert client.post(path, json=review, headers=bob).status_code == 409
    assert client.post(path, json=review, headers=alice).status_code == 200
    exported = client.post("/api/learner/export", headers=alice)
    assert exported.status_code == 200
    record = json.loads(exported.text)
    assert record["review"]["reviewer_id"] == users["alice"].id
    assert record["provenance"]["authorship"] == "model"
    assert record["original_data_eligible"] is False
    assert "text" not in record and "messages" not in record
    assert client.post("/api/learner/export", headers=bob).text == ""
    assert client.get("/api/learner/recent", headers=bob).json()["interactions"] == []
    review["accepted"] = False
    assert client.post(path, json=review, headers=alice).status_code == 200
    assert client.post("/api/learner/export", headers=alice).text == ""


def test_training_api_default_does_not_generate_seeds_and_normal_users_cannot_start(
    api, monkeypatch
):
    main, client, tokens, _, _, _, _ = api
    monkeypatch.setenv("RUH_ENABLED", "true")
    launch = AsyncMock(return_value={"running": True})
    monkeypatch.setattr(main.training_manager, "start_training", launch)
    assert client.post("/api/training/start", json={}).status_code == 401
    assert (
        client.post("/api/training/start", json={}, headers=headers(tokens["alice"])).status_code
        == 403
    )
    launch.assert_not_called()
    admin = main.auth.create_user("admin", "test-password", roles=["admin"])
    authenticated = headers(main.auth.create_token(admin))
    assert client.post("/api/training/start", json={}, headers=authenticated).status_code == 200
    assert launch.await_args.kwargs["generate_seed_data"] is False
    assert (
        client.post(
            "/api/training/start", json={"generate_seed_data": True}, headers=authenticated
        ).status_code
        == 200
    )
    assert launch.await_args.kwargs["generate_seed_data"] is True
