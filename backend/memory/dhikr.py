"""
DHIKR Memory System (ذكر - Remembrance)
=========================================

"And We have certainly made the Quran easy for remembrance" - 54:17

Two memory subsystems working together:

A) MASALIK (مسالك - Pathways) — Neural pathway network
   How humans actually remember. No duplication. Priority by pathway strength.
   Learning strengthens paths. Forgetting prunes weak ones.

B) RECORDS (سجلات - Sijillat) — Transactional storage
   Message history, task logs, audit trails. These are records, not memory.
   Kept in SQLite for persistence and querying.

Quranic Memory Architecture:
  DHIKR (ذكر):     Re-activation that strengthens — not mere retrieval
  NISYAN (نسيان):   Pruning weak pathways — forgetting as mercy
  TAFAKKUR (تفكّر): Reflection creating new connections — insight
  HIKMAH (حكمة):    Pathways used so often they become permanent wisdom
  FITRAH (فطرة):    Innate pre-wired pathways — born knowing these

QCA Integration:
  The Dhikr system maps to QCA's 4-tier Lawh memory (85:22):
    Tier 1: Lawh (Immutable)   → Procedural axioms
    Tier 2: Kitab (Verified)   → Semantic knowledge (high importance)
    Tier 3: Dhikr (Active)     → Working memory / episodic (medium importance)
    Tier 4: Wahm (Conjecture)  → Low-certainty observations
"""

import hashlib
import json
import logging
import math
import os
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

logger = logging.getLogger("mizan.dhikr")

CHAT_PREFERENCE_LIMITS = {
    "language": 120,
    "greeting": 120,
    "avoid_greetings": 300,
    "custom_instructions": 2000,
    # "off" stops MIZAN's nightly self-review (Muhasaba) from posting corrections.
    "muhasaba": 8,
    # "off" stops MIZAN from bringing your words from other chats into a reply.
    "cross_chat_recall": 8,
    # "on" shows a notice's text on the lock screen (default: only "a new notice").
    "push_preview": 8,
}


# ── Phase 2: mizan.nlp native Arabic WSD (IP-4) ──────────────────────────
# Flag-gated: MIZAN_NLP_NATIVE_WSD=1 adds an ADVISORY native-sense note for
# Arabic lemmas in the recall query. Advisory-only: recall ranking and the
# returned memories are NEVER changed by this -- the note just flags which
# sense the native model reads, so same-root/different-sense concepts stay
# distinguishable to the reader. Default OFF = today's behavior bit-for-bit.

#: Native-sense gate: single source of truth in nlp/gate.py (measured
#: Track 3 evidence; operator-tunable via MIZAN_NLP_MIN_SENSE_*).
from nlp.gate import (  # noqa: E402
    passes_sense_gate,
)

_ARABIC_TOKEN_RE = re.compile(r"[\u0600-\u06FF]+")


def _nlp_native_wsd_enabled() -> bool:
    """True when the operator opted into Phase-2 native WSD."""
    return os.getenv("MIZAN_NLP_NATIVE_WSD", "").strip().lower() in ("1", "true", "yes")


def _arabic_lemmas(text: str, limit: int = 5) -> list[str]:
    """Distinct Arabic tokens in `text`, in order (native-WSD input lemmas)."""
    seen: list[str] = []
    for tok in _ARABIC_TOKEN_RE.findall(text or ""):
        if tok not in seen:
            seen.append(tok)
            if len(seen) >= limit:
                break
    return seen


def _native_sense_bits(text: str, lemmas: list[str]) -> list[str]:
    """Guarded native-WSD call. Returns ["lemma->sense_id (conf)", ...].

    Fail-closed: import failure / not-ready / inference exceptions are LOGGED
    and yield [] -- recall behavior continues unchanged (hikmah-stack:
    engines propose, the kernel admits; unknown stays unknown, never
    backfilled with a guess).
    """
    if not lemmas or not _nlp_native_wsd_enabled():
        return []
    try:
        from nlp import ModelNotReadyError, disambiguate, is_ready
    except ImportError as exc:
        logger.warning("mizan.nlp import failed (%s) -- recall advisory skipped", exc)
        return []
    if not is_ready():
        logger.info("mizan.nlp artifact not ready -- recall advisory skipped")
        return []
    bits: list[str] = []
    for lemma in lemmas:
        try:
            candidates = disambiguate(text, lemma)
        except ModelNotReadyError:
            logger.info("mizan.nlp became not-ready mid-call -- recall advisory skipped")
            return bits
        except Exception as exc:  # fail-closed: never break recall
            logger.warning("mizan.nlp inference failed for lemma %r (%s) -- skipped", lemma, exc)
            continue
        if not candidates:
            continue  # unknown stays unknown -- never backfilled
        sense_id, confidence = candidates[0]
        _, runner_up = candidates[1] if len(candidates) > 1 else (None, 0.0)
        margin = confidence - runner_up
        if passes_sense_gate(confidence, margin):
            bits.append(f"{lemma}->{sense_id} ({confidence:.2f})")
    return bits


def _native_sense_advisory(query: str) -> str:
    """Advisory native-WSD note for a recall query (Phase 2, IP-4).

    Returns "" when there is nothing to advise -- recall ranking itself is
    never changed by this function.
    """
    bits = _native_sense_bits(query, _arabic_lemmas(query))
    if not bits:
        return ""
    return "[Native sense advisory: " + ", ".join(bits) + "]"


def about(query: str, rows: list) -> list:
    """The stored statements that speak of what the query speaks of, best first.

    The query's distinctive words are those the user's statements use that
    carry more information than an average word of general language (Lughah's
    corpora): never "what", "the", "hai". A statement is about the query when
    it holds more than half of their information. Sharing only common words
    with a request recalls nothing.
    """
    from core.adaptive import tokenize
    from tadbir.ahl_dhikr import average_information, information

    texts = [set(tokenize(row[2])) for row in rows]
    used = set().union(*texts) if texts else set()
    floor = average_information()
    distinctive = {
        word: information(word)
        for word in set(tokenize(query))
        if word in used and information(word) > floor
    }
    needed = sum(distinctive.values())
    if needed <= 0:
        return []
    scored = []
    for index, (row, text) in enumerate(zip(rows, texts, strict=True)):
        held = sum(value for word, value in distinctive.items() if word in text)
        if 2 * held > needed:
            scored.append((held, -index, row))
    return [row for _held, _order, row in sorted(scored, key=lambda item: item[:2], reverse=True)]


