"""Unit tests for backend/qca/morphology_api.py.

Pure-function tests against the real qca root DB and the real
ArabicMorphAnalyzer. No network, no LLM.
"""

import os
import sys

# Make the module importable in both layouts:
# - repo layout: tests/ at repo root, backend/ sibling (repo conftest inserts
#   backend/; the editable install puts the repo root on sys.path for ruh_model)
# - standalone: backend/ next to tests/
# Directories are only added when they actually contain the needed module, so
# a partial tree can never shadow a complete one.
_HERE = os.path.dirname(os.path.abspath(__file__))


def _ensure_importable() -> None:
    try:
        import qca.roots  # noqa: F401

        has_qca = True
    except ImportError:
        has_qca = False
    try:
        import ruh_model.tokenizer.morphology  # noqa: F401

        has_ruh = True
    except ImportError:
        has_ruh = False
    if has_qca and has_ruh:
        return
    repo_root = os.path.abspath(os.path.join(_HERE, ".."))
    backend_dir = os.path.join(repo_root, "backend")
    for base, marker in (
        (backend_dir, os.path.join("qca", "roots.py")),
        (repo_root, os.path.join("ruh_model", "tokenizer", "morphology.py")),
    ):
        if os.path.isfile(os.path.join(base, marker)) and base not in sys.path:
            sys.path.insert(0, base)


_ensure_importable()

from qca.morphology_api import (  # noqa: E402, I001
    HEURISTIC,
    UNAVAILABLE,
    VERIFIED,
    analyze_word,
    bridge_concept,
    build_explain_prompt,
    get_occurrences,
    get_pattern_siblings,
    get_root_family,
    get_senses,
)


# --- analyze_word -----------------------------------------------------------


def test_analyze_ilm_verified():
    r = analyze_word("علم")
    assert r["root"] == "علم"
    assert r["root_provenance"] == VERIFIED
    assert r["provenance"] == VERIFIED
    assert r["pattern"] == "VERB_PAST"
    assert r["pattern_provenance"] == HEURISTIC  # analyzer guess, always tagged
    assert r["wazn"] == "فَعَلَ"
    assert r["wazn_provenance"] == HEURISTIC
    assert "source" in r and r["source"]


def test_analyze_rahm_katb_verified():
    for word, root in (("رحم", "رحم"), ("كتب", "كتب")):
        r = analyze_word(word)
        assert r["root"] == root, word
        assert r["provenance"] == VERIFIED, word


def test_analyze_katb_prefix_recovery():
    # The analyzer greedily strips ka- ("كتب" -> "تب"); the module must
    # recover the surface form and still verify it against the DB.
    r = analyze_word("كتب")
    assert r["root"] == "كتب"
    assert r["provenance"] == VERIFIED
    assert "recovered from the surface form" in r["note"]


def test_analyze_qara_hamza_normalized():
    # DB key is "قرأ"; analyzer normalizes to "قرا" — lookup must still verify.
    r = analyze_word("قرأ")
    assert r["root"] == "قرأ"
    assert r["provenance"] == VERIFIED


def test_analyze_stopword():
    r = analyze_word("في")
    assert r["pattern"] == "STOPWORD"
    assert r["root"] == ""
    assert r["provenance"] == VERIFIED


def test_analyze_english_bridge():
    r = analyze_word("knowledge")
    assert r["root"] == "علم"
    assert r["pattern"] == "CONCEPT_BRIDGE"
    assert r["provenance"] == VERIFIED


def test_analyze_non_arabic_no_bridge_is_heuristic():
    r = analyze_word("xyz")
    assert r["root"] == ""
    assert r["provenance"] == HEURISTIC
    assert r["pattern"] == "NON_ARABIC"


def test_analyze_empty_is_heuristic():
    r = analyze_word("")
    assert r["root"] == ""
    assert r["provenance"] == HEURISTIC


def test_analyze_unknown_root_is_heuristic_not_invented():
    # Analyzer strips the ب prefix and guesses root "ظغث" — not in the DB,
    # so the whole claim must be tagged heuristic, never presented as fact.
    r = analyze_word("بظغث")
    assert r["provenance"] == HEURISTIC
    assert r["root_provenance"] == HEURISTIC
    assert "not in the verified root database" in r["note"]


