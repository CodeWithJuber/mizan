"""
Tests for the Dhikr Memory System
"""

import pytest
from memory.dhikr import DhikrMemorySystem, Memory


class TestDhikrMemorySystem:
    """Test the three-tier Quranic memory system."""

    @pytest.fixture
    def memory(self, temp_db):
        return DhikrMemorySystem(db_path=temp_db)

    @pytest.mark.asyncio
    async def test_remember_and_recall(self, memory):
        """Test basic store and retrieve."""
        mem_id = await memory.remember(
            "The Quran was revealed in Ramadan",
            memory_type="semantic",
            importance=0.8,
            tags=["quran", "ramadan"],
        )
        assert mem_id

        results = await memory.recall("Quran Ramadan", memory_type="semantic")
        assert len(results) > 0
        assert any("Ramadan" in str(r.content) for r in results)

    @pytest.mark.asyncio
    async def test_memory_types(self, memory):
        """Test all three memory types (episodic, semantic, procedural)."""
        for mtype in ["episodic", "semantic", "procedural"]:
            mem_id = await memory.remember(
                f"Test {mtype} memory",
                memory_type=mtype,
                importance=0.5,
            )
            assert mem_id

        results = await memory.recall("Test", memory_type="semantic")
        assert all(r.memory_type == "semantic" for r in results)

    @pytest.mark.asyncio
    async def test_working_memory_capacity(self, memory):
        """Working memory should respect Miller's Law (7 items)."""
        for i in range(10):
            await memory.remember(
                f"Important fact {i}",
                importance=0.9,  # High importance goes to working memory
            )
        assert len(memory.working_memory) <= memory.working_capacity

    @pytest.mark.asyncio
    async def test_consolidation(self, memory):
        """Memory consolidation should prune low-importance old memories."""
        await memory.remember("ephemeral", importance=0.1)
        result = await memory.consolidate()
        assert result["consolidated"] is True

    @pytest.mark.asyncio
    async def test_save_and_get_agent_profile(self, memory):
        """Test agent profile persistence."""
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
    async def test_save_and_get_messages(self, memory):
        """Test chat message persistence."""
        session = "test-session"
        await memory.save_message(session, "user", "Hello")
        await memory.save_message(session, "assistant", "Hi there!")

        messages = await memory.get_messages(session)
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_task_history(self, memory):
        """Test task history recording."""
        await memory.save_task("agent-1", "test task", "success", True, 100.0)

        history = await memory.get_task_history()
        assert len(history) == 1
        assert history[0]["success"] is True


class TestMemoryDecay:
    """Test the Quranic memory decay model."""

    def test_high_importance_decays_slower(self):
        """Important memories should decay slower (longer half-life)."""
        high = Memory(importance=0.9, access_count=0)
        low = Memory(importance=0.1, access_count=0)

        hours = 48
        assert high.decay(hours) > low.decay(hours)

    def test_frequent_access_strengthens(self):
        """Frequently accessed memories should be stronger."""
        accessed = Memory(importance=0.5, access_count=10)
        fresh = Memory(importance=0.5, access_count=0)

        assert accessed.decay(24) > fresh.decay(24)
