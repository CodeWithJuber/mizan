"""Tadhkir fitted on MIZAN's own memory log: every review logged without words,
erased with its memory, and fitted parameters adopted only on held-out evidence."""

import importlib.util
from datetime import UTC, datetime, timedelta

import pytest

from core.adaptive import AdaptiveStateStore
from memory import daftar, mahw, stateless, tadhkir
from memory.dhikr import DhikrMemorySystem
from tadbir import nawm

OWNER = "user-amina"
GOOD = int(tadhkir.GOOD)


def logged(memory) -> list[tuple]:
    conn = memory._get_conn()
    try:
        return conn.execute(
            "SELECT memory_id, agent_id, rating, kind, reviewed FROM memory_reviews ORDER BY id"
        ).fetchall()
    finally:
        memory._release_conn(conn)


def insert(memory, rows) -> None:
    conn = memory._get_conn()
    try:
        conn.executemany(
            "INSERT INTO memory_reviews (memory_id, agent_id, rating, kind, reviewed) "
            "VALUES (?, '', ?, ?, ?)",
            rows,
        )
        conn.commit()
    finally:
        memory._release_conn(conn)


def adopt(memory, parameters, when: datetime) -> None:
    """A fit in use, as a night that found the evidence leaves it."""
    conn = memory._get_conn()
    try:
        record = tadhkir._record(conn)
        record.update(
            parameters=tuple(parameters),
            fitted=True,
            evaluation={"date": when.isoformat(), "adopted": True},
            tests=1,
        )
        tadhkir._save(conn, record)
    finally:
        memory._release_conn(conn)


def in_use(memory) -> tuple[float, ...]:
    conn = memory._get_conn()
    try:
        return tadhkir.in_use(conn)
    finally:
        memory._release_conn(conn)


# ── the log ──────────────────────────────────────────────────────────────


async def test_every_review_a_memory_gets_is_logged_without_its_words(tmp_path):
    memory = DhikrMemorySystem(str(tmp_path / "memory.db"))
    first = await memory.remember("My son's name is Yusuf.", importance=0.5, agent_id="a1")
    assert await memory.remember("my son's name is Yusuf.", importance=0.5, agent_id="a1") == first
    assert [item.id for item in await memory.recall("Yusuf")] == [first]  # outside a run: a use
    rows = logged(memory)
    assert [row[:4] for row in rows] == [
        (first, "a1", GOOD, "learn"),
        (first, "a1", GOOD, "repeat"),  # said again while held
        (first, "a1", GOOD, "use"),
    ]
    assert all(datetime.fromisoformat(row[4]).tzinfo for row in rows)
    conn = memory._get_conn()
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(memory_reviews)")}
    finally:
        memory._release_conn(conn)
    assert columns == {"id", "memory_id", "agent_id", "rating", "kind", "reviewed"}
    assert "Yusuf" not in repr(rows)


async def test_in_a_run_only_the_used_memory_is_logged(tmp_path):
    from memory.dhikr import defer_reviews, settle_reviews

    memory = DhikrMemorySystem(str(tmp_path / "memory.db"))
    son = await memory.remember("My son's name is Yusuf.", importance=0.5)
    city = await memory.remember("My son Yusuf studies in Hyderabad.", importance=0.5)
    token = defer_reviews()
    await memory.recall("Yusuf", limit=5)
    assert settle_reviews(token, "Yusuf is studying in Hyderabad this year.") == 1
    uses = [row[0] for row in logged(memory) if row[3] == "use"]
    assert uses == [city] and son not in uses


async def test_a_stateless_run_or_learning_off_logs_nothing(tmp_path):
    memory = DhikrMemorySystem(str(tmp_path / "memory.db"))
    with stateless.bind():
        await memory.remember("Prefers Urdu for duas", importance=0.5)
        await memory.recall("Urdu")
    with stateless.no_learning("learning: off"):
        await memory.remember("Prefers Urdu for duas", importance=0.5)  # said again
        await memory.recall("duas")
    assert logged(memory) == []


# ── erased with its memory ───────────────────────────────────────────────


async def test_a_memory_deleted_anywhere_takes_its_reviews(tmp_path):
    memory = DhikrMemorySystem(str(tmp_path / "memory.db"))
    gone = await memory.remember("Allergic to peanuts and sesame", importance=0.5)
    kept = await memory.remember("Prefers Urdu for duas", importance=0.5)
    await memory.recall("peanuts")
    assert daftar.forget_note(memory, gone)
    assert {row[0] for row in logged(memory)} == {kept}


@pytest.fixture
def private(tmp_path, monkeypatch):
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path / "data"))
    folder = mahw.private_dir(OWNER)
    folder.mkdir(parents=True)
    return DhikrMemorySystem(str(folder / "memory.db"))


