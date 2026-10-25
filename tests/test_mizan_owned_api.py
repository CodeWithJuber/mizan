"""Authentication and own inference through the actual application routes."""

import uuid
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from mizan_owned.provider import ABSTAIN


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("MIZAN_OWNED_DB", str(tmp_path / "owned.db"))
    monkeypatch.setenv("MIZAN_OWNED_ONLY", "true")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("DB_PATH", ":memory:")
    monkeypatch.delenv("MIZAN_REPLY_CHECKPOINT", raising=False)
    from api.main import app, auth

    client = TestClient(app, raise_server_exceptions=True)

    def headers(role):
        user = auth.create_user("owned-" + uuid.uuid4().hex, "testpass", roles=[role])
        return {"Authorization": "Bearer " + auth.create_token(user)}

    return client, headers("admin"), headers("user")


@pytest.mark.parametrize("name", ["mizan-owned", "mizan-minimind"])
def test_agent_and_global_provider_requests_accept_both_architectures(api, name):
    # Initialize the real application through the isolated API fixture before
    # importing its schemas; a fresh CI process has no deployment /data volume.
    from api.main import AgentModelRequest, ProviderSwitchRequest

    assert AgentModelRequest(provider=name, model="test-model").provider == name
    assert ProviderSwitchRequest(provider=name, model="test-model").provider == name


def test_real_routes_require_auth_and_admin_for_teacher_review(api, monkeypatch):
    client, admin, user = api
    body = {"messages": [{"role": "user", "content": "hello"}]}
    external = Mock(side_effect=AssertionError("Must not call external teacher"))
    monkeypatch.setattr("mizan_owned.support.draft_support", external)
    assert client.post("/api/owned/chat", json=body).status_code == 401
    assert client.post("/api/owned/support", json=body, headers=user).status_code == 403
    assert client.get("/api/owned/reviews", headers=user).status_code == 403
    response = client.post("/api/owned/chat", json=body, headers=user)
    assert response.status_code == 200
    assert response.json()["text"] == ABSTAIN
    assert response.json()["owned_status"] == "abstained"
    external.assert_not_called()
    assert client.get("/api/providers", headers=admin).json()["active"] == "mizan-owned"
    assert client.get("/api/providers/mizan-owned/health", headers=admin).json()["healthy"]


def test_actual_support_review_and_chat_cycle(api, monkeypatch):
    from providers import ContentBlock, LLMResponse

    client, admin, user = api
    teacher = Mock()
    teacher.create.return_value = LLMResponse([ContentBlock(type="text", text="reviewed fixture")])
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-secret")
    monkeypatch.setenv("MIZAN_SUPPORT_MODEL", "test/teacher")
    monkeypatch.setattr("mizan_owned.support.OpenAICompatibleProvider", lambda **kwargs: teacher)
    body = {"messages": [{"role": "user", "content": "question"}]}
    draft = client.post("/api/owned/support", json=body, headers=admin)
    assert draft.status_code == 200
    proposal = draft.json()["proposal"]
    assert client.post("/api/owned/chat", json=body, headers=admin).json()["text"] == ABSTAIN
    review = {
        "expected_hash": proposal["answer_hash"],
        "accepted": True,
        "evidence": "manual:fixture",
    }
    route = "/api/owned/reviews/" + proposal["id"]
    assert client.post(route, json={**review, "reviewer": "fake"}, headers=admin).status_code == 422
    assert client.post(route, json=review, headers=admin).status_code == 200
    assert (
        client.post("/api/owned/chat", json=body, headers=admin).json()["text"]
        == "reviewed fixture"
    )
    assert client.post("/api/owned/chat", json=body, headers=user).json()["text"] == ABSTAIN
    assert len(client.get("/api/owned/export", headers=admin).json()["records"]) == 1
    response = client.post("/api/owned/retract", json={"evidence": "manual:fixture"}, headers=admin)
    assert response.json()["retracted"] == 1
    assert client.post("/api/owned/chat", json=body, headers=admin).json()["text"] == ABSTAIN
    assert teacher.create.call_count == 1


def test_context_engine_runs_without_teacher_and_rejects_unknown_fields(api):
    client, _, user = api
    body = {
        "ontology": {"place": ["river", "city"]},
        "senses": ["shore", "finance"],
        "language": "en",
        "symbol": "bank",
        "context": {"place": "river"},
        "observations": [
            {"id": "e1", "context": {"place": "river"}, "sense": "shore", "source": "fixture"}
        ],
    }
    response = client.post("/api/owned/context/resolve", json=body, headers=user)
    assert response.status_code == 200 and response.json()["sense"] == "shore"
    assert response.json()["verified"] is False
    body["context"] = {"hidden_intention": "unknown"}
    assert client.post("/api/owned/context/resolve", json=body, headers=user).status_code == 422
