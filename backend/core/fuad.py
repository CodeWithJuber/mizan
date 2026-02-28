"""
Fu'ad Engine (فؤاد) — Conviction Formation
==========================================

"And He gave you hearing and sight and hearts (af'idah — plural of fu'ad).
 Little are you grateful." — Quran 16:78

Fu'ad is the integrating heart — it forms *conviction* from accumulated evidence.
Unlike simple belief, conviction requires multiple independent sources and
temporal consistency before committing.

Three conviction levels (mapped to Yaqin):
  IMPRESSION  → Ilm al-Yaqin  (knowledge by inference — single source)
  BELIEF      → Ayn al-Yaqin  (knowledge by observation — 2+ sources)
  CONVICTION  → Haqq al-Yaqin (knowledge by experience — 3+ consistent sources)
"""

import hashlib
import logging
import time
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("mizan.fuad")


class ConvictionLevel(Enum):
    IMPRESSION = "impression"    # Single source — unverified
    BELIEF = "belief"           # 2+ independent sources
    CONVICTION = "conviction"   # 3+ sources + temporal consistency


@dataclass
class ConvictionAssessment:
    """Result of evidence evaluation."""
    claim: str
    level: ConvictionLevel
    confidence: float            # 0.0 – 1.0
    source_count: int
    supporting: list[str] = field(default_factory=list)
    contradicting: list[str] = field(default_factory=list)
    first_seen: float = field(default_factory=time.time)
    last_updated: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "claim": self.claim[:200],
            "level": self.level.value,
            "confidence": round(self.confidence, 3),
            "source_count": self.source_count,
            "supporting_count": len(self.supporting),
            "contradicting_count": len(self.contradicting),
            "temporal_span_hours": round(
                (self.last_updated - self.first_seen) / 3600, 2
            ),
        }


def _claim_hash(claim: str) -> str:
    """Stable ID for a claim (first 12 chars of sha256)."""
    return hashlib.sha256(claim.lower().strip().encode()).hexdigest()[:12]


def _are_independent(src_a: str, src_b: str) -> bool:
    """
    Heuristic: two sources are independent if they differ significantly.
    Same URL domain or identical string → not independent.
    """
    if src_a == src_b:
        return False
    # If both look like URLs, compare domain
    def _domain(s: str) -> str:
        try:
            return s.split("//")[-1].split("/")[0].lower()
        except Exception:
            return s[:20].lower()

    if src_a.startswith("http") and src_b.startswith("http"):
        return _domain(src_a) != _domain(src_b)
    # For non-URL sources, require at least 10-char difference
    return src_a[:10].lower() != src_b[:10].lower()


