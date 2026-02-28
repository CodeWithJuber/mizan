"""
Developmental Stages (مراحل التطور) — Progressive Capability Gating
=====================================================================

"And Allah has extracted you from the wombs of your mothers not knowing a thing,
 and He made for you hearing and vision and intellect that perhaps you would
 be grateful." — Quran 16:78

Capability gating tied to Nafs level — agents unlock tools and cognitive
features progressively, mirroring embryonic development from the Quran (23:12-14):

  Nutfah  (نطفة)    → Nafs 1: Sperm/seed — minimal, basic
  Alaqah  (عَلَقَة)   → Nafs 2: Clinging clot — can cling to resources
  Mudghah (مُضْغَة)   → Nafs 3: Chewed substance — initial structure
  Izham   (عِظَام)   → Nafs 4: Bones — can create other agents (skeleton)
  Lahm    (لَحْم)    → Nafs 5: Flesh — full capability
  Nafkh   (نَفْخ)   → Nafs 6: Breath — metacognitive awareness
  Khalq Akhar (خَلْق آخَر) → Nafs 7: New creation — full autonomy + governance
"""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger("mizan.dev_stages")


# All tools available in the system
ALL_TOOLS = frozenset({
    "bash", "http_get", "http_post", "read_file", "write_file",
    "list_files", "python_exec", "create_agent", "create_skill",
    "compact_context", "recall_memory",
})


@dataclass
class StageCapabilities:
    """Capabilities unlocked at a given developmental stage."""
    stage_name: str
    nafs_level: int
    quran_ref: str
    allowed_tools: frozenset
    max_turns: int
    # Feature flags
    can_delegate: bool = False    # Can delegate to sub-agents
    nafs_triad: bool = False      # Nafs Triad deliberation
    causal_rung: int = 0          # 0=none, 1=observe, 2=intervene, 3=counterfactual
    lubb_active: bool = False     # Metacognitive monitoring
    fuad_active: bool = False     # Conviction formation
    description: str = ""


# Progressive capability gates — each stage unlocks more
_STAGES: dict[int, StageCapabilities] = {
    1: StageCapabilities(
        stage_name="Nutfah",
        nafs_level=1,
        quran_ref="23:13",
        allowed_tools=frozenset({"bash", "read_file", "recall_memory", "compact_context"}),
        max_turns=5,
        causal_rung=0,
        description="Seed stage — observe and recall only",
    ),
    2: StageCapabilities(
        stage_name="Alaqah",
        nafs_level=2,
        quran_ref="23:14",
        allowed_tools=frozenset({
            "bash", "read_file", "write_file", "http_get",
            "recall_memory", "compact_context",
        }),
        max_turns=8,
        causal_rung=0,
        description="Clot stage — can now write and fetch external data",
    ),
    3: StageCapabilities(
        stage_name="Mudghah",
        nafs_level=3,
        quran_ref="23:14",
        allowed_tools=frozenset({
            "bash", "read_file", "write_file", "list_files",
            "http_get", "http_post", "python_exec",
            "recall_memory", "compact_context",
        }),
        max_turns=10,
        can_delegate=True,
        causal_rung=1,   # Can observe causal associations
        description="Structured stage — execute code, observe causality",
    ),
    4: StageCapabilities(
        stage_name="Izham",
        nafs_level=4,
        quran_ref="23:14",
        allowed_tools=frozenset({
            "bash", "read_file", "write_file", "list_files",
            "http_get", "http_post", "python_exec",
            "create_agent", "recall_memory", "compact_context",
        }),
        max_turns=12,
        can_delegate=True,
        nafs_triad=True,
        causal_rung=2,   # Can intervene and predict effects
        description="Skeleton stage — can create sub-agents, nafs deliberation active",
    ),
    5: StageCapabilities(
        stage_name="Lahm",
        nafs_level=5,
        quran_ref="23:14",
        allowed_tools=ALL_TOOLS,
        max_turns=15,
        can_delegate=True,
        nafs_triad=True,
        causal_rung=3,   # Full causal reasoning
        lubb_active=True,
        fuad_active=True,
        description="Full capability — all tools, metacognition, conviction formation",
    ),
    6: StageCapabilities(
        stage_name="Nafkh",
        nafs_level=6,
        quran_ref="23:14",
        allowed_tools=ALL_TOOLS,
        max_turns=20,
        can_delegate=True,
        nafs_triad=True,
        causal_rung=3,
        lubb_active=True,
        fuad_active=True,
        description="Breath stage — extended reasoning, full metacognitive monitoring",
    ),
    7: StageCapabilities(
        stage_name="Khalq Akhar",
        nafs_level=7,
        quran_ref="23:14",
        allowed_tools=ALL_TOOLS,
        max_turns=25,
        can_delegate=True,
        nafs_triad=True,
        causal_rung=3,
        lubb_active=True,
        fuad_active=True,
        description="New creation — full autonomy, governance role",
    ),
}


