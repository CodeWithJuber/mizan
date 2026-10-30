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


# ── names are written, not translated ─────────────────────────────────────


def test_a_name_and_its_transliteration_sound_alike():
    assert qamus.skeleton("john") == "jhn"
    assert qamus.skeleton("jon") == "jn"  # anyascii("जॉन")
    assert qamus.skeleton("Mississippi") == "msp"
    assert qamus.sounds_alike("jon", "john") > qamus.sounds_alike("bhrt", "pakistan")
    assert qamus.sounds_alike("pkstn", "pakistan") == 1.0  # anyascii("پاکستان")
    assert qamus.sounds_alike("gova", "mumbai") == 0.0  # anyascii("गोवा")
    assert qamus.edit_distance("kitten", "sitting") == 3


def test_the_name_cut_off_is_not_moved_by_mislabelled_pairs():
    # Six transliterations and four other names marked as translated (a
    # localised slot). With or without the four, the cut-off lies above every
    # unrelated pair and keeps most transliterations.
    transliterations = [0.9, 0.8, 1.0, 0.9, 0.75, 0.8]
    positives = transliterations + [0.0, 0.0, 0.2, 0.0]
    negatives = [0.0] * 8 + [0.2, 0.3]
    for kept in (positives, transliterations):
        sigma, j = qamus.youden(kept, negatives)
        assert max(negatives) < sigma <= 0.8
        assert sum(score >= sigma for score in transliterations) >= 4


def test_a_piece_of_a_word_written_apart_is_not_a_word():
    sentences = [
        ["پاکستان", "کا", "وقت"],
        ["پاکستان", "میں", "موسم"],
        ["پا", "کستا", "ن", "میں", "ٹائمر"],
        ["कौन", "है"],
        ["कौन", "सा", "गाना"],
        ["कौन", "आया"],
        ["कौनसा", "दिन"],
    ]
    found = qamus.pieces(sentences)
    assert {"پا", "کستا", "ن"} <= found
    # "कौन" (who) stands alone more often than "कौनसा" is written closed.
    assert "कौन" not in found and "سا" not in found


# ── the shipped lexicon ───────────────────────────────────────────────────


def test_the_shipped_lexicon_is_small_and_records_how_it_was_measured():
    files = sorted(qamus.DATA.glob("*.json.gz"))
    assert {path.name for path in files} == {
        "hi-en.json.gz",
        "ur-en.json.gz",
        "ar-en.json.gz",
        "ta-en.json.gz",
        qamus.ROMAN,
    }
    assert sum(path.stat().st_size for path in files) < 5_000_000
    for path in files:
        if path.name == qamus.ROMAN:
            continue
        data = json.loads(gzip.decompress(path.read_bytes()))
        assert data["format"] == qamus.FORMAT
        assert data["source"]["licence"] == "CC BY 4.0"
        assert data["source"]["romaniser"] == "anyascii 0.3.2"
        names = data["measured"]["names"]
        assert 0 < names["sigma"] <= 1 and names["test"]["precision"] > 0.8
        for direction, measured in data["measured"].items():
            if direction == "names":
                continue
            assert 0.5 < measured["precision_at_1"] <= 1.0, direction
            assert data["fit"][direction]["iterations"] >= 1
            assert set(data["fit"][direction]["removed"]) == {"names", "pieces"}


def test_translations_from_the_shipped_lexicon():
    assert qamus.translations("राजधानी", "hi", "en")[0][0] == "capital"
    assert qamus.translations("शुक्रवार", "hi", "en")[0][0] == "friday"
    assert qamus.translations("capital", "en", "hi")[0][0] == "राजधानी"
    assert qamus.translations("عاصمة", "ar", "en")[0][0] == "capital"
    assert qamus.translations("no-such-word", "hi", "en") == []
    assert qamus.languages()["ur"] == "ARABIC"
    # A pair either direction holds: "delhi" → "दिल्ली" reads "दिल्ली" as "delhi".
    assert "delhi" in qamus.translate("दिल्ली", "en")
    assert "chennai" in qamus.translate("चेन्नई", "en")


