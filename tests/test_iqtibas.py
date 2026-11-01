"""Iqtibas: a message that is the Quran's own words counts as a Quran request."""

import hashlib
import json

import pytest

from core import tamyiz_cache
from tadbir import fahm, iqtibas, qasd
from tests.test_fihris import editions

RANKED = [("converse", 0.6), ("quran_search", 0.3), ("compute", 0.1)]


@pytest.fixture(scope="module")
def quotes():
    return iqtibas.build(editions())


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    iqtibas._span.cache_clear()
    monkeypatch.setattr(iqtibas, "_load_soon", lambda: None)  # never reads the data dir
    yield
    iqtibas._span.cache_clear()


def test_the_longest_span_the_texts_hold_word_for_word(quotes):
    span = iqtibas.quoted("light upon light", quotes)
    assert (span.words, span.view, span.ayah, span.share) == (
        ("light", "upon", "light"),
        "en",
        (24, 35),
        1.0,
    )
    # Uthmani marks and the letter variants are folded on both sides.
    span = iqtibas.quoted("سدرة المنتهى؟", quotes)
    assert (span.view, span.ayah, span.share) == ("ar", (53, 14), 1.0)
    # Transliteration is read by its letters, a repeated letter counting once.
    span = iqtibas.quoted("Inna lillahi wa inna ilaihi rajioon", quotes)
    assert (span.view, span.ayah, span.share) == ("tr", (2, 156), 1.0)


def test_words_the_texts_never_use_are_no_quote(quotes):
    assert iqtibas.quoted("Mudguard मरघाट", quotes) is None
    assert iqtibas.quoted("", quotes) is None


def test_ordinary_speech_makes_a_phrase_it_says_cheap():
    model = iqtibas.Background([["peace", "be", "upon", "you"]] * 5 + [["light"], ["upon"]])
    assert model.surprise(("peace", "be", "upon", "you")) < model.surprise(
        ("light", "upon", "light")
    )
    # A sentence counted out (a seed read while it is held out) leaves no trace.
    before = model.surprise(("peace", "be"))
    model.add(["peace", "be", "upon", "you"], -1)
    model.add(["peace", "be", "upon", "you"], 1)
    assert model.surprise(("peace", "be")) == pytest.approx(before)


def test_a_fragment_weighs_less_than_the_whole_quote(quotes):
    whole = iqtibas.quoted("light upon light", quotes)
    part = iqtibas.quoted("light upon light is what my teacher said today", quotes)
    assert part.words == whole.words and part.weight < whole.weight


def test_the_factor_raises_only_the_quran_family(monkeypatch, quotes):
    monkeypatch.setenv("MIZAN_IQTIBAS", "on")
    monkeypatch.setattr(iqtibas, "_quotes", quotes)
    monkeypatch.setattr(iqtibas, "fitted", lambda: {"b": 0.05})
    weighed, found = iqtibas.weigh(RANKED, "light upon light")
    posterior = dict(weighed)
    assert posterior["quran_search"] > 0.3
    assert posterior["compute"] / posterior["converse"] == pytest.approx(0.1 / 0.6)
    assert sum(posterior.values()) == pytest.approx(1.0)
    assert (found["ayah"], found["view"], found["words"]) == ("24:35", "en", "light upon light")


def test_nothing_changes_without_the_texts_or_when_off(monkeypatch, quotes):
    monkeypatch.setattr(iqtibas, "fitted", lambda: {"b": 0.05})
    monkeypatch.setenv("MIZAN_IQTIBAS", "on")
    monkeypatch.setattr(iqtibas, "_quotes", None)
    assert iqtibas.weigh(RANKED, "light upon light") == (RANKED, {})
    monkeypatch.setattr(iqtibas, "_quotes", quotes)
    monkeypatch.setenv("MIZAN_IQTIBAS", "off")
    assert iqtibas.weigh(RANKED, "light upon light") == (RANKED, {})
    monkeypatch.setenv("MIZAN_IQTIBAS", "on")
    assert iqtibas.weigh(RANKED, "Mudguard मरघाट") == (RANKED, {})  # no span


def test_a_quote_reaches_mizans_quran_search(monkeypatch, quotes):
    monkeypatch.setenv("MIZAN_IQTIBAS", "on")
    monkeypatch.setattr(iqtibas, "_quotes", quotes)
    understood = fahm.understand("light upon light")
    assert understood.intent == "quran_search"
    for said in ("Alhamdulillah", "Bismillah", "Allah knows best"):
        assert fahm.understand(said).intent == "converse", said
    # A salam alone is MIZAN's to return (4:86), never a Quran search.
    assert fahm.understand("Assalamu alaikum").intent == "salam"


def test_the_shipped_fit_is_of_the_shipped_seeds_and_calibration():
    """Seeds or calibration changed without a refit: run
    ``python -m tadbir.iqtibas --fit`` from backend/ (it needs the Quran editions)."""
    saved = json.loads(iqtibas.PACKAGED.read_text(encoding="utf-8"))
    assert saved["b"] > 0
    assert saved["seeds_sha256"] == tamyiz_cache.digest(qasd.examples())
    calibration = hashlib.sha256(iqtibas.CALIBRATION.read_bytes()).hexdigest()
    assert saved["calibration_sha256"] == calibration
