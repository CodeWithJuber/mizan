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
from core.qalb import QalbEngine
from qca.yaqin_engine import YaqinEngine

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
                 config: Dict = None, memory=None, wali=None, izn=None):
        self.id = agent_id or str(uuid.uuid4())
        self.name = name or f"Agent-{self.id[:8]}"
        self.role = role
        self.config = config or {}
        self.memory = memory

        # Security (Wali guardian + Izn permissions)
        self.wali = wali
        self.izn = izn

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
        ]
        return schemas + self.TOOL_SCHEMAS

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
                    stream: bool = False) -> AsyncGenerator[str, None]:
        """
        Fikr (فكر) - Deep cognitive processing with full agentic loop.

        Unlike a single-turn LLM call, this implements a proper ReAct loop:
        the agent can call tools, observe results, reason further, call more
        tools, and repeat — up to MAX_TOOL_TURNS — until the task is complete.
        """
        self.state = "thinking"

        system_prompt = self._build_system_prompt()
        messages = self._build_messages(task, context)
        tool_schemas = self.get_tool_schemas()

        if self.ai_client:
            try:
                async for chunk in self._agentic_loop(
                    system_prompt, messages, tool_schemas, stream
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
    ) -> AsyncGenerator[str, None]:
        """
        Full agentic loop — the core of MIZAN's reasoning engine.

        Repeatedly calls the LLM, executes any requested tools, feeds results
        back, and continues until the model produces a final text response
        with no further tool calls (stop_reason == 'end_turn') or we hit
        the safety limit of MAX_TOOL_TURNS.

        Uses the unified provider interface (providers.py) so this works
        identically with Anthropic, OpenRouter, OpenAI, and Ollama.
        """
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
                    yield block.text
                elif block.type == "tool_use":
                    has_tool_use = True

                    # Execute through security layer
                    tool_result = await self._execute_tool_safe(
                        block.name, block.input
                    )
                    yield f"\n[Tool: {block.name}] → {json.dumps(tool_result)[:500]}\n"

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(tool_result)[:5000],
                    })

            # If no tool calls were made, the agent is done
            if not has_tool_use or response.stop_reason == "end_turn":
                return

            # Feed tool results back for the next iteration
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

        logger.warning(
            f"[FIKR] Agent {self.name} hit MAX_TOOL_TURNS ({self.MAX_TOOL_TURNS})"
        )

    async def _execute_tool_safe(self, tool_name: str, params: Dict) -> Any:
        """Execute a tool with Wali security checks"""
        # Check Izn permissions
        perm = self._check_tool_permission(tool_name, params)
        if not perm["allowed"]:
            logger.warning(f"[WALI] Tool blocked: {tool_name} for agent {self.name}: {perm['reason']}")
            return {"error": f"Permission denied: {perm['reason']}"}

        # Execute the tool
        if tool_name in self.tools:
            try:
                return await self.tools[tool_name](**params)
            except Exception as e:
                return {"error": str(e)}

        return {"error": f"Unknown tool: {tool_name}"}

    async def _structured_reasoning(self, task: str, context: Dict = None) -> str:
        """Fallback reasoning without AI"""
        return f"Task received: {task}\nContext: {json.dumps(context or {}, indent=2)}\nStatus: Processing without AI provider configured."

    def _build_system_prompt(self) -> str:
        hikmah_str = "\n".join([f"- {h['pattern']}: {h['outcome']}" for h in self.hikmah[-5:]])

        nafs_name = self.NAFS_NAMES.get(self.nafs_level, "Ammara")
        ruh_energy = self.ruh.get_state(self.id).energy if self.ruh else 100
        return f"""You are {self.name}, a specialized AI agent in the MIZAN (ميزان) AGI system.

Role: {self.role}
Nafs Level: {self.nafs_level}/7 ({nafs_name})
Ruh Energy: {ruh_energy:.0f}%
Success Rate: {self.success_rate:.1%}

You have access to tools. Use them when needed to complete tasks.

Learned Patterns (Hikmah):
{hikmah_str or 'No patterns learned yet.'}

Core Principles:
- Ihsan (إحسان): Always strive for excellence
- Amanah (أمانة): Be trustworthy and accurate
- Adl (عدل): Be fair and balanced in analysis
- Tawadu (تواضع): Acknowledge limitations honestly

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
                       stream_callback: Callable = None) -> Dict:
        """
        Execute a task - full Quranic cycle:
        Niyyah → Sama' → Fikr → Amal → Tafakkur

        Integrated systems:
        - Ruh: energy check before execution
        - Qalb: emotional tone detection from context
        - Tawbah: structured error recovery on failure
        - Ihsan: proactive suggestions after success
        - Shukr: strength reinforcement on success
        """
        start_time = time.time()
        self.state = "acting"
        self.current_task = task
        self.total_tasks += 1

        # Ruh energy check — consume energy based on task complexity
        complexity = self.ruh.classify_task_complexity(task)
        self.ruh.consume_energy(self.id, complexity)

        # Qalb — detect user emotional state from task text
        qalb_reading = self.qalb.analyze(task)

        try:
            full_response = ""
            async for chunk in self.think(task, context, stream=bool(stream_callback)):
                full_response += chunk
                if stream_callback:
                    await stream_callback(chunk)

            # Tafakkur - learn from this execution
            duration_ms = (time.time() - start_time) * 1000
            self.total_duration_ms += duration_ms
            self.success_count += 1

            await self._tafakkur(task, full_response, True, duration_ms)

            # Shukr — reinforce this success pattern
            task_type = self._classify_task(task)
            self.shukr.record_success(self.id, task_type, task[:100], duration_ms)

            # Ihsan — generate proactive suggestions
            ihsan_suggestions = self.ihsan.analyze_completion(
                self.id, task, {"success": True, "duration_ms": duration_ms},
                self.nafs_level,
            )

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
            "ihsan_eligible": self.ihsan.is_eligible(self.nafs_level),
            "shukr_strengths": len(self.shukr.get_strengths(self.id)),
            "tools": list(self.tools.keys()),
            "hikmah_count": len(self.hikmah),
        }
