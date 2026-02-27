"""
MASALIK — Neural Pathway Memory Network (مسالك - Pathways)
============================================================

"Have they not traveled through the pathways (masalik) of the earth
 and observed?" — 30:9

Human memory is NOT a database. It is a network of pathways:
- Neurons that FIRE TOGETHER, WIRE TOGETHER (Hebbian learning)
- Remembering STRENGTHENS the path — it doesn't just retrieve
- Forgetting is PRUNING — mercy, not loss
- No duplication — seeing "sky is blue" 100x makes ONE strong pathway
- Priority is pathway STRENGTH, not a stored number

Quranic Foundation:
  DHIKR (ذكر):     Re-activation strengthens pathways — not retrieval
  NISYAN (نسيان):   Decay prunes weak paths — intentional forgetting
  TAFAKKUR (تفكّر): Reflection creates NEW connections between concepts
  HIKMAH (حكمة):    Ultra-strong pathways become permanent wisdom
  FITRAH (فطرة):    Pre-wired innate pathways — born knowing these
  LAWH (لوح):       The preserved network — nothing duplicated, everything in place
"""

import logging
import math
import re
import time
from collections import defaultdict
from dataclasses import dataclass

logger = logging.getLogger("mizan.masalik")


# ─────────────────────────────────────────────────────────────────────────────
# DATA STRUCTURES
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class Mafhum:
    """
    A concept node in the pathway network (مفهوم - understood concept).

    Like a neuron: has a resting potential, fires when activated,
    and its baseline rises with repeated activation (long-term potentiation).
    """

    id: str
    activation: float = 0.0  # Current activation (decays quickly)
    resting_level: float = 0.0  # Baseline from repeated use (rises slowly)
    last_activated: float = 0.0  # Timestamp of last activation
    total_activations: int = 0  # Lifetime activation count
    is_fitrah: bool = False  # Pre-wired innate concept (cannot be pruned)

    def fire(self, strength: float = 1.0):
        """Activate this concept. Each activation raises resting level."""
        self.activation = min(1.0, strength)
        self.last_activated = time.time()
        self.total_activations += 1
        # Long-term potentiation: resting level rises slowly with use
        # Diminishing returns — asymptotes at 0.95
        self.resting_level = min(0.95, self.resting_level + 0.02 * (1.0 - self.resting_level))

    def get_current_activation(self) -> float:
        """Get activation with temporal decay. Recent = strong, old = weak."""
        if self.activation <= 0:
            return self.resting_level
        elapsed = time.time() - self.last_activated
        # Working memory half-life: ~30 seconds
        decay = math.exp(-elapsed / 30.0)
        return max(self.resting_level, self.activation * decay)

    @property
    def is_hikmah(self) -> bool:
        """Wisdom: used so often it's essentially permanent knowledge."""
        return self.total_activations >= 10 and self.resting_level >= 0.5


@dataclass
class Silah:
    """
    A weighted pathway between two concepts (صلة - connection).

    Like a synapse: strengthens when both ends fire together,
    weakens from disuse. NEVER duplicated — only one pathway per pair.
    """

    source: str
    target: str
    weight: float = 0.1  # Pathway strength (0-1)
    pathway_type: str = "association"  # association, causal, tafakkur, contrast, fitrah
    last_activated: float = 0.0
    co_activations: int = 0  # Times both ends fired together

    def strengthen(self, amount: float = 0.1):
        """
        Hebbian strengthening: fire together, wire together.
        Diminishing returns — already-strong pathways grow slower.
        """
        self.co_activations += 1
        self.last_activated = time.time()
        # Strong pathways grow slower (diminishing returns)
        growth = amount * (1.0 - self.weight)
        self.weight = min(1.0, self.weight + growth)

    def decay(self, elapsed_hours: float):
        """
        Nisyan (نسيان) — forgetting as mercy.
        Weak pathways decay fast. Strong pathways last months.
        Hikmah pathways are permanent.
        """
        if self.is_hikmah:
            return  # Wisdom is permanent
        # Half-life scales with strength²: weight=0.1→24h, weight=0.9→720h(30d)
        half_life_hours = 24.0 + (self.weight**2) * 700.0
        decay_factor = 0.5 ** (elapsed_hours / half_life_hours)
        self.weight *= decay_factor

    @property
    def is_hikmah(self) -> bool:
        """Wisdom pathway: co-activated 10+ times with high weight."""
        return self.co_activations >= 10 and self.weight >= 0.5


