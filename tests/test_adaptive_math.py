"""Adaptive estimators replace fixed thresholds (Mizan: weigh the evidence)."""

import random
import time
from datetime import UTC, datetime, timedelta

import pytest

from core.adaptive import (
    AdaptiveStateStore,
    BetaEstimator,
    EWStats,
    actr_activation,
    bm25_scores,
    regularized_beta,
    softmax,
    thompson_choice,
    wilson_bounds,
)
from core.developmental_stages import DevelopmentalGate
from core.ruh_engine import RuhEngine
from core.shukr import ShukrSystem
from memory.dhikr import Memory, memory_activation_weight, rank_memories
from task_queue.task_queue import QueuedTask, effective_priority


def test_wilson_interval_narrows_with_evidence():
    small = wilson_bounds(8, 10)
    large = wilson_bounds(800, 1000)
    assert small[0] < large[0] < 0.8 < large[1] < small[1]


def test_regularized_beta_matches_known_values():
    assert regularized_beta(0.5, 2, 2) == pytest.approx(0.5)
    assert regularized_beta(0.3, 5, 7) == pytest.approx(0.2103, abs=1e-3)
    assert regularized_beta(0.0, 3, 3) == 0.0 and regularized_beta(1.0, 3, 3) == 1.0


def test_posterior_probability_rises_with_consistent_evidence():
    few = BetaEstimator().update(1.0, 4)
    many = BetaEstimator().update(1.0, 40)
    assert many.probability_at_least(0.8) > few.probability_at_least(0.8)


def test_forgetting_lets_the_estimate_track_change():
    remembered = BetaEstimator()
    forgetful = BetaEstimator(forgetting=0.9)
    for _ in range(50):
        remembered.update(True)
        forgetful.update(True)
    for _ in range(10):
        remembered.update(False)
        forgetful.update(False)
    assert forgetful.mean < remembered.mean


def test_thompson_sampling_prefers_the_better_arm():
    rng = random.Random(7)
    posteriors = {
        "good": BetaEstimator().update(1.0, 30).update(0.0, 3),
        "poor": BetaEstimator().update(1.0, 10).update(0.0, 20),
    }
    picks = [thompson_choice(["good", "poor"], posteriors, rng) for _ in range(200)]
    assert picks.count("good") > 180


def test_ew_stats_flags_a_sudden_drop():
    stats = EWStats(smoothing=0.2)
    for value in [0.9, 0.92, 0.88, 0.91, 0.9, 0.89]:
        stats.update(value)
    assert stats.z(0.4) < -1.0
    assert abs(stats.z(0.9)) < 1.0


def test_actr_repetition_outlasts_a_single_recent_touch():
    once = actr_activation([3600])
    spaced = actr_activation([3600, 86400, 3 * 86400, 7 * 86400])
    assert spaced > once
    day, month = 86400, 30 * 86400
    assert memory_activation_weight(month, 10) > memory_activation_weight(month, 0)
    assert memory_activation_weight(day, 0) > memory_activation_weight(month, 0)


def test_bm25_ranks_the_relevant_document_first():
    scores = bm25_scores(
        "sabr patience trial",
        ["notes about prayer times", "patience (sabr) during a trial", "trial run of the app"],
    )
    assert scores.index(max(scores)) == 1


def test_softmax_temperature_controls_sharpness():
    flat, sharp = softmax([0.1, 0.2, 0.3], 1.0), softmax([0.1, 0.2, 0.3], 0.05)
    assert max(sharp) > max(flat)


def test_complexity_uses_words_not_substrings():
    ruh = RuhEngine()
    # "this" contains "hi" and "architect" contains "hi": no longer "trivial".
    assert ruh.classify_task_complexity("refactor this module") == "complex"
    assert ruh.classify_task_complexity("architect a new microservice platform") == "extreme"
    long_request = " ".join(["Please handle the migration plan in detail."] * 12)
    assert ruh.task_complexity_score(long_request) > ruh.task_complexity_score("hello")


def test_nafs_promotion_weighs_the_evidence():
    gate = DevelopmentalGate()

    class Agent:
        nafs_level = 1
        total_tasks = 30
        success_count = 20
        success_rate = 20 / 30
        hikmah_count = 0

    assert gate.check_upgrade_readiness(Agent).ready
    Agent.success_count, Agent.success_rate = 15, 0.5
    assert not gate.check_upgrade_readiness(Agent).ready


def test_shukr_selection_uses_posteriors():
    shukr = ShukrSystem()
    for _ in range(8):
        shukr.record_success("a", "coding", "x")
    for _ in range(4):
        shukr.record_success("b", "coding", "x")
        shukr.record_failure("b", "coding", "x")
    assert shukr.get_best_agent_for(["a", "b"], "coding") == "a"
    rng = random.Random(1)
    picks = [shukr.sample_best_agent(["a", "b"], "coding", rng) for _ in range(100)]
    assert picks.count("a") > picks.count("b")


def test_queue_aging_prevents_starvation():
    now = time.time()
    urgent_new = QueuedTask(priority=0, created_at=now, task_id="u", payload={})
    waiting_low = QueuedTask(priority=2, created_at=now - 3 * 3600, task_id="w", payload={})
    assert effective_priority(waiting_low, now) < effective_priority(urgent_new, now)
    fresh_low = QueuedTask(priority=2, created_at=now, task_id="f", payload={})
    assert effective_priority(fresh_low, now) > effective_priority(urgent_new, now)


def test_memory_ranking_prefers_relevant_and_remembered():
    now = datetime.now(UTC)
    memories = [
        Memory(id="1", content="grocery list", importance=0.9, recency=now, access_count=0),
        Memory(
            id="2",
            content="the user's sabr practice notes",
            importance=0.5,
            recency=now - timedelta(days=3),
            access_count=12,
        ),
    ]
    assert rank_memories("sabr practice", memories, now)[0].id == "2"


def test_adaptive_state_persists_across_instances(tmp_path):
    path = str(tmp_path / "state.db")
    store = AdaptiveStateStore(path)
    store.put("tool:read_file", BetaEstimator().update(True).update(True).to_dict())
    reloaded = AdaptiveStateStore(path).beta("tool:read_file")
    assert reloaded.successes == 2
