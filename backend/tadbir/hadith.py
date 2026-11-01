"""Hadith references: MIZAN's own collection index and an open, verbatim source.

MIZAN parses the reference itself, checks the number against its index of the
collection, and quotes the Arabic text with a translation from the open
hadith-api dataset (github.com/fawazahmed0/hadith-api, served by jsDelivr).
Grades are shown exactly as the dataset reports them, scholar by scholar.
MIZAN does not grade hadith itself, and no language model writes or rewrites
a hadith.

Numbering follows how each collection is usually cited: Sahih Muslim by
Muhammad Fu'ad 'Abd al-Baqi's numbers (2564, 2564b), the others by the
numbers this dataset and sunnah.com share.
"""

from __future__ import annotations

import asyncio
import json
import re
import unicodedata
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import httpx

from .quran import _ARABIC_VARIANTS, _ORDINAL_WORDS

API = "https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@1"
SOURCE = "hadith-api (fawazahmed0, open dataset)"
MAX_CHARS = 5000


@dataclass(frozen=True)
class Collection:
    key: str
    name: str
    arabic: str
    last: int
    strong: str  # the name alone identifies the collection
    weak: str = ""  # also an ordinary word (Muslim, Malik): needs a hadith cue
    sahih: bool = False
    sunnah: str = ""  # sunnah.com slug; empty when its numbering differs
    urdu: bool = True
    titled: bool = False  # "40 Hadith ..." collections: the 40 is not a number
    commentary: str = ""  # a recognised sharh, for requests to explain
    commentary_ar: str = ""


_NO = r"(?:no|nr|num|number|#|نمبر|رقم|नंबर)"
COLLECTIONS: tuple[Collection, ...] = (
    Collection(
        "bukhari",
        "Sahih al-Bukhari",
        "صحيح البخاري",
        7563,
        r"\b(?:sahih\s+)?(?:al\s*)?b[ou]u?kh?a+r[iy]\b|بخاري|बुखारी|बुख़ारी",
        sahih=True,
        sunnah="bukhari",
        commentary="Fath al-Bari (Ibn Hajar)",
        commentary_ar="فتح الباري لابن حجر",
    ),
    Collection(
        "muslim",
        "Sahih Muslim",
        "صحيح مسلم",
        3033,
        r"\bsahih\s+muslim\b|\bmuslim\s+share?e?f\b|صحيح\s*مسلم|सहीह\s*मुस्लिम",
        weak=r"\bmuslim\b|مسلم|मुस्लिम",
        sahih=True,
        sunnah="muslim",
        commentary="al-Minhaj (an-Nawawi's Sharh Sahih Muslim)",
        commentary_ar="المنهاج شرح صحيح مسلم للنووي",
    ),
    Collection(
        "abudawud",
        "Sunan Abi Dawud",
        "سنن أبي داود",
        5274,
        r"\bab[ui]\s*da(?:w|v)?(?:u|oo|o|ou)d\b|اب[وي]\s*داود|अबू\s*दाऊद|अबु\s*दाऊद",
        sunnah="abudawud",
        commentary="'Awn al-Ma'bud",
        commentary_ar="عون المعبود",
    ),
    Collection(
        "tirmidhi",
        "Jami` at-Tirmidhi",
        "جامع الترمذي",
        3956,
        r"\b(?:jami\w*\s+)?(?:at\s*)?tirm[iy](?:dh|z|d|th)[iy]\b|ترمذي|तिर्मिज़ी|तिर्मिजी|तिरमिज़ी|तिरमिजी",
        sunnah="tirmidhi",
        commentary="Tuhfat al-Ahwadhi",
        commentary_ar="تحفة الأحوذي",
    ),
    Collection(
        "nasai",
        "Sunan an-Nasa'i",
        "سنن النسائي",
        5758,
        r"\b(?:an\s*)?n[ai]sa+(?:i|ee|y|ie)\b|نسائي|नसाई|नसई",
        sunnah="nasai",
        commentary="Hashiyat as-Sindi",
        commentary_ar="حاشية السندي على سنن النسائي",
    ),
    Collection(
        "ibnmajah",
        "Sunan Ibn Majah",
        "سنن ابن ماجه",
        4341,
        r"\bibn(?:e|\s+e)?\s*maa?jah?\b|ابن\s*ماجه|इब्ने?\s*माजा?ह?",
        sunnah="ibnmajah",
        commentary="Hashiyat as-Sindi",
        commentary_ar="حاشية السندي على سنن ابن ماجه",
    ),
    Collection(
        "malik",
        "Muwatta Malik",
        "موطأ مالك",
        1858,
        r"\bmu(?:w|ow)att?a+\w*(?:\s+(?:imam\s+)?malik)?|موطا(?:\s*مالك)?|मुवत्ता",
        weak=r"\bmalik\b|مالك|मालिक",
        commentary="at-Tamhid (Ibn 'Abd al-Barr)",
        commentary_ar="التمهيد لابن عبد البر",
    ),
    Collection(
        "nawawi",
        "Forty Hadith of an-Nawawi",
        "الأربعون النووية",
        42,
        r"\b(?:an\s*)?nawaw[iy]\w*\b|نووي|नववी|नवावी",
        sunnah="nawawi40",
        commentary="Jami' al-'Ulum wal-Hikam (Ibn Rajab)",
        commentary_ar="جامع العلوم والحكم لابن رجب",
        urdu=False,
        titled=True,
    ),
    Collection(
        "qudsi",
        "Forty Hadith Qudsi",
        "الأربعون القدسية",
        40,
        r"\bqudsi\b|قدسي|क़ुदसी|कुदसी",
        sunnah="qudsi40",
        urdu=False,
        titled=True,
    ),
    Collection(
        "dehlawi",
        "Forty Hadith of Shah Waliullah Dehlawi",
        "الأربعون للدهلوي",
        40,
        r"\bdehl[ae]?w[iy]\b|\bdehlvi\b|\bwali\s*ullah\b|دهلوي",
        urdu=False,
        titled=True,
    ),
)
BY_KEY = {collection.key: collection for collection in COLLECTIONS}