async def test_forgetting_a_note_erases_its_reviews_and_a_fit_made_from_them(private):
    note = await private.remember("Allergic to peanuts and sesame", importance=0.5)
    kept = await private.remember("Prefers Urdu for duas", importance=0.5)
    await private.recall("peanuts")
    adopt(private, tadhkir.FASTER, datetime.now(UTC) + timedelta(seconds=1))
    assert in_use(private) == tadhkir.FASTER

    receipt = await mahw.erase_notes(private=private, owner=OWNER, note_ids=[note])
    assert receipt["removed"]["notes"] == 1
    assert receipt["removed"]["memory reviews"] == 2  # written, then used
    assert receipt["removed"]["memory strength fit"] == 1
    assert {row[0] for row in logged(private)} == {kept}
    assert in_use(private) == tadhkir.DEFAULTS  # fitted again on what is kept


async def test_deleting_a_chat_erases_the_reviews_of_its_notes(private, tmp_path):
    chat = DhikrMemorySystem(str(tmp_path / "chat.db"))
    await chat.authorize_session("chat-1", OWNER, create=True)
    first = await chat.save_message("chat-1", "user", "Remember: my daughter Maryam is 7")
    note = await private.remember("My daughter Maryam is 7", source=f"chat:chat-1:{first}")
    other = await private.remember("Prefers Urdu for duas")
    await private.recall("Maryam")
    receipt = await mahw.erase_chat(
        chat_db=chat.db_path,
        artifacts_db=chat.db_path,
        private=private,
        owner=OWNER,
        session_id="chat-1",
    )
    assert receipt["removed"]["memory reviews"] == 2
    assert "memory strength fit" not in receipt["removed"]  # none was in use
    assert note not in {row[0] for row in logged(private)} and other in {
        row[0] for row in logged(private)
    }


def test_a_fit_adopted_before_the_erased_reviews_stays(tmp_path):
    memory = DhikrMemorySystem(str(tmp_path / "memory.db"))
    adopted = datetime(2026, 10, 1, tzinfo=UTC)
    adopt(memory, tadhkir.FASTER, adopted)
    conn = memory._get_conn()
    try:
        assert tadhkir.unfit(conn, (adopted + timedelta(days=1)).isoformat()) == 0
        assert tadhkir.in_use(conn) == tadhkir.FASTER
        assert tadhkir.unfit(conn, (adopted - timedelta(days=1)).isoformat()) == 1
        assert tadhkir.in_use(conn) == tadhkir.DEFAULTS
    finally:
        memory._release_conn(conn)


# ── fitting, and the guard ───────────────────────────────────────────────


def test_each_test_on_a_log_spends_alpha_so_all_together_stay_below_it():
    assert tadhkir.needed(1) == pytest.approx(40.0)
    assert sum(1 / tadhkir.needed(test) for test in range(1, 10_001)) < tadhkir.ALPHA
    assert tadhkir.needed(365) < 3e6  # a nightly test is not shut out after a year


def test_the_split_is_in_time_and_only_whole_day_reviews_are_scored():
    rows = tadhkir.simulate(tadhkir.DEFAULTS, memories=40, seed=1)
    found = tadhkir.histories((m, g, k, t) for m, g, k, t in rows)
    cut = tadhkir.split(found)
    assert cut is not None
    earlier = tadhkir.losses(found, tadhkir.DEFAULTS, until=cut)
    later = tadhkir.losses(found, tadhkir.DEFAULTS, since=cut)
    assert earlier and later and abs(len(earlier) - len(later)) <= 1
    # A history that does not begin with its first writing cannot be replayed.
    assert tadhkir.histories([("x", GOOD, "use", "2026-01-02T00:00:00+00:00")]) == {}


def test_a_fit_on_another_persons_log_is_adopted_and_recovers_their_forgetting():
    found = tadhkir.measure(tadhkir.FASTER, seed=0, optimizer=False, memories=150)
    assert found["status"] == "adopted" and found["method"] == "light fit"
    loss = found["log_loss"]
    assert loss["truth"] < loss["fitted"] < loss["defaults"]
    # Most of the gap between the defaults and the truth is closed.
    assert loss["defaults"] - loss["fitted"] > 0.5 * (loss["defaults"] - loss["truth"])
    assert found["e_value"] >= found["needed"] == pytest.approx(40.0)
    fitted = found["parameters"]
    # Toward the person: shorter first holds, a steeper curve.
    assert fitted[2] < tadhkir.DEFAULTS[2] and fitted[20] > tadhkir.DEFAULTS[20]


def test_a_log_the_defaults_explain_is_not_refitted():
    # Chance may lower the held-out log-loss a little (here it does); that is
    # not the margin the e-value asks for, so the defaults stay.
    found = tadhkir.measure(tadhkir.DEFAULTS, seed=0, optimizer=False, memories=150)
    assert found["status"] == "kept" and found["e_value"] < found["needed"]


@pytest.mark.skipif(
    not all(importlib.util.find_spec(name) for name in ("torch", "pandas", "tqdm")),
    reason="FSRS's optimizer is not installed (fsrs[optimizer])",
)
def test_fsrs_optimizer_fits_all_parameters_when_installed():
    found = tadhkir.measure(tadhkir.FASTER, seed=0, memories=150)
    assert found["method"] == "fsrs optimizer" and found["optimizer"] == "used"
    assert found["status"] == "adopted"
    assert found["log_loss"]["fitted"] < found["log_loss"]["defaults"]


