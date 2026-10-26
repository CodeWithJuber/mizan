"""Waqt (وقت): dates and times MIZAN states itself.

The Gregorian date and the time come from the server clock in the user's own
timezone, which the browser sends with each chat. Hijri dates use the Umm
al-Qura calendar (``hijridate``), which is computed in advance; where a
month begins by local sighting of the crescent it can differ by a day, and
MIZAN says so with every Hijri date.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from hijridate import Gregorian, Hijri

_ZONE: ContextVar[str | None] = ContextVar("user_timezone", default=None)


@contextmanager
def bind_timezone(name: str | None) -> Iterator[None]:
    """The user's IANA timezone for this request; an unknown name is ignored."""
    zone = None
    if name:
        try:
            ZoneInfo(name)
            zone = name
        except (ValueError, KeyError, OSError):
            zone = None
    token = _ZONE.set(zone)
    try:
        yield
    finally:
        _ZONE.reset(token)


def now() -> tuple[datetime, str | None]:
    """The current time in the user's timezone, and that zone's name (None: UTC)."""
    name = _ZONE.get()
    return datetime.now(ZoneInfo(name or "UTC")), name


MONTHS = (
    "Muharram", "Safar", "Rabi' al-Awwal", "Rabi' al-Akhir", "Jumada al-Ula",
    "Jumada al-Akhirah", "Rajab", "Sha'ban", "Ramadan", "Shawwal", "Dhu al-Qa'dah",
    "Dhu al-Hijjah",
)  # fmt: skip
MONTHS_AR = (
    "محرم", "صفر", "ربيع الأول", "ربيع الآخر", "جمادى الأولى", "جمادى الآخرة", "رجب",
    "شعبان", "رمضان", "شوال", "ذو القعدة", "ذو الحجة",
)  # fmt: skip
_MONTH_PATTERNS = (
    r"muharr?am",
    r"safa?r",
    r"rabi\w*\s*(?:ul|al|-)?\s*-?\s*(?:awwal|awal|aw+al|ula|1st)",
    r"rabi\w*\s*(?:ul|al|us|as|-)?\s*-?\s*(?:akhir|aakhir|thani|sani|saani)",
    r"jumad[ai]\w*\s*(?:ul|al|-)?\s*-?\s*(?:ula|oola|awwal|awal)|jamadi\w*\s*(?:ul)?\s*(?:awwal|awal|ula)",
    r"jumad[ai]\w*\s*(?:ul|al|us|as|-)?\s*-?\s*(?:akhirah|akhira|akhir|thani|sani|saani)"
    r"|jamadi\w*\s*(?:us|ul)?\s*(?:sani|saani|akhir)",
    r"rajab",
    r"sha['’]?a?ban|shaaban",
    r"rama[dz]h?aa?n|ramzan|ramazan",
    r"shaww?al",
    r"dh?[iu]l?\s*-?\s*(?:al\s*)?qa['’]?a?d(?:ah|a)?|zil?\s*-?\s*qa['’]?a?d(?:ah|a)?|zeeqad|ziqad",
    r"dh?[iu]l?\s*-?\s*(?:al\s*)?hij+(?:ah|a)?|zil?\s*-?\s*hij+(?:ah|a)?|zil?\s*-?\s*haj+|zilhaj",
)
_MONTH_SCRIPT = (
    ("محرم",),
    ("صفر",),
    ("ربيع الاول", "ربيع الأول", "ربیع الاول"),
    ("ربيع الآخر", "ربيع الثاني", "ربیع الثانی", "ربیع الآخر"),
    ("جمادى الأولى", "جمادى الاولى", "جمادی الاول", "جمادی الاولی"),
    ("جمادى الآخرة", "جمادى الاخرة", "جمادی الثانی", "جمادی الآخر"),
    ("رجب",),
    ("شعبان",),
    ("رمضان",),
    ("شوال",),
    ("ذو القعدة", "ذوالقعدہ", "ذی قعدہ"),
    ("ذو الحجة", "ذوالحجہ", "ذی الحجہ"),
)
GREGORIAN_MONTHS = (
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december",
)  # fmt: skip
# Days with an established sunnah practice, and the two Eids.
EVENTS = {
    "eid_fitr": ("Eid al-Fitr", 10, 1),
    "eid_adha": ("Eid al-Adha", 12, 10),
    "ramadan": ("Ramadan begins", 9, 1),
    "arafah": ("Day of Arafah", 12, 9),
    "ashura": ("Ashura (10 Muharram)", 1, 10),
    "new_year": ("Islamic New Year (1 Muharram)", 1, 1),
}
_EVENT_PATTERNS = {
    "eid_fitr": r"\beid\s*(?:ul|al|-)?\s*-?\s*fitr\b|\bchh?oti\s+eid\b|\bmeethi\s+eid\b|عيد الفطر|عید الفطر|ईद उल फ़ित्र",
    "eid_adha": r"\beid\s*(?:ul|al|-)?\s*-?\s*a[dz]h?a\b|\bbakr[ai]?\s*-?\s*eid\b|\bbakrid\b|\bbadi\s+eid\b|عيد الأضحى|عید الاضحی|बकरीद",
    "ramadan": r"\brama[dz]h?aa?n\b|\bramzan\b|\bramazan\b|رمضان|रमज़ान|रमजान",
    "arafah": r"\barafa[ht]?\b|\byawm\s+al\s+arafah\b|عرفة|عرفہ",
    "ashura": r"\bashura\b|\baashura\b|عاشوراء|عاشورہ",
    "new_year": r"\bislamic\s+new\s+year\b|\bhijri\s+new\s+year\b|\b1\s+muharram\b|رأس السنة الهجرية",
}

