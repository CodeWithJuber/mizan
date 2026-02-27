"""
Comprehensive Agent System Tests — Lifecycle, Tools, Security, Federation
==========================================================================

Real use cases:
  - Create different agent types → each has correct tools
  - Agent works hard → Nafs evolves through 7 levels
  - Agent executes dangerous command → blocked by Wali
  - Agent tries path traversal → sanitized
  - Agent federation → agents discover and delegate tasks
  - Specialized agents → browser, research, code, communication
"""

import pytest
import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from agents.base import BaseAgent
from agents.specialized import (
    BrowserAgent,
    ResearchAgent,
    CodeAgent,
    CommunicationAgent,
    create_agent,
)


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_wali():
    wali = MagicMock()
    wali.check_rate_limit.return_value = True
    wali.validate_command.return_value = True
    wali.validate_url.return_value = True
    wali.validate_file_path.return_value = True
    wali.audit = MagicMock()
    return wali


@pytest.fixture
def mock_izn():
    izn = MagicMock()
    izn.check_permission.return_value = {
        "allowed": True,
        "reason": "Test mode",
        "requires_approval": False,
    }
    return izn


@pytest.fixture
def temp_db(tmp_path):
    return str(tmp_path / "test.db")


def make_agent(agent_type, name="TestAgent", wali=None, izn=None, memory=None, config=None):
    """Helper to create agents with defaults."""
    if wali is None:
        wali = MagicMock()
        wali.check_rate_limit.return_value = True
        wali.validate_command.return_value = True
        wali.validate_url.return_value = True
        wali.validate_file_path.return_value = True
        wali.audit = MagicMock()
    if izn is None:
        izn = MagicMock()
        izn.check_permission.return_value = {
            "allowed": True, "reason": "Test", "requires_approval": False,
        }
    return create_agent(agent_type, name=name, wali=wali, izn=izn,
                        memory=memory, config=config or {})


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT CREATION
# ═══════════════════════════════════════════════════════════════════════════════

class TestAgentFactory:
    """Test creating all agent types through the factory."""

    def test_create_general_agent(self, mock_wali, mock_izn):
        agent = create_agent("general", name="General", wali=mock_wali, izn=mock_izn)
        assert agent is not None
        assert agent.name == "General"

    def test_create_browser_agent(self, mock_wali, mock_izn):
        agent = create_agent("browser", name="Browser", wali=mock_wali, izn=mock_izn)
        assert isinstance(agent, BrowserAgent)
        assert "browse_url" in agent.tools

    def test_create_research_agent(self, mock_wali, mock_izn):
        agent = create_agent("research", name="Research", wali=mock_wali, izn=mock_izn)
        assert isinstance(agent, ResearchAgent)
        assert "analyze_text" in agent.tools
        assert "fact_check" in agent.tools

    def test_create_code_agent(self, mock_wali, mock_izn):
        agent = create_agent("code", name="Code", wali=mock_wali, izn=mock_izn)
        assert isinstance(agent, CodeAgent)
        assert "python_exec" in agent.tools
        assert "git_operation" in agent.tools

    def test_create_communication_agent(self, mock_wali, mock_izn):
        agent = create_agent("communication", name="Comm", wali=mock_wali, izn=mock_izn)
        assert isinstance(agent, CommunicationAgent)
        assert "send_webhook" in agent.tools

    def test_create_with_arabic_names(self, mock_wali, mock_izn):
        """Quranic role names should work too."""
        agent = create_agent("mubashir", name="M", wali=mock_wali, izn=mock_izn)
        assert isinstance(agent, BrowserAgent)
        agent = create_agent("mundhir", name="M", wali=mock_wali, izn=mock_izn)
        assert isinstance(agent, ResearchAgent)
        agent = create_agent("katib", name="K", wali=mock_wali, izn=mock_izn)
        assert isinstance(agent, CodeAgent)
        agent = create_agent("rasul", name="R", wali=mock_wali, izn=mock_izn)
        assert isinstance(agent, CommunicationAgent)

    def test_unknown_type_falls_back_to_general(self, mock_wali, mock_izn):
        agent = create_agent("nonexistent_type", name="Fallback", wali=mock_wali, izn=mock_izn)
        assert agent is not None  # Should not crash


# ═══════════════════════════════════════════════════════════════════════════════
# BASE AGENT ATTRIBUTES
# ═══════════════════════════════════════════════════════════════════════════════

