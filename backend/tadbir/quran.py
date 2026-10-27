"""Quran references: MIZAN's own surah index and an authentic text source.

Ayah text is never generated or rewritten by a language model. MIZAN parses
the reference itself, validates it against the surah index (Hafs count, 6236
ayahs) and fetches the Uthmani text with a translation from the public Tanzil
based API at api.alquran.cloud. The answer quotes that text verbatim.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

import httpx

# (Latin name, Arabic name, ayah count) in mushaf order.
SURAHS: tuple[tuple[str, str, int], ...] = (
    ("Al-Fatihah", "الفاتحة", 7), ("Al-Baqarah", "البقرة", 286),
    ("Aal-Imran", "آل عمران", 200), ("An-Nisa", "النساء", 176),
    ("Al-Ma'idah", "المائدة", 120), ("Al-An'am", "الأنعام", 165),
    ("Al-A'raf", "الأعراف", 206), ("Al-Anfal", "الأنفال", 75),
    ("At-Tawbah", "التوبة", 129), ("Yunus", "يونس", 109), ("Hud", "هود", 123),
    ("Yusuf", "يوسف", 111), ("Ar-Ra'd", "الرعد", 43), ("Ibrahim", "إبراهيم", 52),
    ("Al-Hijr", "الحجر", 99), ("An-Nahl", "النحل", 128), ("Al-Isra", "الإسراء", 111),
    ("Al-Kahf", "الكهف", 110), ("Maryam", "مريم", 98), ("Ta-Ha", "طه", 135),
    ("Al-Anbiya", "الأنبياء", 112), ("Al-Hajj", "الحج", 78),
    ("Al-Mu'minun", "المؤمنون", 118), ("An-Nur", "النور", 64),
    ("Al-Furqan", "الفرقان", 77), ("Ash-Shu'ara", "الشعراء", 227),
    ("An-Naml", "النمل", 93), ("Al-Qasas", "القصص", 88),
    ("Al-Ankabut", "العنكبوت", 69), ("Ar-Rum", "الروم", 60), ("Luqman", "لقمان", 34),
    ("As-Sajdah", "السجدة", 30), ("Al-Ahzab", "الأحزاب", 73), ("Saba", "سبأ", 54),
    ("Fatir", "فاطر", 45), ("Ya-Sin", "يس", 83), ("As-Saffat", "الصافات", 182),
    ("Sad", "ص", 88), ("Az-Zumar", "الزمر", 75), ("Ghafir", "غافر", 85),
    ("Fussilat", "فصلت", 54), ("Ash-Shura", "الشورى", 53),
    ("Az-Zukhruf", "الزخرف", 89), ("Ad-Dukhan", "الدخان", 59),
    ("Al-Jathiyah", "الجاثية", 37), ("Al-Ahqaf", "الأحقاف", 35),
    ("Muhammad", "محمد", 38), ("Al-Fath", "الفتح", 29), ("Al-Hujurat", "الحجرات", 18),
    ("Qaf", "ق", 45), ("Adh-Dhariyat", "الذاريات", 60), ("At-Tur", "الطور", 49),
    ("An-Najm", "النجم", 62), ("Al-Qamar", "القمر", 55), ("Ar-Rahman", "الرحمن", 78),
    ("Al-Waqi'ah", "الواقعة", 96), ("Al-Hadid", "الحديد", 29),
    ("Al-Mujadilah", "المجادلة", 22), ("Al-Hashr", "الحشر", 24),
    ("Al-Mumtahanah", "الممتحنة", 13), ("As-Saff", "الصف", 14),
    ("Al-Jumu'ah", "الجمعة", 11), ("Al-Munafiqun", "المنافقون", 11),
    ("At-Taghabun", "التغابن", 18), ("At-Talaq", "الطلاق", 12),
    ("At-Tahrim", "التحريم", 12), ("Al-Mulk", "الملك", 30), ("Al-Qalam", "القلم", 52),
    ("Al-Haqqah", "الحاقة", 52), ("Al-Ma'arij", "المعارج", 44), ("Nuh", "نوح", 28),
    ("Al-Jinn", "الجن", 28), ("Al-Muzzammil", "المزمل", 20),
    ("Al-Muddaththir", "المدثر", 56), ("Al-Qiyamah", "القيامة", 40),
    ("Al-Insan", "الإنسان", 31), ("Al-Mursalat", "المرسلات", 50),
    ("An-Naba", "النبأ", 40), ("An-Nazi'at", "النازعات", 46), ("Abasa", "عبس", 42),
    ("At-Takwir", "التكوير", 29), ("Al-Infitar", "الانفطار", 19),
    ("Al-Mutaffifin", "المطففين", 36), ("Al-Inshiqaq", "الانشقاق", 25),
    ("Al-Buruj", "البروج", 22), ("At-Tariq", "الطارق", 17), ("Al-A'la", "الأعلى", 19),
    ("Al-Ghashiyah", "الغاشية", 26), ("Al-Fajr", "الفجر", 30), ("Al-Balad", "البلد", 20),
    ("Ash-Shams", "الشمس", 15), ("Al-Layl", "الليل", 21), ("Ad-Duha", "الضحى", 11),
    ("Ash-Sharh", "الشرح", 8), ("At-Tin", "التين", 8), ("Al-Alaq", "العلق", 19),
    ("Al-Qadr", "القدر", 5), ("Al-Bayyinah", "البينة", 8),
    ("Az-Zalzalah", "الزلزلة", 8), ("Al-Adiyat", "العاديات", 11),
    ("Al-Qari'ah", "القارعة", 11), ("At-Takathur", "التكاثر", 8), ("Al-Asr", "العصر", 3),
    ("Al-Humazah", "الهمزة", 9), ("Al-Fil", "الفيل", 5), ("Quraysh", "قريش", 4),
    ("Al-Ma'un", "الماعون", 7), ("Al-Kawthar", "الكوثر", 3),
    ("Al-Kafirun", "الكافرون", 6), ("An-Nasr", "النصر", 3), ("Al-Masad", "المسد", 5),
    ("Al-Ikhlas", "الإخلاص", 4), ("Al-Falaq", "الفلق", 5), ("An-Nas", "الناس", 6),
)  # fmt: skip

# Common alternative spellings (normalized on lookup).
ALIASES = {
    "fatiha": 1, "alhamd": 1, "baqara": 2, "imran": 3, "aliimran": 3, "nisaa": 4,
    "maida": 5, "anaam": 6, "araaf": 7, "tauba": 9, "taubah": 9, "baraah": 9,
    "younus": 10, "yousuf": 12, "raad": 13, "bani israil": 17, "baniisrail": 17,
    "kahaf": 18, "taha": 20, "mominun": 23, "muminoon": 23, "noor": 24,
    "shuara": 26, "ankaboot": 29, "room": 30, "sajda": 32, "yasin": 36, "yaseen": 36,
    "saffaat": 37, "suad": 38, "mumin": 40, "hamimsajdah": 41, "fussilat": 41,
    "shoora": 42, "zukhruf": 43, "dukhaan": 44, "jasiyah": 45, "hujraat": 49,
    "zariyat": 51, "toor": 52, "rehman": 55, "rahman": 55, "waqia": 56, "waqiah": 56,
    "mujadila": 58, "mumtahina": 60, "juma": 62, "jumma": 62, "munafiqoon": 63,
    "tahreem": 66, "haaqqa": 69, "maarij": 70, "nooh": 71, "muzammil": 73,
    "mudassir": 74, "qiyama": 75, "dahr": 76, "insaan": 76, "mursalaat": 77,
    "nabaa": 78, "naziat": 79, "abas": 80, "takweer": 81, "infitaar": 82,
    "mutaffifeen": 83, "inshiqaaq": 84, "burooj": 85, "taariq": 86, "aala": 87,
    "ghashiya": 88, "shams": 91, "lail": 92, "zuha": 93, "duha": 93, "inshirah": 94,
    "alamnashrah": 94, "teen": 95, "alaq": 96, "iqra": 96, "bayyina": 98,
    "zilzal": 99, "zilzaal": 99, "aadiyat": 100, "qaria": 101, "takasur": 102,
    "takathur": 102, "asr": 103, "humaza": 104, "feel": 105, "quraish": 106,
    "maoon": 107, "kausar": 108, "kauthar": 108, "kafiroon": 109, "kafirun": 109,
    "lahab": 111, "tabbat": 111, "ikhlaas": 112, "qulhuwallah": 112, "falak": 113,
    "naas": 114,
}  # fmt: skip

# Common Devanagari spellings.
ALIASES.update(
    {
        "फातिहा": 1, "फ़ातिहा": 1, "बकरा": 2, "बक़रा": 2, "बकरह": 2, "कहफ": 18, "कहफ़": 18,
        "यासीन": 36, "रहमान": 55, "वाकिआ": 56, "वाक़िआ": 56, "मुल्क": 67, "अस्र": 103,
        "कौसर": 108, "काफिरून": 109, "नस्र": 110, "इखलास": 112, "इख़लास": 112, "फलक": 113,
        "फ़लक़": 113, "नास": 114,
    }
)  # fmt: skip

# Common Urdu spellings.
ALIASES.update({"يسين": 36, "یٰسین": 36, "فاتحہ": 1, "بقرہ": 2, "رحمٰن": 55, "کہف": 18, "واقعہ": 56})

# Ayahs widely known by name.
NAMED_AYAHS = {
    "ayatulkursi": (2, 255),
    "ayatalkursi": (2, 255),
    "ayetelkursi": (2, 255),
    "آيةالكرسي": (2, 255),
    "آیتالکرسی": (2, 255),
}

TRANSLATIONS = {
    "en": "en.sahih",
    "hi-latn": "en.sahih",
    "ur": "ur.jalandhry",
    "hi": "hi.hindi",
    "ar": "",
}
TRANSLATION_NAMES = {
    "en.sahih": "Saheeh International",
    "ur.jalandhry": "Fateh Muhammad Jalandhry",
    "hi.hindi": "Suhel Farooq Khan and Saifur Rahman Nadwi",
}
API = "https://api.alquran.cloud/v1"
BASMALA = "بِسْمِ ٱللَّهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ"
MAX_AYAHS = 10
TOTAL_AYAHS = 6236


# Urdu/Persian letter forms and hamza seats fold to one spelling for lookup.
_ARABIC_VARIANTS = str.maketrans(
    {
        "ی": "ي",
        "ى": "ي",
        "ے": "ي",
        "ک": "ك",
        "ہ": "ه",
        "ۃ": "ه",
        "ة": "ه",
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ٱ": "ا",
    }
)


def _key(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    if re.search(r"[؀-ۿ]", text):
        stripped = re.sub("[\\s\u064b-\u0652\u0670\u0640]+", "", text)
        return stripped.translate(_ARABIC_VARIANTS)
    if re.search("[\u0900-\u097f]", text):
        return re.sub("[\\s\u093c]+", "", text).removeprefix("सूरह").removeprefix("सूरा")
    text = re.sub(r"[^a-z ]+", "", text.replace("-", " "))
    words = [w for w in text.split() if w not in {"surah", "surat", "sura", "soorah"}]
    if words and words[0] in {
        "al",
        "an",
        "ash",
        "ad",
        "at",
        "ar",
        "as",
        "az",
        "adh",
        "aal",
        "ul",
        "el",
    }:
        words = words[1:]
    joined = "".join(words)
    joined = re.sub(r"(.)\1+", r"\1", joined)
    return joined[:-1] if joined.endswith("h") and len(joined) > 3 else joined


_INDEX: dict[str, int] = {}
for _number, (_latin, _arabic, _count) in enumerate(SURAHS, start=1):
    _INDEX[_key(_latin)] = _number
    _INDEX[_key(_arabic)] = _number
    _INDEX[_key("ال" + _arabic) if not _arabic.startswith("ال") else _key(_arabic[2:])] = _number
for _alias, _number in ALIASES.items():
    _INDEX[_key(_alias)] = _number


def surah_number(name: str) -> int | None:
    key = _key(name)
    return _INDEX.get(key) if key else None


@dataclass(frozen=True)
class Reference:
    surah: int
    start: int | None  # None: the whole surah
    end: int | None

    @property
    def label(self) -> str:
        name = SURAHS[self.surah - 1][0]
        if self.start is None:
            return f"Surah {name} ({self.surah})"
        span = f"{self.start}" if self.end in (None, self.start) else f"{self.start}-{self.end}"
        return f"Surah {name} {self.surah}:{span}"


_NUMERIC = re.compile(r"(?<![\d.])(\d{1,3})\s*[:：]\s*(\d{1,3})(?:\s*[-–]\s*(\d{1,3}))?(?![\d.])")
_SURAH_WORD = r"(?:surah|surat|sura|soorah|سورة|سورہ|सूरह|सूरा|सूरत)"
_AYAH_WORD = r"(?:ayah|ayat|aayat|ayaat|verse|verses|آية|آیت|آيت|आयत)"


_ORDINAL_WORDS = {
    "pehli": 1, "pahli": 1, "first": 1, "doosri": 2, "dusri": 2, "second": 2, "teesri": 3,
    "tisri": 3, "third": 3, "chauthi": 4, "fourth": 4, "paanchvi": 5, "panchvi": 5, "fifth": 5,
    "chhathi": 6, "chhati": 6, "sixth": 6, "saatvi": 7, "satvi": 7, "seventh": 7,
    "aathvi": 8, "athvi": 8, "eighth": 8, "nauvi": 9, "nauvin": 9, "ninth": 9, "dasvi": 10,
    "daswi": 10, "tenth": 10, "gyarahvi": 11, "eleventh": 11, "barahvi": 12, "twelfth": 12,
    "terahvi": 13, "tehravi": 13, "thirteenth": 13, "chaudahvi": 14, "fourteenth": 14,
    "pandrahvi": 15, "fifteenth": 15, "solahvi": 16, "sixteenth": 16, "satrahvi": 17,
    "seventeenth": 17, "atharahvi": 18, "eighteenth": 18, "unnisvi": 19, "nineteenth": 19,
    "beesvi": 20, "twentieth": 20,
}  # fmt: skip


def ordinal_ayah(text: str) -> int | None:
    """An ayah given as an ordinal ("13th", "13vi", "terahvi"), next to an ayah word."""
    if not re.search(_AYAH_WORD, text, re.IGNORECASE):
        return None
    numeric = re.search(
        r"\b(\d{1,3})\s*(?:st|nd|rd|th|vi|vin|wi|wa|va|wan|ween|vein|veen)\b", text, re.I
    )
    if numeric:
        return int(numeric[1])
    for word in re.findall(r"[a-z]+", text.lower()):
        if word in _ORDINAL_WORDS:
            return _ORDINAL_WORDS[word]
    return None


def parse_reference(text: str) -> Reference | None:
    """Find one Quran reference in free text (digits, names, Arabic or Urdu)."""
    compact = _key(text)
    for name, (surah, ayah) in NAMED_AYAHS.items():
        if _key(name) and _key(name) in compact:
            return Reference(surah, ayah, ayah)
    if re.search(_SURAH_WORD + r"|\b(?:quran|qur'an|ayah|ayat)\b|قرآن|आयत", text, re.IGNORECASE):
        match = _NUMERIC.search(text)
        if match:
            return _validated(int(match[1]), int(match[2]), int(match[3] or match[2]))
    elif match := re.fullmatch(
        r"\s*(\d{1,3})\s*[:：]\s*(\d{1,3})(?:\s*[-–]\s*(\d{1,3}))?\s*\??\s*", text
    ):
        return _validated(int(match[1]), int(match[2]), int(match[3] or match[2]))
    named = re.search(
        _SURAH_WORD + r"\s+([^\d,.;:!?()]{2,40})(?:(?:" + _AYAH_WORD + r"\s*)?(\d{1,3})"
        r"(?:\s*[-–]\s*(\d{1,3}))?)?(?=[\s,.;:!?()]|$)",
        text,
        re.IGNORECASE,
    )
    if named:
        words = named[1].split()
        # Longest name prefix that is a known surah (names have 1-3 words).
        for size in range(min(3, len(words)), 0, -1):
            number = surah_number(" ".join(words[:size]))
            if number:
                if named[2]:
                    return _validated(number, int(named[2]), int(named[3] or named[2]))
                ordinal = ordinal_ayah(text)
                if ordinal is not None:
                    return _validated(number, ordinal, ordinal)
                return Reference(number, None, None)
        if words and words[0].isdigit():
            return _validated(int(words[0]), None, None)
    numbered = re.search(_SURAH_WORD + r"\s+(\d{1,3})(?:\D+?(\d{1,3}))?", text, re.IGNORECASE)
    if numbered:
        if numbered[2] and re.search(_AYAH_WORD, text, re.IGNORECASE):
            return _validated(int(numbered[1]), int(numbered[2]), int(numbered[2]))
        return _validated(int(numbered[1]), None, None)
    return None


def _validated(surah: int, start: int | None, end: int | None) -> Reference | None:
    if not 1 <= surah <= 114:
        return None
    count = SURAHS[surah - 1][2]
    if start is None:
        return Reference(surah, None, None)
    end = end or start
    if not 1 <= start <= end <= count:
        return None
    return Reference(surah, start, end)


def strip_basmala(text: str) -> str:
    """Remove a leading Basmala, comparing canonically (mark order varies by source)."""
    words = text.split(" ")
    target = unicodedata.normalize("NFC", BASMALA)
    if len(words) > 4 and unicodedata.normalize("NFC", " ".join(words[:4])) == target:
        return " ".join(words[4:]).strip()
    return text


class QuranUnavailable(RuntimeError):
    pass


async def fetch(reference: Reference, language: str) -> dict:
    """Uthmani text (+ translation) for the reference, verbatim from the source."""
    translation = TRANSLATIONS.get(language, "en.sahih")
    editions = "quran-uthmani" + (f",{translation}" if translation else "")
    surah_count = SURAHS[reference.surah - 1][2]
    start = reference.start or 1
    end = reference.end or surah_count
    requested = end - start + 1
    # Long passages are shown in parts; the reply says which part.
    end = min(end, start + MAX_AYAHS - 1)
    ayahs: list[dict] = []
    async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
        if reference.start is None:
            urls = [f"{API}/surah/{reference.surah}/editions/{editions}?offset=0&limit={MAX_AYAHS}"]
        else:
            urls = [
                f"{API}/ayah/{reference.surah}:{number}/editions/{editions}"
                for number in range(start, end + 1)
            ]
        for url in urls:
            try:
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()["data"]
            except (httpx.HTTPError, KeyError, ValueError):
                raise QuranUnavailable("The Quran text source is not reachable right now") from None
            if reference.start is None:
                arabic, *rest = data
                for index, item in enumerate(arabic["ayahs"]):
                    ayahs.append(
                        {
                            "number": item["numberInSurah"],
                            "arabic": item["text"],
                            "translation": rest[0]["ayahs"][index]["text"] if rest else "",
                        }
                    )
            else:
                arabic, *rest = data
                ayahs.append(
                    {
                        "number": arabic["numberInSurah"],
                        "arabic": arabic["text"],
                        "translation": rest[0]["text"] if rest else "",
                    }
                )
    for ayah in ayahs:
        # A byte-order mark is a source artifact, not part of the text.
        ayah["arabic"] = ayah["arabic"].lstrip("\ufeff").strip()
        ayah["translation"] = ayah["translation"].lstrip("\ufeff").strip()
        # The source prefixes ayah 1 with the Basmala; it is part of the text
        # only in Al-Fatihah.
        if reference.surah != 1 and ayah["number"] == 1:
            ayah["arabic"] = strip_basmala(ayah["arabic"])
    return {
        "reference": reference.label,
        "surah": reference.surah,
        "surah_name": SURAHS[reference.surah - 1][0],
        "surah_arabic": SURAHS[reference.surah - 1][1],
        "ayahs": ayahs,
        "translation": TRANSLATION_NAMES.get(translation, ""),
        "source": "api.alquran.cloud (Tanzil Uthmani text)",
        "shown": (start, start + len(ayahs) - 1),
        "requested": requested,
        "total": surah_count,
    }
