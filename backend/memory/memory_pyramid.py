"""
Memory Pyramid (هرم الذاكرة) — Unified 5-Layer Memory Query
=============================================================

"And We have certainly created man and We know what his soul (nafs)
 whispers to him, and We are closer to him than his jugular vein." — Quran 50:16

Unifies all five memory systems into a single query interface.
Each layer contributes what it does best:

  Layer 1 — Masalik       : Spreading activation → associative concepts
  Layer 2 — DhikrMemory   : Keyword SQL search → episodic/semantic records
  Layer 3 — VectorStore   : Semantic embedding search (if available)
  Layer 4 — KnowledgeGraph: Entity + relationship lookup
  Layer 5 — LawhMahfuz    : Immutable fact lookup

Results are merged, deduplicated, and ranked by (relevance × certainty × recency).
"""

import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger("mizan.memory_pyramid")


@dataclass
class MemoryHit:
    """A single result from any memory layer."""
    content: str
    source_layer: str       # "masalik" | "dhikr" | "vector" | "graph" | "lawh"
    relevance: float        # 0-1 (how well it matches query)
    certainty: float        # 0-1 (how reliable the memory is)
    recency_score: float    # 0-1 (1 = very recent)
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def rank_score(self) -> float:
        """Combined ranking score: relevance × certainty × recency."""
        return self.relevance * self.certainty * (0.5 + 0.5 * self.recency_score)

    def to_dict(self) -> dict:
        return {
            "content": self.content[:400],
            "source": self.source_layer,
            "relevance": round(self.relevance, 3),
            "certainty": round(self.certainty, 3),
            "rank": round(self.rank_score, 3),
            "tags": self.tags[:5],
        }


def _recency_score(created_at_ts: float, now: float = None) -> float:
    """Convert timestamp to 0-1 recency score (1 = just now, 0 = very old)."""
    now = now or time.time()
    age_hours = (now - created_at_ts) / 3600
    # Half-life of 24 hours → score ~0.5 at 1 day old
    return max(0.0, min(1.0, 0.5 ** (age_hours / 24)))


