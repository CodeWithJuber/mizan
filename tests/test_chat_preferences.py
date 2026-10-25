"""Durable explicit preferences must outlive transcript recall and stay private."""

import pytest

from memory.dhikr import DhikrMemorySystem


@pytest.mark.asyncio
async def test_preferences_survive_restart_and_old_transcript_window(tmp_path):
    path = str(tmp_path / "memory.db")
    memory = DhikrMemorySystem(db_path=path)
    await memory.authorize_session("old-session", "alice", create=True)
    await memory.save_message("old-session", "user", "Please use salaam and Hinglish.")
    await memory.set_chat_preference("alice", "greeting", "Assalamu alaikum")
    await memory.set_chat_preference("alice", "language", "Hinglish")
    await memory.set_chat_preference("alice", "avoid_greetings", "Namaste")
    await memory.authorize_session("busy-session", "alice", create=True)
    for index in range(205):
        await memory.save_message("busy-session", "user", f"Unrelated task {index}")

    restarted = DhikrMemorySystem(db_path=path)
    recalled = await restarted.recall_conversations(
        "alice", "greeting", exclude_session="new-session"
    )
    assert all("salaam" not in row["content"] for row in recalled)
    preferences = await restarted.get_chat_preferences("alice")
    assert {row["key"]: row["value"] for row in preferences} == {
        "greeting": "Assalamu alaikum",
        "language": "Hinglish",
        "avoid_greetings": "Namaste",
    }
    assert all(row["source"] == "explicit_user_preference" for row in preferences)
    assert all(row["updated_at"] for row in preferences)
    assert await restarted.get_chat_preferences("bob") == []


@pytest.mark.asyncio
async def test_preference_corrections_and_deletion_are_owner_scoped(tmp_path):
    memory = DhikrMemorySystem(db_path=str(tmp_path / "memory.db"))
    await memory.set_chat_preference("alice", "language", "Hinglish")
    await memory.set_chat_preference("bob", "language", "English")
    await memory.set_chat_preference("alice", "language", "Urdu")
    assert [row["value"] for row in await memory.get_chat_preferences("alice")] == ["Urdu"]
    assert await memory.delete_chat_preference("alice", "language") is True
    assert await memory.delete_chat_preference("alice", "language") is False
    assert await memory.get_chat_preferences("alice") == []
    assert [row["value"] for row in await memory.get_chat_preferences("bob")] == ["English"]


@pytest.mark.asyncio
async def test_global_settings_and_legacy_chat_cannot_become_user_preferences(tmp_path):
    memory = DhikrMemorySystem(db_path=str(tmp_path / "memory.db"))
    await memory.set_preference("language", "global value")
    await memory.save_message("legacy", "user", "Always greet with salaam.")
    await memory.save_message("legacy", "assistant", "User prefers invented greeting.")
    assert await memory.get_chat_preferences("alice") == []
    assert await memory.get_chat_preferences("admin") == []
    await memory.set_chat_preference("alice", "language", "Hinglish")
    assert await memory.get_preference("language") == "global value"


@pytest.mark.asyncio
async def test_preference_input_is_bounded_and_requires_owner(tmp_path):
    memory = DhikrMemorySystem(db_path=str(tmp_path / "memory.db"))
    with pytest.raises(ValueError, match="owner"):
        await memory.get_chat_preferences("")
    with pytest.raises(ValueError, match="Unsupported"):
        await memory.set_chat_preference("alice", "api_key", "must not store this")
    with pytest.raises(ValueError, match="empty"):
        await memory.set_chat_preference("alice", "language", " ")
    with pytest.raises(ValueError, match="120"):
        await memory.set_chat_preference("alice", "language", "a" * 121)