_CUE = re.compile(
    r"\b(?:hadith|hadiths|hadees|hadis|hadeeth|ahadith|ahadees|riwayat|narration)\b"
    r"|حديث|احاديث|روايت|رواه|हदीस",
    re.IGNORECASE,
)
_TITLE = re.compile(
    r"\b(?:forty|arba\w*n|chaa?lees|chalis)\b(?:\s*(?:hadith|hadees|hadis|ahadith)\b)?"
    r"|\b40\s*(?:hadith|hadees|hadis|ahadith)\b|الاربعين|اربعين|الاربعون|چهل|چاليس|चालीस",
    re.IGNORECASE,
)
# A year is not a hadith number ("Imam Bukhari 194 hijri").
_NOT_HADITH = r"(?!\s*(?:hijri|ah|ad|ce|bc|saal|sal|years?|baras|san|ھ|هجري|हिजरी)\b)"
_AFTER = re.compile(
    r"^\s*(?:(?:share?e?f|شريف|शरीफ़?)\s*)?(?:ki|ka|ke|كي|كا|की|का|के|,|:|-|/|،)?\s*"
    r"(?:(?:hadith|hadees|hadis|hadeeth|حديث|हदीस)\s*)?(?:" + _NO + r"\s*\.?\s*)?[:#(]?\s*"
    r"(\d{1,4})(?:([a-z])(?![a-z]))?(?!\d)" + _NOT_HADITH,
    re.IGNORECASE,
)
_BEFORE = re.compile(
    r"(?:hadith|hadees|hadis|hadeeth|حديث|हदीस)\s*(?:" + _NO + r"\s*\.?\s*)?[:#]?\s*"
    r"(\d{1,4})(?:([a-z])(?![a-z]))?\s*(?:of|from|in|,|،|-|من|في)?\s*(?:the\s+)?"
    r"(?:sahih\s+|صحيح\s*)?(?:ال)?$",
    re.IGNORECASE,
)
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹०१२३४५६७८९", "0123456789" * 3)


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_DIGITS).lower()
    text = re.sub("[ً-ْٰـ]", "", text).translate(_ARABIC_VARIANTS)
    text = text.replace("ؤ", "و")
    text = re.sub(r"['’`ʿʾ]", "", text)
    return re.sub(r"[-_]", " ", text)


@dataclass(frozen=True)
class HadithRef:
    collection: str
    number: int
    sub: int | None = None  # Sahih Muslim narration letter (1 = a)

    @property
    def label(self) -> str:
        letter = chr(96 + self.sub) if self.sub else ""
        return f"{BY_KEY[self.collection].name} {self.number}{letter}"


@cache
def _muslim_numbers() -> dict[int, dict[int, int]]:
    path = Path(__file__).with_name("muslim_numbers.json")
    data = json.loads(path.read_text(encoding="utf-8"))["numbers"]
    return {int(n): {sub: number for sub, number in pairs} for n, pairs in data.items()}


def validated(collection: str, number: int, sub: int | None = None) -> HadithRef | None:
    item = BY_KEY.get(collection)
    if item is None or not 1 <= number <= item.last:
        return None
    if collection != "muslim":
        return HadithRef(collection, number)
    narrations = _muslim_numbers().get(number)
    if not narrations or (sub is not None and sub not in narrations):
        return None
    return HadithRef(collection, number, sub)


def _ordinal(text: str) -> int | None:
    numeric = re.search(r"\b(\d{1,4})\s*(?:st|nd|rd|th|vi|vin|wi|veen|ween)\b", text)
    if numeric:
        return int(numeric[1])
    for word in re.findall(r"[a-z]+", text):
        if word in _ORDINAL_WORDS:
            return _ORDINAL_WORDS[word]
    return None


