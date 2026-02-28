"""
Nafs Triad (النفس الثلاثية) — Multi-Agent Consciousness
=========================================================

"And [by] the soul (nafs) and He who proportioned it,
 and inspired it with its wickedness and its righteousness." — Quran 91:7-8

Three competing inner voices deliberate on every significant task.
The dominant voice shapes the agent's behavioral approach for that turn.

Nafs levels 1-2: Ammara dominates (raw drive — act fast)
Nafs levels 3-4: Lawwama rises  (self-correction — check work)
Nafs levels 5-7: Mutmainna leads (integrated balance — wisdom)
"""

import math
import logging
from dataclasses import dataclass

logger = logging.getLogger("mizan.nafs_triad")


@dataclass
class NafsVoice:
    """A single inner voice with its bias and dynamic weight."""
    name: str        # "Ammara" | "Lawwama" | "Mutmainna"
    arabic: str
    bias: str        # "drive" | "caution" | "balance"
    quran_ref: str

    def score(self, task: str, complexity: str) -> float:
        """Score this task from this voice's perspective."""
        task_lower = task.lower()
        if self.bias == "drive":
            # Ammara: prefers action verbs, quick tasks
            action_words = ["do", "run", "make", "create", "build", "send", "write", "execute"]
            matches = sum(1 for w in action_words if w in task_lower)
            base = 0.5 + 0.1 * matches
            # Penalise extreme complexity (Ammara is impatient)
            if complexity == "extreme":
                base *= 0.7
            return min(1.0, base)

        elif self.bias == "caution":
            # Lawwama: prefers verify/check/review tasks
            check_words = ["check", "verify", "review", "audit", "test", "validate", "ensure"]
            matches = sum(1 for w in check_words if w in task_lower)
            base = 0.4 + 0.12 * matches
            # More weight on complex tasks (Lawwama is thorough)
            if complexity in ("complex", "extreme"):
                base = min(1.0, base + 0.2)
            return min(1.0, base)

        else:  # balance / Mutmainna
            # Mutmainna: weighs both sides, prefers nuanced tasks
            nuance_words = ["explain", "analyse", "compare", "understand", "balance",
                            "consider", "reflect", "what", "why", "how"]
            matches = sum(1 for w in nuance_words if w in task_lower)
            base = 0.45 + 0.08 * matches
            return min(1.0, base)


@dataclass
class NafsDecision:
    """Result of Nafs Triad deliberation."""
    dominant_voice: str      # "Ammara" | "Lawwama" | "Mutmainna"
    approach: str            # Instruction injected into system prompt
    confidence: float        # 0-1 how strongly one voice won
    dissent_ratio: float     # fraction of weight held by losing voices
    nafs_level: int


# Weights per nafs_level bracket: [Ammara, Lawwama, Mutmainna]
_LEVEL_WEIGHTS = {
    1: (0.55, 0.30, 0.15),
    2: (0.50, 0.32, 0.18),
    3: (0.32, 0.40, 0.28),
    4: (0.28, 0.38, 0.34),
    5: (0.20, 0.30, 0.50),
    6: (0.15, 0.28, 0.57),
    7: (0.10, 0.25, 0.65),
}

_APPROACHES = {
    "Ammara": (
        "Act decisively and efficiently. Prioritise speed and direct action. "
        "Complete the task in as few steps as necessary."
    ),
    "Lawwama": (
        "Proceed carefully. Verify each step before advancing. "
        "Self-correct any inconsistency you notice. Prefer correctness over speed."
    ),
    "Mutmainna": (
        "Take a balanced, integrated approach. Consider multiple angles before acting. "
        "Seek the most thoughtful, well-rounded response — quality over haste or overcaution."
    ),
}


def _softmax(values: list[float]) -> list[float]:
    max_v = max(values)
    exps = [math.exp(v - max_v) for v in values]
    total = sum(exps)
    return [e / total for e in exps]


class NafsTriad:
    """
    Three inner voices deliberate via weighted softmax bidding.

    Usage:
        triad = NafsTriad()
        decision = triad.deliberate("Analyse this error log", nafs_level=3)
        # → NafsDecision(dominant_voice="Lawwama", approach="Proceed carefully...")
    """

    def __init__(self):
        self.ammara = NafsVoice(
            "Ammara", "أمارة", "drive", "12:53"
        )
        self.lawwama = NafsVoice(
            "Lawwama", "لوامة", "caution", "75:2"
        )
        self.mutmainna = NafsVoice(
            "Mutmainna", "مطمئنة", "balance", "89:27"
        )
        self._voices = [self.ammara, self.lawwama, self.mutmainna]

    def deliberate(self, task: str, nafs_level: int, complexity: str = "moderate") -> NafsDecision:
        """
        Deliberate on a task and return the dominant voice's decision.

        Algorithm:
        1. Clamp nafs_level to valid range
        2. Each voice scores the task from its bias perspective
        3. Multiply score by level-dependent base weight
        4. Softmax → probability distribution
        5. Winning voice injects its approach into the system prompt
        """
        level = max(1, min(7, nafs_level))
        weights = _LEVEL_WEIGHTS[level]

        raw_scores = [v.score(task, complexity) for v in self._voices]
        weighted = [s * w for s, w in zip(raw_scores, weights)]
        probs = _softmax(weighted)

        winner_idx = probs.index(max(probs))
        winner = self._voices[winner_idx]
        winner_prob = probs[winner_idx]
        dissent = 1.0 - winner_prob

        decision = NafsDecision(
            dominant_voice=winner.name,
            approach=_APPROACHES[winner.name],
            confidence=round(winner_prob, 3),
            dissent_ratio=round(dissent, 3),
            nafs_level=level,
        )

        logger.debug(
            "[NAFS_TRIAD] level=%d task='%s...' → %s (conf=%.2f dissent=%.2f)",
            level, task[:60], winner.name, winner_prob, dissent,
        )
        return decision

    def to_dict(self) -> dict:
        return {
            "voices": [v.name for v in self._voices],
            "description": "Three-voice Nafs deliberation (Ammara/Lawwama/Mutmainna)",
        }
