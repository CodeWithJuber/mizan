"""Regression cases for observed Arabic evidence, not semantic benchmarks."""

from unittest.mock import Mock

from nlp.arabic import arabic_tokens, lookup_key
from nlp.wsd import _locate_token, disambiguate
from qca.engine import ISMLayer, QCAEngine


def test_punctuation_digits_and_marks_share_agent_qca_boundaries():
    from agents.base import _arabic_lemmas as agent_tokens
    from qca.engine import _arabic_lemmas as qca_tokens

    text = "knowledge، عِلْمٌ؛ كِتَابٌ؟ ١٢٣ ۞ علم"
    expected = ["عِلْمٌ", "كِتَابٌ", "علم"]
    assert arabic_tokens(text) == agent_tokens(text) == qca_tokens(text) == expected
    assert arabic_tokens(text, 0) == []


def test_dictionary_arabic_forms_no_longer_require_english_gloss():
    layer = ISMLayer()
    roots = {item["root"] for item in layer.find_roots_in_text("عِلْم، كِتَاب")}
    assert {"علم", "كتب"} <= roots
    assert all(r["match_type"] == "arabic_dictionary" for r in layer.find_roots_in_text("عِلْم كِتَاب"))
    assert layer.find_roots_in_text("السوبركاليفراجيليستيك") == []
    assert ISMLayer(root_db={}).find_roots_in_text("علم") == []


def test_root_order_and_hamza_are_not_collapsed():
    assert lookup_key("عِلْم") != lookup_key("عَمَل")
    assert lookup_key("أمن") != lookup_key("امن")
    db = {"علم": {"derivatives": {"مشترك": "one"}}, "عمل": {"derivatives": {"مشترك": "two"}}}
    assert {r["root"] for r in ISMLayer(db).find_roots_in_text("مشترك")} == {"علم", "عمل"}


def test_wsd_does_not_use_embedded_root_as_lemma():
    assert _locate_token("هذا معلم", "علم") == (None, None, None)
    assert _locate_token("هذا علم، نافع", "علم")[1] == "علم،"
    assert _locate_token("فَبِأَيِّ ءَالَآءِ", "أَيّ")[1] == "فَبِأَيِّ"


def test_real_wsd_abstains_when_lemma_is_not_in_text():
    # The shipped artifact recognizes يوم, but the English sentence has no
    # Arabic occurrence. It must not fabricate context by substituting يوم.
    assert disambiguate("Tell me about knowledge", "يوم") == []


def test_undiacritized_collision_cannot_choose_by_dictionary_order():
    assert disambiguate("مثل", "مثل") == []
    assert disambiguate("آخر", "آخر") == []
    assert disambiguate("مَثَل", "مَثَل")
    assert disambiguate("مِثْل", "مِثْل")


def test_observed_attached_particle_resolves_only_known_lemma():
    assert disambiguate("وَيَوْم", "وَيَوْم")


def test_english_roots_never_hide_mixed_script_tokens(monkeypatch):
    monkeypatch.setenv("MIZAN_NLP_NATIVE_WSD", "1")
    monkeypatch.setattr("nlp.is_ready", lambda: True)
    classify = Mock(return_value=[])
    monkeypatch.setattr("nlp.disambiguate", classify)
    QCAEngine().process_input("knowledge علم، يوم")
    assert [call.args[1] for call in classify.call_args_list] == ["علم", "يوم"]
    classify.reset_mock()
    assert QCAEngine().process_input("knowledge")["senses_identified"] == []
    classify.assert_not_called()
