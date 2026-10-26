"""Phase 4: Rūḥ gating, scheduled forgetting and the semantic memory layer."""

from datetime import UTC, datetime, timedelta

from memory.dhikr import DhikrMemorySystem
from memory.memory_pyramid import MemoryPyramid
from providers import create_provider, ruh_checkpoint_path


def test_ruh_provider_requires_the_enable_flag(monkeypatch, tmp_path):
    monkeypatch.setenv("RUH_MODEL_PATH", str(tmp_path))
    monkeypatch.delenv("RUH_ENABLED", raising=False)
    assert create_provider(provider="ruh", model="ruh-local") is None
    monkeypatch.setenv("RUH_ENABLED", "true")
    provider = create_provider(provider="ruh", model="ruh-local")
    assert provider is not None and provider.provider_name == "ruh"


def test_ruh_checkpoint_path_prefers_the_configured_path(monkeypatch, tmp_path):
    monkeypatch.setenv("RUH_MODEL_PATH", str(tmp_path / "ckpt"))
    assert ruh_checkpoint_path() == str(tmp_path / "ckpt")
    monkeypatch.delenv("RUH_MODEL_PATH")
    # Without a configured path only a complete conventional checkpoint counts.
    path = ruh_checkpoint_path()
    assert path == "" or path.endswith("checkpoints/latest")


async def test_consolidation_forgets_faded_but_keeps_remembered(tmp_path):
    memory = DhikrMemorySystem(str(tmp_path / "memory.db"))
    faded = await memory.remember("old unimportant note", importance=0.2)
    kept = await memory.remember("old but often recalled lesson", importance=0.6)
    fresh = await memory.remember("new note", importance=0.2)
    old = (datetime.now(UTC) - timedelta(days=60)).isoformat()
    conn = memory._get_conn()
    conn.execute("UPDATE memories SET recency = ?, access_count = 0 WHERE id = ?", (old, faded))
    conn.execute("UPDATE memories SET recency = ?, access_count = 40 WHERE id = ?", (old, kept))
    conn.commit()
    memory._release_conn(conn)

    result = await memory.consolidate()
    conn = memory._get_conn()
    remaining = {row[0] for row in conn.execute("SELECT id FROM memories").fetchall()}
    memory._release_conn(conn)
    assert result["records_pruned"] == 1
    assert faded not in remaining and kept in remaining and fresh in remaining


class FakeVectorStore:
    _available = True

    def __init__(self):
        self.calls = []

    async def search(self, query, limit=10, filters=None):
        self.calls.append((query, limit))
        return [{"content": "semantic neighbour about patience", "score": 0.9}]


async def test_pyramid_uses_the_async_vector_contract():
    store = FakeVectorStore()
    hits = await MemoryPyramid(vector_store=store).query_async("sabr", top_k=3)
    assert store.calls == [("sabr", 3)]
    assert hits[0].source_layer == "vector"


def test_vector_layer_stays_off_without_configuration(tmp_path, monkeypatch):
    monkeypatch.delenv("MIZAN_VECTOR_URL", raising=False)
    memory = DhikrMemorySystem(str(tmp_path / "memory.db"))
    assert memory.vector_store is None