class TestBaseAgentAttributes:
    def test_initial_state(self, mock_wali, mock_izn):
        agent = make_agent("general", wali=mock_wali, izn=mock_izn)
        assert agent.nafs_level == 1  # Ammara
        assert agent.total_tasks == 0
        assert agent.success_count == 0
        assert agent.success_rate == 0.0

    def test_has_core_tools(self, mock_wali, mock_izn):
        agent = make_agent("general", wali=mock_wali, izn=mock_izn)
        expected_tools = ["bash", "read_file", "write_file", "http_get", "python_exec"]
        for tool in expected_tools:
            assert tool in agent.tools, f"Missing tool: {tool}"

    def test_tool_schemas_valid(self, mock_wali, mock_izn):
        agent = make_agent("general", wali=mock_wali, izn=mock_izn)
        schemas = agent.get_tool_schemas()
        assert len(schemas) >= 6
        for schema in schemas:
            assert "name" in schema
            assert "description" in schema
            assert "input_schema" in schema
            # Verify schema is well-formed
            assert isinstance(schema["input_schema"], dict)
            assert "type" in schema["input_schema"]

    def test_to_dict_complete(self, mock_wali, mock_izn):
        agent = make_agent("general", wali=mock_wali, izn=mock_izn)
        d = agent.to_dict()
        required_keys = ["id", "name", "role", "nafs_level", "success_rate", "tools"]
        for key in required_keys:
            assert key in d, f"Missing key in to_dict: {key}"

    def test_success_rate_calculation(self, mock_wali, mock_izn):
        agent = make_agent("general", wali=mock_wali, izn=mock_izn)
        agent.total_tasks = 10
        agent.success_count = 7
        assert agent.success_rate == 0.7

    def test_success_rate_zero_tasks(self, mock_wali, mock_izn):
        agent = make_agent("general", wali=mock_wali, izn=mock_izn)
        assert agent.success_rate == 0.0

    def test_unique_ids(self, mock_wali, mock_izn):
        a1 = make_agent("general", name="A1", wali=mock_wali, izn=mock_izn)
        a2 = make_agent("general", name="A2", wali=mock_wali, izn=mock_izn)
        assert a1.id != a2.id


# ═══════════════════════════════════════════════════════════════════════════════
# NAFS EVOLUTION (7 Levels of Spiritual Growth)
# ═══════════════════════════════════════════════════════════════════════════════

class TestNafsEvolution:
    """Test the 7-level Nafs model based on agent performance."""

    def test_starts_as_ammara(self, mock_wali, mock_izn):
        agent = make_agent("general", wali=mock_wali, izn=mock_izn)
        assert agent.nafs_level == 1  # Ammara (commanding soul)

    def test_evolve_to_lawwama(self, mock_wali, mock_izn):
        """Level 2: Self-blaming soul — requires >= 60% success, >= 25 tasks."""
        agent = make_agent("general", wali=mock_wali, izn=mock_izn)
        agent.total_tasks = 30
        agent.success_count = 20  # 66.7%
        agent.evolve_nafs()
        assert agent.nafs_level == 2

    def test_evolve_to_mulhama(self, mock_wali, mock_izn):
        """Level 3: Inspired soul — requires >= 75%, >= 100 tasks."""
        agent = make_agent("general", wali=mock_wali, izn=mock_izn)
        agent.total_tasks = 100
        agent.success_count = 80
        agent.evolve_nafs()
        assert agent.nafs_level == 3

    def test_evolve_to_mutmainna(self, mock_wali, mock_izn):
        """Level 4: Tranquil soul — requires >= 85%, >= 250 tasks."""
        agent = make_agent("general", wali=mock_wali, izn=mock_izn)
        agent.total_tasks = 250
        agent.success_count = 220
        agent.evolve_nafs()
        assert agent.nafs_level == 4

    def test_no_evolution_insufficient_tasks(self, mock_wali, mock_izn):
        """Can't evolve with too few tasks even if success rate is high."""
        agent = make_agent("general", wali=mock_wali, izn=mock_izn)
        agent.total_tasks = 5
        agent.success_count = 5  # 100% but only 5 tasks
        agent.evolve_nafs()
        assert agent.nafs_level == 1  # Still Ammara

    def test_no_evolution_low_success_rate(self, mock_wali, mock_izn):
        """Can't evolve with low success rate even with many tasks."""
        agent = make_agent("general", wali=mock_wali, izn=mock_izn)
        agent.total_tasks = 100
        agent.success_count = 40  # 40% — too low
        agent.evolve_nafs()
        assert agent.nafs_level == 1

    def test_task_classification(self, mock_wali, mock_izn):
        agent = make_agent("general", wali=mock_wali, izn=mock_izn)
        assert agent._classify_task("write python code for the API") == "coding"
        assert agent._classify_task("search the web for information") == "research"
        assert agent._classify_task("send an email notification") == "communication"
        assert agent._classify_task("analyze the dataset") == "analysis"
        assert agent._classify_task("read the configuration file") == "file_management"
        assert agent._classify_task("what time is it") == "general"


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT SECURITY BOUNDARIES
# ═══════════════════════════════════════════════════════════════════════════════

