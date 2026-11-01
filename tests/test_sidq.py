"""Sidq, the Truth Gate: what MIZAN can prove wrong never reaches the user."""

import pytest

from tadbir import isnad, muhasaba, sidq

REAL_DEAD_LINKS = sidq.dead_links  # the tests below replace it with an offline stand-in
REAL_SCRIPTURE = muhasaba.scripture


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    async def no_links(urls, timeout=4.0):
        return [url for url in urls if "made-up" in url]

    monkeypatch.setattr(sidq, "dead_links", no_links)

    async def no_source(text):
        return []

    monkeypatch.setattr("tadbir.muhasaba.scripture", no_source)


async def test_wrong_arithmetic_is_corrected(monkeypatch):
    monkeypatch.setenv("MIZAN_TRUTH_GATE", "strict")
    text, report = await sidq.gate("So 12 * 12 = 154, which is the area.")
    assert "12 * 12 = 144" in text and "154" not in text
    assert report["corrected"][0]["kind"] == "arithmetic"
    # The note is shown under the answer, never added to its text.
    assert "Truth Gate" in report["note"] and "Truth Gate" not in text


async def test_flag_mode_keeps_the_text_and_marks_it(monkeypatch):
    monkeypatch.setenv("MIZAN_TRUTH_GATE", "flag")
    text, report = await sidq.gate("So 12 * 12 = 154.")
    assert "= 154" in text and report["flagged"] and not report["corrected"]


async def test_an_action_with_no_receipt_is_removed(monkeypatch):
    monkeypatch.setenv("MIZAN_TRUTH_GATE", "strict")
    answer = "The total is 10. I ran the code and verified it in the sandbox."
    ledger = isnad.ledger(answer)
    text, report = await sidq.gate(answer, ledger)
    assert "I ran the code" not in text and "The total is 10." in text
    assert report["removed"][0]["kind"] == "action"


async def test_a_link_that_does_not_exist_is_removed(monkeypatch):
    monkeypatch.setenv("MIZAN_TRUTH_GATE", "strict")
    answer = "See [the guide](https://made-up.example/guide) and https://quran.com/2/255 too."
    text, report = await sidq.gate(answer, isnad.ledger(answer))
    assert "made-up" not in text and "the guide" in text and "https://quran.com/2/255" in text
    assert report["links"]["dead"] == ["https://made-up.example/guide"]


async def test_off_and_correct_answers_pass_untouched(monkeypatch):
    monkeypatch.setenv("MIZAN_TRUTH_GATE", "off")
    assert await sidq.gate("2 + 2 = 5") == ("2 + 2 = 5", {})
    monkeypatch.setenv("MIZAN_TRUTH_GATE", "strict")
    text, report = await sidq.gate("2 + 2 = 4, as expected.")
    assert text == "2 + 2 = 4, as expected." and report == {"mode": "strict", "passed": True}


async def test_an_altered_quote_is_replaced_by_the_source(monkeypatch):
    monkeypatch.setenv("MIZAN_TRUTH_GATE", "strict")
    source = "قُلْ هُوَ اللَّهُ أَحَدٌ"

    async def differs(text):
        return [{"kind": "quote", "reference": "Quran 112:1", "source": source}]

    monkeypatch.setattr("tadbir.muhasaba.scripture", differs)
    text, report = await sidq.gate("Surah 112:1 says:\nقل هو الله واحد احد\nThat is tawhid.")
    assert f"> {source}" in text and "واحد" not in text and "That is tawhid." in text
    assert report["corrected"][0]["kind"] == "quote"


async def test_the_gate_runs_on_words_only_answers(monkeypatch, tmp_path):
    from agents.specialized import create_agent
    from providers import BaseLLMProvider, ContentBlock, LLMResponse
    from security.izn import IznPermission

    class Model(BaseLLMProvider):
        provider_name = "fixture"

        def create(self, **kwargs):
            return LLMResponse([ContentBlock(type="text", text="7 * 8 = 54.")], model="fixture")

    monkeypatch.setenv("MIZAN_ORCHESTRATION", "llm")
    monkeypatch.setenv("MIZAN_TRUTH_GATE", "strict")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "m.db"))
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("agents.base.create_provider", lambda **kwargs: None)
    agent = create_agent("general", izn=IznPermission())
    agent.ai_client = Model()
    monkeypatch.setattr(agent, "get_tool_schemas", lambda: [])
    result = await agent.execute("What is seven times eight, in words?")
    assert "7 * 8 = 56" in result["result"]
    assert result["usage"]["sidq"]["corrected"]


