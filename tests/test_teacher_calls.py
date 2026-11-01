"""The teacher-call share: how often MIZAN answered with no hosted-model call
(usage.lisan per answer, /api/tadbir/teacher-calls over saved answers)."""

import sqlite3

import httpx

from memory.dhikr import DhikrMemorySystem


async def _answer(store: DhikrMemorySystem, session: str, calls: int, family: str) -> None:
    lisan = {"calls": calls, "zero_call": calls == 0, "family": family, "language": "ur",
             "tasks": {"answer": calls} if calls else {}, "verified": calls == 0}  # fmt: skip
    await store.save_message(
        session, "user", "secret question words", metadata={"status": "complete"}
    )
    await store.save_message(
        session,
        "assistant",
        "secret answer words",
        metadata={"status": "complete", "usage": {"lisan": lisan}},
    )


async def test_each_user_sees_their_own_share_and_admins_see_everyone(monkeypatch, tmp_path):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    from api import main

    store = DhikrMemorySystem(db_path=str(tmp_path / "memory.db"))
    monkeypatch.setattr(main, "memory", store)
    users = {
        name: main.auth.create_user(f"teacher-{name}", "pw", roles=roles)
        for name, roles in (("amina", ["user"]), ("bilal", ["user"]), ("owner", ["admin"]))
    }
    headers = {
        name: {"Authorization": f"Bearer {main.auth.create_token(user)}"}
        for name, user in users.items()
    }
    await store.list_sessions(owner_id=users["amina"].id)  # creates the session table
    with sqlite3.connect(tmp_path / "memory.db") as conn:
        conn.executemany(
            "INSERT INTO chat_sessions (session_id, owner_id) VALUES (?, ?)",
            [("chat-a", users["amina"].id), ("chat-b", users["bilal"].id)],
        )
    await _answer(store, "chat-a", 0, "compute")
    await _answer(store, "chat-a", 0, "quran")
    await _answer(store, "chat-a", 1, "converse")
    await _answer(store, "chat-b", 2, "converse")

    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        mine = await client.get("/api/tadbir/teacher-calls", headers=headers["amina"])
        assert mine.status_code == 200, mine.text
        body = mine.json()
        assert (body["requests"], body["zero_call"], body["scope"]) == (3, 2, "me")
        assert body["zero_call_share"] == round(2 / 3, 4)
        assert {f["family"] for f in body["by_family"]} == {"compute", "quran", "converse"}
        assert "secret" not in mine.text  # counts and shares only, never content

        refused = await client.get("/api/tadbir/teacher-calls?scope=all", headers=headers["bilal"])
        assert refused.status_code == 403

        everyone = await client.get(
            "/api/tadbir/teacher-calls?scope=all&days=7", headers=headers["owner"]
        )
        assert everyone.status_code == 200
        assert (everyone.json()["requests"], everyone.json()["zero_call"]) == (4, 2)
        assert everyone.json()["lisan_tasks"] == {"answer": 3}

        assert (await client.get("/api/tadbir/teacher-calls")).status_code == 401


async def test_ruh_data_stats_never_list_scripture_as_training_data(monkeypatch, tmp_path):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    from api import main

    admin = main.auth.create_user("ruh-stats-owner", "pw", roles=["admin"])
    headers = {"Authorization": f"Bearer {main.auth.create_token(admin)}"}
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        stats = await client.get("/api/ruh/data-stats", headers=headers)
    assert stats.status_code == 200, stats.text
    listed = {source["name"] for source in stats.json()["sources"]}
    assert "arabic_wiki" in listed
    assert not listed & {"quran", "hadith"}
    assert "never a training target" in stats.json()["scripture_policy"]
