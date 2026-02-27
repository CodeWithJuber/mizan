"""
Tests for the QCA Engine (7-Layer Cognitive Pipeline)
"""

# QCA engine uses backend.qca imports
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.qca.engine import (
    AqlLayer,
    DualInputProcessor,
    FurqanBayan,
    LawhMemory,
    MizanLayer,
    QCAEngine,
)


class TestDualInputProcessor:
    """Test Sam' + Basar + Fu'ad processing."""

    @pytest.fixture
    def processor(self):
        return DualInputProcessor()

    def test_sam_sequential(self, processor):
        """Sam' should produce sequential token stream."""
        result = processor.process_sam("The knowledge of truth")
        assert "tokens" in result
        assert len(result["tokens"]) == 4
        assert len(result["sequential_pairs"]) == 3

    def test_basar_structural(self, processor):
        """Basar should produce structural analysis."""
        result = processor.process_basar("The quick brown fox jumps over the lazy dog")
        assert "word_frequencies" in result
        assert "vocabulary_richness" in result
        assert result["vocabulary_richness"] > 0

    def test_fuad_integration(self, processor):
        """Fu'ad should integrate Sam' and Basar into unified understanding."""
        result = processor.process("Knowledge is power. Knowledge brings wisdom.")
        assert "fuad" in result
        assert "zahir" in result["fuad"]
        assert "batin" in result["fuad"]
        assert "key_terms" in result["fuad"]


class TestMizanLayer:
    """Test epistemic weighting."""

    @pytest.fixture
    def mizan(self):
        return MizanLayer()

    def test_certainty_levels(self, mizan):
        """Yaqin should weigh higher than Wahm."""
        yaqin = mizan.weigh("yaqin", "quran")
        wahm = mizan.weigh("wahm", "unknown")
        assert yaqin > wahm

    def test_tughyan_detection(self, mizan):
        """Should detect epistemic transgression."""
        is_tughyan, msg = mizan.check_tughyan("yaqin", "wahm")
        assert is_tughyan is True
        assert "TUGHYAN" in msg

    def test_no_tughyan_when_proportionate(self, mizan):
        """Should pass when claim matches evidence."""
        is_tughyan, _ = mizan.check_tughyan("zann", "zann")
        assert is_tughyan is False

    def test_confidence_classification(self, mizan):
        """Float scores should map to correct epistemic levels."""
        assert mizan.classify_confidence(0.95) == "yaqin"
        assert mizan.classify_confidence(0.70) == "zann_rajih"
        assert mizan.classify_confidence(0.50) == "zann"
        assert mizan.classify_confidence(0.25) == "shakk"
        assert mizan.classify_confidence(0.02) == "wahm"


class TestAqlLayer:
    """Test typed relationship binding."""

    @pytest.fixture
    def aql(self):
        return AqlLayer()

    def test_has_bindings(self, aql):
        """Should have pre-seeded Quranic bindings."""
        total, _ = aql.get_all_bindings_summary()
        assert total > 20

    def test_query_concept(self, aql):
        """Should retrieve bindings for known concepts."""
        results = aql.query("Mizan")
        assert len(results) > 0

    def test_tadabbur_trace(self, aql):
        """Should trace causal chains."""
        chain = aql.tadabbur_trace("Teaching", depth=3)
        assert len(chain) >= 1  # At least the start node


class TestLawhMemory:
    """Test 4-tier hierarchical memory."""

    @pytest.fixture
    def lawh(self):
        return LawhMemory()

    def test_tier1_immutable(self, lawh):
        """Tier 1 axioms should not be overwritable."""
        result = lawh.store("TRIADIC_INPUT", "override attempt", 1.0, tier=1)
        assert result is False  # Cannot overwrite

    def test_tier_auto_assignment(self, lawh):
        """Knowledge should be auto-assigned to correct tier by certainty."""
        lawh.store("HIGH_CERT", "verified fact", 0.95)
        lawh.store("LOW_CERT", "maybe true", 0.2)

        high = lawh.retrieve("HIGH_CERT")
        low = lawh.retrieve("LOW_CERT")

        assert high["tier"] == 2  # Kitab
        assert low["tier"] == 4  # Wahm

    def test_search(self, lawh):
        """Should find knowledge by keyword search."""
        lawh.store("TEST_KEY", "quantum computing is interesting", 0.7)
        results = lawh.search("quantum computing", tiers=[2, 3])
        assert len(results) > 0

    def test_consolidation(self, lawh):
        """Should prune old Tier 4 entries."""
        lawh.store("OLD_ENTRY", "old data", 0.1, tier=4)
        # Manually age the entry
        lawh.tiers[4]["OLD_ENTRY"]["timestamp"] = 0  # Very old
        result = lawh.consolidate(max_age_hours=1)
        assert result["pruned"] >= 1

    def test_stats(self, lawh):
        """Should report entry counts per tier."""
        stats = lawh.stats()
        assert 1 in stats
        assert stats[1] > 0  # Tier 1 has axioms


class TestFurqanBayan:
    """Test output discrimination and articulation."""

    @pytest.fixture
    def furqan(self):
        return FurqanBayan()

    def test_low_confidence_gets_prefix(self, furqan):
        """Low-confidence claims should get epistemic prefix."""
        result = furqan.validate_and_express("maybe true", 0.3)
        assert "CONJECTURE" in result["bayan_prefix"]

    def test_high_confidence_verified(self, furqan):
        """High-confidence claims should be marked as verified."""
        result = furqan.validate_and_express("definitely true", 0.95)
        assert "Verified" in result["bayan_prefix"]


class TestQCAEngine:
    """Test the unified 7-layer pipeline."""

    @pytest.fixture
    def engine(self):
        return QCAEngine()

    def test_process_input(self, engine):
        """Should process text through all input layers."""
        result = engine.process_input("Knowledge and wisdom are essential for justice.")
        assert "perception" in result
        assert "roots_identified" in result
        assert "key_terms" in result

    def test_reason(self, engine):
        """Should produce a reasoned answer."""
        result = engine.reason(
            "What is knowledge?",
            context_text="Knowledge is understanding gained through experience and education.",
        )
        assert "question" in result
        assert "confidence" in result
        assert result["confidence"] > 0

    def test_weigh_claim(self, engine):
        """Should weigh claims through Mizan."""
        result = engine.weigh_claim("The earth is round", "yaqin", "quran")
        assert result["passed"] is True

    def test_remember_and_recall(self, engine):
        """Should store and retrieve from Lawh memory."""
        engine.remember("test_fact", "MIZAN is an AGI system", 0.9)
        results = engine.recall("MIZAN AGI")
        assert len(results) > 0