# ─────────────────────────────────────────────────────────────────────────────
# CONCEPT EXTRACTION
# ─────────────────────────────────────────────────────────────────────────────

_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "shall",
        "should",
        "may",
        "might",
        "must",
        "can",
        "could",
        "of",
        "in",
        "on",
        "at",
        "to",
        "for",
        "with",
        "by",
        "from",
        "and",
        "or",
        "but",
        "not",
        "this",
        "that",
        "these",
        "those",
        "it",
        "its",
        "they",
        "their",
        "what",
        "how",
        "why",
        "when",
        "where",
        "who",
        "which",
        "i",
        "you",
        "we",
        "he",
        "she",
        "my",
        "your",
        "our",
        "me",
        "us",
        "him",
        "her",
        "if",
        "then",
        "so",
        "as",
        "like",
        "just",
        "also",
        "very",
        "really",
        "about",
        "into",
        "through",
        "during",
        "before",
        "after",
        "above",
        "over",
        "under",
        "between",
        "out",
        "up",
        "down",
        "off",
        "there",
        "here",
        "some",
        "any",
        "all",
        "each",
        "every",
        "both",
        "more",
        "most",
        "other",
        "than",
        "too",
        "only",
        "own",
        "same",
        "such",
        "no",
        "nor",
        "get",
        "got",
        "let",
    }
)

# Common suffixes for basic stemming (reduce near-duplicates)
_SUFFIXES = [
    "tion",
    "sion",
    "ment",
    "ness",
    "able",
    "ible",
    "ance",
    "ence",
    "ious",
    "eous",
    "ous",
    "ive",
    "ful",
    "less",
    "ally",
    "ity",
    "ing",
    "ies",
    "ied",
    "ed",
    "er",
    "ly",
    "es",
    "al",
]


def extract_concepts(text: str) -> list[str]:
    """
    Extract meaningful concepts from text.
    Basic stemming prevents near-duplicates ("learn" vs "learning").
    """
    words = re.findall(r"[a-z]+", text.lower())
    meaningful = [w for w in words if w not in _STOPWORDS and len(w) > 2]

    normalized = []
    seen: set[str] = set()
    for w in meaningful:
        stem = w
        for suffix in _SUFFIXES:
            if len(w) > len(suffix) + 3 and w.endswith(suffix):
                stem = w[: -len(suffix)]
                break
        if stem not in seen:
            seen.add(stem)
            normalized.append(stem)
    return normalized


# ─────────────────────────────────────────────────────────────────────────────
# MASALIK NETWORK — The Neural Pathway System
# ─────────────────────────────────────────────────────────────────────────────