_TODAY = re.compile(
    r"\b(?:today'?s?\s+(?:date|hijri|islamic)|date\s+today|what(?:'s|\s+is)\s+(?:the\s+)?"
    r"(?:date|day)|aaj\s+(?:ki|ka|kya|kaunsi|konsi|kon\s*si)?\s*(?:date|tarikh|tareekh|din)|"
    r"(?:date|tarikh|tareekh)\s+(?:kya|batao)|islamic\s+date|hijri\s+date|abhi\s+ki\s+date)\b"
    r"|آج کی تاریخ|آج کیا تاریخ|آج کون سی تاریخ|ما التاريخ|تاريخ اليوم|التاريخ اليوم|"
    r"आज की तारीख|आज क्या तारीख|आज कौन सी तारीख",
    re.IGNORECASE,
)
_TIME = re.compile(
    r"\b(?:what\s+time\s+is\s+it|current\s+time|time\s+now|(?:time|samay|waqt)\s+kya\s+(?:hai|hua)|"
    r"kitne\s+baje|kya\s+time|abhi\s+(?:ka\s+)?time)\b|کتنے بجے|کیا وقت ہوا|كم الساعة|कितने बजे|क्या समय",
    re.IGNORECASE,
)
_HIJRI = re.compile(
    r"\b(?:hijri|hijra|islamic|islami|qamari|chand\s+ki|ah)\b|هجري|ہجری|ھجری|हिजरी|اسلامی",
    re.IGNORECASE,
)
_GREGORIAN = re.compile(
    r"\b(?:gregorian|english\s+date|angrezi|christian|ce|ad)\b|میلادی|عیسوی|ميلادي|अंग्रेज़ी",
    re.IGNORECASE,
)
_WHEN = re.compile(
    r"\b(?:when|kab|kis\s+din|kaunse\s+din|next|agla|agli|aane\s+wal[ia]|upcoming|date)\b"
    r"|کب|متى|कब",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class WaqtRequest:
    kind: str  # today | to_hijri | to_gregorian | event
    gregorian: date | None = None
    hijri: tuple[int, int, int] | None = None  # (year, month, day); year 0 = next
    event: str = ""
    with_time: bool = False


def _hijri_month(text: str) -> tuple[int, re.Match[str]] | None:
    for index, pattern in enumerate(_MONTH_PATTERNS, start=1):
        match = re.search(rf"\b(?:{pattern})\b", text, re.IGNORECASE)
        if match:
            return index, match
    for index, names in enumerate(_MONTH_SCRIPT, start=1):
        for name in names:
            position = text.find(name)
            if position >= 0:
                return index, re.search(re.escape(name), text)  # type: ignore[return-value]
    return None


def _gregorian_date(text: str) -> date | None:
    months = "|".join(GREGORIAN_MONTHS) + "|" + "|".join(m[:3] for m in GREGORIAN_MONTHS)
    patterns = (
        (rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({months})\.?,?\s+(\d{{4}})\b", "dmy"),
        (rf"\b({months})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", "mdy"),
        (r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", "iso"),
    )
    for pattern, order in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        try:
            if order == "iso":
                return date(int(match[1]), int(match[2]), int(match[3]))
            day, month, year = (
                (match[1], match[2], match[3]) if order == "dmy" else (match[2], match[1], match[3])
            )
            names = [m[:3] for m in GREGORIAN_MONTHS]
            return date(int(year), names.index(month.lower()[:3]) + 1, int(day))
        except ValueError:
            return None
    return None


def parse(text: str) -> WaqtRequest | None:
    """A date, Hijri conversion or Islamic-calendar question, or None."""
    # "aaj ki date aur time batao": a time word next to a date question.
    with_time = bool(_TIME.search(text)) or bool(
        _TODAY.search(text) and re.search(r"\b(?:time|samay|waqt|baje)\b|وقت|समय", text, re.I)
    )
    gregorian = _gregorian_date(text)
    if gregorian and _HIJRI.search(text):
        return WaqtRequest("to_hijri", gregorian=gregorian)
    month = _hijri_month(text)
    if month is not None:
        number, match = month
        year = re.search(r"\b(1[34]\d\d)\b", text)
        day = re.search(r"(?<![\d.:])(\d{1,2})(?:st|nd|rd|th)?\s*$", text[: match.start()])
        if year and day and (_GREGORIAN.search(text) or _WHEN.search(text) or _HIJRI.search(text)):
            return WaqtRequest("to_gregorian", hijri=(int(year[1]), number, int(day[1])))
    for key, pattern in _EVENT_PATTERNS.items():
        if re.search(pattern, text, re.IGNORECASE) and _WHEN.search(text):
            year = re.search(r"\b(1[34]\d\d)\b", text)
            return WaqtRequest("event", event=key, hijri=(int(year[1]) if year else 0, 0, 0))
    if re.search(r"\beid\b|عيد|عید|ईद", text, re.IGNORECASE) and _WHEN.search(text):
        return WaqtRequest("event", event="eid", hijri=(0, 0, 0))
    if _TODAY.search(text) or with_time:
        return WaqtRequest("today", with_time=with_time)
    return None


class OutOfRange(ValueError):
    pass


def to_hijri(day: date) -> Hijri:
    try:
        return Gregorian(day.year, day.month, day.day).to_hijri()
    except OverflowError as exc:
        raise OutOfRange(str(exc)) from None


def to_gregorian(year: int, month: int, day: int) -> date:
    try:
        value = Hijri(year, month, day).to_gregorian()
    except (OverflowError, ValueError) as exc:
        raise OutOfRange(str(exc)) from None
    return date(value.year, value.month, value.day)


def next_occurrence(month: int, day: int, today: date) -> tuple[int, date]:
    """The next (Hijri year, Gregorian date) of a Hijri day, today included."""
    year = to_hijri(today).year
    for candidate in (year, year + 1):
        when = to_gregorian(candidate, month, day)
        if when >= today:
            return candidate, when
    raise OutOfRange("beyond the calendar")


def hijri_text(value: Hijri) -> str:
    return f"{value.day} {MONTHS[value.month - 1]} {value.year} AH"


def hijri_arabic(value: Hijri) -> str:
    return f"{value.day} {MONTHS_AR[value.month - 1]} {value.year} هـ"


def gregorian_text(value: date) -> str:
    return f"{value:%A}, {value.day} {value:%B %Y}"
