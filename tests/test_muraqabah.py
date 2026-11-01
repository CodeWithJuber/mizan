"""Muraqabah: watchers that work for the user, quiet around salah, and learn when to interrupt."""

import random
from datetime import date, datetime, timedelta

import httpx
import pytest

from automation import muraqabah
from tadbir import fahm, waqt

KARACHI = muraqabah.known_city("Karachi")
FRIDAY = date(2026, 10, 30)


def at(day: date, clock: str, place=KARACHI) -> datetime:
    hours, minutes = (int(part) for part in clock.split(":"))
    return datetime(day.year, day.month, day.day, hours, minutes, tzinfo=place.zone)


@pytest.fixture
def store(tmp_path):
    return muraqabah.Store(str(tmp_path / "muraqabah.db"))


# ── Prayer times and quiet windows ───────────────────────────────────────


def test_prayer_times_are_in_order_and_the_asr_school_matters():
    times = muraqabah.prayer_times(KARACHI, FRIDAY)
    order = ["fajr", "sunrise", "dhuhr", "asr", "maghrib", "isha"]
    assert [times[name] for name in order] == sorted(times.values())
    assert (
        times["fajr"].strftime("%H:%M") == "05:21" and times["maghrib"].strftime("%H:%M") == "17:53"
    )
    shafii = muraqabah.Place("Karachi", KARACHI.lat, KARACHI.lon, KARACHI.tz, "KARACHI", False)
    assert muraqabah.prayer_times(shafii, FRIDAY)["asr"] < times["asr"]  # Hanafi Asr is later


def test_nothing_interrupts_salah_and_jumuah_is_longer():
    windows = {name: (start, end) for name, start, end in muraqabah.quiet_windows(KARACHI, FRIDAY)}
    assert "jumuah" in windows and "dhuhr" not in windows
    start, end = windows["jumuah"]
    assert end - start == timedelta(minutes=90)
    assert muraqabah.quiet_until(KARACHI, at(FRIDAY, "12:20")) == end
    assert muraqabah.quiet_until(KARACHI, at(FRIDAY, "10:00")) is None
    thursday = FRIDAY - timedelta(days=1)
    fajr = muraqabah.prayer_times(KARACHI, thursday)["fajr"]
    assert muraqabah.quiet_until(KARACHI, fajr + timedelta(minutes=10)) == fajr + timedelta(
        minutes=20
    )
    quiet_off = muraqabah.Place(**{**KARACHI.to_dict(), "quiet": False})
    assert muraqabah.quiet_until(quiet_off, at(FRIDAY, "12:20")) is None


def test_triggers_find_their_next_moment():
    now = at(FRIDAY, "06:00")
    daily = muraqabah.next_due({"kind": "daily", "time": "08:30"}, KARACHI, now)
    assert daily.astimezone(KARACHI.zone) == at(FRIDAY, "08:30")
    after_fajr = muraqabah.next_due(
        {"kind": "prayer", "prayer": "fajr", "offset": 20}, KARACHI, now
    )
    tomorrow_fajr = muraqabah.prayer_times(KARACHI, FRIDAY + timedelta(days=1))["fajr"]
    assert after_fajr == tomorrow_fajr + timedelta(minutes=20)
    white_days = muraqabah.validate_trigger({"kind": "hijri", "days": [13, 14, 15]})
    due = muraqabah.next_due(white_days, KARACHI, now).astimezone(KARACHI.zone)
    assert waqt.to_hijri(due.date()).day in (13, 14, 15)
    assert muraqabah.next_due({"kind": "prayer", "prayer": "isha", "offset": 0}, None, now) is None
    with pytest.raises(ValueError):
        muraqabah.validate_trigger({"kind": "prayer", "prayer": "lunch"})


def test_a_daily_watcher_without_a_time_is_due_at_eight_as_a_hijri_one_is():
    # A plan with {"kind": "daily"} and no time raised KeyError, which no
    # caller expects (31 Oct 2026: it stopped a Tadrib lesson collection).
    assert muraqabah.validate_trigger({"kind": "daily"}) == {"kind": "daily", "time": "08:00"}
    assert muraqabah.validate_trigger({"kind": "daily", "time": "7:5"})["time"] == "07:05"
    with pytest.raises(ValueError):
        muraqabah.validate_trigger({"kind": "daily", "time": "noon"})


def test_the_ayah_of_the_day_walks_the_whole_quran_in_order():
    first = date(2026, 1, 1)
    assert muraqabah.ayah_of_the_day(first) == (1, 1)
    assert muraqabah.ayah_of_the_day(first + timedelta(days=7)) == (2, 1)
    assert muraqabah.ayah_of_the_day(first + timedelta(days=6235)) == (114, 6)
    assert muraqabah.ayah_of_the_day(first + timedelta(days=6236)) == (1, 1)


# ── Judging when to interrupt ────────────────────────────────────────────


def notice(store, owner="amina", task="remind:drink water", priority="judge"):
    watcher = store.add(owner, "Water", {"kind": "daily", "time": "09:00"}, task, priority)
    store.notice(owner, watcher, "**Water**\n\ndrink water")
    return watcher


