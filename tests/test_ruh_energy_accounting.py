"""Energy telemetry must be independent of dashboard polling frequency."""

import pytest

from core.ruh_engine import RuhEngine


@pytest.fixture
def clock(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr("core.ruh_engine.time.time", lambda: now[0])
    return now


def test_repeated_status_reads_do_not_recredit_rest(clock):
    engine = RuhEngine()
    engine.initialize_agent("a").energy = 40
    engine.rest("a")
    clock[0] += 60
    for _ in range(10):
        assert engine.get_vitality_report("a")["energy"] == 42
        assert engine.can_handle_task("a", "complex")
    clock[0] += 30
    assert engine.get_state("a").energy == 43


def test_passive_regeneration_is_independent_of_polling(clock):
    engine = RuhEngine()
    engine.initialize_agent("polled").energy = 40
    engine.initialize_agent("idle").energy = 40
    for _ in range(6):
        clock[0] += 30
        engine.get_state("polled")
    assert engine.get_state("polled").energy == pytest.approx(41.2)
    assert engine.get_state("idle").energy == pytest.approx(41.2)


def test_new_activity_stops_rest_and_restarts_idle_grace(clock):
    engine = RuhEngine()
    engine.initialize_agent("a").energy = 40
    engine.rest("a")
    clock[0] += 60
    assert engine.consume_energy("a", "trivial") == 40
    clock[0] += 60
    assert engine.get_state("a").energy == 40
    clock[0] += 60
    assert engine.get_state("a").energy == pytest.approx(40.6)


def test_clock_rollback_cannot_credit_an_interval_twice(clock):
    engine = RuhEngine()
    engine.initialize_agent("a").energy = 40
    engine.rest("a")
    clock[0] += 60
    assert engine.get_state("a").energy == 42
    clock[0] -= 30
    assert engine.get_state("a").energy == 42
    clock[0] += 30
    assert engine.get_state("a").energy == 42
