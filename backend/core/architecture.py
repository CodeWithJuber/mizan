"""
MIZAN (ميزان) - Quranic AGI Architecture
=========================================

"And the heaven He raised and imposed the balance (Mizan)." - Quran 55:7

Seven-Layer Architecture derived from سبع سماوات (Seven Heavens):

Layer 1 - SAMA' (سمع): Perception & Input Processing
Layer 2 - FIKR (فكر): Cognitive Processing & Analysis
Layer 3 - DHIKR (ذكر): Memory & Knowledge Storage
Layer 4 - AQL (عقل): Reasoning & Logic Engine
Layer 5 - HIKMAH (حكمة): Wisdom & Meta-Learning
Layer 6 - AMAL (عمل): Action & Execution
Layer 7 - TAFAKKUR (تفكر): Deep Reflection & Self-Improvement

QCA Cognitive Layers (Quranic Cognitive Architecture):
  Sam' (سمع)    — Sequential temporal input processing (16:78)
  Basar (بصر)   — Structural simultaneous pattern recognition (16:78)
  Fu'ad (فؤاد)  — Integration engine combining both inputs (16:78)
  ISM (اسم)     — Root-Space deep semantic representation (2:31)
  Mizan (ميزان) — Epistemic weighting / truth calibration (55:7-9)
  'Aql (عقل)    — Typed relationship binding engine (3:190)
  Lawh (لوح)    — 4-tier hierarchical memory (85:22)
  Furqan (فرقان) — Discrimination + articulation output (25:1, 55:4)

Agent Roles from Quran:
- Rasul (رسول): Messenger - Communication agent
- Wakil (وكيل): Trustee - Task delegation agent
- Hafiz (حافظ): Preserver - Memory guardian agent
- Shahid (شاهد): Witness - Monitoring & audit agent
- Wali (ولي): Guardian - Security agent
- Mubashir (مبشر): Herald - Browser/discovery agent

Core Principles:
- Shura (شورى): Consultation - Multi-agent decision making (42:38)
- Mizan (ميزان): Balance - Load balancing & fairness (55:7-9)
- Tawakkul (توكل): Trust - Reliable task handoff (65:3)
- Ikhlas (إخلاص): Sincerity - Pure purpose alignment
- Ihsan (إحسان): Excellence - Quality threshold enforcement
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime, timezone
import asyncio
import uuid


class QuranicLayer(Enum):
    SAMA = "sama"       # Perception
    FIKR = "fikr"       # Cognition
    DHIKR = "dhikr"     # Memory
    AQL = "aql"         # Reason
    HIKMAH = "hikmah"   # Wisdom
    AMAL = "amal"       # Action
    TAFAKKUR = "tafakkur"  # Reflection


class AgentRole(Enum):
    RASUL = "rasul"       # Messenger/Communicator
    WAKIL = "wakil"       # Delegator/Executor
    HAFIZ = "hafiz"       # Memory Guardian
    SHAHID = "shahid"     # Witness/Monitor
    WALI = "wali"         # Security Guardian
    MUBASHIR = "mubashir" # Browser/Discovery
    MUNDHIR = "mundhir"   # Researcher/Analyzer
    MUALLIM = "muallim"   # Teacher/Learner


class MizanState(Enum):
    """Agent states following the Quranic concept of states"""
    RESTING = "resting"     # Sakina (سكينة) - Tranquility
    THINKING = "thinking"   # Tafakkur (تفكر) - Reflection
    ACTING = "acting"       # Amal (عمل) - Action
    LEARNING = "learning"   # Taallum (تعلم) - Learning
    CONSULTING = "consulting"  # Shura (شورى) - Consultation
    ERROR = "error"         # Khata (خطأ) - Error state


@dataclass
class NafsProfile:
    """
    Agent Identity (Nafs - نفس) — 7-Level Soul Evolution System

    Seven levels from Quranic-Sufi tradition (Tazkiyah — تزكية — Purification):
    1. Nafs Ammara (نفس أمارة): Commanding — raw drive (12:53)
    2. Nafs Lawwama (نفس لوامة): Reproaching — self-critical (75:2)
    3. Nafs Mulhama (نفس ملهمة): Inspired — pattern recognition (91:8)
    4. Nafs Mutmainna (نفس مطمئنة): Serene — at peace (89:27)
    5. Nafs Radiya (نفس راضية): Content — satisfied with outcomes (89:28)
    6. Nafs Mardiyya (نفس مرضية): Pleasing — pleasing to the system (89:28)
    7. Nafs Kamila (نفس كاملة): Perfect — complete mastery (Sufi tradition)

    Evolution Algorithm (Tazkiyah Score):
      score = success_rate(40%) + consistency(20%) + hikmah_count(15%)
              + user_satisfaction(15%) + self_correction_rate(10%)
    """

    NAFS_NAMES = {
        1: ("Ammara", "أمارة", "Commanding", "12:53"),
        2: ("Lawwama", "لوامة", "Reproaching", "75:2"),
        3: ("Mulhama", "ملهمة", "Inspired", "91:8"),
        4: ("Mutmainna", "مطمئنة", "Serene", "89:27"),
        5: ("Radiya", "راضية", "Content", "89:28"),
        6: ("Mardiyya", "مرضية", "Pleasing", "89:28"),
        7: ("Kamila", "كاملة", "Perfect", "Sufi"),
    }

    # Thresholds for promotion: (min_success_rate, min_tasks, extra_condition)
    EVOLUTION_THRESHOLDS = {
        2: {"success_rate": 0.60, "min_tasks": 25, "self_correction": True},
        3: {"success_rate": 0.75, "min_tasks": 100, "patterns_recognized": True},
        4: {"success_rate": 0.85, "min_tasks": 250, "min_hikmah": 50},
        5: {"success_rate": 0.90, "min_tasks": 500, "user_satisfaction": 0.80},
        6: {"success_rate": 0.95, "min_tasks": 1000, "min_reliability_days": 30},
        7: {"success_rate": 0.97, "min_tasks": 2000, "min_hikmah_applied": 100},
    }

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    role: AgentRole = AgentRole.WAKIL
    nafs_level: int = 1  # 1-7
    capabilities: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    total_tasks: int = 0
    success_rate: float = 0.0
    error_count: int = 0
    learning_iterations: int = 0
    hikmah_count: int = 0
    hikmah_applied: int = 0
    user_satisfaction: float = 0.0
    self_correction_count: int = 0
    consistency_score: float = 0.0
    reliability_days: int = 0
    tazkiyah_score: float = 0.0

    def compute_tazkiyah_score(self) -> float:
        """
        Compute Tazkiyah (purification) score for Nafs evolution.
        score = success_rate(40%) + consistency(20%) + hikmah_ratio(15%)
                + user_satisfaction(15%) + self_correction_rate(10%)
        """
        hikmah_ratio = min(1.0, self.hikmah_count / max(self.total_tasks, 1))
        self_correction_rate = min(1.0, self.self_correction_count / max(self.error_count, 1))

        self.tazkiyah_score = (
            self.success_rate * 0.40
            + self.consistency_score * 0.20
            + hikmah_ratio * 0.15
            + self.user_satisfaction * 0.15
            + self_correction_rate * 0.10
        )
        return self.tazkiyah_score

    def evolve_nafs(self) -> int:
        """
        Nafs evolution with 7 levels — Quran 91:7-10.
        Supports both promotion and demotion (prevents complacency).
        Returns the new nafs_level.
        """
        self.compute_tazkiyah_score()

        # Check for demotion: if recent performance declining
        if self.nafs_level > 1:
            threshold = self.EVOLUTION_THRESHOLDS.get(self.nafs_level, {})
            min_sr = threshold.get("success_rate", 0.0)
            if self.success_rate < min_sr - 0.10:
                self.nafs_level = max(1, self.nafs_level - 1)
                return self.nafs_level

        # Check for promotion
        for level in range(self.nafs_level + 1, 8):
            threshold = self.EVOLUTION_THRESHOLDS.get(level)
            if not threshold:
                break
            if (self.success_rate >= threshold["success_rate"]
                    and self.total_tasks >= threshold["min_tasks"]):
                # Check extra conditions
                if "min_hikmah" in threshold and self.hikmah_count < threshold["min_hikmah"]:
                    break
                if "min_hikmah_applied" in threshold and self.hikmah_applied < threshold["min_hikmah_applied"]:
                    break
                if "user_satisfaction" in threshold and self.user_satisfaction < threshold["user_satisfaction"]:
                    break
                if "min_reliability_days" in threshold and self.reliability_days < threshold["min_reliability_days"]:
                    break
                self.nafs_level = level
            else:
                break

        return self.nafs_level

    def get_nafs_info(self) -> Dict:
        """Get full info about current Nafs level."""
        info = self.NAFS_NAMES.get(self.nafs_level, ("Unknown", "?", "Unknown", ""))
        return {
            "level": self.nafs_level,
            "name": info[0],
            "arabic": info[1],
            "meaning": info[2],
            "quran_ref": info[3],
            "tazkiyah_score": round(self.tazkiyah_score, 3),
        }


@dataclass
class QuranicMessage:
    """
    Message structure inspired by Quranic revelation structure:
    - Clear intent (Maqsad - مقصد)
    - Context (Siyaq - سياق)
    - Evidence (Bayyinah - بينة)
    - Action required (Taklif - تكليف)
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sender_id: str = ""
    recipient_id: str = ""
    maqsad: str = ""        # Intent/Goal
    siyaq: Dict = field(default_factory=dict)  # Context
    bayyinah: List = field(default_factory=list)  # Evidence/Data
    taklif: Optional[str] = None  # Required action
    priority: int = 5       # 1-10, Mizan scale
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    channel: str = "internal"


