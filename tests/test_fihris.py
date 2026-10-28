"""Fihris: MIZAN finds ayahs by their words, however they are spelled."""

import dataclasses

import pytest

from agents.specialized import create_agent
from security.izn import IznPermission
from tadbir import fahm, fihris, quran
from tests.test_tadbir import ScriptedProvider

# A few ayahs in all five views (the real index holds all 6236).
AYAHS = {
    (53, 14): (
        "عند سدرة المنتهى",
        "'Inda sidratil muntaha",
        "At the Lote Tree of the Utmost Boundary -",
        "سدرۃ المنتہیٰ کے پاس",
        "सिदरतुल मुन्तहा के पास",
    ),
    (108, 1): (
        "إنا أعطيناك الكوثر",
        "Innaa a'tainaa kal kauthar",
        "Indeed, We have granted you al-Kawthar.",
        "بےشک ہم نے تم کو کوثر عطا فرمائی ہے",
        "निश्चय ही हमने तुम्हें कौसर प्रदान किया",
    ),
    (2, 153): (
        "يا أيها الذين آمنوا استعينوا بالصبر والصلاة",
        "Yaaa aiyuhal lazeena aamanus ta'eenoo bissabri wassalaah",
        "O you who have believed, seek help through patience and prayer.",
        "اے ایمان والو صبر اور نماز سے مدد لیا کرو",
        "ऐ ईमान लानेवालो! धैर्य और नमाज़ से मदद प्राप्त करो",
    ),
    (24, 35): (
        "الله نور السماوات والأرض نور على نور",
        "Allahu noorus samaawaati wal ard nuurun 'alaa noor",
        "Allah is the Light of the heavens and the earth. Light upon light.",
        "خدا آسمانوں اور زمین کا نور ہے نور علی نور",
        "अल्लाह आकाशों और धरती का प्रकाश है प्रकाश पर प्रकाश",
    ),
    (105, 1): (
        "ألم تر كيف فعل ربك بأصحاب الفيل",
        "Alam tara kaifa fa'ala rabbuka bi ashaabil feel",
        "Have you not considered how your Lord dealt with the companions of the elephant?",
        "کیا تم نے نہیں دیکھا کہ تمہارے پروردگار نے ہاتھی والوں کے ساتھ کیا کیا",
        "क्या तुमने नहीं देखा कि तुम्हारे रब ने हाथीवालों के साथ कैसा बरताव किया",
    ),
    (2, 156): (
        "الذين إذا أصابتهم مصيبة قالوا إنا لله وإنا إليه راجعون",
        "Allazeena izaaa asaabathum museebatun qaalooo innaa lillaahi wa innaaa ilaihi raaji'oon",
        "Who, when disaster strikes them, say, Indeed we belong to Allah, and indeed to Him "
        "we will return.",
        "ان لوگوں پر جب کوئی مصیبت واقع ہوتی ہے تو کہتے ہیں کہ ہم خدا ہی کا مال ہیں",
        "जो लोग उस समय, जबकि उनपर कोई मुसीबत आती है, कहते है, हम तो अल्लाह ही के है",
    ),
}
# Ordinary ayahs, so that common words and letters are common.
FILLER = [
    (
        "ذلك الكتاب لا ريب فيه هدى للمتقين",
        "Zaalikal Kitaabu laa raiba feeh; hudal lilmuttaqeen",
        "This is the Book about which there is no doubt, a guidance for those conscious of Allah",
        "یہ کتاب اس میں کچھ شک نہیں کہ کلام خدا ہے",
        "यह किताब है जिसमें कोई सन्देह नहीं",
    ),
    (
        "الحمد لله رب العالمين",
        "Alhamdu lillaahi Rabbil 'aalameen",
        "All praise is due to Allah, Lord of the worlds",
        "سب طرح کی تعریف خدا ہی کو سزاوار ہے",
        "प्रशंसा अल्लाह ही के लिए है जो सारे संसार का रब है",
    ),
    (
        "وأقيموا الصلاة وآتوا الزكاة",
        "Wa aqeemus salaata wa aatuz zakaata",
        "And establish prayer and give zakah",
        "اور نماز پڑھا کرو اور زکوٰة دیا کرو",
        "और नमाज़ क़ायम करो और ज़कात दो",
    ),
]


def editions() -> dict[str, list[tuple[int, int, str]]]:
    rows = list(AYAHS.items()) + [((1, 100 + i), text) for i, text in enumerate(FILLER * 4)]
    return {
        view: [(surah, ayah, texts[index]) for (surah, ayah), texts in rows]
        for index, view in enumerate(fihris.EDITIONS)
    }


@pytest.fixture(scope="module")
def index():
    return fihris.build(editions())


@pytest.mark.parametrize(
    "query,found",
    [
        # Spelled the person's own way, not the transliteration's
        ("Sidratul muntaha kya hai", "53:14"),
        ("But quran has mentioned sidra tu munhtah", "53:14"),
        ("inna lillahi wa inna ilayhi rajiun", "2:156"),
        # How the request is phrased does not outweigh what it is about
        ("Quran me Kausar ka zikr", "108:1"),
        # Meaning, through a translation
        ("light upon light", "24:35"),
        ("Which surah mentions the elephant?", "105:1"),
        ("ayah about patience and prayer", "2:153"),
        # Arabic and Urdu script
        ("سدرة المنتهى", "53:14"),
        ("ہاتھی والوں کا ذکر", "105:1"),
    ],
)
def test_finds_the_ayah_by_its_words(index, query, found):
    assert index.search(query)[0].label == found


def test_the_way_of_asking_counts_less_than_the_topic(index):
    # Many request seeds say "quran"; none but one says "kausar".
    assert index.topic("quran") < 0.2 <= index.topic("kausar") == 1.0
    assert index.search("Quran me Kausar ka zikr")[0].words == ["kausar"]


