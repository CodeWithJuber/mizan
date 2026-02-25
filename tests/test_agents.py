"""
Tests for the Agent System
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from agents.base import BaseAgent
from agents.specialized import create_agent


class TestBaseAgent:
    """Test base agent functionality."""

    @pytest.fixture
    def agent(self, mock_wali, mock_izn, temp_db):
        from memory.dhikr import DhikrMemorySystem

        memory = DhikrMemorySystem(db_path=temp_db)
        return create_agent(
            "general",
            name="TestAgent",
            memory=memory,
            config={"model": "test-model"},
            wali=mock_wali,
            izn=mock_izn,
        )

    def test_agent_creation(self, agent):
        """Agent should be created with correct attributes."""
        assert agent.name == "TestAgent"
        assert agent.nafs_level == 1  # Starts as Ammara
        assert agent.total_tasks == 0
        assert "bash" in agent.tools
        assert "read_file" in agent.tools

    def test_nafs_evolution(self, agent):
        """Nafs level should evolve based on performance."""
        # Start as Ammara
        assert agent.nafs_level == 1

        # Simulate good performance
        agent.total_tasks = 100
        agent.success_count = 75
        agent.learning_iterations = 10
        agent.evolve_nafs()
        assert agent.nafs_level == 2  # Lawwama

        # Simulate excellent performance
        agent.success_count = 95
        agent.learning_iterations = 60
        agent.evolve_nafs()
        assert agent.nafs_level == 3  # Mutmainna

    def test_success_rate(self, agent):
        """Success rate calculation."""
        assert agent.success_rate == 0.0

        agent.total_tasks = 10
        agent.success_count = 8
        assert agent.success_rate == 0.8

    def test_tool_schemas(self, agent):
        """Tool schemas should be valid for Claude API."""
        schemas = agent.get_tool_schemas()
        assert len(schemas) >= 6  # At least base tools

        for schema in schemas:
            assert "name" in schema
            assert "description" in schema
            assert "input_schema" in schema

    def test_to_dict(self, agent):
        """Serialization should include all key fields."""
        d = agent.to_dict()
        assert "id" in d
        assert "name" in d
        assert "role" in d
        assert "nafs_level" in d
        assert "success_rate" in d
        assert "tools" in d

    def test_classify_task(self, agent):
        """Task classification should work for different types."""
        assert agent._classify_task("write python code") == "coding"
        assert agent._classify_task("search the web") == "research"
        assert agent._classify_task("send an email") == "communication"
        assert agent._classify_task("analyze this data") == "analysis"
        assert agent._classify_task("read the file") == "file_management"
        assert agent._classify_task("hello world") == "general"


class TestAgentSecurity:
    """Test agent security boundaries."""

    @pytest.fixture
    def agent(self, mock_wali, mock_izn):
        return create_agent(
            "general",
            name="SecAgent",
            config={},
            wali=mock_wali,
            izn=mock_izn,
        )

    @pytest.mark.asyncio
    async def test_blocked_command(self, agent):
        """Dangerous commands should be blocked."""
        result = await agent._tool_bash(command="rm -rf /")
        assert "error" in result or "blocked" in str(result).lower()

    @pytest.mark.asyncio
    async def test_permission_denied(self, agent, mock_izn):
        """Tools should be blocked when Izn denies permission."""
        mock_izn.check_permission.return_value = {
            "allowed": False,
            "reason": "Insufficient permissions",
            "requires_approval": True,
        }
        result = await agent._execute_tool_safe("bash", {"command": "ls"})
        assert "error" in result or "denied" in str(result).lower()


class TestAgentCreation:
    """Test specialized agent creation."""

    def test_create_general_agent(self, mock_wali, mock_izn):
        agent = create_agent("general", name="G", wali=mock_wali, izn=mock_izn)
        assert agent is not None

    def test_create_browser_agent(self, mock_wali, mock_izn):
        agent = create_agent("browser", name="B", wali=mock_wali, izn=mock_izn)
        assert "browse_url" in agent.tools or "http_get" in agent.tools

    def test_create_research_agent(self, mock_wali, mock_izn):
        agent = create_agent("research", name="R", wali=mock_wali, izn=mock_izn)
        assert agent is not None

    def test_create_code_agent(self, mock_wali, mock_izn):
        agent = create_agent("code", name="C", wali=mock_wali, izn=mock_izn)
        assert "python_exec" in agent.tools
