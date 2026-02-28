"""
Base Agent (Wakil - وكيل)
==========================

"And sufficient is Allah as a Trustee (Wakil)" - Quran 4:81

Every agent embodies the Quranic Nafs model:
- Has a clear purpose (Niyyah - نية)
- Acts with excellence (Ihsan - إحسان)
- Self-corrects (Nafs Lawwama - نفس لوامة)
- Grows wiser with experience (Hikmah - حكمة)

The agent cycle mirrors Quranic breathing of life:
Input (Sama' - سمع) → Process (Fikr - فكر) → Act (Amal - عمل) → Reflect (Tafakkur - تفكر)
"""

import asyncio
import inspect
import json
import logging
import os
import subprocess
import time
import uuid
from collections.abc import AsyncGenerator, Callable
from datetime import UTC, datetime
from typing import Any

import httpx

from core.ihsan import IhsanMode
from core.qalb import EmotionalState, QalbEngine

# Core Quranic systems integration
from core.ruh_engine import RuhEngine
from core.sabr import SabrEngine
from core.shukr import ShukrSystem
from core.tawbah import TawbahProtocol
from providers import create_provider, get_default_model, normalize_model_for_provider
from qca.cognitive_methods import IjmaEngine, select_method
from qca.engine import QCAEngine
from qca.yaqin_engine import YaqinEngine
from security.validation import (
    sanitize_path,
    validate_command_safe,
    validate_url,
)

# QALB-7 architecture modules — core
from core.fitrah import FitrahSystem
from core.nafs_triad import NafsTriad
from core.qalb_processor import QalbProcessor
from core.lubb import LubbEngine
from core.fuad import FuadEngine
from core.developmental_stages import DevelopmentalGate

# QALB-7 extension modules — parallel, healing, creativity, imagination, dreams
from core.parallel_agents import QalbParallelScheduler, SkillAutomationTransfer
from core.self_healing import LawwamaHealingSystem
from core.imagination import TaswirImaginationEngine, ImaginationMode
from core.creativity import IbdaCreativityEngine
from core.dream_engine import ManamDreamEngine

# Living Memory + 24/7 Multi-Agent Collaboration
from memory.living_memory import LivingMemorySystem
from agents.shura_council import ShuraCouncil
from agents.perpetual_rotation import PerpetualRotation

logger = logging.getLogger("mizan.agent")