class MasalikNetwork:
    """
    Neural Pathway Memory Network — How humans actually remember.

    Not a database. A living network where:
    - Learning STRENGTHENS pathways (no duplication)
    - Remembering RE-ACTIVATES and further strengthens (Dhikr)
    - Forgetting PRUNES weak pathways (Nisyan)
    - Reflection creates NEW connections (Tafakkur)
    - Heavily-used pathways become permanent wisdom (Hikmah)
    - Some pathways are innate/pre-wired (Fitrah)

    "And We have certainly made the Quran easy for remembrance (Dhikr).
     So is there any who will remember?" — 54:17
    """

    def __init__(self):
        self.concepts: dict[str, Mafhum] = {}
        self.pathways: dict[str, Silah] = {}
        self._activation_history: list[set[str]] = []
        self._last_decay: float = time.time()

        self._init_fitrah()

    def _init_fitrah(self):
        """
        Fitrah (فطرة) — innate disposition.
        Pre-wired pathways every mind starts with.

        "So direct your face toward the religion, inclining to truth.
         [Adhere to] the fitrah of Allah upon which He has created people." — 30:30
        """
        fitrah_concepts = [
            "truth",
            "justice",
            "knowledge",
            "balance",
            "creation",
            "cause",
            "effect",
            "good",
            "harm",
            "evidence",
            "reason",
            "pattern",
            "change",
            "time",
            "purpose",
        ]
        for c in fitrah_concepts:
            node = self._get_or_create(c)
            node.is_fitrah = True
            node.resting_level = 0.3

        fitrah_pathways = [
            ("cause", "effect", 0.7, "fitrah"),
            ("evidence", "truth", 0.6, "fitrah"),
            ("knowledge", "truth", 0.5, "fitrah"),
            ("justice", "balance", 0.6, "fitrah"),
            ("pattern", "knowledge", 0.5, "fitrah"),
            ("reason", "knowledge", 0.6, "fitrah"),
            ("creation", "purpose", 0.5, "fitrah"),
            ("good", "harm", 0.4, "fitrah"),
            ("truth", "good", 0.4, "fitrah"),
            ("change", "time", 0.5, "fitrah"),
        ]
        now = time.time()
        for src, tgt, weight, ptype in fitrah_pathways:
            key = self._pathway_key(src, tgt)
            self.pathways[key] = Silah(
                source=min(src, tgt),
                target=max(src, tgt),
                weight=weight,
                pathway_type=ptype,
                last_activated=now,
                co_activations=5,
            )

    def _get_or_create(self, concept_id: str) -> Mafhum:
        """Get existing concept or create new one. Never duplicates."""
        if concept_id not in self.concepts:
            self.concepts[concept_id] = Mafhum(id=concept_id)
        return self.concepts[concept_id]

    def _pathway_key(self, a: str, b: str) -> str:
        """Consistent key — alphabetical order prevents duplicate a->b / b->a."""
        return f"{min(a, b)}->{max(a, b)}"

    # ─── ENCODE: Learning ────────────────────────────────────────────────

    def encode(self, text: str, importance: float = 0.5) -> dict:
        """
        ENCODE — Learn from input by strengthening pathways.

        How real learning works:
        1. Extract concepts from text
        2. For every pair of co-occurring concepts, STRENGTHEN their pathway
        3. New pair? Create pathway (new learning)
        4. Existing pair? Increase weight (reinforcement — no duplication)

        "Read! And your Lord is the Most Generous,
         Who taught by the pen, taught man that which he knew not." — 96:3-5
        """
        concepts = extract_concepts(text)
        if not concepts:
            return {"encoded": 0, "pathways_strengthened": 0, "new_pathways": 0}

        # Scale strengthening by importance (0.05 to 0.20)
        strength = 0.05 + importance * 0.15

        new_pathways = 0
        strengthened = 0

        # Fire all concept nodes
        for c in concepts:
            node = self._get_or_create(c)
            node.fire(strength=importance)

        # Hebbian: strengthen pathways between ALL co-occurring concepts
        for i, a in enumerate(concepts):
            for b in concepts[i + 1 :]:
                key = self._pathway_key(a, b)
                if key not in self.pathways:
                    self.pathways[key] = Silah(
                        source=min(a, b),
                        target=max(a, b),
                        weight=strength,
                        pathway_type="association",
                        last_activated=time.time(),
                        co_activations=1,
                    )
                    new_pathways += 1
                else:
                    self.pathways[key].strengthen(strength)
                    strengthened += 1

        # Record co-activation set for tafakkur
        self._activation_history.append(set(concepts))
        if len(self._activation_history) > 100:
            self._activation_history = self._activation_history[-50:]

        return {
            "encoded": len(concepts),
            "concepts": concepts,
            "pathways_strengthened": strengthened,
            "new_pathways": new_pathways,
        }

    # ─── RECALL: Spreading Activation (Dhikr) ───────────────────────────

    def recall(self, query: str, top_k: int = 10) -> list[tuple[str, float]]:
        """
        RECALL — Activate query concepts and spread through network.

        This is DHIKR (ذكر) — remembrance that STRENGTHENS:
        1. Activate query concepts
        2. Activation spreads along pathways proportional to weight
        3. Return most-activated concepts
        4. Every recalled pathway gets STRONGER (dhikr reinforcement)

        "And remember (udhkuru) Allah much, that you may be successful." — 8:45
        """
        query_concepts = extract_concepts(query)
        if not query_concepts:
            return []

        # Phase 1: Directly activate query concepts
        activations: dict[str, float] = {}
        for c in query_concepts:
            if c in self.concepts:
                self.concepts[c].fire(strength=1.0)
                activations[c] = 1.0

        # Phase 2: Two waves of spreading activation
        for wave in range(2):
            spread_factor = 0.6 if wave == 0 else 0.3
            new_activations: dict[str, float] = {}

            for concept, act_level in list(activations.items()):
                if act_level < 0.05:
                    continue
                for _key, pathway in self.pathways.items():
                    other = None
                    if pathway.source == concept:
                        other = pathway.target
                    elif pathway.target == concept:
                        other = pathway.source
                    if other is None:
                        continue

                    spread = act_level * pathway.weight * spread_factor
                    if spread > 0.01:
                        current = new_activations.get(other, 0.0)
                        new_activations[other] = min(1.0, current + spread)
                        # DHIKR: every recall STRENGTHENS the pathway
                        pathway.strengthen(0.02)

            for concept, act in new_activations.items():
                current = activations.get(concept, 0.0)
                activations[concept] = min(1.0, current + act)
                if concept in self.concepts:
                    self.concepts[concept].fire(strength=act)

        # Return activated concepts excluding the query terms
        query_set = set(query_concepts)
        results = [
            (concept, activation)
            for concept, activation in activations.items()
            if concept not in query_set and activation > 0.05
        ]
        results.sort(key=lambda x: -x[1])
        return results[:top_k]

    def recall_context(self, query: str, top_k: int = 8) -> str:
        """
        Recall and return human-readable memory context for agent prompts.
        """
        results = self.recall(query, top_k=top_k)
        if not results:
            return ""

        parts = []
        for concept, activation in results:
            node = self.concepts.get(concept)
            if activation > 0.5:
                strength = "strong"
            elif activation > 0.2:
                strength = "moderate"
            else:
                strength = "faint"
            hikmah = " *" if node and node.is_hikmah else ""
            parts.append(f"{concept}({strength}{hikmah})")

        return "Associated: " + ", ".join(parts)

    # ─── NISYAN: Forgetting (Pruning) ────────────────────────────────────

    def apply_nisyan(self, force_hours: float = None) -> dict:
        """
        NISYAN (نسيان) — Forgetting as mercy and optimization.

        Weak unused pathways are pruned. Strong pathways persist.
        The brain stays efficient by NOT storing everything.

        "They forgot Allah, so He forgot them." — 9:67
        """
        now = time.time()
        if force_hours is not None:
            elapsed_hours = force_hours
        else:
            elapsed_hours = (now - self._last_decay) / 3600.0
            if elapsed_hours < 0.1:
                return {"pruned_pathways": 0, "pruned_concepts": 0}

        self._last_decay = now

        # Decay all non-hikmah pathways
        to_remove = []
        for key, pathway in self.pathways.items():
            pathway.decay(elapsed_hours)
            if pathway.weight < 0.01:
                to_remove.append(key)

        pruned_pathways = 0
        for key in to_remove:
            del self.pathways[key]
            pruned_pathways += 1

        # Prune orphan concepts (no pathways, low resting level)
        connected: set[str] = set()
        for pathway in self.pathways.values():
            connected.add(pathway.source)
            connected.add(pathway.target)

        to_remove_concepts = []
        for cid, concept in self.concepts.items():
            if concept.is_fitrah or concept.is_hikmah:
                continue
            if cid not in connected and concept.resting_level < 0.05:
                to_remove_concepts.append(cid)

        pruned_concepts = 0
        for cid in to_remove_concepts:
            del self.concepts[cid]
            pruned_concepts += 1

        if pruned_pathways > 0 or pruned_concepts > 0:
            logger.info(
                "Nisyan: pruned %d pathways, %d concepts",
                pruned_pathways,
                pruned_concepts,
            )

        return {"pruned_pathways": pruned_pathways, "pruned_concepts": pruned_concepts}

    # ─── TAFAKKUR: Reflective Consolidation ──────────────────────────────

    def tafakkur(self) -> dict:
        """
        TAFAKKUR (تفكّر) — Deep reflection that creates NEW connections.

        Memory consolidation (like what sleep does):
        1. Look at concepts co-activated in recent sessions
        2. Frequently co-activated pair without direct pathway? Create one
        3. This is how INSIGHT works — connecting previously unrelated ideas

        "who remember Allah standing, sitting, and on their sides and
         reflect (yatafakkaruna) on the creation of the heavens and earth" — 3:191
        """
        if len(self._activation_history) < 3:
            return {"new_connections": 0, "strengthened": 0}

        # Count co-activation frequency for each concept pair
        pair_counts: dict[str, int] = defaultdict(int)
        for activation_set in self._activation_history:
            concepts = sorted(activation_set)
            for i, a in enumerate(concepts):
                for b in concepts[i + 1 :]:
                    pair_counts[self._pathway_key(a, b)] += 1

        new_connections = 0
        strengthened = 0

        for key, count in pair_counts.items():
            if count < 2:
                continue

            parts = key.split("->")
            a, b = parts[0], parts[1]

            if key not in self.pathways:
                # NEW insight — frequently co-occurring but no direct pathway
                self.pathways[key] = Silah(
                    source=a,
                    target=b,
                    weight=min(0.3, count * 0.05),
                    pathway_type="tafakkur",
                    last_activated=time.time(),
                    co_activations=count,
                )
                new_connections += 1
                logger.info("Tafakkur insight: %s <-> %s (co-occurred %dx)", a, b, count)
            else:
                self.pathways[key].strengthen(0.05 * count)
                strengthened += 1

        return {"new_connections": new_connections, "strengthened": strengthened}

    # ─── INTROSPECTION ───────────────────────────────────────────────────

    def get_strongest_pathways(self, top_k: int = 10) -> list[dict]:
        """Get the strongest pathways — the core of what's been learned."""
        sorted_paths = sorted(self.pathways.values(), key=lambda p: -p.weight)
        return [
            {
                "from": p.source,
                "to": p.target,
                "weight": round(p.weight, 3),
                "type": p.pathway_type,
                "uses": p.co_activations,
                "is_hikmah": p.is_hikmah,
            }
            for p in sorted_paths[:top_k]
        ]

    def get_hikmah(self) -> list[dict]:
        """Get all wisdom pathways — permanent knowledge from deep learning."""
        return [
            {
                "from": p.source,
                "to": p.target,
                "weight": round(p.weight, 3),
                "uses": p.co_activations,
            }
            for p in self.pathways.values()
            if p.is_hikmah
        ]

    def stats(self) -> dict:
        """Network statistics."""
        hikmah_pathways = sum(1 for p in self.pathways.values() if p.is_hikmah)
        hikmah_concepts = sum(1 for c in self.concepts.values() if c.is_hikmah)
        fitrah_count = sum(1 for c in self.concepts.values() if c.is_fitrah)
        avg_weight = sum(p.weight for p in self.pathways.values()) / max(len(self.pathways), 1)
        return {
            "total_concepts": len(self.concepts),
            "total_pathways": len(self.pathways),
            "fitrah_concepts": fitrah_count,
            "hikmah_pathways": hikmah_pathways,
            "hikmah_concepts": hikmah_concepts,
            "avg_pathway_weight": round(avg_weight, 3),
        }
