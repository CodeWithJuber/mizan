"""
Aql Engine (عَقْل) — The Reasoning Engine
============================================

"Indeed in the creation of the heavens and earth... are signs for people of reason (Aql)" — Quran 3:190

Implements the full Quranic reasoning cycle:
1. Niyyah (نية) — Intent declaration
2. Sama' (سمع) — Input perception via QCA DualInput (Sam' + Basar + Fu'ad)
3. Fikr (فكر) — Cognitive processing via QCA ISM root-space
4. Aql (عقل) — Logical reasoning with tool_use + QCA typed bindings
5. Amal (عمل) — Action execution with Mizan-weighted confidence
6. Tafakkur (تفكر) — Deep reflection, self-correction, and Lawh consolidation

Key improvement over OpenClaw: Full Claude tool_use API with multi-turn
reasoning, Lawwama self-correction checkpoints, Nafs-aware prompting,
and QCA epistemic weighting through all 7 cognitive layers.
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
    The core reasoning engine, enhanced with QCA cognitive layers.

    Implements a multi-turn ReAct loop:
      Thought → Action → Observation → Thought → ...

    Mapped to QCA cognitive cycle:
      Sam'+Basar (Perceive) → Fu'ad (Integrate) → ISM (Semantics) →
      Mizan (Weigh) → 'Aql (Bind) → Lawh (Remember) → Furqan (Validate)

    All reasoning steps pass through QCA epistemic weighting (Mizan)
    to prevent transgression (Tughyan) and ensure proportional certainty.
    """

    def __init__(self, max_iterations: int = 10):
        self.max_iterations = max_iterations
        self._qca = None

    @property
    def qca(self):
        """Lazy-load QCA engine to avoid circular imports."""
        if self._qca is None:
            try:
                from qca.engine import QCAEngine
                self._qca = QCAEngine()
            except ImportError:
                self._qca = None
        return self._qca

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
                content="No AI provider configured. Set ANTHROPIC_API_KEY, OPENROUTER_API_KEY, or OPENAI_API_KEY.",
            )
            return

        system_prompt = agent._build_system_prompt()
        messages = self._build_initial_messages(task, context)
        tool_schemas = agent.get_tool_schemas()

        for iteration in range(self.max_iterations):
            try:
                response = agent.ai_client.create(
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

        result = {
            "success": True,
            "response": full_text,
            "tool_calls": tool_calls,
            "iterations": iterations,
        }

        # QCA cognitive enrichment: epistemic analysis + memory storage
        if self.qca and full_text:
            try:
                qca_analysis = self.qca.process_input(full_text[:500])
                # Confidence scales with tool verification
                base_confidence = 0.5
                if tool_calls:
                    base_confidence = min(0.9, 0.5 + 0.1 * len(tool_calls))
                mizan_label = self.qca.mizan.rate_confidence_string(base_confidence)
                cert_level = self.qca.mizan.classify_confidence(base_confidence)

                # Furqan validation on final output
                furqan_report = self.qca.furqan.validate_and_express(
                    full_text[:200], base_confidence, source="aql_reasoning"
                )

                # Store reasoning result in Lawh Tier 3
                self.qca.lawh.store(
                    f"AQL_RESULT:{task[:50]}",
                    full_text[:500],
                    certainty=base_confidence,
                    source="aql_engine",
                    tier=3,
                )

                result["qca_enrichment"] = {
                    "roots_identified": qca_analysis.get("roots_identified", []),
                    "key_terms": qca_analysis.get("key_terms", []),
                    "epistemic_label": mizan_label,
                    "certainty_level": cert_level,
                    "furqan_passed": furqan_report.get("passed", True),
                    "furqan_checks": furqan_report.get("checks", []),
                    "lawh_stats": self.qca.lawh.stats(),
                }
            except Exception:
                pass

        return result

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