def test_a_view_counts_by_the_share_of_the_query_it_reads(index):
    # "ka" is barely English; the English view must not decide the answer.
    assert index.search("Zul Qarnain ka qissa ka")[0].label != "1:100"


def test_no_shared_word_finds_nothing(index):
    assert [match for match in index.search("qqqq") if match.words] == []


def test_misaligned_editions_are_refused():
    broken = editions()
    broken["en"] = broken["en"][:-1]
    with pytest.raises(fihris.Unavailable):
        fihris.build(broken)


def test_a_reference_is_read_by_the_reference_recipe():
    assert fahm.understand("Surah Najm 14").intent == "quran"
    assert fahm.understand("Quran me Kausar ka zikr").intent == "quran_search"


@pytest.mark.parametrize("second,shown", [(5.1, False), (13.3, True)])
async def test_mizan_quotes_the_found_ayah_from_the_source(monkeypatch, tmp_path, second, shown):
    monkeypatch.setenv("MIZAN_ORCHESTRATION", "mizan")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "memory.db"))
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("agents.base.create_provider", lambda **kwargs: None)
    agent = create_agent("general", izn=IznPermission())
    agent.ai_client = ScriptedProvider(["Al-Kawthar is what Allah granted the Prophet."])

    async def find(query, limit=3):
        return fihris.Found(
            [
                fihris.Match(108, 1, 13.6, ["kausar"]),
                fihris.Match(67, 4, second, ["kausar"]),
                fihris.Match(54, 50, 4.0, ["kausar"]),
            ],
            [],
        )

    async def fetch(reference, language):
        assert (reference.surah, reference.start, reference.end) == (108, 1, 1)
        return {
            "reference": reference.label,
            "surah_arabic": "الكوثر",
            "ayahs": [
                {
                    "number": 1,
                    "arabic": "إِنَّآ أَعْطَيْنَٰكَ ٱلْكَوْثَرَ",
                    "translation": "Indeed, We have granted you al-Kawthar.",
                }
            ],
            "translation": "Saheeh International",
            "source": "api.alquran.cloud (Tanzil Uthmani text)",
        }

    monkeypatch.setattr(fihris, "find", find)
    monkeypatch.setattr(quran, "fetch", fetch)
    result = await agent.execute("Quran me Kausar ka zikr")
    text = result["result"]
    assert "إِنَّآ أَعْطَيْنَٰكَ ٱلْكَوْثَرَ ﴿1﴾" in text
    assert "kausar" in text
    # Another ayah is named only when it is about as likely as the best match.
    assert ("67:4" in text) is shown and "54:50" not in text
    # The model only answered from the translation; it never chose or wrote the ayah.
    assert "ٱلْكَوْثَرَ" not in str(agent.ai_client.requests)


async def test_no_match_says_so_and_quotes_nothing(monkeypatch, tmp_path):
    monkeypatch.setenv("MIZAN_ORCHESTRATION", "mizan")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "memory.db"))
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("agents.base.create_provider", lambda **kwargs: None)
    agent = create_agent("general", izn=IznPermission())
    agent.ai_client = ScriptedProvider()

    async def find(query, limit=3):
        return fihris.Found([], [])

    monkeypatch.setattr(fihris, "find", find)
    result = await agent.execute("Quran me Kausar ka zikr")
    # In the language asked in (Roman Hindi/Urdu here).
    assert "yaaddasht se nahi likhta" in result["result"]
    assert agent.ai_client.requests == []


class Letters:
    """The letter model's reading of a word: English or a spelling (stubbed;
    the real one is fitted on the 6236 ayahs' Saheeh and transliteration)."""

    def posterior(self, word):
        english = 0.95 if word in {"smartphones", "mentions", "quote"} else 0.05
        return {"en": english, "latn": 1 - english}


def test_words_no_ayah_uses_outweigh_the_best_match(index):
    index = dataclasses.replace(index, english=Letters())
    # "smartphones" is English and no translation uses it: no ayah says this,
    # however the letters of the transliteration happen to meet it.
    found = index.find("Which ayah mentions smartphones?")
    assert found.matches == [] and found.absent == ["smartphones"]
    assert found.nearest is not None
    # A word some view uses is never unused; a spelling is mostly a spelling.
    assert index.unused("elephant") == 0.0 and index.unused("kausar") < 0.5
    assert index.find("Quran me Kausar ka zikr").matches[0].label == "108:1"
    assert index.find("But quran has mentioned sidra tu munhtah").matches[0].label == "53:14"
    # When the words the Quran uses carry most of the query, the ayah is found.
    assert index.find("Quote the ayah that mentions the elephant").matches[0].label == "105:1"


async def test_no_ayah_says_it_plainly_and_quotes_nothing(monkeypatch, tmp_path):
    monkeypatch.setenv("MIZAN_ORCHESTRATION", "mizan")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "memory.db"))
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("agents.base.create_provider", lambda **kwargs: None)
    agent = create_agent("general", izn=IznPermission())
    agent.ai_client = ScriptedProvider()

    async def find(query, limit=3):
        return fihris.Found([], ["continents"], fihris.Match(12, 46, 11.6, ["seven", "continents"]))

    async def fetch(reference, language):
        raise AssertionError("the nearest ayah is named, never quoted as the answer")

    monkeypatch.setattr(fihris, "find", find)
    monkeypatch.setattr(quran, "fetch", fetch)
    result = await agent.execute("Quote the ayah where the Quran mentions the seven continents")
    text = result["result"]
    assert text.startswith("No ayah of the Quran says this.")
    assert "“continents”" in text and "“seven”" in text and "Yusuf 12:46" in text
    assert agent.ai_client.requests == []
