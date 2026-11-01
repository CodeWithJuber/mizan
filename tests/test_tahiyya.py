"""Tahiyya: a salam and nothing else, read by evidence (4:86; docs/fahm.md "Salam (4:86)")."""

import json

import pytest

from tadbir import fahm, tahiyya


def test_the_shipped_fit_is_of_the_shipped_data():
    shipped = json.loads(tahiyya.FIT.read_text(encoding="utf-8"))
    assert shipped["sha256"] == tahiyya.digest()
    assert shipped["order"] in tahiyya.ORDERS and shipped["first_order"] in tahiyya.ORDERS
    # The prior is each reader's share of the messages people send.
    assert abs(sum(shipped["prior"].values()) - 1) < 1e-9


@pytest.mark.parametrize(
    "message",
    ["Assalamualaikum", "AoA", "السلام علیکم", "अस्सलामु अलैकुम", "Assalamualaikum bhai"],
)
def test_a_salam_alone_reads_as_a_salam(message):
    assert tahiyya.reads_salam(message)


@pytest.mark.parametrize(
    "message",
    [
        # a returned salam is a reply, not a salam to return
        "Walaikum assalam bhai",
        "وعلیکم السلام",
        # a salam with a request goes on to the request
        "Assalamualaikum, Surah Ikhlas sunao",
        # words that begin like one
        "Salman Khan movies",
        # ordinary requests, short or long
        "set an alarm for 6",
        "adele",
        "",
    ],
)
def test_anything_else_is_not(message):
    assert not tahiyya.reads_salam(message)


def test_vowel_marks_and_case_do_not_change_the_reading():
    assert tahiyya.normalize("اَلسَّلَامُ عَلَيْكُمْ") == tahiyya.normalize("السلام عليكم")
    assert tahiyya.normalize("ASSALAMU-ALAIKUM!") == "assalamu alaikum"


def test_fahm_asks_tahiyya_first_and_it_can_be_turned_off(monkeypatch):
    assert fahm.understand("Assalamualaikum").intent == "salam"
    monkeypatch.setenv("MIZAN_TAHIYYA", "off")
    assert fahm.understand("Assalamualaikum").intent == "converse"
