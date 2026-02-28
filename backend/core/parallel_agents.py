"""
Parallel Agents — QALB Parallel Processing Architecture
=========================================================

"And We have created you in pairs" — Quran 78:8

Implements Algorithm 1: QALB_PARALLEL_SCHEDULER
Multiple simultaneous thought streams with workspace competition,
salience-gated serial Qalb bottleneck, and cerebellar background processing.

Algorithm 2: SKILL_AUTOMATION_TRANSFER
Mastery-based delegation of automated skills to background processing.

Math:
  dh_i/dt = -h_i/τ_i + σ(W_self·h_i + W_input·x + Σ_j W_ij·broadcast_j)
  P(agent_i) = exp(salience_i/τ) / Σ_j exp(salience_j/τ)
  salience_i = w_novel·novelty(h_i) + w_emotion·|affect(h_i)| + w_task·relevance(h_i, goal)
"""

import logging
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("mizan.parallel_agents")

# Salience weights
W_NOVELTY = 0.35
W_EMOTION = 0.30
W_TASK_RELEVANCE = 0.35

# Softmax temperature for workspace competition
TAU_COMPETITION = 1.0

# Decay time constants per agent type (seconds)
TAU_FAST = 0.1   # reactive / surface agents
TAU_SLOW = 0.5   # deliberative / deep agents

# Skill automation mastery threshold
MASTERY_THRESHOLD = 0.85


class AgentStreamType(Enum):
    REACTIVE = "reactive"       # fast, surface-level (Ammara-like)
    DELIBERATIVE = "deliberative"  # slow, deep reasoning (Mutmainna-like)
    BACKGROUND = "background"   # cerebellar — automated skills, no bottleneck


@dataclass
class AgentStream:
    """A single parallel thought stream."""
    name: str
    stream_type: AgentStreamType
    hidden_state: float = 0.0      # h_i: activation level
    salience: float = 0.0
    novelty: float = 0.0
    affect: float = 0.0
    task_relevance: float = 0.0
    tau: float = TAU_SLOW
    output: str = ""
    latency_ms: float = 0.0
    is_automated: bool = False     # True = background cerebellar processing


@dataclass
class WorkspaceAccess:
    """Result of workspace competition — one stream wins global broadcast."""
    winner: str
    winner_salience: float
    competition_probs: dict[str, float]
    broadcast_content: str
    background_results: list[dict]


@dataclass
class SkillAutomation:
    """A skill that has been transferred to background processing."""
    skill_name: str
    mastery_score: float
    invocation_count: int
    avg_latency_ms: float
    transferred_at: float


@dataclass
class ParallelResult:
    """Full result from parallel processing cycle."""
    workspace: WorkspaceAccess
    integration: str
    streams_active: int
    total_latency_ms: float
    skill_automations: list[str]