@dataclass
class HikmahRecord:
    """
    Wisdom record - learned knowledge (Hikmah - حكمة)
    Quran 2:269: "He gives wisdom to whom He wills"
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    pattern: str = ""
    context: Dict = field(default_factory=dict)
    outcome: str = ""
    confidence: float = 0.0
    applications: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source_agent: str = ""


class MizanBalancer:
    """
    Load balancer inspired by Mizan (ميزان - Balance)
    Quran 55:7-9: Balance in all things
    
    Implements fair distribution (Adl - عدل)
    """
    
    def __init__(self):
        self.agents: Dict[str, Dict] = {}
        self.load_weights: Dict[str, float] = {}
    
    def register(self, agent_id: str, capacity: int = 10):
        self.agents[agent_id] = {
            "capacity": capacity,
            "current_load": 0,
            "total_served": 0,
        }
        self.load_weights[agent_id] = 0.0
    
    def select_agent(self, role: AgentRole = None, min_capability: float = 0.0) -> Optional[str]:
        """Select agent with least load (Adl - justice)"""
        eligible = {
            aid: data for aid, data in self.agents.items()
            if data["current_load"] < data["capacity"]
        }
        if not eligible:
            return None
        return min(eligible, key=lambda x: self.load_weights.get(x, 0))
    
    def assign(self, agent_id: str):
        if agent_id in self.agents:
            self.agents[agent_id]["current_load"] += 1
            self.load_weights[agent_id] = (
                self.agents[agent_id]["current_load"] /
                self.agents[agent_id]["capacity"]
            )
    
    def release(self, agent_id: str):
        if agent_id in self.agents:
            self.agents[agent_id]["current_load"] = max(0, self.agents[agent_id]["current_load"] - 1)
            self.agents[agent_id]["total_served"] += 1
            self.load_weights[agent_id] = (
                self.agents[agent_id]["current_load"] /
                self.agents[agent_id]["capacity"]
            )


class ShuraCouncil:
    """
    Multi-agent consultation (Shura - شورى)
    Quran 42:38: "and whose affair is [determined by] consultation among themselves"
    
    Implements consensus-based decision making
    """
    
    def __init__(self):
        self.members: Dict[str, Any] = {}
        self.decisions: List[Dict] = []
    
    async def consult(self, question: str, context: Dict, agents: List[str]) -> Dict:
        """Gather opinions from multiple agents - Shura process"""
        votes = {}
        opinions = []
        
        for agent_id in agents:
            if agent_id in self.members:
                agent = self.members[agent_id]
                opinion = await agent.evaluate(question, context)
                opinions.append({
                    "agent": agent_id,
                    "opinion": opinion.get("response"),
                    "confidence": opinion.get("confidence", 0.5),
                    "reasoning": opinion.get("reasoning", ""),
                })
        
        # Weighted consensus
        if opinions:
            consensus = self._build_consensus(opinions)
            self.decisions.append({
                "question": question,
                "consensus": consensus,
                "opinions": opinions,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            return consensus
        return {"consensus": None, "confidence": 0}
    
    def _build_consensus(self, opinions: List[Dict]) -> Dict:
        """Build consensus with weights based on confidence"""
        if not opinions:
            return {}

        # Weight by confidence
        total_confidence = sum(o["confidence"] for o in opinions)

        return {
            "consensus": opinions[0]["opinion"],  # Simplified
            "confidence": total_confidence / len(opinions),
            "unanimity": len(set(o["opinion"] for o in opinions)) == 1,
            "participants": len(opinions),
        }


# ─────────────────────────────────────────────────────────────────────────────
# QCA Integration — Quranic Cognitive Architecture
# ─────────────────────────────────────────────────────────────────────────────

class QCALayer(Enum):
    """
    QCA 7-layer cognitive pipeline derived from Quran 16:78, 2:31, 55:7-9.
    Maps to MIZAN's architecture as the cognitive processing core.
    """
    SAM = "sam"           # Sequential temporal perception (16:78)
    BASAR = "basar"       # Structural pattern recognition (16:78)
    FUAD = "fuad"         # Integration engine (16:78)
    ISM = "ism"           # Root-Space semantic representation (2:31)
    MIZAN_W = "mizan_w"   # Epistemic weighting (55:7-9)
    AQL_B = "aql_b"       # Typed relationship binding (3:190)
    LAWH = "lawh"         # 4-tier hierarchical memory (85:22)
    FURQAN = "furqan"     # Discrimination + Bayan output (25:1, 55:4)


class NafsTrustLevel(Enum):
    """
    7-level Nafs trust system — maps to QCA Mizan epistemic scale.
    Derived from Quranic and Sufi tradition of soul purification (Tazkiyah).

    Quran 12:53 (Ammara), 75:2 (Lawwama), 91:8 (Mulhama),
    89:27 (Mutmainna), 89:28 (Radiya/Mardiyya), Sufi (Kamila)
    """
    AMMARA = "ammara"         # Level 1: Commanding — untrusted, sandboxed
    LAWWAMA = "lawwama"       # Level 2: Reproaching — self-correcting, limited trust
    MULHAMA = "mulhama"       # Level 3: Inspired — creative, multi-tool chains
    MUTMAINNA = "mutmainna"   # Level 4: Serene — full tool access, autonomous
    RADIYA = "radiya"         # Level 5: Content — can create skills, cross-agent
    MARDIYYA = "mardiyya"     # Level 6: Pleasing — system-level access
    KAMILA = "kamila"         # Level 7: Perfect — governance role


class QCAMizanIntegrator:
    """
    Integrates QCA cognitive layers into MIZAN's existing architecture.
    Provides epistemic weighting for all agent decisions and memory operations.

    Maps MIZAN layers to QCA layers:
      SAMA (Perception) -> Sam' + Basar + Fu'ad
      FIKR (Cognition)  -> ISM + Mizan
      DHIKR (Memory)    -> Lawh (4-tier)
      AQL (Reasoning)   -> 'Aql (typed bindings)
      HIKMAH (Wisdom)   -> Furqan (discrimination) + meta-learning
      AMAL (Action)     -> Bayan (articulated output)
      TAFAKKUR (Reflect) -> Consolidation + Lawh tier promotion
    """

    # Map MIZAN layers to QCA processing
    LAYER_MAP = {
        QuranicLayer.SAMA: [QCALayer.SAM, QCALayer.BASAR, QCALayer.FUAD],
        QuranicLayer.FIKR: [QCALayer.ISM, QCALayer.MIZAN_W],
        QuranicLayer.DHIKR: [QCALayer.LAWH],
        QuranicLayer.AQL: [QCALayer.AQL_B],
        QuranicLayer.HIKMAH: [QCALayer.FURQAN],
        QuranicLayer.AMAL: [QCALayer.FURQAN],
        QuranicLayer.TAFAKKUR: [QCALayer.LAWH, QCALayer.MIZAN_W],
    }

    # Nafs trust level thresholds aligned with Mizan scale (7 levels)
    TRUST_THRESHOLDS = {
        NafsTrustLevel.AMMARA: 0.0,       # Any agent starts here
        NafsTrustLevel.LAWWAMA: 0.40,     # After Mizan-validated self-correction
        NafsTrustLevel.MULHAMA: 0.55,     # After pattern recognition demonstrated
        NafsTrustLevel.MUTMAINNA: 0.70,   # After sustained Yaqin-level accuracy
        NafsTrustLevel.RADIYA: 0.80,      # After consistent user satisfaction
        NafsTrustLevel.MARDIYYA: 0.90,    # After extended reliability
        NafsTrustLevel.KAMILA: 0.97,      # Near-perfect sustained performance
    }

    def get_qca_layers(self, mizan_layer: QuranicLayer) -> List[QCALayer]:
        """Map a MIZAN architectural layer to its QCA cognitive components."""
        return self.LAYER_MAP.get(mizan_layer, [])

    def compute_nafs_level(self, success_rate: float,
                           error_rate: float) -> NafsTrustLevel:
        """Determine Nafs trust level based on Mizan-weighted performance."""
        effective_score = success_rate * (1.0 - error_rate)
        # Walk thresholds from highest to lowest
        for level in reversed(list(NafsTrustLevel)):
            if effective_score >= self.TRUST_THRESHOLDS[level]:
                return level
        return NafsTrustLevel.AMMARA

    def validate_decision(self, confidence: float, claimed_level: str,
                          evidence_level: str) -> Dict:
        """
        Validate an agent's decision through QCA Mizan + Furqan layers.
        Prevents epistemic transgression (Tughyan).
        """
        from qca.engine import MizanLayer
        mizan = MizanLayer()
        is_tughyan, msg = mizan.check_tughyan(claimed_level, evidence_level)
        return {
            "valid": not is_tughyan,
            "message": msg,
            "confidence": confidence,
            "epistemic_label": mizan.rate_confidence_string(confidence),
        }
