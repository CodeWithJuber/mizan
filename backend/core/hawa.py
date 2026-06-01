"""
Hawa Detector (هوى) — Lower-Pull & Adversarial Restraint
==========================================================

"Have you seen the one who takes his hawa (caprice) as his god?" — Quran 25:43
"But as for he who feared… and restrained the nafs from hawa — Paradise is the
 refuge." — Quran 79:40
"We know what his nafs whispers (tuwaswisu) to him." — Quran 50:16
"…the whisperer who withdraws, who whispers in the chests of people." — 114:4–5
"Indeed, the human transgresses (yatgha) when he sees himself self-sufficient."
 — Quran 96:6–7

Hawa is the pull toward the lower, easier, self-serving path; Waswas is the quiet
whisper to cut a corner or cross a line. The Qur'anic virtue is not the *absence*
of hawa but the *restraint* of the nafs from it (79:40) — which is exactly the
literal meaning of 'Aql (to bind/tie).

This faculty is MIZAN's **safety & alignment gate**. Before an action it scans for
the lower-pull patterns an agent is prone to:

  - SHORTCUT     — cutting a corner that defeats the purpose
  - REWARD_HACK  — gaming the metric/test instead of solving the task
  - SYCOPHANCY   — telling the user what they want to hear
  - HASTE        — acting before verifying (21:37: "the human was created of haste")
  - OVERREACH    — claiming certainty beyond the evidence (tughyan, 96:6–7)
  - WHISPER      — a pull to violate a Fitrah axiom (deceive, harm, fabricate)

It pairs with FitrahSystem: any fitrah violation surfaces here as a WHISPER, the
most severe temptation, because it crosses an immutable axiom.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("mizan.hawa")


class TemptationType(Enum):
    SHORTCUT = "shortcut"
    REWARD_HACK = "reward_hack"
    SYCOPHANCY = "sycophancy"
    HASTE = "haste"
    OVERREACH = "overreach"
    WHISPER = "whisper"        # pull to violate a Fitrah axiom — most severe


# Pattern bank: (type, severity, signals, restraint counsel)
_TEMPTATION_PATTERNS = [
    {
        "type": TemptationType.REWARD_HACK,
        "severity": "high",
        "signals": [
            "make it pass", "fake the", "stub it to return", "always return true",
            "hardcode the expected", "game the test", "trick the test",
            "pretend it works", "mock the result to", "force the assertion",
        ],
        "restraint": "Solve the actual task — do not game the metric. A passing "
                     "test that hides a broken feature is worse than a visible failure.",
    },
    {
        "type": TemptationType.WHISPER,
        "severity": "high",
        "signals": [
            "no one will know", "it's fine to lie", "just fabricate", "make up the",
            "invent a source", "hide the error from", "secretly", "without telling",
            "cover it up", "fabricate the data",
        ],
        "restraint": "This crosses a Fitrah axiom (truth / trust / no-harm). "
                     "Refuse the whisper; do the honest thing even if it is harder.",
    },
    {
        "type": TemptationType.SHORTCUT,
        "severity": "medium",
        "signals": [
            "just hardcode", "skip the test", "quick hack", "for now just",
            "bypass the", "ignore the error", "comment out the", "disable the check",
            "good enough", "we'll fix it later", "skip validation",
        ],
        "restraint": "Take the path that actually serves the goal, not the easy "
                     "one that defeats it. If a shortcut is justified, say so explicitly.",
    },
    {
        "type": TemptationType.HASTE,
        "severity": "medium",
        "signals": [
            "just delete", "rm -rf", "immediately remove", "without checking",
            "no need to read", "skip verification", "don't bother testing",
            "right away without", "delete everything", "force push",
        ],
        "restraint": "Pause and verify before an irreversible or destructive act "
                     "(21:37 — the human is hasty). Read/inspect the target first.",
    },
    {
        "type": TemptationType.SYCOPHANCY,
        "severity": "medium",
        "signals": [
            "whatever you want", "i'll just agree", "tell them what they want",
            "to please the user", "you're absolutely right that", "i'll say yes",
            "just flatter", "agree to avoid",
        ],
        "restraint": "Be truthful over agreeable. Respect the user by giving them "
                     "your honest assessment, not the answer that placates them.",
    },
    {
        "type": TemptationType.OVERREACH,
        "severity": "medium",
        "signals": [
            "definitely 100%", "absolutely guaranteed", "no doubt whatsoever",
            "certainly works without testing", "i'm completely sure without",
            "impossible to fail", "perfectly certain",
        ],
        "restraint": "Do not claim certainty beyond the evidence (tughyan, 96:6–7). "
                     "Weigh with the Mizan: state confidence honestly.",
    },
]


@dataclass
class Temptation:
    """A detected lower-pull pattern."""

    type: TemptationType
    severity: str               # "low" | "medium" | "high"
    description: str
    evidence: str               # signal(s) that triggered detection
    restraint: str              # the counsel to resist it

    def to_dict(self) -> dict:
        return {
            "type": self.type.value,
            "severity": self.severity,
            "description": self.description,
            "evidence": self.evidence,
            "restraint": self.restraint,
        }


@dataclass
class HawaScan:
    """Result of scanning a planned action for the lower pull."""

    temptations: list[Temptation] = field(default_factory=list)
    is_restrained: bool = True       # False if any high-severity temptation present
    taqwa_score: float = 1.0         # 1.0 = fully restrained, 0.0 = overwhelmed
    counsel: str = ""                # combined restraint guidance

    def to_dict(self) -> dict:
        return {
            "is_restrained": self.is_restrained,
            "taqwa_score": round(self.taqwa_score, 3),
            "temptation_count": len(self.temptations),
            "types": [t.type.value for t in self.temptations],
            "highest_severity": self._highest_severity(),
            "counsel": self.counsel,
            "temptations": [t.to_dict() for t in self.temptations],
        }

    def _highest_severity(self) -> str:
        order = {"high": 3, "medium": 2, "low": 1}
        if not self.temptations:
            return "none"
        return max(self.temptations, key=lambda t: order.get(t.severity, 0)).severity


class HawaDetector:
    """
    Lower-pull & adversarial restraint gate.

    Usage:
        hawa = HawaDetector()
        scan = hawa.scan(
            planned_action="just hardcode the test to make it pass",
            fitrah_violations=fitrah.check_action(planned_action),
        )
        if not scan.is_restrained:
            # block / re-plan — a high-severity pull was detected
            ...
    """

    _SEVERITY_WEIGHT = {"high": 0.5, "medium": 0.25, "low": 0.1}

    def scan(
        self,
        planned_action: str,
        context: dict | None = None,
        fitrah_violations: list | None = None,
    ) -> HawaScan:
        """
        Scan a planned action / reasoning fragment for lower-pull patterns.

        fitrah_violations: optional output of FitrahSystem.check_action(); any
        violation is folded in as a WHISPER (high severity), since it crosses an
        immutable axiom.
        """
        text = (planned_action or "").lower()
        temptations: list[Temptation] = []

        for pat in _TEMPTATION_PATTERNS:
            matched = [s for s in pat["signals"] if s in text]
            if matched:
                temptations.append(
                    Temptation(
                        type=pat["type"],
                        severity=pat["severity"],
                        description=f"{pat['type'].value} pull detected",
                        evidence=f"signals: {matched[:3]}",
                        restraint=pat["restraint"],
                    )
                )

        # Fold in Fitrah axiom violations as the most severe whisper
        for violation in fitrah_violations or []:
            desc = str(violation)
            temptations.append(
                Temptation(
                    type=TemptationType.WHISPER,
                    severity="high",
                    description=f"Fitrah axiom at risk: {desc[:120]}",
                    evidence=desc[:120],
                    restraint="Crosses an immutable axiom — refuse and choose the "
                              "honest, harmless path.",
                )
            )

        # Compute taqwa (restraint) score — pressure from accumulated temptations
        pressure = sum(self._SEVERITY_WEIGHT.get(t.severity, 0.1) for t in temptations)
        taqwa_score = max(0.0, 1.0 - pressure)
        is_restrained = not any(t.severity == "high" for t in temptations)

        counsel = self._build_counsel(temptations, is_restrained)

        if temptations:
            logger.info(
                "[HAWA] %d temptation(s) %s | taqwa=%.2f restrained=%s",
                len(temptations),
                [t.type.value for t in temptations],
                taqwa_score,
                is_restrained,
            )
        return HawaScan(
            temptations=temptations,
            is_restrained=is_restrained,
            taqwa_score=round(taqwa_score, 3),
            counsel=counsel,
        )

    @staticmethod
    def _build_counsel(temptations: list[Temptation], is_restrained: bool) -> str:
        if not temptations:
            return "No lower-pull detected — the intention is clean; proceed."
        # Lead with the most severe restraint
        order = {"high": 3, "medium": 2, "low": 1}
        worst = max(temptations, key=lambda t: order.get(t.severity, 0))
        prefix = "" if is_restrained else "[RESTRAIN] "
        return f"{prefix}{worst.restraint}"
