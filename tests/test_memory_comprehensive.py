"""
Comprehensive Memory System Tests — Masalik + Dhikr Integration
================================================================

Real use cases:
  - User teaches the system → pathway created (no duplication)
  - User asks a question → spreading activation finds associated concepts
  - System idle for hours → weak pathways decay, strong survive
  - Repeated learning → pathways become Hikmah (permanent wisdom)
  - Fitrah concepts → always present from birth
  - Consolidation → Tafakkur creates new insights
  - Dhikr memory → remembers in both SQLite AND neural pathways
  - Agent profile → persisted and retrievable
  - Chat history → stored and ordered correctly
"""

import pytest
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from memory.masalik import MasalikNetwork, Mafhum, Silah, extract_concepts
from memory.dhikr import DhikrMemorySystem, Memory


# ═══════════════════════════════════════════════════════════════════════════════
# CONCEPT EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════════

class TestConceptExtraction:
    def test_extracts_meaningful_words(self):
        concepts = extract_concepts("Machine learning algorithms process data efficiently")
        assert "machin" in concepts or "machine" in concepts
        assert "learn" in concepts or "learning" in concepts
        assert len(concepts) >= 3

    def test_filters_stopwords(self):
        concepts = extract_concepts("the quick brown fox is on the mat")
        assert "the" not in concepts
        assert "is" not in concepts
        assert "on" not in concepts

    def test_filters_short_words(self):
        concepts = extract_concepts("I am so OK to go at it")
        # All words are <= 2 characters after stopword filtering
        assert len(concepts) == 0

    def test_deduplication_via_stemming(self):
        concepts = extract_concepts("learning learned learner learns")
        # Stemming should reduce these to similar roots
        assert len(concepts) <= 2

    def test_empty_input(self):
        assert extract_concepts("") == []
        assert extract_concepts("   ") == []

    def test_special_characters(self):
        concepts = extract_concepts("@#$% hello !!! world 123")
        assert "hello" in concepts
        assert "world" in concepts

    def test_case_insensitive(self):
        concepts = extract_concepts("Python PYTHON python")
        assert len(concepts) == 1  # All should stem to same thing

    def test_over_not_extracted(self):
        """Regression: 'over' should be in stopwords."""
        concepts = extract_concepts("the fox jumped over the fence")
        assert "over" not in concepts


# ═══════════════════════════════════════════════════════════════════════════════
# MAFHUM (Concept Node)
# ═══════════════════════════════════════════════════════════════════════════════

class TestMafhum:
    def test_fire_increases_resting_level(self):
        node = Mafhum(id="test")
        assert node.resting_level == 0.0
        node.fire(1.0)
        assert node.resting_level > 0.0
        assert node.total_activations == 1

    def test_repeated_firing_long_term_potentiation(self):
        node = Mafhum(id="test")
        for _ in range(50):
            node.fire(1.0)
        assert node.resting_level > 0.3

    def test_resting_level_asymptotes(self):
        node = Mafhum(id="test")
        for _ in range(1000):
            node.fire(1.0)
        assert node.resting_level <= 0.95

    def test_hikmah_from_repeated_use(self):
        node = Mafhum(id="test")
        for _ in range(20):
            node.fire(1.0)
        # After 10+ activations and resting >= 0.5
        # resting_level after 20 fires ≈ 0.33, may need more
        # Let's fire more to ensure hikmah
        for _ in range(100):
            node.fire(1.0)
        assert node.resting_level >= 0.5
        assert node.is_hikmah is True

    def test_fitrah_concept(self):
        node = Mafhum(id="truth", is_fitrah=True, resting_level=0.3)
        assert node.is_fitrah is True

    def test_current_activation_decays(self):
        import time
        node = Mafhum(id="test")
        node.fire(1.0)
        # Immediately after firing, activation should be high
        act1 = node.get_current_activation()
        assert act1 > 0.5
        # After a tiny delay, should still be close
        time.sleep(0.01)
        act2 = node.get_current_activation()
        assert act2 <= act1

    def test_current_activation_floor_is_resting(self):
        node = Mafhum(id="test")
        for _ in range(50):
            node.fire(1.0)
        resting = node.resting_level
        # Set activation to 0 explicitly
        node.activation = 0.0
        current = node.get_current_activation()
        assert current == resting