class MemoryPyramid:
    """
    Unified query across all five memory systems.

    Usage:
        pyramid = MemoryPyramid(dhikr, masalik, lawh_mahfuz, vector_store, knowledge_graph)
        hits = pyramid.query("zaheer khan", top_k=10)
        for hit in hits:
            print(f"[{hit.source_layer}] {hit.content[:100]} (rank={hit.rank_score:.2f})")
    """

    def __init__(
        self,
        dhikr=None,
        masalik=None,
        lawh_mahfuz=None,
        vector_store=None,
        knowledge_graph=None,
    ):
        self.dhikr = dhikr
        self.masalik = masalik
        self.lawh_mahfuz = lawh_mahfuz
        self.vector_store = vector_store
        self.knowledge_graph = knowledge_graph

    def query(self, text: str, top_k: int = 10) -> list[MemoryHit]:
        """
        Query all available layers and return merged, ranked results.
        Layers that are unavailable are silently skipped.
        """
        hits: list[MemoryHit] = []
        now = time.time()

        # ── Layer 1: Masalik (neural pathway spreading activation) ──
        if self.masalik:
            try:
                pathway_results = self.masalik.recall(text, top_k=top_k)
                for concept, activation in pathway_results:
                    node = self.masalik.concepts.get(concept)
                    certainty = node.resting_level if node else 0.3
                    hits.append(MemoryHit(
                        content=f"Associated concept: {concept}",
                        source_layer="masalik",
                        relevance=float(activation),
                        certainty=certainty,
                        recency_score=_recency_score(
                            node.last_activated if node else now - 3600, now
                        ),
                        tags=["concept", "association"],
                    ))
            except Exception as e:
                logger.debug("[PYRAMID] Masalik query failed: %s", e)

        # ── Layer 2: DhikrMemory (SQL keyword search) ──
        if self.dhikr:
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Use sync fallback if we're inside async context
                    memories = self._dhikr_sync_recall(text, top_k)
                else:
                    memories = loop.run_until_complete(
                        self.dhikr.recall(text, limit=top_k)
                    )
                for mem in memories:
                    content_str = str(mem.content)
                    recency = _recency_score(mem.recency.timestamp(), now)
                    hits.append(MemoryHit(
                        content=content_str,
                        source_layer="dhikr",
                        relevance=float(mem.importance),
                        certainty=min(0.9, 0.3 + mem.access_count * 0.05),
                        recency_score=recency,
                        tags=mem.tags or [],
                        metadata={"type": mem.memory_type},
                    ))
            except Exception as e:
                logger.debug("[PYRAMID] Dhikr query failed: %s", e)

        # ── Layer 3: VectorStore (semantic embedding search) ──
        if self.vector_store and getattr(self.vector_store, "_available", False):
            try:
                vector_results = self.vector_store.search(text, top_k=top_k)
                for result in vector_results:
                    hits.append(MemoryHit(
                        content=result.get("content", ""),
                        source_layer="vector",
                        relevance=float(result.get("score", 0.5)),
                        certainty=0.7,  # Vector search has good precision
                        recency_score=0.5,  # Unknown recency
                        tags=result.get("tags", []),
                    ))
            except Exception as e:
                logger.debug("[PYRAMID] VectorStore query failed: %s", e)

        # ── Layer 4: KnowledgeGraph (entity + relationship lookup) ──
        if self.knowledge_graph:
            try:
                entities = self.knowledge_graph.search_entities(text, limit=top_k)
                for entity in entities:
                    props = entity.get("properties", {})
                    content = f"{entity.get('name', '')} ({entity.get('type', 'entity')})"
                    if props:
                        content += f": {list(props.items())[:3]}"
                    hits.append(MemoryHit(
                        content=content,
                        source_layer="graph",
                        relevance=0.7,  # Entity match is high relevance
                        certainty=0.6,
                        recency_score=0.4,
                        tags=["entity", entity.get("type", "concept")],
                    ))
            except Exception as e:
                logger.debug("[PYRAMID] KnowledgeGraph query failed: %s", e)

        # ── Layer 5: LawhMahfuz (immutable facts) ──
        if self.lawh_mahfuz:
            try:
                lawh_results = self.lawh_mahfuz.search(text, top_k=top_k)
                for entry in lawh_results:
                    hits.append(MemoryHit(
                        content=entry.content,
                        source_layer="lawh",
                        relevance=0.9,  # Immutable facts are highly reliable
                        certainty=entry.certainty,
                        recency_score=1.0,  # Immutable facts never decay
                        tags=["immutable", entry.category],
                        metadata={"source": entry.source},
                    ))
            except Exception as e:
                logger.debug("[PYRAMID] LawhMahfuz query failed: %s", e)

        # ── Merge, deduplicate, rank ──
        deduplicated = self._deduplicate(hits)
        deduplicated.sort(key=lambda h: -h.rank_score)
        return deduplicated[:top_k]

    def _deduplicate(self, hits: list[MemoryHit]) -> list[MemoryHit]:
        """Remove near-duplicate hits (same content prefix from different layers)."""
        seen_prefixes: set[str] = set()
        unique: list[MemoryHit] = []
        for hit in hits:
            prefix = hit.content[:80].lower().strip()
            if prefix not in seen_prefixes:
                seen_prefixes.add(prefix)
                unique.append(hit)
        return unique

    def _dhikr_sync_recall(self, query: str, limit: int) -> list:
        """Synchronous fallback for dhikr recall when inside async context."""
        try:
            import asyncio
            import concurrent.futures
            # Run the coroutine in a separate thread with its own event loop
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    asyncio.run, self.dhikr.recall(query, limit=limit)
                )
                return future.result(timeout=5)
        except Exception:
            return []

    def format_for_prompt(self, text: str, top_k: int = 5) -> str:
        """
        Query and format results for injection into an agent system prompt.
        Returns empty string if nothing relevant found.
        """
        hits = self.query(text, top_k=top_k)
        if not hits:
            return ""

        lines = ["Unified Memory Recall:"]
        for hit in hits:
            source = hit.source_layer.upper()
            content_preview = hit.content[:150].replace("\n", " ")
            lines.append(f"  [{source}] {content_preview}")

        return "\n".join(lines)

    def stats(self) -> dict:
        """Return availability status of each memory layer."""
        return {
            "masalik": self.masalik is not None,
            "dhikr": self.dhikr is not None,
            "vector_store": self.vector_store is not None
                and getattr(self.vector_store, "_available", False),
            "knowledge_graph": self.knowledge_graph is not None,
            "lawh_mahfuz": self.lawh_mahfuz is not None,
        }
