"""
Yaqin Engine (يقين) — Three Levels of Certainty
==================================================

"Nay, if you only knew with knowledge of certainty (Ilm al-Yaqin)." — Quran 102:5
"Then you will surely see it with the eye of certainty (Ayn al-Yaqin)." — 102:7
"Indeed, this is the truth of certainty (Haqq al-Yaqin)." — 56:95

Every piece of knowledge in MIZAN is tagged with its Yaqin level:

  Level 1: Ilm al-Yaqin (علم اليقين)  — Inferential knowledge from reasoning
  Level 2: Ayn al-Yaqin (عين اليقين)  — Witnessed knowledge from observation/tools
  Level 3: Haqq al-Yaqin (حق اليقين)  — Embodied knowledge from proven experience

This engine prevents hallucination by forcing agents to distinguish
what they infer vs. what they have actually verified.
"""

import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("mizan.yaqin")


class YaqinLevel(Enum):
    """Three levels of epistemic certainty from the Quran."""
    ILM_AL_YAQIN = "ilm_al_yaqin"    # Inferential — from reasoning/training
    AYN_AL_YAQIN = "ayn_al_yaqin"    # Witnessed — verified through tools/tests
    HAQQ_AL_YAQIN = "haqq_al_yaqin"  # Embodied — proven through repeated success


# Confidence range for each Yaqin level
YAQIN_RANGES = {
    YaqinLevel.ILM_AL_YAQIN: (0.3, 0.6),
    YaqinLevel.AYN_AL_YAQIN: (0.6, 0.9),
    YaqinLevel.HAQQ_AL_YAQIN: (0.9, 1.0),
}

YAQIN_NAMES = {
    YaqinLevel.ILM_AL_YAQIN: ("Ilm al-Yaqin", "علم اليقين", "Inferential Knowledge"),
    YaqinLevel.AYN_AL_YAQIN: ("Ayn al-Yaqin", "عين اليقين", "Witnessed Knowledge"),
    YaqinLevel.HAQQ_AL_YAQIN: ("Haqq al-Yaqin", "حق اليقين", "Embodied Truth"),
}


@dataclass
class YaqinTag:
    """A certainty tag attached to any knowledge claim or response."""
    level: YaqinLevel
    confidence: float
    source: str = ""             # What produced this knowledge
    evidence: List[str] = field(default_factory=list)  # Evidence trail
    verified_at: Optional[float] = None  # Timestamp of verification
    verification_count: int = 0  # Times independently verified
    pattern_id: Optional[str] = None  # If from Haqq, the pattern it matches

    def to_dict(self) -> Dict:
        name_info = YAQIN_NAMES[self.level]
        return {
            "level": self.level.value,
            "name": name_info[0],
            "arabic": name_info[1],
            "description": name_info[2],
            "confidence": round(self.confidence, 3),
            "source": self.source,
            "evidence_count": len(self.evidence),
            "verification_count": self.verification_count,
        }

    @property
    def label(self) -> str:
        """Human-readable label for display."""
        name = YAQIN_NAMES[self.level][0]
        return f"[{name} — {self.confidence:.0%}]"


