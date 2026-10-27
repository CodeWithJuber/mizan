"""Muraqabah (مراقبة): watchers that work for the user, and judge when to interrupt.

A watcher pairs a trigger with a task:

- **triggers**: a daily time; a time before or after one of the five prayers;
  chosen days of the Hijri month (for example the 13th-15th, the days of the
  white nights); or a page that changes
- **tasks**: run through the user's own agent, so Quran, hadith and dates come
  from MIZAN's sources and recipes; or MIZAN's built-in "ayah of the day", which
  needs no model at all

Two judgements decide when a notice reaches the user:

1. **Quiet around salah.** Prayer times are computed on the server from the
   user's place (adhanpy, the Adhan algorithms, MIT licence). Nothing is
   delivered from 5 minutes before each adhan until 20 minutes after, or, on
   Friday, from 30 minutes before Dhuhr until 60 after (Jumu'ah). A notice due
   in that time waits until it ends.
2. **Attention.** Each kind of watcher keeps a Beta posterior of how often its
   notices were useful to this user (their "useful" and "not now" feedback). A
   notice is delivered when a Thompson draw says it is likely to be useful and
   today's attention budget (default 6) has room; otherwise it waits for the
   evening digest. A watcher the user marks "always" skips the draw but still
   waits for salah.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import re
import sqlite3
import threading
import uuid
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger("mizan.muraqabah")

PRAYERS = ("fajr", "dhuhr", "asr", "maghrib", "isha")
METHODS = (
    "MUSLIM_WORLD_LEAGUE", "EGYPTIAN", "KARACHI", "UMM_AL_QURA", "DUBAI",
    "MOON_SIGHTING_COMMITTEE", "NORTH_AMERICA", "KUWAIT", "QATAR", "SINGAPORE", "UOIF",
)  # fmt: skip
TRIGGERS = ("daily", "prayer", "hijri", "page")
BUILT_IN_TASKS = ("ayah_of_the_day",)
REMIND = "remind:"  # a task that is only a reminder: its text, no model call
MAX_WATCHERS = 30
DEFAULT_BUDGET = 6
_PRIOR = (2.0, 1.0)  # a new kind of watcher starts out mostly trusted

# Places MIZAN knows without a network call: (lat, lon, time zone, method, Hanafi Asr).
CITIES: dict[str, tuple[float, float, str, str, bool]] = {
    "makkah": (21.4225, 39.8262, "Asia/Riyadh", "UMM_AL_QURA", False),
    "mecca": (21.4225, 39.8262, "Asia/Riyadh", "UMM_AL_QURA", False),
    "madinah": (24.4672, 39.6111, "Asia/Riyadh", "UMM_AL_QURA", False),
    "medina": (24.4672, 39.6111, "Asia/Riyadh", "UMM_AL_QURA", False),
    "riyadh": (24.7136, 46.6753, "Asia/Riyadh", "UMM_AL_QURA", False),
    "jeddah": (21.4858, 39.1925, "Asia/Riyadh", "UMM_AL_QURA", False),
    "dubai": (25.2048, 55.2708, "Asia/Dubai", "DUBAI", False),
    "abu dhabi": (24.4539, 54.3773, "Asia/Dubai", "DUBAI", False),
    "doha": (25.2854, 51.5310, "Asia/Qatar", "QATAR", False),
    "kuwait": (29.3759, 47.9774, "Asia/Kuwait", "KUWAIT", False),
    "cairo": (30.0444, 31.2357, "Africa/Cairo", "EGYPTIAN", False),
    "istanbul": (41.0082, 28.9784, "Europe/Istanbul", "MUSLIM_WORLD_LEAGUE", True),
    "karachi": (24.8607, 67.0011, "Asia/Karachi", "KARACHI", True),
    "lahore": (31.5204, 74.3587, "Asia/Karachi", "KARACHI", True),
    "islamabad": (33.6844, 73.0479, "Asia/Karachi", "KARACHI", True),
    "peshawar": (34.0151, 71.5249, "Asia/Karachi", "KARACHI", True),
    "delhi": (28.6139, 77.2090, "Asia/Kolkata", "KARACHI", True),
    "new delhi": (28.6139, 77.2090, "Asia/Kolkata", "KARACHI", True),
    "mumbai": (19.0760, 72.8777, "Asia/Kolkata", "KARACHI", True),
    "hyderabad": (17.3850, 78.4867, "Asia/Kolkata", "KARACHI", True),
    "lucknow": (26.8467, 80.9462, "Asia/Kolkata", "KARACHI", True),
    "bengaluru": (12.9716, 77.5946, "Asia/Kolkata", "KARACHI", True),
    "bangalore": (12.9716, 77.5946, "Asia/Kolkata", "KARACHI", True),
    "kolkata": (22.5726, 88.3639, "Asia/Kolkata", "KARACHI", True),
    "chennai": (13.0827, 80.2707, "Asia/Kolkata", "KARACHI", True),
    "srinagar": (34.0837, 74.7973, "Asia/Kolkata", "KARACHI", True),
    "dhaka": (23.8103, 90.4125, "Asia/Dhaka", "KARACHI", True),
    "kabul": (34.5553, 69.2075, "Asia/Kabul", "KARACHI", True),
    "jakarta": (-6.2088, 106.8456, "Asia/Jakarta", "SINGAPORE", False),
    "kuala lumpur": (3.1390, 101.6869, "Asia/Kuala_Lumpur", "SINGAPORE", False),
    "singapore": (1.3521, 103.8198, "Asia/Singapore", "SINGAPORE", False),
    "london": (51.5072, -0.1276, "Europe/London", "MOON_SIGHTING_COMMITTEE", False),
    "birmingham": (52.4862, -1.8904, "Europe/London", "MOON_SIGHTING_COMMITTEE", False),
    "paris": (48.8566, 2.3522, "Europe/Paris", "UOIF", False),
    "new york": (40.7128, -74.0060, "America/New_York", "NORTH_AMERICA", False),
    "chicago": (41.8781, -87.6298, "America/Chicago", "NORTH_AMERICA", False),
    "toronto": (43.6532, -79.3832, "America/Toronto", "NORTH_AMERICA", False),
}
_COUNTRY_METHOD = {
    "PK": ("KARACHI", True), "IN": ("KARACHI", True), "BD": ("KARACHI", True),
    "AF": ("KARACHI", True), "SA": ("UMM_AL_QURA", False), "AE": ("DUBAI", False),
    "EG": ("EGYPTIAN", False), "US": ("NORTH_AMERICA", False), "CA": ("NORTH_AMERICA", False),
    "KW": ("KUWAIT", False), "QA": ("QATAR", False), "SG": ("SINGAPORE", False),
    "MY": ("SINGAPORE", False), "ID": ("SINGAPORE", False), "FR": ("UOIF", False),
    "GB": ("MOON_SIGHTING_COMMITTEE", False), "TR": ("MUSLIM_WORLD_LEAGUE", True),
}  # fmt: skip


@dataclass
class Place:
    label: str
    lat: float
    lon: float
    tz: str
    method: str = "MUSLIM_WORLD_LEAGUE"
    hanafi: bool = False
    budget: int = DEFAULT_BUDGET
    digest: str = "21:00"
    quiet: bool = True

    @property
    def zone(self) -> ZoneInfo:
        try:
            return ZoneInfo(self.tz)
        except (ZoneInfoNotFoundError, ValueError):
            return ZoneInfo("UTC")

    def to_dict(self) -> dict:
        return {
            "label": self.label, "lat": self.lat, "lon": self.lon, "tz": self.tz,
            "method": self.method, "hanafi": self.hanafi, "budget": self.budget,
            "digest": self.digest, "quiet": self.quiet,
        }  # fmt: skip


def _utc(moment: datetime) -> str:
    """Times are stored and compared as UTC ISO strings (one offset, so text order is time order)."""
    return moment.astimezone(UTC).isoformat()


def known_city(name: str) -> Place | None:
    entry = CITIES.get(" ".join(name.lower().split()))
    if entry is None:
        return None
    lat, lon, tz, method, hanafi = entry
    return Place(name.strip().title(), lat, lon, tz, method, hanafi)


def city_in(text: str) -> Place | None:
    """A city from MIZAN's own table named in the text ("Fajr ka time Karachi me")."""
    lowered = " " + " ".join(re.findall(r"\w+", text.lower())) + " "
    for name in sorted(CITIES, key=len, reverse=True):
        if f" {name} " in lowered:
            return known_city(name)
    return None