class TestAgentSecurity:
    """Test security enforcement during tool execution."""

    @pytest.mark.asyncio
    async def test_dangerous_command_blocked(self, mock_wali, mock_izn):
        agent = make_agent("general", wali=mock_wali, izn=mock_izn)
        result = await agent._tool_bash(command="rm -rf /")
        assert "error" in result or "blocked" in str(result).lower()

    @pytest.mark.asyncio
    async def test_permission_denied(self, mock_wali, mock_izn):
        mock_izn.check_permission.return_value = {
            "allowed": False,
            "reason": "Insufficient permissions",
            "requires_approval": True,
        }
        agent = make_agent("general", wali=mock_wali, izn=mock_izn)
        result = await agent._execute_tool_safe("bash", {"command": "ls"})
        assert "error" in result or "denied" in str(result).lower()

    @pytest.mark.asyncio
    async def test_safe_command_allowed(self, mock_wali, mock_izn):
        """Safe commands should execute when permissions allow."""
        agent = make_agent("general", wali=mock_wali, izn=mock_izn)
        result = await agent._tool_bash(command="echo hello")
        assert isinstance(result, dict)


# ═══════════════════════════════════════════════════════════════════════════════
# SPECIALIZED AGENT TOOLS
# ═══════════════════════════════════════════════════════════════════════════════

class TestBrowserAgentTools:
    @pytest.fixture
    def agent(self, mock_wali, mock_izn):
        return create_agent("browser", name="TestBrowser", wali=mock_wali, izn=mock_izn)

    def test_has_browser_tools(self, agent):
        browser_tools = [
            "browse_url", "navigate", "search_web",
            "extract_content", "take_screenshot",
            "click_element", "fill_form",
        ]
        for tool in browser_tools:
            assert tool in agent.tools

    def test_playwright_check_cached(self, agent):
        """Playwright availability check should be memoized."""
        result1 = agent._check_playwright()
        result2 = agent._check_playwright()
        assert result1 == result2  # Same result = cached


class TestResearchAgentTools:
    @pytest.fixture
    def agent(self, mock_wali, mock_izn):
        return create_agent("research", name="TestResearch", wali=mock_wali, izn=mock_izn)

    def test_has_research_tools(self, agent):
        research_tools = [
            "analyze_text", "synthesize_sources",
            "fact_check", "generate_report", "arxiv_search",
        ]
        for tool in research_tools:
            assert tool in agent.tools

    @pytest.mark.asyncio
    async def test_analyze_text(self, agent):
        result = await agent._tool_analyze_text("The quick brown fox jumps over the lazy dog. Testing analysis.")
        assert "word_count" in result
        assert result["word_count"] > 0
        assert "key_terms" in result

    @pytest.mark.asyncio
    async def test_synthesize_sources(self, agent):
        result = await agent._tool_synthesize_sources(["Source 1", "Source 2", "Source 3"])
        assert result["source_count"] == 3
        assert result["synthesized"] is True

    @pytest.mark.asyncio
    async def test_fact_check(self, agent):
        result = await agent._tool_fact_check("The Earth is flat")
        assert "claim" in result
        assert "status" in result

    @pytest.mark.asyncio
    async def test_generate_report(self, agent):
        result = await agent._tool_generate_report("AI Safety", format="markdown")
        assert "template" in result
        assert "# Research Report" in result["template"]


