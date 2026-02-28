"""
Living Memory System — InsÄn-NisyÄn Architecture
==================================================

"And remember your Lord when you forget" — Quran 18:24
"Remember Me and I will remember you" — Quran 2:152

Memory is NOT a database — it's a living organism that decides what to store,
what to forget, strengthens with use, fades with neglect, transforms over time,
and recalls differently depending on context.

Implements:
- NOVELTY_GATE: "Do I already know this?" (θ_identical=0.98, θ_similar=0.85, θ_related=0.5)
- IMPORTANCE_SCORER: Multi-factor importance scoring (emotional, goal, surprise, causal, trust, rarity)
- DYNAMIC_RECALL: Context-dependent associative recall with spread activation + emotional modulation
- DHIKR_MAINTENANCE_DAEMON: Spaced repetition, decay, consolidation, Ṣadr→Dhikr→ʿIlm→Lawḥ promotion
- Memory 1+1=2 lifecycle: learn once, activate existing, never re-store

Principles:
  1. Intelligent forgetting enables intelligent remembering
  2. Memory requires active maintenance (dhikr) — unreviewed decays, reviewed strengthens
  3. Memory has depth: Ḥifẓ (raw) → ʿIlm (structural) → Fahm (applicable) → Tafaqquh (transformative)
  4. Novelty gates storage — only genuinely new information creates new traces
"""

import hashlib
import logging
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("mizan.living_memory")

# Novelty Gate thresholds
THETA_IDENTICAL = 0.98    # "I already know this exactly"
THETA_SIMILAR = 0.85      # "I know something like this"
THETA_RELATED = 0.50      # "This is new but related"
THETA_WORTH_STORING = 0.3 # Minimum importance to store unrelated info

# Importance scoring weights
W_EMOTION = 0.20
W_GOAL = 0.20
W_SURPRISE = 0.20
W_CAUSAL = 0.15
W_TRUST = 0.10
W_RARITY = 0.15

# Strength / decay parameters
INITIAL_STRENGTH = 0.30
DELTA_REINFORCE = 0.12     # strength boost on re-encounter
DELTA_RETRIEVAL = 0.08     # testing effect: recall strengthens memory
DELTA_REVIEW = 0.05        # dhikr daemon review boost (diminishing)
DELTA_DECAY = 0.02         # per-cycle decay rate for unreviewed
PHI_SPACING = 1.5          # spacing effect exponent

# Consolidation thresholds
CONSOLIDATE_RECALL_COUNT = 5   # promote Dhikr→ʿIlm after N retrievals
CONSOLIDATE_CONSISTENCY = 0.7
PROVE_COUNT = 20               # promote ʿIlm→Lawḥ after N verifications
FORGET_THRESHOLD = 0.05        # archive if strength drops below
MIN_STRENGTH = 0.01

# Spread activation parameters
ALPHA_CONTEXT = 0.3
ALPHA_EMOTION = 0.25
ALPHA_GOAL = 0.2
LAMBDA_RECENCY = 0.001  # recency decay constant

# Working memory capacity (Miller's Law)
SADR_CAPACITY = 7

# Review intervals
BASE_REVIEW_INTERVAL = 3600  # 1 hour base


class MemoryLevel(Enum):
    SADR = "sadr"      # Working memory (~4-7 items, seconds)
    DHIKR = "dhikr"    # Episodic/active (hours-days)
    ILM = "ilm"        # Semantic/knowledge (weeks-years)
    LAWH = "lawh"      # Immutable core (forever, write-once-read-many)


class GateDecision(Enum):
    STORE_NEW = "store_new"
    STORE_NEW_WITH_LINKS = "store_new_with_links"
    UPDATE_EXISTING = "update_existing"
    ACTIVATE_EXISTING = "activate_existing"
    IGNORE = "ignore"


