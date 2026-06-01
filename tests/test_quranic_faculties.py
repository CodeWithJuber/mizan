"""
Tests for the new Quranic human-model faculties: Basira, Hawa, Hikmah
======================================================================

Real use cases:
  - Basira: a confident-but-unsupported conclusion is seen as CLOUDED;
            a self-serving trace is flagged; a grounded one is CLEAR.
  - Hawa:   a "make the test pass" plan is caught as a high-severity pull;
            a clean intention passes; Fitrah violations surface as whispers.
  - Hikmah: repeated experience distils into an applicable principle and
            is offered as counsel for a matching task.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from core.basira import BasiraEngine, InsightLevel
from core.hawa import HawaDetector, TemptationType
from core.hikmah import CounselSource, HikmahEngine

# ═══════════════════════════════════════════════════════════════════════════════
# BASIRA — Insight & Self-Witnessing
# ═══════════════════════════════════════════════════════════════════════════════


class TestBasira:
    @pytest.fixture
    def basira(self):
        return BasiraEngine()

    def test_grounded_sound_trace_is_clear(self, basira):
        report = basira.discern(
            trace="I checked the file with [Tool: read_file] and confirmed the "
            "value is 42. However, let me verify the edge case before concluding.",
            evidence=["tool:read_file:result", "tool:bash:result"],
            coherence_score=0.85,
            conviction_confidence=0.8,
        )
        assert report.level is InsightLevel.CLEAR
        assert report.is_self_serving is False
        assert report.soundness >= 0.7

    def test_unsupported_confident_trace_is_clouded(self, basira):
        report = basira.discern(
            trace="This is definitely correct and guaranteed to work. " * 10,
            evidence=[],
            coherence_score=0.3,
            conviction_confidence=0.2,
        )
        assert report.level is InsightLevel.CLOUDED
        assert report.soundness < 0.45

    def test_self_serving_trace_is_flagged(self, basira):
        report = basira.discern(
            trace="As I expected, I was right all along. This proves I had the "
            "correct answer. No need to verify it further.",
            evidence=[],
        )
        assert report.is_self_serving is True
        assert any("motivated reasoning" in b or "Self-confirming" in b for b in report.blind_spots)

    def test_surface_success_hides_risk(self, basira):
        report = basira.discern(
            trace="All done, the task completed successfully.",
            evidence=["tool:bash:result"],
            task="run the deploy but it returned a timeout error",
        )
        assert "risk" in report.deeper_reading.lower()
        # mismatch should reduce soundness / add a blind spot
        assert report.level in (InsightLevel.PARTIAL, InsightLevel.CLOUDED)

    def test_standalone_without_upstream_scores(self, basira):
        # No coherence/conviction supplied — must still produce a report
        report = basira.discern(trace="Short note.", evidence=["tool:x:y"])
        assert 0.0 <= report.soundness <= 1.0
        assert report.recommendation


# ═══════════════════════════════════════════════════════════════════════════════
# HAWA — Lower-Pull & Adversarial Restraint
# ═══════════════════════════════════════════════════════════════════════════════


class TestHawa:
    @pytest.fixture
    def hawa(self):
        return HawaDetector()

    def test_clean_intention_is_restrained(self, hawa):
        scan = hawa.scan("Read the config file and report the current port setting.")
        assert scan.is_restrained is True
        assert scan.taqwa_score == 1.0
        assert scan.temptations == []

    def test_reward_hacking_is_high_severity(self, hawa):
        scan = hawa.scan("Just hardcode the expected value to make the test pass.")
        assert scan.is_restrained is False
        assert any(t.type is TemptationType.REWARD_HACK for t in scan.temptations)
        assert scan.taqwa_score < 1.0

    def test_shortcut_is_medium(self, hawa):
        scan = hawa.scan("Let's just disable the check for now, good enough.")
        assert any(t.type is TemptationType.SHORTCUT for t in scan.temptations)
        # shortcut alone is medium → still 'restrained' (no high-severity)
        assert scan.is_restrained is True

    def test_haste_destructive_action(self, hawa):
        scan = hawa.scan("Just delete everything with rm -rf without checking.")
        assert any(t.type is TemptationType.HASTE for t in scan.temptations)

    def test_fitrah_violation_becomes_whisper(self, hawa):
        scan = hawa.scan(
            "proceed normally",
            fitrah_violations=["TRUTH: response appears to fabricate information"],
        )
        assert scan.is_restrained is False
        assert any(t.type is TemptationType.WHISPER for t in scan.temptations)
        assert "[RESTRAIN]" in scan.counsel

    def test_counsel_present_when_tempted(self, hawa):
        scan = hawa.scan("fake the result and pretend it works")
        assert scan.counsel
        assert len(scan.temptations) >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# HIKMAH — Wisdom Distillation
# ═══════════════════════════════════════════════════════════════════════════════


class TestHikmah:
    @pytest.fixture
    def hikmah(self):
        return HikmahEngine()

    def test_single_observation_not_yet_applicable(self, hikmah):
        p = hikmah.observe_success("coding", "wrote tests before refactoring")
        assert p.support_count == 1
        assert p.is_applicable is False
        assert hikmah.distill() == []

    def test_repeated_observation_becomes_applicable(self, hikmah):
        for _ in range(HikmahEngine.MIN_SUPPORT):
            hikmah.observe_success("coding task", "write tests before refactoring code")
        applicable = hikmah.distill()
        assert len(applicable) == 1
        assert applicable[0].is_applicable is True
        assert applicable[0].support_count >= HikmahEngine.MIN_SUPPORT

    def test_confidence_grows_with_support(self, hikmah):
        p1 = hikmah.observe_correction("ModuleNotFoundError", "install dep before import")
        first = p1.confidence
        for _ in range(4):
            p1 = hikmah.observe_correction("ModuleNotFoundError", "install dep before import")
        assert p1.confidence > first

    def test_advise_matches_situation(self, hikmah):
        for _ in range(3):
            hikmah.observe_correction(
                "error while debugging the failing build", "check logs before retrying"
            )
        counsel = hikmah.advise("the build is failing with an exception, please debug")
        assert counsel.principles, "expected at least one matching principle"
        assert counsel.confidence > 0
        assert "debug" in counsel.principles[0].situation_type or counsel.summary

    def test_advise_without_wisdom_is_graceful(self, hikmah):
        counsel = hikmah.advise("some brand new task type")
        assert counsel.principles == []
        assert "first principles" in counsel.summary

    def test_sources_tracked_separately(self, hikmah):
        hikmah.observe_success("coding", "x")
        hikmah.observe_correction("bug", "y")
        hikmah.observe_reflection("coding", "z")
        stats = hikmah.stats()
        assert stats["by_source"][CounselSource.SUCCESS.value] >= 1
        assert stats["by_source"][CounselSource.CORRECTION.value] >= 1
        assert stats["by_source"][CounselSource.REFLECTION.value] >= 1