async def find_place(name: str) -> Place | None:
    """A city by name: MIZAN's own table first, then Open-Meteo's free geocoder."""
    place = known_city(name)
    if place is not None:
        return place
    import httpx

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": name.strip()[:80], "count": 1, "format": "json"},
            )
            response.raise_for_status()
            found = (response.json().get("results") or [None])[0]
    except (httpx.HTTPError, ValueError):
        return None
    if not found:
        return None
    method, hanafi = _COUNTRY_METHOD.get(
        found.get("country_code", ""), ("MUSLIM_WORLD_LEAGUE", False)
    )
    label = ", ".join(part for part in (found.get("name"), found.get("country")) if part)
    return Place(
        label, float(found["latitude"]), float(found["longitude"]),
        found.get("timezone") or "UTC", method, hanafi,
    )  # fmt: skip


# ── Prayer times and quiet windows ───────────────────────────────────────


def prayer_times(place: Place, day: date) -> dict[str, datetime]:
    from adhanpy.calculation.CalculationMethod import CalculationMethod
    from adhanpy.calculation.CalculationParameters import CalculationParameters
    from adhanpy.calculation.Madhab import Madhab
    from adhanpy.PrayerTimes import PrayerTimes

    params = CalculationParameters(method=CalculationMethod[place.method])
    params.madhab = Madhab.HANAFI if place.hanafi else Madhab.SHAFI
    times = PrayerTimes(
        (place.lat, place.lon),
        datetime(day.year, day.month, day.day),
        calculation_parameters=params,
        time_zone=place.zone,
    )
    return {name: getattr(times, name) for name in (*PRAYERS[:1], "sunrise", *PRAYERS[1:])}