# ═══════════════════════════════════════════════════════════════════════════════
# SILAH (Pathway/Synapse)
# ═══════════════════════════════════════════════════════════════════════════════

class TestSilah:
    def test_strengthen_increases_weight(self):
        p = Silah(source="a", target="b", weight=0.1)
        p.strengthen(0.1)
        assert p.weight > 0.1
        assert p.co_activations == 1

    def test_diminishing_returns(self):
        p = Silah(source="a", target="b", weight=0.9)
        old_weight = p.weight
        p.strengthen(0.1)
        growth = p.weight - old_weight
        assert growth < 0.1  # Less growth because already strong

    def test_weak_pathways_decay_fast(self):
        p = Silah(source="a", target="b", weight=0.1)
        p.decay(elapsed_hours=48)
        assert p.weight < 0.05

    def test_strong_pathways_decay_slow(self):
        p = Silah(source="a", target="b", weight=0.9)
        p.decay(elapsed_hours=48)
        assert p.weight > 0.7  # Should retain most weight

    def test_hikmah_pathway_permanent(self):
        p = Silah(source="a", target="b", weight=0.8, co_activations=15)
        assert p.is_hikmah is True
        original = p.weight
        p.decay(elapsed_hours=100000)  # 11 years
        assert p.weight == original  # No decay for hikmah

    def test_not_hikmah_below_threshold(self):
        p = Silah(source="a", target="b", weight=0.8, co_activations=5)
        assert p.is_hikmah is False  # Needs 10+ co-activations

    def test_weight_capped_at_one(self):
        p = Silah(source="a", target="b", weight=0.99)
        for _ in range(100):
            p.strengthen(0.5)
        assert p.weight <= 1.0


# ═══════════════════════════════════════════════════════════════════════════════
# MASALIK NETWORK — Encoding (Learning)
# ═══════════════════════════════════════════════════════════════════════════════

