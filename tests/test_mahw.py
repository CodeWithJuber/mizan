"""Mahw: deleting a chat or forgetting a note leaves no trace, and says so."""

import json
import sqlite3
import time

import pytest

from core.adaptive import AdaptiveStateStore
from memory import mahw
from memory.dhikr import DhikrMemorySystem

OWNER = "user-amina"
SECRET = "My daughter Maryam starts school at Al-Huda Academy next Tuesday morning"
KEPT = "Remind me what time Asr is in Hyderabad today please"


@pytest.fixture
def stores(tmp_path, monkeypatch):
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "chat.db"))
    chat = DhikrMemorySystem(str(tmp_path / "chat.db"))
    folder = mahw.private_dir(OWNER)
    folder.mkdir(parents=True)
    private = DhikrMemorySystem(str(folder / "memory.db"))
    return chat, private, folder


async def seed_chat(chat, private, folder, session_id, text):
    """A chat and every copy MIZAN makes of it while answering."""
    await chat.authorize_session(session_id, OWNER, create=True)
    first = await chat.save_message(session_id, "user", text)
    await chat.save_message(
        session_id, "assistant", f"Noted. {text[:30]} — may Allah make it easy."
    )
    await chat.save_session_summary(
        session_id,
        summary=f"The user said: {text}",
        covered_last_id=first,
        covered_count=2,
        method="test",
    )
    await private.remember(f"Asked in chat: {text}", source=f"chat:{session_id}:{first}")
    await private.save_task("agent", text, f"Answered about: {text}", True, 12.0)
    private.masalik.encode(f"{text} response Answered", importance=0.7)
    await private.store_hikmah("pattern", text[:200], "success")
    await private.knowledge_graph.add_entity(text[:100], "task", {"success": True})
    adaptive = AdaptiveStateStore(private.db_path)
    from tadbir import hifz, qasd

    qasd.learn(adaptive, OWNER, text, "converse", False)
    hifz.keep(adaptive, OWNER, text, "en", "print('ok')", "ok")
    from learner.ruh_learner import RuhLearner

    learner = RuhLearner(str(folder / "learner.sqlite3"))
    await learner.initialize()
    await learner.capture(text, "reply", "test", "m", {"session_id": session_id})
    with sqlite3.connect(folder / "debug_runs.db") as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS debug_runs (id TEXT PRIMARY KEY, created_at REAL, "
            "prompt TEXT, summary TEXT, data TEXT)"
        )
        conn.execute(
            "INSERT INTO debug_runs VALUES (?,?,?,?,?)", (session_id, time.time(), text, "", "{}")
        )
    from agents import session_state

    session_state.update(OWNER, session_id, "todos", [{"content": text, "status": "pending"}])
    return first


async def test_deleting_a_chat_removes_every_copy_and_finds_no_trace(stores):
    chat, private, folder = stores
    await seed_chat(chat, private, folder, "chat-secret", SECRET)
    await seed_chat(chat, private, folder, "chat-kept", KEPT)
    assert "maryam" in private.masalik.concepts

    receipt = await mahw.erase_chat(
        chat_db=chat.db_path,
        artifacts_db=chat.db_path,
        private=private,
        owner=OWNER,
        session_id="chat-secret",
    )

    removed = receipt["removed"]
    for store in (
        "chat messages",
        "chat summary",
        "notes",
        "task records",
        "wisdom",
        "knowledge graph",
        "learned from requests",
        "learner examples",
        "debug runs",
        "chat plan",
        "chat",
    ):
        assert removed.get(store), store
    assert receipt["checked"] > 0 and receipt["traces"] == 0
    assert SECRET not in json.dumps(receipt)  # the receipt keeps no content
    # The pathways are rebuilt from what is kept.
    assert "maryam" not in private.masalik.concepts
    assert any(word in private.masalik.concepts for word in ("asr", "hyderabad"))
    # The other chat is untouched.
    assert len(await chat.get_messages("chat-kept")) == 2
    assert await chat.get_messages("chat-secret") == []
    assert [r["kind"] for r in mahw.receipts(OWNER)] == ["chat"]