def quiet_windows(place: Place, day: date) -> list[tuple[str, datetime, datetime]]:
    """(prayer, start, end) for the day: nothing interrupts the user then."""
    times = prayer_times(place, day)
    windows = []
    for name in PRAYERS:
        moment = times[name]
        if name == "dhuhr" and day.weekday() == 4:
            windows.append(
                ("jumuah", moment - timedelta(minutes=30), moment + timedelta(minutes=60))
            )
        else:
            windows.append((name, moment - timedelta(minutes=5), moment + timedelta(minutes=20)))
    return windows


def quiet_until(place: Place | None, moment: datetime) -> datetime | None:
    """When the salah window around ``moment`` ends, or None when it is not in one."""
    if place is None or not place.quiet:
        return None
    local = moment.astimezone(place.zone)
    for day in (local.date() - timedelta(days=1), local.date()):
        for _name, start, end in quiet_windows(place, day):
            if start <= moment < end:
                return end
    return None


# ── Triggers ─────────────────────────────────────────────────────────────


def _clock(value: str) -> time:
    hours, _, minutes = (value or "08:00").partition(":")
    return time(max(0, min(23, int(hours))), max(0, min(59, int(minutes or 0))))


def validate_trigger(trigger: dict) -> dict:
    """A trigger MIZAN can schedule, or ValueError."""
    kind = trigger.get("kind")
    if kind == "daily":
        _clock(str(trigger.get("time", "")))
        return {"kind": "daily", "time": _clock(str(trigger["time"])).strftime("%H:%M")}
    if kind == "prayer":
        prayer = str(trigger.get("prayer", "")).lower()
        if prayer not in PRAYERS:
            raise ValueError("prayer must be one of " + ", ".join(PRAYERS))
        offset = int(trigger.get("offset", 0))
        return {"kind": "prayer", "prayer": prayer, "offset": max(-120, min(240, offset))}
    if kind == "hijri":
        days = sorted({int(d) for d in trigger.get("days") or [] if 1 <= int(d) <= 30})
        if not days:
            raise ValueError("hijri needs days of the month (1-30)")
        months = sorted({int(m) for m in trigger.get("months") or [] if 1 <= int(m) <= 12})
        return {"kind": "hijri", "days": days, "months": months,
                "time": _clock(str(trigger.get("time", "08:00"))).strftime("%H:%M")}  # fmt: skip
    if kind == "page":
        url = str(trigger.get("url", ""))
        if not url.startswith(("https://", "http://")):
            raise ValueError("page needs a web address")
        return {
            "kind": "page",
            "url": url[:500],
            "hours": max(1, min(168, int(trigger.get("hours", 6)))),
        }
    raise ValueError("trigger kind must be one of " + ", ".join(TRIGGERS))


