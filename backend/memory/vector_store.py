"""
Vector Store (Luh Mahfuz Enhancement - لَوْح مَحْفُوظ)
=========================================================

"Nay, it is a Glorious Quran, inscribed in a Preserved Tablet (Luh Mahfuz)" — Quran 85:21-22

Semantic memory using ChromaDB vector embeddings.
Enables meaning-based retrieval rather than keyword matching.
"""

import logging
import uuid
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger("mizan.vector")


class VectorStore:
    """
    Semantic memory layer using ChromaDB.
    Falls back gracefully if ChromaDB is not available.
    """

    def __init__(self, chroma_url: str = "http://localhost:8100",
                 collection_name: str = "mizan_dhikr"):
        self.chroma_url = chroma_url
        self.collection_name = collection_name
        self._client = None
        self._collection = None
        self._available = False
        self._init_client()

    def _init_client(self):
        """Initialize ChromaDB client"""
        try:
            import chromadb
            self._client = chromadb.HttpClient(
                host=self.chroma_url.replace("http://", "").split(":")[0],
                port=int(self.chroma_url.split(":")[-1]) if ":" in self.chroma_url.split("//")[-1] else 8100,
            )
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"description": "MIZAN Dhikr Memory Vectors"},
            )
            self._available = True
            logger.info("[VECTOR] ChromaDB connected")
        except ImportError:
            logger.warning("[VECTOR] chromadb not installed, vector search disabled")
        except Exception as e:
            logger.warning(f"[VECTOR] ChromaDB not available: {e}")

    @property
    def is_available(self) -> bool:
        return self._available

    async def store(self, content: str, memory_id: str = None,
                    metadata: Dict = None) -> Optional[str]:
        """Store content with auto-generated embedding"""
        if not self._available:
            return None

        mem_id = memory_id or str(uuid.uuid4())

        try:
            self._collection.add(
                documents=[content],
                ids=[mem_id],
                metadatas=[metadata or {}],
            )
            return mem_id
        except Exception as e:
            logger.error(f"[VECTOR] Store failed: {e}")
            return None

    async def search(self, query: str, limit: int = 10,
                     filters: Dict = None) -> List[Dict]:
        """Semantic similarity search"""
        if not self._available:
            return []

        try:
            where = filters if filters else None
            results = self._collection.query(
                query_texts=[query],
                n_results=limit,
                where=where,
            )

            items = []
            if results and results.get("documents"):
                for i, doc in enumerate(results["documents"][0]):
                    items.append({
                        "id": results["ids"][0][i],
                        "content": doc,
                        "distance": results["distances"][0][i] if results.get("distances") else None,
                        "metadata": results["metadatas"][0][i] if results.get("metadatas") else {},
                    })

            return items
        except Exception as e:
            logger.error(f"[VECTOR] Search failed: {e}")
            return []

    async def delete(self, memory_id: str):
        """Delete a vector by ID"""
        if not self._available:
            return

        try:
            self._collection.delete(ids=[memory_id])
        except Exception as e:
            logger.error(f"[VECTOR] Delete failed: {e}")

    async def count(self) -> int:
        """Get total number of vectors"""
        if not self._available:
            return 0
        try:
            return self._collection.count()
        except Exception:
            return 0