@dataclass
class UpgradeReport:
    """Result of checking if an agent is ready to advance nafs levels."""
    current_level: int
    target_level: int
    ready: bool
    missing_requirements: list[str] = field(default_factory=list)
    tazkiyah_score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "current_level": self.current_level,
            "target_level": self.target_level,
            "ready": self.ready,
            "missing": self.missing_requirements,
            "tazkiyah_score": round(self.tazkiyah_score, 3),
        }


class DevelopmentalGate:
    """
    Progressive capability gating tied to nafs_level.

    Usage:
        gate = DevelopmentalGate()
        caps = gate.get_capabilities(nafs_level=3)
        # caps.allowed_tools, caps.max_turns, caps.causal_rung, etc.

        report = gate.check_upgrade_readiness(agent)
        if report.ready:
            agent.nafs_level += 1
    """

    def get_capabilities(self, nafs_level: int) -> StageCapabilities:
        """Get capabilities for a given nafs_level (clamps to valid range)."""
        level = max(1, min(7, nafs_level))
        return _STAGES[level]

    def filter_tool_schemas(
        self, tool_schemas: list[dict], nafs_level: int
    ) -> list[dict]:
        """
        Filter tool schemas to only include tools allowed at this nafs level.
        Skills and plugin tools are always allowed (dynamic capabilities).
        """
        caps = self.get_capabilities(nafs_level)
        filtered = []
        for schema in tool_schemas:
            name = schema.get("name", "")
            # Always include: tools not in the base set (skills/plugins)
            if name not in ALL_TOOLS:
                filtered.append(schema)
            elif name in caps.allowed_tools:
                filtered.append(schema)
            else:
                logger.debug(
                    "[DEV_GATE] Blocking tool '%s' at nafs_level=%d (%s)",
                    name, nafs_level, caps.stage_name,
                )
        return filtered

    def check_upgrade_readiness(self, agent) -> UpgradeReport:
        """
        Check if an agent meets the requirements to advance to the next nafs level.
        Uses NafsProfile.EVOLUTION_THRESHOLDS from core/architecture.py.
        """
        from core.architecture import NafsProfile

        current = getattr(agent, "nafs_level", 1)
        target = min(7, current + 1)

        if current >= 7:
            return UpgradeReport(
                current_level=current,
                target_level=7,
                ready=False,
                missing_requirements=["Already at maximum nafs level"],
                tazkiyah_score=1.0,
            )

        threshold = NafsProfile.EVOLUTION_THRESHOLDS.get(target, {})
        missing = []

        success_rate = getattr(agent, "success_rate", 0.0)
        total_tasks = getattr(agent, "total_tasks", 0)
        required_sr = threshold.get("success_rate", 0.0)
        required_tasks = threshold.get("min_tasks", 0)

        if success_rate < required_sr:
            missing.append(f"success_rate {success_rate:.0%} < {required_sr:.0%}")
        if total_tasks < required_tasks:
            missing.append(f"tasks {total_tasks} < {required_tasks}")
        if "min_hikmah" in threshold:
            hikmah = len(getattr(agent, "hikmah", []))
            if hikmah < threshold["min_hikmah"]:
                missing.append(f"hikmah {hikmah} < {threshold['min_hikmah']}")

        # Compute rough tazkiyah score
        tazkiyah = (
            min(1.0, success_rate / max(required_sr, 0.01)) * 0.6
            + min(1.0, total_tasks / max(required_tasks, 1)) * 0.4
        )

        report = UpgradeReport(
            current_level=current,
            target_level=target,
            ready=len(missing) == 0,
            missing_requirements=missing,
            tazkiyah_score=round(tazkiyah, 3),
        )

        if report.ready:
            logger.info(
                "[DEV_GATE] Agent ready to advance nafs_level %d → %d (tazkiyah=%.2f)",
                current, target, tazkiyah,
            )

        return report

    def stage_summary(self) -> list[dict]:
        """Summary of all stages for display."""
        return [
            {
                "level": level,
                "stage": s.stage_name,
                "quran_ref": s.quran_ref,
                "tools": len(s.allowed_tools),
                "max_turns": s.max_turns,
                "causal_rung": s.causal_rung,
                "lubb": s.lubb_active,
                "description": s.description,
            }
            for level, s in _STAGES.items()
        ]
