"""Tests for backend/memory/mem0_store.py — graceful degradation is the point.

Covers: disabled → no-op fallbacks, missing mem0ai package → clean fallback,
append-only API surface (no update/delete), RRF fusion ordering, token cap,
and failure isolation (exceptions never propagate).
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from memory import mem0_store
from memory.mem0_store import (
    Mem0Store,
    add_turn_async,
    enabled,
    get_store,
    recall_block_core,
    recall_block_sync,
    reset_store,
)


class FakeDhikrHit:
    def __init__(self, content):
        self.content = content


class FakeDhikr:
    def __init__(self, texts):
        self._texts = texts

    def recall_unified(self, query, top_k=10):
        return [FakeDhikrHit(t) for t in self._texts]


def _with_env(monkeypatch, **env):
    for k, v in env.items():
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, v)


def test_disabled_by_default(monkeypatch):
    _with_env(monkeypatch, MEM0_ENABLED=None)
    reset_store()
    try:
        assert enabled() is False
        assert get_store() is None
        assert recall_block_sync("s1", "hello") == ""
        assert asyncio.run(add_turn_async("s1", "hi", "hello")) is False
    finally:
        reset_store()


def test_enabled_but_mem0_not_installed(monkeypatch):
    """MEM0_ENABLED=true but mem0ai missing → store stays None, chat unaffected."""
    _with_env(monkeypatch, MEM0_ENABLED="true")
    reset_store()
    try:
        assert get_store() is None
        assert recall_block_sync("s1", "hello") == ""
        assert asyncio.run(add_turn_async("s1", "hi", "hello")) is False
    finally:
        reset_store()


def test_enabled_but_no_llm_key(monkeypatch):
    _with_env(
        monkeypatch,
        MEM0_ENABLED="true",
        ANTHROPIC_API_KEY=None,
        OPENROUTER_API_KEY=None,
        OPENAI_API_KEY=None,
    )
    reset_store()
    try:
        assert get_store() is None
    finally:
        reset_store()


def test_append_only_surface():
    """The wrapper exposes add only — no update/delete anywhere."""
    assert hasattr(Mem0Store, "add_memory")
    assert not hasattr(Mem0Store, "update_memory")
    assert not hasattr(Mem0Store, "delete_memory")
    assert not hasattr(Mem0Store, "update")
    assert not hasattr(Mem0Store, "delete")


def test_rrf_fusion_orders_by_combined_rank():
    fused = Mem0Store.rrf_fuse(
        [
            ["alpha shared", "beta mem0-only"],
            ["alpha shared", "gamma dhikr-only"],
        ]
    )
    # "alpha shared" ranks first in both lists → highest fused score.
    assert fused[0][0] == "alpha shared"
    labels = [t for t, _ in fused]
    assert "beta mem0-only" in labels and "gamma dhikr-only" in labels


def test_rrf_fusion_empty():
    assert Mem0Store.rrf_fuse([]) == []
    assert Mem0Store.rrf_fuse([[], []]) == []


def test_recall_block_core_fuses_and_caps():
    store = Mem0Store()
    store._memory = object()  # mark "ready" without real mem0
    store._mem0_search = lambda sid, q, k: [{"text": "mem0 says the user likes tea", "score": 0.9}]
    dhikr = FakeDhikr(["dhikr recalls user prefers green tea"])
    block = recall_block_core(store, "s1", "what tea?", dhikr=dhikr, top_k=5)
    assert "mem0 says the user likes tea" in block
    assert "green tea" in block
    # token budget: ≤800 tokens ≈ 3200 chars
    assert len(block) <= 3200 + 50


def test_recall_block_core_truncates_long_block():
    store = Mem0Store()
    store._memory = object()
    store._mem0_search = lambda sid, q, k: [{"text": "x" * 5000, "score": 1.0}]
    block = recall_block_core(store, "s1", "q", dhikr=None, top_k=5)
    assert len(block) <= 3200 + 50
    assert "truncated" in block


def test_recall_core_survives_dhikr_failure():
    class BrokenDhikr:
        def recall_unified(self, query, top_k=10):
            raise RuntimeError("db gone")

    store = Mem0Store()
    store._memory = object()
    store._mem0_search = lambda sid, q, k: [{"text": "mem0 fact", "score": 1.0}]
    block = recall_block_core(store, "s1", "q", dhikr=BrokenDhikr(), top_k=5)
    assert "mem0 fact" in block  # dhikr failure doesn't kill mem0 signal


def test_recall_core_survives_mem0_search_failure():
    store = Mem0Store()
    store._memory = object()

    def boom(sid, q, k):
        raise RuntimeError("vector store down")

    store._mem0_search = boom
    # sync helper catches and returns "" (via get_store? no — core raises;
    # recall() wraps it). Core itself raising is expected; the guard lives
    # in recall()/recall_block_sync().
    import pytest as _pytest

    with _pytest.raises(RuntimeError):
        recall_block_core(store, "s1", "q", dhikr=None)


def test_recall_block_sync_guards_everything(monkeypatch):
    """Even if the store raises, the sync helper returns ''."""
    _with_env(monkeypatch, MEM0_ENABLED="true")
    reset_store()

    class ExplodingStore(Mem0Store):
        @property
        def ready(self):
            return True

    monkeypatch.setattr(mem0_store, "_store", ExplodingStore())

    def boom_core(store, sid, q, dhikr=None, top_k=8):
        raise RuntimeError("total failure")

    monkeypatch.setattr(mem0_store, "recall_block_core", boom_core)
    try:
        assert recall_block_sync("s1", "hello", dhikr=None) == ""
    finally:
        reset_store()


def test_add_memory_never_breaks_chat():
    """add_memory on a broken client returns False, never raises."""
    store = Mem0Store()
    store._memory = None
    assert asyncio.run(store.add_memory("s", [{"role": "user", "content": "x"}])) is False


def test_empty_query_returns_empty():
    store = Mem0Store()
    assert asyncio.run(store.recall("s", "   ")) == ""
    assert asyncio.run(store.recall("s", "")) == ""
