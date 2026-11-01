"""Gharib: a word's information in its own language, from word frequencies."""

import gzip
import importlib.util
import json
import math
from pathlib import Path

import pytest

from tadbir import gharib

ROOT = Path(__file__).resolve().parents[1]


def test_the_shipped_lists_cover_every_language():
    data = json.loads(gzip.decompress((gharib.DATA / "words.json.gz").read_bytes()))
    assert data["format"] == gharib.FORMAT
    assert set(data["languages"]) == set(gharib.LANGUAGES)
    for code in gharib.LANGUAGES:
        # An average running word carries some nats, never the most a word can.
        assert 4.0 < gharib.floor(code) < gharib.MOST_INFORMATION
    # Roman Hindi mixes English in: its other words are read from English.
    assert data["mixed"]["hi-latn"]["base"] == "en"
    assert 0 < data["mixed"]["hi-latn"]["share"] < 1
    assert (gharib.DATA / "LICENSES.md").exists()


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("The capital of Australia is Canberra.", "en"),
        ("ऑस्ट्रेलिया की राजधानी कैनबरा है।", "hi"),
        ("آسٹریلیا کا دارالحکومت کینبرا ہے۔", "ur"),
        ("عاصمة أستراليا هي كانبرا.", "ar"),
        ("ஆஸ்திரேலியாவின் தலைநகரம் கான்பரா.", "ta"),
        ("Australia ki rajdhani kya hai bhai?", "hi-latn"),
    ],
)
def test_a_text_is_read_in_the_language_its_words_are_most_probable_in(text, language):
    assert gharib.language_of(text) == language


@pytest.mark.parametrize(
    ("common", "rare", "language"),
    [
        ("the", "canberra", "en"),
        ("है", "राजधानी", "hi"),
        ("کے", "دارالحکومت", "ur"),
        ("في", "عاصمة", "ar"),
        ("hai", "rajdhani", "hi-latn"),
    ],
)
def test_function_words_carry_less_than_an_average_word(common, rare, language):
    assert not gharib.informative(common, language)
    assert gharib.informative(rare, language)
    assert gharib.information(common, language) < gharib.information(rare, language)


def test_an_ordinary_word_is_not_as_rare_as_a_name():
    # The pooled corpora read "प्रसिद्ध" (famous) as rarely as a name.
    assert gharib.information("प्रसिद्ध", "hi") < gharib.information("कैनबरा", "hi")
    assert gharib.information("سب", "ur") < gharib.floor("ur")


def test_a_word_no_list_holds_is_as_rare_as_the_rarest():
    assert gharib.information("zxqvbnkw", "en") == pytest.approx(gharib.MOST_INFORMATION)
    assert gharib.information("कैनबरा", "en") == pytest.approx(gharib.MOST_INFORMATION)


def test_words_are_read_as_the_lists_write_them():
    # Arabic script without vowel marks or tatweel; case folded; NFKC.
    assert gharib.information("كَلِمَة", "ar") == gharib.information("كلمة", "ar")
    assert gharib.information("الحمــــد", "ar") == gharib.information("الحمد", "ar")
    assert gharib.information("Canberra", "en") == gharib.information("canberra", "en")


def test_a_number_is_its_shape_spread_evenly():
    # Every four-digit number is equally likely: 10^-4 of the shape "0000".
    assert gharib.probability("1975", "en") == gharib.probability("2024", "en")
    assert gharib.probability("1975", "hi") == gharib.probability("१९७५", "hi")
    shape = gharib.probability("12", "en")
    assert gharib.probability("1975", "en") <= shape
    assert gharib.shape("1975ء") == ("0000ء", 4)
    # A year in a Hindi claim says much more than an average Hindi word.
    assert gharib.informative("१९६९", "hi")


def test_a_word_alone_is_read_in_the_language_that_writes_it_most():
    assert gharib.information("the") == pytest.approx(gharib.information("the", "en"))
    assert gharib.information("राजधानी") == pytest.approx(gharib.information("राजधानी", "hi"))
    assert math.isclose(
        gharib.information("hai"), min(gharib.information("hai", c) for c in gharib.LANGUAGES)
    )


def _builder():
    spec = importlib.util.spec_from_file_location("build_gharib", ROOT / "scripts/build_gharib.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_builder_reads_wordfreq_cbpack_without_its_code():
    builder = _builder()
    # [{"format": "cB", "version": 1}, [], ["the"], ["a", "of"]] in msgpack
    packed = b"\x94\x82\xa6format\xa2cB\xa7version\x01\x90\x91\xa3the\x92\xa1a\xa2of"
    value, end = builder._unpack(packed)
    assert end == len(packed)
    assert value == [{"format": "cB", "version": 1}, [], ["the"], ["a", "of"]]


def test_the_builder_counts_words_as_mizan_cuts_them():
    builder = _builder()
    # "don't" is two of MIZAN's words; every one-in-ten word is "the".
    found = builder.frequencies([[], [], [], [], [], [], [], [], [], [], [], ["don't"]], "en")
    assert set(found) == {"don", "t"}
    assert found["don"] == found["t"]
    assert builder.pieces("1,975", "en") == ["0", "000"]


def test_about_weighs_by_lughah_unless_told_to_read_gharib(monkeypatch):
    from tadbir import ahl_dhikr

    # Measured on 30 Oct 2026 and not adopted (docs/ahl-dhikr.md).
    assert ahl_dhikr.WORDS == "lughah"
    monkeypatch.setattr(ahl_dhikr, "WORDS", "gharib")
    claim = "ऑस्ट्रेलिया की राजधानी कैनबरा है।"
    assert ahl_dhikr.about(claim, "कैनबरा ऑस्ट्रेलिया की राजधानी है।")
    assert not ahl_dhikr.about(claim, "भारत की राजधानी नई दिल्ली है।")
    # Across scripts, a translation counts when it is no function word.
    assert ahl_dhikr.about("भारत की राजधानी नई दिल्ली है।", "New Delhi is the capital of India.")