async def test_a_notice_waits_for_salah_then_arrives(store):
    store.set_place("amina", KARACHI)
    notice(store, priority="always")  # only salah decides here, not attention
    sent = []

    async def deliver(owner, text, meta):
        sent.append(text)

    during = at(FRIDAY, "12:30")
    assert (await muraqabah.deliver_waiting(store, during, deliver, random.Random(1)))["hold"] == 1
    assert sent == []
    later = at(FRIDAY, "13:20")
    assert (await muraqabah.deliver_waiting(store, later, deliver, random.Random(1)))[
        "deliver"
    ] == 1
    assert sent == ["**Water**\n\ndrink water"]


async def test_not_now_teaches_mizan_to_wait_for_the_digest(store):
    store.set_place("amina", KARACHI)
    watcher = notice(store)
    first = store.notices("amina")[0]
    for _ in range(12):
        store.feedback("amina", first["id"], useful=False)
    alpha, beta = store.posterior("amina", "daily")
    assert beta > alpha
    store.notice("amina", watcher, "again")
    verdicts = {
        muraqabah.decide(
            store, "amina", {"kind": "daily"}, "judge", at(FRIDAY, "10:00"), random.Random(seed)
        )[0]
        for seed in range(10)
    }
    assert verdicts == {"digest"}
    # A watcher marked "always" is delivered regardless (but still never during salah).
    assert (
        muraqabah.decide(store, "amina", {"kind": "daily"}, "always", at(FRIDAY, "10:00"))[0]
        == "deliver"
    )
    assert (
        muraqabah.decide(store, "amina", {"kind": "daily"}, "always", at(FRIDAY, "12:30"))[0]
        == "hold"
    )


async def test_the_daily_attention_budget_sends_the_rest_to_the_evening_digest(store):
    store.set_place(
        "amina", muraqabah.Place(**{**KARACHI.to_dict(), "budget": 1, "digest": "21:00"})
    )
    sent = []

    async def deliver(owner, text, meta):
        sent.append((text, meta))

    notice(store)
    notice(store)
    morning = at(FRIDAY, "10:00")
    counts = await muraqabah.deliver_waiting(store, morning, deliver, random.Random(3))
    assert counts["deliver"] == 1 and counts["digest"] == 1
    assert await muraqabah.send_digests(store, morning, deliver) == 0  # not yet evening
    assert await muraqabah.send_digests(store, at(FRIDAY, "21:05"), deliver) == 1
    assert sent[-1][0].startswith("**Muraqabah digest** (1)") and sent[-1][1] == {"digest": True}


async def test_a_due_watcher_fires_and_waits_out_the_salah_window(store):
    store.set_place("amina", KARACHI)
    watcher = store.add(
        "amina",
        "Witr",
        {"kind": "prayer", "prayer": "isha", "offset": 10},
        "remind:pray witr",
        "always",
    )
    due = datetime.fromisoformat(watcher["next_due"])
    sent = []

    async def deliver(owner, text, meta):
        sent.append(text)

    async def never(*args):
        raise AssertionError("a reminder needs no model and no page")

    # Isha + 10 min is inside Isha's quiet window: the reminder waits until it ends.
    counts = await muraqabah.tick(
        store, due + timedelta(minutes=1), run_task=never, deliver=deliver, read_page=never
    )
    assert counts["fired"] == 1 and counts["hold"] == 1 and sent == []
    assert datetime.fromisoformat(store.watcher("amina", watcher["id"])["next_due"]) > due
    await muraqabah.tick(
        store, due + timedelta(minutes=11), run_task=never, deliver=deliver, read_page=never
    )
    assert sent == ["**Witr**\n\npray witr"]


async def test_a_watched_page_reports_only_a_change(store):
    watcher = store.add(
        "amina", "Masjid page", {"kind": "page", "url": "https://masjid.example/times"}, ""
    )
    pages = iter(["Jumu'ah 1:15", "Jumu'ah 1:15", "Jumu'ah 1:30"])

    async def read(owner, url):
        return next(pages)

    for minutes in (0, 400, 800):
        await muraqabah.fire(
            store,
            store.watcher("amina", watcher["id"]),
            at(FRIDAY, "08:00") + timedelta(minutes=minutes),
            None,
            read,
        )
    texts = [item["text"] for item in store.notices("amina")]
    assert len(texts) == 1 and "Jumu'ah 1:30" in texts[0]


def test_watchers_are_private_and_bounded(store):
    store.add("amina", "Water", {"kind": "daily", "time": "09:00"}, "remind:drink water")
    assert store.watchers("bilal") == []
    with pytest.raises(ValueError, match="city"):
        store.add("bilal", "Witr", {"kind": "prayer", "prayer": "isha"}, "remind:witr")
    for index in range(muraqabah.MAX_WATCHERS - 1):
        store.add("amina", f"n{index}", {"kind": "daily", "time": "09:00"}, "remind:x")
    with pytest.raises(ValueError):
        store.add("amina", "one more", {"kind": "daily", "time": "09:00"}, "remind:x")