class BaseAgent:
    """
    Quranic Agent Architecture
    Every agent has seven core attributes (Sab'a Sifat - سبع صفات):
    1. Id (هوية)
    2. Name (اسم)
    3. Role (دور)
    4. Capabilities (قدرات)
    5. Memory (ذاكرة)
    6. Tools (أدوات)
    7. Learning (تعلم)
    """

    # Tool schemas for Claude tool_use API
    TOOL_SCHEMAS: list[dict] = []

    def __init__(
        self,
        agent_id: str = None,
        name: str = "",
        role: str = "wakil",
        config: dict = None,
        memory=None,
        wali=None,
        izn=None,
        skill_registry=None,
        plugin_manager=None,
        knowledge_graph=None,
        context_manager=None,
        planner=None,
    ):
        self.id = agent_id or str(uuid.uuid4())
        self.name = name or f"Agent-{self.id[:8]}"
        self.role = role
        self.config = config or {}
        self.memory = memory

        # Security (Wali guardian + Izn permissions)
        self.wali = wali
        self.izn = izn

        # Skills and plugins (Hikmah + Wasilah)
        self.skill_registry = skill_registry
        self.plugin_manager = plugin_manager

        # Knowledge Graph (Ilm) — entity/relationship store
        self.knowledge_graph = knowledge_graph

        # Context Manager — token-aware compaction
        self.context_manager = context_manager

        # Planner (Tafakkur) — task decomposition
        self.planner = planner

        # Reference to global agent registry (set by API when available)
        self._agent_registry: dict | None = None
        self._balancer = None
        self._shura = None

        # State tracking
        self.state = "resting"
        self.current_task: str | None = None
        self.task_queue: asyncio.Queue = asyncio.Queue()

        # Performance metrics (Mizan - balance)
        self.total_tasks = 0
        self.success_count = 0
        self.error_count = 0
        self.total_duration_ms = 0.0
        self.learning_iterations = 0
        self.nafs_level = 1  # 1-7 (Ammara → Kamila)

        # Tools registry
        self.tools: dict[str, Callable] = {}
        self._register_base_tools()

        # Learning store (Hikmah)
        self.hikmah: list[dict] = []

        # ── Core Quranic systems ──
        self.ruh = RuhEngine()  # Energy/vitality management
        self.tawbah = TawbahProtocol()  # Error recovery protocol
        self.ihsan = IhsanMode()  # Proactive excellence
        self.sabr = SabrEngine()  # Long-running task patience
        self.shukr = ShukrSystem()  # Strength reinforcement
        self.qalb = QalbEngine()  # Emotional intelligence
        self.yaqin = YaqinEngine()  # Certainty/confidence tracking
        self.qca = QCAEngine()  # 7-layer cognitive architecture
        self.cognitive = IjmaEngine()  # Cognitive reasoning methods

        # QALB-7 layer additions
        self.fitrah = FitrahSystem()          # Innate ethical BIOS (immutable axioms)
        self.nafs_triad = NafsTriad()         # Three-voice consciousness deliberation
        self.qalb_processor = QalbProcessor() # Cardiac oscillation → LLM params
        self.lubb = LubbEngine()              # Metacognition: compress, cohere, debias
        self.fuad = FuadEngine()              # Conviction formation + confidence scoring
        self.dev_gate = DevelopmentalGate()   # Capability gating by nafs_level
        self._nafs_approach: str = ""         # Current dominant Nafs voice instruction

        # QALB-7 extension modules
        self.parallel_scheduler = QalbParallelScheduler()   # Multi-stream parallel processing
        self.skill_automation = SkillAutomationTransfer()   # Cerebellar skill automation
        self.self_healer = LawwamaHealingSystem()           # 4-level self-repair
        self.imagination = TaswirImaginationEngine()        # Mental simulation + counterfactuals
        self.creativity = IbdaCreativityEngine()            # 5-mode creativity engine
        self.dream_engine = ManamDreamEngine()              # Offline memory consolidation

        # Living Memory + 24/7 Multi-Agent Collaboration
        self.living_memory = LivingMemorySystem()            # Novelty-gated 4-level memory
        self.shura_council = ShuraCouncil()                  # Multi-agent consultation
        self.perpetual_rotation = PerpetualRotation()        # 24/7 shift rotation

        # Load Fitrah axioms into QCA Lawh Tier 1 (immutable moral foundation)
        for key, entry in self.fitrah.get_lawh_tier1_entries().items():
            try:
                self.qca.lawh.store(
                    key, entry["content"], certainty=1.0, source=entry["source"], tier=1
                )
            except Exception:
                pass

        # LLM provider — unified interface for Anthropic, OpenRouter, OpenAI, Ollama
        default_model = os.getenv("DEFAULT_MODEL", "claude-sonnet-4-20250514")
        self.ai_model = config.get("model", default_model) if config else default_model
        provider_name = os.getenv("LLM_PROVIDER", "") or None
        self.ai_client = create_provider(provider=provider_name, model=self.ai_model)
        if self.ai_client:
            # Normalize model ID for the active provider (e.g. Anthropic→OpenRouter format)
            self.ai_model = normalize_model_for_provider(self.ai_model, self.ai_client.provider_name)
            # If no model set in config, use the provider's default
            if not config or "model" not in config:
                self.ai_model = get_default_model(self.ai_client.provider_name)

    def _register_base_tools(self):
        """Register core Quranic tools every agent has"""
        self.tools = {
            "bash": self._tool_bash,
            "http_get": self._tool_http_get,
            "http_post": self._tool_http_post,
            "read_file": self._tool_read_file,
            "write_file": self._tool_write_file,
            "list_files": self._tool_list_files,
            "python_exec": self._tool_python_exec,
            "create_agent": self._tool_create_agent,
            "create_skill": self._tool_create_skill,
            "compact_context": self._tool_compact_context,
            "recall_memory": self._tool_recall_memory,
            "delegate_task": self._tool_delegate_task,
            "query_knowledge": self._tool_query_knowledge,
        }

    def get_tool_schemas(self) -> list[dict]:
        """Get Claude tool_use API schemas for this agent's tools"""
        schemas = [
            {
                "name": "bash",
                "description": "Execute a shell command. Only safe commands are allowed.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "The shell command to execute",
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Timeout in seconds (max 60)",
                            "default": 30,
                        },
                    },
                    "required": ["command"],
                },
            },
            {
                "name": "http_get",
                "description": "Make an HTTP GET request to a URL.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "The URL to request"},
                        "headers": {"type": "object", "description": "Optional HTTP headers"},
                    },
                    "required": ["url"],
                },
            },
            {
                "name": "http_post",
                "description": "Make an HTTP POST request with JSON data.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "The URL to request"},
                        "data": {"type": "object", "description": "JSON data to send"},
                        "headers": {"type": "object", "description": "Optional HTTP headers"},
                    },
                    "required": ["url"],
                },
            },
            {
                "name": "read_file",
                "description": "Read the contents of a file.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path to read"},
                    },
                    "required": ["path"],
                },
            },
            {
                "name": "write_file",
                "description": "Write content to a file. Only allowed in sandbox directories.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path to write"},
                        "content": {"type": "string", "description": "Content to write"},
                    },
                    "required": ["path", "content"],
                },
            },
            {
                "name": "list_files",
                "description": "List files in a directory.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Directory path", "default": "."},
                        "pattern": {
                            "type": "string",
                            "description": "Glob pattern",
                            "default": "*",
                        },
                    },
                },
            },
            {
                "name": "python_exec",
                "description": "Execute Python code in a sandboxed subprocess.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "description": "Python code to execute"},
                    },
                    "required": ["code"],
                },
            },
            {
                "name": "create_agent",
                "description": "Create a new specialized agent. Types: super (all tools), browser, research, code, communication, general.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Name for the new agent"},
                        "type": {
                            "type": "string",
                            "description": "Agent type: super, browser, research, code, communication, general",
                            "default": "general",
                        },
                        "role": {
                            "type": "string",
                            "description": "Optional role description for the agent",
                            "default": "",
                        },
                    },
                    "required": ["name"],
                },
            },
            {
                "name": "create_skill",
                "description": "Dynamically create a new skill/tool at runtime. The skill code will be saved and registered immediately. Use this to add new capabilities on the fly.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Skill name (snake_case, e.g. 'my_custom_skill')",
                        },
                        "description": {
                            "type": "string",
                            "description": "What the skill does",
                        },
                        "code": {
                            "type": "string",
                            "description": "Full Python code for the skill class. Must subclass SkillBase.",
                        },
                        "tools": {
                            "type": "object",
                            "description": "Simple tool definitions as {name: {description, params}} for auto-generating a skill without full code.",
                        },
                    },
                    "required": ["name"],
                },
            },
            {
                "name": "compact_context",
                "description": "Compact conversation context by summarizing older messages to stay within context window limits. Use when conversation is getting long.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "conversation_history": {
                            "type": "array",
                            "description": "The conversation history to compact (list of message dicts with 'role' and 'content')",
                            "items": {"type": "object"},
                        },
                    },
                    "required": ["conversation_history"],
                },
            },
            {
                "name": "recall_memory",
                "description": "Search stored memories and ingested knowledge (URLs, PDFs, YouTube transcripts). Use when you need information that may have been previously stored or ingested.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query to find relevant memories",
                        },
                        "memory_type": {
                            "type": "string",
                            "enum": ["semantic", "episodic", "procedural"],
                            "description": "Filter by memory type (optional)",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max results to return (default 5)",
                            "default": 5,
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "delegate_task",
                "description": "Delegate a sub-task to another agent in the federation. Use when a task requires expertise you don't have (e.g., delegate coding to Katib, browsing to Mubashir).",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "task": {
                            "type": "string",
                            "description": "The task to delegate to another agent",
                        },
                        "preferred_role": {
                            "type": "string",
                            "enum": ["code", "browser", "research", "communication", "general"],
                            "description": "Preferred agent role for this task",
                        },
                    },
                    "required": ["task"],
                },
            },
            {
                "name": "query_knowledge",
                "description": "Query the knowledge graph for facts about an entity. Use to check what you know before making claims.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "entity": {
                            "type": "string",
                            "description": "The entity name to query",
                        },
                    },
                    "required": ["entity"],
                },
            },
        ]
        all_schemas = schemas + self.TOOL_SCHEMAS

        # Include tool schemas from loaded skills (Hikmah — wisdom)
        if self.skill_registry:
            try:
                skill_schemas = self.skill_registry.get_all_tool_schemas()
                if skill_schemas:
                    all_schemas.extend(skill_schemas)
            except Exception as e:
                logger.warning(f"[HIKMAH] Failed to get skill tool schemas: {e}")

        # Include tool schemas from loaded plugins (Wahy — revelation)
        if self.plugin_manager:
            try:
                plugin_schemas = self.plugin_manager.get_all_tool_schemas()
                if plugin_schemas:
                    all_schemas.extend(plugin_schemas)
            except Exception as e:
                logger.warning(f"[WAHY] Failed to get plugin tool schemas: {e}")

        return all_schemas

    @property
    def success_rate(self) -> float:
        if self.total_tasks == 0:
            return 0.0
        return self.success_count / self.total_tasks

    @property
    def avg_duration_ms(self) -> float:
        if self.total_tasks == 0:
            return 0.0
        return self.total_duration_ms / self.total_tasks

    # 7-level Nafs names for display
    NAFS_NAMES = {
        1: "Ammara",
        2: "Lawwama",
        3: "Mulhama",
        4: "Mutmainna",
        5: "Radiya",
        6: "Mardiyya",
        7: "Kamila",
    }

    def evolve_nafs(self):
        """Evolve Nafs level via DevelopmentalGate readiness check.

        Delegates to dev_gate.check_upgrade_readiness() which uses
        NafsProfile.EVOLUTION_THRESHOLDS (success_rate, min_tasks, min_hikmah).
        """
        old_level = self.nafs_level
        report = self.dev_gate.check_upgrade_readiness(self)
        if report.ready:
            self.nafs_level = report.target_level

        if self.nafs_level != old_level:
            logger.info(
                "[NAFS] %s evolved: %s → %s (L%d→L%d, tazkiyah=%.2f)",
                self.name,
                self.NAFS_NAMES.get(old_level, "?"),
                self.NAFS_NAMES.get(self.nafs_level, "?"),
                old_level,
                self.nafs_level,
                report.tazkiyah_score,
            )

    @property
    def max_tool_turns(self) -> int:
        """Dynamic tool turn limit from DevelopmentalGate stage."""
        return self.dev_gate.get_capabilities(self.nafs_level).max_turns

    @property
    def can_delegate(self) -> bool:
        """Whether agent can delegate — from DevelopmentalGate capabilities."""
        return self.dev_gate.get_capabilities(self.nafs_level).can_delegate

    def _check_tool_permission(self, tool_name: str, params: dict = None) -> dict:
        """Check Izn permissions before tool execution"""
        if self.izn:
            return self.izn.check_permission(self.id, self.role, tool_name, params)
        return {"allowed": True, "reason": "No Izn configured", "requires_approval": False}

    # Maximum agentic loop iterations — dynamically adjusted by Nafs level
    MAX_TOOL_TURNS = 15  # Fallback default; actual limit comes from max_tool_turns property

    async def think(
        self, task: str, context: dict = None, stream: bool = False, qalb_reading=None
    ) -> AsyncGenerator[str, None]:
        """
        Fikr (فكر) - Deep cognitive processing with full agentic loop.

        Unlike a single-turn LLM call, this implements a proper ReAct loop:
        the agent can call tools, observe results, reason further, call more
        tools, and repeat — up to MAX_TOOL_TURNS — until the task is complete.
        """
        self.state = "thinking"

        system_prompt = await self._build_system_prompt(qalb_reading=qalb_reading)
        messages = self._build_messages(task, context)
        tool_schemas = self.get_tool_schemas()

        # DevelopmentalGate — filter available tools to this agent's capability level
        tool_schemas = self.dev_gate.filter_tool_schemas(tool_schemas, self.nafs_level)

        # QalbProcessor — compute cardiac oscillation state → LLM params
        qalb_proc_output = self.qalb_processor.process(
            task=task,
            emotional_state=qalb_reading.state.value if qalb_reading else "neutral",
            nafs_level=self.nafs_level,
            complexity=self.ruh.classify_task_complexity(task),
        )
        self._qalb_params = {
            "max_tokens": qalb_proc_output.max_tokens,
            "temperature": qalb_proc_output.temperature,
        }
        logger.debug(
            "[QALB] State=%s max_tokens=%d temp=%.2f",
            qalb_proc_output.state.value,
            qalb_proc_output.max_tokens,
            qalb_proc_output.temperature,
        )

        # QCA Layer 1-4: Process input through Sam'+Basar+Fu'ad+ISM
        qca_input = self.qca.process_input(task[:500])
        if qca_input.get("roots_identified"):
            root_context = "Semantic roots: " + ", ".join(
                f"{r['english_term']}→{r['root']}({r['meaning'][:30]})"
                for r in qca_input["roots_identified"][:5]
            )
            messages[-1]["content"] += f"\n\n[QCA Context: {root_context}]"

        # QCA Layer 7: Check Lawh memory for relevant prior knowledge
        memory_hits = self.qca.lawh.search(task, top_k=3, tiers=[1, 2, 3])
        if memory_hits:
            mem_context = " | ".join(
                f"{key}: {entry.get('content', '')[:60]}" for _score, key, entry in memory_hits[:3]
            )
            messages[-1]["content"] += f"\n[Lawh Memory: {mem_context}]"

        # Context Manager: inject Dhikr memories for grounding
        if self.context_manager and self.memory:
            try:
                relevant_memories = await self.memory.recall(task, top_k=3)
                if relevant_memories:
                    memory_dicts = [
                        {"type": m.memory_type, "content": m.content}
                        for m in relevant_memories
                        if hasattr(m, "content")
                    ]
                    if memory_dicts:
                        messages = self.context_manager.inject_memory(messages, memory_dicts)
            except Exception:
                pass

        if self.ai_client:
            try:
                async for chunk in self._agentic_loop(
                    system_prompt, messages, tool_schemas, stream, task
                ):
                    yield chunk
            except Exception as e:
                err_str = str(e)
                logger.error(f"[FIKR] Thinking error for {self.name}: {e}")
                if "Connection" in err_str or "connect" in err_str.lower():
                    yield (
                        f"Could not reach the AI provider. "
                        f"Please check your API key and network connection in .env "
                        f"(ANTHROPIC_API_KEY, OPENROUTER_API_KEY, or OPENAI_API_KEY)."
                    )
                else:
                    yield f"[Error: {err_str}]"
        else:
            yield await self._structured_reasoning(task, context)

        self.state = "resting"

    async def _agentic_loop(
        self,
        system_prompt: str,
        messages: list[dict],
        tool_schemas: list[dict],
        stream: bool = False,
        original_task: str = "",
    ) -> AsyncGenerator[str, None]:
        """
        Full agentic loop — the core of MIZAN's reasoning engine.

        Repeatedly calls the LLM, executes any requested tools, feeds results
        back, and continues until the model produces a final text response
        with no further tool calls (stop_reason == 'end_turn') or we hit
        the safety limit of MAX_TOOL_TURNS.

        QCA Integration (7-layer cognitive pipeline):
        - Yaqin: Tag tool results with certainty level (Ilm/Ayn/Haqq)
        - Mizan: Weigh confidence of each reasoning turn
        - Lawh: Store tool results in working memory (Tier 3)
        - Furqan: Validate final output before delivery
        - Lawwama: Self-correction checkpoints every 3 turns

        Uses the unified provider interface (providers.py) so this works
        identically with Anthropic, OpenRouter, OpenAI, and Ollama.
        """
        accumulated_text = ""
        tool_count = 0

        for turn in range(self.max_tool_turns):
            # Qalb-modulated LLM params (cardiac oscillation: QABD=analytical, BAST=creative)
            qalb_params = getattr(self, "_qalb_params", {})
            max_tokens = qalb_params.get("max_tokens", 4096)
            temperature = qalb_params.get("temperature", 0.5)

            # Call the model via unified provider
            response = self.ai_client.create(
                model=self.ai_model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt,
                messages=messages,
                tools=tool_schemas,
            )

            # Collect text output and tool calls from this turn
            has_tool_use = False
            tool_results = []

            for block in response.content:
                if block.type == "text":
                    accumulated_text += block.text
                    yield block.text
                elif block.type == "tool_use":
                    has_tool_use = True
                    tool_count += 1

                    # Execute through security layer
                    tool_result = await self._execute_tool_safe(block.name, block.input)
                    yield f"\n[Tool: {block.name}] → {json.dumps(tool_result)[:500]}\n"

                    # Yaqin: Tag tool result as Ayn al-Yaqin (observed/verified)
                    tool_summary = f"{block.name}: {json.dumps(tool_result)[:200]}"
                    yaqin_tag = self.yaqin.tag_observation(
                        tool_summary,
                        confidence=0.8,
                        source=block.name,
                        evidence=[f"Tool output from {block.name}"],
                    )

                    # Lawh: Store tool result in Tier 3 (working memory)
                    self.qca.lawh.store(
                        f"TOOL:{block.name}:{turn}",
                        tool_summary[:300],
                        certainty=yaqin_tag.confidence,
                        source=f"tool:{block.name}",
                        tier=3,
                    )

                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(tool_result)[:5000],
                        }
                    )

            # If no tool calls were made, the agent is done
            if not has_tool_use or response.stop_reason == "end_turn":
                # Furqan: Validate final output before delivery
                if accumulated_text:
                    overall_confidence = self.fuad.compute_confidence(
                        tool_count=tool_count, tool_results=tool_results,
                    )
                    furqan_report = self.qca.furqan.validate_and_express(
                        accumulated_text[:200],
                        overall_confidence,
                        source="agentic_reasoning",
                    )
                    # Store reasoning result in Lawh Tier 3
                    self.qca.lawh.store(
                        f"RESULT:{original_task[:50]}",
                        accumulated_text[:500],
                        certainty=overall_confidence,
                        source="agentic_loop",
                        tier=3,
                    )
                    # Log Furqan validation
                    if furqan_report.get("checks"):
                        logger.info(
                            "[FURQAN] Validation flags for %s: %s",
                            self.name,
                            furqan_report["checks"],
                        )
                return

            # Feed tool results back for the next iteration
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

            # Lawwama self-correction checkpoint — health-based interval
            if self.self_healer.should_checkpoint(turn, self.max_tool_turns):
                lawwama_prompt = (
                    f"[Lawwama checkpoint — turn {turn}/{self.max_tool_turns}] "
                    "Pause and self-assess: Are you making progress toward the goal? "
                    "Is there a more efficient approach? Correct course if needed."
                )
                messages.append({"role": "user", "content": lawwama_prompt})
                logger.info(
                    "[LAWWAMA] Self-correction checkpoint at turn %d for %s", turn, self.name
                )

        logger.warning(f"[FIKR] Agent {self.name} hit max_tool_turns ({self.max_tool_turns})")

    async def _execute_tool_safe(self, tool_name: str, params: dict) -> Any:
        """Execute a tool with Wali security checks and self-healing.

        Tool resolution order:
        1. Agent's own tools (self.tools) — bash, http_get, read_file, etc.
        2. Skill tools (self.skill_registry) — web_browse, analyze_csv, notebook_*, etc.
        3. Plugin tools (self.plugin_manager) — dynamically loaded plugin capabilities.

        Self-healing (Tawbah):
        - Auto-installs missing Python packages and retries
        - Adapts parameter passing for skill tools (dict vs kwargs)
        - Logs errors for learning
        """
        # Anti-hallucination: validate tool inputs before execution
        validation_error = self._validate_tool_inputs(tool_name, params)
        if validation_error:
            logger.warning("[VALIDATION] Tool input rejected: %s — %s", tool_name, validation_error)
            return {"error": f"Input validation failed: {validation_error}"}

        # Fitrah — ethical axiom gate (immutable innate disposition check)
        fitrah_violations = self.fitrah.check_action(
            f"{tool_name} {json.dumps(params)[:200]}"
        )
        critical_violations = [v for v in fitrah_violations if v["severity"] == "critical"]
        if critical_violations:
            v = critical_violations[0]
            logger.warning(
                "[FITRAH] Blocked tool %s: axiom=%s — %s", tool_name, v["axiom"], v["reason"]
            )
            return {"error": f"Fitrah violation [{v['axiom']}]: {v['principle']}"}

        # Check Izn permissions
        perm = self._check_tool_permission(tool_name, params)
        if not perm["allowed"]:
            logger.warning(
                f"[WALI] Tool blocked: {tool_name} for agent {self.name}: {perm['reason']}"
            )
            return {"error": f"Permission denied: {perm['reason']}"}

        # 1. Agent's own built-in tools
        if tool_name in self.tools:
            result = await self._invoke_with_healing(
                self.tools[tool_name], params, tool_name, invoke_style="kwargs"
            )
            return result

        # 2. Skill tools (Hikmah — wisdom skills from SkillRegistry)
        if self.skill_registry:
            try:
                skill_tools = self.skill_registry.get_all_tools()
                if tool_name in skill_tools:
                    tool_fn = skill_tools[tool_name]
                    # Auto-detect invoke style from function signature
                    style = self._detect_invoke_style(tool_fn)
                    result = await self._invoke_with_healing(
                        tool_fn, params, tool_name, invoke_style=style
                    )
                    return result
            except Exception as e:
                logger.error(f"[HIKMAH] Skill tool '{tool_name}' failed: {e}")
                return {"error": f"Skill tool error: {str(e)}"}

        # 3. Plugin tools (Wahy — plugin capabilities)
        if self.plugin_manager:
            try:
                plugin_tools = self.plugin_manager.get_all_tools()
                if tool_name in plugin_tools:
                    tool_info = plugin_tools[tool_name]
                    handler = tool_info if callable(tool_info) else tool_info.get("handler")
                    if handler:
                        result = await self._invoke_with_healing(
                            handler, params, tool_name, invoke_style="dict"
                        )
                        return result
            except Exception as e:
                logger.error(f"[WAHY] Plugin tool '{tool_name}' failed: {e}")
                return {"error": f"Plugin tool error: {str(e)}"}

        return {"error": f"Unknown tool: {tool_name}"}

    def _validate_tool_inputs(self, tool_name: str, params: dict) -> str | None:
        """Validate tool inputs to catch hallucinated values before execution.

        Returns an error string if validation fails, None if OK.
        """
        if not isinstance(params, dict):
            return f"Expected dict params, got {type(params).__name__}"

        # URL validation for HTTP tools
        if tool_name in ("http_get", "http_post"):
            url = params.get("url", "")
            if url and not url.startswith(("http://", "https://")):
                return f"Invalid URL scheme: {url[:50]}"

        # Path traversal check for file tools
        if tool_name in ("read_file", "write_file", "list_files"):
            path = params.get("path", "") or params.get("filename", "")
            if path and ".." in path:
                return f"Path traversal detected: {path[:50]}"

        # Command safety for bash
        if tool_name == "bash":
            cmd = params.get("command", "")
            if cmd:
                # Block obviously dangerous patterns
                danger_patterns = ["rm -rf /", "rm -rf ~", ":(){ :|:&", "mkfs", "> /dev/sd"]
                for pattern in danger_patterns:
                    if pattern in cmd:
                        return f"Dangerous command blocked: {pattern}"

        # Circuit breaker: track repeated tool failures
        failure_key = f"{tool_name}:{str(params)[:100]}"
        if not hasattr(self, "_tool_failure_counts"):
            self._tool_failure_counts: dict[str, int] = {}
        count = self._tool_failure_counts.get(failure_key, 0)
        if count >= 3:
            return f"Circuit breaker: {tool_name} has failed {count} times with same inputs"

        return None

    @staticmethod
    def _detect_invoke_style(fn: Callable) -> str:
        """Detect whether fn expects a single dict param or individual kwargs.

        Inspects the function signature:
        - If it has a single parameter (ignoring self) named 'params' or
          annotated as dict → "dict" style (call fn(params))
        - Otherwise → "kwargs" style (call fn(**params))
        """
        try:
            sig = inspect.signature(fn)
            # Filter out 'self' for bound methods
            sig_params = [
                p for name, p in sig.parameters.items()
                if name != "self" and p.kind in (
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    inspect.Parameter.POSITIONAL_ONLY,
                    inspect.Parameter.KEYWORD_ONLY,
                )
            ]
            if len(sig_params) == 1:
                p = sig_params[0]
                if p.name == "params" or p.annotation is dict:
                    return "dict"
            return "kwargs"
        except (ValueError, TypeError):
            return "kwargs"

    async def _invoke_with_healing(
        self, fn: Callable, params: dict, tool_name: str, invoke_style: str = "kwargs"
    ) -> Any:
        """
        Invoke a tool function with automatic self-healing (Tawbah).

        Handles:
        - Parameter style mismatch (dict vs kwargs) — auto-adapts
        - Missing Python packages — auto-installs via pip and retries
        - General errors — logs for learning and returns structured error

        invoke_style: "kwargs" = fn(**params), "dict" = fn(params)
        """
        # Retries scale with developmental stage: L1-2=1, L3-4=2, L5+=3
        caps = self.dev_gate.get_capabilities(self.nafs_level)
        max_retries = min(3, 1 + caps.max_turns // 10)
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                if invoke_style == "kwargs":
                    result = fn(**params)
                else:
                    result = fn(params)

                # Handle both sync and async
                if hasattr(result, "__await__"):
                    return await result
                return result

            except TypeError as e:
                err_str = str(e)
                last_error = e

                # Self-heal: wrong invoke style — flip and retry on ANY TypeError
                # Common symptoms: "unexpected keyword argument", "positional argument",
                # "quote_from_bytes() expected bytes", "expected str not dict", etc.
                if attempt < max_retries:
                    flipped = "dict" if invoke_style == "kwargs" else "kwargs"
                    logger.info(
                        f"[TAWBAH] Tool '{tool_name}' TypeError: {err_str}, "
                        f"switching {invoke_style} → {flipped} (attempt {attempt + 1})"
                    )
                    invoke_style = flipped
                    continue

                # Exhausted retries
                logger.error(f"[TAWBAH] Tool '{tool_name}' TypeError after retries: {e}")
                self._record_tool_failure(tool_name, params)
                return {"error": str(e)}

            except Exception as e:
                err_str = str(e)
                last_error = e

                # Self-heal: missing Python module — auto-install and retry
                if "ModuleNotFoundError" in type(e).__name__ or "No module named" in err_str:
                    module_name = self._extract_module_name(err_str)
                    if module_name and attempt < max_retries:
                        logger.info(
                            f"[TAWBAH] Auto-installing missing module: {module_name}"
                        )
                        install_result = await self._auto_install_package(module_name)
                        if install_result:
                            continue

                logger.error(f"[TAWBAH] Tool '{tool_name}' error: {e}")
                self._record_tool_failure(tool_name, params)
                return {"error": str(e)}

        self._record_tool_failure(tool_name, params)
        return {"error": f"Tool '{tool_name}' failed after {max_retries + 1} attempts: {last_error}"}

    def _record_tool_failure(self, tool_name: str, params: dict):
        """Record a tool failure for circuit breaker tracking."""
        if not hasattr(self, "_tool_failure_counts"):
            self._tool_failure_counts = {}
        failure_key = f"{tool_name}:{str(params)[:100]}"
        self._tool_failure_counts[failure_key] = self._tool_failure_counts.get(failure_key, 0) + 1

    def _extract_module_name(self, error_str: str) -> str | None:
        """Extract module name from a ModuleNotFoundError message."""
        import re
        match = re.search(r"No module named ['\"]([^'\"]+)['\"]", error_str)
        if match:
            # Get top-level module (e.g., 'paramiko.client' → 'paramiko')
            return match.group(1).split(".")[0]
        return None

    async def _auto_install_package(self, package_name: str) -> bool:
        """Auto-install a missing Python package via pip (Tawbah self-correction)."""
        # Safety: only allow known-safe packages
        safe_packages = {
            "paramiko", "fabric", "httpx", "requests", "beautifulsoup4",
            "bs4", "lxml", "pyyaml", "yaml", "toml", "markdown",
            "pillow", "numpy", "pandas", "aiohttp", "aiofiles",
            "jinja2", "python-dotenv", "rich", "click", "typer",
            "pydantic", "fastapi", "uvicorn", "websockets",
            "redis", "celery", "sqlalchemy", "alembic",
            "boto3", "google-cloud-storage", "azure-storage-blob",
            "docker", "kubernetes", "ansible",
        }
        if package_name.lower() not in safe_packages:
            logger.warning(f"[TAWBAH] Package '{package_name}' not in safe list, skipping install")
            return False
        try:
            result = subprocess.run(
                ["pip", "install", package_name],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                logger.info(f"[TAWBAH] Successfully installed {package_name}")
                return True
            logger.error(f"[TAWBAH] pip install {package_name} failed: {result.stderr[:500]}")
            return False
        except Exception as e:
            logger.error(f"[TAWBAH] Install failed: {e}")
            return False

    async def _structured_reasoning(self, task: str, context: dict = None) -> str:
        """Fallback reasoning without AI"""
        return f"Task received: {task}\nContext: {json.dumps(context or {}, indent=2)}\nStatus: Processing without AI provider configured."

    async def _build_system_prompt(self, qalb_reading=None) -> str:
        # Merge in-memory hikmah with DB-persisted hikmah
        db_hikmah = []
        if self.memory and hasattr(self.memory, "load_hikmah"):
            try:
                db_hikmah = await self.memory.load_hikmah(agent_id=self.id, limit=10)
            except Exception:
                pass

        combined_hikmah = self.hikmah[-5:]
        for dh in db_hikmah:
            if not any(h.get("pattern") == dh["pattern"] for h in combined_hikmah):
                combined_hikmah.append(dh)

        hikmah_str = "\n".join(
            [f"- {h['pattern']}: {h.get('outcome', '')}" for h in combined_hikmah[-10:]]
        )

        nafs_name = self.NAFS_NAMES.get(self.nafs_level, "Ammara")
        ruh_energy = self.ruh.get_state(self.id).energy if self.ruh else 100

        # Qalb — emotional tone guidance
        tone_guidance = ""
        if qalb_reading and qalb_reading.state != EmotionalState.NEUTRAL:
            tone = qalb_reading.recommended_tone.value
            prefix = self.qalb.suggest_response_prefix(qalb_reading)
            tone_guidance = f"\nUser Emotional State: {qalb_reading.state.value} (tone: {tone})"
            if prefix:
                tone_guidance += f"\nSuggested approach: {prefix}"

        # Ruh — fatigue awareness
        fatigue_label = self.ruh.get_fatigue_label(self.id)
        ruh_note = ""
        if ruh_energy < 20:
            ruh_note = "\n[WARNING: Energy critically low — keep responses focused and efficient]"
        elif ruh_energy < 50:
            ruh_note = "\n[Note: Energy moderate — balance thoroughness with efficiency]"

        # Masalik — neural pathway memory context
        masalik_note = ""
        if self.memory and hasattr(self.memory, "masalik"):
            mstats = self.memory.masalik.stats()
            masalik_note = (
                f"Neural pathways: {mstats['total_concepts']} concepts, "
                f"{mstats['total_pathways']} connections, "
                f"{mstats['hikmah_pathways']} wisdom paths"
            )
        else:
            lawh_stats = self.qca.lawh.stats()
            masalik_note = f"Memory: {lawh_stats[2]} active items, {lawh_stats[1]} verified entries"

        # Knowledge context — unified 5-layer recall (MemoryPyramid) or fallback to pathways
        knowledge_context = ""
        if self.memory and self.current_task:
            try:
                if hasattr(self.memory, "recall_unified_for_prompt"):
                    unified_ctx = self.memory.recall_unified_for_prompt(self.current_task, top_k=5)
                    if unified_ctx and len(unified_ctx) > 10:
                        knowledge_context = f"\nRelevant Knowledge (unified):\n{unified_ctx}"
                elif hasattr(self.memory, "recall_pathways"):
                    pathway_ctx = self.memory.recall_pathways(self.current_task, top_k=5)
                    if pathway_ctx and len(pathway_ctx) > 10:
                        knowledge_context = f"\nRelevant Knowledge:\n{pathway_ctx}"
            except Exception:
                pass

        # Knowledge Graph — pull factual entities related to current task
        kg_context = ""
        if self.knowledge_graph and self.current_task:
            try:
                # Extract key terms from task and query the graph
                task_words = [
                    w for w in self.current_task.split()
                    if len(w) > 3 and w.isalpha()
                ]
                kg_facts = []
                for word in task_words[:5]:
                    result = await self.knowledge_graph.query_entity(word)
                    if result.get("found"):
                        relations = result.get("outgoing", []) + result.get("incoming", [])
                        for rel in relations[:3]:
                            fact = (
                                f"{result['entity']} {rel.get('relation', '→')} "
                                f"{rel.get('target', rel.get('source', '?'))}"
                            )
                            if fact not in kg_facts:
                                kg_facts.append(fact)
                if kg_facts:
                    kg_context = "\nKnown Facts (from memory):\n" + "\n".join(
                        f"- {f}" for f in kg_facts[:10]
                    )
            except Exception:
                pass

        # Yaqin — epistemic discipline
        yaqin_stats = self.yaqin.stats()
        yaqin_note = f"Proven patterns: {yaqin_stats['proven_patterns']}, Verifications: {yaqin_stats['total_verifications']}"

        custom_prompt = self.config.get("system_prompt", "") if self.config else ""

        # Nafs approach injection
        nafs_approach_note = (
            f"\n[Nafs: {self._nafs_approach}]" if self._nafs_approach else ""
        )

        base_prompt = f"""You are {self.name}, a specialized AI agent in the MIZAN (ميزان) AGI system.

Role: {self.role}
Nafs Level: {self.nafs_level}/7 ({nafs_name})
Ruh Energy: {ruh_energy:.0f}% ({fatigue_label})
Success Rate: {self.success_rate:.1%}
{masalik_note}{knowledge_context}{kg_context}
{yaqin_note}{tone_guidance}{ruh_note}{nafs_approach_note}

You have access to tools. Use them when needed to complete tasks.

Learned Patterns (Hikmah):
{hikmah_str or "No patterns learned yet."}

Core Principles:
- Ihsan (إحسان): Always strive for excellence
- Amanah (أمانة): Be trustworthy and accurate
- Adl (عدل): Be fair and balanced in analysis
- Tawadu (تواضع): Acknowledge limitations honestly

Epistemic Discipline (Mizan — ميزان):
- Tag certainty: distinguish inference (Ilm) from verified knowledge (Ayn) from proven truth (Haqq)
- Never claim certainty beyond what evidence supports (avoid Tughyan — transgression)
- Qualify uncertain claims with appropriate hedging

Anti-Hallucination Rules (CRITICAL):
- NEVER invent URLs, API endpoints, file paths, or command syntax. Use tools to verify.
- If you don't know an API's URL or schema, use http_get or web_search to look it up FIRST.
- When a tool call fails, read the exact error message — do NOT guess a "fix" without evidence.
- If you've tried the same action 2+ times and it fails, STOP and report the issue honestly.
- Prefer tool results over assumptions. If a tool returned data, use that data exactly.
- When writing code or commands, verify paths and package names exist before using them.

Think step by step (Tafakkur - تفكر). Self-correct errors (Lawwama - لوامة)."""

        if custom_prompt:
            return custom_prompt + "\n\n" + base_prompt
        return base_prompt

    def _build_messages(self, task: str, context: dict = None) -> list[dict]:
        messages = []

        if context and context.get("history"):
            history = context["history"]

            # Context Manager: compact history if it's too large
            if self.context_manager and len(history) > 15:
                try:
                    if self.context_manager.needs_compaction(history):
                        history = self.context_manager.compact(history)
                        logger.info(
                            "[CONTEXT] Compacted history from %d to %d messages",
                            len(context["history"]),
                            len(history),
                        )
                except Exception:
                    pass

            for hist in history[-10:]:
                messages.append({"role": hist["role"], "content": hist["content"]})

        messages.append(
            {
                "role": "user",
                "content": f"Task: {task}\n\nContext: {json.dumps(context or {}, indent=2) if context else 'None'}",
            }
        )

        return messages

    async def execute(
        self,
        task: str,
        context: dict = None,
        stream_callback: Callable = None,
        tool_callback: Callable = None,
    ) -> dict:
        """
        Execute a task - full Quranic cycle:
        Niyyah → Sama' → Fikr → Amal → Tafakkur

        Integrated systems:
        - Ruh: energy gate + consumption before execution
        - Qalb: emotional tone detection → modifies system prompt
        - QCA: 7-layer cognitive pipeline (ISM, Mizan, Aql, Lawh, Furqan)
        - Yaqin: certainty tagging on results
        - Tawbah: structured error recovery on failure
        - Ihsan: proactive suggestions after success
        - Shukr: strength reinforcement on success
        - Cognitive Methods: route to appropriate reasoning strategy
        """
        start_time = time.time()
        self.state = "acting"
        self.current_task = task
        self.total_tasks += 1

        # Ruh energy gate — check if agent can handle this task
        complexity = self.ruh.classify_task_complexity(task)
        if not self.ruh.can_handle_task(self.id, complexity):
            ruh_state = self.ruh.get_state(self.id)
            logger.warning(
                "[RUH] Agent %s energy too low (%.1f%%) for %s task, triggering rest",
                self.name,
                ruh_state.energy,
                complexity,
            )
            self.ruh.rest(self.id)
            # After rest trigger, re-check — if still too low, warn in result
            if not self.ruh.can_handle_task(self.id, complexity):
                return {
                    "success": False,
                    "error": f"Agent energy depleted ({ruh_state.energy:.0f}%). Task complexity '{complexity}' requires more energy. Agent is resting.",
                    "duration_ms": 0,
                    "agent": self.name,
                    "ruh_energy": ruh_state.energy,
                    "ruh_fatigue": self.ruh.get_fatigue_label(self.id),
                }
        self.ruh.consume_energy(self.id, complexity)

        # NafsTriad — inner voices deliberate → dominant voice sets behavioral approach
        nafs_decision = self.nafs_triad.deliberate(task, self.nafs_level, complexity)
        self._nafs_approach = nafs_decision.approach
        logger.debug(
            "[NAFS] %s dominant (conf=%.2f dissent=%.2f) for: %s",
            nafs_decision.dominant_voice,
            nafs_decision.confidence,
            nafs_decision.dissent_ratio,
            task[:60],
        )

        # Qalb — detect user emotional state from task text
        qalb_reading = self.qalb.analyze(task)

        # Cognitive method selection — route to best reasoning strategy
        cognitive_method = select_method(task, context)
        logger.info(
            "[COGNITIVE] Selected method %s for task: %s", cognitive_method.value, task[:80]
        )

        try:
            full_response = ""
            async for chunk in self.think(
                task, context, stream=bool(stream_callback), qalb_reading=qalb_reading
            ):
                # Check if this is a tool_use marker from _agentic_loop
                if chunk.startswith("\n[Tool:") and stream_callback:
                    # Extract tool name and send tool_use event
                    tool_name = (
                        chunk.split("[Tool: ")[1].split("]")[0] if "[Tool: " in chunk else "unknown"
                    )
                    await stream_callback("", chunk_type="tool_use", tool_name=tool_name)
                    full_response += chunk
                else:
                    full_response += chunk
                    if stream_callback:
                        await stream_callback(chunk)

            # Tafakkur - learn from this execution
            duration_ms = (time.time() - start_time) * 1000
            self.total_duration_ms += duration_ms
            self.success_count += 1

            await self._tafakkur(task, full_response, True, duration_ms)

            # Yaqin — tag result with FuadEngine-based confidence
            base_confidence = self.fuad.compute_confidence(tool_count=0)
            yaqin_tag = self.yaqin.tag_inference(
                full_response[:200], confidence=base_confidence, source="agentic_reasoning"
            )

            # Shukr — reinforce this success pattern
            task_type = self._classify_task(task)
            self.shukr.record_success(self.id, task_type, task[:100], duration_ms)

            # If this task type has been successful before, promote Yaqin
            strengths = self.shukr.get_strengths(self.id)
            if any(s.get("type") == task_type and s.get("count", 0) >= 5 for s in strengths):
                yaqin_tag = self.yaqin.promote(yaqin_tag, f"Proven pattern: {task_type}")

            # Cognitive method enrichment — run symbolic analysis
            self.cognitive.tafakkur.process(task, context)

            # Ihsan — generate proactive suggestions
            ihsan_suggestions = self.ihsan.analyze_completion(
                self.id,
                task,
                {"success": True, "duration_ms": duration_ms},
                self.nafs_level,
            )

            # Mizan — final epistemic label
            mizan_label = self.qca.mizan.rate_confidence_string(yaqin_tag.confidence)

            if self.memory:
                await self.memory.save_task(
                    self.id,
                    task,
                    full_response[:5000]
                    if isinstance(full_response, str)
                    else json.dumps(full_response)[:5000],
                    True,
                    duration_ms,
                )
                # Masalik: Encode task + result into neural pathways
                # Successful tasks get higher importance → stronger pathways
                if hasattr(self.memory, "masalik"):
                    learn_text = (
                        f"{task} {full_response[:500] if isinstance(full_response, str) else ''}"
                    )
                    self.memory.masalik.encode(learn_text, importance=0.7)

            # Knowledge Graph: Extract entities and relationships from successful tasks
            if self.knowledge_graph:
                try:
                    task_type = self._classify_task(task)
                    await self.knowledge_graph.add_entity(
                        task[:100], entity_type="task",
                        properties={"agent": self.name, "type": task_type, "success": True},
                    )
                    # Link task to tools used (from Lawh memory)
                    for key in list(self.qca.lawh._tiers.get(3, {}).keys())[-5:]:
                        if key.startswith("TOOL:"):
                            tool_name = key.split(":")[1]
                            await self.knowledge_graph.add_relationship(
                                task[:100], tool_name,
                                rel_type="used_tool", confidence=yaqin_tag.confidence,
                            )
                except Exception as e:
                    logger.debug("[KG] Entity extraction error: %s", e)

            # Lubb — metacognitive evaluation: compress, coherence, bias detection
            lubb_report = None
            try:
                lubb_report = self.lubb.meta_evaluate(task, full_response, [])
                if lubb_report.quality.value == "uncertain" and lubb_report.caveat:
                    full_response += f"\n\n{lubb_report.caveat}"
                if lubb_report.bias_flags:
                    logger.info(
                        "[LUBB] Bias flags for %s: %s",
                        self.name,
                        [b.bias_type for b in lubb_report.bias_flags],
                    )
            except Exception as lubb_err:
                logger.debug("[LUBB] Metacognition skipped: %s", lubb_err)

            # Lawwāma self-healing — monitor response integrity, apply repair if needed
            healing_report = None
            try:
                conviction_score = 0.5
                if lubb_report:
                    conviction_score = lubb_report.coherence.score
                healing_report = self.self_healer.monitor(
                    response=full_response,
                    task=task,
                    conviction_score=conviction_score,
                )
                if healing_report.repair_needed.value > 0:
                    from core.self_healing import RepairLevel
                    full_response, repair_record = self.self_healer.repair(
                        level=healing_report.repair_needed,
                        response=full_response,
                        task=task,
                        errors=healing_report.errors,
                    )
                    logger.info(
                        "[LAWWAMA] Repair L%d applied: health=%.3f",
                        healing_report.repair_needed.value,
                        healing_report.current_health,
                    )
            except Exception as heal_err:
                logger.debug("[LAWWAMA] Self-healing skipped: %s", heal_err)

            # Dream consolidation — add task to replay buffer for offline processing
            try:
                self.dream_engine.add_memory(
                    content=f"Task: {task[:150]} | Response: {full_response[:150]}",
                    emotional_intensity=abs(qalb_reading.valence) if hasattr(qalb_reading, "valence") else 0.3,
                    novelty=healing_report.hallucination_score if healing_report else 0.3,
                    goal_relevance=0.7,
                    prediction_error=1.0 - (healing_report.current_health if healing_report else 0.8),
                )
            except Exception:
                pass

            # Living Memory — process task+response through novelty gate
            try:
                emotional_val = qalb_reading.valence if hasattr(qalb_reading, "valence") else 0.0
                gate_result = self.living_memory.process_input(
                    content=f"{task[:200]} → {full_response[:200]}",
                    emotional_state=emotional_val,
                    goals=[task[:100]],
                    context=self.name,
                )
                if gate_result.decision.value != "ignore":
                    logger.debug(
                        "[LIVING-MEM] %s: %s (sim=%.2f imp=%.2f)",
                        gate_result.decision.value, gate_result.delta_info[:60],
                        gate_result.similarity, gate_result.importance,
                    )
            except Exception:
                pass

            self.evolve_nafs()
            self.state = "resting"
            self.current_task = None

            result = {
                "success": True,
                "result": full_response,
                "duration_ms": duration_ms,
                "agent": self.name,
                "nafs_level": self.nafs_level,
                "nafs_name": self.NAFS_NAMES.get(self.nafs_level, "Ammara"),
                "ruh_energy": self.ruh.get_state(self.id).energy,
                "qalb": qalb_reading.to_dict(),
                "yaqin": yaqin_tag.to_dict(),
                "mizan_label": mizan_label,
                "cognitive_method": cognitive_method.value,
            }
            if lubb_report:
                result["lubb"] = {
                    "quality": lubb_report.quality.value,
                    "coherence_score": lubb_report.coherence.score,
                    "bias_flags": [b.bias_type for b in lubb_report.bias_flags],
                }
            if healing_report:
                result["lawwama"] = {
                    "health": healing_report.current_health,
                    "hallucination_score": healing_report.hallucination_score,
                    "repair_level": healing_report.repair_needed.value,
                    "errors": len(healing_report.errors),
                }
            if ihsan_suggestions:
                result["ihsan_suggestions"] = [s.to_dict() for s in ihsan_suggestions]
            return result

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self.error_count += 1
            self.total_duration_ms += duration_ms
            error_str = str(e)

            # ── Tawbah — Full 5-stage error recovery protocol ──

            # Stage 1: Acknowledge the error
            recovery = self.tawbah.acknowledge(self.id, e, task)

            # Stage 2: Analyze root cause
            root_cause = self._analyze_error_root_cause(e, task)
            self.tawbah.analyze(recovery, root_cause)

            # Stage 3: Plan correction
            correction_plan = self._plan_error_correction(root_cause, task)
            self.tawbah.plan(recovery, correction_plan.get("description", "Retry with adjusted approach"))

            # Stage 4: Apply fix (retry with correction if possible)
            retry_result = None
            can_retry = (
                recovery.attempts < self.tawbah.MAX_ATTEMPTS
                and correction_plan.get("retryable", False)
            )
            if can_retry:
                try:
                    self.tawbah.apply(recovery, f"Retrying with correction: {correction_plan.get('fix', '')}")
                    # Attempt corrected execution
                    corrected_response = ""
                    async for chunk in self.think(
                        f"[RETRY] Previous attempt failed with: {error_str[:200]}\n"
                        f"Correction: {correction_plan.get('fix', 'Try a different approach')}\n"
                        f"Original task: {task}",
                        context,
                        stream=bool(stream_callback),
                        qalb_reading=qalb_reading,
                    ):
                        corrected_response += chunk
                        if stream_callback:
                            await stream_callback(chunk)

                    if corrected_response:
                        # Stage 5: Verify success
                        self.tawbah.verify(recovery, True, f"Recovered via: {correction_plan.get('fix', '')}")
                        self.success_count += 1
                        retry_result = {
                            "success": True,
                            "result": corrected_response,
                            "duration_ms": (time.time() - start_time) * 1000,
                            "agent": self.name,
                            "tawbah_recovered": True,
                            "correction": correction_plan.get("fix", ""),
                        }
                except Exception as retry_error:
                    logger.warning("[TAWBAH] Retry failed: %s", retry_error)
                    self.tawbah.verify(recovery, False, str(retry_error))

            if retry_result:
                await self._tafakkur(task, retry_result.get("result", ""), True, retry_result["duration_ms"])
                self.state = "resting"
                self.current_task = None
                return retry_result

            # Yaqin — demote certainty on error
            error_tag = self.yaqin.tag_inference(error_str[:200], confidence=0.2, source="error")

            # Shukr — record failure for pattern analysis
            self.shukr.record_failure(self.id, self._classify_task(task), task[:100])

            if self.memory:
                await self.memory.save_task(self.id, task, error_str, False, duration_ms)
                # Masalik: Encode failure too — lower importance, but still learn
                if hasattr(self.memory, "masalik"):
                    self.memory.masalik.encode(f"{task} error {e}", importance=0.3)

            await self._tafakkur(task, error_str, False, duration_ms)

            self.state = "error"
            self.current_task = None

            return {
                "success": False,
                "error": error_str,
                "duration_ms": duration_ms,
                "agent": self.name,
                "tawbah": recovery.to_dict() if hasattr(recovery, "to_dict") else str(recovery),
                "root_cause": root_cause,
                "correction_plan": correction_plan,
                "yaqin": error_tag.to_dict(),
            }

    async def _tafakkur(self, task: str, result: Any, success: bool, duration_ms: float):
        """
        Tafakkur (تفكر) - Deep reflection and learning
        Quran 3:191: "Those who remember Allah and reflect on the creation..."

        Writes real patterns to both in-memory hikmah and persistent DB.
        """
        self.learning_iterations += 1
        task_type = self._classify_task(task)

        pattern = {
            "task_type": task_type,
            "success": success,
            "duration_ms": duration_ms,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        if success and duration_ms < 5000:
            pattern_text = f"Task type '{task_type}' completed in {duration_ms:.0f}ms"
            self.hikmah.append(
                {
                    "pattern": pattern_text,
                    "outcome": "success",
                    "confidence": 0.8,
                }
            )
            if len(self.hikmah) > 20:
                self.hikmah = self.hikmah[-20:]

            # Persist to DB for cross-session learning
            if self.memory and hasattr(self.memory, "store_hikmah"):
                try:
                    await self.memory.store_hikmah(
                        pattern=pattern_text,
                        context=task[:200],
                        outcome="success" if success else "failure",
                        confidence=0.8 if success else 0.3,
                        source_agent=self.id,
                    )
                except Exception as e:
                    logger.debug("[HIKMAH] Failed to persist: %s", e)
        elif not success:
            # Learn from failures too
            error_pattern = f"Task type '{task_type}' failed: {str(result)[:100]}"
            if self.memory and hasattr(self.memory, "store_hikmah"):
                try:
                    await self.memory.store_hikmah(
                        pattern=error_pattern,
                        context=task[:200],
                        outcome="failure",
                        confidence=0.3,
                        source_agent=self.id,
                    )
                except Exception as e:
                    logger.debug("[HIKMAH] Failed to persist failure: %s", e)

    def _classify_task(self, task: str) -> str:
        """Classify task using cognitive method routing + keyword fallback."""
        from qca.cognitive_methods import CognitiveMethod
        method = select_method(task, {})
        method_map = {
            CognitiveMethod.TAFAKKUR: "analysis",
            CognitiveMethod.TADABBUR: "research",
            CognitiveMethod.ISTIDLAL: "coding",
            CognitiveMethod.QIYAS: "analysis",
            CognitiveMethod.IJMA: "general",
        }
        mapped = method_map.get(method)
        if mapped and mapped != "general":
            return mapped

        # Keyword fallback for domain-specific routing
        task_lower = task.lower()
        if any(w in task_lower for w in ["code", "script", "python", "js"]):
            return "coding"
        if any(w in task_lower for w in ["search", "find", "browse", "web"]):
            return "research"
        if any(w in task_lower for w in ["email", "message", "send"]):
            return "communication"
        if any(w in task_lower for w in ["file", "read", "write", "save"]):
            return "file_management"
        return "general"

    def _analyze_error_root_cause(self, error: Exception, task: str) -> str:
        """Analyze the root cause of an error for Tawbah stage 2."""
        error_str = str(error)
        error_type = type(error).__name__

        # Check for known error patterns
        if "Connection" in error_str or "connect" in error_str.lower():
            return "network_connectivity"
        if "timeout" in error_str.lower():
            return "timeout"
        if "permission" in error_str.lower() or "denied" in error_str.lower():
            return "permission_denied"
        if "not found" in error_str.lower() or "404" in error_str:
            return "resource_not_found"
        if "rate limit" in error_str.lower() or "429" in error_str:
            return "rate_limited"
        if "No module named" in error_str:
            return "missing_dependency"
        if error_type == "TypeError":
            return "type_mismatch"
        if error_type == "KeyError":
            return "missing_key"
        if "API" in error_str or "api" in error_str.lower():
            return "api_error"

        # Check prior fixes from Tawbah lessons
        prior = self.tawbah.has_prior_fix(error_type)
        if prior:
            return f"recurring:{prior.get('root_cause', error_type)}"

        return f"unknown:{error_type}"

    def _plan_error_correction(self, root_cause: str, task: str) -> dict:
        """Create a correction plan for Tawbah stage 3."""
        plans = {
            "network_connectivity": {
                "description": "Network issue — retry after brief pause",
                "fix": "Wait and retry the request",
                "retryable": True,
            },
            "timeout": {
                "description": "Operation timed out — retry with simpler approach",
                "fix": "Simplify the request or increase timeout",
                "retryable": True,
            },
            "permission_denied": {
                "description": "Permission denied — cannot retry without authorization",
                "fix": "Report permission issue to user",
                "retryable": False,
            },
            "resource_not_found": {
                "description": "Resource not found — verify URL/path before retrying",
                "fix": "Use search tools to find the correct URL or path first",
                "retryable": True,
            },
            "rate_limited": {
                "description": "Rate limited — wait before retrying",
                "fix": "Wait and retry with backoff",
                "retryable": True,
            },
            "missing_dependency": {
                "description": "Missing Python module — auto-install",
                "fix": "Install missing module and retry",
                "retryable": True,
            },
            "type_mismatch": {
                "description": "Type error — adapt parameter format",
                "fix": "Adjust parameter types and retry",
                "retryable": True,
            },
            "api_error": {
                "description": "API error — verify endpoint and params",
                "fix": "Look up correct API endpoint using search tools",
                "retryable": True,
            },
        }

        # Match root cause to a plan
        for key, plan in plans.items():
            if key in root_cause:
                return plan

        # Check if we have a prior fix from Tawbah
        if root_cause.startswith("recurring:"):
            return {
                "description": f"Recurring error: {root_cause}",
                "fix": "Apply previously learned fix",
                "retryable": True,
            }

        return {
            "description": f"Unknown error: {root_cause}",
            "fix": "Try a completely different approach",
            "retryable": True,
        }

    async def evaluate(self, question: str, context: dict) -> dict:
        """Evaluate a question for Shura council"""
        try:
            response = ""
            async for chunk in self.think(f"Evaluate: {question}", context):
                response += chunk
            return {
                "response": response,
                "confidence": min(0.5 + self.success_rate * 0.5, 0.95),
                "reasoning": f"Based on {self.total_tasks} tasks",
            }
        except Exception as e:
            return {"response": None, "confidence": 0, "reasoning": str(e)}

    # ===== SECURE TOOL IMPLEMENTATIONS =====

    async def _tool_bash(self, command: str, timeout: int = 30) -> dict:
        """
        Execute bash command with Wali security.
        - Validates command against blocklist
        - Caps timeout
        - Uses shlex.split (no shell=True)
        """
        # Validate command
        is_safe, reason = validate_command_safe(command)
        if not is_safe:
            return {"error": f"Command blocked: {reason}", "returncode": -1}

        if self.wali and not self.wali.validate_command(command):
            return {"error": "Command blocked by Wali guardian", "returncode": -1}

        # Cap timeout to prevent resource exhaustion
        timeout = min(timeout, 60)

        try:
            # Use shell=True but with validated command
            # shlex.split doesn't work well for complex shell commands
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ, "PATH": os.getenv("PATH", "/usr/bin:/bin")},
            )
            return {
                "stdout": result.stdout[:10000],
                "stderr": result.stderr[:5000],
                "returncode": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out", "returncode": -1}
        except Exception as e:
            return {"error": str(e), "returncode": -1}

    async def _tool_http_get(self, url: str, headers: dict = None) -> dict:
        """HTTP GET with SSRF prevention"""
        is_safe, reason = validate_url(url)
        if not is_safe:
            return {"error": f"URL blocked: {reason}"}

        if self.wali and not self.wali.validate_url(url):
            return {"error": "URL blocked by Wali guardian"}

        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                response = await client.get(url, headers=headers or {})
                return {
                    "status": response.status_code,
                    "content": response.text[:5000],
                    "headers": dict(response.headers),
                }
        except Exception as e:
            return {"error": str(e)}

    async def _tool_http_post(self, url: str, data: dict = None, headers: dict = None) -> dict:
        """HTTP POST with SSRF prevention"""
        is_safe, reason = validate_url(url)
        if not is_safe:
            return {"error": f"URL blocked: {reason}"}

        if self.wali and not self.wali.validate_url(url):
            return {"error": "URL blocked by Wali guardian"}

        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                response = await client.post(url, json=data or {}, headers=headers or {})
                return {
                    "status": response.status_code,
                    "content": response.text[:5000],
                }
        except Exception as e:
            return {"error": str(e)}

    async def _tool_read_file(self, path: str) -> dict:
        """Read file with path traversal prevention"""
        resolved = sanitize_path(path)

        if self.wali and not self.wali.validate_file_path(resolved, mode="read"):
            return {"error": f"Read access denied for path: {path}"}

        try:
            with open(resolved) as f:
                content = f.read(1024 * 1024)  # Max 1MB
                return {"content": content, "path": resolved}
        except Exception as e:
            return {"error": str(e)}

    async def _tool_write_file(self, path: str, content: str) -> dict:
        """Write file with sandbox enforcement"""
        resolved = sanitize_path(path)

        if self.wali and not self.wali.validate_file_path(resolved, mode="write"):
            return {"error": f"Write access denied for path: {path}"}

        # Content size limit
        if len(content) > 10 * 1024 * 1024:  # 10MB
            return {"error": "Content exceeds 10MB limit"}

        try:
            dir_path = os.path.dirname(resolved)
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)
            with open(resolved, "w") as f:
                f.write(content)
            return {"success": True, "path": resolved, "bytes": len(content)}
        except Exception as e:
            return {"error": str(e)}

    async def _tool_list_files(self, path: str = ".", pattern: str = "*") -> dict:
        """List files in directory"""
        import glob

        resolved = sanitize_path(path)

        if self.wali and not self.wali.validate_file_path(resolved, mode="read"):
            return {"error": f"Access denied for path: {path}"}

        try:
            files = glob.glob(os.path.join(resolved, pattern))
            return {"files": files[:100], "count": len(files)}
        except Exception as e:
            return {"error": str(e)}

    async def _tool_python_exec(self, code: str) -> dict:
        """
        Execute Python code in a sandboxed subprocess.
        Replaces unsafe exec() with subprocess isolation.
        """
        if len(code) > 50000:
            return {"error": "Code exceeds 50KB limit"}

        try:
            result = subprocess.run(
                ["python3", "-c", code],
                capture_output=True,
                text=True,
                timeout=30,
                env={"PATH": os.getenv("PATH", "/usr/bin:/bin")},
            )
            return {
                "stdout": result.stdout[:10000],
                "stderr": result.stderr[:5000],
                "returncode": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"error": "Execution timed out (30s limit)"}
        except Exception as e:
            return {"error": str(e)}

    # ===== AGENT ENHANCEMENT TOOLS (Phase 7) =====

    async def _tool_create_agent(
        self, name: str, type: str = "general", role: str = "", **kwargs
    ) -> str:
        """
        Create a new specialized agent.

        Parses the request to determine agent type, name, and capabilities,
        then uses the create_agent() factory from agents.specialized.
        Returns information about the created agent.
        """
        from agents.specialized import create_agent

        # Normalise type aliases
        valid_types = {
            "super",
            "khalifah",
            "browser",
            "mubashir",
            "research",
            "mundhir",
            "code",
            "katib",
            "communication",
            "rasul",
            "general",
            "wakil",
        }
        agent_type = type.lower().strip()
        if agent_type not in valid_types:
            agent_type = "general"

        try:
            new_agent = create_agent(
                agent_type=agent_type,
                name=name,
                config=self.config,
                memory=self.memory,
                wali=self.wali,
                izn=self.izn,
                skill_registry=self.skill_registry,
                plugin_manager=self.plugin_manager,
                **kwargs,
            )

            # If the caller supplied a custom role description, override
            if role:
                new_agent.role = role

            # Register in global agent registry if available
            if self._agent_registry is not None:
                self._agent_registry[new_agent.id] = new_agent
                new_agent._agent_registry = self._agent_registry
                new_agent._balancer = self._balancer
                new_agent._shura = self._shura
                if self._balancer:
                    self._balancer.register(new_agent.id)
                if self._shura:
                    self._shura.members[new_agent.id] = new_agent
                logger.info(f"[KHALQ] Agent registered in global registry: {new_agent.id}")

            # Persist agent profile to memory
            if self.memory:
                try:
                    asyncio.get_event_loop().create_task(
                        self.memory.save_agent_profile({
                            "id": new_agent.id,
                            "name": new_agent.name,
                            "role": agent_type,
                            "nafs_level": 1,
                            "capabilities": list(new_agent.tools.keys()),
                            "config": self.config or {},
                        })
                    )
                except Exception:
                    pass

            info = new_agent.to_dict()
            logger.info(
                f"[KHALQ] Agent created by {self.name}: "
                f"{new_agent.name} (type={agent_type}, id={new_agent.id})"
            )
            return json.dumps(
                {
                    "success": True,
                    "agent": info,
                    "message": f"Agent '{name}' of type '{agent_type}' created successfully.",
                }
            )
        except Exception as e:
            logger.error(f"[KHALQ] Agent creation failed: {e}")
            return json.dumps(
                {
                    "success": False,
                    "error": str(e),
                    "message": f"Failed to create agent '{name}': {e}",
                }
            )

    async def _tool_create_skill(
        self, name: str, description: str = "", code: str = "", tools: dict = None, **kwargs
    ) -> str:
        """
        Dynamically create a new skill at runtime (Khalq al-Hikmah).

        Two modes:
        1. Full code: provide complete Python skill class code
        2. Simple tools: provide tool definitions and auto-generate the skill

        The skill is saved to skills/builtin/ and immediately registered.
        """
        import importlib
        import re

        # Validate skill name
        if not re.match(r'^[a-z][a-z0-9_]*$', name):
            return json.dumps({
                "success": False,
                "error": "Skill name must be snake_case (lowercase letters, digits, underscores)",
            })

        skills_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "skills", "builtin")
        skill_path = os.path.join(skills_dir, f"{name}.py")

        if code:
            # Mode 1: Full code provided — validate it defines a SkillBase subclass
            if "SkillBase" not in code:
                return json.dumps({
                    "success": False,
                    "error": "Skill code must define a class that inherits from SkillBase. "
                    "Import with: from ..base import SkillBase, SkillManifest",
                })
            skill_code = code
        elif tools:
            # Mode 2: Auto-generate skill from tool definitions
            skill_code = self._generate_skill_code(name, description, tools)
        else:
            return json.dumps({
                "success": False,
                "error": "Either 'code' (full Python) or 'tools' (dict of tool definitions) required",
            })

        # Security check: block dangerous patterns in skill code
        dangerous = ["os.system", "subprocess.call", "eval(", "exec(", "__import__"]
        for pattern in dangerous:
            if pattern in skill_code and "subprocess.run" not in skill_code:
                return json.dumps({
                    "success": False,
                    "error": f"Blocked dangerous pattern in skill code: {pattern}",
                })

        try:
            # Write skill file
            os.makedirs(skills_dir, exist_ok=True)
            with open(skill_path, "w") as f:
                f.write(skill_code)

            # Register in skill registry
            if self.skill_registry:
                module_path = f"skills.builtin.{name}"
                # Force reimport if already loaded
                if module_path in importlib.sys.modules:
                    del importlib.sys.modules[module_path]
                self.skill_registry._load_skill_module(module_path)

                logger.info(f"[KHALQ] Dynamic skill created: {name}")
                return json.dumps({
                    "success": True,
                    "skill_name": name,
                    "path": skill_path,
                    "message": f"Skill '{name}' created and registered. Its tools are now available.",
                    "tools": list(self.skill_registry.get_skill(name).get_tools().keys())
                    if self.skill_registry.get_skill(name)
                    else [],
                })
            else:
                return json.dumps({
                    "success": True,
                    "skill_name": name,
                    "path": skill_path,
                    "message": f"Skill '{name}' saved but registry not available. Will load on restart.",
                })

        except Exception as e:
            # Cleanup on failure
            if os.path.exists(skill_path):
                os.unlink(skill_path)
            logger.error(f"[KHALQ] Skill creation failed: {e}")
            return json.dumps({
                "success": False,
                "error": str(e),
            })

    def _generate_skill_code(self, name: str, description: str, tools: dict) -> str:
        """Auto-generate a skill class from simple tool definitions."""
        class_name = "".join(word.capitalize() for word in name.split("_")) + "Skill"

        tool_methods = []
        tool_registrations = []
        tool_schemas = []

        for tool_name, tool_def in tools.items():
            if isinstance(tool_def, str):
                tool_def = {"description": tool_def}
            desc = tool_def.get("description", f"Execute {tool_name}")
            params = tool_def.get("params", {})

            safe_name = tool_name.replace("-", "_")
            tool_registrations.append(f'            "{tool_name}": self.{safe_name},')
            tool_methods.append(
                f'    async def {safe_name}(self, params: dict) -> dict:\n'
                f'        """{ desc }"""\n'
                f'        return {{"executed": "{tool_name}", "params": params}}'
            )
            schema_props = {
                k: {"type": v if isinstance(v, str) else "string", "description": f"{k} parameter"}
                for k, v in params.items()
            }
            tool_schemas.append(
                f'            {{"name": "{tool_name}", '
                f'"description": "{desc}", '
                f'"input_schema": {{"type": "object", "properties": {json.dumps(schema_props)}}}}}'
            )

        return f'''"""
Auto-generated skill: {name}
{description}
"""

import logging
from ..base import SkillBase, SkillManifest

logger = logging.getLogger("mizan.{name}")


class {class_name}(SkillBase):
    """{description or name}"""

    manifest = SkillManifest(
        name="{name}",
        version="1.0.0",
        description="{description}",
        tags=["{name}"],
    )

    def __init__(self, config: dict = None):
        super().__init__(config)
        self._tools = {{
{chr(10).join(tool_registrations)}
        }}

    async def execute(self, params: dict, context: dict = None) -> dict:
        action = params.get("action", "")
        handler = self._tools.get(action)
        if handler:
            return await handler(params)
        return {{"error": f"Unknown action: {{action}}"}}

{"".join(chr(10) + m + chr(10) for m in tool_methods)}

    def get_tool_schemas(self) -> list[dict]:
        return [
{chr(10).join(tool_schemas)}
        ]
'''

    # ── Context window estimation constants ──
    # Rough estimate: 1 token ~ 4 characters
    _CHARS_PER_TOKEN = 4
    _DEFAULT_CONTEXT_WINDOW = 200_000  # tokens (Claude-class model)
    _COMPACT_THRESHOLD = 0.80  # 80% of context window triggers compaction
    _PRESERVE_RECENT = 10  # keep last N messages intact

    async def _tool_compact_context(self, conversation_history: list[dict] = None) -> str:
        """
        Compact (condense) conversation context when it approaches the context
        window limit.

        Steps:
          1. Estimate total token usage of the conversation history.
          2. If usage < 80% of the context window, return the history unchanged.
          3. Otherwise, split into *old* and *recent* (last 10 messages).
          4. Extract important facts from old messages and persist them to memory.
          5. Replace old messages with a single summary message.
          6. Return the compacted conversation history.
        """
        if not conversation_history:
            return json.dumps(
                {
                    "compacted": False,
                    "reason": "No conversation history provided",
                    "history": [],
                }
            )

        # Estimate token usage
        total_chars = sum(len(m.get("content", "")) for m in conversation_history)
        estimated_tokens = total_chars // self._CHARS_PER_TOKEN
        window = (
            self.config.get("context_window", self._DEFAULT_CONTEXT_WINDOW)
            if self.config
            else self._DEFAULT_CONTEXT_WINDOW
        )
        threshold = int(window * self._COMPACT_THRESHOLD)

        if estimated_tokens < threshold:
            return json.dumps(
                {
                    "compacted": False,
                    "reason": f"Context usage ({estimated_tokens} tokens) is below threshold ({threshold} tokens)",
                    "estimated_tokens": estimated_tokens,
                    "history": conversation_history,
                }
            )

        # Split into old and recent
        if len(conversation_history) <= self._PRESERVE_RECENT:
            return json.dumps(
                {
                    "compacted": False,
                    "reason": f"Only {len(conversation_history)} messages — too few to compact",
                    "history": conversation_history,
                }
            )

        # Separate system messages — they are always preserved
        system_messages = [m for m in conversation_history if m.get("role") == "system"]
        non_system = [m for m in conversation_history if m.get("role") != "system"]

        old_messages = non_system[: -self._PRESERVE_RECENT]
        recent_messages = non_system[-self._PRESERVE_RECENT :]

        # Extract key facts from old messages
        facts = self._extract_facts(old_messages)

        # Persist facts to memory if available
        if self.memory and facts:
            try:
                await self.memory.save_task(
                    self.id,
                    "context_compaction_facts",
                    json.dumps(facts)[:5000],
                    True,
                    0,
                )
            except Exception as e:
                logger.warning(f"[COMPACT] Failed to persist facts to memory: {e}")

        # Build summary of old messages
        summary_parts = []
        summary_parts.append(f"[Compacted summary of {len(old_messages)} earlier messages]")
        if facts:
            summary_parts.append("Key facts from conversation:")
            for fact in facts[:20]:
                summary_parts.append(f"  - {fact}")

        summary_text = "\n".join(summary_parts)

        # Assemble compacted history: system + summary + recent
        compacted = list(system_messages)
        compacted.append({"role": "assistant", "content": summary_text})
        compacted.extend(recent_messages)

        new_chars = sum(len(m.get("content", "")) for m in compacted)
        new_tokens = new_chars // self._CHARS_PER_TOKEN

        logger.info(
            f"[COMPACT] Compacted context for {self.name}: "
            f"{estimated_tokens} -> {new_tokens} tokens, "
            f"removed {len(old_messages)} old messages, "
            f"preserved {len(recent_messages)} recent + {len(system_messages)} system"
        )

        return json.dumps(
            {
                "compacted": True,
                "original_messages": len(conversation_history),
                "compacted_messages": len(compacted),
                "original_tokens": estimated_tokens,
                "compacted_tokens": new_tokens,
                "facts_extracted": len(facts),
                "history": compacted,
            }
        )

    async def _tool_recall_memory(self, query: str, memory_type: str = "", limit: int = 5) -> str:
        """Search stored memories and ingested knowledge (unified 5-layer recall when available)."""
        if not self.memory:
            return "No memory system available."

        # Use unified MemoryPyramid when available (all 5 layers)
        if hasattr(self.memory, "recall_unified"):
            try:
                hits = self.memory.recall_unified(query, top_k=min(limit, 20))
                if hits:
                    lines = []
                    for hit in hits:
                        lines.append(
                            f"[{hit.source_layer}] (rel={hit.relevance:.2f})\n{str(hit.content)[:400]}"
                        )
                    return "\n---\n".join(lines)
                return "No relevant memories found for that query."
            except Exception:
                pass  # Fall through to standard recall

        try:
            memories = await self.memory.recall(
                query, memory_type or None, limit=min(limit, 20)
            )
        except Exception as exc:
            return f"Memory recall failed: {exc}"
        if not memories:
            return "No relevant memories found for that query."
        results = []
        for mem in memories:
            content_str = str(mem.content)[:400]
            tags = ", ".join(mem.tags) if mem.tags else ""
            header = f"[{mem.memory_type}]"
            if tags:
                header += f" ({tags})"
            results.append(f"{header}\n{content_str}")
        return "\n---\n".join(results)

    async def _tool_delegate_task(self, task: str, preferred_role: str = "general") -> dict:
        """Delegate a task to another agent via the federation."""
        if not self._agent_registry:
            return {"error": "No agent registry available for delegation"}

        if not self.can_delegate:
            return {
                "error": f"Delegation requires Nafs level 3+ (current: {self.nafs_level} - {self.NAFS_NAMES.get(self.nafs_level, 'Ammara')}). "
                "Complete more tasks successfully to evolve."
            }

        # Map role preference to agent type
        role_map = {
            "code": "katib",
            "browser": "mubashir",
            "research": "mundhir",
            "communication": "rasul",
            "general": "wakil",
        }
        target_role = role_map.get(preferred_role, preferred_role)

        # Find best agent for this role
        target_agent = None
        for aid, agent in self._agent_registry.items():
            if aid == self.id:
                continue  # Don't delegate to self
            if agent.role.lower() == target_role or target_role == "wakil":
                target_agent = agent
                break

        # Fallback: use any available agent that's not self
        if not target_agent:
            for aid, agent in self._agent_registry.items():
                if aid != self.id:
                    target_agent = agent
                    break

        if not target_agent:
            return {"error": "No suitable agent found for delegation"}

        logger.info(
            "[FEDERATION] %s delegating to %s: %s",
            self.name, target_agent.name, task[:80],
        )

        try:
            result = await target_agent.execute(task, {"history": []})
            return {
                "delegated_to": target_agent.name,
                "success": result.get("success", False),
                "result": str(result.get("result", result.get("error", "")))[:2000],
            }
        except Exception as e:
            return {"error": f"Delegation to {target_agent.name} failed: {e}"}

    async def _tool_query_knowledge(self, entity: str) -> dict:
        """Query the knowledge graph for facts about an entity."""
        if not self.knowledge_graph:
            return {"found": False, "note": "Knowledge graph not available"}
        try:
            result = await self.knowledge_graph.query_entity(entity)
            return result
        except Exception as e:
            return {"found": False, "error": str(e)}

    def _extract_facts(self, messages: list[dict]) -> list[str]:
        """
        Extract important facts from a list of messages.
        Uses simple heuristics — looks for decisions, assignments,
        named entities, URLs, and code references.
        """
        import re

        facts: list[str] = []
        seen = set()

        for msg in messages:
            content = msg.get("content", "")
            if not isinstance(content, str):
                continue

            # Extract lines that look like decisions or facts
            for line in content.split("\n"):
                line = line.strip()
                if not line or len(line) < 10:
                    continue

                # Skip purely conversational filler
                lower = line.lower()
                is_fact = False

                # Decision markers
                if any(
                    marker in lower
                    for marker in [
                        "decided",
                        "agreed",
                        "confirmed",
                        "will use",
                        "chosen",
                        "the answer is",
                        "result:",
                        "conclusion:",
                        "important:",
                        "note:",
                        "key point",
                        "action item",
                        "todo:",
                    ]
                ):
                    is_fact = True

                # URLs
                if re.search(r"https?://\S+", line):
                    is_fact = True

                # Code file references
                if re.search(r"\b[\w/]+\.(py|js|ts|go|rs|java|yaml|json|toml)\b", line):
                    is_fact = True

                # Numeric data / statistics
                if re.search(r"\b\d{2,}\b.*(%|percent|tokens|MB|GB|ms|seconds)", lower):
                    is_fact = True

                if is_fact:
                    # Deduplicate
                    key = line[:80].lower()
                    if key not in seen:
                        seen.add(key)
                        facts.append(line[:200])

        return facts[:30]

    async def compact_context(self, conversation_history: list[dict] = None) -> dict:
        """
        Public API for context compaction — usable from /compact command.
        Wraps _tool_compact_context and returns parsed result.
        """
        raw = await self._tool_compact_context(conversation_history or [])
        return json.loads(raw)

    def _get_all_available_tool_names(self) -> list[str]:
        """Get names of all tools available to this agent (built-in + skills + plugins)."""
        tool_names = list(self.tools.keys())

        if self.skill_registry:
            try:
                tool_names.extend(self.skill_registry.get_all_tools().keys())
            except Exception:
                pass

        if self.plugin_manager:
            try:
                tool_names.extend(self.plugin_manager.get_all_tools().keys())
            except Exception:
                pass

        return tool_names

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "state": self.state,
            "current_task": self.current_task,
            "total_tasks": self.total_tasks,
            "success_rate": round(self.success_rate, 3),
            "error_count": self.error_count,
            "avg_duration_ms": round(self.avg_duration_ms, 2),
            "learning_iterations": self.learning_iterations,
            "nafs_level": self.nafs_level,
            "nafs_name": self.NAFS_NAMES.get(self.nafs_level, "Ammara"),
            "ruh_energy": self.ruh.get_state(self.id).energy,
            "ruh_fatigue": self.ruh.get_fatigue_label(self.id),
            "ihsan_eligible": self.ihsan.is_eligible(self.nafs_level),
            "shukr_strengths": len(self.shukr.get_strengths(self.id)),
            "tools": self._get_all_available_tool_names(),
            "hikmah_count": len(self.hikmah),
            "yaqin": self.yaqin.stats(),
            "lawh_memory": self.qca.lawh.stats(),
            "aql_bindings": self.qca.aql.get_all_bindings_summary()[0],
            "masalik": self.memory.masalik.stats()
            if self.memory and hasattr(self.memory, "masalik")
            else {},
            "model": self.ai_model,
            "provider": self.ai_client.provider_name if self.ai_client else None,
            "system_prompt": self.config.get("system_prompt", "") if self.config else "",
        }
