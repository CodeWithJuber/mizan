"""
Comprehensive Core Systems Tests — Ruh, Qalb, Tawbah, Ihsan, Sabr, Shukr
===========================================================================

Real use cases:
  - Agent works hard → energy depletes → rest regenerates
  - User is frustrated → Qalb detects → suggests patient tone
  - Task fails → Tawbah guides recovery → lessons learned
  - Good performance → Ihsan suggests improvements
  - Long task → Sabr decomposes into steps → tracks progress
  - Repeated success → Shukr builds confidence → identifies strengths
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from core.ihsan import IhsanMode
from core.qalb import EmotionalState, QalbEngine, QalbReading, ToneStyle
from core.ruh_engine import RuhEngine
from core.sabr import SabrEngine, SabrTaskState
from core.shukr import ShukrSystem
from core.tawbah import TawbahProtocol, TawbahStage

# ═══════════════════════════════════════════════════════════════════════════════
# RUH ENGINE — Agent Energy System
# ═══════════════════════════════════════════════════════════════════════════════


class TestRuhEnginePositive:
    @pytest.fixture
    def ruh(self):
        return RuhEngine()

    def test_agent_starts_full_energy(self, ruh):
        state = ruh.get_state("agent-1")
        assert state.energy == 100.0
        assert state.fatigue_level == 0.0

    def test_trivial_task_low_cost(self, ruh):
        ruh.consume_energy("agent-1", "trivial")
        state = ruh.get_state("agent-1")
        assert state.energy >= 95.0  # Only costs 2.0

    def test_complex_task_high_cost(self, ruh):
        ruh.consume_energy("agent-1", "complex")
        state = ruh.get_state("agent-1")
        assert state.energy <= 75.0  # Costs 30.0

    def test_extreme_task_very_high_cost(self, ruh):
        ruh.consume_energy("agent-1", "extreme")
        state = ruh.get_state("agent-1")
        assert state.energy <= 55.0  # Costs 50.0

    def test_energy_never_below_zero(self, ruh):
        for _ in range(10):
            ruh.consume_energy("agent-1", "extreme")
        state = ruh.get_state("agent-1")
        assert state.energy >= 0.0

    def test_can_handle_when_enough_energy(self, ruh):
        assert ruh.can_handle_task("agent-1", "complex") is True

    def test_cannot_handle_when_exhausted(self, ruh):
        for _ in range(5):
            ruh.consume_energy("agent-1", "extreme")
        assert ruh.can_handle_task("agent-1", "extreme") is False

    def test_task_complexity_classification(self, ruh):
        assert ruh.classify_task_complexity("hello") == "trivial"
        assert ruh.classify_task_complexity("read the file") == "simple"
        assert ruh.classify_task_complexity("analyze the data") == "moderate"
        assert ruh.classify_task_complexity("implement the feature") == "complex"
        assert ruh.classify_task_complexity("overhaul the full system") == "extreme"

    def test_fatigue_label(self, ruh):
        assert ruh.get_fatigue_label("agent-1") == "fresh"
        ruh.consume_energy("agent-1", "extreme")
        ruh.consume_energy("agent-1", "extreme")
        label = ruh.get_fatigue_label("agent-1")
        assert label in ("exhausted", "tired", "working", "alert")

    def test_vitality_report_structure(self, ruh):
        report = ruh.get_vitality_report("agent-1")
        assert "energy" in report
        assert "max_energy" in report
        assert "energy_percent" in report
        assert "fatigue_level" in report
        assert "fatigue_label" in report
        assert "tasks_since_rest" in report
        assert "is_resting" in report

    def test_rest_resets_tasks_counter(self, ruh):
        ruh.consume_energy("agent-1", "moderate")
        ruh.consume_energy("agent-1", "moderate")
        state = ruh.get_state("agent-1")
        assert state.total_tasks_since_rest == 2
        ruh.rest("agent-1")
        state = ruh.get_state("agent-1")
        assert state.total_tasks_since_rest == 0

    def test_find_most_rested(self, ruh):
        ruh.get_state("a")
        ruh.get_state("b")
        ruh.consume_energy("a", "extreme")
        ruh.consume_energy("a", "extreme")
        best = ruh.find_most_rested(["a", "b"])
        assert best == "b"

    def test_multiple_agents_independent(self, ruh):
        ruh.consume_energy("agent-a", "extreme")
        state_a = ruh.get_state("agent-a")
        state_b = ruh.get_state("agent-b")
        assert state_a.energy < state_b.energy


class TestRuhEngineNegative:
    @pytest.fixture
    def ruh(self):
        return RuhEngine()

    def test_find_most_rested_empty(self, ruh):
        assert ruh.find_most_rested([]) is None

    def test_unknown_complexity(self, ruh):
        """Unknown complexity should use default cost."""
        initial = ruh.get_state("agent-1").energy
        ruh.consume_energy("agent-1", "made_up_complexity")
        after = ruh.get_state("agent-1").energy
        assert after < initial  # Default cost should apply

    def test_fatigue_increases_with_work(self, ruh):
        ruh.consume_energy("agent-1", "extreme")
        state = ruh.get_state("agent-1")
        assert state.fatigue_level > 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# QALB ENGINE — Emotional Intelligence
# ═══════════════════════════════════════════════════════════════════════════════


class TestQalbEnginePositive:
    @pytest.fixture
    def qalb(self):
        return QalbEngine()

    def test_detect_frustration(self, qalb):
        reading = qalb.analyze("I'm so frustrated, this keeps failing!")
        assert reading.state == EmotionalState.FRUSTRATED
        assert reading.recommended_tone == ToneStyle.PATIENT

    def test_detect_anxiety(self, qalb):
        reading = qalb.analyze("I'm worried about the deadline, feeling stressed")
        assert reading.state == EmotionalState.ANXIOUS
        assert reading.recommended_tone == ToneStyle.ENCOURAGING

    def test_detect_confusion(self, qalb):
        reading = qalb.analyze("I'm confused, don't understand how this works")
        assert reading.state == EmotionalState.CONFUSED
        assert reading.recommended_tone == ToneStyle.PATIENT

    def test_detect_positive(self, qalb):
        reading = qalb.analyze("Thanks! This is awesome, great work!")
        assert reading.state == EmotionalState.POSITIVE
        assert reading.recommended_tone == ToneStyle.WARM

    def test_detect_determined(self, qalb):
        reading = qalb.analyze("Let's do this, need to focus on the goal")
        assert reading.state == EmotionalState.DETERMINED
        assert reading.recommended_tone == ToneStyle.FOCUSED

    def test_detect_fatigued(self, qalb):
        reading = qalb.analyze("I'm so tired and exhausted, too much today")
        assert reading.state == EmotionalState.FATIGUED
        assert reading.recommended_tone == ToneStyle.ENCOURAGING

    def test_neutral_default(self, qalb):
        reading = qalb.analyze("Process the data from the CSV file")
        assert reading.state == EmotionalState.NEUTRAL
        assert reading.recommended_tone == ToneStyle.STANDARD

    def test_record_and_get_trend(self, qalb):
        for _ in range(5):
            reading = qalb.analyze("I'm frustrated again")
            qalb.record("user-1", reading)
        trend = qalb.get_trend("user-1")
        assert trend["dominant_state"] == "frustrated"
        assert trend["stability"] == 1.0
        assert trend["readings"] == 5

    def test_suggest_response_prefix_frustrated(self, qalb):
        reading = qalb.analyze("I'm so frustrated, this keeps failing over and over!")
        prefix = qalb.suggest_response_prefix(reading)
        assert prefix is not None
        assert "frustrating" in prefix.lower()

    def test_suggest_response_prefix_neutral(self, qalb):
        reading = qalb.analyze("do the task")
        prefix = qalb.suggest_response_prefix(reading)
        assert prefix is None  # No prefix for neutral

    def test_reading_to_dict(self, qalb):
        reading = qalb.analyze("test message")
        d = reading.to_dict()
        assert "state" in d
        assert "confidence" in d
        assert "recommended_tone" in d


class TestQalbEngineNegative:
    @pytest.fixture
    def qalb(self):
        return QalbEngine()

    def test_empty_message(self, qalb):
        reading = qalb.analyze("")
        assert reading.state == EmotionalState.NEUTRAL

    def test_trend_no_history(self, qalb):
        trend = qalb.get_trend("nonexistent-user")
        assert trend["dominant_state"] == "neutral"
        assert trend["readings"] == 0

    def test_mixed_emotions_picks_strongest(self, qalb):
        reading = qalb.analyze("I'm stuck and frustrated but also worried about the deadline")
        # Should pick the strongest signal
        assert reading.state in (EmotionalState.FRUSTRATED, EmotionalState.ANXIOUS)

    def test_history_limit(self, qalb):
        for _i in range(150):
            reading = QalbReading(
                state=EmotionalState.NEUTRAL,
                confidence=0.5,
                recommended_tone=ToneStyle.STANDARD,
            )
            qalb.record("user-x", reading)
        assert len(qalb._history["user-x"]) <= 100


# ═══════════════════════════════════════════════════════════════════════════════
# TAWBAH PROTOCOL — Error Recovery
# ═══════════════════════════════════════════════════════════════════════════════


class TestTawbahProtocolPositive:
    @pytest.fixture
    def tawbah(self):
        return TawbahProtocol()

    def test_full_recovery_cycle(self, tawbah):
        """Complete Tawbah cycle: acknowledge → analyze → plan → apply → verify."""
        record = tawbah.acknowledge("agent-1", ValueError("null pointer"), "read file")
        assert record.stage == TawbahStage.ACKNOWLEDGE

        tawbah.analyze(record, "File path was None")
        assert record.stage == TawbahStage.ANALYZE

        tawbah.plan(record, "Add None check before file read")
        assert record.stage == TawbahStage.PLAN

        tawbah.apply(record, "Added null check at line 42")
        assert record.stage == TawbahStage.APPLY

        tawbah.verify(record, success=True, lesson="Always validate file paths")
        assert record.stage == TawbahStage.COMPLETE
        assert record.success is True
        assert record.verified is True

    def test_lessons_learned(self, tawbah):
        record = tawbah.acknowledge("agent-1", "Error", "task")
        tawbah.analyze(record, "root cause")
        tawbah.plan(record, "fix plan")
        tawbah.apply(record, "fix applied")
        tawbah.verify(record, success=True, lesson="Always check inputs")

        lessons = tawbah.get_lessons()
        assert len(lessons) == 1
        assert lessons[0]["lesson"] == "Always check inputs"

    def test_failed_verification_retries(self, tawbah):
        record = tawbah.acknowledge("agent-1", "Error", "task")
        tawbah.analyze(record, "cause")
        tawbah.plan(record, "plan")
        tawbah.apply(record, "fix")
        tawbah.verify(record, success=False)
        # Should go back to ANALYZE for retry
        assert record.stage == TawbahStage.ANALYZE
        assert record.attempts == 2

    def test_max_attempts_reached(self, tawbah):
        record = tawbah.acknowledge("agent-1", "Error", "task")
        for _ in range(3):
            tawbah.analyze(record, "cause")
            tawbah.plan(record, "plan")
            tawbah.apply(record, "fix")
            tawbah.verify(record, success=False)
        assert record.stage == TawbahStage.COMPLETE
        assert record.success is False

    def test_has_prior_fix(self, tawbah):
        record = tawbah.acknowledge("agent-1", TypeError("type mismatch"), "task")
        tawbah.analyze(record, "wrong type")
        tawbah.plan(record, "cast type")
        tawbah.apply(record, "added cast")
        tawbah.verify(record, success=True)

        prior = tawbah.has_prior_fix("TypeError")
        assert prior is not None
        assert prior["error_type"] == "TypeError"

    def test_error_patterns_tracked(self, tawbah):
        tawbah.acknowledge("a", ValueError("x"), "task1")
        tawbah.acknowledge("a", ValueError("y"), "task2")
        tawbah.acknowledge("a", TypeError("z"), "task3")
        patterns = tawbah.get_pattern_frequency()
        assert patterns.get("ValueError", 0) == 2
        assert patterns.get("TypeError", 0) == 1

    def test_record_to_dict(self, tawbah):
        record = tawbah.acknowledge("a", "err", "task")
        d = record.to_dict()
        assert "id" in d
        assert "agent_id" in d
        assert "error_type" in d
        assert "stage" in d
        assert "duration_s" in d

    def test_stats(self, tawbah):
        record = tawbah.acknowledge("a", "err", "task")
        tawbah.verify(record, success=True)
        stats = tawbah.stats()
        assert stats["total_recoveries"] == 1
        assert stats["successful"] == 1


class TestTawbahProtocolNegative:
    @pytest.fixture
    def tawbah(self):
        return TawbahProtocol()

    def test_no_prior_fix(self, tawbah):
        assert tawbah.has_prior_fix("NonexistentError") is None

    def test_get_active_no_records(self, tawbah):
        assert tawbah.get_active_recoveries("agent-x") == []

    def test_string_error(self, tawbah):
        """Should handle string errors, not just Exceptions."""
        record = tawbah.acknowledge("a", "Something went wrong", "task")
        assert record.error_type == "TaskError"
        assert record.error_message == "Something went wrong"


# ═══════════════════════════════════════════════════════════════════════════════
# IHSAN MODE — Proactive Excellence
# ═══════════════════════════════════════════════════════════════════════════════


class TestIhsanModePositive:
    @pytest.fixture
    def ihsan(self):
        return IhsanMode()

    def test_eligible_at_mulhama(self, ihsan):
        assert ihsan.is_eligible(3) is True
        assert ihsan.is_eligible(4) is True

    def test_not_eligible_below_mulhama(self, ihsan):
        assert ihsan.is_eligible(1) is False
        assert ihsan.is_eligible(2) is False

    def test_coding_task_suggests_tests(self, ihsan):
        suggestions = ihsan.analyze_completion(
            "agent-1",
            "implement the login feature",
            {"success": True},
            nafs_level=3,
        )
        assert len(suggestions) > 0
        assert any("test" in s.suggestion.lower() for s in suggestions)

    def test_delete_task_suggests_backup(self, ihsan):
        suggestions = ihsan.analyze_completion(
            "agent-1",
            "delete the old config file",
            {"success": True},
            nafs_level=3,
        )
        assert any("backup" in s.suggestion.lower() for s in suggestions)

    def test_failed_task_suggests_error_handling(self, ihsan):
        suggestions = ihsan.analyze_completion(
            "agent-1",
            "process data",
            {"success": False},
            nafs_level=3,
        )
        assert any("error" in s.suggestion.lower() for s in suggestions)

    def test_slow_task_suggests_optimization(self, ihsan):
        suggestions = ihsan.analyze_completion(
            "agent-1",
            "analyze the dataset",
            {"success": True, "duration_ms": 15000},
            nafs_level=3,
        )
        assert any(
            "optimization" in s.category or "cach" in s.suggestion.lower() for s in suggestions
        )

    def test_feedback_updates_acceptance(self, ihsan):
        suggestions = ihsan.analyze_completion(
            "agent-1",
            "write code",
            {"success": True},
            nafs_level=3,
        )
        ihsan.record_feedback(suggestions[0].id, accepted=True)
        assert ihsan.get_acceptance_rate() > 0

    def test_stats(self, ihsan):
        ihsan.analyze_completion("a", "code task", {"success": True}, nafs_level=3)
        s = ihsan.stats()
        assert s["total_suggestions"] > 0


class TestIhsanModeNegative:
    @pytest.fixture
    def ihsan(self):
        return IhsanMode()

    def test_low_nafs_no_suggestions(self, ihsan):
        suggestions = ihsan.analyze_completion(
            "agent-1",
            "implement feature",
            {"success": True},
            nafs_level=1,
        )
        assert len(suggestions) == 0

    def test_generic_task_may_have_no_suggestions(self, ihsan):
        suggestions = ihsan.analyze_completion(
            "agent-1",
            "hello world",
            {"success": True, "duration_ms": 100},
            nafs_level=3,
        )
        # Generic task with fast execution — may produce 0 suggestions
        assert isinstance(suggestions, list)


# ═══════════════════════════════════════════════════════════════════════════════
# SABR ENGINE — Long-Running Task Management
# ═══════════════════════════════════════════════════════════════════════════════


class TestSabrEnginePositive:
    @pytest.fixture
    def sabr(self):
        return SabrEngine()

    def test_create_workflow(self, sabr):
        wf = sabr.create_workflow(
            "agent-1",
            "Build website",
            [
                "Design layout",
                "Write HTML",
                "Add CSS",
                "Test",
            ],
        )
        assert len(wf.steps) == 4
        assert wf.state == SabrTaskState.PENDING

    def test_step_execution_flow(self, sabr):
        wf = sabr.create_workflow("agent-1", "Task", ["Step 1", "Step 2"])

        step = sabr.start_step(wf.id)
        assert step.description == "Step 1"
        assert step.state == SabrTaskState.RUNNING

        sabr.complete_step(wf.id, result="Done step 1")
        assert wf.progress == 0.5
        assert wf.current_step == 1

        sabr.start_step(wf.id)
        sabr.complete_step(wf.id, result="Done step 2")
        assert wf.state == SabrTaskState.COMPLETED
        assert wf.progress == 1.0

    def test_pause_and_resume(self, sabr):
        wf = sabr.create_workflow("agent-1", "Task", ["Step 1", "Step 2"])
        sabr.start_step(wf.id)

        result = sabr.pause(wf.id)
        assert result is True
        assert wf.state == SabrTaskState.PAUSED

        resumed = sabr.resume(wf.id)
        assert resumed is not None
        assert resumed.state == SabrTaskState.RUNNING

    def test_cancel_workflow(self, sabr):
        wf = sabr.create_workflow("agent-1", "Task", ["Step 1"])
        sabr.start_step(wf.id)
        result = sabr.cancel(wf.id)
        assert result is True
        assert wf.state == SabrTaskState.CANCELLED

    def test_step_failure(self, sabr):
        wf = sabr.create_workflow("agent-1", "Task", ["Step 1", "Step 2"])
        sabr.start_step(wf.id)
        sabr.complete_step(wf.id, error="Connection timeout")
        assert wf.steps[0].state == SabrTaskState.FAILED
        assert wf.current_step == 0  # Doesn't advance on failure

    def test_decompose_coding_task(self, sabr):
        steps = sabr.decompose_task("Implement the authentication module")
        assert len(steps) >= 3
        assert any("implement" in s.lower() or "core" in s.lower() for s in steps)

    def test_decompose_research_task(self, sabr):
        steps = sabr.decompose_task("Research the latest AI papers")
        assert len(steps) >= 3

    def test_decompose_writing_task(self, sabr):
        steps = sabr.decompose_task("Write a technical report")
        assert len(steps) >= 3

    def test_decompose_default(self, sabr):
        steps = sabr.decompose_task("do something")
        assert len(steps) == 3  # Default has 3 steps

    def test_get_active_workflows(self, sabr):
        wf1 = sabr.create_workflow("agent-1", "Task1", ["Step"])
        sabr.start_step(wf1.id)
        # Use a different agent_id to avoid timestamp collision in IDs
        sabr.create_workflow("agent-2", "Task2", ["Step"])

        active = sabr.get_active_workflows("agent-1")
        assert len(active) == 1  # Only wf1 is RUNNING

    def test_workflow_to_dict(self, sabr):
        wf = sabr.create_workflow("agent-1", "Task", ["Step 1"])
        d = wf.to_dict()
        assert "id" in d
        assert "state" in d
        assert "progress" in d
        assert "steps" in d

    def test_stats(self, sabr):
        wf = sabr.create_workflow("agent-1", "Task", ["Step"])
        sabr.start_step(wf.id)
        sabr.complete_step(wf.id)
        s = sabr.stats()
        assert s["total_workflows"] == 1
        assert s["completed"] == 1


class TestSabrEngineNegative:
    @pytest.fixture
    def sabr(self):
        return SabrEngine()

    def test_start_step_invalid_workflow(self, sabr):
        result = sabr.start_step("nonexistent-id")
        assert result is None

    def test_complete_step_invalid_workflow(self, sabr):
        result = sabr.complete_step("nonexistent-id")
        assert result is None

    def test_pause_not_running(self, sabr):
        wf = sabr.create_workflow("agent-1", "Task", ["Step"])
        result = sabr.pause(wf.id)  # PENDING, not RUNNING
        assert result is False

    def test_resume_not_paused(self, sabr):
        wf = sabr.create_workflow("agent-1", "Task", ["Step"])
        result = sabr.resume(wf.id)  # PENDING, not PAUSED
        assert result is None

    def test_cancel_already_completed(self, sabr):
        wf = sabr.create_workflow("agent-1", "Task", ["Step"])
        sabr.start_step(wf.id)
        sabr.complete_step(wf.id)
        result = sabr.cancel(wf.id)
        assert result is False


# ═══════════════════════════════════════════════════════════════════════════════
# SHUKR SYSTEM — Positive Reinforcement
# ═══════════════════════════════════════════════════════════════════════════════


class TestShukrSystemPositive:
    @pytest.fixture
    def shukr(self):
        return ShukrSystem()

    def test_record_success(self, shukr):
        shukr.record_success("agent-1", "coding", "python_debugging", 1500)
        shukr.record_success("agent-1", "coding", "python_debugging", 1200)
        shukr.record_success("agent-1", "coding", "python_debugging", 1000)

        strengths = shukr.get_strengths("agent-1")
        assert len(strengths) == 1
        assert strengths[0]["success_count"] == 3
        assert strengths[0]["success_rate"] == 1.0

    def test_record_failure_decreases_rate(self, shukr):
        for _ in range(3):
            shukr.record_success("agent-1", "coding", "tests", 500)
        shukr.record_failure("agent-1", "coding", "tests")

        strengths = shukr.get_strengths("agent-1")
        assert strengths[0]["success_rate"] == 0.75

    def test_confidence_boost(self, shukr):
        for _ in range(10):
            shukr.record_success("agent-1", "coding", "debugging", 1000)

        boost = shukr.get_confidence_boost("agent-1", "coding")
        assert boost > 0

    def test_gratitude_milestones(self, shukr):
        for _i in range(10):
            shukr.record_success("agent-1", "coding", "refactoring", 1000)

        milestones = shukr.get_gratitude_milestones("agent-1")
        assert len(milestones) == 1  # Milestone at 10

    def test_get_best_agent_for(self, shukr):
        for _ in range(5):
            shukr.record_success("agent-a", "research", "analysis", 2000)
        for _ in range(5):
            shukr.record_success("agent-b", "research", "analysis", 2000)
            shukr.record_failure("agent-b", "research", "analysis")

        best = shukr.get_best_agent_for(["agent-a", "agent-b"], "research")
        assert best == "agent-a"

    def test_stats_per_agent(self, shukr):
        shukr.record_success("agent-1", "coding", "debugging", 1000)
        shukr.record_success("agent-1", "coding", "testing", 500)
        stats = shukr.stats("agent-1")
        assert stats["total_patterns"] == 2
        assert stats["total_successes"] == 2

    def test_stats_global(self, shukr):
        shukr.record_success("agent-1", "coding", "x", 100)
        stats = shukr.stats()
        assert stats["agents_tracked"] == 1


class TestShukrSystemNegative:
    @pytest.fixture
    def shukr(self):
        return ShukrSystem()

    def test_strengths_below_threshold(self, shukr):
        shukr.record_success("agent-1", "coding", "new_skill", 100)
        strengths = shukr.get_strengths("agent-1", min_success=3)
        assert len(strengths) == 0

    def test_no_best_agent(self, shukr):
        best = shukr.get_best_agent_for(["a", "b"], "nonexistent_category")
        assert best is None

    def test_empty_strengths(self, shukr):
        strengths = shukr.get_strengths("nonexistent-agent")
        assert strengths == []

    def test_confidence_boost_no_data(self, shukr):
        boost = shukr.get_confidence_boost("nonexistent", "coding")
        assert boost == 0.0
