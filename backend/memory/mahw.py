"""Mahw (محو): forgetting for real, with a receipt.

When a user deletes a chat or forgets a note, Mahw removes it from every place
MIZAN keeps it and from what was derived from it: the chat's messages and
summary, the task records, wisdom, knowledge-graph entries, learned wording and
programs built from its requests, learner rows, debug runs, held actions, the
chat's plan file, and the vectors of erased notes. The pathway network (Masalik)
cannot have one experience subtracted, since Hebbian updates do not reverse, so
it is rebuilt from what is kept.

Then Mahw checks its own work. It cuts each erased text into 20-character
pieces and looks for them in every store it can read. A piece that also appears
in text the user kept (the same words said in another chat) explains itself;
any other match counts as a trace. The receipt records what was removed from
each store, how many checks ran and how many traces were found. It keeps none
of the erased content and no hashes of it.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import sqlite3
import tempfile
import uuid
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("mizan.mahw")

# A 20-character run of someone's words almost never recurs by chance, so a
# match means a copy survived.
PIECE = 20
MAX_PROBES = 400

_LOCKS: dict[str, asyncio.Lock] = {}


def _lock(owner: str) -> asyncio.Lock:
    return _LOCKS.setdefault(owner, asyncio.Lock())


def _data_dir() -> Path:
    return Path(os.getenv("MIZAN_DATA_DIR", "/data/mizan"))


def private_dir(owner: str) -> Path:
    return _data_dir() / "private" / hashlib.sha256(owner.encode()).hexdigest()


# ── small SQLite helpers that tolerate a store that was never created ─────


def _connect(path: str | Path) -> sqlite3.Connection | None:
    if not path or not Path(path).exists():
        return None
    return sqlite3.connect(str(path), timeout=10)


def _run(path: str | Path, sql: str, params: Sequence[Any] = ()) -> int:
    conn = _connect(path)
    if conn is None:
        return 0
    try:
        cursor = conn.execute(sql, tuple(params))
        conn.commit()
        return max(0, int(cursor.rowcount))
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc) or "no such column" in str(exc):
            return 0
        raise
    finally:
        conn.close()


def _select(path: str | Path, sql: str, params: Sequence[Any] = ()) -> list[tuple]:
    conn = _connect(path)
    if conn is None:
        return []
    try:
        return conn.execute(sql, tuple(params)).fetchall()
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc) or "no such column" in str(exc):
            return []
        raise
    finally:
        conn.close()


def _marks(values: Sequence[Any]) -> str:
    return ",".join("?" for _ in values)


def _in_batches(values: Sequence[Any], size: int = 400) -> Iterable[Sequence[Any]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def _delete_in(
    path: str | Path,
    table: str,
    column: str,
    values: Sequence[Any],
    extra: str = "",
    extra_params: Sequence[Any] = (),
) -> int:
    """DELETE FROM table WHERE column IN values [AND extra]; names are fixed by callers."""
    removed = 0
    for batch in _in_batches(list(values)):
        if not batch:
            continue
        sql = f"DELETE FROM {table} WHERE {column} IN ({_marks(batch)}){extra}"  # noqa: S608
        removed += _run(path, sql, (*batch, *extra_params))
    return removed


# ── what was derived from the erased words ───────────────────────────────


def _forget_learned(adaptive: Any, owner: str, texts: Sequence[str], chat: str = "") -> int:
    """Drop learned wording (Qasd, Ta'allum), kept programs (Hifz), what
    sources settled (Ahl al-Dhikr) and repair lessons (Tajriba) that came from
    these requests or this chat; the rest of what was learned stays."""
    if adaptive is None or not (texts or chat):
        return 0
    from tadbir import ahl_dhikr, hifz, qasd, taallum, tajriba

    removed = 0
    try:
        removed += tajriba.unlearn(adaptive, owner, chat, list(texts))
    except Exception:  # noqa: BLE001 - no lessons yet
        logger.debug("[MAHW] no repair lessons to drop")
    if not texts:
        return removed

    words = [taallum.content_words(text) for text in texts]
    for module in (hifz, taallum, ahl_dhikr):
        try:
            items = module._load(adaptive, owner)
        except Exception:  # noqa: BLE001 - nothing learned yet
            continue
        kept = [item for item in items if item.get("tokens") not in words]
        if len(kept) != len(items):
            removed += len(items) - len(kept)
            module._save(adaptive, owner, kept)
    try:
        removed += qasd.unlearn(adaptive, owner, texts)
    except Exception:  # noqa: BLE001
        logger.debug("[MAHW] no learned intents to drop")
    return removed


def _rebuild_masalik(store: Any) -> int:
    """Rebuild the pathway network from the memories and task records kept.

    Returns how many experiences were encoded. Built on a fresh network and
    swapped in whole, so a concurrent reader never sees half a graph.
    """
    network = getattr(store, "masalik", None)
    if network is None:
        return 0
    from memory.masalik import MasalikNetwork

    rows = _select(store.db_path, "SELECT content, tags, importance FROM memories")
    tasks = _select(store.db_path, "SELECT task, result, success FROM task_history")
    # A path that does not exist: the fresh network starts from its innate
    # pathways and is never saved there.
    fresh = MasalikNetwork(
        persist_path=str(Path(tempfile.gettempdir()) / f"mahw-{uuid.uuid4().hex}.json")
    )
    fresh._save_every_n = 1 << 30
    count = 0
    for content, tags, importance in rows:
        text = str(content or "")
        try:
            extra = " ".join(json.loads(tags)) if tags else ""
        except (TypeError, ValueError):
            extra = ""
        fresh.encode(f"{text} {extra}".strip(), importance=float(importance or 0.5))
        count += 1
    for task, result, success in tasks:
        outcome = "response" if success else "error"
        fresh.encode(
            f"{task} {outcome} {str(result or '')[:500]}", importance=0.7 if success else 0.3
        )
        count += 1
    network._invalidate_stats_cache()
    network.concepts, network.pathways = fresh.concepts, fresh.pathways
    network._activation_history = fresh._activation_history
    network._invalidate_stats_cache()
    network.save_to_disk()
    return count


async def _drop_vectors(store: Any, ids: Sequence[str]) -> tuple[int, int]:
    """Delete erased notes' vectors; returns (deleted, still found)."""
    vectors = getattr(store, "vector_store", None)
    if vectors is None or not ids:
        return 0, 0
    for memory_id in ids:
        await vectors.delete(memory_id)
    left = 0
    collection = getattr(vectors, "_collection", None)
    if collection is not None:
        try:
            found = await asyncio.to_thread(collection.get, ids=list(ids))
            left = len(found.get("ids") or [])
        except Exception:  # noqa: BLE001 - an unreachable vector store is reported, not hidden
            left = -1
    return len(ids), left


def _drop_cached(store: Any, ids: Iterable[str]) -> None:
    for memory_id in ids:
        for kind in ("episodic", "semantic", "procedural"):
            try:
                store._get_cache(kind).pop(memory_id, None)
            except Exception:  # noqa: BLE001
                pass
        getattr(store, "working_memory", {}).pop(memory_id, None)


# ── checking that nothing is left ────────────────────────────────────────


def _normal(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def pieces(texts: Sequence[str], limit: int = MAX_PROBES) -> list[str]:
    """Non-overlapping 20-character pieces of the erased texts, spread evenly."""
    found: list[str] = []
    for text in texts:
        flat = _normal(text)
        found.extend(
            flat[start : start + PIECE] for start in range(0, len(flat) - PIECE + 1, PIECE)
        )
    unique = list(dict.fromkeys(piece for piece in found if piece.strip()))
    if len(unique) <= limit:
        return unique
    step = len(unique) / limit
    return [unique[int(index * step)] for index in range(limit)]


def _probe(
    places: Sequence[tuple[str, str, str, tuple]], probes: Sequence[str], kept: str
) -> tuple[int, int, dict[str, int]]:
    """(checks, traces, traces per store) for each piece in each place.

    A place is (name, db, sql, params): ``sql`` counts the rows that contain
    the piece (``instr``, a literal match) and takes the piece for each ``?``
    before ``params``. A piece also present in the kept text explains itself.
    """
    checks, traces = 0, 0
    per_store: dict[str, int] = {}
    unexplained = [piece for piece in probes if piece not in kept]
    for name, path, sql, params in places:
        if _connect(path) is None:
            continue
        slots = sql.count("?") - len(params)
        for piece in unexplained:
            rows = _select(path, sql, (*(piece,) * slots, *params))
            hits = int(rows[0][0]) if rows else 0
            if hits:
                per_store[name] = per_store.get(name, 0) + hits
                traces += hits
        checks += len(probes)
    return checks, traces, per_store


# ── receipts ─────────────────────────────────────────────────────────────


def _receipts_path() -> Path:
    return _data_dir() / "mahw.db"


def _save_receipt(receipt: dict) -> None:
    path = _receipts_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(path), timeout=10) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS receipts (id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, "
            "kind TEXT NOT NULL, created TEXT NOT NULL, data TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO receipts VALUES (?,?,?,?,?)",
            (
                receipt["id"],
                receipt["owner_id"],
                receipt["kind"],
                receipt["created"],
                json.dumps(receipt),
            ),
        )


def receipts(owner: str, limit: int = 50) -> list[dict]:
    rows = _select(
        _receipts_path(),
        "SELECT data FROM receipts WHERE owner_id=? ORDER BY created DESC LIMIT ?",
        (owner, max(1, min(limit, 200))),
    )
    return [json.loads(row[0]) for row in rows]


def _receipt(
    owner: str,
    kind: str,
    scope: str,
    removed: dict[str, int],
    checks: int,
    traces: int,
    where: dict[str, int],
    kept: list[str],
    outside: list[str],
    vectors_left: int,
) -> dict:
    receipt = {
        "id": uuid.uuid4().hex,
        "owner_id": owner,
        "kind": kind,
        "scope": scope,
        "created": datetime.now(UTC).isoformat(),
        "removed": {name: count for name, count in removed.items() if count},
        "checked": checks,
        "traces": traces + max(0, vectors_left),
        "traces_by_store": {**where, **({"vectors": vectors_left} if vectors_left else {})},
        "vector_check": "unavailable" if vectors_left < 0 else "done",
        "kept": kept,
        "outside": outside,
    }
    _save_receipt(receipt)
    return receipt


# ── erasing ──────────────────────────────────────────────────────────────


def _owner_places(
    chat_db: str, private: str, learner: str, debug: str, owner: str, session_id: str = ""
) -> list[tuple[str, str, str, tuple]]:
    """Where a piece of the user's words could survive: (name, db, count query, params)."""
    mine = "(session_id = ? OR session_id IN (SELECT session_id FROM chat_sessions WHERE owner_id = ?))"
    return [
        (
            "chat messages",
            chat_db,
            f"SELECT COUNT(*) FROM agent_messages WHERE instr(content, ?) > 0 AND {mine}",  # noqa: S608
            (session_id, owner),
        ),
        (
            "chat summaries",
            chat_db,
            f"SELECT COUNT(*) FROM session_summaries WHERE instr(summary, ?) > 0 AND {mine}",  # noqa: S608
            (session_id, owner),
        ),
        ("notes", private, "SELECT COUNT(*) FROM memories WHERE instr(content, ?) > 0", ()),
        (
            "task records",
            private,
            "SELECT COUNT(*) FROM task_history WHERE instr(task, ?) > 0 OR instr(result, ?) > 0",
            (),
        ),
        ("wisdom", private, "SELECT COUNT(*) FROM hikmah WHERE instr(context, ?) > 0", ()),
        (
            "knowledge graph",
            private,
            "SELECT COUNT(*) FROM kg_entities WHERE instr(name, ?) > 0",
            (),
        ),
        (
            "learner",
            learner,
            "SELECT COUNT(*) FROM interactions WHERE instr(prompt, ?) > 0 OR instr(response, ?) > 0",
            (),
        ),
        ("debug runs", debug, "SELECT COUNT(*) FROM debug_runs WHERE instr(prompt, ?) > 0", ()),
    ]


def _kept_text(chat_db: str, owner: str) -> str:
    """The words the user still has in their other chats: a piece found there
    was said again, not left behind. Copies in notes or other stores are
    reported as traces, so the user can forget them too."""
    rows = _select(
        chat_db,
        "SELECT m.content FROM agent_messages m JOIN chat_sessions s ON s.session_id = m.session_id "
        "WHERE s.owner_id = ?",
        (owner,),
    )
    return "\n".join(_normal(str(row[0] or "")) for row in rows)


async def erase_chat(
    *,
    chat_db: str,
    artifacts_db: str,
    private: Any,
    owner: str,
    session_id: str,
    held_db: str | None = None,
) -> dict:
    """Erase one chat and everything derived from it; returns the receipt."""
    async with _lock(owner):
        parts = await asyncio.to_thread(
            _erase_chat_rows, chat_db, artifacts_db, private, owner, session_id, held_db
        )
        deleted, left = await _drop_vectors(private, parts["note_ids"])
        parts["removed"]["vectors"] = deleted
        return await asyncio.to_thread(_finish_chat, private, owner, session_id, parts, left)


def _image_shas(metadata_rows: Any) -> set[str]:
    found: set[str] = set()
    for raw in metadata_rows:
        try:
            metadata = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except ValueError:
            continue
        if not isinstance(metadata, dict):
            continue
        for item in metadata.get("images") or []:
            if isinstance(item, dict) and item.get("sha"):
                found.add(str(item["sha"]))
    return found


def _erase_chat_rows(
    chat_db: str, artifacts_db: str, private: Any, owner: str, session_id: str, held_db: str | None
) -> dict:
    messages = _select(
        chat_db,
        "SELECT id, role, content, metadata FROM agent_messages WHERE session_id = ?",
        (session_id,),
    )
    ids = [row[0] for row in messages]
    images = _image_shas(row[3] for row in messages)
    asked = [str(row[2] or "") for row in messages if row[1] == "user" and row[2]]
    texts = [str(row[2] or "") for row in messages if row[2]]
    summary = _select(
        chat_db, "SELECT summary FROM session_summaries WHERE session_id = ?", (session_id,)
    )
    texts += [str(row[0] or "") for row in summary]
    removed: dict[str, int] = {}
    removed["muhasaba reviews"] = _delete_in(chat_db, "muhasaba_reviews", "message_id", ids)
    removed["chat messages"] = _run(
        chat_db, "DELETE FROM agent_messages WHERE session_id = ?", (session_id,)
    )
    # Images attached in this chat (Basar), unless another of the owner's chats
    # still shows the same picture.
    shown_elsewhere = _image_shas(
        row[0]
        for row in _select(
            chat_db,
            "SELECT m.metadata FROM agent_messages m JOIN chat_sessions s "
            "ON s.session_id = m.session_id WHERE s.owner_id = ? AND m.metadata LIKE '%\"images\"%'",
            (owner,),
        )
    )
    from perception import basar

    removed["images"] = basar.erase(owner, [sha for sha in images if sha not in shown_elsewhere])
    removed["chat summary"] = _run(
        chat_db, "DELETE FROM session_summaries WHERE session_id = ?", (session_id,)
    )
    removed["request receipts"] = _run(
        chat_db,
        "DELETE FROM chat_stream_requests WHERE owner_id = ? AND session_id = ?",
        (owner, session_id),
    )
    unlinked = _run(
        chat_db,
        "UPDATE chat_preferences SET session_id = '' WHERE owner_id = ? AND session_id = ?",
        (owner, session_id),
    )
    artifacts = [
        row[0]
        for row in _select(
            artifacts_db,
            "SELECT id FROM artifacts WHERE user_id = ? AND session_id = ?",
            (owner, session_id),
        )
    ]
    removed["artifact versions"] = _delete_in(
        artifacts_db, "artifact_versions", "artifact_id", artifacts
    )
    removed["artifacts"] = _delete_in(artifacts_db, "artifacts", "id", artifacts)
    if held_db:
        removed["held actions"] = _run(
            held_db, "DELETE FROM held WHERE owner_id = ? AND session_id = ?", (owner, session_id)
        )
        # What the person allowed "always" in this chat (security/approvals.ChatAlways).
        removed["always allowed"] = _run(
            held_db,
            "DELETE FROM chat_always WHERE owner_id = ? AND session_id = ?",
            (owner, session_id),
        )
    removed["chat"] = _run(
        chat_db,
        "DELETE FROM chat_sessions WHERE session_id = ? AND owner_id = ?",
        (session_id, owner),
    )
    from agents import session_state

    plan = session_state._path(owner, session_id)
    if plan.exists():
        plan.unlink()
        removed["chat plan"] = 1

    # What MIZAN derived from the chat, in the user's own stores.
    db = private.db_path
    note_ids = [
        row[0]
        for row in _select(
            db, "SELECT id FROM memories WHERE source LIKE ?", (f"chat:{session_id}%",)
        )
    ]
    texts += [
        str(row[0] or "")
        for row in _select(
            db, "SELECT content FROM memories WHERE source LIKE ?", (f"chat:{session_id}%",)
        )
    ]
    removed["notes"] = _delete_in(db, "memories", "id", note_ids)
    _drop_cached(private, note_ids)
    removed["task records"] = _delete_in(db, "task_history", "task", asked) + _run(
        db,
        "DELETE FROM task_history WHERE json_valid(metadata) "
        "AND json_extract(metadata, '$.session') = ?",
        (session_id,),
    )
    removed["wisdom"] = _delete_in(db, "hikmah", "context", [text[:200] for text in asked])
    names = list(dict.fromkeys(text[:100] for text in asked))
    entities = [
        row[0]
        for batch in _in_batches(names)
        for row in _select(
            db,
            f"SELECT id FROM kg_entities WHERE type = 'task' AND name IN ({_marks(batch)})",  # noqa: S608
            batch,
        )
    ]
    removed["knowledge links"] = _delete_in(
        db, "kg_relationships", "source_id", entities
    ) + _delete_in(db, "kg_relationships", "target_id", entities)
    removed["knowledge graph"] = _delete_in(db, "kg_entities", "id", entities)
    removed["learned from requests"] = _forget_learned(_adaptive(db), owner, asked, session_id)
    # What the live learning record and the instruction harness noted from this chat.
    from tadbir import sijill, tajdid

    removed["learning notes"] = sijill.forget_chat(owner, session_id)
    try:
        removed["instruction failure notes"] = tajdid.forget_chat(session_id)
    except Exception:  # noqa: BLE001 - the harness store may be absent
        removed["instruction failure notes"] = 0
    folder = private_dir(owner)
    learner = folder / "learner.sqlite3"
    rows = _select(
        learner,
        "SELECT id FROM interactions WHERE json_extract(metadata, '$.session_id') = ?",
        (session_id,),
    )
    interactions = [row[0] for row in rows]
    removed["learner reviews"] = _delete_in(
        learner, "interaction_reviews", "interaction_id", interactions
    )
    removed["learner examples"] = _delete_in(learner, "interactions", "id", interactions)
    removed["debug runs"] = _delete_in(folder / "debug_runs.db", "debug_runs", "prompt", asked)
    kept = [
        "Action receipts (Sakk) stay: which tool ran and how it ended, with keyed "
        "digests only; no words from this chat are in them"
    ]
    if unlinked:
        kept.append(
            f"{unlinked} preference(s) you set in this chat stay in your Daftar "
            "(forget them there); they no longer point to this chat"
        )
    return {
        "removed": removed,
        "texts": texts,
        "note_ids": note_ids,
        "kept": kept,
        "chat_db": chat_db,
        "learner": str(learner),
        "debug": str(folder / "debug_runs.db"),
    }


def _adaptive(db_path: str) -> Any:
    from core.adaptive import AdaptiveStateStore

    return AdaptiveStateStore(db_path)


def _finish_chat(private: Any, owner: str, session_id: str, parts: dict, vectors_left: int) -> dict:
    removed = parts["removed"]
    removed["pathways rebuilt from kept memories"] = (
        _rebuild_masalik(private)
        if any(removed.get(name) for name in ("notes", "task records", "chat messages"))
        else 0
    )
    kept_text = _kept_text(parts["chat_db"], owner)
    places = _owner_places(
        parts["chat_db"], private.db_path, parts["learner"], parts["debug"], owner, session_id
    )
    checks, traces, where = _probe(places, pieces(parts["texts"]), kept_text)
    return _receipt(
        owner,
        "chat",
        hashlib.sha256(session_id.encode()).hexdigest()[:16],
        removed,
        checks,
        traces,
        where,
        parts["kept"],
        _outside(),
        vectors_left,
    )


def _outside() -> list[str]:
    """Copies MIZAN cannot reach: what left the server."""
    return [
        "Text already sent to the model provider for an answer is held under that "
        "provider's own retention policy",
    ]


async def erase_notes(
    *, private: Any, owner: str, note_ids: Sequence[str], chat_db: str = ""
) -> dict:
    """Forget notes everywhere they live (row, caches, vectors, pathways); returns the receipt."""
    async with _lock(owner):
        db = private.db_path
        ids = list(note_ids)[:500]
        query = f"SELECT content FROM memories WHERE id IN ({_marks(ids)})"  # noqa: S608
        texts = [str(row[0] or "") for row in _select(db, query, ids)] if ids else []
        removed = {"notes": await asyncio.to_thread(_delete_in, db, "memories", "id", ids)}
        _drop_cached(private, ids)
        deleted, left = await _drop_vectors(private, ids)
        removed["vectors"] = deleted
        removed["pathways rebuilt from kept memories"] = (
            await asyncio.to_thread(_rebuild_masalik, private) if removed["notes"] else 0
        )
        folder = private_dir(owner)

        def check() -> tuple[int, int, dict[str, int]]:
            kept = _kept_text(chat_db, owner) if chat_db else ""
            places = [
                place
                for place in _owner_places(
                    chat_db,
                    db,
                    str(folder / "learner.sqlite3"),
                    str(folder / "debug_runs.db"),
                    owner,
                )
                if place[0] == "notes"
            ]
            return _probe(places, pieces(texts), kept)

        checks, traces, where = await asyncio.to_thread(check)
        return await asyncio.to_thread(
            _receipt,
            owner,
            "notes",
            f"{removed['notes']} note(s)",
            removed,
            checks,
            traces,
            where,
            [],
            [],
            left,
        )
