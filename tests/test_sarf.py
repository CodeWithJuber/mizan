"""Sarf: one analyzer for the root, pattern, part of speech and meaning of a
word, read from the Quranic Arabic Corpus (here a small corpus in its format).

The live benchmark (27 Oct 2026) found /api/v1/root-analyze dropping the first
radical (كتب → تب, كاتب → اتب, مكتوب → مكت) and calling يوم a past-tense verb."""

import hashlib

import pytest

from tadbir import sarf

# The corpus's own format (location, form, tag, features); written for this test.
MORPHOLOGY = """\
1:1:1:1\tكَتَبَ\tV\tPERF|VF:1|ROOT:كتب|LEM:كَتَبَ|3MS
1:1:2:1\tكَاتِبٌ\tN\tACT_PCPL|VF:1|ROOT:كتب|LEM:كاتِب|M|NOM
1:1:3:1\tمَكْتُوبٌ\tN\tPASS_PCPL|VF:1|ROOT:كتب|LEM:مَكْتُوب|M|NOM
1:1:4:1\tٱل\tP\tDET|PREF|LEM:ال
1:1:4:2\tكِتَٰبُ\tN\tROOT:كتب|LEM:كِتاب|M|NOM
1:1:5:1\tيَوْمَ\tN\tROOT:يوم|LEM:يَوْم|M|ACC
1:1:6:1\tمَرْحَمَةٍ\tN\tROOT:رحم|LEM:مَرْحَمَة|F|GEN
1:1:7:1\tمَسْطُورٍ\tN\tPASS_PCPL|ROOT:سطر|LEM:مَسْطُور|M|GEN
1:1:8:1\tفِى\tP\tP|LEM:فِي
1:1:9:1\tقَالَ\tV\tPERF|VF:1|ROOT:قول|LEM:قالَ|3MS
"""
GLOSSES = [
    "(he) wrote",
    "a scribe",
    "written",
    "the book",
    "(the) day",
    "mercy",
    "inscribed",
    "in",
    "said",
]


@pytest.fixture
def corpus():
    return sarf.build(MORPHOLOGY, GLOSSES)


@pytest.mark.parametrize("word", ["كتب", "كاتب", "مكتوب", "مكتبة", "كتاب", "الكتاب"])
def test_every_form_of_ktb_has_the_root_ktb(corpus, word):
    found = sarf.analyze_word(corpus, word)
    assert found["root_letters"] == "ك-ت-ب", found


def test_words_of_the_quran_are_read_from_the_corpus_with_their_wazn(corpus):
    katib = sarf.analyze_word(corpus, "كاتب")
    assert katib["pos"] == "active participle" and katib["pattern"] == "فَاعِل"
    assert katib["source"] == "quran" and katib["gloss"] == "a scribe"
    maktub = sarf.analyze_word(corpus, "مَكْتُوب")  # vowel marks are read through
    assert maktub["pos"] == "passive participle" and maktub["pattern"] == "مَفْعُول"
    yawm = sarf.analyze_word(corpus, "يوم")
    assert yawm["pos"] == "noun" and yawm["root_letters"] == "ي-و-م"
    assert sarf.analyze_word(corpus, "قال")["root_letters"] == "ق-و-ل"  # a weak root


def test_other_words_are_read_by_the_most_probable_pattern_and_root(corpus):
    maktaba = sarf.analyze_word(corpus, "مكتبة")
    assert maktaba["source"] == "inferred" and maktaba["pattern"] == "مَفْعَلَة"
    assert 0 < maktaba["probability"] <= 1
    assert sarf.analyze_word(corpus, "في")["is_stopword"]


def test_a_root_means_what_the_corpus_glosses_its_words(corpus):
    assert "wrote" in sarf.analyze_word(corpus, "كتب")["meaning"]


async def test_the_corpus_is_used_only_when_it_matches_its_pinned_digest(tmp_path, monkeypatch):
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    data = MORPHOLOGY.encode()
    path = tmp_path / "morphology" / "quran-morphology.txt"
    path.parent.mkdir(parents=True)
    path.write_bytes(data)
    monkeypatch.setitem(
        sarf.SOURCES,
        "quran-morphology.txt",
        ("https://invalid.test/", hashlib.sha256(data).hexdigest()),
    )
    assert await sarf._download("quran-morphology.txt") == MORPHOLOGY
    path.write_bytes(data + b"tampered")
    with pytest.raises(sarf.Unavailable):  # no network here: a changed file is not trusted
        await sarf._download("quran-morphology.txt")


def test_the_api_and_the_analyzer_agree(corpus, monkeypatch):
    from fastapi.testclient import TestClient

    from api.main import app

    async def ready():
        return corpus

    monkeypatch.setattr(sarf, "corpus", ready)
    body = TestClient(app).post("/api/v1/root-analyze", json={"text": "كاتب يوم"}).json()
    assert [item["root_letters"] for item in body["analysis"]] == ["ك-ت-ب", "ي-و-م"]
    assert body["analysis"][1]["pos"] == "noun" and "Quranic Arabic Corpus" in body["source"]
