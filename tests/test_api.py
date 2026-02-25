"""
Tests for the API endpoints
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create a test client with mocked dependencies."""
    # We need to mock heavy dependencies before importing
    with patch.dict("os.environ", {
        "ANTHROPIC_API_KEY": "",
        "DB_PATH": ":memory:",
        "SECRET_KEY": "test-secret",
    }):
        from api.main import app
        return TestClient(app, raise_server_exceptions=False)


class TestRootEndpoint:
    def test_root(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["system"] == "MIZAN (ميزان)"
        assert "version" in data
        assert data["status"] == "active"


class TestAgentEndpoints:
    def test_list_agents(self, client):
        resp = client.get("/api/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert "agents" in data
        assert "total" in data


class TestMemoryEndpoints:
    def test_store_memory(self, client):
        resp = client.post("/api/memory/store", json={
            "content": "Test memory",
            "memory_type": "semantic",
            "importance": 0.7,
        })
        assert resp.status_code == 200
        assert resp.json()["stored"] is True

    def test_query_memory(self, client):
        resp = client.post("/api/memory/query", json={
            "query": "test",
            "limit": 5,
        })
        assert resp.status_code == 200
        assert "results" in resp.json()


class TestSystemEndpoints:
    def test_status(self, client):
        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["system"] == "MIZAN"
        assert "agents" in data
        assert "security" in data
