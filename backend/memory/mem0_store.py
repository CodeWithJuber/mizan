"""mem0 long-term memory (OSS v3), env-gated with dhikr fallback.

Env:
  MEM0_ENABLED=true|false   (default false — zero behavior change when off)
  MEM0_DATA_DIR             (default: {MIZAN_DATA_DIR|data}/mem0)
  MEM0_LLM_MODEL            (default: app's DEFAULT_MODEL)
  MEM0_QDRANT_PATH          (default: {MEM0_DATA_DIR}/qdrant)
  MEM0_HISTORY_DB           (default: {MEM0_DATA_DIR}/history.db)

Design:
  - PyPI package ``mem0ai`` (verified: wheel ships top-level ``mem0``,
    ``from mem0 import Memory``), local Qdrant vector store + SQLite history.
  - LLM/embedder config reuses the app's existing provider env vars
    (ANTHROPIC_API_KEY / OPENROUTER_API_KEY / OPENAI_API_KEY) — never
    hardcoded, no new key required.
  - Writes are APPEND-ONLY: this module only ever calls ``mem0.add()``;
    no update/delete path exists anywhere in this code. (mem0 internally
    deduplicates during extraction — that is mem0's own pipeline, not a
    caller-initiated mutation.)
  - Recall fuses two signals via reciprocal rank fusion (RRF, k=60):
    mem0 semantic search + dhikr unified recall → compact block capped at
    ~800 tokens.
  - Everything is guarded: any mem0 failure logs and returns empty, so chat
    never breaks. When MEM0_ENABLED is false or mem0 is not installed,
    ``get_store()`` returns None and all helpers are no-ops.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("mizan.mem0")

MEM0_TOKEN_BUDGET = 800  # injected memory block cap (tokens)
_MEM0_CHAR_BUDGET = MEM0_TOKEN_BUDGET * 4


def enabled() -> bool:
    return os.getenv("MEM0_ENABLED", "false").lower() in ("1", "true", "yes")


def _data_dir() -> Path:
    base = Path(os.getenv("MIZAN_DATA_DIR", "data"))
    return Path(os.getenv("MEM0_DATA_DIR", str(base / "mem0")))


def _llm_config() -> dict[str, Any] | None:
    """Build a mem0 LLM config from the app's existing provider env.

    Returns None when no usable LLM key is configured (mem0 stays disabled).
    """
    default_model = os.getenv("MEM0_LLM_MODEL") or os.getenv(
        "DEFAULT_MODEL", "claude-sonnet-4-20250514"
    )
    if os.getenv("ANTHROPIC_API_KEY", "").startswith("sk-ant-"):
        return {
            "provider": "anthropic",
            "config": {"model": default_model, "temperature": 0.1, "max_tokens": 2000},
        }
    if os.getenv("OPENROUTER_API_KEY"):
        # OpenRouter is OpenAI-compatible; reuse the same key the chat layer uses.
        return {
            "provider": "openai",
            "config": {
                "model": default_model,
                "temperature": 0.1,
                "max_tokens": 2000,
                "openai_base_url": "https://openrouter.ai/api/v1",
            },
        }
    if os.getenv("OPENAI_API_KEY"):
        return {
            "provider": "openai",
            "config": {"model": default_model, "temperature": 0.1, "max_tokens": 2000},
        }
    return None


def _embedder_config() -> dict[str, Any] | None:
    """Embedder config reusing the same keys as the LLM config."""
    if os.getenv("OPENROUTER_API_KEY"):
        return {
            "provider": "openai",
            "config": {
                "model": "text-embedding-3-small",
                "embedding_dims": 1536,
                "openai_base_url": "https://openrouter.ai/api/v1",
            },
        }
    if os.getenv("OPENAI_API_KEY"):
        return {
            "provider": "openai",
            "config": {"model": "text-embedding-3-small", "embedding_dims": 1536},
        }
    return None


class Mem0Store:
    """Thin append-only wrapper around mem0 OSS v3 (``from mem0 import Memory``)."""

    def __init__(self) -> None:
        self._memory = None
        self._init_error: str | None = None

    # ── lifecycle ──────────────────────────────────────────────────────────

    def init(self) -> bool:
        """Initialise the mem0 client. Returns False (and stays disabled) when
        mem0 is not installed, disabled, or unconfigurable."""
        if not enabled():
            return False
        try:
            from mem0 import Memory  # noqa: PLC0415 - optional dependency
            from mem0.configs.base import MemoryConfig  # noqa: PLC0415
        except Exception as e:  # noqa: BLE001
            self._init_error = f"mem0ai not installed: {e}"
            logger.warning("mem0 disabled: %s", self._init_error)
            return False

        llm_cfg = _llm_config()
        emb_cfg = _embedder_config()
        if llm_cfg is None or emb_cfg is None:
            self._init_error = "no LLM/embedder key configured for mem0"
            logger.warning("mem0 disabled: %s", self._init_error)
            return False

        try:
            data_dir = _data_dir()
            data_dir.mkdir(parents=True, exist_ok=True)
            config = MemoryConfig(
                vector_store={
                    "provider": "qdrant",
                    "config": {
                        "collection_name": "mizan_mem0",
                        "path": os.getenv("MEM0_QDRANT_PATH", str(data_dir / "qdrant")),
                        "on_disk": True,
                    },
                },
                llm=llm_cfg,
                embedder=emb_cfg,
                history_db_path=os.getenv("MEM0_HISTORY_DB", str(data_dir / "history.db")),
            )
            self._memory = Memory(config)
            logger.info("mem0 initialised (local qdrant + sqlite history)")
            return True
        except Exception as e:  # noqa: BLE001
            self._init_error = str(e)[:300]
            logger.warning("mem0 init failed, falling back to dhikr: %s", e)
            self._memory = None
            return False

    @property
    def ready(self) -> bool:
        return self._memory is not None

    # ── append-only writes ─────────────────────────────────────────────────

    async def add_memory(self, session_id: str, messages: list[dict]) -> bool:
        """Add a turn to mem0. ADD-only — never updates or deletes."""
        if not self.ready:
            return False
        try:
            await asyncio.to_thread(
                self._memory.add,
                messages,
                user_id=f"session:{session_id}",
                infer=True,
            )
            return True
        except Exception as e:  # noqa: BLE001 - never break chat
            logger.warning("mem0 add failed: %s", e)
            return False

    # ── recall with multi-signal RRF fusion ────────────────────────────────

    def _mem0_search(self, session_id: str, query: str, top_k: int) -> list[dict]:
        """Raw mem0 search → [{'text', 'score'}]. Empty list on any failure."""
        if not self.ready:
            return []
        try:
            res = self._memory.search(
                query,
                top_k=top_k,
                filters={"user_id": f"session:{session_id}"},
            )
            out = []
            for item in res.get("results", []) if isinstance(res, dict) else []:
                text = item.get("memory") or item.get("text") or ""
                if text:
                    out.append({"text": str(text), "score": float(item.get("score", 0) or 0)})
            return out
        except Exception as e:  # noqa: BLE001
            logger.warning("mem0 search failed: %s", e)
            return []

    @staticmethod
    def rrf_fuse(ranked_lists: list[list[str]], k: int = 60) -> list[tuple[str, float]]:
        """Reciprocal rank fusion over multiple ranked text lists."""
        scores: dict[str, float] = {}
        for ranked in ranked_lists:
            for rank, text in enumerate(ranked, start=1):
                key = text.strip()
                if key:
                    scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
        return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)

    async def recall(self, session_id: str, query: str, top_k: int = 8, dhikr=None) -> str:
        """Recall relevant memories, fused from mem0 + dhikr via RRF.

        Returns a compact block (≤800 tokens) for context injection, or ""
        when mem0 is unavailable (caller falls back to dhikr alone).
        """
        if not query or not query.strip():
            return ""
        try:
            return await asyncio.to_thread(recall_block_core, self, session_id, query, dhikr, top_k)
        except Exception as e:  # noqa: BLE001 - never break chat
            logger.warning("mem0 recall failed: %s", e)
            return ""


_store: Mem0Store | None = None


def get_store() -> Mem0Store | None:
    """Return the process-wide mem0 store, or None when disabled/unavailable."""
    global _store
    if _store is None:
        candidate = Mem0Store()
        _store = candidate if candidate.init() else None
    return _store


def reset_store() -> None:
    """Test hook: drop the cached store."""
    global _store
    _store = None


# ── Chat-loop helpers (guarded, no-op when disabled) ─────────────────────────


def recall_block_core(
    store: Mem0Store, session_id: str, query: str, dhikr=None, top_k: int = 8
) -> str:
    """Sync recall core used by both the async and sync helpers."""
    mem0_hits = store._mem0_search(session_id, query, top_k)
    mem0_texts = [h["text"] for h in mem0_hits]

    dhikr_texts: list[str] = []
    if dhikr is not None:
        try:
            hits = dhikr.recall_unified(query, top_k=top_k)
            for h in hits:
                content = getattr(h, "content", None) or getattr(h, "memory", None)
                if content:
                    dhikr_texts.append(str(content))
        except Exception:  # noqa: BLE001 - dhikr failure ≠ chat failure
            logger.warning("dhikr recall failed during mem0 fusion", exc_info=True)

    fused = Mem0Store.rrf_fuse([mem0_texts, dhikr_texts])
    block = "\n".join(f"- {text}" for text, _ in fused[:top_k])
    if len(block) > _MEM0_CHAR_BUDGET:
        block = block[:_MEM0_CHAR_BUDGET].rsplit("\n", 1)[0] + "\n- …(truncated)"
    return block


def recall_block_sync(session_id: str, query: str, dhikr=None, top_k: int = 8) -> str:
    """Synchronous recall for the agent context-build path.

    Safe to call from sync code (including inside a running event loop);
    returns "" on any failure or when disabled.
    """
    store = get_store()
    if store is None or not store.ready or not query or not query.strip():
        return ""
    try:
        return recall_block_core(store, session_id, query, dhikr, top_k)
    except Exception as e:  # noqa: BLE001
        logger.warning("mem0 recall_block failed: %s", e)
        return ""


async def add_turn_async(session_id: str, user_msg: str, assistant_msg: str) -> bool:
    """Append one completed turn to mem0 (fire-and-forget safe)."""
    store = get_store()
    if store is None or not store.ready:
        return False
    messages = [
        {"role": "user", "content": user_msg},
        {"role": "assistant", "content": assistant_msg},
    ]
    return await store.add_memory(session_id, messages)
