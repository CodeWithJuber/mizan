"""
DHIKR Memory System (ذكر - Remembrance)
=========================================

"And We have certainly made the Quran easy for remembrance" - 54:17

Three Memory Types from Quranic Epistemology:

1. EPISODIC (Qisas - قصص): Event/episode memory - Stories & experiences
   "We relate to you the best of stories" - 12:3

2. SEMANTIC (Ilm - علم): Conceptual knowledge - Facts & relationships
   "And He taught Adam the names of all things" - 2:31

3. PROCEDURAL (Sunnah - سنة): How-to / skill memory - Ways of doing
   "You will not find in Our way any change" - 35:43

Memory consolidation follows Tafakkur cycle (تفكر - deep reflection)
Forgetting follows Nisyan principle (نسيان) - selective forgetting for optimization

QCA Integration:
  The Dhikr system maps to QCA's 4-tier Lawh memory (85:22):
    Tier 1: Lawh (Immutable)   → Procedural axioms
    Tier 2: Kitab (Verified)   → Semantic knowledge (high importance)
    Tier 3: Dhikr (Active)     → Working memory / episodic (medium importance)
    Tier 4: Wahm (Conjecture)  → Low-certainty observations
"""

import json
import hashlib
import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
import sqlite3
import pickle
import os


@dataclass
class Memory:
    """Base memory unit"""
    id: str = ""
    content: Any = None
    memory_type: str = "episodic"  # episodic | semantic | procedural
    importance: float = 0.5        # 0-1 Mizan scale
    recency: datetime = field(default_factory=datetime.utcnow)
    access_count: int = 0
    agent_id: str = ""
    tags: List[str] = field(default_factory=list)
    embeddings: Optional[List[float]] = None
    related_ids: List[str] = field(default_factory=list)
    
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
    Three-tier Quranic memory architecture
    Inspired by: Luh Mahfuz (لوح محفوظ) - The Preserved Tablet (85:22)
    """

    def __init__(self, db_path: str = "mizan_memory.db"):
        self.db_path = db_path
        # For in-memory databases, keep a persistent connection
        # since each sqlite3.connect(":memory:") creates a new database
        self._persistent_conn: Optional[sqlite3.Connection] = None
        if db_path == ":memory:":
            self._persistent_conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._init_db()

        # Working memory (short-term) - like immediate consciousness
        self.working_memory: Dict[str, Memory] = {}
        self.working_capacity = 7  # Miller's Law meets Quranic pattern (7 heavens)

        # Long-term memory tiers
        self._episodic_cache: Dict[str, Memory] = {}
        self._semantic_cache: Dict[str, Memory] = {}
        self._procedural_cache: Dict[str, Memory] = {}

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
        conn.commit()
        self._release_conn(conn)

    async def remember(self, content: Any, memory_type: str = "episodic",
                       importance: float = 0.5, agent_id: str = "",
                       tags: List[str] = None) -> str:
        """Store a new memory"""
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
        
        # Add to working memory (if important enough)
        if importance > 0.6:
            self._add_to_working(memory)
        
        # Persist to database
        await self._persist(memory)
        
        # Update appropriate cache
        cache = self._get_cache(memory_type)
        cache[mem_id] = memory
        
        return mem_id
    
    def _add_to_working(self, memory: Memory):
        """Add to working memory with capacity management"""
        if len(self.working_memory) >= self.working_capacity:
            # Remove least important
            least_important = min(self.working_memory, 
                                   key=lambda k: self.working_memory[k].importance)
            del self.working_memory[least_important]
        self.working_memory[memory.id] = memory
    
    def _get_cache(self, memory_type: str) -> Dict:
        caches = {
            "episodic": self._episodic_cache,
            "semantic": self._semantic_cache,
            "procedural": self._procedural_cache,
        }
        return caches.get(memory_type, self._episodic_cache)
    
    async def recall(self, query: str, memory_type: str = None,
                     agent_id: str = None, limit: int = 10) -> List[Memory]:
        """Recall memories by query"""
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
            # Split query into words and match each one (AND logic)
            words = query.strip().split()
            for word in words:
                escaped_word = word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                sql += " AND (content LIKE ? ESCAPE '\\' OR tags LIKE ? ESCAPE '\\')"
                params.extend([f"%{escaped_word}%", f"%{escaped_word}%"])
        
        sql += " ORDER BY importance DESC, recency DESC LIMIT ?"
        params.append(limit)
        
        c.execute(sql, params)
        rows = c.fetchall()
        self._release_conn(conn)

        memories = []
        for row in rows:
            try:
                content = json.loads(row[1]) if row[1] else None
            except:
                content = row[1]
            
            memories.append(Memory(
                id=row[0],
                content=content,
                memory_type=row[2],
                importance=row[3],
                recency=datetime.fromisoformat(row[4]) if row[4] else datetime.utcnow(),
                access_count=row[5],
                agent_id=row[6],
                tags=json.loads(row[7]) if row[7] else [],
            ))
        
        # Update access count for recalled memories
        for mem in memories:
            mem.access_count += 1
        
        return memories
    
    async def _persist(self, memory: Memory):
        """Persist memory to database"""
        conn = self._get_conn()
        c = conn.cursor()
        
        try:
            content_str = json.dumps(memory.content) if not isinstance(memory.content, str) else memory.content
        except:
            content_str = str(memory.content)
        
        c.execute("""
            INSERT OR REPLACE INTO memories 
            (id, content, memory_type, importance, recency, access_count, agent_id, tags, related_ids)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            memory.id,
            content_str,
            memory.memory_type,
            memory.importance,
            memory.recency.isoformat(),
            memory.access_count,
            memory.agent_id,
            json.dumps(memory.tags),
            json.dumps(memory.related_ids),
        ))
        conn.commit()
        self._release_conn(conn)
    
    async def consolidate(self, agent_id: str = None):
        """
        Memory consolidation - Tafakkur process
        Removes low-importance, old memories (Nisyan)
        Strengthens important, frequently accessed memories
        """
        cutoff = datetime.utcnow() - timedelta(days=30)
        
        conn = self._get_conn()
        c = conn.cursor()
        
        # Delete low-importance old memories
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
        
        return {"consolidated": True, "pruned": deleted}
    
    async def save_agent_profile(self, profile: Dict):
        """Save agent profile"""
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("""
            INSERT OR REPLACE INTO agent_profiles 
            (id, name, role, nafs_level, capabilities, created_at, total_tasks, 
             success_rate, error_count, learning_iterations, config)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            profile.get("id"),
            profile.get("name"),
            profile.get("role"),
            profile.get("nafs_level", 1),
            json.dumps(profile.get("capabilities", [])),
            profile.get("created_at", datetime.utcnow().isoformat()),
            profile.get("total_tasks", 0),
            profile.get("success_rate", 0.0),
            profile.get("error_count", 0),
            profile.get("learning_iterations", 0),
            json.dumps(profile.get("config", {})),
        ))
        conn.commit()
        self._release_conn(conn)
    
    async def get_all_agents(self) -> List[Dict]:
        """Get all agent profiles"""
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM agent_profiles")
        rows = c.fetchall()
        self._release_conn(conn)
        
        agents = []
        for row in rows:
            agents.append({
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
            })
        return agents
    
    async def save_message(self, session_id: str, role: str, content: str, 
                            agent_id: str = "", metadata: Dict = None) -> str:
        """Save chat message"""
        import uuid
        msg_id = str(uuid.uuid4())
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO agent_messages (id, session_id, role, content, agent_id, created_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            msg_id, session_id, role, content, agent_id,
            datetime.utcnow().isoformat(),
            json.dumps(metadata or {})
        ))
        conn.commit()
        self._release_conn(conn)
        return msg_id
    
    async def get_messages(self, session_id: str, limit: int = 50) -> List[Dict]:
        """Get messages for a session"""
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("""
            SELECT id, session_id, role, content, agent_id, created_at, metadata
            FROM agent_messages WHERE session_id = ? ORDER BY created_at ASC LIMIT ?
        """, (session_id, limit))
        rows = c.fetchall()
        self._release_conn(conn)
        
        return [{
            "id": r[0], "session_id": r[1], "role": r[2],
            "content": r[3], "agent_id": r[4], "created_at": r[5],
            "metadata": json.loads(r[6]) if r[6] else {}
        } for r in rows]
    
    async def save_task(self, agent_id: str, task: str, result: str, 
                         success: bool, duration_ms: float, metadata: Dict = None) -> str:
        """Save task history"""
        import uuid
        task_id = str(uuid.uuid4())
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO task_history (id, agent_id, task, result, success, duration_ms, created_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            task_id, agent_id, task, result, int(success), duration_ms,
            datetime.utcnow().isoformat(), json.dumps(metadata or {})
        ))
        conn.commit()
        self._release_conn(conn)
        return task_id
    
    async def get_task_history(self, agent_id: str = None, limit: int = 100) -> List[Dict]:
        """Get task history"""
        conn = self._get_conn()
        c = conn.cursor()
        
        if agent_id:
            c.execute("SELECT * FROM task_history WHERE agent_id = ? ORDER BY created_at DESC LIMIT ?", 
                       (agent_id, limit))
        else:
            c.execute("SELECT * FROM task_history ORDER BY created_at DESC LIMIT ?", (limit,))
        
        rows = c.fetchall()
        self._release_conn(conn)
        
        return [{
            "id": r[0], "agent_id": r[1], "task": r[2], "result": r[3],
            "success": bool(r[4]), "duration_ms": r[5], "created_at": r[6],
            "metadata": json.loads(r[7]) if r[7] else {}
        } for r in rows]
    
    async def save_integration(self, integration: Dict) -> str:
        """Save integration config"""
        import uuid
        int_id = integration.get("id") or str(uuid.uuid4())
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("""
            INSERT OR REPLACE INTO integrations (id, name, type, config, enabled, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            int_id, integration.get("name"), integration.get("type"),
            json.dumps(integration.get("config", {})),
            int(integration.get("enabled", True)),
            datetime.utcnow().isoformat()
        ))
        conn.commit()
        self._release_conn(conn)
        return int_id
    
    async def get_integrations(self) -> List[Dict]:
        """Get all integrations"""
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM integrations")
        rows = c.fetchall()
        self._release_conn(conn)
        return [{
            "id": r[0], "name": r[1], "type": r[2],
            "config": json.loads(r[3]) if r[3] else {},
            "enabled": bool(r[4]), "created_at": r[5]
        } for r in rows]

    # ── QCA Lawh Memory Bridge ──────────────────────────────────────────

    def get_qca_lawh(self):
        """
        Get QCA's 4-tier Lawh memory instance.
        Bridges Dhikr's 3-tier (episodic/semantic/procedural) with
        QCA's 4-tier (Lawh immutable / Kitab verified / Dhikr active / Wahm conjecture).
        """
        try:
            from backend.qca.engine import LawhMemory
            return LawhMemory()
        except ImportError:
            return None

    async def remember_with_mizan(self, content: Any, memory_type: str = "episodic",
                                  importance: float = 0.5, agent_id: str = "",
                                  tags: List[str] = None,
                                  certainty_level: str = "zann") -> str:
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
            "yaqin": 1.0, "zann_rajih": 0.75, "zann": 0.5,
            "shakk": 0.25, "wahm": 0.05,
        }
        mizan_factor = mizan_weights.get(certainty_level, 0.5)
        adjusted_importance = min(1.0, importance * (0.5 + mizan_factor * 0.5))

        return await self.remember(
            content, memory_type, adjusted_importance, agent_id, tags
        )
