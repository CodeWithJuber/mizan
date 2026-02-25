"""
Knowledge Graph (Ilm - عِلْم — Knowledge)
============================================

"And He taught Adam the names of all things" — Quran 2:31

Stores entities and relationships extracted from agent interactions.
Enables graph-based reasoning and "what do I know about X?" queries.
"""

import json
import uuid
import logging
import sqlite3
from typing import Dict, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger("mizan.knowledge")


class KnowledgeGraph:
    """
    Simple knowledge graph backed by SQLite.
    Stores entities and their relationships.
    """

    def __init__(self, db_path: str = "/tmp/mizan_memory.db"):
        self.db_path = db_path
        self._init_tables()

    def _init_tables(self):
        """Create knowledge graph tables"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute("""
            CREATE TABLE IF NOT EXISTS kg_entities (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT DEFAULT 'concept',
                properties TEXT DEFAULT '{}',
                created_at TEXT,
                updated_at TEXT
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS kg_relationships (
                id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                type TEXT NOT NULL,
                properties TEXT DEFAULT '{}',
                confidence REAL DEFAULT 0.5,
                created_at TEXT,
                FOREIGN KEY (source_id) REFERENCES kg_entities(id),
                FOREIGN KEY (target_id) REFERENCES kg_entities(id)
            )
        """)

        c.execute("CREATE INDEX IF NOT EXISTS idx_entity_name ON kg_entities(name)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_rel_source ON kg_relationships(source_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_rel_target ON kg_relationships(target_id)")

        conn.commit()
        conn.close()

    async def add_entity(self, name: str, entity_type: str = "concept",
                         properties: Dict = None) -> str:
        """Add or update an entity"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        # Check if entity exists
        c.execute("SELECT id FROM kg_entities WHERE name = ? AND type = ?", (name, entity_type))
        row = c.fetchone()

        now = datetime.utcnow().isoformat()
        if row:
            entity_id = row[0]
            c.execute(
                "UPDATE kg_entities SET properties = ?, updated_at = ? WHERE id = ?",
                (json.dumps(properties or {}), now, entity_id),
            )
        else:
            entity_id = str(uuid.uuid4())
            c.execute(
                "INSERT INTO kg_entities (id, name, type, properties, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (entity_id, name, entity_type, json.dumps(properties or {}), now, now),
            )

        conn.commit()
        conn.close()
        return entity_id

    async def add_relationship(self, source_name: str, target_name: str,
                                rel_type: str, confidence: float = 0.5,
                                properties: Dict = None) -> str:
        """Add a relationship between two entities (creating them if needed)"""
        source_id = await self.add_entity(source_name)
        target_id = await self.add_entity(target_name)

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        rel_id = str(uuid.uuid4())
        c.execute(
            """INSERT INTO kg_relationships
            (id, source_id, target_id, type, properties, confidence, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (rel_id, source_id, target_id, rel_type,
             json.dumps(properties or {}), confidence,
             datetime.utcnow().isoformat()),
        )

        conn.commit()
        conn.close()
        return rel_id

    async def query_entity(self, name: str) -> Dict:
        """Get everything known about an entity"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        # Find entity
        c.execute("SELECT * FROM kg_entities WHERE name LIKE ?", (f"%{name}%",))
        entities = c.fetchall()

        if not entities:
            conn.close()
            return {"entity": name, "found": False, "relationships": []}

        entity = entities[0]
        entity_id = entity[0]

        # Find relationships
        c.execute("""
            SELECT r.type, e.name, r.confidence, r.properties
            FROM kg_relationships r
            JOIN kg_entities e ON r.target_id = e.id
            WHERE r.source_id = ?
        """, (entity_id,))
        outgoing = [
            {"relation": r[0], "target": r[1], "confidence": r[2]}
            for r in c.fetchall()
        ]

        c.execute("""
            SELECT r.type, e.name, r.confidence, r.properties
            FROM kg_relationships r
            JOIN kg_entities e ON r.source_id = e.id
            WHERE r.target_id = ?
        """, (entity_id,))
        incoming = [
            {"relation": r[0], "source": r[1], "confidence": r[2]}
            for r in c.fetchall()
        ]

        conn.close()

        return {
            "entity": entity[1],
            "type": entity[2],
            "properties": json.loads(entity[3]) if entity[3] else {},
            "found": True,
            "outgoing": outgoing,
            "incoming": incoming,
        }

    async def get_stats(self) -> Dict:
        """Get knowledge graph statistics"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute("SELECT COUNT(*) FROM kg_entities")
        entities = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM kg_relationships")
        relationships = c.fetchone()[0]

        conn.close()

        return {
            "entities": entities,
            "relationships": relationships,
        }