def test_analyze_always_carries_provenance_and_source():
    for word in ("علم", "بظغث", "xyz", "", "في"):
        r = analyze_word(word)
        assert r["provenance"] in (VERIFIED, HEURISTIC, UNAVAILABLE), word
        assert r["source"], word
        assert r["note"], word


# --- get_root_family --------------------------------------------------------


def test_root_family_ilm():
    f = get_root_family("علم")
    assert f is not None
    assert f["root"] == "علم"
    assert "know" in f["meaning"].lower()
    assert f["meaning_en"] == f["meaning"]
    assert f["domain"] == "epistemology"
    assert f["frequency"] == 854
    assert f["provenance"] == VERIFIED
    assert len(f["derivatives"]) > 0
    surfaces = [d["surface"] for d in f["derivatives"]]
    assert "عِلْم" in surfaces
    assert f["patterns_provenance"] == HEURISTIC


def test_root_family_hamza_normalized_lookup():
    f = get_root_family("قرأ")
    assert f is not None
    assert f["root"] == "قرأ"
    assert f["provenance"] == VERIFIED


def test_root_family_unknown_returns_none():
    assert get_root_family("بظغث") is None
    assert get_root_family("") is None


# --- get_senses -------------------------------------------------------------


def test_senses_rahm():
    s = get_senses("رحم")
    assert s["root"] == "رحم"
    assert s["provenance"] == VERIFIED
    assert s["senses"][0]["kind"] == "root"
    assert len(s["senses"]) > 1
    assert s["ranked_by_context"] is False


def test_senses_context_ranking():
    # Root gloss "knowing — imprinting knowledge on mind" has no "scholar";
    # the derivative عَالِم ("scholar/one who knows") must outrank it.
    s = get_senses("علم", context="scholar")
    assert s["ranked_by_context"] is True
    glosses = [str(x["gloss"]).lower() for x in s["senses"]]
    first_scholar = next(i for i, g in enumerate(glosses) if "scholar" in g)
    root_idx = next(i for i, x in enumerate(s["senses"]) if x["kind"] == "root")
    assert first_scholar < root_idx


def test_senses_unknown_word_empty():
    s = get_senses("بظغث")
    assert s["senses"] == []
    assert s["provenance"] == HEURISTIC


# --- bridge_concept ---------------------------------------------------------


def test_bridge_mercy():
    b = bridge_concept("mercy")
    assert b is not None
    assert b["arabic_root"] == "رحم"
    assert b["provenance"] == VERIFIED
    assert "mercy" in b["root_entry"]["meaning"].lower()
    assert b["source"]


def test_bridge_case_insensitive():
    b = bridge_concept("Mercy")
    assert b is not None
    assert b["arabic_root"] == "رحم"


def test_bridge_unknown_concept_returns_none_404_path():
    assert bridge_concept("flibbertigibbet") is None
    assert bridge_concept("") is None


# --- get_pattern_siblings ---------------------------------------------------


def test_pattern_siblings_unavailable_honest():
    r = get_pattern_siblings("فَعَلَ")
    assert r["available"] is False
    assert r["siblings"] == []
    assert r["provenance"] == UNAVAILABLE
    assert r["reason"]


# --- get_occurrences --------------------------------------------------------


def test_occurrences_unavailable_no_invented_verses():
    r = get_occurrences("علم")
    assert r["available"] is False
    assert r["occurrences"] == []
    assert r["frequency"] == 854  # aggregate count, labeled as such
    assert "not a per-verse occurrence list" in r["frequency_note"]
    assert r["provenance"] == UNAVAILABLE
    assert r["reason"]


# --- build_explain_prompt ---------------------------------------------------


def test_explain_prompt_constrained():
    p = build_explain_prompt("كتب")
    assert p["word"] == "كتب"
    facts = p["verified_facts"]
    assert facts["root"] == "كتب"
    assert facts["root_provenance"] == VERIFIED
    assert len(facts["derivatives"]) > 0
    assert p["provenance"] == VERIFIED
    instr = p["system_instruction"]
    assert "NEVER invent" in instr
    assert "verse numbers" in instr
    assert "not in the verified data" in instr


def test_explain_prompt_unknown_word_stays_honest():
    p = build_explain_prompt("بظغث")
    assert p["verified_facts"]["derivatives"] == []
    assert p["provenance"] == HEURISTIC