async def test_a_task_record_of_the_chat_goes_even_when_its_text_differs(stores):
    chat, private, folder = stores
    await seed_chat(chat, private, folder, "chat-secret", SECRET)
    # The agent records the request as it ran it (rewritten, or a refusal), and
    # long chats keep compaction facts; both carry the chat they came from.
    await private.save_task(
        "agent",
        f"[rewritten] {SECRET}",
        "Today's limit is used up",
        False,
        1.0,
        metadata={"session": "chat-secret"},
    )
    await private.save_task(
        "agent",
        "context_compaction_facts",
        json.dumps([SECRET]),
        True,
        0,
        metadata={"session": "chat-secret"},
    )
    await private.save_task("agent", "other chat", "kept", True, 1.0, metadata={"session": "x"})

    receipt = await mahw.erase_chat(
        chat_db=chat.db_path,
        artifacts_db=chat.db_path,
        private=private,
        owner=OWNER,
        session_id="chat-secret",
    )
    assert receipt["removed"]["task records"] == 3 and receipt["traces"] == 0
    left = [row["task"] for row in await private.get_task_history(limit=10)]
    assert left == ["other chat"]


async def test_a_copy_mahw_does_not_know_about_is_reported(stores):
    chat, private, folder = stores
    await seed_chat(chat, private, folder, "chat-secret", SECRET)
    # A copy outside the chat's provenance: Mahw does not remove it, so the
    # check must find it instead of claiming success.
    await private.remember(f"Pasted elsewhere: {SECRET}", source="manual")

    receipt = await mahw.erase_chat(
        chat_db=chat.db_path,
        artifacts_db=chat.db_path,
        private=private,
        owner=OWNER,
        session_id="chat-secret",
    )
    assert receipt["traces"] > 0 and "notes" in receipt["traces_by_store"]


async def test_the_same_words_in_a_kept_chat_are_not_traces(stores):
    chat, private, folder = stores
    await seed_chat(chat, private, folder, "chat-secret", SECRET)
    await chat.authorize_session("chat-other", OWNER, create=True)
    await chat.save_message("chat-other", "user", SECRET)  # said again elsewhere

    receipt = await mahw.erase_chat(
        chat_db=chat.db_path,
        artifacts_db=chat.db_path,
        private=private,
        owner=OWNER,
        session_id="chat-secret",
    )
    assert receipt["traces"] == 0
    assert len(await chat.get_messages("chat-other")) == 1


async def test_forgetting_a_note_removes_it_from_pathways_too(stores):
    _, private, _ = stores
    note = await private.remember("Allergic to peanuts and sesame, carry the EpiPen always")
    await private.remember("Prefers Urdu for duas")
    assert "epipen" in private.masalik.concepts

    receipt = await mahw.erase_notes(private=private, owner=OWNER, note_ids=[note])
    assert receipt["removed"]["notes"] == 1 and receipt["traces"] == 0
    assert "epipen" not in private.masalik.concepts
    assert "urdu" in private.masalik.concepts


@pytest.fixture
def chat_api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "chat.db"))
    monkeypatch.setenv("MIZAN_OWNED_DB", str(tmp_path / "owned.sqlite3"))
    import api.main as main
    from security.auth import MizanAuth

    chat = DhikrMemorySystem(str(tmp_path / "chat.db"))
    auth = MizanAuth("mahw-test-signing-key-" * 4, data_dir=str(tmp_path / "users"))
    amina = auth.create_user("amina", "test-password", roles=["user"])
    other = auth.create_user("other", "test-password", roles=["user"])
    monkeypatch.setattr(main, "auth", auth)
    monkeypatch.setattr(main, "memory", chat)
    monkeypatch.setattr(main, "_tadbir_coordinator", lambda: None)
    monkeypatch.setattr(main, "_private_memories", {})
    monkeypatch.setattr(main, "_stream_sessions", set())

    def headers(user):
        return {"Authorization": "Bearer " + auth.create_token(user)}

    return TestClient(main.app), main, chat, amina, headers(amina), headers(other)


def test_only_the_owner_deletes_a_chat_and_not_while_it_runs(chat_api):
    import asyncio

    client, main, chat, amina, mine, theirs = chat_api
    asyncio.run(chat.authorize_session("s-1", amina.id, create=True))
    asyncio.run(chat.save_message("s-1", "user", SECRET))

    assert client.delete("/api/chat/s-1", headers=theirs).status_code == 404
    main._stream_sessions.add((amina.id, "s-1"))
    assert client.delete("/api/chat/s-1", headers=mine).status_code == 409
    main._stream_sessions.clear()
    response = client.delete("/api/chat/s-1", headers=mine)
    assert response.status_code == 200, response.text
    assert response.json()["traces"] == 0 and response.json()["removed"]["chat messages"] == 1
    assert client.get("/api/chat/s-1", headers=mine).status_code == 404
    listed = client.get("/api/daftar/receipts", headers=mine).json()["receipts"]
    assert listed and listed[0]["kind"] == "chat"
