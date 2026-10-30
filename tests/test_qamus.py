"""Qāmūs: MIZAN's own cross-lingual lexicon, learned from parallel sentences."""

import gzip
import json

import pytest

from core.adaptive import AdaptiveStateStore, tokenize
from memory import mahw
from tadbir import ahl_dhikr, qamus, taallum

# ── reading words ─────────────────────────────────────────────────────────


def test_a_word_keeps_its_combining_marks():
    assert tokenize("भारत की राजधानी नई दिल्ली है।") == ["भारत", "की", "राजधानी", "नई", "दिल्ली", "है"]
    assert tokenize("இந்தியாவின் தலைநகரம்") == ["இந்தியாவின்", "தலைநகரம்"]
    assert tokenize("مُحَمَّدٌ رَسُولُ") == ["مُحَمَّدٌ", "رَسُولُ"]
    assert tokenize("Hello, World 42") == ["hello", "world", "42"]
    # The older reading, kept only to find what was stored under it.
    assert tokenize("राजधानी", marks=False) == ["र", "जध", "न"]


def test_scripts_are_read_from_unicode_names():
    assert qamus.script("राजधानी") == "DEVANAGARI"
    assert qamus.script("دارالحکومت") == "ARABIC"
    assert qamus.script("capital") == "LATIN"
    assert qamus.script("1947") == ""
    assert qamus.script_of("New Delhi (नई दिल्ली) is the capital") == "LATIN"


# ── learning: IBM Model 1 by EM ───────────────────────────────────────────

# A parallel corpus in which no word pair is given: each sentence pair only
# says that its words go together somehow.
CORPUS = [
    ("das haus", "the house"),
    ("das buch", "the book"),
    ("ein buch", "a book"),
    ("ein haus", "a house"),
    ("das kleine haus", "the small house"),
    ("ein kleines buch", "a small book"),
    ("das haus ist klein", "the house is small"),
    ("das buch ist klein", "the book is small"),
]
HELDOUT = [("ein kleines haus", "a small house"), ("das buch ist klein", "the book is small")]


def _pairs(rows, flip=False):
    found = [(tokenize(source), tokenize(target)) for source, target in rows]
    return [(target, source) for source, target in found] if flip else found


def test_em_learns_which_words_translate_each_other():
    to_english, english_trace = qamus.ibm1(_pairs(CORPUS), _pairs(HELDOUT))
    to_german, _ = qamus.ibm1(_pairs(CORPUS, flip=True), _pairs(HELDOUT, flip=True))
    shares = qamus.symmetrise(to_english, to_german)
    best = {word: max(row, key=row.__getitem__) for word, row in shares.items()}
    assert best["haus"] == "house"
    assert best["buch"] == "book"
    assert best["das"] == "the"
    assert best["ein"] == "a"
    assert best["ist"] == "is"
    # Each kept iteration raised the held-out log-likelihood.
    assert all(
        later > earlier for earlier, later in zip(english_trace, english_trace[1:], strict=False)
    )
    assert len(english_trace) >= 2


def test_em_stops_when_held_out_pairs_stop_improving():
    _, unbounded = qamus.ibm1(_pairs(CORPUS), _pairs(HELDOUT))
    _, bounded = qamus.ibm1(_pairs(CORPUS), _pairs(HELDOUT), limit=1)
    assert len(bounded) == 2  # the uniform start and one iteration
    assert unbounded[: len(bounded)] == bounded


def test_the_cut_off_is_chosen_by_f1_on_a_held_out_dictionary():
    shares = {
        "haus": {"house": 0.9, "the": 0.1},
        "buch": {"book": 0.6, "a": 0.4},
        "klein": {"small": 0.45, "is": 0.55},
    }
    gold = {"haus": {"house"}, "buch": {"book"}, "klein": {"small"}}
    tau, f1 = qamus.cutoff(shares, gold)
    # P ≥ 0.6: 2 right of 2, 2 of 3 found (F1 0.8). P ≥ 0.45: 3 right of 4,
    # all 3 found (F1 6/7). P ≥ 0.4 adds a wrong one (F1 0.75).
    assert tau == 0.45
    assert f1 == pytest.approx(6 / 7)
    assert qamus.keep(shares, tau) == {
        "haus": [["house", 0.9]],
        "buch": [["book", 0.6]],
        "klein": [["is", 0.55], ["small", 0.45]],
    }


def test_a_pair_seen_once_is_not_yet_known():
    shares = {"rare": {"word": 0.95}, "common": {"word": 0.95}}
    bounds = qamus.lower_bounds(shares, {"rare": 1, "common": 40})
    assert bounds["rare"]["word"] < 0.5 < bounds["common"]["word"]
    assert qamus.keep(shares, 0.5, by=bounds) == {"common": [["word", 0.95]]}


