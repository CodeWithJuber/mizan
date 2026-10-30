"""The owner's consent decisions of 30 Oct 2026 (docs/consent.md): MIZAN learns
from a person's work for them unless they switch it off, their words become
training candidates only if they switch that on, each change is a Sakk receipt,
and only people aged 16 or older can sign up."""

import uuid

from fastapi.testclient import TestClient

from core.adaptive import AdaptiveStateStore
from memory import stateless


def bindings(**chosen):
    from api.main import consent_bindings

    return consent_bindings([{"key": key, "value": value} for key, value in chosen.items()])


def test_learning_is_on_and_training_off_by_default():
    with bindings():
        assert stateless.learns() and not stateless.trains()
        assert not stateless.active()  # nothing else changes: recall still reads


def test_learning_off_keeps_nothing_but_still_reads(tmp_path):
    store = AdaptiveStateStore(str(tmp_path / "adaptive.db"))
    store.put("kept", {"n": 1})
    with bindings(learning="Off"):
        assert not stateless.learns() and not stateless.active()
        store.put("kept", {"n": 2})
        store.put("learned", {"n": 3})
        assert store.get("kept") == {"n": 1}
    assert stateless.learns()
    assert store.get("learned") is None


def test_training_needs_a_yes():
    with bindings(training="on"):
        assert stateless.trains() and stateless.learns()
    with bindings(training="off", learning="on"):
        assert not stateless.trains() and stateless.learns()
    with stateless.bind(), bindings(training="on"):
        assert not stateless.trains()  # an evaluation never trains


def _client_and_headers():
    from api.main import app, auth

    user = auth.create_user(f"consent-{uuid.uuid4().hex[:8]}", "pass", roles=["user"])
    return TestClient(app), {"Authorization": f"Bearer {auth.create_token(user)}"}, user.id


def test_a_consent_choice_is_on_or_off_and_leaves_a_receipt(monkeypatch):
    from security import sakk

    receipts = []
    monkeypatch.setattr(
        sakk,
        "record",
        lambda owner, kind, fields, display="": receipts.append((owner, kind, fields)),
    )
    client, headers, owner = _client_and_headers()
    assert (
        client.put(
            "/api/chat/preferences/learning", json={"value": "maybe"}, headers=headers
        ).status_code
        == 422
    )
    saved = client.put("/api/chat/preferences/learning", json={"value": " Off "}, headers=headers)
    assert saved.status_code == 200 and saved.json()["value"] == "off"
    assert client.delete("/api/chat/preferences/learning", headers=headers).json()["deleted"]
    assert receipts == [
        (owner, "consent", {"purpose": "learning", "value": "off"}),
        (owner, "consent", {"purpose": "learning", "value": "default"}),
    ]
    # An ordinary preference is not a consent choice.
    client.put("/api/chat/preferences/language", json={"value": "Hinglish"}, headers=headers)
    assert len(receipts) == 2


def test_only_people_aged_16_or_older_can_sign_up():
    from api.main import app

    client = TestClient(app)
    name = f"age-{uuid.uuid4().hex[:8]}"
    refused = client.post(
        "/api/auth/register", json={"username": name, "password": "a-long-pass-1"}
    )
    assert refused.status_code == 422 and "16" in refused.text
    made = client.post(
        "/api/auth/register",
        json={"username": name, "password": "a-long-pass-1", "age_16_or_older": True},
    )
    assert made.status_code == 200 and made.json()["token"]


async def test_every_writer_keeps_consent_on_or_off(tmp_path):
    import pytest

    from memory import daftar
    from memory.dhikr import DhikrMemorySystem

    memory = DhikrMemorySystem(str(tmp_path / "memory.db"))
    with pytest.raises(ValueError, match="on or off"):
        await memory.set_chat_preference("amina", "training", "yes please")
    assert (await memory.set_chat_preference("amina", "learning", " OFF "))["value"] == "off"

    # An imported ledger never carries a consent choice; other preferences come in.
    class Notes:
        async def remember(self, *args, **kwargs):
            return "n1"

    export = {
        "format": daftar.FORMAT,
        "entries": [
            {"kind": "preference", "key": "training", "content": "on"},
            {"kind": "preference", "key": "language", "content": "Urdu"},
        ],
    }
    added = await daftar.import_entries(
        notes_store=Notes(), memory=memory, owner_id="amina", data=export
    )
    assert added["preference"] == 1 and added["skipped"] == 1
    kept = {row["key"]: row["value"] for row in await memory.get_chat_preferences("amina")}
    assert kept == {"learning": "off", "language": "Urdu"}


def test_daftar_edits_and_forgets_of_a_choice_leave_receipts(monkeypatch, tmp_path):
    from security import sakk

    # A non-admin's own memory lives under the data folder.
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))

    receipts = []
    monkeypatch.setattr(
        sakk,
        "record",
        lambda owner, kind, fields, display="": receipts.append((kind, fields)),
    )
    client, headers, _owner = _client_and_headers()
    edited = client.patch(
        "/api/daftar/preference:training", json={"content": "ON"}, headers=headers
    )
    assert edited.status_code == 200 and edited.json()["value"] == "on"
    assert (
        client.patch(
            "/api/daftar/preference:training", json={"content": "maybe"}, headers=headers
        ).status_code
        == 422
    )
    forgot = client.post(
        "/api/daftar/forget", json={"ids": ["preference:training"]}, headers=headers
    )
    assert forgot.json()["forgotten"]["preference"] == 1
    assert receipts == [
        ("consent", {"purpose": "training", "value": "on"}),
        ("consent", {"purpose": "training", "value": "default"}),
    ]