def _stateless_message(metadata: str | None) -> bool:
    """Whether a stored message was sent as ``stateless`` (kept, never recalled)."""
    try:
        return bool(json.loads(metadata or "{}").get("stateless"))
    except (ValueError, AttributeError):
        return False


@dataclass
class Memory:
    """Base memory unit"""

    id: str = ""
    content: Any = None
    memory_type: str = "episodic"  # episodic | semantic | procedural
    importance: float = 0.5  # 0-1 Mizan scale
    recency: datetime = field(default_factory=lambda: datetime.now(UTC))
    access_count: int = 0
    agent_id: str = ""
    tags: list[str] = field(default_factory=list)
    embeddings: list[float] | None = None
    related_ids: list[str] = field(default_factory=list)
    source: str = ""  # Daftar provenance: manual | import | knowledge:<title> | chat:<session>
    expires: str = ""  # ISO time after which the memory is forgotten ("" = never)
    # Tadhkir (memory/tadhkir.py): FSRS stability, difficulty and last review.
    strength: dict | None = None

    def decay(self, hours_elapsed: float) -> float:
        """How strongly the memory is held after ``hours_elapsed`` without use:
        ACT-R activation from its recalls and age (dhikr strengthens, nisyan
        fades), weighed by importance; the same strength consolidation prunes by."""
        weight = memory_activation_weight(max(1.0, hours_elapsed * 3600.0), self.access_count)
        return float(weight * self.importance)


def rank_memories(
    query: str, memories: list["Memory"], now: datetime | None = None
) -> list["Memory"]:
    """Order memories by relevance × activation × importance (Mizan weighing).

    Relevance is BM25 over content and tags; activation is ACT-R base-level
    activation from access count and age, so repeated remembrance (dhikr)
    keeps a memory retrievable while unused ones fade (nisyan).
    """
    from core.adaptive import bm25_scores, normalise

    now = now or datetime.now(UTC)
    texts = [
        f"{m.content if isinstance(m.content, str) else json.dumps(m.content)} {' '.join(m.tags or [])}"
        for m in memories
    ]
    relevance = normalise(bm25_scores(query, texts))

    from memory import tadhkir

    def score(index: int) -> float:
        memory = memories[index]
        # The chance MIZAN still recalls it (FSRS), or ACT-R for one kept before Tadhkir.
        weight = tadhkir.retrievability(memory.strength, now)
        if weight is None:
            age = max(1.0, (now - memory.recency).total_seconds())
            weight = memory_activation_weight(age, memory.access_count)
        return float((0.25 + 0.75 * relevance[index]) * weight * (0.5 + 0.5 * memory.importance))

    order = sorted(range(len(memories)), key=score, reverse=True)
    return [memories[index] for index in order]


def memory_activation_weight(age_seconds: float, accesses: int, decay: float = 0.5) -> float:
    """ACT-R retrieval weight with the optimized-learning approximation.

    B ≈ ln(n / (1 − d)) − d·ln(L): n accesses over a lifetime L (seconds).
    """
    from core.adaptive import activation_weight

    n = max(1, int(accesses) + 1)
    activation = math.log(n / (1.0 - decay)) - decay * math.log(max(age_seconds, 1.0))
    return float(activation_weight(activation))