def test_every_learning_step_reaches_the_live_record():
    from types import SimpleNamespace

    from security.auth import bind_principal, reset_principal
    from tadbir import sijill, trace

    sijill.clear("u-live")
    tokens = bind_principal(SimpleNamespace(user_id="u-live", roles=["user"]))
    try:
        trace.event("learn", "hifz", kept=True, language="python")  # traced or not
        trace.event("verify", "furqan")  # not a learning step
        trace.event("learn", "majlis", agent="Katib", intent="build_and_run", worked=True)
    finally:
        reset_principal(tokens)
    notes = sijill.since("u-live")
    assert [note["kind"] for note in notes] == ["hifz", "majlis"]
    assert notes[0]["summary"] == "Kept a verified python program to re-run next time"
    assert "Katib" in notes[1]["summary"] and notes[1]["summary"].endswith("worked")
    assert sijill.since("u-live", after=notes[0]["seq"]) == notes[1:]
    assert sijill.since("someone-else") == []


async def test_every_redirect_hop_is_checked_and_a_private_one_is_not_followed(monkeypatch):
    import httpx

    from connectors import net_guard

    async def public(url, **kwargs):
        return None

    async def pinned(url):
        host = httpx.URL(url).host
        if host == "internal.example":
            raise ValueError("URL resolves to a non-public address")
        return httpx.URL(url), host, host

    asked = []

    def handler(request):
        host = request.headers["host"]
        asked.append(host)
        routes = {
            "a.example": httpx.Response(302, headers={"location": "http://internal.example/"}),
            "b.example": httpx.Response(301, headers={"location": "https://c.example/gone"}),
            "c.example": httpx.Response(404),
        }
        return routes.get(host, httpx.Response(200))

    real = httpx.AsyncClient
    monkeypatch.setattr(net_guard, "check_url", public)
    monkeypatch.setattr(net_guard, "pinned_destination", pinned)
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw)
    )
    dead = await REAL_DEAD_LINKS(["https://a.example/x", "https://b.example/y"])
    assert dead == ["https://b.example/y"]  # moved, then gone
    assert "internal.example" not in asked  # the private hop was never opened


SOURCES = {
    (112, 1): "قُلْ هُوَ اللَّهُ أَحَدٌ",
    (2, 255): "اللَّهُ لَا إِلَٰهَ إِلَّا هُوَ الْحَيُّ الْقَيُّومُ",
}


@pytest.fixture
def mushaf(monkeypatch):
    """MIZAN's Quran source, offline; the real quote check reads it."""
    from tadbir import muhasaba, quran

    async def fetch(reference, language):
        arabic = SOURCES[(reference.surah, reference.start)]
        return {
            "reference": f"Quran {reference.surah}:{reference.start}",
            "ayahs": [{"arabic": arabic}],
        }

    monkeypatch.setattr(quran, "fetch", fetch)
    monkeypatch.setattr(muhasaba, "scripture", REAL_SCRIPTURE)


ANSWER = (
    "Surah 112:1:\nقل هو الله احد\nThat is tawhid.\n\n"
    "Surah 2:255:\nالله لا اله الا هو الحي القيوم\nThat is Ayat al-Kursi."
)


async def test_each_quote_is_checked_against_the_reference_it_is_given_under(mushaf):
    from tadbir import muhasaba

    # Two right quotes under two references: nothing to correct (it used to be
    # checked against the first reference only, and flagged).
    assert await muhasaba.scripture(ANSWER) == []
    text, report = await sidq.gate(ANSWER)
    assert text == ANSWER and report.get("passed") is True


async def test_arabic_words_in_an_explanation_are_not_a_misquote(mushaf):
    from tadbir import muhasaba

    answer = (
        "In Surah 2:255 the word القيوم means the One who sustains all, and the "
        "phrase لا تأخذه سنة says He never tires."
    )
    assert await muhasaba.scripture(answer) == []


async def test_every_altered_quote_is_replaced_by_its_own_source(mushaf, monkeypatch):
    monkeypatch.setenv("MIZAN_TRUTH_GATE", "strict")
    altered = ANSWER.replace("قل هو الله احد", "قل هو الله واحد").replace(
        "الحي القيوم", "الرحمن الرحيم"
    )
    text, report = await sidq.gate(altered)
    assert f"> {SOURCES[(112, 1)]}" in text and f"> {SOURCES[(2, 255)]}" in text
    assert "واحد" not in text and "الرحمن" not in text
    assert text.index(SOURCES[(112, 1)]) < text.index("That is tawhid.")
    assert text.index(SOURCES[(2, 255)]) < text.index("That is Ayat al-Kursi.")
    assert len(report["corrected"]) == 2


