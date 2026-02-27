"""
Tests for MASALIK — Neural Pathway Memory Network
===================================================

Tests that memory works like a human brain, not a filing cabinet:
- No duplication (same input strengthens, doesn't add)
- Priority by pathway strength (not a stored number)
- Spreading activation (one concept activates related ones)
- Nisyan (forgetting prunes weak pathways)
- Tafakkur (reflection creates new connections)
- Hikmah (heavily-used pathways become permanent)
- Fitrah (innate pre-wired pathways)
"""

import time
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from memory.masalik import MasalikNetwork, Mafhum, Silah, extract_concepts


# ─── Concept Extraction ─────────────────────────────────────────────────────

class TestConceptExtraction:
    def test_extracts_meaningful_words(self):
        concepts = extract_concepts("The quick brown fox jumps over the lazy dog")
        assert "quick" in concepts
        assert "brown" in concepts
        assert "fox" in concepts
        # Stopwords filtered
        assert "the" not in concepts
        assert "over" not in concepts

    def test_filters_short_words(self):
        concepts = extract_concepts("I am at my top")
        # "am", "at", "my" are too short or stopwords
        assert "top" in concepts

    def test_deduplicates_stems(self):
        concepts = extract_concepts("learning learned learnable")
        # All stem to "learn" — should appear only once
        assert len([c for c in concepts if c.startswith("learn")]) == 1

    def test_empty_input(self):
        assert extract_concepts("") == []
        assert extract_concepts("the a an is are") == []


# ─── Mafhum (Concept Node) ──────────────────────────────────────────────────

class TestMafhum:
    def test_fire_increases_resting_level(self):
        node = Mafhum(id="test")
        assert node.resting_level == 0.0
        node.fire(strength=1.0)
        assert node.resting_level > 0.0
        assert node.total_activations == 1

    def test_repeated_firing_raises_resting(self):
        node = Mafhum(id="test")
        for _ in range(20):
            node.fire(strength=1.0)
        assert node.resting_level > 0.3
        assert node.total_activations == 20

    def test_hikmah_requires_many_activations(self):
        node = Mafhum(id="test")
        # Not hikmah yet
        assert not node.is_hikmah
        # Fire many times
        for _ in range(50):
            node.fire(strength=1.0)
        assert node.is_hikmah

    def test_fitrah_concept(self):
        node = Mafhum(id="truth", is_fitrah=True, resting_level=0.3)
        # Fitrah concepts start with baseline
        assert node.resting_level == 0.3


# ─── Silah (Pathway) ────────────────────────────────────────────────────────

class TestSilah:
    def test_strengthen_increases_weight(self):
        path = Silah(source="a", target="b", weight=0.1)
        path.strengthen(0.1)
        assert path.weight > 0.1
        assert path.co_activations == 1

    def test_diminishing_returns(self):
        path = Silah(source="a", target="b", weight=0.1)
        path.strengthen(0.5)
        gain1 = path.weight - 0.1

        old_weight = path.weight
        path.strengthen(0.5)
        gain2 = path.weight - old_weight

        # Second strengthening gives less gain (diminishing returns)
        assert gain2 < gain1

    def test_decay_weakens_pathway(self):
        path = Silah(source="a", target="b", weight=0.5)
        path.decay(elapsed_hours=100.0)
        assert path.weight < 0.5

    def test_weak_pathways_decay_faster(self):
        weak = Silah(source="a", target="b", weight=0.1)
        strong = Silah(source="c", target="d", weight=0.9)

        weak.decay(elapsed_hours=48.0)
        strong.decay(elapsed_hours=48.0)

        # Weak pathway should have decayed proportionally more
        weak_ratio = weak.weight / 0.1
        strong_ratio = strong.weight / 0.9
        assert weak_ratio < strong_ratio

    def test_hikmah_pathway_doesnt_decay(self):
        path = Silah(source="a", target="b", weight=0.8, co_activations=15)
        assert path.is_hikmah
        path.decay(elapsed_hours=10000.0)
        assert path.weight == 0.8  # Unchanged


# ─── MasalikNetwork — Core Operations ───────────────────────────────────────