@dataclass
class MemoryTrace:
    """A single memory trace in the living memory system."""
    trace_id: str
    content: str
    content_hash: str          # for fast exact-match
    level: MemoryLevel
    strength: float
    importance: float
    emotional_tag: float       # -1.0 to +1.0
    context_tags: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)  # trace_ids of associated memories
    recall_count: int = 0
    activation_count: int = 0
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    optimal_interval: float = BASE_REVIEW_INTERVAL
    contradiction_count: int = 0
    proven_count: int = 0
    mutable: bool = True
    gist: str = ""             # extracted abstract form (for ʿIlm level)
    source: str = ""

    def age_hours(self) -> float:
        return (time.time() - self.created_at) / 3600

    def hours_since_access(self) -> float:
        return (time.time() - self.last_accessed) / 3600

    def review_urgency(self) -> float:
        """How overdue is this trace for review? >1.0 = overdue."""
        time_since = time.time() - self.last_accessed
        return time_since / max(self.optimal_interval, 60)


@dataclass
class GateResult:
    """Result of the Novelty Gate evaluation."""
    decision: GateDecision
    matched_trace: MemoryTrace | None
    similarity: float
    importance: float
    delta_info: str  # what's new vs existing


@dataclass
class RecallResult:
    """A recalled memory with contextual scoring."""
    trace: MemoryTrace
    activation: float
    context_match: float
    emotional_match: float
    goal_match: float
    recency: float
    reconstructed: str  # may differ from original (reconstructive recall)


@dataclass
class MaintenanceReport:
    """Result of one Dhikr Daemon maintenance cycle."""
    reviewed: int
    decayed: int
    archived: int
    promoted_to_ilm: int
    promoted_to_lawh: int
    cycle_time_ms: float