def next_due(
    trigger: dict, place: Place | None, after: datetime, last: str = ""
) -> datetime | None:
    """The next moment this trigger fires, strictly after ``after``."""
    zone = place.zone if place else ZoneInfo("UTC")
    local = after.astimezone(zone)
    kind = trigger["kind"]
    if kind == "page":
        start = datetime.fromisoformat(last) if last else after
        return max(start + timedelta(hours=trigger["hours"]), after + timedelta(minutes=1))
    for offset in range(0, 400):
        day = local.date() + timedelta(days=offset)
        if kind == "daily":
            moment = datetime.combine(day, _clock(trigger["time"]), zone)
        elif kind == "prayer":
            if place is None:
                return None  # prayer times need the user's place
            moment = prayer_times(place, day)[trigger["prayer"]] + timedelta(
                minutes=trigger["offset"]
            )
        else:
            from tadbir import waqt

            hijri = waqt.to_hijri(day)
            if hijri.day not in trigger["days"] or (
                trigger["months"] and hijri.month not in trigger["months"]
            ):
                continue
            moment = datetime.combine(day, _clock(trigger["time"]), zone)
        if moment > after:
            return moment.astimezone(UTC)
    return None


def describe(trigger: dict) -> str:
    kind = trigger["kind"]
    if kind == "daily":
        return f"every day at {trigger['time']}"
    if kind == "prayer":
        offset = trigger["offset"]
        when = "at" if offset == 0 else f"{abs(offset)} min {'after' if offset > 0 else 'before'}"
        return f"{when} {trigger['prayer'].title()} every day"
    if kind == "hijri":
        days = ", ".join(str(d) for d in trigger["days"])
        months = (
            f" of month {', '.join(str(m) for m in trigger['months'])}" if trigger["months"] else ""
        )
        return f"on Hijri day {days}{months} at {trigger['time']}"
    return f"when {trigger['url']} changes (checked every {trigger['hours']} h)"


# ── Storage ──────────────────────────────────────────────────────────────