def test_precision_at_1_counts_the_first_translation():
    lexicon = {"haus": [["house", 0.9]], "buch": [["a", 0.6], ["book", 0.4]]}
    gold = {"haus": {"house"}, "buch": {"book"}, "klein": {"small"}}
    assert qamus.precision_at_1(lexicon, gold) == {"words": 3, "held": 2, "correct": 1}


# ── the shipped lexicon ───────────────────────────────────────────────────


def test_the_shipped_lexicon_is_small_and_records_how_it_was_measured():
    files = sorted(qamus.DATA.glob("*.json.gz"))
    assert {path.name for path in files} == {
        "hi-en.json.gz",
        "ur-en.json.gz",
        "ar-en.json.gz",
        "ta-en.json.gz",
    }
    assert sum(path.stat().st_size for path in files) < 5_000_000
    for path in files:
        data = json.loads(gzip.decompress(path.read_bytes()))
        assert data["format"] == qamus.FORMAT
        assert data["source"]["licence"] == "CC BY 4.0"
        for direction, measured in data["measured"].items():
            assert 0.5 < measured["precision_at_1"] <= 1.0, direction
            assert data["fit"][direction]["iterations"] >= 1


def test_translations_from_the_shipped_lexicon():
    assert qamus.translations("राजधानी", "hi", "en")[0][0] == "capital"
    assert qamus.translations("भारत", "hi", "en")[0][0] == "india"
    assert qamus.translations("capital", "en", "hi")[0][0] == "राजधानी"
    assert qamus.translations("عاصمة", "ar", "en")[0][0] == "capital"
    assert qamus.translations("no-such-word", "hi", "en") == []
    assert qamus.languages()["ur"] == "ARABIC"


def test_bridge_gives_the_words_a_text_translates_to():
    bridged = qamus.bridge("भारत की राजधानी नई दिल्ली है।", "en")
    assert {"india", "capital", "new"} <= set(bridged)
    # A word in the target's own script is matched as it is, not translated.
    assert qamus.translate("capital", "en") == []
    # A number in another script's digits is the same number.
    assert qamus.translate("१९४७", "en") == ["1947"]


def test_bridge_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("MIZAN_QAMUS", "off")
    assert qamus.bridge("भारत की राजधानी", "en") == []
    assert qamus.found_in(["राजधानी"], "the capital of India") == set()


def test_one_word_of_the_text_stands_for_one_word_at_most():
    # "براہ کرم" are two words for one "please".
    assert len(qamus.found_in(["براہ", "کرم"], "please turn off the lights")) == 1
    # A translation that is no evidence (a function word) is not counted.
    assert (
        qamus.found_in(["की"], "the capital of india", lambda word: word not in {"of", "the"})
        == set()
    )


# ── where MIZAN uses it: is a source sentence about a claim? ─────────────

CLAIM_HI = "भारत की राजधानी नई दिल्ली है।"
SOURCE = "New Delhi is the capital of India."
UNRELATED = (
    "Paris is the capital and largest city of France.",
    "Titan is the largest moon of Saturn.",
    "Play some jazz music in the kitchen.",
)


def test_about_reads_a_hindi_claim_against_its_english_source():
    assert ahl_dhikr.about(CLAIM_HI, SOURCE)
    for sentence in UNRELATED:
        assert not ahl_dhikr.about(CLAIM_HI, sentence)


def test_about_reads_other_scripts_too():
    assert ahl_dhikr.about("आज मौसम कैसा है", "What is the weather like today?")
    assert ahl_dhikr.about("آج موسم کیسا ہے", "What is the weather like today?")
    for sentence in UNRELATED:
        assert not ahl_dhikr.about("آج موسم کیسا ہے", sentence)


def test_without_qamus_no_word_of_another_script_is_found(monkeypatch):
    monkeypatch.setenv("MIZAN_QAMUS", "off")
    assert not ahl_dhikr.about(CLAIM_HI, SOURCE)


def test_same_language_text_is_read_as_before():
    assert ahl_dhikr.about(
        "Saturn ka sabse bada chand Titan hai", "Titan is the largest moon of Saturn."
    )
    assert not ahl_dhikr.about("The largest moon of Saturn is Titan.", UNRELATED[0])


# ── forgetting what was stored under the older reading ───────────────────


def test_mahw_erases_what_was_learned_under_the_older_reading(tmp_path):
    store = AdaptiveStateStore(str(tmp_path / "adaptive.db"))
    request = "मुझे शुक्रवार को सुबह नौ बजे जगा दो"
    assert taallum.content_words(request) != taallum.content_words(request, marks=False)
    old = {"tokens": taallum.content_words(request, marks=False), "used": 1, "family": "x"}
    new = {"tokens": taallum.content_words(request), "used": 2, "family": "x"}
    kept = {"tokens": ["something", "else"], "used": 3, "family": "x"}
    taallum._save(store, "u1", [old, new, kept])
    assert mahw._forget_learned(store, "u1", [request]) == 2
    assert taallum._load(store, "u1") == [kept]
