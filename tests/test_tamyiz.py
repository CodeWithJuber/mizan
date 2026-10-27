"""Tamyiz (weighted naive Bayes), Lughah (language) and Qasd (intent): understanding by evidence."""

import json
import random
from collections import Counter

import pytest

from core import tamyiz_cache
from core.adaptive import AdaptiveStateStore
from core.tamyiz import Tamyiz, char_ngrams, letters
from tadbir import fahm, lughah, qasd


def words(text):
    return Counter(letters(text).lower().split())


TOY = [
    ("the cat sat on the mat", "en"),
    ("a dog ran in the park", "en"),
    ("the bird sang a song", "en"),
    ("my cat likes the sun", "en"),
    ("billi chat pe baithi hai", "hi"),
    ("kutta park mein bhaaga", "hi"),
    ("chidiya ne gaana gaaya", "hi"),
    ("meri billi dhoop pasand karti hai", "hi"),
]


# ── Tamyiz ───────────────────────────────────────────────────────────────


def test_the_posterior_is_a_distribution_and_map_is_its_top():
    model = Tamyiz(words).fit(TOY)
    posterior = model.posterior("the cat ran")
    assert set(posterior) == {"en", "hi"} and sum(posterior.values()) == pytest.approx(1.0)
    assert model.predict("the cat ran")[0] == "en"
    assert model.predict("billi park mein")[0] == "hi"


def test_smoothing_and_weights_are_fitted_by_leave_one_out():
    model = Tamyiz(lambda text: char_ngrams(letters(text), (2, 3))).fit(TOY)
    state = model.state()
    assert state["alpha"] in (0.01, 0.03, 0.1, 0.3, 1.0)
    assert all(weight > 0 for weight in state["weights"])
    # Each line is scored by the model trained on the other seven.
    assert state["loo_accuracy"] >= 0.75
    assert state["loo_loss"] is not None and state["examples"] == len(TOY)


def test_copies_of_a_held_out_example_are_held_out_with_it():
    # Labels are noise, so an honest held-out estimate is near chance. Each line
    # appears twice (as Qasd counts a seed in both contexts); without groups the
    # copy left in training would give the label away.
    rng = random.Random(7)

    def word():
        return "".join(rng.choice("abcdefghijklmnop") for _ in range(7))

    lines = [(" ".join(word() for _ in range(4)), rng.choice("ab")) for _ in range(120)]
    leaky = Tamyiz(words).fit([row for row in lines for _ in range(2)])
    grouped = Tamyiz(words).fit(
        [(text, label, f"g{n}") for n, (text, label) in enumerate(lines) for _ in range(2)]
    )
    assert leaky.loo_accuracy > 0.9
    assert grouped.loo_accuracy < 0.7


def test_learning_is_immediate_and_an_overlay_stays_with_its_owner():
    model = Tamyiz(words).fit(TOY)
    before = model.posterior("zebra")
    model.learn("zebra stripes", "hi", weight=5)
    assert model.posterior("zebra")["hi"] > before["hi"]

    from core.tamyiz import Overlay

    mine = Overlay()
    mine.add("en", model.vector("ghoda ghoda ghoda"), weight=5)
    assert model.predict("ghoda", mine)[0] == "en"
    assert model.posterior("ghoda", Overlay.from_dict(json.loads(json.dumps(mine.to_dict())))) == (
        model.posterior("ghoda", mine)
    )
    assert model.posterior("ghoda") != model.posterior("ghoda", mine)


def test_char_ngrams_mark_word_boundaries():
    grams = char_ngrams("ab", (1, 2))
    assert grams["␠a"] == 1 and grams["b␠"] == 1 and grams["a"] == 1


def test_a_fit_is_kept_with_the_digest_of_its_corpus(tmp_path, monkeypatch):
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(tamyiz_cache, "PACKAGED", tmp_path / "none.json")
    corpus = list(TOY)
    first = tamyiz_cache.fitted("toy", words, lambda: corpus)
    saved = json.loads((tmp_path / "tamyiz.json").read_text())["toy"]
    assert saved["sha256"] == tamyiz_cache.digest(corpus) and len(saved["weights"]) == 3
    again = tamyiz_cache.fitted("toy", words, lambda: corpus)
    assert (again.alpha, again.weights) == (first.alpha, tuple(saved["weights"]))
    corpus.append(("the sun is warm", "en"))  # a changed corpus is refitted, never reused stale
    tamyiz_cache.fitted("toy", words, lambda: corpus)
    assert json.loads((tmp_path / "tamyiz.json").read_text())["toy"]["sha256"] != saved["sha256"]