# ── From the chat ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "message,trigger,task",
    [
        (
            "Har subah Fajr ke baad ek ayat aur Hijri date bhejo",
            {"kind": "prayer", "prayer": "fajr", "offset": 20},
            "ayah_of_the_day",
        ),
        (
            "every day at 8:30 pm remind me to read Surah Al-Mulk",
            {"kind": "daily", "time": "20:30"},
            "remind:read Surah Al-Mulk",
        ),
        (
            "Isha ke 10 minute baad mujhe witr padhne ka yaad dilana",
            {"kind": "prayer", "prayer": "isha", "offset": 10},
            "remind:witr padhne",
        ),
        (
            "15 minutes before Maghrib remind me to break my fast with dates",
            {"kind": "prayer", "prayer": "maghrib", "offset": -15},
            "remind:break my fast with dates",
        ),
        (
            "har shaam 7 baje mujhe Hijri date bhejo",
            {"kind": "daily", "time": "19:00"},
            "Hijri date",
        ),
    ],
)
def test_standing_requests_are_understood_without_a_model(message, trigger, task):
    understood = fahm.understand(message)
    assert understood.intent == "watch"
    assert understood.entities["trigger"] == trigger and understood.entities["task"] == task


@pytest.mark.parametrize(
    "message",
    [
        "Fajr ka time kya hai?",
        "Send me the Quran 2:255",
        "Remind me to call mom",
        "aaj ki date kya hai",
    ],
)
def test_ordinary_requests_are_not_watchers(message):
    assert fahm.understand(message).intent != "watch"


@pytest.fixture
def agent(monkeypatch, tmp_path):
    from agents.specialized import create_agent
    from security.auth import TokenPayload, bind_principal, reset_principal
    from security.izn import IznPermission

    monkeypatch.setenv("MIZAN_ORCHESTRATION", "mizan")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "memory.db"))
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("agents.base.create_provider", lambda **kwargs: None)
    created = create_agent("general", izn=IznPermission())
    created.ai_client = None
    token = bind_principal(TokenPayload("amina", "Amina", ["user"], 9999999999, 0, "t"))
    yield created
    reset_principal(token)


async def test_a_watcher_is_created_from_chat_and_a_watcher_never_creates_one(agent):
    result = await agent.execute("Har subah Fajr ke baad ek ayat aur Hijri date bhejo, Karachi")
    assert result["task_verified"] and "Ayah of the day" in result["result"]
    store = muraqabah.default_store()
    assert store.place("amina").label == "Karachi"
    (watcher,) = store.watchers("amina")
    assert watcher["when"] == "20 min after Fajr every day"
    with muraqabah.running_watcher():
        await agent.execute("har roz 7 baje mujhe news bhejo")
    assert len(store.watchers("amina")) == 1


async def test_prayer_times_are_answered_for_the_users_place(agent):
    result = await agent.execute("Karachi me Fajr ka time kya hai?")
    assert result["task_verified"]
    assert "**Fajr: " in result["result"] and "Maghrib: " in result["result"]
    assert "Karachi" in result["result"] and "Hanafi" in result["result"]


async def test_the_watchers_api_is_per_user(monkeypatch, tmp_path):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    from api import main

    tokens = {
        name: main.auth.create_token(main.auth.create_user(f"watch-{name}", "pw", roles=["user"]))
        for name in ("amina", "bilal")
    }
    headers = {name: {"Authorization": f"Bearer {token}"} for name, token in tokens.items()}
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        place = await client.put(
            "/api/muraqabah/place", json={"city": "Lahore"}, headers=headers["amina"]
        )
        assert place.status_code == 200 and place.json()["method"] == "KARACHI"
        made = await client.post(
            "/api/muraqabah/watchers",
            json={"title": "Witr", "trigger": {"kind": "prayer", "prayer": "isha", "offset": 15},
                  "task": "remind:pray witr"},
            headers=headers["amina"],
        )  # fmt: skip
        assert made.status_code == 200, made.text
        overview = (await client.get("/api/muraqabah", headers=headers["amina"])).json()
        assert overview["today"]["times"]["isha"] and len(overview["watchers"]) == 1
        theirs = (await client.get("/api/muraqabah", headers=headers["bilal"])).json()
        assert theirs["watchers"] == [] and theirs["place"] is None
        gone = await client.delete(
            f"/api/muraqabah/watchers/{made.json()['id']}", headers=headers["bilal"]
        )
        assert gone.status_code == 404


async def test_a_city_named_in_the_message_is_geocoded_by_its_own_word(monkeypatch):
    looked_up = []

    async def find(name):
        looked_up.append(name)
        if name == "Sharjah":
            return muraqabah.Place("Sharjah city, AE", 25.3463, 55.4209, "Asia/Dubai")
        return None

    monkeypatch.setattr(muraqabah, "find_place", find)
    place = await muraqabah.place_named("Aaj Sharjah mein Maghrib kab hai?")
    assert place is not None and place.label.startswith("Sharjah")
    assert "kab" not in looked_up and "hai" not in looked_up  # ways of asking are not places