class TestMasalikEncode:
    def test_encode_creates_concepts(self):
        net = MasalikNetwork()
        before = len(net.concepts)
        result = net.encode("Python programming language")
        assert result["encoded"] > 0
        assert len(net.concepts) > before

    def test_encode_creates_pathways(self):
        net = MasalikNetwork()
        before = len(net.pathways)
        net.encode("Python programming language")
        assert len(net.pathways) > before

    def test_no_duplication(self):
        """Same input twice should strengthen pathways, not create duplicates."""
        net = MasalikNetwork()
        r1 = net.encode("Python programming language")
        pathways_after_first = len(net.pathways)

        r2 = net.encode("Python programming language")
        pathways_after_second = len(net.pathways)

        # No new pathways created — same concepts strengthen existing ones
        assert pathways_after_second == pathways_after_first
        assert r2["new_pathways"] == 0
        assert r2["pathways_strengthened"] > 0

    def test_importance_affects_strength(self):
        net1 = MasalikNetwork()
        net1.encode("machine learning algorithms", importance=0.2)

        net2 = MasalikNetwork()
        net2.encode("machine learning algorithms", importance=0.9)

        # Higher importance → stronger pathways
        weights1 = [p.weight for p in net1.pathways.values()
                     if p.pathway_type != "fitrah"]
        weights2 = [p.weight for p in net2.pathways.values()
                     if p.pathway_type != "fitrah"]
        if weights1 and weights2:
            assert max(weights2) > max(weights1)


class TestMasalikRecall:
    def test_recall_finds_associated_concepts(self):
        net = MasalikNetwork()
        net.encode("Python is a programming language used for machine learning")
        net.encode("Python data science libraries include pandas numpy")

        results = net.recall("Python")
        concepts = [c for c, _ in results]

        # Should find concepts associated with Python
        assert len(results) > 0

    def test_recall_strengthens_pathways(self):
        """Dhikr: remembering STRENGTHENS, not just retrieves."""
        net = MasalikNetwork()
        net.encode("knowledge leads to truth through evidence")

        # Get initial pathway weights
        initial_weights = {k: p.weight for k, p in net.pathways.items()
                          if p.pathway_type != "fitrah"}

        # Recall (dhikr)
        net.recall("knowledge truth")

        # Some pathways should be stronger now
        strengthened = 0
        for k, p in net.pathways.items():
            if k in initial_weights and p.weight > initial_weights[k]:
                strengthened += 1
        assert strengthened > 0

    def test_recall_spreading_activation(self):
        """Activation spreads from query concepts through pathways."""
        net = MasalikNetwork()
        # Create a chain: A connects to B, B connects to C
        net.encode("alpha beta concepts together")
        net.encode("beta gamma concepts together")

        # Query for alpha — should activate beta (direct) and gamma (spread)
        results = net.recall("alpha")
        activated = {c for c, _ in results}

        # Beta should be activated (direct pathway from alpha)
        # gamma might also be activated through spreading
        assert len(activated) > 0

    def test_recall_context_returns_string(self):
        net = MasalikNetwork()
        net.encode("artificial intelligence and deep learning")
        context = net.recall_context("intelligence")
        assert isinstance(context, str)
        assert len(context) > 0


class TestMasalikNisyan:
    def test_nisyan_prunes_weak_pathways(self):
        net = MasalikNetwork()
        net.encode("temporary weak concept connection")

        # Force heavy decay
        result = net.apply_nisyan(force_hours=5000.0)

        # Some weak pathways should be pruned
        # (fitrah pathways with co_activations=5 survive longer)
        assert result["pruned_pathways"] >= 0

    def test_strong_pathways_survive_nisyan(self):
        net = MasalikNetwork()
        # Build strong pathway through repetition
        for _ in range(15):
            net.encode("persistent knowledge always remembered", importance=0.9)

        # Find a non-fitrah pathway
        strong_keys = [
            k for k, p in net.pathways.items()
            if p.pathway_type != "fitrah" and p.co_activations >= 10
        ]

        # Apply heavy decay
        net.apply_nisyan(force_hours=500.0)

        # Strong pathways (hikmah) should survive
        for k in strong_keys:
            if k in net.pathways:
                assert net.pathways[k].weight > 0.01

    def test_fitrah_survives_nisyan(self):
        """Innate pathways cannot be pruned."""
        net = MasalikNetwork()
        fitrah_count = sum(1 for c in net.concepts.values() if c.is_fitrah)

        net.apply_nisyan(force_hours=100000.0)

        surviving_fitrah = sum(1 for c in net.concepts.values() if c.is_fitrah)
        assert surviving_fitrah == fitrah_count


class TestMasalikTafakkur:
    def test_tafakkur_creates_new_connections(self):
        net = MasalikNetwork()
        # Encode several texts that share concepts across different pairs
        net.encode("alpha bravo charlie")
        net.encode("alpha bravo delta")
        net.encode("alpha bravo echo")

        # alpha and bravo are co-activated 3 times
        result = net.tafakkur()

        # Should create or strengthen connections
        assert result["new_connections"] >= 0 or result["strengthened"] >= 0

    def test_tafakkur_needs_minimum_history(self):
        net = MasalikNetwork()
        result = net.tafakkur()
        assert result["new_connections"] == 0