def test_without_the_optimizer_the_light_fit_is_used(monkeypatch):
    monkeypatch.setattr(tadhkir, "optimizer_fit", lambda *a, **k: (None, "not installed", 0.0))
    found = tadhkir.measure(tadhkir.FASTER, seed=0, memories=150)
    assert found["method"] == "light fit" and found["optimizer"] == "not installed"


async def test_adopted_parameters_review_later_and_a_kept_strength_stays_valid(tmp_path):
    memory = DhikrMemorySystem(str(tmp_path / "memory.db"))
    mem_id = await memory.remember("My city is Hyderabad", importance=0.5)
    then = datetime.now(UTC) - timedelta(days=10)
    held = tadhkir.learn(0.5, then)  # its strength under the defaults
    conn = memory._get_conn()
    try:
        conn.execute(
            "UPDATE memories SET stability = ?, difficulty = ?, last_review = ? WHERE id = ?",
            (held["stability"], held["difficulty"], held["last_review"], mem_id),
        )
        conn.commit()
    finally:
        memory._release_conn(conn)
    insert(memory, tadhkir.simulate(tadhkir.FASTER, memories=150, seed=0))
    conn = memory._get_conn()
    try:
        found = tadhkir.refit(conn, optimizer=False)
        assert found["status"] == "adopted"
        fitted = tadhkir.in_use(conn)
        assert fitted != tadhkir.DEFAULTS
        assert tadhkir.refit(conn, optimizer=False)["status"] == "unchanged"
    finally:
        memory._release_conn(conn)

    [recalled] = await memory.recall("Hyderabad")
    expected = tadhkir.review(held, tadhkir.GOOD, parameters=fitted)
    assert recalled.strength["stability"] == pytest.approx(expected["stability"], rel=1e-3)
    by_default = tadhkir.review(held, tadhkir.GOOD)
    assert recalled.strength["stability"] != pytest.approx(by_default["stability"], rel=1e-3)


async def test_the_night_fits_the_persons_log_within_their_choice(tmp_path, monkeypatch):
    monkeypatch.setattr(tadhkir, "optimizer_fit", lambda *a, **k: (None, "not installed", 0.0))
    memory = DhikrMemorySystem(str(tmp_path / "memory.db"))
    insert(memory, tadhkir.simulate(tadhkir.FASTER, memories=150, seed=0))
    store = AdaptiveStateStore(memory.db_path)  # an agent's store shares its memory's file
    with stateless.no_learning("learning: off"):
        assert (await nawm.night(store, "u1"))["fitted"] == 0
    assert (await nawm.night(store, "u1", idle=lambda: False))["fitted"] == 0
    assert in_use(memory) == tadhkir.DEFAULTS
    assert (await nawm.night(store, "u1"))["fitted"] == 1
    assert in_use(memory) != tadhkir.DEFAULTS
    # A store with no memories beside it is left alone.
    other = AdaptiveStateStore(str(tmp_path / "adaptive.db"))
    assert (await tadhkir.rest(other.db_path))["status"] == "no memories"


# ── the endpoint ─────────────────────────────────────────────────────────


@pytest.fixture
def api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "chat.db"))
    monkeypatch.setenv("MIZAN_OWNED_DB", str(tmp_path / "owned.sqlite3"))
    import api.main as main
    from security.auth import MizanAuth

    shared = DhikrMemorySystem(str(tmp_path / "memory.db"))
    auth = MizanAuth("tadhkir-fit-signing-key-" * 4, data_dir=str(tmp_path / "users"))
    admin = auth.create_user("admin", "test-password", roles=["admin"])
    user = auth.create_user("amina", "test-password", roles=["user"])
    monkeypatch.setattr(main, "auth", auth)
    monkeypatch.setattr(main, "memory", shared)
    monkeypatch.setattr(main, "_tadbir_coordinator", lambda: None)
    monkeypatch.setattr(main, "_private_memories", {})

    def headers(account):
        return {"Authorization": "Bearer " + auth.create_token(account)}

    return TestClient(main.app), shared, headers(admin), headers(user)


def test_only_an_administrator_reads_the_parameters_in_use(api):
    client, shared, admin, user = api
    response = client.get("/api/memory/tadhkir", headers=admin)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["fitted"] is False and body["evaluation"] is None
    assert body["parameters"] == pytest.approx(list(tadhkir.DEFAULTS))
    assert client.get("/api/memory/tadhkir", headers=user).status_code == 403
    assert client.get("/api/memory/tadhkir").status_code == 401

    adopt(shared, tadhkir.FASTER, datetime.now(UTC))
    body = client.get("/api/memory/tadhkir", headers=admin).json()
    assert body["fitted"] is True and body["evaluation"]["adopted"] is True
    assert body["parameters"] == pytest.approx(list(tadhkir.FASTER))
