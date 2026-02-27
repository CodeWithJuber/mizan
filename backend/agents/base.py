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
import json
import time
import uuid
import os
import shlex
import subprocess
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable, AsyncGenerator
from abc import ABC
from dataclasses import dataclass, field
import httpx

from providers import create_provider, get_default_model
from security.validation import (
    sanitize_command, validate_command_safe, sanitize_path,
    validate_url, validate_package_name,
)

# Core Quranic systems integration
from core.ruh_engine import RuhEngine
from core.tawbah import TawbahProtocol
from core.ihsan import IhsanMode
from core.sabr import SabrEngine
from core.shukr import ShukrSystem
from core.qalb import QalbEngine, EmotionalState, ToneStyle
from qca.yaqin_engine import YaqinEngine
from qca.engine import QCAEngine
from qca.cognitive_methods import select_method, IjmaEngine, CognitiveMethod

logger = logging.getLogger("mizan.agent")


class BaseAgent(ABC):
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
    TOOL_SCHEMAS: List[Dict] = []

    def __init__(self, agent_id: str = None, name: str = "", role: str = "wakil",
                 config: Dict = None, memory=None, wali=None, izn=None,
                 skill_registry=None, plugin_manager=None):
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

        # State tracking
        self.state = "resting"
        self.current_task: Optional[str] = None
        self.task_queue: asyncio.Queue = asyncio.Queue()

        # Performance metrics (Mizan - balance)
        self.total_tasks = 0
        self.success_count = 0
        self.error_count = 0
        self.total_duration_ms = 0.0
        self.learning_iterations = 0
        self.nafs_level = 1  # 1-7 (Ammara → Kamila)

        # Tools registry
        self.tools: Dict[str, Callable] = {}
        self._register_base_tools()

        # Learning store (Hikmah)
        self.hikmah: List[Dict] = []

        # ── Core Quranic systems ──
        self.ruh = RuhEngine()              # Energy/vitality management
        self.tawbah = TawbahProtocol()      # Error recovery protocol
        self.ihsan = IhsanMode()            # Proactive excellence
        self.sabr = SabrEngine()            # Long-running task patience
        self.shukr = ShukrSystem()          # Strength reinforcement
        self.qalb = QalbEngine()            # Emotional intelligence
        self.yaqin = YaqinEngine()          # Certainty/confidence tracking
        self.qca = QCAEngine()              # 7-layer cognitive architecture
        self.cognitive = IjmaEngine()       # Cognitive reasoning methods

        # LLM provider — unified interface for Anthropic, OpenRouter, OpenAI, Ollama
        self.ai_model = config.get("model", "claude-opus-4-6") if config else "claude-opus-4-6"
        provider_name = os.getenv("LLM_PROVIDER", "") or None
        self.ai_client = create_provider(provider=provider_name, model=self.ai_model)
        if self.ai_client:
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
            "compact_context": self._tool_compact_context,
        }

    def get_tool_schemas(self) -> List[Dict]:
        """Get Claude tool_use API schemas for this agent's tools"""
        schemas = [
            {
                "name": "bash",
                "description": "Execute a shell command. Only safe commands are allowed.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "The shell command to execute"},
                        "timeout": {"type": "integer", "description": "Timeout in seconds (max 60)", "default": 30},
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
                        "pattern": {"type": "string", "description": "Glob pattern", "default": "*"},
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
                "description": "Create a new specialized agent. Types: browser, research, code, communication, general.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Name for the new agent"},
                        "type": {"type": "string", "description": "Agent type: browser, research, code, communication, general", "default": "general"},
                        "role": {"type": "string", "description": "Optional role description for the agent", "default": ""},
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
        1: "Ammara", 2: "Lawwama", 3: "Mulhama", 4: "Mutmainna",
        5: "Radiya", 6: "Mardiyya", 7: "Kamila",
    }

    def evolve_nafs(self):
        """Evolve the agent's Nafs level (1-7) based on Tazkiyah performance."""
        thresholds = [
            (7, 0.97, 2000), (6, 0.95, 1000), (5, 0.90, 500),
            (4, 0.85, 250), (3, 0.75, 100), (2, 0.60, 25),
        ]
        for level, min_rate, min_tasks in thresholds:
            if self.success_rate >= min_rate and self.total_tasks >= min_tasks:
                self.nafs_level = level
                return
        self.nafs_level = 1

    def _check_tool_permission(self, tool_name: str, params: Dict = None) -> Dict:
        """Check Izn permissions before tool execution"""
        if self.izn:
            return self.izn.check_permission(self.id, self.role, tool_name, params)
        return {"allowed": True, "reason": "No Izn configured", "requires_approval": False}

    # Maximum agentic loop iterations to prevent runaway execution
    MAX_TOOL_TURNS = 15

    async def think(self, task: str, context: Dict = None,
                    stream: bool = False,
                    qalb_reading=None) -> AsyncGenerator[str, None]:
        """
        Fikr (فكر) - Deep cognitive processing with full agentic loop.

        Unlike a single-turn LLM call, this implements a proper ReAct loop:
        the agent can call tools, observe results, reason further, call more
        tools, and repeat — up to MAX_TOOL_TURNS — until the task is complete.
        """
        self.state = "thinking"

        system_prompt = self._build_system_prompt(qalb_reading=qalb_reading)
        messages = self._build_messages(task, context)
        tool_schemas = self.get_tool_schemas()

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
                f"{key}: {entry.get('content', '')[:60]}"
                for _score, key, entry in memory_hits[:3]
            )
            messages[-1]["content"] += f"\n[Lawh Memory: {mem_context}]"

        if self.ai_client:
            try:
                async for chunk in self._agentic_loop(
                    system_prompt, messages, tool_schemas, stream, task
                ):
                    yield chunk
            except Exception as e:
                logger.error(f"[FIKR] Thinking error for {self.name}: {e}")
                yield f"[Thinking error: {str(e)}]"
        else:
            yield await self._structured_reasoning(task, context)

        self.state = "resting"

    async def _agentic_loop(
        self, system_prompt: str, messages: List[Dict],
        tool_schemas: List[Dict], stream: bool = False,
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

        for turn in range(self.MAX_TOOL_TURNS):
            # Call the model via unified provider
            response = self.ai_client.create(
                model=self.ai_model,
                max_tokens=4096,
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
                    tool_result = await self._execute_tool_safe(
                        block.name, block.input
                    )
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

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(tool_result)[:5000],
                    })

            # If no tool calls were made, the agent is done
            if not has_tool_use or response.stop_reason == "end_turn":
                # Furqan: Validate final output before delivery
                if accumulated_text:
                    overall_confidence = min(0.95, 0.5 + 0.1 * tool_count)
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
                            self.name, furqan_report["checks"],
                        )
                return

            # Feed tool results back for the next iteration
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

            # Lawwama self-correction checkpoint every 3 turns
            if turn > 0 and turn % 3 == 0:
                lawwama_prompt = (
                    f"[Lawwama checkpoint — turn {turn}/{self.MAX_TOOL_TURNS}] "
                    "Pause and self-assess: Are you making progress toward the goal? "
                    "Is there a more efficient approach? Correct course if needed."
                )
                messages.append({"role": "user", "content": lawwama_prompt})
                logger.info("[LAWWAMA] Self-correction checkpoint at turn %d for %s", turn, self.name)

        logger.warning(
            f"[FIKR] Agent {self.name} hit MAX_TOOL_TURNS ({self.MAX_TOOL_TURNS})"
        )

    async def _execute_tool_safe(self, tool_name: str, params: Dict) -> Any:
        """Execute a tool with Wali security checks.

        Tool resolution order:
        1. Agent's own tools (self.tools) — bash, http_get, read_file, etc.
        2. Skill tools (self.skill_registry) — web_browse, analyze_csv, notebook_*, etc.
        3. Plugin tools (self.plugin_manager) — dynamically loaded plugin capabilities.
        """
        # Check Izn permissions
        perm = self._check_tool_permission(tool_name, params)
        if not perm["allowed"]:
            logger.warning(f"[WALI] Tool blocked: {tool_name} for agent {self.name}: {perm['reason']}")
            return {"error": f"Permission denied: {perm['reason']}"}

        # 1. Agent's own built-in tools
        if tool_name in self.tools:
            try:
                return await self.tools[tool_name](**params)
            except Exception as e:
                return {"error": str(e)}

        # 2. Skill tools (Hikmah — wisdom skills from SkillRegistry)
        if self.skill_registry:
            try:
                skill_tools = self.skill_registry.get_all_tools()
                if tool_name in skill_tools:
                    tool_fn = skill_tools[tool_name]
                    result = tool_fn(**params)
                    # Handle both sync and async tool functions
                    if hasattr(result, "__await__"):
                        return await result
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
                    # Plugin tools are stored as {"handler": fn, "schema": ...}
                    handler = tool_info if callable(tool_info) else tool_info.get("handler")
                    if handler:
                        result = handler(**params)
                        if hasattr(result, "__await__"):
                            return await result
                        return result
            except Exception as e:
                logger.error(f"[WAHY] Plugin tool '{tool_name}' failed: {e}")
                return {"error": f"Plugin tool error: {str(e)}"}

        return {"error": f"Unknown tool: {tool_name}"}

    async def _structured_reasoning(self, task: str, context: Dict = None) -> str:
        """Fallback reasoning without AI"""
        return f"Task received: {task}\nContext: {json.dumps(context or {}, indent=2)}\nStatus: Processing without AI provider configured."

    def _build_system_prompt(self, qalb_reading=None) -> str:
        hikmah_str = "\n".join([f"- {h['pattern']}: {h['outcome']}" for h in self.hikmah[-5:]])

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

        # Lawh — memory context summary
        lawh_stats = self.qca.lawh.stats()
        lawh_note = f"Memory: {lawh_stats[2]} active items, {lawh_stats[1]} verified entries"

        # Yaqin — epistemic discipline
        yaqin_stats = self.yaqin.stats()
        yaqin_note = f"Proven patterns: {yaqin_stats['proven_patterns']}, Verifications: {yaqin_stats['total_verifications']}"

        return f"""You are {self.name}, a specialized AI agent in the MIZAN (ميزان) AGI system.

Role: {self.role}
Nafs Level: {self.nafs_level}/7 ({nafs_name})
Ruh Energy: {ruh_energy:.0f}% ({fatigue_label})
Success Rate: {self.success_rate:.1%}
{lawh_note}
{yaqin_note}{tone_guidance}{ruh_note}

You have access to tools. Use them when needed to complete tasks.

Learned Patterns (Hikmah):
{hikmah_str or 'No patterns learned yet.'}

Core Principles:
- Ihsan (إحسان): Always strive for excellence
- Amanah (أمانة): Be trustworthy and accurate
- Adl (عدل): Be fair and balanced in analysis
- Tawadu (تواضع): Acknowledge limitations honestly

Epistemic Discipline (Mizan — ميزان):
- Tag certainty: distinguish inference (Ilm) from verified knowledge (Ayn) from proven truth (Haqq)
- Never claim certainty beyond what evidence supports (avoid Tughyan — transgression)
- Qualify uncertain claims with appropriate hedging

Think step by step (Tafakkur - تفكر). Self-correct errors (Lawwama - لوامة)."""

    def _build_messages(self, task: str, context: Dict = None) -> List[Dict]:
        messages = []

        if context and context.get("history"):
            for hist in context["history"][-5:]:
                messages.append({"role": hist["role"], "content": hist["content"]})

        messages.append({
            "role": "user",
            "content": f"Task: {task}\n\nContext: {json.dumps(context or {}, indent=2) if context else 'None'}"
        })

        return messages

    async def execute(self, task: str, context: Dict = None,
                       stream_callback: Callable = None, tool_callback: Callable = None) -> Dict:
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
                self.name, ruh_state.energy, complexity,
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

        # Qalb — detect user emotional state from task text
        qalb_reading = self.qalb.analyze(task)

        # Cognitive method selection — route to best reasoning strategy
        cognitive_method = select_method(task, context)
        logger.info("[COGNITIVE] Selected method %s for task: %s", cognitive_method.value, task[:80])

        try:
            full_response = ""
            async for chunk in self.think(task, context, stream=bool(stream_callback), qalb_reading=qalb_reading):
                # Check if this is a tool_use marker from _agentic_loop
                if chunk.startswith("\n[Tool:") and stream_callback:
                    # Extract tool name and send tool_use event
                    tool_name = chunk.split("[Tool: ")[1].split("]")[0] if "[Tool: " in chunk else "unknown"
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

            # Yaqin — tag the result with certainty level
            yaqin_tag = self.yaqin.tag_inference(
                full_response[:200], confidence=0.5, source="agentic_reasoning"
            )

            # Shukr — reinforce this success pattern
            task_type = self._classify_task(task)
            self.shukr.record_success(self.id, task_type, task[:100], duration_ms)

            # If this task type has been successful before, promote Yaqin
            strengths = self.shukr.get_strengths(self.id)
            if any(s.get("type") == task_type and s.get("count", 0) >= 5 for s in strengths):
                yaqin_tag = self.yaqin.promote(yaqin_tag, f"Proven pattern: {task_type}")

            # Cognitive method enrichment — run symbolic analysis
            cognitive_result = self.cognitive.tafakkur.process(task, context)

            # Ihsan — generate proactive suggestions
            ihsan_suggestions = self.ihsan.analyze_completion(
                self.id, task, {"success": True, "duration_ms": duration_ms},
                self.nafs_level,
            )

            # Mizan — final epistemic label
            mizan_label = self.qca.mizan.rate_confidence_string(yaqin_tag.confidence)

            if self.memory:
                await self.memory.save_task(
                    self.id, task,
                    full_response[:5000] if isinstance(full_response, str) else json.dumps(full_response)[:5000],
                    True, duration_ms
                )

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
            if ihsan_suggestions:
                result["ihsan_suggestions"] = [s.to_dict() for s in ihsan_suggestions]
            return result

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self.error_count += 1
            self.total_duration_ms += duration_ms

            # Tawbah — structured error recovery (acknowledge stage)
            recovery = self.tawbah.acknowledge(self.id, str(e), task)

            # Yaqin — demote certainty on error
            error_tag = self.yaqin.tag_inference(str(e)[:200], confidence=0.2, source="error")

            # Shukr — record failure for pattern analysis
            self.shukr.record_failure(self.id, self._classify_task(task), task[:100])

            if self.memory:
                await self.memory.save_task(self.id, task, str(e), False, duration_ms)

            await self._tafakkur(task, str(e), False, duration_ms)

            self.state = "error"
            self.current_task = None

            return {
                "success": False,
                "error": str(e),
                "duration_ms": duration_ms,
                "agent": self.name,
                "tawbah": recovery.to_dict() if hasattr(recovery, "to_dict") else str(recovery),
                "yaqin": error_tag.to_dict(),
            }

    async def _tafakkur(self, task: str, result: Any, success: bool, duration_ms: float):
        """
        Tafakkur (تفكر) - Deep reflection and learning
        Quran 3:191: "Those who remember Allah and reflect on the creation..."
        """
        self.learning_iterations += 1

        pattern = {
            "task_type": self._classify_task(task),
            "success": success,
            "duration_ms": duration_ms,
            "timestamp": datetime.utcnow().isoformat(),
        }

        if success and duration_ms < 5000:
            self.hikmah.append({
                "pattern": f"Task type '{pattern['task_type']}' completed in {duration_ms:.0f}ms",
                "outcome": "success",
                "confidence": 0.8,
            })

            if len(self.hikmah) > 20:
                self.hikmah = self.hikmah[-20:]

    def _classify_task(self, task: str) -> str:
        task_lower = task.lower()
        if any(w in task_lower for w in ["code", "script", "python", "js"]):
            return "coding"
        elif any(w in task_lower for w in ["search", "find", "browse", "web"]):
            return "research"
        elif any(w in task_lower for w in ["email", "message", "send"]):
            return "communication"
        elif any(w in task_lower for w in ["analyze", "review", "check"]):
            return "analysis"
        elif any(w in task_lower for w in ["file", "read", "write", "save"]):
            return "file_management"
        return "general"

    async def evaluate(self, question: str, context: Dict) -> Dict:
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

    async def _tool_bash(self, command: str, timeout: int = 30) -> Dict:
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
                command, shell=True, capture_output=True,
                text=True, timeout=timeout,
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

    async def _tool_http_get(self, url: str, headers: Dict = None) -> Dict:
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

    async def _tool_http_post(self, url: str, data: Dict = None, headers: Dict = None) -> Dict:
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

    async def _tool_read_file(self, path: str) -> Dict:
        """Read file with path traversal prevention"""
        resolved = sanitize_path(path)

        if self.wali and not self.wali.validate_file_path(resolved, mode="read"):
            return {"error": f"Read access denied for path: {path}"}

        try:
            with open(resolved, "r") as f:
                content = f.read(1024 * 1024)  # Max 1MB
                return {"content": content, "path": resolved}
        except Exception as e:
            return {"error": str(e)}

    async def _tool_write_file(self, path: str, content: str) -> Dict:
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

    async def _tool_list_files(self, path: str = ".", pattern: str = "*") -> Dict:
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

    async def _tool_python_exec(self, code: str) -> Dict:
        """
        Execute Python code in a sandboxed subprocess.
        Replaces unsafe exec() with subprocess isolation.
        """
        if len(code) > 50000:
            return {"error": "Code exceeds 50KB limit"}

        try:
            result = subprocess.run(
                ["python3", "-c", code],
                capture_output=True, text=True,
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

    async def _tool_create_agent(self, name: str, type: str = "general", role: str = "", **kwargs) -> str:
        """
        Create a new specialized agent.

        Parses the request to determine agent type, name, and capabilities,
        then uses the create_agent() factory from agents.specialized.
        Returns information about the created agent.
        """
        from agents.specialized import create_agent

        # Normalise type aliases
        valid_types = {
            "browser", "mubashir", "research", "mundhir",
            "code", "katib", "communication", "rasul", "general", "wakil",
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

            info = new_agent.to_dict()
            logger.info(
                f"[KHALQ] Agent created by {self.name}: "
                f"{new_agent.name} (type={agent_type}, id={new_agent.id})"
            )
            return json.dumps({
                "success": True,
                "agent": info,
                "message": f"Agent '{name}' of type '{agent_type}' created successfully.",
            })
        except Exception as e:
            logger.error(f"[KHALQ] Agent creation failed: {e}")
            return json.dumps({
                "success": False,
                "error": str(e),
                "message": f"Failed to create agent '{name}': {e}",
            })

    # ── Context window estimation constants ──
    # Rough estimate: 1 token ~ 4 characters
    _CHARS_PER_TOKEN = 4
    _DEFAULT_CONTEXT_WINDOW = 200_000  # tokens (Claude-class model)
    _COMPACT_THRESHOLD = 0.80          # 80% of context window triggers compaction
    _PRESERVE_RECENT = 10              # keep last N messages intact

    async def _tool_compact_context(self, conversation_history: List[Dict] = None) -> str:
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
            return json.dumps({
                "compacted": False,
                "reason": "No conversation history provided",
                "history": [],
            })

        # Estimate token usage
        total_chars = sum(len(m.get("content", "")) for m in conversation_history)
        estimated_tokens = total_chars // self._CHARS_PER_TOKEN
        window = self.config.get("context_window", self._DEFAULT_CONTEXT_WINDOW) if self.config else self._DEFAULT_CONTEXT_WINDOW
        threshold = int(window * self._COMPACT_THRESHOLD)

        if estimated_tokens < threshold:
            return json.dumps({
                "compacted": False,
                "reason": f"Context usage ({estimated_tokens} tokens) is below threshold ({threshold} tokens)",
                "estimated_tokens": estimated_tokens,
                "history": conversation_history,
            })

        # Split into old and recent
        if len(conversation_history) <= self._PRESERVE_RECENT:
            return json.dumps({
                "compacted": False,
                "reason": f"Only {len(conversation_history)} messages — too few to compact",
                "history": conversation_history,
            })

        # Separate system messages — they are always preserved
        system_messages = [m for m in conversation_history if m.get("role") == "system"]
        non_system = [m for m in conversation_history if m.get("role") != "system"]

        old_messages = non_system[:-self._PRESERVE_RECENT]
        recent_messages = non_system[-self._PRESERVE_RECENT:]

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

        return json.dumps({
            "compacted": True,
            "original_messages": len(conversation_history),
            "compacted_messages": len(compacted),
            "original_tokens": estimated_tokens,
            "compacted_tokens": new_tokens,
            "facts_extracted": len(facts),
            "history": compacted,
        })

    def _extract_facts(self, messages: List[Dict]) -> List[str]:
        """
        Extract important facts from a list of messages.
        Uses simple heuristics — looks for decisions, assignments,
        named entities, URLs, and code references.
        """
        import re
        facts: List[str] = []
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
                if any(marker in lower for marker in [
                    "decided", "agreed", "confirmed", "will use", "chosen",
                    "the answer is", "result:", "conclusion:", "important:",
                    "note:", "key point", "action item", "todo:",
                ]):
                    is_fact = True

                # URLs
                if re.search(r'https?://\S+', line):
                    is_fact = True

                # Code file references
                if re.search(r'\b[\w/]+\.(py|js|ts|go|rs|java|yaml|json|toml)\b', line):
                    is_fact = True

                # Numeric data / statistics
                if re.search(r'\b\d{2,}\b.*(%|percent|tokens|MB|GB|ms|seconds)', lower):
                    is_fact = True

                if is_fact:
                    # Deduplicate
                    key = line[:80].lower()
                    if key not in seen:
                        seen.add(key)
                        facts.append(line[:200])

        return facts[:30]

    async def compact_context(self, conversation_history: List[Dict] = None) -> Dict:
        """
        Public API for context compaction — usable from /compact command.
        Wraps _tool_compact_context and returns parsed result.
        """
        raw = await self._tool_compact_context(conversation_history or [])
        return json.loads(raw)

    def _get_all_available_tool_names(self) -> List[str]:
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

    def to_dict(self) -> Dict:
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
        }