class FuadEngine:
    """
    Bayesian conviction formation from accumulated evidence.

    Usage:
        fuad = FuadEngine()
        assessment = fuad.evaluate_evidence(
            "Python is widely used for AI",
            ["tool:bash:result1", "tool:http_get:result2"]
        )
        # IMPRESSION if 1 source, BELIEF if 2+, CONVICTION if 3+ + time
    """

    # Minimum independent sources needed per level
    _MIN_SOURCES = {
        ConvictionLevel.BELIEF: 2,
        ConvictionLevel.CONVICTION: 3,
    }
    # Minimum hours between first and last sighting for CONVICTION
    _CONVICTION_MIN_HOURS = 0.1  # 6 minutes — practical for session use

    def __init__(self):
        # claim_hash → ConvictionAssessment
        self._assessments: dict[str, ConvictionAssessment] = {}

    def evaluate_evidence(
        self,
        claim: str,
        sources: list[str],
        contradicting_sources: list[str] = None,
    ) -> ConvictionAssessment:
        """
        Evaluate or update conviction for a claim.

        Algorithm:
        1. Count independent sources (different domains / names)
        2. Apply Bayesian prior: P(claim) starts at 0.5, updates per source
        3. Each independent supporting source × 1.5, contradicting × 0.6
        4. Classify: 1 source→IMPRESSION, 2+→BELIEF, 3++time→CONVICTION
        """
        key = _claim_hash(claim)
        contradicting_sources = contradicting_sources or []
        now = time.time()

        if key in self._assessments:
            existing = self._assessments[key]
            # Merge new sources
            all_supporting = list(set(existing.supporting + sources))
            all_contradicting = list(set(existing.contradicting + contradicting_sources))
            existing.supporting = all_supporting
            existing.contradicting = all_contradicting
            existing.last_updated = now
            assessment = existing
        else:
            assessment = ConvictionAssessment(
                claim=claim,
                level=ConvictionLevel.IMPRESSION,
                confidence=0.5,
                source_count=0,
                supporting=list(sources),
                contradicting=list(contradicting_sources),
                first_seen=now,
                last_updated=now,
            )
            self._assessments[key] = assessment

        # Count independent supporting sources
        independent_count = 0
        seen_sources = []
        for src in assessment.supporting:
            if all(_are_independent(src, prev) for prev in seen_sources):
                independent_count += 1
                seen_sources.append(src)

        assessment.source_count = independent_count

        # Bayesian confidence update
        confidence = 0.5
        for _ in range(independent_count):
            confidence = confidence + (1.0 - confidence) * 0.35  # Each source +35% of gap
        for _ in range(len(assessment.contradicting)):
            confidence = confidence * 0.70  # Each contradiction reduces by 30%
        confidence = max(0.05, min(0.97, confidence))
        assessment.confidence = confidence

        # Classify level
        temporal_span_hours = (assessment.last_updated - assessment.first_seen) / 3600
        if (
            independent_count >= self._MIN_SOURCES[ConvictionLevel.CONVICTION]
            and temporal_span_hours >= self._CONVICTION_MIN_HOURS
            and len(assessment.contradicting) == 0
        ):
            assessment.level = ConvictionLevel.CONVICTION
        elif independent_count >= self._MIN_SOURCES[ConvictionLevel.BELIEF]:
            assessment.level = ConvictionLevel.BELIEF
        else:
            assessment.level = ConvictionLevel.IMPRESSION

        logger.debug(
            "[FUAD] claim='%s...' level=%s conf=%.2f sources=%d",
            claim[:60], assessment.level.value, confidence, independent_count,
        )
        return assessment

    def compute_confidence(
        self,
        tool_count: int = 0,
        tool_results: list[dict] | None = None,
    ) -> float:
        """
        Compute overall confidence from tool evidence using Bayesian update.

        Each successful tool result acts as an independent evidence source.
        Replaces the hardcoded `0.5 + 0.1 * tool_count` formula.

        P(confident) = 0.5, then each evidence source closes 35% of the gap.
        Failed tool results penalize by 30%.
        """
        tool_results = tool_results or []
        confidence = 0.5

        # Count successful vs failed results
        successes = 0
        failures = 0
        for result in tool_results:
            content = str(result.get("content", ""))
            if '"error"' in content or content.startswith('{"error'):
                failures += 1
            else:
                successes += 1

        # If no parsed results, use tool_count as proxy for successes
        if not tool_results and tool_count > 0:
            successes = tool_count

        # Bayesian update: each success closes 35% of gap to 1.0
        for _ in range(successes):
            confidence = confidence + (1.0 - confidence) * 0.35

        # Each failure reduces by 30%
        for _ in range(failures):
            confidence = confidence * 0.70

        return max(0.05, min(0.95, round(confidence, 4)))

    def get_assessment(self, claim: str) -> ConvictionAssessment | None:
        """Retrieve existing assessment without updating."""
        return self._assessments.get(_claim_hash(claim))

    def stats(self) -> dict:
        levels = {level.value: 0 for level in ConvictionLevel}
        for a in self._assessments.values():
            levels[a.level.value] += 1
        return {
            "total_claims": len(self._assessments),
            "by_level": levels,
        }
