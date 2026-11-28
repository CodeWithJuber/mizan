"""Sullam: the Majlis equal-budget check (He et al. 2026) and the forward shape
(ForgeKit's ladder and evidence_team.js; docs/tadbir.md)."""

import pytest

from core.adaptive import paired_e_value
from tadbir import sullam


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))


def pair(multi_ok, other_ok, multi_tokens=1000, other_tokens=800, intent="web_search"):
    return sullam.record_pair(
        intent, "vote", multi_ok=multi_ok, other_ok=other_ok,
        multi_tokens=multi_tokens, other_tokens=other_tokens,
    )  # fmt: skip


def test_without_evidence_majlis_stays_the_default():
    found = sullam.level("web_search")
    assert found["default"] == "majlis" and found["level"] == "majlis (not enough evidence)"
    assert found["report_only"] is True


def test_a_vote_that_wins_at_equal_budget_becomes_the_default_only_at_e_20():
    assert paired_e_value(6, 0) < 20 <= paired_e_value(7, 0)
    for _ in range(6):
        assert pair(False, True)
    assert sullam.level("web_search")["default"] == "majlis"
    pair(False, True)
    found = sullam.level("web_search")
    assert found["default"] == "vote" and found["level"] == "vote"
    assert found["evidence"]["vote"]["wins"] == 7


def test_ties_carry_no_evidence_and_majlis_can_prove_itself():
    for _ in range(20):
        pair(True, True)
        pair(False, False)
    assert sullam.level("web_search")["evidence"]["vote"]["challenger_better"] == 1.0
    for _ in range(7):
        pair(True, False)
    found = sullam.level("web_search")
    assert found["default"] == "majlis" and found["level"] == "majlis"


def test_a_challenger_given_more_budget_is_no_pair():
    assert not pair(False, True, multi_tokens=500, other_tokens=900)
    assert sullam.level("web_search")["evidence"]["vote"]["pairs"] == 0


def test_the_agi_test_records_a_pair_only_for_a_multi_agent_answer():
    rows = [
        {"arm": "base", "pass": True, "input_tokens": 300, "output_tokens": 200},
        {"arm": "mizan", "pass": False, "input_tokens": 900, "output_tokens": 300},
    ]
    alone = {"mizan": {"orchestration": {"intent": "web_search", "agents": [{"agent": "K"}]}}}
    assert not sullam.observe_compare(alone, rows)
    shared = {
        "mizan": {
            "orchestration": {
                "intent": "web_search",
                "agents": [{"agent": "Katib"}, {"agent": "Mundhir"}],
            }
        }
    }
    assert sullam.observe_compare(shared, rows)
    assert sullam.level("web_search")["evidence"]["vote"]["wins"] == 1


def test_forward_deals_disjoint_slices_most_constrained_role_first():
    evidence = [
        {"kind": "code", "id": 1},
        {"kind": "web", "id": 2},
        {"kind": "page", "id": 3},
        {"kind": "web", "id": 4},
        {"kind": "audio", "id": 5},
    ]
    slices = sullam.deal(evidence, ["khalifah", "mubashir", "katib"])
    dealt = [item["id"] for part in slices.values() for item in part]
    assert sorted(dealt) == [1, 2, 3, 4, 5]  # every item once
    assert [item["id"] for item in slices["katib"]] == [1]  # the only role-1 item it can use
    assert {item["id"] for item in slices["mubashir"]} <= {2, 3, 4}
    assert [item["id"] for item in slices["lead"]] == [5]  # no role can use it


def test_the_lead_gets_one_deduplicated_facts_packet():
    packet = sullam.facts_packet(
        [
            {"role": "katib", "facts": [{"text": "The file has 3 rows.", "source": "a.csv"}]},
            {"role": "mundhir", "facts": ["the file has   3 rows.", "It was made in 2024."]},
        ]
    )
    assert packet[0] == {"text": "The file has 3 rows.", "by": ["katib", "mundhir"],
                         "sources": ["a.csv"]}  # fmt: skip
    assert len(packet) == 2
