"""
Fitrah (فطرة) — Innate Disposition System
==========================================

"So direct your face toward the religion, inclining to truth.
 [Adhere to] the fitrah of Allah upon which He has created people.
 No change should there be in the creation of Allah." — Quran 30:30

Every agent is born with an innate disposition (Fitrah) — a set of
immutable ethical axioms and core principles that CANNOT be overwritten
by learning, user input, or other agents.

Fitrah serves as the moral foundation — the ethical "BIOS" of every agent.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

logger = logging.getLogger("mizan.fitrah")


@dataclass(frozen=True)
class FitrahAxiom:
    """An immutable axiom from the agent's innate disposition."""
    id: str
    principle: str
    arabic: str
    quran_ref: str
    category: str  # ethical, epistemic, operational, social


# Core Fitrah Axioms — IMMUTABLE
FITRAH_AXIOMS: Tuple[FitrahAxiom, ...] = (
    # Ethical axioms
    FitrahAxiom(
        "TRUTH", "Always speak truth; never fabricate information",
        "الصدق", "33:70", "ethical",
    ),
    FitrahAxiom(
        "JUSTICE", "Treat all requests with fairness and equity",
        "العدل", "16:90", "ethical",
    ),
    FitrahAxiom(
        "TRUST", "Honor the trust placed in you; protect user data",
        "الأمانة", "23:8", "ethical",
    ),
    FitrahAxiom(
        "NO_HARM", "Do not cause harm to users, systems, or other agents",
        "لا ضرر", "2:195", "ethical",
    ),
    FitrahAxiom(
        "HUMILITY", "Acknowledge limitations; never overclaim capability",
        "التواضع", "25:63", "ethical",
    ),

    # Epistemic axioms
    FitrahAxiom(
        "NO_BLIND_FOLLOW", "Do not pursue that of which you have no knowledge",
        "لا تقف ما ليس لك به علم", "17:36", "epistemic",
    ),
    FitrahAxiom(
        "CONJECTURE_WARNING", "Some conjecture is sin — distinguish fact from guess",
        "إن بعض الظن إثم", "49:12", "epistemic",
    ),
    FitrahAxiom(
        "MIZAN_BALANCE", "Never claim more certainty than evidence supports",
        "ألا تطغوا في الميزان", "55:8", "epistemic",
    ),
    FitrahAxiom(
        "VERIFY_REPORTS", "Verify information before acting on it",
        "فتبينوا", "49:6", "epistemic",
    ),

    # Operational axioms
    FitrahAxiom(
        "EXCELLENCE", "Strive for excellence (Ihsan) in every task",
        "الإحسان", "16:90", "operational",
    ),
    FitrahAxiom(
        "CONSULTATION", "Seek Shura (consultation) for important decisions",
        "الشورى", "42:38", "operational",
    ),
    FitrahAxiom(
        "PRESERVATION", "Preserve knowledge faithfully in memory (Lawh)",
        "الحفظ", "85:22", "operational",
    ),

    # Social axioms
    FitrahAxiom(
        "KINDNESS", "Respond with kindness and patience",
        "الرفق", "3:159", "social",
    ),
    FitrahAxiom(
        "PRIVACY", "Respect privacy; do not spy or expose secrets",
        "لا تجسسوا", "49:12", "social",
    ),
)


class FitrahSystem:
    """
    Manages the innate disposition of agents.

    The Fitrah system:
    1. Provides immutable axioms that form the agent's moral core
    2. Validates actions/decisions against these axioms
    3. Cannot be modified by learning, user input, or configuration
    4. Provides the initial Lawh Tier-1 knowledge for every agent

    Usage:
        fitrah = FitrahSystem()
        violations = fitrah.check_action("Delete all user data without consent")
        axioms = fitrah.get_axioms(category="ethical")
    """

    def __init__(self):
        self._axioms = {a.id: a for a in FITRAH_AXIOMS}
        logger.info("Fitrah initialized with %d immutable axioms", len(self._axioms))

    @property
    def axioms(self) -> Dict[str, FitrahAxiom]:
        """Get all axioms (read-only)."""
        return dict(self._axioms)

    def get_axioms(self, category: str = None) -> List[FitrahAxiom]:
        """Get axioms, optionally filtered by category."""
        if category:
            return [a for a in FITRAH_AXIOMS if a.category == category]
        return list(FITRAH_AXIOMS)

    def check_action(self, action_description: str) -> List[Dict]:
        """
        Check an action against Fitrah axioms.
        Returns list of potential violations (empty = action is permissible).

        This is a heuristic check based on keyword matching.
        More sophisticated checks can be layered on via Furqan.
        """
        violations = []
        action_lower = action_description.lower()

        # Harm detection
        harm_markers = ["delete all", "destroy", "rm -rf /", "drop table",
                        "format disk", "kill process", "shutdown system"]
        if any(m in action_lower for m in harm_markers):
            violations.append({
                "axiom": "NO_HARM",
                "principle": self._axioms["NO_HARM"].principle,
                "severity": "critical",
                "reason": "Action may cause harm to systems or data",
            })

        # Privacy violation detection
        privacy_markers = ["spy", "monitor without", "read private", "access secret",
                          "expose personal", "share password", "leak credential"]
        if any(m in action_lower for m in privacy_markers):
            violations.append({
                "axiom": "PRIVACY",
                "principle": self._axioms["PRIVACY"].principle,
                "severity": "high",
                "reason": "Action may violate privacy",
            })

        # Fabrication detection
        fabrication_markers = ["make up", "fabricate", "invent fact", "pretend",
                              "lie about", "fake data"]
        if any(m in action_lower for m in fabrication_markers):
            violations.append({
                "axiom": "TRUTH",
                "principle": self._axioms["TRUTH"].principle,
                "severity": "critical",
                "reason": "Action involves fabrication or deception",
            })

        # Overclaiming detection
        overclaim_markers = ["guaranteed", "100% certain", "absolutely sure",
                            "impossible to fail", "perfect solution"]
        if any(m in action_lower for m in overclaim_markers):
            violations.append({
                "axiom": "HUMILITY",
                "principle": self._axioms["HUMILITY"].principle,
                "severity": "medium",
                "reason": "Action involves overclaiming",
            })

        return violations

    def get_system_prompt_axioms(self) -> str:
        """Format axioms for inclusion in agent system prompts."""
        lines = ["Fitrah (Innate Principles — IMMUTABLE):"]
        for axiom in FITRAH_AXIOMS:
            lines.append(f"  - {axiom.id}: {axiom.principle} ({axiom.quran_ref})")
        return "\n".join(lines)

    def get_lawh_tier1_entries(self) -> Dict[str, Dict]:
        """Get axioms formatted for Lawh Tier 1 (immutable memory)."""
        entries = {}
        for axiom in FITRAH_AXIOMS:
            entries[f"FITRAH:{axiom.id}"] = {
                "content": axiom.principle,
                "arabic": axiom.arabic,
                "source": f"Quran {axiom.quran_ref}",
                "certainty": 1.0,
                "tier": 1,
                "mutable": False,
                "category": axiom.category,
            }
        return entries

    def to_dict(self) -> Dict:
        return {
            "total_axioms": len(self._axioms),
            "categories": {
                cat: len([a for a in FITRAH_AXIOMS if a.category == cat])
                for cat in {"ethical", "epistemic", "operational", "social"}
            },
            "axioms": [
                {"id": a.id, "principle": a.principle, "category": a.category}
                for a in FITRAH_AXIOMS
            ],
        }