class YaqinEngine:
    """
    Core certainty engine that tags knowledge with its epistemic level.

    Usage:
        engine = YaqinEngine()

        # Tag an inference
        tag = engine.tag_inference("Based on patterns, this has a bug")

        # Tag a tool-verified observation
        tag = engine.tag_observation("3 tests fail", source="pytest", evidence=["test_output.txt"])

        # Tag proven knowledge
        tag = engine.tag_proven("This fix works", pattern_id="null_check_fix", count=47)

        # Classify arbitrary confidence
        level = engine.classify(0.75)  # -> AYN_AL_YAQIN
    """

    def __init__(self):
        # Track proven patterns for Haqq al-Yaqin
        self._proven_patterns: Dict[str, Dict] = {}
        # Track verification history
        self._verification_log: List[Dict] = []

    def classify(self, confidence: float) -> YaqinLevel:
        """Classify a confidence score into a Yaqin level."""
        if confidence >= 0.9:
            return YaqinLevel.HAQQ_AL_YAQIN
        if confidence >= 0.6:
            return YaqinLevel.AYN_AL_YAQIN
        return YaqinLevel.ILM_AL_YAQIN

    def tag_inference(self, claim: str, confidence: float = 0.45,
                      source: str = "reasoning") -> YaqinTag:
        """
        Tag knowledge as Ilm al-Yaqin — inferential.
        Used when the agent reasons without direct verification.
        Confidence capped at 0.6 (cannot claim higher without evidence).
        """
        capped = min(confidence, 0.6)
        return YaqinTag(
            level=YaqinLevel.ILM_AL_YAQIN,
            confidence=capped,
            source=source,
            evidence=[f"Inference: {claim[:200]}"],
        )

    def tag_observation(self, claim: str, confidence: float = 0.75,
                        source: str = "tool",
                        evidence: List[str] = None) -> YaqinTag:
        """
        Tag knowledge as Ayn al-Yaqin — witnessed/observed.
        Used when the agent has verified through tools, tests, or direct observation.
        Confidence range: 0.6–0.9.
        """
        clamped = max(0.6, min(confidence, 0.9))
        tag = YaqinTag(
            level=YaqinLevel.AYN_AL_YAQIN,
            confidence=clamped,
            source=source,
            evidence=evidence or [f"Observed: {claim[:200]}"],
            verified_at=time.time(),
            verification_count=1,
        )
        self._verification_log.append({
            "claim": claim[:200],
            "level": "ayn",
            "source": source,
            "timestamp": time.time(),
        })
        return tag

    def tag_proven(self, claim: str, pattern_id: str,
                   count: int = 1, confidence: float = 0.95) -> YaqinTag:
        """
        Tag knowledge as Haqq al-Yaqin — embodied truth.
        Used when the agent has proven this pattern through repeated success.
        Requires pattern_id and verified success count.
        """
        # Update proven pattern registry
        if pattern_id not in self._proven_patterns:
            self._proven_patterns[pattern_id] = {
                "claim": claim[:200],
                "success_count": 0,
                "first_proven": time.time(),
            }
        self._proven_patterns[pattern_id]["success_count"] += count
        self._proven_patterns[pattern_id]["last_proven"] = time.time()

        total = self._proven_patterns[pattern_id]["success_count"]
        # Confidence scales with verification count
        scaled_confidence = min(1.0, 0.9 + (total / 1000.0))

        return YaqinTag(
            level=YaqinLevel.HAQQ_AL_YAQIN,
            confidence=max(0.9, min(scaled_confidence, confidence)),
            source=f"proven_pattern:{pattern_id}",
            evidence=[f"Proven {total} times: {claim[:100]}"],
            verified_at=time.time(),
            verification_count=total,
            pattern_id=pattern_id,
        )

    def promote(self, tag: YaqinTag, new_evidence: str,
                source: str = "verification") -> YaqinTag:
        """
        Promote a Yaqin tag to a higher level based on new evidence.
        Ilm -> Ayn (when verified), Ayn -> Haqq (when proven repeatedly).
        """
        tag.evidence.append(new_evidence)
        tag.verification_count += 1
        tag.verified_at = time.time()

        if tag.level == YaqinLevel.ILM_AL_YAQIN:
            # Promote to Ayn after verification
            tag.level = YaqinLevel.AYN_AL_YAQIN
            tag.confidence = max(0.6, tag.confidence + 0.2)
            tag.source = source
            logger.info("Yaqin promoted: Ilm -> Ayn (%s)", new_evidence[:50])

        elif tag.level == YaqinLevel.AYN_AL_YAQIN and tag.verification_count >= 10:
            # Promote to Haqq after 10+ verifications
            tag.level = YaqinLevel.HAQQ_AL_YAQIN
            tag.confidence = max(0.9, tag.confidence)
            logger.info("Yaqin promoted: Ayn -> Haqq (%d verifications)", tag.verification_count)

        return tag

    def demote(self, tag: YaqinTag, reason: str) -> YaqinTag:
        """
        Demote a Yaqin tag when contradicting evidence is found.
        Haqq -> Ayn (contradiction), Ayn -> Ilm (failed verification).
        """
        tag.evidence.append(f"DEMOTION: {reason}")

        if tag.level == YaqinLevel.HAQQ_AL_YAQIN:
            tag.level = YaqinLevel.AYN_AL_YAQIN
            tag.confidence = min(0.8, tag.confidence)
            logger.warning("Yaqin demoted: Haqq -> Ayn (%s)", reason[:50])

        elif tag.level == YaqinLevel.AYN_AL_YAQIN:
            tag.level = YaqinLevel.ILM_AL_YAQIN
            tag.confidence = min(0.5, tag.confidence)
            logger.warning("Yaqin demoted: Ayn -> Ilm (%s)", reason[:50])

        return tag

    def format_response_prefix(self, tag: YaqinTag) -> str:
        """Generate an epistemic prefix for agent responses."""
        name = YAQIN_NAMES[tag.level][0]
        if tag.level == YaqinLevel.ILM_AL_YAQIN:
            return f"[{name} — inference, {tag.confidence:.0%}] "
        if tag.level == YaqinLevel.AYN_AL_YAQIN:
            return f"[{name} — verified via {tag.source}, {tag.confidence:.0%}] "
        return f"[{name} — proven ({tag.verification_count}x), {tag.confidence:.0%}] "

    def get_proven_patterns(self) -> Dict[str, Dict]:
        """Get all proven patterns (Haqq al-Yaqin registry)."""
        return dict(self._proven_patterns)

    def stats(self) -> Dict:
        """Engine statistics."""
        return {
            "proven_patterns": len(self._proven_patterns),
            "total_verifications": len(self._verification_log),
        }
