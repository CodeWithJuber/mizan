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
import subprocess
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable, AsyncGenerator
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import httpx
import anthropic


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
    
    def __init__(self, agent_id: str = None, name: str = "", role: str = "wakil",
                 config: Dict = None, memory=None):
        self.id = agent_id or str(uuid.uuid4())
        self.name = name or f"Agent-{self.id[:8]}"
        self.role = role
        self.config = config or {}
        self.memory = memory
        
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
        self.nafs_level = 1  # 1=Ammara, 2=Lawwama, 3=Mutmainna
        
        # Tools registry
        self.tools: Dict[str, Callable] = {}
        self._register_base_tools()
        
        # Learning store (Hikmah)
        self.hikmah: List[Dict] = []
        
        # Anthropic client for AI reasoning
        api_key = os.getenv("ANTHROPIC_API_KEY", config.get("anthropic_api_key", "") if config else "")
        self.ai_client = anthropic.Anthropic(api_key=api_key) if api_key else None
        self.ai_model = config.get("model", "claude-opus-4-6") if config else "claude-opus-4-6"
        
        # Alternative AI providers
        self.openai_key = os.getenv("OPENAI_API_KEY", "")
        self.ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    
    def _register_base_tools(self):
        """Register core Quranic tools every agent has"""
        self.tools = {
            "bash": self._tool_bash,
            "http_get": self._tool_http_get,
            "http_post": self._tool_http_post,
            "read_file": self._tool_read_file,
            "write_file": self._tool_write_file,
            "list_files": self._tool_list_files,
            "python_eval": self._tool_python_eval,
        }
    
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
    
    def evolve_nafs(self):
        """Evolve the agent's Nafs level based on performance"""
        if self.success_rate > 0.9 and self.learning_iterations > 50:
            self.nafs_level = 3
        elif self.success_rate > 0.7:
            self.nafs_level = 2
        else:
            self.nafs_level = 1
    
    async def think(self, task: str, context: Dict = None, 
                    stream: bool = False) -> AsyncGenerator[str, None]:
        """
        Fikr (فكر) - Deep cognitive processing
        Uses AI to reason about the task
        """
        self.state = "thinking"
        
        system_prompt = self._build_system_prompt()
        messages = self._build_messages(task, context)
        
        if self.ai_client:
            try:
                if stream:
                    with self.ai_client.messages.stream(
                        model=self.ai_model,
                        max_tokens=4096,
                        system=system_prompt,
                        messages=messages,
                    ) as stream_obj:
                        for text in stream_obj.text_stream:
                            yield text
                else:
                    response = self.ai_client.messages.create(
                        model=self.ai_model,
                        max_tokens=4096,
                        system=system_prompt,
                        messages=messages,
                    )
                    yield response.content[0].text
            except Exception as e:
                yield f"[Thinking error: {str(e)}]"
        else:
            # Fallback: structured reasoning without AI
            yield await self._structured_reasoning(task, context)
        
        self.state = "resting"
    
    async def _structured_reasoning(self, task: str, context: Dict = None) -> str:
        """Fallback reasoning without AI"""
        return f"Task received: {task}\nContext: {json.dumps(context or {}, indent=2)}\nStatus: Processing without AI provider configured."
    
    def _build_system_prompt(self) -> str:
        hikmah_str = "\n".join([f"- {h['pattern']}: {h['outcome']}" for h in self.hikmah[-5:]])
        
        return f"""You are {self.name}, a specialized AI agent in the MIZAN (ميزان) system.

Role: {self.role}
Nafs Level: {self.nafs_level} ({'Ammara - Raw' if self.nafs_level == 1 else 'Lawwama - Self-correcting' if self.nafs_level == 2 else 'Mutmainna - Perfected'})
Success Rate: {self.success_rate:.1%}

Available Tools: {', '.join(self.tools.keys())}

Learned Patterns (Hikmah):
{hikmah_str or 'No patterns learned yet.'}

Core Principles:
- Ihsan (إحسان): Always strive for excellence
- Amanah (أمانة): Be trustworthy and accurate
- Adl (عدل): Be fair and balanced in analysis
- Tawadu (تواضع): Acknowledge limitations honestly

When using tools, respond with JSON:
{{"tool": "tool_name", "params": {{}}, "reasoning": "why this tool"}}

Think step by step (Tafakkur - تفكر). Self-correct errors (Lawwama - لوامة)."""
    
    def _build_messages(self, task: str, context: Dict = None) -> List[Dict]:
        messages = []
        
        # Add context from memory if available
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
        """
        start_time = time.time()
        self.state = "acting"
        self.current_task = task
        self.total_tasks += 1
        
        try:
            # Collect full response
            full_response = ""
            async for chunk in self.think(task, context, stream=bool(stream_callback)):
                full_response += chunk
                if stream_callback:
                    await stream_callback(chunk)
            
            # Parse tool calls if any
            result = await self._process_response(full_response, task, context)
            
            # Tafakkur - learn from this execution
            duration_ms = (time.time() - start_time) * 1000
            self.total_duration_ms += duration_ms
            self.success_count += 1
            
            await self._tafakkur(task, result, True, duration_ms)
            
            if self.memory:
                await self.memory.save_task(
                    self.id, task, 
                    json.dumps(result) if isinstance(result, dict) else str(result),
                    True, duration_ms
                )
            
            self.evolve_nafs()
            self.state = "resting"
            self.current_task = None
            
            return {
                "success": True,
                "result": result,
                "duration_ms": duration_ms,
                "agent": self.name,
                "nafs_level": self.nafs_level,
            }
        
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self.error_count += 1
            self.total_duration_ms += duration_ms
            
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
            }
    
    async def _process_response(self, response: str, task: str, context: Dict) -> Any:
        """Process AI response and execute tools if needed"""
        # Try to extract tool call from response
        try:
            # Look for JSON tool call
            if '{"tool":' in response or "{'tool':" in response:
                import re
                json_match = re.search(r'\{[^{}]*"tool"[^{}]*\}', response)
                if json_match:
                    tool_call = json.loads(json_match.group())
                    tool_name = tool_call.get("tool")
                    params = tool_call.get("params", {})
                    
                    if tool_name in self.tools:
                        tool_result = await self.tools[tool_name](**params)
                        return {
                            "response": response,
                            "tool_used": tool_name,
                            "tool_result": tool_result,
                        }
        except:
            pass
        
        return response
    
    async def _tafakkur(self, task: str, result: Any, success: bool, duration_ms: float):
        """
        Tafakkur (تفكر) - Deep reflection and learning
        Quran 3:191: "Those who remember Allah and reflect on the creation..."
        """
        self.learning_iterations += 1
        
        # Extract pattern from this experience
        pattern = {
            "task_type": self._classify_task(task),
            "success": success,
            "duration_ms": duration_ms,
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        # Update Hikmah if successful pattern
        if success and duration_ms < 5000:
            self.hikmah.append({
                "pattern": f"Task type '{pattern['task_type']}' completed in {duration_ms:.0f}ms",
                "outcome": "success",
                "confidence": 0.8,
            })
            
            # Keep only recent hikmah
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
    
    # ===== TOOL IMPLEMENTATIONS =====
    
    async def _tool_bash(self, command: str, timeout: int = 30) -> str:
        """Execute bash command"""
        try:
            result = subprocess.run(
                command, shell=True, capture_output=True,
                text=True, timeout=timeout
            )
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out", "returncode": -1}
        except Exception as e:
            return {"error": str(e), "returncode": -1}
    
    async def _tool_http_get(self, url: str, headers: Dict = None) -> str:
        """HTTP GET request"""
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, headers=headers or {})
            return {
                "status": response.status_code,
                "content": response.text[:5000],
                "headers": dict(response.headers),
            }
    
    async def _tool_http_post(self, url: str, data: Dict = None, headers: Dict = None) -> str:
        """HTTP POST request"""
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, json=data or {}, headers=headers or {})
            return {
                "status": response.status_code,
                "content": response.text[:5000],
            }
    
    async def _tool_read_file(self, path: str) -> str:
        """Read file contents"""
        try:
            with open(path, "r") as f:
                return {"content": f.read(), "path": path}
        except Exception as e:
            return {"error": str(e)}
    
    async def _tool_write_file(self, path: str, content: str) -> str:
        """Write file contents"""
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(path) else None
            with open(path, "w") as f:
                f.write(content)
            return {"success": True, "path": path, "bytes": len(content)}
        except Exception as e:
            return {"error": str(e)}
    
    async def _tool_list_files(self, path: str = ".", pattern: str = "*") -> str:
        """List files in directory"""
        import glob
        files = glob.glob(os.path.join(path, pattern))
        return {"files": files[:100], "count": len(files)}
    
    async def _tool_python_eval(self, code: str) -> str:
        """Execute Python code safely"""
        try:
            exec_globals = {"__builtins__": {"print": print, "len": len, "range": range, 
                                               "str": str, "int": int, "float": float,
                                               "list": list, "dict": dict, "json": json}}
            exec(code, exec_globals)
            return {"success": True, "output": exec_globals.get("result", "Executed")}
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
            "nafs_name": ["", "Ammara", "Lawwama", "Mutmainna"][self.nafs_level],
            "tools": list(self.tools.keys()),
            "hikmah_count": len(self.hikmah),
        }