# Pairs a translator's localisation put in the lexicon before names were
# checked (one name put in another's place, or a word of the same sentence).
SWAPS = [
    ("pakistan", "ur", "بھارت"),
    ("india", "ur", "پاکستان"),
    ("japan", "ur", "پاکستان"),
    ("japan", "ur", "ن"),
    ("japan", "ur", "کستا"),
    ("york", "ur", "گوجرانوالہ"),
    ("york", "ur", "کراچی"),
    ("york", "ur", "اسلام"),
    ("mumbai", "ur", "شالیمار"),
    ("china", "ur", "ووک"),
    ("mumbai", "hi", "गोवा"),
    ("london", "hi", "गाड़ी"),
    ("mumbai", "ar", "المنورة"),
    ("mumbai", "ar", "للمدينة"),
    ("york", "ar", "سيناء"),
    ("york", "ar", "بموعد"),
    ("chennai", "ar", "الوضع"),
    ("america", "ar", "تخبرنا"),
    ("japan", "ar", "أيم"),
    ("america", "ta", "ஓலா"),
]


@pytest.mark.parametrize(("english", "language", "other"), SWAPS)
def test_a_name_put_in_another_names_place_is_not_a_translation(english, language, other):
    assert other not in qamus.translate(english, language)
    assert english not in qamus.translate(other, "en")


def test_real_names_keep_their_transliterations():
    assert "दिल्ली" in qamus.translate("delhi", "hi")
    assert "न्यूयॉर्क" in qamus.translate("york", "hi")
    assert "الهند" in qamus.translate("india", "ar")
    assert "லண்டன்" in qamus.translate("london", "ta")


def test_bridge_gives_the_words_a_text_translates_to():
    bridged = qamus.bridge("भारत की राजधानी नई दिल्ली है।", "en")
    assert {"capital", "new", "delhi"} <= set(bridged)
    # "भारत" is not a transliteration of "india", so it is not given as one.
    assert "india" not in qamus.translate("भारत", "en")
    # A word in the target's own script is matched as it is, not translated.
    assert qamus.translate("capital", "en") == []
    # A number in another script's digits is the same number.
    assert qamus.translate("१९४७", "en") == ["1947"]
    # An invisible direction mark inside a word does not cut it in two.
    assert qamus.tokens("جا‎ۓ گی") == ["جاۓ", "گی"]


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


def test_about_never_reads_one_place_as_another():
    # A claim about India is not about a sentence on Pakistan, nor one about
    # Mumbai about a sentence on Goa: neither name is translated as the other.
    assert not ahl_dhikr.about(
        "بھارت کا دارالحکومت نئی دہلی ہے", "The capital of Pakistan is Islamabad."
    )
    assert not ahl_dhikr.about(
        "پاکستان کا دارالحکومت اسلام آباد ہے", "New Delhi is the capital of India."
    )
    assert not ahl_dhikr.about("मुंबई भारत का सबसे बड़ा शहर है", "Goa is the smallest state of India.")
    assert not ahl_dhikr.about("मुंबई महाराष्ट्र की राजधानी है", "Panaji is the capital of Goa.")
    # A correct pair across scripts is still read.
    assert ahl_dhikr.about(CLAIM_HI, SOURCE)
    assert ahl_dhikr.about("آج موسم کیسا ہے", "What is the weather like today?")


def test_without_qamus_no_word_of_another_script_is_found(monkeypatch):
    monkeypatch.setenv("MIZAN_QAMUS", "off")
    assert not ahl_dhikr.about(CLAIM_HI, SOURCE)


def test_same_language_text_is_read_as_before():
    assert ahl_dhikr.about(
        "Saturn ka sabse bada chand Titan hai", "Titan is the largest moon of Saturn."
    )
    assert not ahl_dhikr.about("The largest moon of Saturn is Titan.", UNRELATED[0])


# ── Roman Hindi and Urdu ──────────────────────────────────────────────────

# Words and their spellings in Latin letters; no letter is paired with letters.
ROMAN_PAIRS = [
    ("कमल", "kamal"),
    ("कलम", "kalam"),
    ("मकान", "makaan"),
    ("नमक", "namak"),
    ("काम", "kaam"),
    ("नाम", "naam"),
    ("मन", "man"),
    ("कान", "kaan"),
    ("कल", "kal"),
    ("लाल", "laal"),
    ("माल", "maal"),
    ("नल", "nal"),
]