class DhikrMemorySystem:
    """
    Quranic memory architecture with two subsystems:

    1. MASALIK — Neural pathway network (how humans actually remember)
       No duplication. Pathways strengthen with use, decay from neglect.

    2. RECORDS — SQLite transactional storage (message history, task logs)
       These are records (sijillat), not memory. Stored for audit/retrieval.

    Inspired by: Lawh al-Mahfuz (لوح المحفوظ) - The Preserved Tablet (85:22)
    """

    def __init__(self, db_path: str = "mizan_memory.db"):
        self.db_path = db_path
        # For in-memory databases, keep a persistent connection
        # since each sqlite3.connect(":memory:") creates a new database
        self._persistent_conn: sqlite3.Connection | None = None
        if db_path == ":memory:":
            self._persistent_conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._init_db()

        # ── Masalik: Neural pathway network (the real memory) ──
        from memory.masalik import MasalikNetwork

        self.masalik = MasalikNetwork(
            persist_path=(
                str(Path(db_path).with_name("masalik_network.json"))
                if db_path != ":memory:"
                else None
            )
        )

        # ── KnowledgeGraph: Entity + relationship store ──
        try:
            from memory.knowledge_graph import KnowledgeGraph

            self.knowledge_graph = KnowledgeGraph(db_path=self.db_path)
        except Exception:
            self.knowledge_graph = None

        # ── LawhMahfuz: Immutable preserved memory ──
        try:
            import os

            from memory.lawh_mahfuz import LawhMahfuz

            lawh_dir = os.path.dirname(self.db_path) if self.db_path != ":memory:" else "/tmp"
            lawh_db = (
                os.path.join(lawh_dir, "lawh_mahfuz.db")
                if self.db_path != ":memory:"
                else ":memory:"
            )
            self.lawh_mahfuz = LawhMahfuz(db_path=lawh_db)
        except Exception:
            self.lawh_mahfuz = None

        # ── VectorStore: semantic recall when a Chroma server is configured ──
        self.vector_store = None
        vector_url = os.getenv("MIZAN_VECTOR_URL", "").strip()
        if vector_url and self.db_path != ":memory:":
            try:
                from memory.vector_store import VectorStore

                # One collection per memory database: private per-user
                # memories never share a vector index.
                scope = hashlib.sha256(os.path.abspath(self.db_path).encode()).hexdigest()[:16]
                store = VectorStore(chroma_url=vector_url, collection_name=f"mizan_{scope}")
                self.vector_store = store if store.is_available else None
            except Exception:
                self.vector_store = None

        # ── MemoryPyramid: Unified 5-layer query ──
        try:
            from memory.memory_pyramid import MemoryPyramid

            self.pyramid = MemoryPyramid(
                dhikr=self,
                masalik=self.masalik,
                lawh_mahfuz=self.lawh_mahfuz,
                vector_store=self.vector_store,
                knowledge_graph=self.knowledge_graph,
            )
        except Exception:
            self.pyramid = None

        # Working memory (short-term) - like immediate consciousness
        self.working_memory: dict[str, Memory] = {}
        self.working_capacity = 7  # Miller's Law meets Quranic pattern (7 heavens)

        # Long-term memory tiers (legacy caches — kept for compatibility)
        self._episodic_cache: dict[str, Memory] = {}
        self._semantic_cache: dict[str, Memory] = {}
        self._procedural_cache: dict[str, Memory] = {}

    def _get_conn(self) -> sqlite3.Connection:
        """Get a database connection. Reuses persistent connection for :memory: DBs."""
        if self._persistent_conn is not None:
            return self._persistent_conn
        return sqlite3.connect(self.db_path)

    def _release_conn(self, conn: sqlite3.Connection):
        """Close connection if it's not the persistent in-memory one."""
        if conn is not self._persistent_conn:
            conn.close()

    def _init_db(self):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                content TEXT,
                memory_type TEXT,
                importance REAL,
                recency TEXT,
                access_count INTEGER,
                agent_id TEXT,
                tags TEXT,
                related_ids TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS hikmah (
                id TEXT PRIMARY KEY,
                pattern TEXT,
                context TEXT,
                outcome TEXT,
                confidence REAL,
                applications INTEGER,
                created_at TEXT,
                source_agent TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS agent_profiles (
                id TEXT PRIMARY KEY,
                name TEXT,
                role TEXT,
                nafs_level INTEGER,
                capabilities TEXT,
                created_at TEXT,
                total_tasks INTEGER,
                success_rate REAL,
                error_count INTEGER,
                learning_iterations INTEGER,
                config TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS task_history (
                id TEXT PRIMARY KEY,
                agent_id TEXT,
                task TEXT,
                result TEXT,
                success INTEGER,
                duration_ms REAL,
                created_at TEXT,
                metadata TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS agent_messages (
                id TEXT PRIMARY KEY,
                session_id TEXT,
                role TEXT,
                content TEXT,
                agent_id TEXT,
                created_at TEXT,
                metadata TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS integrations (
                id TEXT PRIMARY KEY,
                name TEXT,
                type TEXT,
                config TEXT,
                enabled INTEGER,
                created_at TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                severity TEXT DEFAULT 'info',
                user_id TEXT,
                ip_address TEXT,
                resource TEXT,
                details TEXT,
                success INTEGER DEFAULT 1
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS preferences (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS chat_preferences (
                owner_id TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (owner_id, key)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS session_summaries (
                session_id TEXT PRIMARY KEY,
                summary TEXT NOT NULL,
                covered_last_id TEXT NOT NULL,
                covered_count INTEGER NOT NULL,
                method TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        # Daftar: provenance columns, added in place to older databases.
        existing = {row[1] for row in c.execute("PRAGMA table_info(memories)").fetchall()}
        for column in ("source", "created", "last_used", "expires"):
            if column not in existing:
                c.execute(f"ALTER TABLE memories ADD COLUMN {column} TEXT DEFAULT ''")
        # Tadhkir: each memory's FSRS strength.
        for column, kind in (
            ("stability", "REAL"),
            ("difficulty", "REAL"),
            ("last_review", "TEXT"),
        ):
            if column not in existing:
                c.execute(f"ALTER TABLE memories ADD COLUMN {column} {kind}")
        existing = {row[1] for row in c.execute("PRAGMA table_info(chat_preferences)").fetchall()}
        if "session_id" not in existing:
            c.execute("ALTER TABLE chat_preferences ADD COLUMN session_id TEXT DEFAULT ''")
        # Performance indexes
        c.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_audit_severity ON audit_log(severity)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_messages_session ON agent_messages(session_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_memories_agent ON memories(agent_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(memory_type)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_task_history_agent ON task_history(agent_id)")
        conn.commit()
        self._release_conn(conn)

    async def remember(
        self,
        content: Any,
        memory_type: str = "episodic",
        importance: float = 0.5,
        agent_id: str = "",
        tags: list[str] | None = None,
        *,
        source: str = "",
        expires: str = "",
    ) -> str:
        """
        Store a new memory — dual pathway:
        1. Masalik: Encode into neural pathways (strengthens, never duplicates)
        2. SQLite: Persist record for audit/retrieval
        """
        import uuid

        from memory import tadhkir

        # Said again: the memory already held is repeated, not copied ("he used to
        # repeat it thrice so that the people could understand it", Bukhari 95).
        repeated = self._repeated(content, memory_type, agent_id)
        if repeated is not None:
            self.masalik.encode(
                content if isinstance(content, str) else str(content), importance=importance
            )
            return repeated

        mem_id = str(uuid.uuid4())

        memory = Memory(
            id=mem_id,
            content=content,
            memory_type=memory_type,
            importance=importance,
            agent_id=agent_id,
            tags=tags or [],
            source=source,
            expires=expires,
            strength=tadhkir.learn(importance),
        )

        # ── Masalik: Encode into neural pathways ──
        # This is the real learning — strengthens pathways, no duplication
        text = str(content) if not isinstance(content, str) else content
        if tags:
            text += " " + " ".join(tags)
        self.masalik.encode(text, importance=importance)

        # Add to working memory (if important enough)
        if importance > 0.6:
            self._add_to_working(memory)

        # Persist record to database
        await self._persist(memory)
        if self.vector_store is not None:
            await self.vector_store.store(
                text, memory_id=mem_id, metadata={"memory_type": memory_type, "agent_id": agent_id}
            )

        # Update appropriate cache
        cache = self._get_cache(memory_type)
        cache[mem_id] = memory

        return mem_id

    def _repeated(self, content: Any, memory_type: str, agent_id: str) -> str | None:
        """The id of a live memory with the same words, reviewed as recalled and
        used (Tadhkir), or None. Whitespace and case aside, nothing is merged
        that the user did not say again."""
        from memory import tadhkir

        text = content if isinstance(content, str) else json.dumps(content)
        wanted = " ".join(str(text).split()).casefold()
        if not wanted:
            return None
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT id, content, stability, difficulty, last_review FROM memories "
                "WHERE memory_type = ? AND agent_id = ? "
                "AND (expires IS NULL OR expires = '' OR expires > ?)",
                (memory_type, agent_id or "", datetime.now(UTC).isoformat()),
            ).fetchall()
            for mem_id, stored, stability, difficulty, last_review in rows:
                if " ".join(str(stored or "").split()).casefold() != wanted:
                    continue
                state = tadhkir.review(
                    {"stability": stability, "difficulty": difficulty, "last_review": last_review},
                    tadhkir.GOOD,
                )
                conn.execute(
                    "UPDATE memories SET stability = ?, difficulty = ?, last_review = ?, "
                    "recency = ? WHERE id = ?",
                    (
                        state["stability"],
                        state["difficulty"],
                        state["last_review"],
                        datetime.now(UTC).isoformat(),
                        mem_id,
                    ),
                )
                conn.commit()
                return str(mem_id)
        finally:
            self._release_conn(conn)
        return None

    def _add_to_working(self, memory: Memory):
        """Add to working memory with capacity management"""
        if len(self.working_memory) >= self.working_capacity:
            # Remove least important
            least_important = min(
                self.working_memory, key=lambda k: self.working_memory[k].importance
            )
            del self.working_memory[least_important]
        self.working_memory[memory.id] = memory

    def _get_cache(self, memory_type: str) -> dict:
        caches = {
            "episodic": self._episodic_cache,
            "semantic": self._semantic_cache,
            "procedural": self._procedural_cache,
        }
        return caches.get(memory_type, self._episodic_cache)

    async def recall(
        self,
        query: str,
        memory_type: str | None = None,
        agent_id: str | None = None,
        limit: int = 10,
    ) -> list[Memory]:
        """
        Recall memories — dual pathway:
        1. Masalik: Spreading activation finds associated concepts (Dhikr)
        2. SQLite: Keyword search finds stored records

        The masalik recall also STRENGTHENS the recalled pathways —
        this is real Dhikr, not just retrieval.
        """
        # ── Masalik: Spreading activation (this IS remembering) ──
        # Side effect: strengthens the recalled pathways (Dhikr reinforcement)
        self.masalik.recall_context(query, top_k=8)

        # ── SQLite: Record search ──
        conn = self._get_conn()
        c = conn.cursor()

        sql = "SELECT * FROM memories WHERE (expires IS NULL OR expires = '' OR expires > ?)"
        params: list = [datetime.now(UTC).isoformat()]

        if memory_type:
            sql += " AND memory_type = ?"
            params.append(memory_type)
        if agent_id:
            sql += " AND agent_id = ?"
            params.append(agent_id)
        if query:
            words = query.strip().split()
            if words:
                # Use OR across words so partial matches still return results
                word_clauses = []
                for word in words:
                    escaped = word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                    word_clauses.append("(content LIKE ? ESCAPE '\\' OR tags LIKE ? ESCAPE '\\')")
                    params.extend([f"%{escaped}%", f"%{escaped}%"])
                sql += " AND (" + " OR ".join(word_clauses) + ")"

        # Wider candidate set; the final order weighs relevance and memory
        # activation below instead of stored importance alone.
        sql += " ORDER BY importance DESC, recency DESC LIMIT ?"
        params.append(max(limit, 1) * 4 if query else limit)

        c.execute(sql, params)
        names = [column[0] for column in c.description]
        rows = [dict(zip(names, row, strict=True)) for row in c.fetchall()]
        self._release_conn(conn)

        memories = []
        for row in rows:
            try:
                content = json.loads(row["content"]) if row["content"] else None
            except Exception:
                content = row["content"]

            memories.append(
                Memory(
                    id=row["id"],
                    content=content,
                    memory_type=row["memory_type"],
                    importance=row["importance"],
                    recency=datetime.fromisoformat(row["recency"])
                    if row["recency"]
                    else datetime.now(UTC),
                    access_count=row["access_count"],
                    agent_id=row["agent_id"],
                    tags=json.loads(row["tags"]) if row["tags"] else [],
                    strength={
                        "stability": row.get("stability"),
                        "difficulty": row.get("difficulty"),
                        "last_review": row.get("last_review"),
                    },
                )
            )

        if query and memories:
            memories = rank_memories(query, memories)[:limit]

        # A recalled memory is remembered: its access count and its strength grow
        # (Tadhkir: a Good review; one the same hour adds little, one after a gap
        # more). Daftar shows when each was last used.
        from memory import tadhkir

        for mem in memories:
            mem.access_count += 1
            mem.strength = tadhkir.review(mem.strength, tadhkir.GOOD)
        if memories:
            used = datetime.now(UTC).isoformat()
            conn = self._get_conn()
            try:
                conn.executemany(
                    "UPDATE memories SET access_count = ?, last_used = ?, stability = ?, "
                    "difficulty = ?, last_review = ? WHERE id = ?",
                    [
                        (
                            mem.access_count,
                            used,
                            (mem.strength or {}).get("stability"),
                            (mem.strength or {}).get("difficulty"),
                            (mem.strength or {}).get("last_review"),
                            mem.id,
                        )
                        for mem in memories
                    ],
                )
                conn.commit()
            finally:
                self._release_conn(conn)

        return memories

    def recall_pathways(self, query: str, top_k: int = 8) -> str:
        """
        Pure pathway recall — returns associated concepts from the neural network.
        Use this for agent system prompts where you need semantic context.
        """
        return cast(str, self.masalik.recall_context(query, top_k=top_k))

    async def recall_unified_async(self, query: str, top_k: int = 10) -> list:
        return await self.pyramid.query_async(query, top_k) if self.pyramid else []

    async def recall_unified_for_prompt_async(self, query: str, top_k: int = 5) -> str:
        advisory = _native_sense_advisory(query)
        base = (
            await self.pyramid.format_for_prompt_async(query, top_k)
            if self.pyramid
            else self.recall_pathways(query, top_k)
        )
        return f"{base}\n{advisory}" if advisory and base else advisory or base

    def recall_unified(self, query: str, top_k: int = 10) -> list:
        """
        Unified recall across all 5 memory layers via MemoryPyramid.
        Returns list of MemoryHit objects ranked by (relevance × certainty × recency).
        Falls back to standard dhikr recall if pyramid not available.
        """
        if self.pyramid:
            return cast(list, self.pyramid.query(query, top_k=top_k))
        return []

    def recall_unified_for_prompt(self, query: str, top_k: int = 5) -> str:
        """
        Recall unified memory and format for system prompt injection.
        Returns empty string if nothing relevant found.
        """
        # Phase 2 (mizan.nlp, IP-4): advisory native-sense note on the query.
        # Advisory-only -- the recalled memories below are unchanged; the note
        # keeps native/LLM sense readings visibly side-by-side (hikmah-stack:
        # contradiction visibility -- never silently fold one into the other).
        advisory = _native_sense_advisory(query)
        base = (
            self.pyramid.format_for_prompt(query, top_k=top_k)
            if self.pyramid
            else self.recall_pathways(query, top_k=top_k)
        )
        if advisory:
            return f"{base}\n{advisory}" if base else advisory
        return base

    async def _persist(self, memory: Memory):
        """Persist memory to database"""
        conn = self._get_conn()
        c = conn.cursor()

        try:
            content_str = (
                json.dumps(memory.content)
                if not isinstance(memory.content, str)
                else memory.content
            )
        except (TypeError, ValueError):
            content_str = str(memory.content)

        previous = c.execute(
            "SELECT created, source, last_used, expires, stability, difficulty, last_review "
            "FROM memories WHERE id = ?",
            (memory.id,),
        ).fetchone()
        created = (previous[0] if previous and previous[0] else "") or datetime.now(UTC).isoformat()
        strength = memory.strength or (
            {"stability": previous[4], "difficulty": previous[5], "last_review": previous[6]}
            if previous
            else {}
        )
        c.execute(
            """
            INSERT OR REPLACE INTO memories
            (id, content, memory_type, importance, recency, access_count, agent_id, tags,
             related_ids, source, created, last_used, expires, stability, difficulty, last_review)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                memory.id,
                content_str,
                memory.memory_type,
                memory.importance,
                memory.recency.isoformat(),
                memory.access_count,
                memory.agent_id,
                json.dumps(memory.tags),
                json.dumps(memory.related_ids),
                memory.source or (previous[1] if previous else ""),
                created,
                previous[2] if previous else "",
                memory.expires or (previous[3] if previous else ""),
                strength.get("stability"),
                strength.get("difficulty"),
                strength.get("last_review"),
            ),
        )
        conn.commit()
        self._release_conn(conn)

    async def consolidate(self, agent_id: str | None = None):
        """
        Memory consolidation — two processes:

        1. TAFAKKUR (تفكّر): Reflection creates new pathway connections
           between concepts that were frequently co-activated.

        2. NISYAN (نسيان): Prune weak pathways and old SQL records.
           Forgetting is mercy — keeps the mind efficient.

        "Those who remember Allah standing, sitting, and on their sides
         and reflect (yatafakkaruna) on the creation..." — 3:191
        """
        # ── Masalik: Tafakkur (create new connections from co-activation) ──
        tafakkur_result = self.masalik.tafakkur()

        # ── Masalik: Nisyan (prune weak pathways) ──
        nisyan_result = self.masalik.apply_nisyan()

        # ── SQLite: forget records whose retrieval strength has faded ──
        # Strength = ACT-R activation weight (age and number of recalls)
        # × importance; a week-old memory below MIZAN_MEMORY_FORGET_BELOW
        # (default 0.05) is pruned. Recalled memories keep their strength.
        now = datetime.now(UTC)
        cutoff = now - timedelta(days=7)
        try:
            forget_below = float(os.getenv("MIZAN_MEMORY_FORGET_BELOW", "0.05"))
        except ValueError:
            forget_below = 0.05
        conn = self._get_conn()
        c = conn.cursor()
        sql = "SELECT id, importance, recency, access_count FROM memories WHERE recency < ?"
        params: list = [cutoff.isoformat()]
        if agent_id:
            sql += " AND agent_id = ?"
            params.append(agent_id)
        faded = []
        for mem_id, importance, recency, accesses in c.execute(sql, params).fetchall():
            try:
                last = datetime.fromisoformat(recency)
            except (TypeError, ValueError):
                continue
            if last.tzinfo is None:
                last = last.replace(tzinfo=UTC)
            age = max(1.0, (now - last).total_seconds())
            strength = memory_activation_weight(age, accesses or 0) * float(importance or 0.0)
            if strength < forget_below:
                faded.append((mem_id,))
        c.executemany("DELETE FROM memories WHERE id = ?", faded)
        deleted = len(faded)
        conn.commit()
        self._release_conn(conn)

        return {
            "consolidated": True,
            "tafakkur": tafakkur_result,
            "nisyan": nisyan_result,
            "records_pruned": deleted,
        }

    async def save_agent_profile(self, profile: dict):
        """Save agent profile"""
        conn = self._get_conn()
        c = conn.cursor()
        c.execute(
            """
            INSERT OR REPLACE INTO agent_profiles
            (id, name, role, nafs_level, capabilities, created_at, total_tasks,
             success_rate, error_count, learning_iterations, config)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                profile.get("id"),
                profile.get("name"),
                profile.get("role"),
                profile.get("nafs_level", 1),
                json.dumps(profile.get("capabilities", [])),
                profile.get("created_at", datetime.now(UTC).isoformat()),
                profile.get("total_tasks", 0),
                profile.get("success_rate", 0.0),
                profile.get("error_count", 0),
                profile.get("learning_iterations", 0),
                json.dumps(profile.get("config", {})),
            ),
        )
        conn.commit()
        self._release_conn(conn)

    async def get_all_agents(self) -> list[dict]:
        """Get all agent profiles"""
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM agent_profiles")
        rows = c.fetchall()
        self._release_conn(conn)

        agents = []
        for row in rows:
            agents.append(
                {
                    "id": row[0],
                    "name": row[1],
                    "role": row[2],
                    "nafs_level": row[3],
                    "capabilities": json.loads(row[4]) if row[4] else [],
                    "created_at": row[5],
                    "total_tasks": row[6],
                    "success_rate": row[7],
                    "error_count": row[8],
                    "learning_iterations": row[9],
                    "config": json.loads(row[10]) if row[10] else {},
                }
            )
        return agents

    def _session_table(self, conn):
        conn.execute(
            "CREATE TABLE IF NOT EXISTS chat_sessions (session_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL)"
        )

    async def session_owner(self, session_id: str) -> str | None:
        conn = self._get_conn()
        try:
            self._session_table(conn)
            row = conn.execute(
                "SELECT owner_id FROM chat_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            conn.commit()
            return row[0] if row else None
        finally:
            self._release_conn(conn)

    async def authorize_session(
        self, session_id: str, owner_id: str, *, create=False, adopt_legacy=False
    ) -> bool:
        conn = self._get_conn()
        try:
            self._session_table(conn)
            # One SQLite transaction makes concurrent first claims atomic.
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT owner_id FROM chat_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            if row:
                allowed = row[0] == owner_id
            else:
                legacy = conn.execute(
                    "SELECT 1 FROM agent_messages WHERE session_id = ? LIMIT 1", (session_id,)
                ).fetchone()
                allowed = (create and not legacy) or (adopt_legacy and bool(legacy))
                if allowed:
                    conn.execute("INSERT INTO chat_sessions VALUES (?, ?)", (session_id, owner_id))
            conn.commit()
            return cast(bool, allowed)
        finally:
            self._release_conn(conn)

    async def save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        agent_id: str = "",
        metadata: dict | None = None,
    ) -> str:
        """Save chat message"""
        import uuid

        msg_id = str(uuid.uuid4())
        conn = self._get_conn()
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO agent_messages (id, session_id, role, content, agent_id, created_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                msg_id,
                session_id,
                role,
                content,
                agent_id,
                datetime.now(UTC).isoformat(),
                json.dumps(metadata or {}),
            ),
        )
        conn.commit()
        self._release_conn(conn)
        return msg_id

    async def get_session_summary(self, session_id: str) -> dict | None:
        """The persisted running summary of a long session, if any."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT summary, covered_last_id, covered_count, method, updated_at "
                "FROM session_summaries WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        finally:
            self._release_conn(conn)
        if row is None:
            return None
        return {
            "summary": row[0],
            "covered_last_id": row[1],
            "covered_count": row[2],
            "method": row[3],
            "updated_at": row[4],
        }

    async def save_session_summary(
        self,
        session_id: str,
        *,
        summary: str,
        covered_last_id: str,
        covered_count: int,
        method: str,
    ) -> None:
        conn = self._get_conn()
        try:
            conn.execute(
                "INSERT INTO session_summaries VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(session_id) DO UPDATE SET summary = excluded.summary, "
                "covered_last_id = excluded.covered_last_id, "
                "covered_count = excluded.covered_count, method = excluded.method, "
                "updated_at = excluded.updated_at",
                (
                    session_id,
                    summary,
                    covered_last_id,
                    int(covered_count),
                    method,
                    datetime.now(UTC).isoformat(),
                ),
            )
            conn.commit()
        finally:
            self._release_conn(conn)

    async def get_messages(
        self, session_id: str, limit: int | None = 50, before_id: str | None = None
    ) -> list[dict]:
        """Get messages for a session, oldest first.

        ``limit=None`` returns the whole session. ``before_id`` pages backwards:
        only messages older than that message are returned.
        """
        conn = self._get_conn()
        c = conn.cursor()
        query = """
            SELECT id, session_id, role, content, agent_id, created_at, metadata
            FROM agent_messages WHERE session_id = ?
        """
        params: list = [session_id]
        if before_id:
            query += """
            AND rowid < (SELECT rowid FROM agent_messages WHERE id = ? AND session_id = ?)
            """
            params += [before_id, session_id]
        query += " ORDER BY created_at DESC, rowid DESC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(int(limit))
        c.execute(query, params)
        rows = c.fetchall()
        self._release_conn(conn)

        return [
            {
                "id": r[0],
                "session_id": r[1],
                "role": r[2],
                "content": r[3],
                "agent_id": r[4],
                "created_at": r[5],
                "metadata": json.loads(r[6]) if r[6] else {},
            }
            for r in reversed(rows)
        ]

    async def recall_conversations(
        self, owner_id: str, query: str, *, exclude_session: str, limit: int = 5
    ) -> list[dict]:
        """Recall bounded, attributed user statements from owned conversations.

        Assistant replies are not facts or training labels. Legacy sessions
        without an owner are deliberately excluded, including for admins. Only
        real chats are recalled: messages sent as ``stateless`` (tests,
        evaluations) never are, and neither is a message Amanah reads as an
        instruction aimed at the AI, since in another chat it is outside text.
        """
        if not owner_id:
            return []
        conn = self._get_conn()
        try:
            self._session_table(conn)
            rows = conn.execute(
                """SELECT m.id, m.session_id, m.content, m.created_at, m.metadata
                FROM agent_messages m JOIN chat_sessions s ON s.session_id = m.session_id
                WHERE s.owner_id = ? AND m.session_id != ? AND m.role = 'user'
                  AND m.content NOT LIKE '/%'
                ORDER BY m.created_at DESC, m.rowid DESC LIMIT 200""",
                (owner_id, exclude_session),
            ).fetchall()
        finally:
            self._release_conn(conn)
        from tadbir import amanah

        rows = [row for row in rows if not _stateless_message(row[4])]
        candidates = about(query, rows)
        wanted = max(0, min(limit, 5))
        selected: list = []
        for row in candidates:
            if len(selected) >= wanted:
                break
            if not amanah.scan(row[2], "recalled chat"):
                selected.append(row)
        return [
            {
                "message_id": row[0],
                "session_id": row[1],
                "content": row[2][:1000],
                "created_at": row[3],
                "source": "prior_user_statement",
            }
            for row in selected
        ]

    async def conversation_counts(self, owner_id: str) -> dict:
        conn = self._get_conn()
        try:
            self._session_table(conn)
            row = conn.execute(
                """SELECT COUNT(DISTINCT s.session_id), COUNT(m.id)
                FROM chat_sessions s LEFT JOIN agent_messages m ON m.session_id = s.session_id
                WHERE s.owner_id = ?""",
                (owner_id,),
            ).fetchone()
            return {"owned_sessions": row[0], "stored_chat_messages": row[1]}
        finally:
            self._release_conn(conn)

    async def list_sessions(
        self, limit: int = 20, owner_id: str | None = None, offset: int = 0
    ) -> list[dict]:
        """List recent chat sessions with metadata, newest first (``offset`` pages)."""
        conn = self._get_conn()
        self._session_table(conn)
        c = conn.cursor()
        c.execute(
            """
            SELECT m.session_id,
                   MIN(m.created_at) as started_at,
                   MAX(m.created_at) as last_message_at,
                   COUNT(*) as message_count,
                   (SELECT content FROM agent_messages
                    WHERE session_id = m.session_id AND role = 'user'
                    ORDER BY created_at LIMIT 1) as first_message
            FROM agent_messages m
            WHERE (? IS NULL OR m.session_id IN (SELECT session_id FROM chat_sessions WHERE owner_id = ?))
            GROUP BY m.session_id
            ORDER BY MAX(m.created_at) DESC
            LIMIT ? OFFSET ?
        """,
            (owner_id, owner_id, limit, max(0, offset)),
        )
        rows = c.fetchall()
        self._release_conn(conn)

        return [
            {
                "session_id": r[0],
                "started_at": r[1],
                "last_message_at": r[2],
                "message_count": r[3],
                "first_message": (r[4] or "")[:80] if len(r) > 4 else "",
            }
            for r in rows
        ]

    # ── Preferences ─────────────────────────────────────────────

    @staticmethod
    def _validate_chat_preference(owner_id: str, key: str | None = None) -> None:
        if not isinstance(owner_id, str) or not owner_id.strip():
            raise ValueError("An authenticated owner is required")
        if key is not None and key not in CHAT_PREFERENCE_LIMITS:
            raise ValueError("Unsupported chat preference")

    async def get_chat_preferences(self, owner_id: str) -> list[dict]:
        """Read explicitly saved user preferences, independent of transcript age.

        These are user instructions, not verified knowledge or model training.
        Global provider settings and legacy chat text are never promoted here.
        """
        self._validate_chat_preference(owner_id)
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT key, value, updated_at FROM chat_preferences "
                "WHERE owner_id = ? ORDER BY key",
                (owner_id,),
            ).fetchall()
            return [
                {
                    "key": row[0],
                    "value": row[1],
                    "updated_at": row[2],
                    "source": "explicit_user_preference",
                }
                for row in rows
            ]
        finally:
            self._release_conn(conn)

    async def set_chat_preference(self, owner_id: str, key: str, value: str) -> dict:
        """Replace one preference for the authenticated owner only."""
        self._validate_chat_preference(owner_id, key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Preference value must not be empty; delete it to forget it")
        value = value.strip()
        if len(value) > CHAT_PREFERENCE_LIMITS[key]:
            raise ValueError(f"Preference exceeds {CHAT_PREFERENCE_LIMITS[key]} characters")
        updated_at = datetime.now(UTC).isoformat()
        from workspace.context import current_chat_session

        session_id = current_chat_session() or ""
        conn = self._get_conn()
        try:
            conn.execute(
                "INSERT INTO chat_preferences (owner_id, key, value, updated_at, session_id) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT(owner_id, key) DO UPDATE SET "
                "value = excluded.value, updated_at = excluded.updated_at, "
                "session_id = excluded.session_id",
                (owner_id, key, value, updated_at, session_id),
            )
            conn.commit()
        finally:
            self._release_conn(conn)
        return {
            "key": key,
            "value": value,
            "updated_at": updated_at,
            "source": "explicit_user_preference",
        }

    async def delete_chat_preference(self, owner_id: str, key: str) -> bool:
        """Forget a saved preference without changing another owner's record."""
        self._validate_chat_preference(owner_id, key)
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                "DELETE FROM chat_preferences WHERE owner_id = ? AND key = ?", (owner_id, key)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            self._release_conn(conn)

    # ── Hikmah (Wisdom Patterns) ─────────────────────────────────

    async def store_hikmah(
        self,
        pattern: str,
        context: str,
        outcome: str,
        confidence: float = 0.5,
        source_agent: str = "",
    ) -> str:
        """Persist a learned wisdom pattern to the hikmah table."""
        import uuid as _uuid

        hikmah_id = str(_uuid.uuid4())
        conn = self._get_conn()
        c = conn.cursor()
        # Avoid duplicates: if same pattern+context exists, update confidence
        c.execute(
            "SELECT id, applications, confidence FROM hikmah WHERE pattern = ? AND context = ?",
            (pattern[:500], context[:500]),
        )
        existing = c.fetchone()
        if existing:
            new_apps = (existing[1] or 0) + 1
            new_conf = min(1.0, existing[2] + 0.05)
            c.execute(
                "UPDATE hikmah SET applications = ?, confidence = ? WHERE id = ?",
                (new_apps, new_conf, existing[0]),
            )
            hikmah_id = existing[0]
        else:
            c.execute(
                """INSERT INTO hikmah (id, pattern, context, outcome, confidence, applications, created_at, source_agent)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    hikmah_id,
                    pattern[:500],
                    context[:500],
                    outcome[:1000],
                    confidence,
                    1,
                    datetime.now(UTC).isoformat(),
                    source_agent,
                ),
            )
        conn.commit()
        self._release_conn(conn)
        return hikmah_id

    async def count_hikmah(self, agent_id: str = "") -> int:
        """Total learned patterns (not capped like the in-prompt list)."""
        conn = self._get_conn()
        try:
            if agent_id:
                row = conn.execute(
                    "SELECT COUNT(*) FROM hikmah WHERE source_agent = ?", (agent_id,)
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) FROM hikmah").fetchone()
        finally:
            self._release_conn(conn)
        return int(row[0]) if row else 0

    async def load_hikmah(self, agent_id: str = "", limit: int = 20) -> list[dict]:
        """Load learned wisdom patterns from the hikmah table."""
        conn = self._get_conn()
        c = conn.cursor()
        if agent_id:
            c.execute(
                """SELECT pattern, context, outcome, confidence, applications
                   FROM hikmah WHERE source_agent = ?
                   ORDER BY confidence DESC, applications DESC LIMIT ?""",
                (agent_id, limit),
            )
        else:
            c.execute(
                """SELECT pattern, context, outcome, confidence, applications
                   FROM hikmah ORDER BY confidence DESC, applications DESC LIMIT ?""",
                (limit,),
            )
        rows = c.fetchall()
        self._release_conn(conn)
        return [
            {
                "pattern": r[0],
                "context": r[1],
                "outcome": r[2],
                "confidence": r[3],
                "applications": r[4],
            }
            for r in rows
        ]

    async def get_preference(self, key: str, default: str = "") -> str:
        """Read a persisted preference by key."""
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT value FROM preferences WHERE key = ?", (key,))
        row = c.fetchone()
        self._release_conn(conn)
        return row[0] if row else default

    async def set_preference(self, key: str, value: str) -> None:
        """Upsert a persisted preference."""
        from datetime import UTC, datetime

        conn = self._get_conn()
        c = conn.cursor()
        c.execute(
            """INSERT INTO preferences (key, value, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at""",
            (key, value, datetime.now(UTC).isoformat()),
        )
        conn.commit()
        self._release_conn(conn)

    async def get_all_preferences(self) -> dict[str, str]:
        """Read all persisted preferences as a dict."""
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT key, value FROM preferences")
        rows = c.fetchall()
        self._release_conn(conn)
        return {r[0]: r[1] for r in rows}

    async def save_task(
        self,
        agent_id: str,
        task: str,
        result: str,
        success: bool,
        duration_ms: float,
        metadata: dict | None = None,
    ) -> str:
        """Save task history"""
        import uuid

        task_id = str(uuid.uuid4())
        conn = self._get_conn()
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO task_history (id, agent_id, task, result, success, duration_ms, created_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                task_id,
                agent_id,
                task,
                result,
                int(success),
                duration_ms,
                datetime.now(UTC).isoformat(),
                json.dumps(metadata or {}),
            ),
        )
        conn.commit()
        self._release_conn(conn)
        return task_id

    async def get_task_history(self, agent_id: str | None = None, limit: int = 100) -> list[dict]:
        """Get task history"""
        conn = self._get_conn()
        c = conn.cursor()

        if agent_id:
            c.execute(
                "SELECT * FROM task_history WHERE agent_id = ? ORDER BY created_at DESC LIMIT ?",
                (agent_id, limit),
            )
        else:
            c.execute("SELECT * FROM task_history ORDER BY created_at DESC LIMIT ?", (limit,))

        rows = c.fetchall()
        self._release_conn(conn)

        return [
            {
                "id": r[0],
                "agent_id": r[1],
                "task": r[2],
                "result": r[3],
                "success": bool(r[4]),
                "duration_ms": r[5],
                "created_at": r[6],
                "metadata": json.loads(r[7]) if r[7] else {},
            }
            for r in rows
        ]

    async def save_integration(self, integration: dict) -> str:
        """Save integration config"""
        import uuid

        int_id = integration.get("id") or str(uuid.uuid4())
        conn = self._get_conn()
        c = conn.cursor()
        c.execute(
            """
            INSERT OR REPLACE INTO integrations (id, name, type, config, enabled, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (
                int_id,
                integration.get("name"),
                integration.get("type"),
                json.dumps(integration.get("config", {})),
                int(integration.get("enabled", True)),
                datetime.now(UTC).isoformat(),
            ),
        )
        conn.commit()
        self._release_conn(conn)
        return int_id

    async def get_integrations(self) -> list[dict]:
        """Get all integrations"""
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM integrations")
        rows = c.fetchall()
        self._release_conn(conn)
        return [
            {
                "id": r[0],
                "name": r[1],
                "type": r[2],
                "config": json.loads(r[3]) if r[3] else {},
                "enabled": bool(r[4]),
                "created_at": r[5],
            }
            for r in rows
        ]

    # ── Audit Log Persistence ────────────────────────────────────────────

    async def log_audit(
        self,
        event_type: str,
        severity: str = "info",
        user_id: str = "",
        ip_address: str = "",
        resource: str = "",
        details: dict | None = None,
        success: bool = True,
    ):
        """Persist an audit log entry to SQLite."""
        conn = self._get_conn()
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO audit_log (timestamp, event_type, severity, user_id,
                                   ip_address, resource, details, success)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                datetime.now(UTC).isoformat(),
                event_type,
                severity,
                user_id,
                ip_address,
                resource,
                json.dumps(details or {}),
                int(success),
            ),
        )
        conn.commit()
        self._release_conn(conn)

    async def get_audit_logs(
        self, limit: int = 100, severity: str | None = None, event_type: str | None = None
    ) -> list[dict]:
        """Query audit logs with optional filtering."""
        conn = self._get_conn()
        c = conn.cursor()
        query = "SELECT * FROM audit_log"
        params: list = []
        conditions = []
        if severity:
            conditions.append("severity = ?")
            params.append(severity)
        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        c.execute(query, params)
        rows = c.fetchall()
        self._release_conn(conn)
        cols = [
            "id",
            "timestamp",
            "event_type",
            "severity",
            "user_id",
            "ip_address",
            "resource",
            "details",
            "success",
        ]
        results = []
        for r in rows:
            entry = dict(zip(cols, r, strict=False))
            if entry.get("details"):
                try:
                    entry["details"] = json.loads(entry["details"])
                except (json.JSONDecodeError, TypeError):
                    pass
            entry["success"] = bool(entry.get("success", 1))
            results.append(entry)
        return results

    async def get_audit_summary(self) -> dict:
        """Get audit log summary statistics."""
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM audit_log")
        total = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM audit_log WHERE severity = 'warning'")
        warnings = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM audit_log WHERE severity = 'error'")
        errors = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM audit_log WHERE severity = 'critical'")
        critical = c.fetchone()[0]
        self._release_conn(conn)
        return {
            "total_events": total,
            "warnings": warnings,
            "errors": errors,
            "critical": critical,
        }

    # ── QCA Lawh Memory Bridge ──────────────────────────────────────────

    def get_qca_lawh(self):
        """
        Get QCA's 4-tier Lawh memory instance.
        Bridges Dhikr's 3-tier (episodic/semantic/procedural) with
        QCA's 4-tier (Lawh immutable / Kitab verified / Dhikr active / Wahm conjecture).
        """
        try:
            from qca.engine import LawhMemory

            return LawhMemory()
        except ImportError:
            return None

    async def remember_with_mizan(
        self,
        content: Any,
        memory_type: str = "episodic",
        importance: float = 0.5,
        agent_id: str = "",
        tags: list[str] | None = None,
        certainty_level: str = "zann",
    ) -> str:
        """
        Store a new memory with QCA Mizan-weighted importance.
        The certainty_level maps to QCA epistemic scale:
          yaqin (1.0) → highest importance
          zann_rajih (0.75) → high importance
          zann (0.50) → medium importance
          shakk (0.25) → low importance
          wahm (0.05) → very low importance
        """
        # Map certainty to importance boost
        mizan_weights = {
            "yaqin": 1.0,
            "zann_rajih": 0.75,
            "zann": 0.5,
            "shakk": 0.25,
            "wahm": 0.05,
        }
        mizan_factor = mizan_weights.get(certainty_level, 0.5)
        adjusted_importance = min(1.0, importance * (0.5 + mizan_factor * 0.5))

        return await self.remember(content, memory_type, adjusted_importance, agent_id, tags)