def parse_reference(text: str) -> HadithRef | None:
    """Find one hadith reference ("Bukhari 1", "Sahih Muslim 2564b", "صحيح البخاري ١")."""
    folded = _fold(text)
    cue = bool(_CUE.search(folded))
    for item in COLLECTIONS:
        match = re.search(item.strong, folded, re.IGNORECASE)
        if match is None and item.weak:
            weak = re.search(item.weak, folded, re.IGNORECASE)
            # "Muslim 2564" alone, or with a hadith word; never "Muslim 5 waqt".
            short = weak is not None and len(re.findall(r"\w+", folded)) <= 3
            if weak is not None and (cue or short or re.search(r"[:#]\s*\d", folded)):
                match = weak
        if match is None:
            continue
        if not cue and re.search(r"\bimam\s*$|امام\s*$|इमाम\s*$", folded[: match.start()]):
            return None  # the scholar, not his book
        before, after = folded[: match.start()], folded[match.end() :]
        if item.titled:
            before, after = _TITLE.sub(" ", before), _TITLE.sub(" ", after)
        found = _AFTER.match(after[:48]) or _BEFORE.search(before[-48:])
        if found:
            number = int(found[1])
            letter = found[2] if item.key == "muslim" else None
            return validated(item.key, number, ord(letter) - 96 if letter else None)
        if cue and (ordinal := _ordinal(folded)) is not None:
            return validated(item.key, ordinal)
        return None
    return None


class HadithUnavailable(RuntimeError):
    pass


class HadithNotFound(RuntimeError):
    pass


_WEAK_GRADE = re.compile(
    r"da[ʿ'`]?[ie]e?f|daeef|weak|maud?u|mawdu|fabricat|munkar|shadh|batil|ضعيف|موضوع|منكر",
    re.IGNORECASE,
)


def is_weak(grade: str) -> bool:
    return bool(_WEAK_GRADE.search(grade))


def _edition_for(item: Collection, language: str) -> tuple[str, str]:
    if language == "ar":
        return "", ""
    if language == "ur" and item.urdu:
        return f"urd-{item.key}", "Urdu"
    return f"eng-{item.key}", "English"


def _clip(text: str) -> tuple[str, bool]:
    text = text.strip()
    if len(text) <= MAX_CHARS:
        return text, False
    cut = text[:MAX_CHARS]
    return cut[: cut.rfind(" ")] if " " in cut[-200:] else cut, True


def link(reference: HadithRef) -> str:
    item = BY_KEY[reference.collection]
    if not item.sunnah:
        return ""
    letter = ""
    if reference.collection == "muslim":
        narrations = _muslim_numbers().get(reference.number, {})
        if len(narrations) > 1:
            letter = chr(96 + (reference.sub or min(narrations)))
    return f"https://sunnah.com/{item.sunnah}:{reference.number}{letter}"


async def fetch(reference: HadithRef, language: str) -> dict:
    """Arabic text (+ translation) and grades, verbatim from the source."""
    item = BY_KEY[reference.collection]
    narrations: dict[int, int] = {}
    if reference.collection == "muslim":
        narrations = _muslim_numbers()[reference.number]
        sub = reference.sub or min(narrations)
        dataset_number = narrations[sub]
    else:
        sub, dataset_number = None, reference.number
    edition, translation_language = _edition_for(item, language)
    editions = [f"ara-{item.key}"] + ([edition] if edition else [])
    async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:

        async def one(name: str) -> dict:
            response = await client.get(f"{API}/editions/{name}/{dataset_number}.min.json")
            if response.status_code == 404:
                raise HadithNotFound(f"{reference.label} is not in this edition")
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("unexpected hadith payload")
            return data

        try:
            results = await asyncio.gather(*(one(name) for name in editions))
        except HadithNotFound:
            raise
        except (httpx.HTTPError, ValueError):
            raise HadithUnavailable("The hadith source is not reachable right now") from None
    try:
        arabic_data = results[0]["hadiths"][0]
        translated = results[1]["hadiths"][0] if len(results) > 1 else {}
        section = next(iter(results[0]["metadata"].get("section", {}).values()), "")
    except (KeyError, IndexError, TypeError):
        raise HadithUnavailable("The hadith source returned an unexpected format") from None
    arabic, arabic_clipped = _clip(str(arabic_data.get("text", "")))
    translation, translation_clipped = _clip(str(translated.get("text", "")))
    if not arabic:
        raise HadithNotFound(f"{reference.label} has no text in this edition")
    grades = [
        {"name": str(grade.get("name", "")), "grade": str(grade.get("grade", ""))}
        for grade in (translated or arabic_data).get("grades", []) or arabic_data.get("grades", [])
        if isinstance(grade, dict)
    ]
    shown = HadithRef(reference.collection, reference.number, sub)
    return {
        "reference": shown.label,
        "collection": item.name,
        "collection_arabic": item.arabic,
        "sahih_collection": item.sahih,
        "section": str(section),
        "book": (arabic_data.get("reference") or {}).get("book"),
        "in_book": (arabic_data.get("reference") or {}).get("hadith"),
        "arabic": arabic,
        "translation": translation,
        "translation_language": translation_language if translation else "",
        "clipped": arabic_clipped or translation_clipped,
        "grades": grades,
        "narrations": [f"{reference.number}{chr(96 + key)}" for key in sorted(narrations)]
        if len(narrations) > 1
        else [],
        "link": link(shown),
        "source": SOURCE,
    }
