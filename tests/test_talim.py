"""Ta'lim: an administrator teaches MIZAN, and a batch that makes it worse is refused."""

import pytest

from tadbir import lisan, lughah, qasd, talim

TAMIL = [
    "இன்று என்ன தேதி?",
    "நான் பள்ளிக்கு செல்கிறேன்",
    "உங்கள் பெயர் என்ன?",
    "இது ஒரு நல்ல நாள்",
    "எனக்கு தண்ணீர் வேண்டும்",
    "நாளை மழை பெய்யுமா?",
    "அவர் புத்தகம் படிக்கிறார்",
    "நீங்கள் எப்படி இருக்கிறீர்கள்?",
    "இந்த ஊரில் மசூதி எங்கே?",
    "தொழுகை நேரம் என்ன?",
    "எனக்கு உதவி செய்யுங்கள்",
    "இது எவ்வளவு விலை?",
]


@pytest.fixture(autouse=True)
def fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("MIZAN_TALIM", raising=False)
    for name in ("lughah", "qasd", "qasd.ruling"):
        talim._clear(name)
    yield
    for name in ("lughah", "qasd", "qasd.ruling"):
        talim._clear(name)


def test_the_bootstrap_says_worse_only_when_the_evidence_says_so():
    same = [True] * 100
    assert talim.p_worse(same, same) == 0.0
    one_flip = [True] * 99 + [False]
    assert talim.p_worse(same, one_flip) < talim.REFUSE_AT  # one slip is not evidence
    many = [True] * 70 + [False] * 30
    assert talim.p_worse(same, many) >= talim.REFUSE_AT


def test_a_harmless_batch_is_kept_read_at_once_and_can_be_undone():
    before = len(qasd.facet_examples("ruling"))
    kept = talim.teach(
        "qasd.ruling",
        [("Is it permissible to pray with shoes on?", "yes"), ("Explain photosynthesis", "no")],
        source="test",
        licence="CC0",
        by="admin",
    )
    assert kept["status"] == "kept" and kept["p_worse"] < talim.REFUSE_AT
    assert len(qasd.facet_examples("ruling")) == before + 2
    assert [b["status"] for b in talim.batches()] == ["kept"]
    assert talim.undo(kept["batch"], "admin")
    assert len(qasd.facet_examples("ruling")) == before
    assert not talim.undo(kept["batch"], "admin")  # once


def test_a_batch_that_makes_mizan_worse_is_refused_and_changes_nothing():
    flipped = [
        (text, "no" if label == "yes" else "yes") for text, label in qasd.facet_examples("ruling")
    ]
    refused = talim.teach("qasd.ruling", flipped * 3, source="test", licence="", by="admin")
    assert refused["status"] == "refused" and refused["p_worse"] >= talim.REFUSE_AT
    assert refused["after"] < refused["before"] and refused["changed_classes"]
    assert talim.rows("qasd.ruling") == []  # nothing of it is used


def test_a_new_language_is_learned_and_named_for_lisan():
    with pytest.raises(ValueError):
        talim.check("lughah", [("இன்று என்ன தேதி?", "ta")])  # a new language needs its name
    taught = talim.teach(
        "lughah",
        [(text, "ta") for text in TAMIL],
        source="written for the test",
        licence="CC0",
        by="admin",
        language_name="Tamil",
    )
    assert taught["status"] == "kept" and taught["learned"] == 1.0
    assert "ta" in lughah.languages()
    assert lughah.language("நாளை எத்தனை மணிக்கு தொழுகை?") == "ta"
    assert lughah.language("What is the date today?") == "en"
    assert lisan.language_name("ta") == "Tamil"
    # MIZAN_TALIM=off sets every taught batch aside.
    import os

    os.environ["MIZAN_TALIM"] = "off"
    try:
        talim._clear("lughah")
        assert "ta" not in lughah.languages()
    finally:
        del os.environ["MIZAN_TALIM"]


def test_only_the_models_own_labels_are_taught():
    with pytest.raises(ValueError):
        talim.check("qasd", [("Book me a flight", "book_flight")])
    with pytest.raises(ValueError):
        talim.check("no-such-model", [("x", "y")])
    assert talim.from_rows(
        [{"utt": "wake me at 6", "intent": "alarm_set"}, {"utt": "hi", "intent": "greet"}],
        "utt",
        "intent",
        {"greet": "converse"},
    ) == [("hi", "converse")]


def test_teaching_is_for_administrators_only(tmp_path):
    from fastapi.testclient import TestClient

    import api.main as main

    member = main.auth.create_token(main.auth.create_user("talimuser", "pw", roles=["user"]))
    client = TestClient(main.app)
    denied = client.get("/api/tadbir/talim", headers={"Authorization": f"Bearer {member}"})
    assert denied.status_code == 403
    admin = main.auth.create_token(main.auth.create_user("talimadmin", "pw", roles=["admin"]))
    seen = client.get("/api/tadbir/talim", headers={"Authorization": f"Bearer {admin}"})
    assert seen.status_code == 200 and "qasd" in seen.json()["models"]