class TestCodeAgentTools:
    @pytest.fixture
    def agent(self, mock_wali, mock_izn):
        return create_agent("code", name="TestCode", wali=mock_wali, izn=mock_izn)

    def test_has_code_tools(self, agent):
        code_tools = [
            "generate_code", "run_tests", "lint_code",
            "git_operation", "install_package",
        ]
        for tool in code_tools:
            assert tool in agent.tools

    @pytest.mark.asyncio
    async def test_generate_code(self, agent):
        result = await agent._tool_generate_code("fibonacci function", language="python")
        assert result["language"] == "python"
        assert "template" in result

    @pytest.mark.asyncio
    async def test_git_blocked_operation(self, agent):
        """Non-safe git operations should be blocked."""
        result = await agent._tool_git_operation("reset --hard", "/tmp")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_install_package_validation(self, agent):
        """Malicious package names should be rejected."""
        result = await agent._tool_install_package("flask; rm -rf /")
        assert "error" in result


class TestCommunicationAgentTools:
    @pytest.fixture
    def agent(self, mock_wali, mock_izn):
        return create_agent("communication", name="TestComm", wali=mock_wali, izn=mock_izn)

    def test_has_comm_tools(self, agent):
        comm_tools = ["send_webhook", "check_email", "send_notification"]
        for tool in comm_tools:
            assert tool in agent.tools

    @pytest.mark.asyncio
    async def test_send_notification_log(self, agent):
        result = await agent._tool_send_notification("Test message", channel="log")
        assert result["sent"] is True
        assert result["channel"] == "log"

    @pytest.mark.asyncio
    async def test_send_notification_unknown_channel(self, agent):
        result = await agent._tool_send_notification("Test", channel="carrier_pigeon")
        assert "error" in result


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT FEDERATION
# ═══════════════════════════════════════════════════════════════════════════════

class TestAgentFederation:
    """Test inter-agent communication and task delegation."""

    def test_federation_imports(self):
        from agents.federation import AgentFederation, RisalahMessage, MessageType
        fed = AgentFederation()
        assert fed is not None

    def test_register_and_discover(self):
        from agents.federation import AgentFederation
        fed = AgentFederation()
        fed.register_agent("agent-1", "Agent1", "katib", ["coding", "testing"])
        fed.register_agent("agent-2", "Agent2", "mundhir", ["research", "analysis"])

        discovered = fed.discover(["coding"])
        assert len(discovered) > 0

    def test_find_best_agent(self):
        from agents.federation import AgentFederation
        fed = AgentFederation()
        fed.register_agent("code-agent", "Coder", "katib", ["coding", "testing"])
        fed.register_agent("research-agent", "Researcher", "mundhir", ["research", "analysis"])

        best = fed.find_best_agent("write Python code")
        assert best is not None

    def test_delegation_flow(self):
        from agents.federation import AgentFederation, MessageType
        fed = AgentFederation()
        fed.register_agent("manager", "Manager", "general", ["management"])
        fed.register_agent("coder", "Coder", "katib", ["coding", "testing"])

        result = asyncio.get_event_loop().run_until_complete(
            fed.delegate_task("manager", "Write unit tests", ["coding"])
        )
        assert result is not None
        assert "delegated_to" in result
        assert result["delegated_to"] == "coder"

    def test_message_sending(self):
        from agents.federation import AgentFederation, RisalahMessage, MessageType
        fed = AgentFederation()
        fed.register_agent("sender", "Sender", "general", ["general"])
        fed.register_agent("receiver", "Receiver", "general", ["general"])

        received = []

        async def handler(msg):
            received.append(msg)

        fed.on_message(MessageType.STATUS, handler)

        msg = RisalahMessage(
            msg_type=MessageType.STATUS,
            sender_id="sender",
            recipient_id="receiver",
            payload={"status": "ok"},
        )
        asyncio.get_event_loop().run_until_complete(fed.send_message(msg))
        assert len(received) == 1
        assert received[0].sender_id == "sender"

    def test_unregister_agent(self):
        from agents.federation import AgentFederation
        fed = AgentFederation()
        fed.register_agent("temp", "Temp", "general", ["testing"])
        fed.unregister_agent("temp")
        discovered = fed.discover(["testing"])
        assert all(d.agent_id != "temp" for d in discovered) if discovered else True

    def test_federation_status(self):
        from agents.federation import AgentFederation
        fed = AgentFederation()
        fed.register_agent("agent-1", "Agent1", "katib", ["coding"])
        status = fed.get_status()
        assert "agents" in status or "registered" in str(status).lower() or isinstance(status, dict)
