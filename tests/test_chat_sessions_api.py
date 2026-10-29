"""Chat titles, rename and search: what the chat sidebar lists.

``PATCH /api/chat/{session_id}`` names one of the caller's chats and
``GET /api/chat/sessions/list?q=`` finds chats by title or first message.
"""

import asyncio
import sqlite3

import pytest

from memory.dhikr import DhikrMemorySystem


@pytest.fixture
def sidebar(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "chat.db"))
    monkeypatch.setenv("MIZAN_OWNED_DB", str(tmp_path / "owned.sqlite3"))
    import api.main as main
    from security.auth import MizanAuth

    chat = DhikrMemorySystem(str(tmp_path / "chat.db"))
    auth = MizanAuth("sidebar-test-signing-key-" * 4, data_dir=str(tmp_path / "users"))
    amina = auth.create_user("amina", "test-password", roles=["user"])
    other = auth.create_user("other", "test-password", roles=["user"])
    admin = auth.create_user("admin", "test-password", roles=["admin"])
    monkeypatch.setattr(main, "auth", auth)
    monkeypatch.setattr(main, "memory", chat)

    def headers(user):
        return {"Authorization": "Bearer " + auth.create_token(user)}

    users = {"amina": amina, "other": other, "admin": admin}
    tokens = {name: headers(user) for name, user in users.items()}
    return TestClient(main.app), chat, users, tokens


def seed(chat, owner, session_id, first, *more):
    asyncio.run(chat.authorize_session(session_id, owner.id, create=True))
    asyncio.run(chat.save_message(session_id, "user", first))
    for text in more:
        asyncio.run(chat.save_message(session_id, "assistant", text))


def listing(client, token, **params):
    response = client.get("/api/chat/sessions/list", params=params, headers=token)
    assert response.status_code == 200, response.text
    return response.json()


def ids(body):
    return [item["session_id"] for item in body["sessions"]]


# ── Rename ───────────────────────────────────────────────────────────────


def test_renaming_my_chat_lists_it_with_its_title(sidebar):
    client, chat, users, tokens = sidebar
    seed(chat, users["amina"], "s-1", "When should we leave for Hajj?")
    seed(chat, users["amina"], "s-2", "Unnamed chat")

    response = client.patch(
        "/api/chat/s-1", json={"title": "  Hajj plans  "}, headers=tokens["amina"]
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"session_id": "s-1", "title": "Hajj plans"}

    def titles():
        body = listing(client, tokens["amina"])
        assert body["q"] is None
        return {item["session_id"]: item["title"] for item in body["sessions"]}

    assert titles() == {"s-1": "Hajj plans", "s-2": None}
    # Renaming again replaces the title; the first message is still listed.
    client.patch("/api/chat/s-1", json={"title": "Hajj 2027"}, headers=tokens["amina"])
    assert titles() == {"s-1": "Hajj 2027", "s-2": None}
    first = listing(client, tokens["amina"])["sessions"][1]
    assert first["first_message"] == "When should we leave for Hajj?"


def test_a_title_may_be_120_characters_in_any_script(sidebar):
    client, chat, users, tokens = sidebar
    seed(chat, users["amina"], "s-1", "first")
    for title in ("ح" * 120, "خطة الحج", "می‌خواهم", "🕋 Umrah"):
        response = client.patch("/api/chat/s-1", json={"title": title}, headers=tokens["amina"])
        assert response.status_code == 200, (title, response.text)
        assert response.json()["title"] == title


def test_someone_elses_chat_cannot_be_renamed(sidebar):
    client, chat, users, tokens = sidebar
    seed(chat, users["amina"], "s-1", "My private chat")

    response = client.patch("/api/chat/s-1", json={"title": "Mine now"}, headers=tokens["other"])
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    # A chat that does not exist is not created by naming it.
    missing = client.patch("/api/chat/nope", json={"title": "x"}, headers=tokens["amina"])
    assert missing.status_code == 404
    assert asyncio.run(chat.session_owner("nope")) is None
    # Nothing changed for the owner, and the other user lists nothing.
    assert listing(client, tokens["amina"])["sessions"][0]["title"] is None
    assert listing(client, tokens["other"])["sessions"] == []


