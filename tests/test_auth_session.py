"""Who am I, and logging out for real (the live benchmark, 27 Oct 2026: there
was no /api/auth/me and no way to revoke a token before it expired)."""

from fastapi.testclient import TestClient

from security.auth import MizanAuth


def test_a_revoked_token_stays_revoked_after_a_restart(tmp_path):
    auth = MizanAuth("secret", data_dir=str(tmp_path))
    user = auth.create_user("amina", "pass", roles=["user"])
    token = auth.create_token(user)
    payload = auth.verify_token(token)
    assert payload is not None
    auth.revoke_token(payload.jti, payload.exp)
    restarted = MizanAuth("secret", data_dir=str(tmp_path))
    assert restarted.verify_token(token) is None


def test_logging_out_everywhere_ends_every_earlier_token(tmp_path):
    auth = MizanAuth("secret", data_dir=str(tmp_path))
    user = auth.create_user("bilal", "pass", roles=["user"])
    first, second = auth.create_token(user), auth.create_token(user)
    auth.revoke_all(user.id)
    assert auth.verify_token(first) is None and auth.verify_token(second) is None
    assert auth.verify_token(auth.create_token(user)) is not None  # a new login works
    restarted = MizanAuth("secret", data_dir=str(tmp_path))
    assert restarted.verify_token(first) is None


def test_me_and_logout_routes():
    from api.main import app, auth

    user = auth.create_user("me-route-user", "pass", roles=["user"])
    headers = {"Authorization": f"Bearer {auth.create_token(user)}"}
    client = TestClient(app)
    me = client.get("/api/auth/me", headers=headers).json()
    assert me["username"] == "me-route-user" and me["credential"] == "token"
    assert me["expires_at"] > me["issued_at"]
    assert client.post("/api/auth/logout", headers=headers).json()["logged_out"]
    assert client.get("/api/auth/me", headers=headers).status_code == 401
    assert client.get("/api/auth/me").status_code == 401


def test_an_unknown_caller_gets_401_before_its_body_is_read():
    from api.main import app

    client = TestClient(app)
    malformed = client.post(
        "/api/chat/stream", content=b"{not json", headers={"Content-Type": "application/json"}
    )
    assert malformed.status_code == 401
    assert client.get("/api/health").status_code in {200, 503}  # public stays public


def test_cors_credentials_only_with_a_matched_origin():
    from api.main import app

    client = TestClient(app)
    foreign = client.get("/api/health", headers={"Origin": "https://attacker.example"})
    assert "access-control-allow-credentials" not in foreign.headers
    assert "access-control-allow-origin" not in foreign.headers


def test_failed_sign_ins_are_limited_with_retry_after(monkeypatch):
    import asyncio

    from api import main

    async def no_wait(_seconds):
        return None

    monkeypatch.setattr(main.asyncio, "sleep", no_wait)
    monkeypatch.setattr(main, "_login_failures", main.RateLimiter(per_minute=5, burst=5))
    client = TestClient(main.app)
    body = {"username": "nobody-here", "password": "wrong"}
    codes = [client.post("/api/auth/login", json=body).status_code for _ in range(6)]
    assert codes[:5] == [401] * 5 and codes[5] == 429
    limited = client.post("/api/auth/login", json=body)
    assert (
        int(limited.headers["retry-after"]) >= 1 and limited.headers["ratelimit-remaining"] == "0"
    )
    assert asyncio  # the sleep after a failure is patched out for speed


def test_every_error_has_one_shape():
    from api.main import app

    client = TestClient(app)
    unauthenticated = client.get("/api/agents").json()
    assert unauthenticated["error"] == {
        "code": "unauthenticated",
        "status": 401,
        "message": "Authentication required",
    }
    assert unauthenticated["detail"] == "Authentication required"  # what clients read today
    from api.main import auth

    user = auth.create_user("envelope-user", "pass", roles=["user"])
    headers = {"Authorization": f"Bearer {auth.create_token(user)}"}
    missing = client.get("/api/no-such-route", headers=headers).json()
    assert missing["error"]["code"] == "not_found"
    invalid = client.post("/api/chat/stream", json={"content": ""}, headers=headers).json()
    assert invalid["error"]["code"] == "invalid_request" and isinstance(invalid["detail"], list)


def test_the_api_is_documented_in_public():
    from api.main import app

    client = TestClient(app)
    spec = client.get("/api/openapi.json")
    assert spec.status_code == 200 and "/api/chat/stream" in spec.json()["paths"]
    page = client.get("/api/docs")
    assert page.status_code == 200 and "cdn.jsdelivr.net" in page.headers["content-security-policy"]


def test_agents_can_be_listed_briefly_and_in_pages():
    from api.main import active_agents, app, auth

    admin = auth.create_user("paging-admin", "pass", roles=["admin"])
    headers = {"Authorization": f"Bearer {auth.create_token(admin)}"}
    client = TestClient(app)
    brief = client.get("/api/agents?detail=false", headers=headers).json()
    assert brief["total"] == len(active_agents)
    for item in brief["agents"]:
        assert set(item) <= {
            "id",
            "name",
            "role",
            "state",
            "nafs_level",
            "current_task",
            "model",
            "load",
        }
    page = client.get("/api/agents?limit=1&offset=0", headers=headers).json()
    assert len(page["agents"]) == min(1, len(active_agents))