class Store:
    """Watchers, notices, places and attention posteriors, one SQLite file."""

    def __init__(self, path: str | None = None):
        directory = Path(os.getenv("MIZAN_DATA_DIR", "/data/mizan"))
        self.path = path or str(directory / "muraqabah.db")
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS places (owner_id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS watchers (
                    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, title TEXT NOT NULL,
                    trigger TEXT NOT NULL, task TEXT NOT NULL, priority TEXT NOT NULL,
                    enabled INTEGER NOT NULL, created TEXT NOT NULL, last_fired TEXT,
                    next_due TEXT, state TEXT NOT NULL DEFAULT '{}');
                CREATE TABLE IF NOT EXISTS notices (
                    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, watcher_id TEXT NOT NULL,
                    kind TEXT NOT NULL, text TEXT NOT NULL, status TEXT NOT NULL,
                    created TEXT NOT NULL, deliver_after TEXT, delivered TEXT, feedback TEXT);
                CREATE TABLE IF NOT EXISTS attention (
                    owner_id TEXT NOT NULL, kind TEXT NOT NULL, alpha REAL NOT NULL,
                    beta REAL NOT NULL, PRIMARY KEY (owner_id, kind));
                CREATE INDEX IF NOT EXISTS idx_watchers_due ON watchers(enabled, next_due);
                CREATE INDEX IF NOT EXISTS idx_notices_owner ON notices(owner_id, status);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _run(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock, self._connect() as conn:
            return conn.execute(sql, params).fetchall()

    # places
    def place(self, owner: str) -> Place | None:
        rows = self._run("SELECT data FROM places WHERE owner_id = ?", (owner,))
        return Place(**json.loads(rows[0]["data"])) if rows else None

    def set_place(self, owner: str, place: Place) -> None:
        self._run(
            "INSERT INTO places VALUES (?, ?) ON CONFLICT(owner_id) DO UPDATE SET data = excluded.data",
            (owner, json.dumps(place.to_dict())),
        )

    # watchers
    def watchers(self, owner: str) -> list[dict]:
        rows = self._run("SELECT * FROM watchers WHERE owner_id = ? ORDER BY created", (owner,))
        return [_watcher(row) for row in rows]

    def watcher(self, owner: str, watcher_id: str) -> dict | None:
        rows = self._run(
            "SELECT * FROM watchers WHERE owner_id = ? AND id = ?", (owner, watcher_id)
        )
        return _watcher(rows[0]) if rows else None

    def add(
        self, owner: str, title: str, trigger: dict, task: str, priority: str = "judge"
    ) -> dict:
        if len(self.watchers(owner)) >= MAX_WATCHERS:
            raise ValueError(f"At most {MAX_WATCHERS} watchers")
        trigger = validate_trigger(trigger)
        due = next_due(trigger, self.place(owner), datetime.now(UTC))
        if due is None and trigger["kind"] == "prayer":
            raise ValueError("Set your city first: prayer times need it")
        watcher_id = uuid.uuid4().hex[:12]
        self._run(
            "INSERT INTO watchers (id, owner_id, title, trigger, task, priority, enabled, created, "
            "next_due) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)",
            (watcher_id, owner, title[:120], json.dumps(trigger), task[:1000],
             "always" if priority == "always" else "judge", _utc(datetime.now(UTC)),
             _utc(due) if due else None),
        )  # fmt: skip
        return self.watcher(owner, watcher_id) or {}

    def update(self, owner: str, watcher_id: str, **changes: Any) -> dict | None:
        current = self.watcher(owner, watcher_id)
        if current is None:
            return None
        fields = {
            k: v
            for k, v in changes.items()
            if k in {"title", "task", "priority", "enabled"} and v is not None
        }
        trigger = (
            validate_trigger(changes["trigger"]) if changes.get("trigger") else current["trigger"]
        )
        if fields or changes.get("trigger") or changes.get("enabled"):
            due = next_due(
                trigger, self.place(owner), datetime.now(UTC), current.get("last_fired") or ""
            )
            fields["next_due"] = _utc(due) if due else None
        fields["trigger"] = json.dumps(trigger)
        if "enabled" in fields:
            fields["enabled"] = 1 if fields["enabled"] else 0
        assignments = ", ".join(f"{key} = ?" for key in fields)  # keys from the fixed set above
        self._run(
            f"UPDATE watchers SET {assignments} WHERE owner_id = ? AND id = ?",  # noqa: S608
            (*fields.values(), owner, watcher_id),
        )
        return self.watcher(owner, watcher_id)

    def remove(self, owner: str, watcher_id: str) -> bool:
        found = self.watcher(owner, watcher_id) is not None
        self._run("DELETE FROM watchers WHERE owner_id = ? AND id = ?", (owner, watcher_id))
        return found

    def due(self, now: datetime) -> list[dict]:
        rows = self._run(
            "SELECT * FROM watchers WHERE enabled = 1 AND next_due IS NOT NULL AND next_due <= ?",
            (_utc(now),),
        )
        return [_watcher(row) for row in rows]

    def fired(self, watcher: dict, now: datetime, state: dict | None = None) -> None:
        due = next_due(watcher["trigger"], self.place(watcher["owner_id"]), now, _utc(now))
        self._run(
            "UPDATE watchers SET last_fired = ?, next_due = ?, state = ? WHERE id = ?",
            (_utc(now), _utc(due) if due else None,
             json.dumps(state if state is not None else watcher["state"]), watcher["id"]),
        )  # fmt: skip

    # notices
    def notice(self, owner: str, watcher: dict, text: str) -> str:
        notice_id = uuid.uuid4().hex[:12]
        self._run(
            "INSERT INTO notices (id, owner_id, watcher_id, kind, text, status, created) "
            "VALUES (?, ?, ?, ?, ?, 'pending', ?)",
            (notice_id, owner, watcher["id"], watcher["trigger"]["kind"], text,
             _utc(datetime.now(UTC))),
        )  # fmt: skip
        return notice_id

    def notices(self, owner: str, status: str | None = None, limit: int = 50) -> list[dict]:
        sql = "SELECT * FROM notices WHERE owner_id = ?"
        params: tuple = (owner,)
        if status:
            sql += " AND status = ?"
            params += (status,)
        rows = self._run(sql + " ORDER BY created DESC LIMIT ?", (*params, limit))
        return [dict(row) for row in rows]

    def waiting(self, now: datetime) -> list[dict]:
        rows = self._run(
            "SELECT * FROM notices WHERE status = 'pending' OR (status = 'held' AND deliver_after <= ?)",
            (_utc(now),),
        )
        return [dict(row) for row in rows]

    def waiting_digest(self) -> list[dict]:
        return [dict(row) for row in self._run("SELECT * FROM notices WHERE status = 'digest'")]

    def mark(self, notice_id: str, status: str, **values: Any) -> None:
        allowed = {
            k: v for k, v in values.items() if k in {"deliver_after", "delivered", "feedback"}
        }
        assignments = "".join(f", {key} = ?" for key in allowed)  # keys from the fixed set above
        self._run(
            f"UPDATE notices SET status = ?{assignments} WHERE id = ?",  # noqa: S608
            (status, *allowed.values(), notice_id),
        )

    def delivered_today(self, owner: str, place: Place | None, now: datetime) -> int:
        zone = place.zone if place else ZoneInfo("UTC")
        start = datetime.combine(now.astimezone(zone).date(), time(0), zone).astimezone(UTC)
        rows = self._run(
            "SELECT COUNT(*) AS n FROM notices WHERE owner_id = ? AND status IN ('delivered', 'opened') "
            "AND delivered >= ?",
            (owner, _utc(start)),
        )
        return int(rows[0]["n"])

    # attention
    def posterior(self, owner: str, kind: str) -> tuple[float, float]:
        rows = self._run(
            "SELECT alpha, beta FROM attention WHERE owner_id = ? AND kind = ?", (owner, kind)
        )
        return (rows[0]["alpha"], rows[0]["beta"]) if rows else _PRIOR

    def feedback(self, owner: str, notice_id: str, useful: bool) -> bool:
        rows = self._run(
            "SELECT kind FROM notices WHERE owner_id = ? AND id = ?", (owner, notice_id)
        )
        if not rows:
            return False
        kind = rows[0]["kind"]
        alpha, beta = self.posterior(owner, kind)
        alpha, beta = (alpha + 1, beta) if useful else (alpha, beta + 1)
        self._run(
            "INSERT INTO attention VALUES (?, ?, ?, ?) ON CONFLICT(owner_id, kind) DO UPDATE SET "
            "alpha = excluded.alpha, beta = excluded.beta",
            (owner, kind, alpha, beta),
        )
        self.mark(
            notice_id,
            "opened" if useful else "dismissed",
            feedback="useful" if useful else "not_now",
        )
        return True

    def owners(self) -> list[str]:
        return [row["owner_id"] for row in self._run("SELECT DISTINCT owner_id FROM watchers")]


def _watcher(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["trigger"] = json.loads(data["trigger"])
    data["state"] = json.loads(data.get("state") or "{}")
    data["enabled"] = bool(data["enabled"])
    data["when"] = describe(data["trigger"])
    return data


# ── Judging and running ──────────────────────────────────────────────────


def decide(store: Store, owner: str, notice: dict, priority: str, now: datetime,
           rng: random.Random | None = None) -> tuple[str, datetime | None]:  # fmt: skip
    """("deliver" | "hold" | "digest", hold-until) for one waiting notice."""
    place = store.place(owner)
    until = quiet_until(place, now)
    if until is not None:
        return "hold", until
    if priority == "always":
        return "deliver", None
    budget = place.budget if place else DEFAULT_BUDGET
    if store.delivered_today(owner, place, now) >= budget:
        return "digest", None
    alpha, beta = store.posterior(owner, notice["kind"])
    draw = (rng or random).betavariate(alpha, beta)
    return ("deliver", None) if draw >= 0.5 else ("digest", None)


def ayah_of_the_day(day: date) -> tuple[int, int]:
    """(surah, ayah): the whole Quran in order, one ayah a day."""
    from tadbir.quran import SURAHS

    index = (day.toordinal() - date(2026, 1, 1).toordinal()) % 6236
    for number, (_name, _arabic, count) in enumerate(SURAHS, start=1):
        if index < count:
            return number, index + 1
        index -= count
    return 1, 1


async def ayah_text(day: date, language: str = "en") -> str:
    from tadbir import quran, waqt

    surah, ayah = ayah_of_the_day(day)
    reference = quran.Reference(surah, ayah, ayah)
    hijri = waqt.to_hijri(day)
    lines = [f"**{waqt.hijri_text(hijri)}** · {waqt.gregorian_text(day)}", ""]
    try:
        data = await quran.fetch(reference, language)
        verse = data["ayahs"][0]
        lines += [f"> {verse['arabic']}", ""]
        if verse.get("translation"):
            lines += [verse["translation"], ""]
    except quran.QuranUnavailable:
        lines += ["(MIZAN could not reach its Quran source; it will not quote from memory.)", ""]
    lines.append(f"— {reference.label}")
    return "\n".join(lines)


RunTask = Callable[[str, str], Awaitable[str]]
Deliver = Callable[[str, str, dict], Awaitable[None]]
ReadPage = Callable[[str, str], Awaitable[str | None]]


async def fire(
    store: Store, watcher: dict, now: datetime, run_task: RunTask, read_page: ReadPage
) -> None:
    owner = watcher["owner_id"]
    state = dict(watcher["state"])
    text: str | None
    if watcher["trigger"]["kind"] == "page":
        page = await read_page(owner, watcher["trigger"]["url"])
        digest = hashlib.sha256((page or "").encode()).hexdigest()
        text = None
        if page is not None and state.get("digest") and state["digest"] != digest:
            text = f"**{watcher['title']}**: the page changed.\n\n{page[:600]}\n\n{watcher['trigger']['url']}"
        if page is not None:
            state["digest"] = digest
    elif watcher["task"].startswith(REMIND):
        text = f"**{watcher['title']}**\n\n{watcher['task'][len(REMIND) :].strip()}"
    elif watcher["task"] in BUILT_IN_TASKS:
        place = store.place(owner)
        local = now.astimezone(place.zone if place else ZoneInfo("UTC")).date()
        text = f"**{watcher['title']}**\n\n" + await ayah_text(local)
    else:
        result = await run_task(owner, watcher["task"])
        text = f"**{watcher['title']}**\n\n{result}" if result else None
    store.fired(watcher, now, state)
    if text:
        store.notice(owner, watcher, text)


async def deliver_waiting(store: Store, now: datetime, deliver: Deliver,
                          rng: random.Random | None = None) -> dict[str, int]:  # fmt: skip
    counts = {"deliver": 0, "hold": 0, "digest": 0}
    for notice in store.waiting(now):
        watcher = store.watcher(notice["owner_id"], notice["watcher_id"]) or {"priority": "judge"}
        verdict, until = decide(store, notice["owner_id"], notice, watcher["priority"], now, rng)
        counts[verdict] += 1
        if verdict == "hold":
            store.mark(notice["id"], "held", deliver_after=_utc(until) if until else None)
        elif verdict == "deliver":
            await deliver(notice["owner_id"], notice["text"], {"notice_id": notice["id"]})
            store.mark(notice["id"], "delivered", delivered=_utc(now))
        else:
            store.mark(notice["id"], "digest")
    return counts


async def send_digests(store: Store, now: datetime, deliver: Deliver) -> int:
    """At each user's digest time, one message with what waited, outside salah."""
    sent = 0
    for owner in {notice["owner_id"] for notice in store.waiting_digest()}:
        place = store.place(owner)
        zone = place.zone if place else ZoneInfo("UTC")
        local = now.astimezone(zone)
        at = datetime.combine(local.date(), _clock(place.digest if place else "21:00"), zone)
        if local < at or quiet_until(place, now) is not None:
            continue
        items = store.notices(owner, "digest", limit=20)
        if not items:
            continue
        body = "\n\n---\n\n".join(item["text"] for item in reversed(items))
        await deliver(owner, f"**Muraqabah digest** ({len(items)})\n\n{body}", {"digest": True})
        for item in items:
            store.mark(item["id"], "delivered", delivered=_utc(now))
        sent += 1
    return sent


async def tick(store: Store, now: datetime, *, run_task: RunTask, deliver: Deliver,
               read_page: ReadPage) -> dict[str, int]:  # fmt: skip
    """One pass: fire what is due, then deliver, hold or digest what waits."""
    fired = 0
    for watcher in store.due(now):
        try:
            await fire(store, watcher, now, run_task, read_page)
            fired += 1
        except Exception:  # noqa: BLE001 - one watcher must not stop the others
            logger.exception("[MURAQABAH] watcher %s failed", watcher["id"])
            store.fired(watcher, now)
    counts = await deliver_waiting(store, now, deliver)
    counts["digests"] = await send_digests(store, now, deliver)
    counts["fired"] = fired
    return counts


_STORES: dict[str, Store] = {}
_inside: ContextVar[bool] = ContextVar("mizan_inside_watcher", default=False)


def default_store() -> Store:
    path = str(Path(os.getenv("MIZAN_DATA_DIR", "/data/mizan")) / "muraqabah.db")
    if path not in _STORES:
        _STORES[path] = Store(path)
    return _STORES[path]


@contextmanager
def running_watcher() -> Iterator[None]:
    """While a watcher's task runs: it may not create watchers (no loops)."""
    token = _inside.set(True)
    try:
        yield
    finally:
        _inside.reset(token)


def inside_watcher() -> bool:
    return _inside.get()


def session_id(owner: str) -> str:
    """The chat where a user's watchers post."""
    return "muraqabah-" + hashlib.sha256(owner.encode()).hexdigest()[:16]