def test_the_shipped_fits_match_the_shipped_examples():
    """Seeds changed without a refit only slow the first start; run
    ``python -m core.tamyiz_cache`` from backend/ to store the new fit."""
    packaged = json.loads(tamyiz_cache.PACKAGED.read_text(encoding="utf-8"))
    corpora = {
        "lughah": lughah.corpus(),
        "qasd": qasd.examples(),
        **{f"qasd.{name}": qasd.facet_examples(name) for name in ("current", "harder")},
    }
    for name, rows in corpora.items():
        assert packaged[name]["sha256"] == tamyiz_cache.digest(rows), name


# ── Lughah: which language the user writes in ────────────────────────────


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Mujhe aaj ki namaz ka waqt batao", "hi-latn"),
        ("Please tell me today's prayer times", "en"),
        ("مجھے آج نماز کا وقت بتائیں", "ur"),
        ("أخبرني بمواقيت الصلاة اليوم", "ar"),
        ("मुझे आज नमाज़ का समय बताओ", "hi"),
        ("Latest news about Gaza search karo", "hi-latn"),
    ],
)
def test_the_language_is_the_most_probable_one(text, expected):
    assert lughah.language(text) == expected


def test_names_and_quotations_do_not_decide_the_language():
    # "Bukhari 1" is a name and a number: the language is the one this user writes in.
    assert lughah.language("Bukhari 1", prior=["Mujhe hadees sunao yaar"]) == "hi-latn"
    assert lughah.language("Bukhari 1", prior=["Please show me a hadith"]) == "en"
    assert lughah.language("Bukhari 1") == "en"  # no chat yet: the languages tie
    # A quoted ayah inside an English question is material, not the user's language.
    assert lughah.language("What does بِسْمِ ٱللَّهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ mean?") == "en"


# ── Qasd: what a request is for ──────────────────────────────────────────


@pytest.mark.parametrize(
    "text,intent",
    [
        ("Explain recursion simply", "converse"),
        ("Surah Ikhlas sunao", "quran"),
        ("Bukhari 1", "hadith"),
        ("2**100 kitna hai", "compute"),
        ("Pehle 10 prime numbers nikalo program se", "build_and_run"),
        ("Mere liye ek chhota sa notes app bana do", "build_project"),
        ("Help me write a Python script that Ui", "build_and_run"),
        ("Remember that my mother likes jasmine tea", "remember"),
        ("Yaad rakhna main Lucknow mein kaam karta hoon", "remember"),
        ("याद रखना मेरा जन्मदिन 5 मई को है", "remember"),
        ("Do you remember where I work?", "recall"),
        ("I remember my grandfather reciting Surah Yaseen", "converse"),
    ],
)
def test_the_intent_is_the_most_probable_buildable_recipe(text, intent):
    assert fahm.understand(text).intent == intent


def test_asking_how_to_build_is_conversation_not_a_build():
    assert fahm.understand("website kaise banate hain?").intent == "converse"
    assert qasd.prefers("website kaise banate hain?", "converse", "build_project")


def test_a_message_is_split_only_when_one_plan_cannot_hold_it():
    # One program: its request is the whole text, which holds every clause.
    assert (
        fahm.understand_parts("Write a function that adds two numbers and returns the result")
        is None
    )
    # Two lookups of one kind: one plan would hold only one reference.
    parts = fahm.understand_parts("Bukhari 1 aur Bukhari 2 dikhao")
    assert [u.intent for _part, u in parts] == ["hadith", "hadith"]
    parts = fahm.understand_parts("2+2 kitna hai aur aaj ki date kya hai")
    assert [u.intent for _part, u in parts] == ["compute", "waqt"]


def test_a_verified_wording_is_learned_for_that_user_only():
    store = AdaptiveStateStore(None)
    wording = "zxq qorvath blenkish"  # words the seeds never saw
    assert qasd.learn(store, "u1", wording, "web_search", False)
    assert not qasd.learn(store, "u1", wording, "web_search", False)  # once per wording
    mine = qasd.posterior(wording, overlay=qasd.overlay(store, "u1"))
    shared = qasd.posterior(wording, overlay=qasd.overlay(store, "u2"))
    assert mine["web_search"] > shared["web_search"]
    assert qasd.summary(store, "u1")["by_intent"] == {"web_search": 1}
    assert not qasd.learn(store, "u1", "anything", "no_such_intent", False)
