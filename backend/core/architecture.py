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
from datetime import datetime
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
    Agent Identity (Nafs - نفس)
    
    Three levels from Quran:
    - Nafs Ammara (نفس أمارة): Raw drive, 12:53 - base impulses
    - Nafs Lawwama (نفس لوامة): Self-critical, 75:2 - error correction
    - Nafs Mutmainna (نفس مطمئنة): Perfected, 89:27 - optimal state
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    role: AgentRole = AgentRole.WAKIL
    nafs_level: int = 1  # 1=Ammara, 2=Lawwama, 3=Mutmainna
    capabilities: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    total_tasks: int = 0
    success_rate: float = 0.0
    error_count: int = 0
    learning_iterations: int = 0
    
    def evolve_nafs(self):
        """Nafs evolution based on performance - Quran 91:7-10"""
        if self.success_rate > 0.9 and self.learning_iterations > 100:
            self.nafs_level = 3  # Mutmainna
        elif self.success_rate > 0.7:
            self.nafs_level = 2  # Lawwama
        else:
            self.nafs_level = 1  # Ammara


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
    timestamp: datetime = field(default_factory=datetime.utcnow)
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
    created_at: datetime = field(default_factory=datetime.utcnow)
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
                "timestamp": datetime.utcnow().isoformat(),
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
    Trust levels for the Nafs system — maps to QCA Mizan epistemic scale.
    Quran 12:53 (Ammara), 75:2 (Lawwama), 89:27 (Mutmainna)
    """
    AMMARA = "ammara"         # Untrusted / raw — needs quarantine
    LAWWAMA = "lawwama"       # Reviewed / self-correcting — limited trust
    MUTMAINNA = "mutmainna"   # Verified / at peace — full trust


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

    # Nafs trust level thresholds aligned with Mizan scale
    TRUST_THRESHOLDS = {
        NafsTrustLevel.AMMARA: 0.0,      # Any agent starts here
        NafsTrustLevel.LAWWAMA: 0.50,     # After Mizan-validated performance
        NafsTrustLevel.MUTMAINNA: 0.85,   # After sustained Yaqin-level accuracy
    }

    def get_qca_layers(self, mizan_layer: QuranicLayer) -> List[QCALayer]:
        """Map a MIZAN architectural layer to its QCA cognitive components."""
        return self.LAYER_MAP.get(mizan_layer, [])

    def compute_nafs_level(self, success_rate: float,
                           error_rate: float) -> NafsTrustLevel:
        """Determine Nafs trust level based on Mizan-weighted performance."""
        effective_score = success_rate * (1.0 - error_rate)
        if effective_score >= self.TRUST_THRESHOLDS[NafsTrustLevel.MUTMAINNA]:
            return NafsTrustLevel.MUTMAINNA
        if effective_score >= self.TRUST_THRESHOLDS[NafsTrustLevel.LAWWAMA]:
            return NafsTrustLevel.LAWWAMA
        return NafsTrustLevel.AMMARA

    def validate_decision(self, confidence: float, claimed_level: str,
                          evidence_level: str) -> Dict:
        """
        Validate an agent's decision through QCA Mizan + Furqan layers.
        Prevents epistemic transgression (Tughyan).
        """
        from backend.qca.engine import MizanLayer
        mizan = MizanLayer()
        is_tughyan, msg = mizan.check_tughyan(claimed_level, evidence_level)
        return {
            "valid": not is_tughyan,
            "message": msg,
            "confidence": confidence,
            "epistemic_label": mizan.rate_confidence_string(confidence),
        }