def test_rename_needs_a_signed_in_owner_and_a_valid_session_id(sidebar):
    client, chat, users, tokens = sidebar
    seed(chat, users["amina"], "s-1", "first")
    assert client.patch("/api/chat/s-1", json={"title": "x"}).status_code == 401
    too_long = client.patch("/api/chat/" + "a" * 101, json={"title": "x"}, headers=tokens["amina"])
    assert too_long.status_code == 400  # as for DELETE /api/chat/{session_id}


@pytest.mark.parametrize(
    "body",
    [
        {"title": ""},
        {"title": "   "},
        {"title": "x" * 121},
        {"title": "  " + "x" * 121 + "  "},
        {"title": "two\nlines"},
        {"title": "tab\there"},
        {"title": "nul\x00byte"},
        {"title": "del\x7f"},
        {"title": "c1\x85control"},
        {"title": None},
        {"title": 7},
        {},
    ],
)
def test_invalid_titles_are_refused(sidebar, body):
    client, chat, users, tokens = sidebar
    seed(chat, users["amina"], "s-1", "first")
    response = client.patch("/api/chat/s-1", json=body, headers=tokens["amina"])
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "invalid_request"
    assert listing(client, tokens["amina"])["sessions"][0]["title"] is None


def test_a_lone_surrogate_is_refused(sidebar):
    client, chat, users, tokens = sidebar
    seed(chat, users["amina"], "s-1", "first")
    response = client.patch(
        "/api/chat/s-1",
        content=b'{"title": "a\\ud800b"}',
        headers={**tokens["amina"], "Content-Type": "application/json"},
    )
    assert response.status_code == 422


def test_a_legacy_chat_is_renamed_only_by_whoever_may_adopt_it(sidebar):
    client, chat, users, tokens = sidebar
    # Messages from before chats had owners: no chat_sessions row.
    asyncio.run(chat.save_message("legacy", "user", "an old conversation"))

    refused = client.patch("/api/chat/legacy", json={"title": "x"}, headers=tokens["amina"])
    assert refused.status_code == 404
    assert asyncio.run(chat.session_owner("legacy")) is None
    # An administrator adopts legacy chats (as when opening one), so may name it.
    named = client.patch("/api/chat/legacy", json={"title": "Old one"}, headers=tokens["admin"])
    assert named.status_code == 200, named.text
    assert asyncio.run(chat.session_owner("legacy")) == users["admin"].id
    assert listing(client, tokens["admin"])["sessions"][0]["title"] == "Old one"


# ── Search ───────────────────────────────────────────────────────────────


def test_search_finds_chats_by_title_or_first_message_in_any_case(sidebar):
    client, chat, users, tokens = sidebar
    seed(chat, users["amina"], "titled", "when do we leave", "In Dhul Hijjah.")
    seed(chat, users["amina"], "biryani", "Recipe for BIRYANI please", "Here it is.")
    seed(chat, users["amina"], "later", "unrelated question", "A reply about hajj.")
    seed(chat, users["amina"], "accents", "Notes on ÉTÉ")
    seed(chat, users["other"], "theirs", "My hajj plans too")
    client.patch("/api/chat/titled", json={"title": "Hajj Plans"}, headers=tokens["amina"])

    def found(q):
        return ids(listing(client, tokens["amina"], q=q))

    assert found("hajj") == ["titled"]  # not the assistant's words, not another user's chat
    assert found("PLANS") == ["titled"]
    assert found("biryani") == ["biryani"]
    assert found("recipe FOR") == ["biryani"]
    assert found("  biryani  ") == ["biryani"]  # trimmed
    assert found("été") == ["accents"]  # folded beyond ASCII
    assert found("nothing like this") == []
    assert listing(client, tokens["amina"], q="  biryani ")["q"] == "biryani"
    # A blank q lists every chat.
    assert len(found("   ")) == 4
    assert len(found("")) == 4


