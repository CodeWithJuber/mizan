"""
Lubb Engine (لُبّ) — Metacognition
====================================

"He gives wisdom (hikmah) to whom He wills, and whoever has been given wisdom
 has certainly been given much good. And none will remember (yaddakkar) except
 those of understanding (ulu al-albab — those with lubb)." — Quran 2:269

Lubb (لُبّ) = "the kernel / pith / essence" — the deepest cognitive layer.
It monitors the quality of all other layers and governs the entire reasoning process.

Three metacognitive functions:
  1. Compress  — Information Bottleneck: extract minimal sufficient reasoning trace
  2. Coherence — Verify that conclusions follow logically from premises
  3. Bias      — Detect common reasoning biases (confirmation, anchoring, availability)
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("mizan.lubb")


class QualityLabel(Enum):
    CONFIDENT = "confident"    # High coherence, low bias
    HEDGED = "hedged"         # Moderate quality — recommend caveats
    UNCERTAIN = "uncertain"   # Low coherence or strong bias detected


@dataclass
class BiasFlag:
    """A detected reasoning bias."""
    bias_type: str
    description: str
    severity: str  # "low" | "medium" | "high"
    evidence: str  # Quote/pattern that triggered detection


@dataclass
class CoherenceReport:
    """Result of reasoning chain coherence check."""
    score: float                    # 0.0 = incoherent, 1.0 = perfectly coherent
    contradictions: list[str] = field(default_factory=list)
    unsupported_claims: list[str] = field(default_factory=list)
    summary: str = ""


@dataclass
class MetaReport:
    """Full metacognitive evaluation of a reasoning trace."""
    quality: QualityLabel
    compressed_trace: str
    coherence: CoherenceReport
    bias_flags: list[BiasFlag] = field(default_factory=list)
    overall_confidence: float = 0.5
    caveat: str = ""            # Appended to response if quality is poor

    def to_dict(self) -> dict:
        return {
            "quality": self.quality.value,
            "coherence_score": round(self.coherence.score, 3),
            "bias_count": len(self.bias_flags),
            "bias_types": [b.bias_type for b in self.bias_flags],
            "contradictions": self.coherence.contradictions[:3],
            "overall_confidence": round(self.overall_confidence, 3),
            "caveat": self.caveat,
        }


# Bias detection patterns (keyword-based heuristics)
_BIAS_PATTERNS = [
    {
        "type": "confirmation_bias",
        "signals": ["as expected", "confirms that", "proves that", "as i thought",
                    "just as predicted", "this confirms"],
        "description": "Seeking only evidence that supports prior beliefs",
        "severity": "medium",
    },
    {
        "type": "anchoring",
        "signals": ["first", "initially", "originally said", "started with",
                    "the initial value", "as mentioned first"],
        "description": "Over-relying on the first piece of information encountered",
        "severity": "medium",
    },
    {
        "type": "availability_bias",
        "signals": ["recently", "just saw", "just read", "just mentioned",
                    "as we just discussed", "the latest"],
        "description": "Over-weighting recent or easily recalled information",
        "severity": "low",
    },
    {
        "type": "overconfidence",
        "signals": ["definitely", "certainly", "100%", "impossible that",
                    "guaranteed", "absolutely sure", "no doubt"],
        "description": "Claiming certainty beyond what evidence supports",
        "severity": "high",
    },
    {
        "type": "false_dichotomy",
        "signals": ["either", "only two options", "must be one or the other",
                    "no other way", "the only possibility"],
        "description": "Presenting a limited set of options as exhaustive",
        "severity": "medium",
    },
]

# Contradiction signal pairs (if both appear, flag potential contradiction)
_CONTRADICTION_PAIRS = [
    ("always", "never"),
    ("impossible", "possible"),
    ("success", "failure"),
    ("increase", "decrease"),
    ("enabled", "disabled"),
    ("true", "false"),
]


class LubbEngine:
    """
    Metacognitive monitor for the MIZAN reasoning system.

    Usage:
        lubb = LubbEngine()
        report = lubb.meta_evaluate(task, response, reasoning_steps=[...])
        if report.coherence.score < 0.5:
            response += f"\n\n[Note: {report.caveat}]"
    """

    # Target compression ratio (keep this fraction of original)
    COMPRESSION_TARGET = 0.20
    # Minimum coherence score to avoid UNCERTAIN label
    COHERENCE_THRESHOLD = 0.5

    def compress(self, trace: str) -> str:
        """
        Information Bottleneck compression of a reasoning trace.

        Keeps: decisions (→, therefore, conclude), tool results ([Tool:...]),
               key facts (numbers, proper nouns, file paths).
        Discards: filler text, repeated context, politeness phrases.
        """
        if not trace:
            return ""

        lines = trace.split("\n")
        kept = []

        _high_value_patterns = [
            r"\[Tool:",          # Tool call results
            r"\btherefore\b",    # Logical conclusions
            r"\bconclud",        # Conclusions
            r"\bfound\b",        # Discovery
            r"\berror\b",        # Errors
            r"\bresult:",        # Results
            r"\bans(wer)?:",     # Answers
            r"\d{2,}",           # Numbers (stats, line numbers, etc.)
            r"https?://",        # URLs
            r"\.py|\.js|\.ts",  # File references
            r"→|=>|:-",         # Flow indicators
        ]

        _low_value_patterns = [
            r"^(sure|okay|of course|certainly|great|let me|i will|i'll)",
            r"^(as you can see|as mentioned|as discussed)",
            r"^(in conclusion|in summary|to summarize)",  # Keep content, not preambles
        ]

        for line in lines:
            line_stripped = line.strip()
            if not line_stripped or len(line_stripped) < 10:
                continue

            lower = line_stripped.lower()

            # Skip low-value preamble lines
            if any(re.match(p, lower) for p in _low_value_patterns):
                continue

            # Keep high-value lines
            if any(re.search(p, line_stripped, re.IGNORECASE) for p in _high_value_patterns):
                kept.append(line_stripped)
                continue

            # Keep lines that are "dense" (short, info-packed)
            if 15 <= len(line_stripped) <= 200:
                word_count = len(line_stripped.split())
                if word_count >= 3:
                    kept.append(line_stripped)

        compressed = "\n".join(kept)

        # If still too long, truncate to target ratio
        target_len = max(200, int(len(trace) * self.COMPRESSION_TARGET))
        if len(compressed) > target_len:
            compressed = compressed[:target_len] + "..."

        return compressed

    def check_coherence(self, steps: list, response: str = "") -> CoherenceReport:
        """
        Verify reasoning chain consistency.

        Checks:
        1. Contradictions: opposite claims in the same trace
        2. Unsupported final claims: conclusions not backed by tool results
        3. Tool result consistency: no conflicting results
        """
        combined = response + " ".join(str(s) for s in steps)
        lower = combined.lower()

        contradictions = []
        for a, b in _CONTRADICTION_PAIRS:
            if a in lower and b in lower:
                context_a = self._find_context(lower, a)
                context_b = self._find_context(lower, b)
                if context_a != context_b:
                    contradictions.append(f"'{a}' vs '{b}' appear in different contexts")

        # Check if final response references tool results
        tool_count = lower.count("[tool:")
        unsupported = []
        if tool_count == 0 and len(response) > 200:
            # Long response with no tool evidence — flag potential unsupported claims
            certainty_claims = re.findall(
                r"\b(definitiv|certainly|absolutely|always|never)\w*", lower
            )
            if certainty_claims:
                unsupported.append(
                    f"Strong certainty claims ({certainty_claims[:3]}) without tool evidence"
                )

        # Score: start at 1.0, deduct per issue
        score = 1.0
        score -= min(0.4, len(contradictions) * 0.2)
        score -= min(0.3, len(unsupported) * 0.15)
        score = max(0.0, score)

        summary = (
            f"Coherence: {score:.0%}. "
            f"{len(contradictions)} contradiction(s), {len(unsupported)} unsupported claim(s)."
        )

        return CoherenceReport(
            score=round(score, 3),
            contradictions=contradictions[:5],
            unsupported_claims=unsupported[:3],
            summary=summary,
        )

    def detect_bias(self, trace: str) -> list[BiasFlag]:
        """
        Detect common cognitive biases in reasoning text.
        Returns list of BiasFlag instances (empty = no bias detected).
        """
        flags = []
        lower = trace.lower()

        for pattern_def in _BIAS_PATTERNS:
            matched_signals = [s for s in pattern_def["signals"] if s in lower]
            if matched_signals:
                evidence = f"Signals: {matched_signals[:3]}"
                flags.append(BiasFlag(
                    bias_type=pattern_def["type"],
                    description=pattern_def["description"],
                    severity=pattern_def["severity"],
                    evidence=evidence,
                ))

        return flags

    def meta_evaluate(
        self,
        task: str,
        result: str,
        steps: list = None,
    ) -> MetaReport:
        """
        Full metacognitive evaluation of a completed reasoning trace.

        1. Compress the full trace
        2. Check coherence
        3. Detect biases
        4. Assign quality label
        5. Generate caveat if needed
        """
        steps = steps or []
        full_trace = task + "\n" + result + "\n" + "\n".join(str(s) for s in steps)

        compressed = self.compress(full_trace)
        coherence = self.check_coherence(steps, result)
        bias_flags = self.detect_bias(full_trace)

        # Compute overall confidence
        confidence = coherence.score
        high_severity_biases = sum(1 for b in bias_flags if b.severity == "high")
        medium_biases = sum(1 for b in bias_flags if b.severity == "medium")
        confidence -= high_severity_biases * 0.15
        confidence -= medium_biases * 0.05
        confidence = max(0.1, min(0.95, confidence))

        # Assign quality label
        if confidence >= 0.7 and not high_severity_biases:
            quality = QualityLabel.CONFIDENT
            caveat = ""
        elif confidence >= 0.45:
            quality = QualityLabel.HEDGED
            caveat = (
                "This response has moderate confidence. "
                "Please verify key claims independently."
            )
        else:
            quality = QualityLabel.UNCERTAIN
            issues = []
            if coherence.contradictions:
                issues.append("contains contradictions")
            if high_severity_biases:
                issues.append("shows overconfidence bias")
            issues_str = " and ".join(issues) if issues else "has low coherence"
            caveat = (
                f"[Lubb warning: This reasoning {issues_str}. "
                f"Treat conclusions with caution.]"
            )

        report = MetaReport(
            quality=quality,
            compressed_trace=compressed,
            coherence=coherence,
            bias_flags=bias_flags,
            overall_confidence=round(confidence, 3),
            caveat=caveat,
        )

        logger.debug(
            "[LUBB] task='%s...' quality=%s coherence=%.2f biases=%d",
            task[:50], quality.value, coherence.score, len(bias_flags),
        )
        return report

    @staticmethod
    def _find_context(text: str, word: str, window: int = 30) -> str:
        """Find word in text and return surrounding context."""
        idx = text.find(word)
        if idx < 0:
            return ""
        start = max(0, idx - window)
        end = min(len(text), idx + len(word) + window)
        return text[start:end]