# MIZAN's Quran offline: the Uthmani text quran.fetch gives (the Basmala taken
# from ayah 1), and the common-script edition Iqtibas reads to find an ayah by
# its words (it spells الأقصى where the Uthmani writes ٱلْأَقْصَا).
UTHMANI = {
    (2, 255): (
        "ٱللَّهُ لَآ إِلَٰهَ إِلَّا هُوَ ٱلْحَىُّ ٱلْقَيُّومُ ۚ لَا تَأْخُذُهُۥ سِنَةٌۭ وَلَا نَوْمٌۭ ۚ "
        "لَّهُۥ مَا فِى ٱلسَّمَٰوَٰتِ وَمَا فِى ٱلْأَرْضِ ۗ مَن ذَا ٱلَّذِى يَشْفَعُ عِندَهُۥٓ إِلَّا "
        "بِإِذْنِهِۦ ۚ يَعْلَمُ مَا بَيْنَ أَيْدِيهِمْ وَمَا خَلْفَهُمْ ۖ وَلَا يُحِيطُونَ بِشَىْءٍۢ "
        "مِّنْ عِلْمِهِۦٓ إِلَّا بِمَا شَآءَ ۚ وَسِعَ كُرْسِيُّهُ ٱلسَّمَٰوَٰتِ وَٱلْأَرْضَ ۖ وَلَا "
        "يَـُٔودُهُۥ حِفْظُهُمَا ۚ وَهُوَ ٱلْعَلِىُّ ٱلْعَظِيمُ"
    ),
    (37, 35): "إِنَّهُمْ كَانُوٓا۟ إِذَا قِيلَ لَهُمْ لَآ إِلَٰهَ إِلَّا ٱللَّهُ يَسْتَكْبِرُونَ",
    (17, 1): (
        "سُبْحَٰنَ ٱلَّذِىٓ أَسْرَىٰ بِعَبْدِهِۦ لَيْلًۭا مِّنَ ٱلْمَسْجِدِ ٱلْحَرَامِ إِلَى "
        "ٱلْمَسْجِدِ ٱلْأَقْصَا ٱلَّذِى بَٰرَكْنَا حَوْلَهُۥ لِنُرِيَهُۥ مِنْ ءَايَٰتِنَآ ۚ إِنَّهُۥ "
        "هُوَ ٱلسَّمِيعُ ٱلْبَصِيرُ"
    ),
}
EDITION = {
    (2, 255): (
        "الله لا إله إلا هو الحي القيوم ۚ لا تأخذه سنة ولا نوم ۚ له ما في السماوات وما في "
        "الأرض ۗ من ذا الذي يشفع عنده إلا بإذنه ۚ يعلم ما بين أيديهم وما خلفهم ۖ ولا يحيطون "
        "بشيء من علمه إلا بما شاء ۚ وسع كرسيه السماوات والأرض ۖ ولا يئوده حفظهما ۚ وهو العلي "
        "العظيم"
    ),
    (37, 35): "إنهم كانوا إذا قيل لهم لا إله إلا الله يستكبرون",
    (17, 1): (
        "بسم الله الرحمن الرحيم سبحان الذي أسرى بعبده ليلا من المسجد الحرام إلى المسجد "
        "الأقصى الذي باركنا حوله لنريه من آياتنا ۚ إنه هو السميع البصير"
    ),
}
# Ayat al-Kursi as an answer writes it in the common script.
KURSI = (
    "اللَّهُ لَا إِلَٰهَ إِلَّا هُوَ الْحَيُّ الْقَيُّومُ ۚ لَا تَأْخُذُهُ سِنَةٌ وَلَا نَوْمٌ ۚ لَهُ مَا "
    "فِي السَّمَاوَاتِ وَمَا فِي الْأَرْضِ ۗ مَنْ ذَا الَّذِي يَشْفَعُ عِنْدَهُ إِلَّا بِإِذْنِهِ ۚ "
    "يَعْلَمُ مَا بَيْنَ أَيْدِيهِمْ وَمَا خَلْفَهُمْ ۖ وَلَا يُحِيطُونَ بِشَيْءٍ مِنْ عِلْمِهِ إِلَّا "
    "بِمَا شَاءَ ۚ وَسِعَ كُرْسِيُّهُ السَّمَاوَاتِ وَالْأَرْضَ ۖ وَلَا يَئُودُهُ حِفْظُهُمَا ۚ وَهُوَ "
    "الْعَلِيُّ الْعَظِيمُ"
)
# Words in the mushaf's script that no ayah says.
INVENTED = "وَٱلْقَمَرُ ٱلْمُنِيرُ يَسْكُنُ فِى ٱلسَّحَابِ ٱلْأَخْضَرِ"


@pytest.fixture
def quran_text(monkeypatch):
    """MIZAN's Quran source and the text it finds ayahs in, offline."""
    from tadbir import fihris, iqtibas, muhasaba, quran

    async def fetch(reference, language):
        ayahs = range(reference.start, reference.end + 1)
        return {
            "reference": reference.label,
            "ayahs": [{"arabic": UTHMANI[(reference.surah, n)]} for n in ayahs],
        }

    monkeypatch.setattr(quran, "fetch", fetch)
    monkeypatch.setattr(muhasaba, "scripture", REAL_SCRIPTURE)
    rows = [(surah, ayah, text) for (surah, ayah), text in EDITION.items()]
    monkeypatch.setattr(iqtibas, "_quotes", iqtibas.build({v: rows for v in fihris.EDITIONS}))


