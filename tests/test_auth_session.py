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