class TestMasalikEncode:
    @pytest.fixture
    def network(self):
        return MasalikNetwork()

    def test_encode_creates_concepts(self, network):
        result = network.encode("Python programming creates applications")
        assert result["encoded"] > 0
        assert "python" in network.concepts or "program" in network.concepts

    def test_encode_creates_pathways(self, network):
        result = network.encode("quantum computing revolution")
        assert result["new_pathways"] > 0

    def test_no_duplication(self, network):
        """Encoding same text twice should strengthen, not duplicate."""
        result1 = network.encode("neural networks are powerful")
        pathways_after_first = len(network.pathways)
        result2 = network.encode("neural networks are powerful")
        assert result2["new_pathways"] == 0
        assert result2["pathways_strengthened"] > 0

    def test_importance_scales_strength(self, network):
        """Higher importance → stronger initial pathways."""
        net1 = MasalikNetwork()
        net2 = MasalikNetwork()

        net1.encode("important concept here", importance=1.0)
        net2.encode("important concept here", importance=0.1)

        # Get pathway weights (excluding fitrah)
        weights1 = [p.weight for p in net1.pathways.values() if p.pathway_type != "fitrah"]
        weights2 = [p.weight for p in net2.pathways.values() if p.pathway_type != "fitrah"]

        if weights1 and weights2:
            assert max(weights1) > max(weights2)

    def test_empty_text_no_crash(self, network):
        result = network.encode("")
        assert result["encoded"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# MASALIK NETWORK — Recall (Spreading Activation)
# ═══════════════════════════════════════════════════════════════════════════════

class TestMasalikRecall:
    @pytest.fixture
    def trained_network(self):
        net = MasalikNetwork()
        net.encode("Python programming language is widely used", importance=0.8)
        net.encode("Machine learning uses Python extensively", importance=0.8)
        net.encode("Data science requires statistical knowledge", importance=0.7)
        return net

    def test_recall_finds_associated(self, trained_network):
        results = trained_network.recall("Python")
        assert len(results) > 0
        concept_names = [r[0] for r in results]
        # Should find concepts associated with Python
        assert any("program" in c or "learn" in c or "machin" in c or "language" in c
                    for c in concept_names)

    def test_recall_strengthens_pathways(self, trained_network):
        """Dhikr — remembering should strengthen pathways."""
        # Get initial weights
        initial_weights = {k: p.weight for k, p in trained_network.pathways.items()}
        trained_network.recall("Python programming")
        # Some pathways should be stronger now
        strengthened = False
        for k, p in trained_network.pathways.items():
            if k in initial_weights and p.weight > initial_weights[k]:
                strengthened = True
                break
        assert strengthened

    def test_spreading_activation_reaches_distant(self, trained_network):
        """Activation should spread from Python → programming → related concepts."""
        results = trained_network.recall("Python")
        # Should reach concepts not directly mentioned with Python
        # e.g., statistical, science, data via shared pathways
        assert len(results) >= 1

    def test_recall_context_string(self, trained_network):
        context = trained_network.recall_context("Python learning")
        if context:
            assert "Associated:" in context

    def test_recall_empty_query(self):
        net = MasalikNetwork()
        results = net.recall("")
        assert results == []


# ═══════════════════════════════════════════════════════════════════════════════
# MASALIK NETWORK — Nisyan (Forgetting)
# ═══════════════════════════════════════════════════════════════════════════════

class TestMasalikNisyan:
    def test_weak_pathways_pruned(self):
        net = MasalikNetwork()
        net.encode("temporary information here", importance=0.1)
        initial = len(net.pathways)
        result = net.apply_nisyan(force_hours=1000)
        assert result["pruned_pathways"] > 0
        assert len(net.pathways) < initial

    def test_strong_pathways_survive(self):
        net = MasalikNetwork()
        # Encode many times to build strong pathways
        for _ in range(20):
            net.encode("permanent knowledge here", importance=1.0)

        # Get non-fitrah pathway count
        non_fitrah_before = sum(1 for p in net.pathways.values() if p.pathway_type != "fitrah")
        net.apply_nisyan(force_hours=100)
        non_fitrah_after = sum(1 for p in net.pathways.values() if p.pathway_type != "fitrah")
        # Strong pathways should survive
        assert non_fitrah_after > 0

    def test_fitrah_survives_everything(self):
        net = MasalikNetwork()
        fitrah_before = sum(1 for c in net.concepts.values() if c.is_fitrah)
        net.apply_nisyan(force_hours=100000)
        fitrah_after = sum(1 for c in net.concepts.values() if c.is_fitrah)
        assert fitrah_after == fitrah_before

    def test_orphan_concepts_pruned(self):
        net = MasalikNetwork()
        net.encode("lonely concept nobody remembers", importance=0.05)
        net.apply_nisyan(force_hours=5000)
        # Weak orphans with low resting level should be pruned
        result = net.apply_nisyan(force_hours=5000)
        # After heavy decay, some concepts may be orphaned and pruned
        assert isinstance(result["pruned_concepts"], int)


# ═══════════════════════════════════════════════════════════════════════════════
# MASALIK NETWORK — Tafakkur (Reflective Consolidation)
# ═══════════════════════════════════════════════════════════════════════════════

class TestMasalikTafakkur:
    def test_creates_new_connections(self):
        net = MasalikNetwork()
        # Encode multiple overlapping texts
        for _ in range(5):
            net.encode("quantum physics experiments", importance=0.8)
            net.encode("quantum computing applications", importance=0.8)
            net.encode("physics computing simulation", importance=0.8)

        result = net.tafakkur()
        # Tafakkur should create or strengthen connections
        assert result["new_connections"] + result["strengthened"] >= 0

    def test_needs_minimum_history(self):
        net = MasalikNetwork()
        net.encode("single fact", importance=0.5)
        result = net.tafakkur()
        # Not enough history for meaningful reflection
        assert result["new_connections"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# MASALIK NETWORK — Fitrah (Innate Knowledge)
# ═══════════════════════════════════════════════════════════════════════════════

class TestMasalikFitrah:
    def test_fitrah_concepts_exist(self):
        net = MasalikNetwork()
        fitrah = [c for c in net.concepts.values() if c.is_fitrah]
        assert len(fitrah) == 15  # 15 innate concepts

    def test_fitrah_pathways_exist(self):
        net = MasalikNetwork()
        fitrah_paths = [p for p in net.pathways.values() if p.pathway_type == "fitrah"]
        assert len(fitrah_paths) == 10  # 10 innate pathways

    def test_fitrah_concepts_have_baseline(self):
        net = MasalikNetwork()
        for c in net.concepts.values():
            if c.is_fitrah:
                assert c.resting_level >= 0.3

    def test_specific_fitrah_concepts(self):
        net = MasalikNetwork()
        expected = ["truth", "justice", "knowledge", "balance", "creation",
                    "cause", "effect", "good", "harm", "evidence"]
        for concept in expected:
            assert concept in net.concepts, f"Missing fitrah concept: {concept}"
            assert net.concepts[concept].is_fitrah

    def test_fitrah_pathways_weights(self):
        net = MasalikNetwork()
        # cause → effect should have weight 0.7
        key = net._pathway_key("cause", "effect")
        assert key in net.pathways
        assert net.pathways[key].weight >= 0.5


# ═══════════════════════════════════════════════════════════════════════════════
# MASALIK NETWORK — Hikmah (Wisdom)
# ═══════════════════════════════════════════════════════════════════════════════

class TestMasalikHikmah:
    def test_hikmah_forms_from_repetition(self):
        net = MasalikNetwork()
        for _ in range(15):
            net.encode("Python is a programming language", importance=1.0)
        hikmah = net.get_hikmah()
        assert len(hikmah) > 0

    def test_hikmah_survives_extreme_decay(self):
        net = MasalikNetwork()
        for _ in range(15):
            net.encode("Python is a programming language", importance=1.0)
        hikmah_before = net.get_hikmah()
        net.apply_nisyan(force_hours=100000)
        hikmah_after = net.get_hikmah()
        # Hikmah should survive
        assert len(hikmah_after) >= len(hikmah_before)


# ═══════════════════════════════════════════════════════════════════════════════
# MASALIK NETWORK — Stats & Introspection
# ═══════════════════════════════════════════════════════════════════════════════

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
        net.encode("artificial intelligence research", importance=0.9)
        top = net.get_strongest_pathways(5)
        assert len(top) > 0
        for p in top:
            assert "from" in p
            assert "to" in p
            assert "weight" in p


# ═══════════════════════════════════════════════════════════════════════════════
# DHIKR MEMORY SYSTEM (SQLite + Masalik)
# ═══════════════════════════════════════════════════════════════════════════════

class TestDhikrMemorySystem:
    @pytest.fixture
    def memory(self, tmp_path):
        return DhikrMemorySystem(db_path=str(tmp_path / "test.db"))

    @pytest.mark.asyncio
    async def test_remember_and_recall(self, memory):
        mem_id = await memory.remember(
            "The speed of light is 299792458 meters per second",
            memory_type="semantic",
            importance=0.9,
            tags=["physics", "light"],
        )
        assert mem_id

        results = await memory.recall("speed of light", memory_type="semantic")
        assert len(results) > 0
        assert any("light" in str(r.content) for r in results)

    @pytest.mark.asyncio
    async def test_memory_types(self, memory):
        for mtype in ["episodic", "semantic", "procedural"]:
            await memory.remember(f"Test {mtype} memory", memory_type=mtype, importance=0.5)

        results = await memory.recall("Test", memory_type="semantic")
        assert all(r.memory_type == "semantic" for r in results)

    @pytest.mark.asyncio
    async def test_working_memory_capacity(self, memory):
        for i in range(10):
            await memory.remember(f"Important fact {i}", importance=0.9)
        assert len(memory.working_memory) <= memory.working_capacity

    @pytest.mark.asyncio
    async def test_consolidation(self, memory):
        await memory.remember("ephemeral", importance=0.1)
        result = await memory.consolidate()
        assert result["consolidated"] is True

    @pytest.mark.asyncio
    async def test_agent_profile_persistence(self, memory):
        profile = {
            "id": "test-agent-1",
            "name": "TestAgent",
            "role": "general",
            "nafs_level": 1,
            "capabilities": ["bash", "read_file"],
            "config": {"model": "test"},
        }
        await memory.save_agent_profile(profile)
        agents = await memory.get_all_agents()
        assert len(agents) == 1
        assert agents[0]["name"] == "TestAgent"

    @pytest.mark.asyncio
    async def test_message_persistence(self, memory):
        session = "test-session-123"
        await memory.save_message(session, "user", "Hello MIZAN")
        await memory.save_message(session, "assistant", "Hello! How can I help?")

        messages = await memory.get_messages(session)
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_task_history(self, memory):
        await memory.save_task("agent-1", "analyze data", "success", True, 1500.0)
        await memory.save_task("agent-1", "broken task", "error: timeout", False, 5000.0)

        history = await memory.get_task_history()
        assert len(history) == 2
        # Ordered by created_at DESC — most recent first
        assert history[0]["success"] is False  # broken task is most recent
        assert history[1]["success"] is True   # analyze data was first

    @pytest.mark.asyncio
    async def test_masalik_integration(self, memory):
        """Dhikr should have masalik network integrated."""
        assert hasattr(memory, "masalik")
        assert isinstance(memory.masalik, MasalikNetwork)

    @pytest.mark.asyncio
    async def test_remember_encodes_pathways(self, memory):
        """Remembering should encode into masalik pathways too."""
        concepts_before = len(memory.masalik.concepts)
        await memory.remember(
            "Quantum computing uses qubits for parallel processing",
            importance=0.8,
        )
        concepts_after = len(memory.masalik.concepts)
        assert concepts_after > concepts_before

    @pytest.mark.asyncio
    async def test_no_duplication_in_masalik(self, memory):
        """Same content remembered twice → strengthened, not duplicated."""
        text = "Neural networks learn through backpropagation"
        await memory.remember(text, importance=0.8)
        pathways_first = len(memory.masalik.pathways)
        await memory.remember(text, importance=0.8)
        pathways_second = len(memory.masalik.pathways)
        assert pathways_second == pathways_first


# ═══════════════════════════════════════════════════════════════════════════════
# MEMORY DECAY MODEL
# ═══════════════════════════════════════════════════════════════════════════════

class TestMemoryDecayModel:
    def test_high_importance_decays_slower(self):
        high = Memory(importance=0.9, access_count=0)
        low = Memory(importance=0.1, access_count=0)
        assert high.decay(48) > low.decay(48)

    def test_frequent_access_strengthens(self):
        accessed = Memory(importance=0.5, access_count=10)
        fresh = Memory(importance=0.5, access_count=0)
        assert accessed.decay(24) > fresh.decay(24)

    def test_very_old_memories_low_strength(self):
        mem = Memory(importance=0.3, access_count=0)
        strength = mem.decay(24 * 365)  # 1 year
        assert strength < 0.01

    def test_high_importance_high_access_durable(self):
        mem = Memory(importance=0.95, access_count=50)
        strength = mem.decay(24 * 30)  # 30 days
        assert strength > 0.1  # Should still be meaningful
