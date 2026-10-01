"""
Tests for the API endpoints
"""

import builtins
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create a test client with mocked dependencies."""
    # We need to mock heavy dependencies before importing
    with patch.dict(
        "os.environ",
        {
            "ANTHROPIC_API_KEY": "",
            "DB_PATH": ":memory:",
            "SECRET_KEY": "test-secret",
        },
    ):
        from api.main import app

        return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def auth_headers(client):
    """Create an admin user and return Bearer auth headers."""
    from api.main import auth

    user = auth.create_user("testadmin", "testpass", roles=["admin"])
    token = auth.create_token(user)
    return {"Authorization": f"Bearer {token}"}


class TestRootEndpoint:
    def test_root(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["system"] == "MIZAN (ميزان)"
        assert "version" in data
        assert data["status"] == "active"


@pytest.mark.parametrize(
    ("path", "field"),
    [
        ("/api/v1/root-analyze", "analysis"),
        ("/api/v1/tokenize", "tokens"),
        ("/api/v1/q28-features", "features"),
    ],
)
def test_public_nlp_routes_use_installed_package(client, monkeypatch, path, field):
    # Production contains ruh_model, without a standalone tokenizer package.
    # Other model tests may have exposed its directory on sys.path, so reject
    # that development-only import explicitly to reproduce the deployed layout.
    original_import = builtins.__import__

    def installed_import(name, *args, **kwargs):
        if name.startswith("tokenizer."):
            raise ModuleNotFoundError("No standalone tokenizer package")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", installed_import)
    response = client.post(path, json={"text": "علم", "lang": "ar"})
    assert response.status_code == 200, response.text
    assert response.json()[field]


class TestAgentEndpoints:
    def test_list_agents(self, client, auth_headers):
        resp = client.get("/api/agents", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "agents" in data
        assert "total" in data


class TestMemoryEndpoints:
    def test_store_memory(self, client, auth_headers):
        resp = client.post(
            "/api/memory/store",
            json={
                "content": "Test memory",
                "memory_type": "semantic",
                "importance": 0.7,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["stored"] is True

    def test_query_memory(self, client, auth_headers):
        resp = client.post(
            "/api/memory/query",
            json={
                "query": "test",
                "limit": 5,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert "results" in resp.json()


class TestAuthEnforcement:
    """Anonymous/invalid credentials must fail on state-changing routes."""

    def test_anonymous_store_memory_denied(self, client):
        resp = client.post("/api/memory/store", json={"content": "x"})
        assert resp.status_code == 401

    def test_anonymous_query_memory_denied(self, client):
        resp = client.post("/api/memory/query", json={"query": "x"})
        assert resp.status_code == 401

    def test_invalid_token_denied(self, client):
        resp = client.post(
            "/api/memory/store",
            json={"content": "x"},
            headers={"Authorization": "Bearer invalid-token"},
        )
        assert resp.status_code == 401


class TestSystemEndpoints:
    def test_status(self, client, auth_headers):
        resp = client.get("/api/status", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["system"] == "MIZAN"
        assert "agents" in data
        assert "security" in data

    def test_status_anonymous_denied(self, client):
        resp = client.get("/api/status")
        assert resp.status_code == 401