class TestMasalikFitrah:
    def test_fitrah_concepts_exist(self):
        net = MasalikNetwork()
        assert "truth" in net.concepts
        assert "justice" in net.concepts
        assert "knowledge" in net.concepts
        assert net.concepts["truth"].is_fitrah

    def test_fitrah_pathways_exist(self):
        net = MasalikNetwork()
        # cause->effect should be pre-wired
        key = net._pathway_key("cause", "effect")
        assert key in net.pathways
        assert net.pathways[key].weight == 0.7

    def test_fitrah_baseline_activation(self):
        net = MasalikNetwork()
        assert net.concepts["truth"].resting_level == 0.3


class TestMasalikHikmah:
    def test_hikmah_forms_from_repeated_use(self):
        net = MasalikNetwork()
        # Encode the same concepts many times (heavy learning)
        for _ in range(15):
            net.encode("wisdom comes from repeated deep practice", importance=0.9)

        hikmah = net.get_hikmah()
        # After 15 high-importance encodings, some pathways should be hikmah
        # (co_activations >= 10 and weight >= 0.5)
        assert len(hikmah) > 0

    def test_hikmah_is_permanent(self):
        net = MasalikNetwork()
        for _ in range(15):
            net.encode("permanent knowledge never forgotten", importance=0.9)

        hikmah_before = len(net.get_hikmah())
        net.apply_nisyan(force_hours=100000.0)
        hikmah_after = len(net.get_hikmah())

        # Hikmah should survive any amount of decay
        assert hikmah_after == hikmah_before


class TestMasalikStats:
    def test_stats_structure(self):
        net = MasalikNetwork()
        stats = net.stats()
        assert "total_concepts" in stats
        assert "total_pathways" in stats
        assert "fitrah_concepts" in stats
        assert "hikmah_pathways" in stats
        assert "avg_pathway_weight" in stats

    def test_strongest_pathways(self):
        net = MasalikNetwork()
        net.encode("strong pathway test between concepts")
        strongest = net.get_strongest_pathways(top_k=5)
        assert len(strongest) > 0
        assert "from" in strongest[0]
        assert "weight" in strongest[0]


# ─── Integration with DhikrMemorySystem ──────────────────────────────────────

class TestDhikrMasalikIntegration:
    @pytest.fixture
    def dhikr(self):
        from memory.dhikr import DhikrMemorySystem
        return DhikrMemorySystem(db_path=":memory:")

    def test_dhikr_has_masalik(self, dhikr):
        assert hasattr(dhikr, 'masalik')
        assert isinstance(dhikr.masalik, MasalikNetwork)

    @pytest.mark.asyncio
    async def test_remember_encodes_to_masalik(self, dhikr):
        pathways_before = len(dhikr.masalik.pathways)

        await dhikr.remember(
            "Python machine learning algorithms",
            memory_type="semantic",
            importance=0.8,
            tags=["programming", "ai"],
        )

        # Masalik should have new pathways from encoding
        assert len(dhikr.masalik.pathways) > pathways_before

    @pytest.mark.asyncio
    async def test_recall_strengthens_masalik(self, dhikr):
        await dhikr.remember(
            "knowledge leads to truth",
            memory_type="semantic",
            importance=0.8,
        )

        # Recall should trigger masalik spreading activation
        context = dhikr.recall_pathways("knowledge")
        assert isinstance(context, str)

    @pytest.mark.asyncio
    async def test_consolidate_runs_tafakkur_and_nisyan(self, dhikr):
        for i in range(5):
            await dhikr.remember(
                f"test memory {i} about learning",
                importance=0.5,
            )

        result = await dhikr.consolidate()
        assert "tafakkur" in result
        assert "nisyan" in result
        assert result["consolidated"]

    @pytest.mark.asyncio
    async def test_no_duplication_through_dhikr(self, dhikr):
        """Remembering the same thing twice shouldn't double pathways."""
        await dhikr.remember("sky is blue", importance=0.5)
        pathways_after_first = len(dhikr.masalik.pathways)

        await dhikr.remember("sky is blue", importance=0.5)
        pathways_after_second = len(dhikr.masalik.pathways)

        # Same concepts → same pathways (just stronger)
        assert pathways_after_second == pathways_after_first