def test_like_wildcards_in_q_are_plain_characters(sidebar):
    client, chat, users, tokens = sidebar
    seed(chat, users["amina"], "percent", "We are 100% ready")
    seed(chat, users["amina"], "underscore", "rename my_file.py")
    seed(chat, users["amina"], "backslash", "path C:\\Users\\amina")
    seed(chat, users["amina"], "plain", "nothing special here at all")

    def found(q):
        return sorted(ids(listing(client, tokens["amina"], q=q)))

    assert found("%") == ["percent"]
    assert found("_") == ["underscore"]
    assert found("\\") == ["backslash"]
    assert found("100%") == ["percent"]
    assert found("my_f") == ["underscore"]
    assert found("e%y") == []  # as a wildcard it would match "We are 100% ready"
    assert found("g_s") == []  # as a wildcard it would match "nothing special"
    assert found("my_") == ["underscore"]


def test_search_pages_like_the_full_list(sidebar):
    client, chat, users, tokens = sidebar
    matching = []
    for n in range(5):
        seed(chat, users["amina"], f"quran-{n}", f"Question {n} about the Quran")
        matching.append(f"quran-{n}")
        seed(chat, users["amina"], f"other-{n}", f"Question {n} about cooking")
    newest_first = list(reversed(matching))

    seen, offset, pages = [], 0, 0
    while offset is not None:
        body = listing(client, tokens["amina"], q="quran", limit=2, offset=offset)
        assert body["limit"] == 2 and body["offset"] == offset
        seen += ids(body)
        offset = body["next_offset"]
        pages += 1
    assert seen == newest_first and pages == 3
    # The full list still pages as before.
    first = listing(client, tokens["amina"], limit=4)
    assert len(first["sessions"]) == 4 and first["next_offset"] == 4


def test_a_search_longer_than_200_characters_is_refused(sidebar):
    client, chat, users, tokens = sidebar
    response = client.get(
        "/api/chat/sessions/list", params={"q": "x" * 201}, headers=tokens["amina"]
    )
    assert response.status_code == 422
    assert listing(client, tokens["amina"], q="x" * 200)["sessions"] == []


# ── Storage ──────────────────────────────────────────────────────────────


async def test_an_existing_database_gains_the_title_column(tmp_path):
    path = tmp_path / "old.db"
    chat = DhikrMemorySystem(str(path))
    with sqlite3.connect(path) as conn:  # the table as production has it today
        conn.execute(
            "CREATE TABLE chat_sessions (session_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL)"
        )
        conn.execute("INSERT INTO chat_sessions VALUES ('old', 'u1')")
    await chat.save_message("old", "user", "kept from before")

    assert (await chat.list_sessions(owner_id="u1"))[0]["title"] is None
    assert await chat.authorize_session("new", "u1", create=True)  # inserts still work
    assert await chat.rename_session("u1", "old", "Named later")
    with sqlite3.connect(path) as conn:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(chat_sessions)")]
        rows = conn.execute("SELECT * FROM chat_sessions ORDER BY session_id").fetchall()
    assert columns == ["session_id", "owner_id", "title"]
    assert rows == [("new", "u1", None), ("old", "u1", "Named later")]
    # Opening it again does not add the column twice.
    again = DhikrMemorySystem(str(path))
    assert (await again.list_sessions(owner_id="u1", q="named"))[0]["session_id"] == "old"


async def test_rename_session_is_owner_scoped(tmp_path):
    chat = DhikrMemorySystem(str(tmp_path / "chat.db"))
    await chat.authorize_session("s", "u1", create=True)
    await chat.save_message("s", "user", "hello")
    await chat.save_message("legacy", "user", "no owner row")

    assert not await chat.rename_session("u2", "s", "taken")
    assert not await chat.rename_session("u1", "missing", "x")
    assert not await chat.rename_session("u1", "legacy", "x")
    assert await chat.rename_session("u1", "legacy", "adopted", adopt_legacy=True)
    assert await chat.session_owner("legacy") == "u1"
    assert await chat.rename_session("u1", "s", "  mine ")
    titles = {row["session_id"]: row["title"] for row in await chat.list_sessions(owner_id="u1")}
    assert titles == {"s": "mine", "legacy": "adopted"}
    assert await chat.rename_session("u1", "s", None)  # clears it
    assert (await chat.list_sessions(owner_id="u1", q="hello"))[0]["title"] is None
    with pytest.raises(ValueError):
        await chat.list_sessions(owner_id="u1", q="x" * 201)
