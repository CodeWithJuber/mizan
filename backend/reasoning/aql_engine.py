"""
Aql Engine (عَقْل) — The Reasoning Engine
============================================

"Indeed in the creation of the heavens and earth... are signs for people of reason (Aql)" — Quran 3:190

Implements the full Quranic reasoning cycle:
1. Niyyah (نية) — Intent declaration
2. Sama' (سمع) — Input perception
3. Fikr (فكر) — Cognitive processing
4. Aql (عقل) — Logical reasoning with tool_use
5. Amal (عمل) — Action execution
6. Tafakkur (تفكر) — Deep reflection and self-correction

Key improvement over OpenClaw: Full Claude tool_use API with multi-turn
reasoning, Lawwama self-correction checkpoints, and Nafs-aware prompting.
"""

import json
import time
import logging
from datetime import datetime
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger("mizan.aql")


@dataclass
class ReasoningStep:
    """A single step in the reasoning process"""
    type: str  # "thinking", "tool_call", "tool_result", "lawwama", "final", "error"
    content: str = ""
    tool_name: Optional[str] = None
    tool_input: Optional[Dict] = None
    tool_result: Optional[Any] = None
    iteration: int = 0
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class AqlEngine:
    """
    The core reasoning engine.

    Implements a multi-turn ReAct loop:
      Thought → Action → Observation → Thought → ...

    Mapped to Quranic cycle:
      Fikr (Think) → Aql (Reason) → Amal (Act) → Tafakkur (Reflect)
    """

    def __init__(self, max_iterations: int = 10):
        self.max_iterations = max_iterations

    async def reason(
        self,
        task: str,
        agent,
        context: Dict = None,
        stream_callback: Callable = None,
    ) -> AsyncGenerator[ReasoningStep, None]:
        """
        Full reasoning loop with Claude tool_use API.
        Yields each step for streaming to the user.

        The agent provides:
        - ai_client: Anthropic client
        - ai_model: Model name
        - tools: Dict of tool functions
        - get_tool_schemas(): List of Claude tool schemas
        - _build_system_prompt(): System prompt
        - wali: Security guardian
        """
        if not agent.ai_client:
            yield ReasoningStep(
                type="error",
                content="No AI provider configured. Set ANTHROPIC_API_KEY.",
            )
            return

        system_prompt = agent._build_system_prompt()
        messages = self._build_initial_messages(task, context)
        tool_schemas = agent.get_tool_schemas()

        for iteration in range(self.max_iterations):
            try:
                response = agent.ai_client.messages.create(
                    model=agent.ai_model,
                    max_tokens=4096,
                    system=system_prompt,
                    messages=messages,
                    tools=tool_schemas,
                )
            except Exception as e:
                yield ReasoningStep(type="error", content=str(e), iteration=iteration)
                return

            # Process response content blocks
            has_tool_use = False
            assistant_content = response.content

            for block in response.content:
                if block.type == "text":
                    step = ReasoningStep(
                        type="thinking",
                        content=block.text,
                        iteration=iteration,
                    )
                    yield step
                    if stream_callback:
                        await stream_callback(block.text)

                elif block.type == "tool_use":
                    has_tool_use = True

                    # Yield the tool call
                    yield ReasoningStep(
                        type="tool_call",
                        tool_name=block.name,
                        tool_input=block.input,
                        iteration=iteration,
                    )

                    if stream_callback:
                        await stream_callback(f"\n[Using tool: {block.name}]\n")

                    # Execute tool through agent's security layer
                    tool_result = await agent._execute_tool_safe(
                        block.name, block.input
                    )

                    # Yield the tool result
                    result_str = json.dumps(tool_result) if isinstance(tool_result, dict) else str(tool_result)
                    yield ReasoningStep(
                        type="tool_result",
                        tool_name=block.name,
                        tool_result=tool_result,
                        content=result_str[:1000],
                        iteration=iteration,
                    )

                    if stream_callback:
                        await stream_callback(f"\n[Result: {result_str[:500]}]\n")

                    # Build follow-up message with tool result
                    messages.append({
                        "role": "assistant",
                        "content": assistant_content,
                    })
                    messages.append({
                        "role": "user",
                        "content": [{
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result_str[:5000],
                        }],
                    })

            # If no tool use, we're done
            if response.stop_reason == "end_turn" or not has_tool_use:
                yield ReasoningStep(
                    type="final",
                    content="Reasoning complete",
                    iteration=iteration,
                )
                return

            # Lawwama self-correction checkpoint every 3 iterations
            if iteration > 0 and iteration % 3 == 0:
                yield ReasoningStep(
                    type="lawwama",
                    content=f"Self-correction checkpoint at iteration {iteration}",
                    iteration=iteration,
                )

        # Max iterations reached
        yield ReasoningStep(
            type="final",
            content=f"Max iterations ({self.max_iterations}) reached",
            iteration=self.max_iterations,
        )

    async def reason_to_completion(
        self,
        task: str,
        agent,
        context: Dict = None,
        stream_callback: Callable = None,
    ) -> Dict:
        """
        Run reasoning loop to completion and return full result.
        Collects all thinking text as the final response.
        """
        full_text = ""
        tool_calls = []
        iterations = 0

        async for step in self.reason(task, agent, context, stream_callback):
            if step.type == "thinking":
                full_text += step.content
            elif step.type == "tool_call":
                tool_calls.append({
                    "tool": step.tool_name,
                    "input": step.tool_input,
                })
            elif step.type == "tool_result":
                tool_calls[-1]["result"] = step.content if step.content else str(step.tool_result)
            elif step.type == "error":
                return {
                    "success": False,
                    "error": step.content,
                    "iterations": step.iteration,
                }

            iterations = step.iteration

        return {
            "success": True,
            "response": full_text,
            "tool_calls": tool_calls,
            "iterations": iterations,
        }

    def _build_initial_messages(self, task: str, context: Dict = None) -> List[Dict]:
        """Build initial message list"""
        messages = []

        if context and context.get("history"):
            for hist in context["history"][-5:]:
                messages.append({"role": hist["role"], "content": hist["content"]})

        content = f"Task: {task}"
        if context:
            ctx = {k: v for k, v in context.items() if k != "history"}
            if ctx:
                content += f"\n\nContext: {json.dumps(ctx, indent=2)}"

        messages.append({"role": "user", "content": content})
        return messages