class LivingMemorySystem:
    """
    The complete Living Memory architecture.

    4-level hierarchy: Ṣadr → Dhikr → ʿIlm → Lawḥ
    Novelty-gated storage, importance-scored encoding,
    context-dependent recall, and Dhikr maintenance daemon.
    """

    def __init__(self, masalik=None, dhikr_db=None, lawh=None, vector_store=None):
        # Memory stores by level
        self.sadr: list[MemoryTrace] = []       # working memory (capacity-limited)
        self.traces: dict[str, MemoryTrace] = {}  # all traces by ID
        self.archive: list[str] = []             # archived (forgotten) trace IDs

        # External system references (for integration)
        self._masalik = masalik     # MasalikNetwork for spread activation
        self._dhikr_db = dhikr_db  # DhikrMemorySystem for persistence
        self._lawh = lawh          # LawhMahfuz for immutable storage
        self._vector_store = vector_store  # VectorStore for semantic similarity

        self._daemon_cycle = 0
        self._content_hashes: dict[str, str] = {}  # hash → trace_id for fast lookup

    def process_input(
        self,
        content: str,
        emotional_state: float = 0.0,
        goals: list[str] | None = None,
        context: str = "",
        source_trust: float = 0.7,
    ) -> GateResult:
        """
        NOVELTY_GATE + IMPORTANCE_SCORER combined entry point.

        1. Compute similarity to existing memories
        2. Decide: STORE_NEW | UPDATE | ACTIVATE | IGNORE
        3. Score importance
        4. Execute storage or activation
        """
        goals = goals or []

        # Fast exact-match via content hash
        content_hash = self._hash_content(content)
        if content_hash in self._content_hashes:
            existing_id = self._content_hashes[content_hash]
            if existing_id in self.traces:
                existing = self.traces[existing_id]
                return self._activate_existing(existing, "Exact hash match")

        # Similarity search against all traces
        best_match, max_similarity = self._find_best_match(content)

        # Importance scoring
        importance = self._score_importance(
            content, emotional_state, goals, context, source_trust
        )

        # Decision tree (Algorithm: NOVELTY_GATE)
        if max_similarity > THETA_IDENTICAL and best_match:
            # "I already know this exactly" → like seeing 1+1=2 again
            return self._activate_existing(best_match, "Near-identical match")

        elif max_similarity > THETA_SIMILAR and best_match:
            # "I know something like this" → enrich existing
            delta = self._extract_novel_parts(content, best_match)
            return self._update_existing(best_match, delta, importance)

        elif max_similarity > THETA_RELATED and best_match:
            # "New but related" → store with links
            trace = self._create_trace(
                content, content_hash, importance, emotional_state, context
            )
            trace.links.append(best_match.trace_id)
            self._store_trace(trace)
            return GateResult(
                decision=GateDecision.STORE_NEW_WITH_LINKS,
                matched_trace=trace,
                similarity=max_similarity,
                importance=importance,
                delta_info=f"Linked to '{best_match.content[:40]}'",
            )

        else:
            # Completely new
            if importance > THETA_WORTH_STORING:
                trace = self._create_trace(
                    content, content_hash, importance, emotional_state, context
                )
                self._store_trace(trace)
                return GateResult(
                    decision=GateDecision.STORE_NEW,
                    matched_trace=trace,
                    similarity=max_similarity,
                    importance=importance,
                    delta_info="Novel information stored",
                )
            else:
                return GateResult(
                    decision=GateDecision.IGNORE,
                    matched_trace=None,
                    similarity=max_similarity,
                    importance=importance,
                    delta_info="Not novel enough and not important enough",
                )

    def recall(
        self,
        query: str,
        context: str = "",
        emotional_state: float = 0.0,
        goals: list[str] | None = None,
        top_k: int = 10,
    ) -> list[RecallResult]:
        """
        DYNAMIC_RECALL: Context-dependent associative recall.

        1. Spread activation from query
        2. Context modulation
        3. Emotional modulation (mood-congruent memory)
        4. Goal modulation
        5. Recency weighting
        6. Reconstruction
        7. Post-retrieval update (reconsolidation)
        """
        goals = goals or []
        if not self.traces:
            return []

        # Step 1: Spread activation
        activations: dict[str, float] = {}

        # Wave 1: Direct matches
        query_words = set(query.lower().split())
        for tid, trace in self.traces.items():
            if tid in self.archive:
                continue
            sim = self._text_similarity(query, trace.content)
            if sim > 0.1:
                activations[tid] = sim * trace.strength

        # Wave 2: Spread through links (1-hop)
        wave2 = {}
        for tid, activation in list(activations.items()):
            trace = self.traces[tid]
            for linked_id in trace.links:
                if linked_id in self.traces and linked_id not in self.archive:
                    link_activation = activation * 0.6
                    wave2[linked_id] = max(
                        wave2.get(linked_id, 0), link_activation
                    )
        for tid, act in wave2.items():
            activations[tid] = max(activations.get(tid, 0), act)

        # Wave 3: Spread through links (2-hop)
        wave3 = {}
        for tid, activation in wave2.items():
            trace = self.traces[tid]
            for linked_id in trace.links:
                if linked_id in self.traces and linked_id not in self.archive:
                    wave3[linked_id] = max(
                        wave3.get(linked_id, 0), activation * 0.3
                    )
        for tid, act in wave3.items():
            activations[tid] = max(activations.get(tid, 0), act)

        if not activations:
            return []

        # Steps 2-5: Modulation
        results = []
        for tid, base_activation in activations.items():
            trace = self.traces[tid]

            # Context modulation
            context_match = self._text_similarity(context, " ".join(trace.context_tags)) if context else 0.0
            modulated = base_activation * (1 + ALPHA_CONTEXT * context_match)

            # Emotional modulation (mood-congruent)
            emotional_match = 1.0 - abs(emotional_state - trace.emotional_tag)
            modulated *= (1 + ALPHA_EMOTION * emotional_match)

            # Goal modulation
            goal_match = 0.0
            if goals:
                goal_match = max(
                    self._text_similarity(g, trace.content) for g in goals
                )
                modulated *= (1 + ALPHA_GOAL * goal_match)

            # Recency weighting
            recency = math.exp(-LAMBDA_RECENCY * trace.hours_since_access())
            modulated *= recency

            results.append(RecallResult(
                trace=trace,
                activation=modulated,
                context_match=context_match,
                emotional_match=emotional_match,
                goal_match=goal_match,
                recency=recency,
                reconstructed=trace.content,  # simplified: no gap-filling yet
            ))

        # Sort by activation, take top-k
        results.sort(key=lambda r: r.activation, reverse=True)
        results = results[:top_k]

        # Step 7: Post-retrieval update (reconsolidation)
        for result in results:
            trace = result.trace
            trace.recall_count += 1
            trace.strength = min(1.0, trace.strength + DELTA_RETRIEVAL)
            trace.last_accessed = time.time()
            if context:
                if context not in trace.context_tags:
                    trace.context_tags.append(context)
                    if len(trace.context_tags) > 20:
                        trace.context_tags.pop(0)

        return results

    def run_maintenance(self) -> MaintenanceReport:
        """
        DHIKR_MAINTENANCE_DAEMON: One maintenance cycle.

        1. Compute review priority
        2. Review top-priority memories
        3. Decay unreviewed memories
        4. Consolidate: Dhikr→ʿIlm→Lawḥ promotions
        5. Archive forgotten traces
        """
        self._daemon_cycle += 1
        start = time.monotonic()

        reviewed = 0
        decayed = 0
        archived = 0
        promoted_ilm = 0
        promoted_lawh = 0

        # Step 1-2: Review overdue traces
        overdue = [
            t for t in self.traces.values()
            if t.mutable and t.trace_id not in self.archive and t.review_urgency() > 1.0
        ]
        overdue.sort(key=lambda t: t.review_urgency() * t.importance, reverse=True)

        for trace in overdue[:20]:  # max 20 reviews per cycle
            trace.strength = min(1.0,
                trace.strength + DELTA_REVIEW / max(trace.recall_count, 1)
            )
            trace.last_accessed = time.time()
            # Extend optimal interval (spaced repetition)
            trace.optimal_interval *= (1 + trace.strength) ** PHI_SPACING
            reviewed += 1

        # Step 3: Decay unreviewed traces
        for trace in self.traces.values():
            if trace.trace_id in self.archive or not trace.mutable:
                continue
            if trace.review_urgency() < 1.0:
                continue  # not overdue, no decay
            if trace.importance < 0.5:  # only decay low-importance
                trace.strength *= (1 - DELTA_DECAY)
                decayed += 1

                # Archive if too weak
                if trace.strength < FORGET_THRESHOLD:
                    self.archive.append(trace.trace_id)
                    archived += 1

        # Step 4: Consolidation promotions
        for trace in list(self.traces.values()):
            if trace.trace_id in self.archive:
                continue

            # Dhikr → ʿIlm: frequently recalled + consistent
            if (
                trace.level == MemoryLevel.DHIKR
                and trace.recall_count >= CONSOLIDATE_RECALL_COUNT
                and trace.strength >= CONSOLIDATE_CONSISTENCY
            ):
                trace.level = MemoryLevel.ILM
                trace.gist = self._extract_gist(trace)
                promoted_ilm += 1

            # ʿIlm → Lawḥ: proven beyond doubt
            elif (
                trace.level == MemoryLevel.ILM
                and trace.proven_count >= PROVE_COUNT
                and trace.contradiction_count == 0
            ):
                trace.level = MemoryLevel.LAWH
                trace.mutable = False
                trace.strength = 1.0
                # Store in external LawhMahfuz if available
                if self._lawh:
                    try:
                        self._lawh.store_immutable(
                            key=f"LM:{trace.trace_id}",
                            content=trace.gist or trace.content,
                            source="living_memory_promotion",
                        )
                    except Exception:
                        pass
                promoted_lawh += 1

        elapsed_ms = (time.monotonic() - start) * 1000
        logger.debug(
            "[DHIKR-DAEMON] cycle=%d reviewed=%d decayed=%d archived=%d ilm=%d lawh=%d",
            self._daemon_cycle, reviewed, decayed, archived, promoted_ilm, promoted_lawh,
        )

        return MaintenanceReport(
            reviewed=reviewed,
            decayed=decayed,
            archived=archived,
            promoted_to_ilm=promoted_ilm,
            promoted_to_lawh=promoted_lawh,
            cycle_time_ms=round(elapsed_ms, 2),
        )

    def _score_importance(
        self,
        content: str,
        emotional_state: float,
        goals: list[str],
        context: str,
        source_trust: float,
    ) -> float:
        """
        IMPORTANCE_SCORER: Multi-factor scoring.

        importance = Σ weights · factors:
          emotional_weight, goal_relevance, prediction_error (surprise),
          causal_impact, source_trust, rarity
        """
        content_lower = content.lower()

        # Factor 1: Emotional weight (|affect|)
        emotional_weight = abs(emotional_state)

        # Factor 2: Goal relevance
        goal_relevance = 0.0
        if goals:
            goal_relevance = max(
                self._text_similarity(g, content) for g in goals
            )

        # Factor 3: Prediction error (surprise) — novelty proxy
        _, max_sim = self._find_best_match(content)
        prediction_error = 1.0 - max_sim

        # Factor 4: Causal significance (keyword heuristic)
        causal_keywords = {"because", "caused", "leads to", "therefore", "result", "effect"}
        causal_impact = min(1.0,
            sum(1 for k in causal_keywords if k in content_lower) / 3
        )

        # Factor 5: Source trust
        trust = min(1.0, max(0.0, source_trust))

        # Factor 6: Rarity (inverse frequency of similar content)
        similar_count = sum(
            1 for t in self.traces.values()
            if self._text_similarity(content, t.content) > THETA_RELATED
        )
        rarity = 1.0 / (1.0 + similar_count)

        # Weighted combination → sigmoid
        raw = (
            W_EMOTION * emotional_weight
            + W_GOAL * goal_relevance
            + W_SURPRISE * prediction_error
            + W_CAUSAL * causal_impact
            + W_TRUST * trust
            + W_RARITY * rarity
        )
        return self._sigmoid(raw * 3)  # scale into sigmoid range

    def _activate_existing(
        self, trace: MemoryTrace, reason: str
    ) -> GateResult:
        """Activate an existing trace: no new storage, just strengthen."""
        trace.activation_count += 1
        trace.last_accessed = time.time()
        trace.strength = min(1.0, trace.strength + DELTA_REINFORCE)
        trace.proven_count += 1

        return GateResult(
            decision=GateDecision.ACTIVATE_EXISTING,
            matched_trace=trace,
            similarity=1.0,
            importance=trace.importance,
            delta_info=f"{reason} — activated (count={trace.activation_count})",
        )

    def _update_existing(
        self, trace: MemoryTrace, delta: str, importance: float
    ) -> GateResult:
        """Update an existing trace with novel information delta."""
        if delta:
            trace.content += f" | UPDATE: {delta[:200]}"
        trace.activation_count += 1
        trace.last_accessed = time.time()
        trace.strength = min(1.0, trace.strength + DELTA_REINFORCE * 0.7)
        trace.importance = max(trace.importance, importance)

        return GateResult(
            decision=GateDecision.UPDATE_EXISTING,
            matched_trace=trace,
            similarity=0.9,
            importance=importance,
            delta_info=f"Enriched with: {delta[:80]}",
        )

    def _create_trace(
        self,
        content: str,
        content_hash: str,
        importance: float,
        emotional_tag: float,
        context: str,
    ) -> MemoryTrace:
        trace_id = hashlib.md5(
            f"{content[:100]}:{time.time()}".encode()
        ).hexdigest()[:12]

        # New traces start in Ṣadr (working memory)
        trace = MemoryTrace(
            trace_id=trace_id,
            content=content,
            content_hash=content_hash,
            level=MemoryLevel.SADR,
            strength=INITIAL_STRENGTH,
            importance=importance,
            emotional_tag=emotional_tag,
            context_tags=[context] if context else [],
            source="living_memory",
        )
        return trace

    def _store_trace(self, trace: MemoryTrace) -> None:
        """Store trace and manage Ṣadr capacity."""
        self.traces[trace.trace_id] = trace
        self._content_hashes[trace.content_hash] = trace.trace_id

        # Ṣadr → Dhikr promotion when working memory full
        self.sadr.append(trace)
        if len(self.sadr) > SADR_CAPACITY:
            # Oldest items move to Dhikr level
            evicted = self.sadr.pop(0)
            if evicted.trace_id in self.traces:
                evicted.level = MemoryLevel.DHIKR

        # Persist to external Masalik if available
        if self._masalik:
            try:
                self._masalik.encode(trace.content, importance=trace.importance)
            except Exception:
                pass

        # Persist to VectorStore for semantic similarity search
        if self._vector_store and getattr(self._vector_store, "_available", False):
            try:
                import asyncio
                import concurrent.futures

                metadata = {"level": trace.level.value, "importance": trace.importance}
                coro = self._vector_store.store(
                    trace.content, memory_id=trace.trace_id, metadata=metadata
                )
                try:
                    asyncio.get_running_loop()
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                        executor.submit(asyncio.run, coro).result(timeout=5)
                except RuntimeError:
                    asyncio.run(coro)
            except Exception:
                pass

    def _find_best_match(self, content: str) -> tuple[MemoryTrace | None, float]:
        """Find the most similar existing trace (text + optional vector similarity)."""
        best = None
        best_sim = 0.0

        # Primary: Jaccard text similarity (always available)
        for trace in self.traces.values():
            if trace.trace_id in self.archive:
                continue
            sim = self._text_similarity(content, trace.content)
            if sim > best_sim:
                best_sim = sim
                best = trace

        # Secondary: Vector similarity via ChromaDB (if available)
        if self._vector_store and getattr(self._vector_store, "_available", False):
            try:
                # VectorStore.search() is async but underlying ChromaDB is sync.
                # Use sync wrapper to avoid event loop issues.
                vector_results = self._vector_search_sync(content, limit=5)
                for vr in vector_results:
                    distance = vr.get("distance", 1.0)
                    # ChromaDB L2 distance → 0-1 similarity
                    vector_sim = max(0.0, 1.0 - (distance / 2.0))
                    vec_id = vr.get("id", "")
                    if vec_id in self.traces and vec_id not in self.archive:
                        trace = self.traces[vec_id]
                        hybrid_sim = max(
                            self._text_similarity(content, trace.content),
                            vector_sim,
                        )
                        if hybrid_sim > best_sim:
                            best_sim = hybrid_sim
                            best = trace
            except Exception:
                pass  # Graceful degradation to text-only

        return best, best_sim

    def _vector_search_sync(self, query: str, limit: int = 5) -> list[dict]:
        """Synchronous wrapper for VectorStore.search()."""
        import asyncio
        import concurrent.futures

        try:
            asyncio.get_running_loop()
            # Already in async context — run in thread to avoid nested loop
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    asyncio.run, self._vector_store.search(query, limit=limit)
                )
                return future.result(timeout=5)
        except RuntimeError:
            # No running event loop — safe to run directly
            return asyncio.run(self._vector_store.search(query, limit=limit))

    def _extract_novel_parts(self, new_content: str, existing: MemoryTrace) -> str:
        """Extract what's genuinely new in content vs existing trace."""
        new_words = set(new_content.lower().split())
        existing_words = set(existing.content.lower().split())
        novel = new_words - existing_words
        if novel:
            return " ".join(sorted(novel)[:15])
        return ""

    def _extract_gist(self, trace: MemoryTrace) -> str:
        """Extract abstract gist from a trace (for ʿIlm promotion)."""
        words = trace.content.split()
        # Keep first sentence or first 15 words
        gist_words = words[:15]
        return " ".join(gist_words)

    @staticmethod
    def _text_similarity(text_a: str, text_b: str) -> float:
        """Jaccard similarity on word sets."""
        if not text_a or not text_b:
            return 0.0
        words_a = set(text_a.lower().split())
        words_b = set(text_b.lower().split())
        if not words_a or not words_b:
            return 0.0
        intersection = len(words_a & words_b)
        union = len(words_a | words_b)
        return intersection / union if union > 0 else 0.0

    @staticmethod
    def _hash_content(content: str) -> str:
        return hashlib.sha256(content.strip().lower().encode()).hexdigest()[:16]

    @staticmethod
    def _sigmoid(x: float) -> float:
        return 1.0 / (1.0 + math.exp(-x))

    def get_level_counts(self) -> dict[str, int]:
        counts = {level.value: 0 for level in MemoryLevel}
        for trace in self.traces.values():
            if trace.trace_id not in self.archive:
                counts[trace.level.value] += 1
        counts["archived"] = len(self.archive)
        return counts

    def to_dict(self) -> dict:
        return {
            "total_traces": len(self.traces),
            "levels": self.get_level_counts(),
            "sadr_capacity": f"{len(self.sadr)}/{SADR_CAPACITY}",
            "daemon_cycles": self._daemon_cycle,
        }
