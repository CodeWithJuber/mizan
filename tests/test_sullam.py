"""Sullam: the Majlis equal-budget check (He et al. 2026) and the forward shape
(ForgeKit's ladder and evidence_team.js; docs/tadbir.md)."""

import pytest

from tadbir import sullam


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))


def suite(n=30, pool_size=8, k_correct=2, group_correct=lambda q: True, group_tokens=400, unit=100):
    """n questions; each has pool_size independent single answers, k_correct right."""
    group, pool = [], []
    for q in range(n):
        qid = f"q{q:02d}"
        group.append({"id": qid, "correct": group_correct(q), "tokens": group_tokens})
        pool.extend({"id": qid, "correct": j < k_correct, "tokens": unit} for j in range(pool_size))
    return group, pool


def test_pass_at_n_and_the_majority_vote_are_exact():
    # The values ForgeKit's ladder tests check by hand (test/ladder.test.js).
    assert sullam.pass_at_n(4, 1, 1) == pytest.approx(0.25)
    assert sullam.pass_at_n(4, 1, 2) == pytest.approx(1 - (3 / 4) * (2 / 3))
    assert sullam.pass_at_n(4, 1, 4) == 1 and sullam.pass_at_n(10, 0, 5) == 0
    assert sullam.majority_at_n(4, 2, 3) == pytest.approx(0.5)  # C(2,2)·C(2,1)/C(4,3)
    assert sullam.majority_at_n(4, 2, 2) == pytest.approx(0.5)  # a tie counts one half
    assert sullam.majority_at_n(5, 2, 1) == pytest.approx(2 / 5)


def test_pass_at_n_bounds_the_vote_on_seeded_pools():
    import random

    rng = random.Random(11)
    for _ in range(200):
        m = rng.randint(2, 15)
        k, n = rng.randint(0, m), rng.randint(1, m)
        t, v1, vn = (sullam.pass_at_n(m, k, n), sullam.majority_at_n(m, k, 1),
                     sullam.majority_at_n(m, k, n))  # fmt: skip
        assert t >= max(v1, vn) - 1e-9 and t <= min(1, n * v1) + 1e-9


def test_the_paired_one_sided_t_test_matches_the_t_table():
    d = [1 if i % 2 else -1 for i in range(20)]
    sd = (sum(x * x for x in d) / 19) ** 0.5
    found = sullam.paired_one_sided([x + 2.093 * sd / 20**0.5 for x in d])
    assert found["t"] == pytest.approx(2.093) and found["p"] == pytest.approx(0.025, abs=1e-4)
    assert sullam.paired_one_sided([0.5])["p"] is None  # one question cannot be tested
    assert sullam.paired_one_sided([0.2, 0.2, 0.2])["p"] == 0  # no spread, positive mean


def test_a_team_that_solves_what_one_answer_solves_a_quarter_of_the_time_clears_all_levels():
    found = sullam.grade(*suite(group_tokens=300))  # n_B = 3
    assert found["n_b"] == 3 and found["level"] == 3


def test_levels_are_monotone_and_a_vote_that_does_as_well_is_reported():
    # Right 60% of the time; one answer 25%; pass@3 of 8-with-2 ≈ 0.64.
    found = sullam.grade(*suite(n=60, group_correct=lambda q: q % 5 < 3, group_tokens=300))
    assert found["tests"]["1"]["cleared"] and not found["tests"]["3"]["cleared"]
    assert 1 <= found["level"] < 3


def test_too_few_single_answers_leave_the_vote_undecided():
    found = sullam.grade(*suite(pool_size=2, group_tokens=400))  # n_B = 4, only 2 answers
    assert found["tests"]["2"]["indeterminate"] and found["level"] <= 1
    assert any("more repeats" in w for w in found["warnings"])


def run(arm, question, correct, tokens, intent="web_search"):
    return sullam.record_run(arm, question, correct=correct, tokens=tokens, intent=intent)


def test_without_evidence_majlis_stays_the_reported_default():
    found = sullam.level("web_search")
    assert found["default"] == "majlis" and found["verdict"] == "not enough evidence yet"
    assert found["report_only"] is True and found["level"] == 0


def test_a_team_no_better_than_the_vote_at_the_same_budget_is_reported_as_such():
    for q in range(30):
        for j in range(4):
            run("pool", f"t{q}", j < 2, 100)  # half of the single answers are right
        run("group", f"t{q}", q % 2 == 0, 300)  # the team: half right, three times the budget
    found = sullam.level("web_search")
    assert found["default"] == "vote" and found["level"] == 0
    assert found["verdict"].startswith("a vote of single answers")


def test_a_team_that_beats_the_vote_stays_the_default():
    for q in range(30):
        for j in range(4):
            run("pool", f"t{q}", j < 1, 100)
        run("group", f"t{q}", True, 200)
    found = sullam.level("web_search")
    assert found["level"] >= 2 and found["default"] == "majlis"
    assert found["verdict"].startswith("Majlis beats")


def test_a_run_without_a_token_count_is_not_priced():
    assert not run("pool", "t1", True, None)
    assert not run("group", "t1", True, 100, intent="")
    assert sullam.level("web_search")["questions"] == 0


def test_the_agi_test_adds_every_base_answer_to_the_pool_and_only_multi_agent_runs_to_the_group():
    rows = [
        {"arm": "base", "task_id": "t1", "pass": True, "output_tokens": 200},
        {"arm": "mizan", "task_id": "t1", "pass": False, "output_tokens": 600},
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
    found = sullam.level("web_search")
    assert found["questions"] == 1 and found["c1"] == 200 and found["n_b"] == 3


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