async def test_one_word_changed_in_a_long_ayah_is_replaced(quran_text, monkeypatch):
    monkeypatch.setenv("MIZAN_TRUTH_GATE", "strict")
    words = KURSI.split()
    words[3] = "الْعَلِيمُ"  # in place of إِلَّا: 49 of 50 words used to "match"
    answer = "Ayat al-Kursi (2:255):\n" + " ".join(words) + "\nIt is the greatest ayah."
    text, report = await sidq.gate(answer)
    assert "الْعَلِيمُ هُوَ" not in text and f"> {UTHMANI[(2, 255)]}" in text
    assert report["corrected"][0]["kind"] == "quote"


async def test_an_altered_ayah_given_without_a_reference_is_checked(quran_text, monkeypatch):
    from tadbir import muhasaba

    monkeypatch.setenv("MIZAN_TRUTH_GATE", "strict")
    words = KURSI.split()
    words[3] = "الْعَلِيمُ"
    answer = "Allah says:\n" + " ".join(words) + "\nIt is the greatest ayah."
    (finding,) = await muhasaba.scripture(answer)
    assert finding["unreferenced"] and finding["reference"] == "Surah Al-Baqarah 2:255"
    assert finding["changed"][0]["given"] == "الْعَلِيمُ"
    text, report = await sidq.gate(answer)
    assert f"> {UTHMANI[(2, 255)]}" in text and "It is the greatest ayah." in text
    assert "without a reference" in report["corrected"][0]["detail"]


async def test_an_exact_ayah_or_a_formula_given_without_a_reference_passes(quran_text):
    from tadbir import muhasaba

    for answer in (
        f"Allah says:\n{KURSI}\nIt is the greatest ayah.",
        f"Allah says:\n{UTHMANI[(2, 255)]}",
        # A formula that shares four words with 37:35 is not given as that ayah.
        "The shahada is لا إله إلا الله محمد رسول الله, the first pillar.",
    ):
        assert await muhasaba.scripture(answer) == []
        text, report = await sidq.gate(answer)
        assert text == answer and report.get("passed") is True


async def test_invented_words_in_the_mushafs_script_are_marked(quran_text, monkeypatch):
    for mode in ("strict", "flag"):
        monkeypatch.setenv("MIZAN_TRUTH_GATE", mode)
        answer = f"The Quran says:\n{INVENTED}\nThis is about the moon."
        text, report = await sidq.gate(answer)
        assert text == answer  # marked under the answer, never rewritten
        (item,) = report["flagged"]
        assert item["kind"] == "mushaf_script" and "ٱلسَّحَابِ" in item["detail"]


async def test_mizans_own_uthmani_quote_is_never_marked(quran_text):
    # 17:1 is spelled ٱلْأَقْصَا in the Uthmani text and الأقصى in the edition
    # MIZAN finds ayahs in: the quote is read against its source, not marked.
    for answer in (
        f"**Surah Al-Isra 17:1**\n\n> {UTHMANI[(17, 1)]}\n\nGlory be to Him.",
        f"> {UTHMANI[(17, 1)]}",
        f"> {UTHMANI[(2, 255)]}",
    ):
        text, report = await sidq.gate(answer)
        assert text == answer and report.get("passed") is True, report


async def test_an_altered_mushaf_quote_is_reported_once(quran_text, monkeypatch):
    monkeypatch.setenv("MIZAN_TRUTH_GATE", "flag")
    altered = UTHMANI[(2, 255)].replace("ٱلْعَظِيمُ", "ٱلْكَرِيمُ")
    text, report = await sidq.gate(f"Allah says:\n{altered}")
    assert [item["kind"] for item in report["flagged"]] == ["quote"]


async def test_nothing_is_claimed_without_mizans_quran_text(mushaf):
    answer = f"The Quran says:\n{INVENTED}"
    text, report = await sidq.gate(answer)
    assert text == answer and report.get("passed") is True


async def test_urdu_spelled_with_the_superscript_alif_is_not_the_mushafs_script(quran_text):
    # Urdu writes ٰ in ordinary words (تعالیٰ, زکوٰۃ); only the marks no other
    # writing uses (ٱ, the Quranic signs) make a passage look like the mushaf.
    answer = "اللہ تعالیٰ نے زکوٰۃ فرض کی ہے اور نماز کا حکم دیا ہے۔"
    text, report = await sidq.gate(answer)
    assert text == answer and report.get("passed") is True
