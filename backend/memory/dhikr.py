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

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any


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

    def decay(self, hours_elapsed: float) -> float:
        """
        Memory decay following Quranic pattern:
        - Frequently accessed memories persist (Dhikr strengthens)
        - Unused memories fade (Nisyan - نسيان)
        Half-life based on importance
        """
        half_life_hours = self.importance * 720  # Max 30 days half-life
        decay_factor = 0.5 ** (hours_elapsed / max(half_life_hours, 1))
        return self.importance * decay_factor * (1 + 0.1 * self.access_count)


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

        self.masalik = MasalikNetwork()

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

        # ── MemoryPyramid: Unified 5-layer query ──
        try:
            from memory.memory_pyramid import MemoryPyramid
            self.pyramid = MemoryPyramid(
                dhikr=self,
                masalik=self.masalik,
                lawh_mahfuz=self.lawh_mahfuz,
                vector_store=None,
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
        tags: list[str] = None,
    ) -> str:
        """
        Store a new memory — dual pathway:
        1. Masalik: Encode into neural pathways (strengthens, never duplicates)
        2. SQLite: Persist record for audit/retrieval
        """
        import uuid

        mem_id = str(uuid.uuid4())

        memory = Memory(
            id=mem_id,
            content=content,
            memory_type=memory_type,
            importance=importance,
            agent_id=agent_id,
            tags=tags or [],
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

        # Update appropriate cache
        cache = self._get_cache(memory_type)
        cache[mem_id] = memory

        return mem_id

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
        self, query: str, memory_type: str = None, agent_id: str = None, limit: int = 10
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

        sql = "SELECT * FROM memories WHERE 1=1"
        params = []

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

        sql += " ORDER BY importance DESC, recency DESC LIMIT ?"
        params.append(limit)

        c.execute(sql, params)
        rows = c.fetchall()
        self._release_conn(conn)

        memories = []
        for row in rows:
            try:
                content = json.loads(row[1]) if row[1] else None
            except Exception:
                content = row[1]

            memories.append(
                Memory(
                    id=row[0],
                    content=content,
                    memory_type=row[2],
                    importance=row[3],
                    recency=datetime.fromisoformat(row[4]) if row[4] else datetime.now(UTC),
                    access_count=row[5],
                    agent_id=row[6],
                    tags=json.loads(row[7]) if row[7] else [],
                )
            )

        # Update access count for recalled memories
        for mem in memories:
            mem.access_count += 1

        return memories

    def recall_pathways(self, query: str, top_k: int = 8) -> str:
        """
        Pure pathway recall — returns associated concepts from the neural network.
        Use this for agent system prompts where you need semantic context.
        """
        return self.masalik.recall_context(query, top_k=top_k)

    def recall_unified(self, query: str, top_k: int = 10) -> list:
        """
        Unified recall across all 5 memory layers via MemoryPyramid.
        Returns list of MemoryHit objects ranked by (relevance × certainty × recency).
        Falls back to standard dhikr recall if pyramid not available.
        """
        if self.pyramid:
            return self.pyramid.query(query, top_k=top_k)
        return []

    def recall_unified_for_prompt(self, query: str, top_k: int = 5) -> str:
        """
        Recall unified memory and format for system prompt injection.
        Returns empty string if nothing relevant found.
        """
        if self.pyramid:
            return self.pyramid.format_for_prompt(query, top_k=top_k)
        return self.recall_pathways(query, top_k=top_k)

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

        c.execute(
            """
            INSERT OR REPLACE INTO memories
            (id, content, memory_type, importance, recency, access_count, agent_id, tags, related_ids)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            ),
        )
        conn.commit()
        self._release_conn(conn)

    async def consolidate(self, agent_id: str = None):
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

        # ── SQLite: Prune old low-importance records ──
        cutoff = datetime.now(UTC) - timedelta(days=30)
        conn = self._get_conn()
        c = conn.cursor()

        sql = """
            DELETE FROM memories
            WHERE importance < 0.3
            AND recency < ?
            AND access_count < 3
        """
        params = [cutoff.isoformat()]
        if agent_id:
            sql += " AND agent_id = ?"
            params.append(agent_id)

        c.execute(sql, params)
        deleted = c.rowcount
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

    async def save_message(
        self, session_id: str, role: str, content: str, agent_id: str = "", metadata: dict = None
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

    async def get_messages(self, session_id: str, limit: int = 50) -> list[dict]:
        """Get messages for a session"""
        conn = self._get_conn()
        c = conn.cursor()
        c.execute(
            """
            SELECT id, session_id, role, content, agent_id, created_at, metadata
            FROM agent_messages WHERE session_id = ? ORDER BY created_at ASC LIMIT ?
        """,
            (session_id, limit),
        )
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
            for r in rows
        ]

    async def list_sessions(self, limit: int = 20) -> list[dict]:
        """List recent chat sessions with metadata"""
        conn = self._get_conn()
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
            GROUP BY m.session_id
            ORDER BY MAX(m.created_at) DESC
            LIMIT ?
        """,
            (limit,),
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
        from datetime import datetime, UTC

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
        metadata: dict = None,
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

    async def get_task_history(self, agent_id: str = None, limit: int = 100) -> list[dict]:
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
        details: dict = None,
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
        self, limit: int = 100, severity: str = None, event_type: str = None
    ) -> list[dict]:
        """Query audit logs with optional filtering."""
        conn = self._get_conn()
        c = conn.cursor()
        query = "SELECT * FROM audit_log"
        params = []
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
        tags: list[str] = None,
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