class QalbParallelScheduler:
    """
    Algorithm 1: QALB_PARALLEL_SCHEDULER

    Manages multiple simultaneous reasoning streams with:
    - Global workspace competition (softmax salience)
    - Serial Qalb bottleneck (only 1 stream accesses broadcast)
    - Background cerebellar processing (automated skills bypass bottleneck)
    - Cross-stream integration via broadcast signal

    Biological analogy:
    - Reactive streams ↔ fast System 1 (basal ganglia)
    - Deliberative streams ↔ slow System 2 (prefrontal cortex)
    - Background ↔ cerebellum (automated, parallel, no bottleneck)
    """

    def __init__(self):
        self.streams: dict[str, AgentStream] = self._init_default_streams()
        self.automation_registry: dict[str, SkillAutomation] = {}
        self.broadcast_history: list[str] = []
        self.cycle_count = 0

    def _init_default_streams(self) -> dict[str, AgentStream]:
        return {
            "reactive": AgentStream(
                name="reactive",
                stream_type=AgentStreamType.REACTIVE,
                tau=TAU_FAST,
            ),
            "deliberative": AgentStream(
                name="deliberative",
                stream_type=AgentStreamType.DELIBERATIVE,
                tau=TAU_SLOW,
            ),
            "background": AgentStream(
                name="background",
                stream_type=AgentStreamType.BACKGROUND,
                tau=TAU_SLOW,
                is_automated=True,
            ),
        }

    def process(
        self,
        task: str,
        context: dict | None = None,
        task_goal: str = "",
    ) -> ParallelResult:
        """
        Run one full parallel processing cycle.

        Steps:
        1. Perceive — update stream hidden states
        2. Compete — compute salience, softmax competition
        3. Bottleneck — winner accesses Qalb global workspace
        4. Background — automated skills run in parallel
        5. Integrate — broadcast merges all streams
        """
        self.cycle_count += 1
        start = time.monotonic()

        # Step 1: Update hidden states
        for stream in self.streams.values():
            stream.hidden_state = self._update_hidden_state(stream, task, context)

        # Step 2: Compute salience and competition (skip background — no bottleneck)
        competing = {
            name: stream
            for name, stream in self.streams.items()
            if not stream.is_automated
        }
        for stream in competing.values():
            stream.novelty = self._compute_novelty(stream, task)
            stream.affect = self._compute_affect(stream, task)
            stream.task_relevance = self._compute_task_relevance(stream, task, task_goal)
            stream.salience = self._compute_salience(stream)

        # Step 3: Softmax competition → workspace winner
        winner_name, probs = self._softmax_compete(competing)
        winner = competing[winner_name]

        # Generate winner output
        winner.output = self._generate_stream_output(winner, task)
        broadcast = winner.output

        # Step 4: Background streams run without bottleneck
        background_results = []
        for stream in self.streams.values():
            if stream.is_automated:
                result = self._run_background_stream(stream, task, broadcast)
                background_results.append(result)

        self.broadcast_history.append(broadcast[:200])
        if len(self.broadcast_history) > 50:
            self.broadcast_history.pop(0)

        workspace = WorkspaceAccess(
            winner=winner_name,
            winner_salience=winner.salience,
            competition_probs=probs,
            broadcast_content=broadcast,
            background_results=background_results,
        )

        # Step 5: Integrate — merge broadcast + background
        integration = self._integrate(broadcast, background_results, task)

        elapsed_ms = (time.monotonic() - start) * 1000
        logger.debug(
            "[PARALLEL] cycle=%d winner=%s salience=%.3f",
            self.cycle_count, winner_name, winner.salience,
        )

        return ParallelResult(
            workspace=workspace,
            integration=integration,
            streams_active=len(self.streams),
            total_latency_ms=elapsed_ms,
            skill_automations=list(self.automation_registry.keys()),
        )

    def _update_hidden_state(
        self, stream: AgentStream, task: str, context: dict | None
    ) -> float:
        """
        Simplified discrete-time hidden state update:
        h_i(t+1) = h_i(t)·(1 - 1/τ_i) + σ(W_input·x)

        x = task complexity signal (0-1)
        """
        complexity = min(1.0, len(task.split()) / 50.0)
        broadcast_signal = (
            self._hash_to_float(self.broadcast_history[-1])
            if self.broadcast_history else 0.0
        )
        decay = 1.0 - (1.0 / max(stream.tau * 10, 1))
        input_signal = self._sigmoid(complexity + 0.3 * broadcast_signal)
        return stream.hidden_state * decay + input_signal * (1 - decay)

    def _compute_novelty(self, stream: AgentStream, task: str) -> float:
        """
        novelty(h_i) = 1 - max_k cos_sim(h_i, known_k)
        Approximated by checking if task tokens appear in broadcast history.
        """
        task_words = set(task.lower().split())
        if not self.broadcast_history:
            return 0.8
        history_words = set(" ".join(self.broadcast_history).lower().split())
        overlap = len(task_words & history_words) / max(len(task_words), 1)
        return max(0.0, 1.0 - overlap)

    def _compute_affect(self, stream: AgentStream, task: str) -> float:
        """Emotional valence magnitude |affect(h_i)|."""
        positive = ["help", "create", "build", "solve", "improve", "good"]
        negative = ["error", "fail", "danger", "harm", "delete", "wrong"]
        task_lower = task.lower()
        pos_score = sum(1 for w in positive if w in task_lower) / len(positive)
        neg_score = sum(1 for w in negative if w in task_lower) / len(negative)
        return abs(pos_score - neg_score) + 0.1 * stream.hidden_state

    def _compute_task_relevance(
        self, stream: AgentStream, task: str, goal: str
    ) -> float:
        """Relevance of stream hidden state to task goal."""
        if not goal:
            return 0.5
        goal_words = set(goal.lower().split())
        task_words = set(task.lower().split())
        if not goal_words:
            return 0.5
        overlap = len(task_words & goal_words) / len(goal_words)
        # Reactive streams prefer simple tasks, deliberative prefer complex
        complexity = min(1.0, len(task.split()) / 50.0)
        if stream.stream_type == AgentStreamType.REACTIVE:
            return overlap * (1.0 - complexity * 0.3)
        return overlap * (1.0 + complexity * 0.3)

    def _compute_salience(self, stream: AgentStream) -> float:
        """
        salience_i = w_novel·novelty + w_emotion·|affect| + w_task·relevance
        """
        return (
            W_NOVELTY * stream.novelty
            + W_EMOTION * stream.affect
            + W_TASK_RELEVANCE * stream.task_relevance
        )

    def _softmax_compete(
        self, streams: dict[str, AgentStream]
    ) -> tuple[str, dict[str, float]]:
        """
        P(agent_i) = exp(salience_i / τ) / Σ_j exp(salience_j / τ)
        Winner = argmax P.
        """
        saliences = {name: s.salience for name, s in streams.items()}
        max_s = max(saliences.values()) if saliences else 0.0
        exps = {k: math.exp((v - max_s) / TAU_COMPETITION) for k, v in saliences.items()}
        total = sum(exps.values())
        probs = {k: v / total for k, v in exps.items()}
        winner = max(probs, key=lambda k: probs[k])
        return winner, probs

    def _generate_stream_output(self, stream: AgentStream, task: str) -> str:
        """Placeholder: in production, each stream calls its LLM sub-agent."""
        type_label = {
            AgentStreamType.REACTIVE: "Quick assessment",
            AgentStreamType.DELIBERATIVE: "Deep analysis",
            AgentStreamType.BACKGROUND: "Background task",
        }[stream.stream_type]
        return f"[{stream.name.upper()}:{type_label}] Processing: {task[:80]}"

    def _run_background_stream(
        self, stream: AgentStream, task: str, broadcast: str
    ) -> dict:
        """Background cerebellar streams — run automated skills."""
        results = []
        for skill_name, automation in self.automation_registry.items():
            if automation.mastery_score >= MASTERY_THRESHOLD:
                results.append(f"{skill_name}:automated")
        return {
            "stream": stream.name,
            "skills_run": results,
            "output": f"[BACKGROUND] {len(results)} automated skills active",
        }

    def _integrate(
        self, broadcast: str, background_results: list[dict], task: str
    ) -> str:
        """Merge broadcast signal with background processing results."""
        parts = [f"WORKSPACE: {broadcast[:200]}"]
        for bg in background_results:
            if bg.get("skills_run"):
                parts.append(f"BACKGROUND: {bg['output']}")
        return "\n".join(parts)

    @staticmethod
    def _sigmoid(x: float) -> float:
        return 1.0 / (1.0 + math.exp(-x))

    @staticmethod
    def _hash_to_float(s: str) -> float:
        """Map string to float in [0, 1] via hash."""
        return (hash(s) % 10000) / 10000.0