def test_the_channel_learns_how_letters_are_written_in_latin():
    pairs = [(qamus.contexts(native), roman) for native, roman in ROMAN_PAIRS]
    table, trace = qamus.channel(pairs, pairs[:4])
    assert len(trace) >= 2 and trace == sorted(trace)  # EM stops when held out stops rising
    # Words it never saw are spelled as their letters are.
    assert qamus.spellings(qamus.contexts("मलाल"), table)[0][0] == "malaal"
    assert qamus.spellings(qamus.contexts("नकल"), table)[0][0] == "nakal"
    assert qamus.written_as(qamus.contexts("कमल"), "kamal", table) > 0.5
    assert qamus.written_as(qamus.contexts("कमल"), "kmla", table) == 0.0
    # A spelling is read as the word that most probably wrote it.
    found = qamus.readings({"कमल": 5, "कलम": 1, "नकल": 1}, table, "kind", keep=5)
    assert found["kamal"][0] == "कमल" and found["kalam"][0] == "कलम"


def test_units_and_contexts_are_letters_with_their_marks():
    assert qamus.units("बनवाया") == ["ब", "न", "वा", "या"]
    assert qamus.contexts("बनवाया") == ["ब\tc", "न\tm", "वा\tm", "या\t$"]
    assert qamus.contexts("دنیا", "letter") == ["د\tن", "ن\tی", "ی\tا", "ا\t$"]
    assert qamus.roman_letters("Ban'waya") == "banwaya"


def test_the_shipped_roman_reading_records_how_it_was_measured():
    data = json.loads(gzip.decompress((qamus.DATA / qamus.ROMAN).read_bytes()))
    assert data["format"] == qamus.ROMAN_FORMAT
    assert data["source"]["left_out"] == ["Dakshina"]
    for language in ("hi", "ur"):
        assert data["fit"][language]["iterations"] >= 2
        assert data["measured"][language]["read_accuracy"] > 0.5
        assert data["read"][language]


def test_roman_hindi_and_urdu_words_are_read_and_translated():
    assert qamus.read_roman("duniya")["hi"] == "दुनिया"
    assert "world" in qamus.translate("duniya", "en")
    assert "wife" in qamus.translate("biwi", "en")
    assert "capital" in qamus.translate("rajdhani", "en")
    assert "दुनिया" in qamus.translate("duniya", "hi")
    # English words are not read as Roman Hindi, though some are spelled alike.
    for english in ("main", "the", "door", "capital"):
        assert qamus.read_roman(english) == {}
    assert qamus.translate("capital", "en") == []


# A claim from production (30 Oct 2026), with how the Taj Mahal's page says it.
TAJ_ROMAN = "Taj Mahal Shah Jahan ne apni biwi Mumtaz Mahal ki yaad mein banwaya tha."
TAJ_SENTENCE = "It was built by the emperor Shah Jahan in memory of his wife, Mumtaz Mahal."


def test_a_roman_claim_finds_its_english_sentence():
    assert ahl_dhikr.about(TAJ_ROMAN, TAJ_SENTENCE)
    assert "wife" in ahl_dhikr.searched(TAJ_ROMAN).split()


def test_a_roman_claim_is_not_read_against_another_subject():
    berlin = "Berlin ki deewar 9 November 1989 ko giri thi."
    china = "China ki deewar duniya ki sabse lambi deewar hai."
    assert not ahl_dhikr.about(berlin, "The Great Wall of China is the longest wall in the world.")
    assert not ahl_dhikr.about(china, "The Berlin Wall was taken down on November 9, 1989.")
    assert not ahl_dhikr.about(TAJ_ROMAN, "Titan is the largest moon of Saturn.")


def test_a_roman_claim_is_read_by_the_nli_model_in_devanagari():
    premise = "Its chemical symbol is Au, from the Latin word for gold."
    read = qamus.devanagari("Sone ka chemical symbol Au hai.", keep=premise)
    # The source's own words ("Au", "chemical") stay as they are.
    assert "Au" in read and "chemical symbol" in read
    assert "Sone" not in read and "सोने" in read
    assert ahl_dhikr.roman(TAJ_ROMAN)
    assert not ahl_dhikr.roman("The Taj Mahal was built by Shah Jahan.")


def test_without_qamus_no_roman_word_is_read(monkeypatch):
    monkeypatch.setenv("MIZAN_QAMUS", "off")
    assert not ahl_dhikr.about(TAJ_ROMAN, TAJ_SENTENCE)
    assert qamus.bridge(TAJ_ROMAN, "en") == []
    assert qamus.devanagari("Sone ka chemical symbol Au hai.") == "Sone ka chemical symbol Au hai."
    assert not ahl_dhikr.roman(TAJ_ROMAN)


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
