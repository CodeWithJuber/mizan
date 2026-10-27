"""Web Push: known push services only, own signing key, gone devices removed."""

import base64
import json
import sqlite3
from types import SimpleNamespace

import pytest

from gateway import push
from gateway.store import BabStore

# What a browser sends: a 65-byte P-256 point and a 16-byte secret, base64url.
P256DH = base64.urlsafe_b64encode(b"\x04" + bytes(range(64))).decode().rstrip("=")
AUTH = base64.urlsafe_b64encode(bytes(range(16))).decode().rstrip("=")


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    return BabStore(str(tmp_path / "bab.db"))


@pytest.mark.parametrize(
    "endpoint,ok",
    [
        ("https://fcm.googleapis.com/fcm/send/abc", True),
        ("https://updates.push.services.mozilla.com/wpush/v2/x", True),
        ("https://web.push.apple.com/QGx", True),
        ("https://wns2-par02p.notify.windows.com/w/?token=x", True),
        ("http://fcm.googleapis.com/fcm/send/abc", False),  # not HTTPS
        ("https://evil.example/fcm.googleapis.com", False),
        ("https://fcm.googleapis.com.evil.example/x", False),
        ("https://user@fcm.googleapis.com/x", False),
        ("https://fcm.googleapis.com:8443/x", False),
        ("https://169.254.169.254/latest", False),
    ],
)
def test_only_known_push_services_are_accepted(endpoint, ok):
    assert push.allowed_endpoint(endpoint) is ok


def test_a_subscription_to_anywhere_else_is_refused(store):
    with pytest.raises(ValueError):
        push.subscribe(store, "alice", "https://internal.example/hook", P256DH, AUTH)
    push.subscribe(store, "alice", "https://fcm.googleapis.com/fcm/send/1", P256DH, AUTH)
    assert [s["endpoint"] for s in push.subscriptions(store, "alice")] == [
        "https://fcm.googleapis.com/fcm/send/1"
    ]
    assert push.subscriptions(store, "bob") == []


def test_the_signing_key_is_made_once_and_kept_sealed(store):
    first, second = push.public_key(store), push.public_key(store)
    assert first == second and len(first) == 87  # 65-byte P-256 point, base64url
    with sqlite3.connect(store.path) as conn:
        sealed = conn.execute("SELECT value FROM state WHERE key = 'vapid_private'").fetchone()[0]
    assert "PRIVATE KEY" not in sealed  # never stored as plain PEM


async def test_a_notice_reaches_each_device_and_gone_ones_are_removed(store, monkeypatch):
    import pywebpush

    sent = []

    def webpush(subscription_info, data, **kwargs):
        sent.append((subscription_info["endpoint"], json.loads(data), kwargs["vapid_claims"]))
        if subscription_info["endpoint"].endswith("/gone"):
            raise pywebpush.WebPushException("gone", response=SimpleNamespace(status_code=410))

    monkeypatch.setattr(pywebpush, "webpush", webpush)
    push.subscribe(store, "alice", "https://fcm.googleapis.com/fcm/send/live", P256DH, AUTH)
    push.subscribe(store, "alice", "https://fcm.googleapis.com/fcm/send/gone", P256DH, AUTH)

    counts = await push.notify(store, "alice", "MIZAN", "Asr in 10 minutes", "/?session=m")
    assert counts == {"sent": 1, "gone": 1, "failed": 0}
    assert [s["endpoint"] for s in push.subscriptions(store, "alice")] == [
        "https://fcm.googleapis.com/fcm/send/live"
    ]
    payload = sent[0][1]
    assert payload["body"] == "MIZAN has a new notice"  # the lock screen shows no content
    assert payload["url"] == "/?session=m" and sent[0][2]["sub"].startswith("mailto:")

    await push.notify(store, "alice", "MIZAN", "Asr in 10 minutes", preview=True)
    assert sent[-1][1]["body"] == "Asr in 10 minutes"


async def test_nobody_subscribed_sends_nothing(store, monkeypatch):
    import pywebpush

    monkeypatch.setattr(pywebpush, "webpush", lambda **kwargs: pytest.fail("no device"))
    assert await push.notify(store, "alice", "MIZAN", "x") == {"sent": 0, "gone": 0, "failed": 0}


def test_push_routes(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "chat.db"))
    monkeypatch.setenv("MIZAN_OWNED_DB", str(tmp_path / "owned.sqlite3"))
    import api.main as main
    from gateway import store as bab_store
    from security.auth import MizanAuth

    bab_store._STORES.clear()
    auth = MizanAuth("push-test-signing-key-" * 4, data_dir=str(tmp_path / "users"))
    alice = auth.create_user("alice", "test-password", roles=["user"])
    monkeypatch.setattr(main, "auth", auth)
    client = TestClient(main.app)
    headers = {"Authorization": "Bearer " + auth.create_token(alice)}

    key = client.get("/api/bab/push/key", headers=headers).json()
    assert len(key["public_key"]) == 87 and key["devices"] == 0
    refused = client.post(
        "/api/bab/push/subscription",
        json={"endpoint": "https://example.com/push", "keys": {"p256dh": P256DH, "auth": AUTH}},
        headers=headers,
    )
    assert refused.status_code == 400
    endpoint = "https://fcm.googleapis.com/fcm/send/device-1"
    ok = client.post(
        "/api/bab/push/subscription",
        json={"endpoint": endpoint, "keys": {"p256dh": P256DH, "auth": AUTH}},
        headers=headers,
    )
    assert ok.status_code == 200
    assert client.get("/api/bab/push/key", headers=headers).json()["devices"] == 1
    gone = client.delete(
        "/api/bab/push/subscription", params={"endpoint": endpoint}, headers=headers
    )
    assert gone.json() == {"removed": True}