class SkillAutomationTransfer:
    """
    Algorithm 2: SKILL_AUTOMATION_TRANSFER

    Tracks skill invocation mastery. When mastery >= MASTERY_THRESHOLD,
    the skill is delegated to background cerebellar processing,
    freeing the serial Qalb bottleneck for novel tasks.

    Mastery score: exponential moving average of success rate.
    mastery(t+1) = α·success(t) + (1-α)·mastery(t)
    """

    ALPHA = 0.15  # EMA learning rate

    def __init__(self):
        self.skill_stats: dict[str, dict] = {}
        self.automated: dict[str, SkillAutomation] = {}

    def record_invocation(
        self, skill_name: str, success: bool, latency_ms: float
    ) -> bool:
        """Record a skill invocation. Returns True if newly automated."""
        if skill_name not in self.skill_stats:
            self.skill_stats[skill_name] = {
                "mastery": 0.0,
                "count": 0,
                "total_latency": 0.0,
            }

        stats = self.skill_stats[skill_name]
        stats["count"] += 1
        stats["total_latency"] += latency_ms
        stats["mastery"] = (
            self.ALPHA * (1.0 if success else 0.0)
            + (1.0 - self.ALPHA) * stats["mastery"]
        )

        # Check if ready for automation
        if (
            stats["mastery"] >= MASTERY_THRESHOLD
            and skill_name not in self.automated
            and stats["count"] >= 5
        ):
            avg_latency = stats["total_latency"] / stats["count"]
            self.automated[skill_name] = SkillAutomation(
                skill_name=skill_name,
                mastery_score=stats["mastery"],
                invocation_count=stats["count"],
                avg_latency_ms=avg_latency,
                transferred_at=time.time(),
            )
            logger.info(
                "[AUTOMATION] Skill '%s' transferred to background (mastery=%.2f)",
                skill_name, stats["mastery"],
            )
            return True
        return False

    def is_automated(self, skill_name: str) -> bool:
        return skill_name in self.automated

    def get_mastery(self, skill_name: str) -> float:
        return self.skill_stats.get(skill_name, {}).get("mastery", 0.0)

    def get_automated_skills(self) -> list[str]:
        return list(self.automated.keys())

    def to_dict(self) -> dict:
        return {
            "tracked_skills": len(self.skill_stats),
            "automated_skills": len(self.automated),
            "automation_threshold": MASTERY_THRESHOLD,
            "skills": {
                name: {
                    "mastery": round(stats["mastery"], 3),
                    "count": stats["count"],
                    "automated": name in self.automated,
                }
                for name, stats in self.skill_stats.items()
            },
        }
