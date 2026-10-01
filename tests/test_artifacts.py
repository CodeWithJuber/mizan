"""Tests for the chat artifacts API (backend/api/artifacts.py).

Two layers:
1. Router-level tests: mount the router on a bare FastAPI app with a temp
   DB_PATH and dependency_overrides for require_auth — full CRUD + privacy.
2. Delegation tests: the router's require_auth delegates to
   backend.api.main.require_auth via sys.modules. Importing the real main
   needs the full dependency tree (torch, ...), so here a stand-in api.main
   module proves the lookup; the real mount line is asserted from source.
"""

import sys
import types
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from api.artifacts import require_auth, router  # noqa: E402
from security.auth import TokenPayload  # noqa: E402

USER_1 = TokenPayload(
    user_id="user-1",
    username="tester1",
    roles=["user"],
    exp=9999999999.0,
    iat=1000000000.0,
    jti="test-jti-1",
)
USER_2 = TokenPayload(
    user_id="user-2",
    username="tester2",
    roles=["user"],
    exp=9999999999.0,
    iat=1000000000.0,
    jti="test-jti-2",
)


def make_client(db_file: Path, user: TokenPayload) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_auth] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def db_file(tmp_path, monkeypatch):
    path = tmp_path / "artifacts_test.db"
    monkeypatch.setenv("DB_PATH", str(path))
    return path


@pytest.fixture
def client(db_file):
    return make_client(db_file, USER_1)


def _create(client, **kw):
    payload = {
        "session_id": "sess-1",
        "title": "Test artifact",
        "kind": "markdown",
        "content": "# Hello\n\nSome *markdown* content.",
    }
    payload.update(kw)
    return client.post("/api/artifacts/", json=payload)


class TestCreate:
    def test_create_returns_id_and_version_1(self, client):
        r = _create(client)
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["version"] == 1
        assert isinstance(data["id"], str) and len(data["id"]) >= 16

    def test_create_each_kind(self, client):
        for kind in ("code", "html", "markdown"):
            r = _create(client, kind=kind, title=f"kind {kind}")
            assert r.status_code == 201, (kind, r.text)

    def test_create_invalid_kind_422(self, client):
        assert _create(client, kind="pdf").status_code == 422

    def test_create_empty_content_422(self, client):
        assert _create(client, content="").status_code == 422

    def test_create_missing_title_422(self, client):
        r = client.post("/api/artifacts/", json={"session_id": "s", "kind": "code"})
        assert r.status_code == 422


class TestRead:
    def test_get_roundtrip(self, client):
        created = _create(client, language="python").json()
        r = client.get(f"/api/artifacts/{created['id']}")
        assert r.status_code == 200, r.text
        art = r.json()
        assert art["id"] == created["id"]
        assert art["version"] == 1
        assert art["title"] == "Test artifact"
        assert art["kind"] == "markdown"
        assert art["language"] == "python"
        assert art["session_id"] == "sess-1"
        assert "# Hello" in art["content"]
        assert art["created_at"] and art["updated_at"]

    def test_get_missing_404(self, client):
        assert client.get("/api/artifacts/does-not-exist").status_code == 404


class TestVersions:
    def test_add_version_increments(self, client):
        created = _create(client).json()
        aid = created["id"]
        r = client.post(
            f"/api/artifacts/{aid}/versions",
            json={"content": "# v2 content", "title": "Renamed"},
        )
        assert r.status_code == 200, r.text
        assert r.json() == {"id": aid, "version": 2}

        latest = client.get(f"/api/artifacts/{aid}").json()
        assert latest["version"] == 2
        assert latest["content"] == "# v2 content"
        assert latest["title"] == "Renamed"

        versions = client.get(f"/api/artifacts/{aid}/versions").json()
        assert [v["version"] for v in versions] == [1, 2]
        assert "# Hello" in versions[0]["content"]
        assert versions[1]["content"] == "# v2 content"

    def test_add_version_missing_404(self, client):
        r = client.post("/api/artifacts/nope/versions", json={"content": "x"})
        assert r.status_code == 404

    def test_versions_missing_404(self, client):
        assert client.get("/api/artifacts/nope/versions").status_code == 404


class TestList:
    def test_list_filters_by_session(self, client):
        _create(client, session_id="sess-A", title="a1")
        _create(client, session_id="sess-A", title="a2")
        _create(client, session_id="sess-B", title="b1")
        all_items = client.get("/api/artifacts/").json()
        assert len(all_items) == 3
        sess_a = client.get("/api/artifacts/", params={"session_id": "sess-A"}).json()
        assert {a["title"] for a in sess_a} == {"a1", "a2"}
        assert all(a["version"] == 1 for a in sess_a)


class TestPrivacy:
    """Artifacts are private: cross-user access must 404, never leak."""

    def test_cross_user_isolation(self, db_file):
        c1 = make_client(db_file, USER_1)
        c2 = make_client(db_file, USER_2)
        aid = _create(c1).json()["id"]

        assert c2.get(f"/api/artifacts/{aid}").status_code == 404
        assert c2.get(f"/api/artifacts/{aid}/versions").status_code == 404
        assert (
            c2.post(f"/api/artifacts/{aid}/versions", json={"content": "evil"}).status_code == 404
        )
        assert c2.get("/api/artifacts/").json() == []
        # owner still sees it untouched
        assert c1.get(f"/api/artifacts/{aid}").status_code == 200


class TestAuthDelegation:
    """The router's require_auth must delegate to main.require_auth.

    The real backend.api.main cannot be imported here (needs torch etc.),
    so a stand-in module proves the sys.modules lookup; the actual mount
    line in main.py is asserted from source below.
    """

    def _client_with_fake_main(self, db_file, monkeypatch, behavior):
        fake_main = types.ModuleType("api.main")

        async def fake_require_auth(authorization=None, x_api_key=None):
            return await behavior(authorization, x_api_key)

        fake_main.require_auth = fake_require_auth
        monkeypatch.setitem(sys.modules, "api.main", fake_main)
        monkeypatch.delitem(sys.modules, "backend.api.main", raising=False)
        app = FastAPI()
        app.include_router(router)  # no dependency_overrides: delegation path
        return TestClient(app, raise_server_exceptions=False)

    def test_delegation_returns_main_payload(self, db_file, monkeypatch):
        async def ok(authorization=None, x_api_key=None):
            assert authorization == "Bearer good-token"
            return USER_1

        client = self._client_with_fake_main(db_file, monkeypatch, ok)
        r = client.get("/api/artifacts/", headers={"Authorization": "Bearer good-token"})
        assert r.status_code == 200, r.text
        assert r.json() == []

    def test_delegation_propagates_401(self, db_file, monkeypatch):
        async def deny(authorization=None, x_api_key=None):
            raise HTTPException(status_code=401, detail="Authentication required")

        client = self._client_with_fake_main(db_file, monkeypatch, deny)
        assert client.get("/api/artifacts/").status_code == 401
        assert client.post("/api/artifacts/", json={"session_id": "s"}).status_code == 401


class TestMountInMain:
    """The 2-line mount must exist in backend/api/main.py."""

    def test_router_mounted_in_main(self):
        main_py = Path(__file__).parent.parent / "backend" / "api" / "main.py"
        src = main_py.read_text(encoding="utf-8")
        assert "app.include_router(_artifacts_module.router)" in src
        assert "from . import artifacts as _artifacts_module" in src
        # require_auth must be defined in main for delegation to find it
        assert "async def require_auth(" in src
