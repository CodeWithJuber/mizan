"""
Basira Engine (بصيرة) — Insight & Self-Witnessing
===================================================

"I call to Allah upon clear insight (basira), I and those who follow me."
— Quran 12:108
"Rather, the human, against himself, is a witness (basira)." — Quran 75:14

Basira is *inner sight* — discernment of the real situation behind the surface,
plus the conscience that witnesses one's own reasoning. Where Lubb checks the
*quality* of a trace and Fu'ad measures *conviction* from evidence, Basira asks
two harder questions:

  1. Is this conclusion actually *sound*, or does it merely look confident?
  2. Is my own reasoning *self-serving* — am I believing what I want to believe?

It synthesizes three upstream signals into one discernment:
  - coherence  (from Lubb metacognition)
  - conviction (from Fu'ad evidence assessment)
  - evidence density + self-witness scan (computed here)

Basira does not replace Lubb or Fu'ad; it integrates them and adds the
self-witnessing dimension (75:14) that neither covers.
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("mizan.basira")


class InsightLevel(Enum):
    CLEAR = "clear"  # Sound reasoning, grounded in evidence, no self-deception
    PARTIAL = "partial"  # Reasonable but with blind spots or thin evidence
    CLOUDED = "clouded"  # Unsound, self-serving, or unsupported — do not trust


# Phrases where the agent praises/justifies its *own* reasoning rather than the
# evidence — the marker of a self-serving (non-witnessing) trace (cf. 75:14).
_SELF_SERVING_SIGNALS = [
    "as i expected",
    "as i predicted",
    "i was right",
    "this proves i",
    "just as i said",
    "i already knew",
    "obviously correct",
    "clearly i",
    "my answer is definitely",
    "no need to check",
    "no need to verify",
    "i'm confident this is correct",
]

# Words that signal the *surface* hides a risk the reasoning may be glossing over.
_HIDDEN_RISK_SIGNALS = [
    "error",
    "failed",
    "exception",
    "denied",
    "timeout",
    "not found",
    "null",
    "undefined",
    "conflict",
    "deprecated",
]

# Words that signal the agent considered alternatives / its own fallibility —
# the *presence* of witnessing. These raise discernment.
_WITNESS_SIGNALS = [
    "however",
    "on the other hand",
    "alternatively",
    "i might be wrong",
    "let me verify",
    "let me check",
    "this assumes",
    "one caveat",
    "to confirm",
    "counterexample",
    "if instead",
]


@dataclass
class DiscernmentReport:
    """Result of a Basira discernment pass."""

    level: InsightLevel
    soundness: float  # 0.0 – 1.0, overall trustworthiness
    is_self_serving: bool  # True if the trace believes-what-it-wants
    deeper_reading: str  # what the surface may be hiding
    blind_spots: list[str] = field(default_factory=list)
    witnessing_score: float = 0.0  # 0 = no self-scrutiny, 1 = strong
    recommendation: str = ""  # actionable next step

    def to_dict(self) -> dict:
        return {
            "level": self.level.value,
            "soundness": round(self.soundness, 3),
            "is_self_serving": self.is_self_serving,
            "witnessing_score": round(self.witnessing_score, 3),
            "blind_spots": self.blind_spots[:5],
            "deeper_reading": self.deeper_reading,
            "recommendation": self.recommendation,
        }


class BasiraEngine:
    """
    Inner-sight discernment for the MIZAN reasoning system.

    Usage:
        basira = BasiraEngine()
        report = basira.discern(
            trace=response_text,
            evidence=["tool:bash:...", "tool:http_get:..."],
            coherence_score=lubb_report.coherence.score,
            conviction_confidence=fuad_assessment.confidence,
        )
        if report.level is InsightLevel.CLOUDED:
            # re-examine before trusting the conclusion
            ...
    """

    # Soundness blend weights — coherence, conviction, evidence density
    _W_COHERENCE = 0.4
    _W_CONVICTION = 0.35
    _W_EVIDENCE = 0.25

    def discern(
        self,
        trace: str,
        evidence: list[str] | None = None,
        coherence_score: float | None = None,
        conviction_confidence: float | None = None,
        task: str = "",
    ) -> DiscernmentReport:
        """
        Form a discernment from a reasoning trace and its supporting signals.

        coherence_score / conviction_confidence are optional — when not supplied
        (e.g. Lubb/Fu'ad not run), Basira falls back to its own estimates so it
        is usable standalone.
        """
        evidence = evidence or []
        trace = trace or ""
        lower = trace.lower()

        # 1. Self-witnessing scan (75:14) — does the trace scrutinize itself?
        self_serving_hits = [s for s in _SELF_SERVING_SIGNALS if s in lower]
        witness_hits = [w for w in _WITNESS_SIGNALS if w in lower]
        is_self_serving = bool(self_serving_hits) and not witness_hits
        witnessing_score = self._witnessing_score(witness_hits, self_serving_hits)

        # 2. Evidence density — strong claims need backing
        evidence_density = self._evidence_density(trace, evidence)

        # 3. Deeper reading — does the surface hide a risk the conclusion ignores?
        deeper_reading, surface_mismatch = self._read_beneath(trace, task)

        # 4. Blind spots
        blind_spots = self._find_blind_spots(trace, evidence, self_serving_hits, surface_mismatch)

        # 5. Soundness blend (fall back to internal estimates when missing)
        coherence = (
            coherence_score if coherence_score is not None else self._estimate_coherence(trace)
        )
        conviction = (
            conviction_confidence if conviction_confidence is not None else evidence_density
        )
        soundness = (
            self._W_COHERENCE * coherence
            + self._W_CONVICTION * conviction
            + self._W_EVIDENCE * evidence_density
        )
        # Penalties: self-deception and surface mismatch corrode discernment
        if is_self_serving:
            soundness -= 0.20
        if surface_mismatch:
            soundness -= 0.15
        soundness -= 0.05 * len(blind_spots)
        # Reward genuine self-witnessing
        soundness += 0.05 * min(2, len(witness_hits))
        soundness = max(0.0, min(1.0, soundness))

        # 6. Classify
        if soundness >= 0.7 and not is_self_serving:
            level = InsightLevel.CLEAR
        elif soundness >= 0.45:
            level = InsightLevel.PARTIAL
        else:
            level = InsightLevel.CLOUDED

        recommendation = self._recommend(level, is_self_serving, blind_spots, surface_mismatch)

        logger.debug(
            "[BASIRA] level=%s soundness=%.2f self_serving=%s blind_spots=%d",
            level.value,
            soundness,
            is_self_serving,
            len(blind_spots),
        )
        return DiscernmentReport(
            level=level,
            soundness=round(soundness, 3),
            is_self_serving=is_self_serving,
            deeper_reading=deeper_reading,
            blind_spots=blind_spots[:5],
            witnessing_score=round(witnessing_score, 3),
            recommendation=recommendation,
        )

    # ── internals ──────────────────────────────────────────────

    @staticmethod
    def _witnessing_score(witness_hits: list[str], self_serving_hits: list[str]) -> float:
        """0 = no self-scrutiny, 1 = strong self-witnessing (more witness, less self-serving)."""
        score = 0.5 + 0.15 * len(witness_hits) - 0.20 * len(self_serving_hits)
        return max(0.0, min(1.0, score))

    @staticmethod
    def _evidence_density(trace: str, evidence: list[str]) -> float:
        """
        How well-grounded the trace is. Counts explicit tool evidence and
        external references against the volume of assertion.
        """
        tool_refs = trace.lower().count("[tool:") + len(evidence)
        url_refs = len(re.findall(r"https?://", trace))
        grounded = tool_refs + url_refs
        if grounded == 0:
            # No evidence at all — density floor depends on claim strength
            strong_claims = len(
                re.findall(r"\b(definitely|certainly|always|never|guaranteed)\b", trace.lower())
            )
            return max(0.1, 0.4 - 0.1 * strong_claims)
        # Each independent piece of grounding closes 30% of the gap to 1.0
        density = 0.4
        for _ in range(min(grounded, 6)):
            density += (1.0 - density) * 0.30
        return min(0.95, density)

    @staticmethod
    def _estimate_coherence(trace: str) -> float:
        """Lightweight standalone coherence estimate when Lubb is unavailable."""
        if not trace:
            return 0.3
        overconfident = len(
            re.findall(r"\b(definitely|certainly|100%|guaranteed|impossible)\b", trace.lower())
        )
        return max(0.3, 0.75 - 0.1 * overconfident)

    @staticmethod
    def _read_beneath(trace: str, task: str) -> tuple[str, bool]:
        """
        Look beneath the surface: if the trace/task contains risk signals but the
        conclusion sounds untroubled, that mismatch is what Basira should surface.
        """
        combined = (task + " " + trace).lower()
        risks = [r for r in _HIDDEN_RISK_SIGNALS if r in combined]
        sounds_fine = any(
            p in trace.lower()
            for p in ["success", "done", "completed", "works", "all good", "no problem"]
        )
        if risks and sounds_fine:
            return (
                f"Surface reads as success, but the trace contains risk signals "
                f"({', '.join(risks[:3])}). The real situation may be unresolved.",
                True,
            )
        if risks:
            return (
                f"Underlying risk signals present: {', '.join(risks[:3])}. "
                f"Confirm these are actually handled.",
                False,
            )
        return ("Surface and substance appear aligned.", False)

    @staticmethod
    def _find_blind_spots(
        trace: str,
        evidence: list[str],
        self_serving_hits: list[str],
        surface_mismatch: bool,
    ) -> list[str]:
        spots: list[str] = []
        lower = trace.lower()

        if not evidence and "[tool:" not in lower and len(trace) > 200:
            spots.append("Conclusion drawn without any tool/external evidence")
        if self_serving_hits:
            spots.append(
                f"Self-confirming language ({self_serving_hits[0]}) — possible motivated reasoning"
            )
        if surface_mismatch:
            spots.append("Optimistic conclusion despite unresolved risk signals")
        # Single-source reliance
        if len(evidence) == 1:
            spots.append("Single source of evidence — no independent corroboration")
        # No counterfactual considered
        if not any(
            w in lower for w in ["if not", "otherwise", "what if", "unless", "could be wrong"]
        ):
            if len(trace) > 150:
                spots.append("No counterfactual considered ('what if this is wrong?')")
        return spots

    @staticmethod
    def _recommend(
        level: InsightLevel,
        is_self_serving: bool,
        blind_spots: list[str],
        surface_mismatch: bool,
    ) -> str:
        if level is InsightLevel.CLEAR:
            return "Discernment is clear — proceed, stating confidence honestly."
        if is_self_serving:
            return (
                "Step back from the conclusion you want to be true; seek a "
                "counterexample or independent check before committing."
            )
        if surface_mismatch:
            return "Verify the unresolved risk signals before reporting success."
        if blind_spots:
            return f"Address the blind spot first: {blind_spots[0]}"
        return "Gather one more independent piece of evidence to firm up the conclusion."
