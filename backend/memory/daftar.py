"""Daftar (دفتر): the ledger of everything MIZAN keeps about a user, which the user can read, correct and take away.

One list, four kinds:

- **note**: something saved to remember (by the user, an import, or a knowledge source)
- **preference**: how the user wants MIZAN to answer (name, language, tone, ...)
- **summary**: MIZAN's running summary of a long chat
- **learned**: wording, programs and repair lessons MIZAN learned from the user's verified work

Each entry says where it came from, when it was made and last used, and (for
notes) when it expires. Notes and preferences can be edited and forgotten one
by one, or by topic after a preview. The whole ledger exports as Markdown (to
read) and JSON (to import into another MIZAN).
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from core.adaptive import bm25_scores, tokenize

FORMAT = "mizan-daftar/1"
MAX_IMPORT = 500


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _rows(store: Any, sql: str, params: tuple = ()) -> list[tuple]:
    conn = store._get_conn()
    try:
        rows: list[tuple] = conn.execute(sql, params).fetchall()
        return rows
    finally:
        store._release_conn(conn)


def _write(store: Any, sql: str, params: tuple = ()) -> int:
    conn = store._get_conn()
    try:
        cursor = conn.execute(sql, params)
        conn.commit()
        return int(cursor.rowcount)
    finally:
        store._release_conn(conn)


def purge_expired(store: Any) -> int:
    """Forget notes whose expiry has passed."""
    return _write(
        store,
        "DELETE FROM memories WHERE expires IS NOT NULL AND expires != '' AND expires <= ?",
        (_now(),),
    )


def _source(raw: str, titles: dict[str, str]) -> dict:
    """Where an entry came from, in words the user can follow."""
    raw = raw or ""
    if raw.startswith("chat:"):
        session = raw[5:]
        return {"kind": "chat", "session_id": session, "label": titles.get(session) or "a chat"}
    if raw.startswith("knowledge:"):
        return {"kind": "knowledge", "label": raw[10:] or "a knowledge source"}
    if raw == "import":
        return {"kind": "import", "label": "imported"}
    if raw == "manual":
        return {"kind": "manual", "label": "you added it"}
    return {"kind": "unknown", "label": "saved before MIZAN kept provenance"}


def notes(store: Any, titles: dict[str, str]) -> list[dict]:
    purge_expired(store)
    rows = _rows(
        store,
        "SELECT id, content, memory_type, importance, recency, access_count, tags, "
        "source, created, last_used, expires FROM memories ORDER BY recency DESC LIMIT 1000",
    )
    entries = []
    for row in rows:
        try:
            content = json.loads(row[1]) if row[1] and row[1][:1] in '[{"' else row[1]
        except ValueError:
            content = row[1]
        entries.append(
            {
                "id": f"note:{row[0]}",
                "kind": "note",
                "content": content if isinstance(content, str) else json.dumps(content),
                "type": row[2],
                "importance": round(float(row[3] or 0), 2),
                "tags": json.loads(row[6]) if row[6] else [],
                "source": _source(row[7], titles),
                "created": row[8] or row[4] or "",
                "last_used": row[9] or "",
                "uses": int(row[5] or 0),
                "expires": row[10] or "",
                "editable": True,
            }
        )
    return entries


async def preferences(memory: Any, owner_id: str, titles: dict[str, str]) -> list[dict]:
    rows = _rows(
        memory,
        "SELECT key, value, updated_at, session_id FROM chat_preferences WHERE owner_id = ? "
        "ORDER BY key",
        (owner_id,),
    )
    return [
        {
            "id": f"preference:{row[0]}",
            "kind": "preference",
            "key": row[0],
            "content": row[1],
            "source": _source(f"chat:{row[3]}" if row[3] else "manual", titles),
            "created": row[2],
            "last_used": "",
            "expires": "",
            "editable": True,
        }
        for row in rows
    ]


async def summaries(memory: Any, sessions: list[dict]) -> list[dict]:
    entries = []
    for session in sessions:
        summary = await memory.get_session_summary(session["session_id"])
        if not summary or not summary.get("summary"):
            continue
        entries.append(
            {
                "id": f"summary:{session['session_id']}",
                "kind": "summary",
                "content": summary["summary"],
                "source": {
                    "kind": "chat",
                    "session_id": session["session_id"],
                    "label": session.get("title") or "a chat",
                },
                "created": summary.get("updated_at", ""),
                "last_used": summary.get("updated_at", ""),
                "expires": "",
                "covers": summary.get("covered_count", 0),
                "editable": False,
            }
        )
    return entries


def learned(adaptive: Any, owner_id: str) -> list[dict]:
    """Counts of what MIZAN learned from this user's verified work (managed in Learning)."""
    from tadbir import hifz, taallum, tajriba, talaqqi

    entries = []
    for kind, label, summary in (
        ("wording", "Phrasings MIZAN understands without the model", taallum.summary),
        ("programs", "Verified programs MIZAN re-runs", hifz.summary),
        ("lessons", "Lessons from verified repairs", tajriba.summary),
        (
            "answers",
            "Answers its sources confirmed, given again without the model",
            talaqqi.summary,
        ),
    ):
        try:
            data = summary(adaptive, owner_id)
        except Exception:  # noqa: BLE001 - a missing store is simply nothing learned
            continue
        count = next(
            (data[key] for key in ("examples", "programs", "lessons", "answers") if key in data), 0
        )
        if count:
            entries.append(
                {
                    "id": f"learned:{kind}",
                    "kind": "learned",
                    "content": f"{label}: {count}",
                    "source": {"kind": "verified_work", "label": "your verified requests"},
                    "created": "",
                    "last_used": "",
                    "expires": "",
                    "editable": False,
                }
            )
    try:
        from tadbir.tadrib import store as lessons

        found = lessons.counts(owner_id)
        count = found.get("learned", 0) + found.get("held_out", 0)
    except Exception:  # noqa: BLE001 - a missing store is simply nothing learned
        count = 0
    if count:
        entries.append(
            {
                "id": "learned:reader",
                "kind": "learned",
                "content": f"Your messages MIZAN's own language reader learned from: {count}",
                "source": {"kind": "verified_work", "label": "your messages (training: on)"},
                "created": "",
                "last_used": "",
                "expires": "",
                "editable": False,
            }
        )
    try:
        from memory import episodic

        held = episodic.counts(owner_id)
    except Exception:  # noqa: BLE001 - a missing store is simply nothing kept
        held = {"episodes": 0, "lasting": 0}
    if held["episodes"]:
        entries.append(
            {
                "id": "learned:episodes",
                "kind": "learned",
                "content": (
                    f"Things you said that MIZAN keeps as episodes: {held['episodes']}, "
                    f"of which {held['lasting']} came up again (not yet used in answers)"
                ),
                "source": {"kind": "chat", "label": "your chats (learning: on)"},
                "created": "",
                "last_used": "",
                "expires": "",
                "editable": False,
            }
        )
    return entries


def search(entries: list[dict], query: str) -> list[dict]:
    """Entries about a topic (BM25 over their words), best first."""
    terms = tokenize(query)
    if not terms:
        return entries
    documents = [tokenize(f"{entry.get('key', '')} {entry['content']}") for entry in entries]
    scores = bm25_scores(terms, documents)
    ranked = sorted(
        (pair for pair in zip(scores, entries, strict=True) if pair[0] > 0),
        key=lambda pair: pair[0],
        reverse=True,
    )
    return [entry for _score, entry in ranked]


async def ledger(
    *, notes_store: Any, memory: Any, adaptive: Any, owner_id: str, query: str = "", kind: str = ""
) -> dict:
    sessions = await memory.list_sessions(limit=200, owner_id=owner_id)
    titles = {item["session_id"]: item.get("title") or "" for item in sessions}
    entries = [
        *notes(notes_store, titles),
        *(await preferences(memory, owner_id, titles)),
        *(await summaries(memory, sessions)),
        *learned(adaptive, owner_id),
    ]
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry["kind"]] = counts.get(entry["kind"], 0) + 1
    if kind:
        entries = [entry for entry in entries if entry["kind"] == kind]
    if query.strip():
        entries = search(entries, query)
    return {"entries": entries, "counts": counts}


# ── Changes ──────────────────────────────────────────────────────────────


def edit_note(
    store: Any, note_id: str, *, content: str | None, tags: list[str] | None, expires: str | None
) -> bool:
    from security import satr

    changes, params = [], []
    if content is not None:
        changes.append("content = ?")
        params.append(satr.cover_text(content.strip()))  # a secret is never kept (Satr)
    if tags is not None:
        changes.append("tags = ?")
        params.append(json.dumps([tag.strip() for tag in tags if tag.strip()][:20]))
    if expires is not None:
        changes.append("expires = ?")
        params.append(expires)
    if not changes:
        return False
    # The column names come from the fixed list above, never from input.
    sql = "UPDATE memories SET " + ", ".join(changes) + " WHERE id = ?"  # noqa: S608
    found = _write(store, sql, (*params, note_id))
    _drop_cached(store, note_id)
    return found > 0


def forget_note(store: Any, note_id: str) -> bool:
    removed = _write(store, "DELETE FROM memories WHERE id = ?", (note_id,))
    _drop_cached(store, note_id)
    return removed > 0


def _drop_cached(store: Any, note_id: str) -> None:
    for kind in ("episodic", "semantic", "procedural"):
        store._get_cache(kind).pop(note_id, None)
    store.working_memory.pop(note_id, None)


async def forget(*, notes_store: Any, memory: Any, owner_id: str, ids: list[str]) -> dict[str, int]:
    """Forget the chosen notes and preferences (summaries and learned items are managed elsewhere)."""
    forgotten = {"note": 0, "preference": 0}
    for entry_id in ids[:MAX_IMPORT]:
        kind, _, key = entry_id.partition(":")
        if kind == "note" and forget_note(notes_store, key):
            forgotten["note"] += 1
        elif kind == "preference":
            try:
                if await memory.delete_chat_preference(owner_id, key):
                    forgotten["preference"] += 1
            except ValueError:
                continue
    return forgotten


# ── Export and import ────────────────────────────────────────────────────


def to_markdown(entries: list[dict], owner: str) -> str:
    lines = [f"# What MIZAN keeps about {owner}", "", f"Exported {_now()[:19]} UTC.", ""]
    titles = {
        "preference": "Preferences",
        "note": "Notes",
        "summary": "Chat summaries",
        "learned": "Learned from your verified work",
    }
    for kind, title in titles.items():
        chosen = [entry for entry in entries if entry["kind"] == kind]
        if not chosen:
            continue
        lines += [f"## {title}", ""]
        for entry in chosen:
            head = f"**{entry['key']}**: " if entry.get("key") else ""
            text = re.sub(r"\s+", " ", str(entry["content"])).strip()
            meta = [entry["source"]["label"]]
            if entry.get("created"):
                meta.append(f"made {entry['created'][:10]}")
            if entry.get("last_used"):
                meta.append(f"last used {entry['last_used'][:10]}")
            if entry.get("expires"):
                meta.append(f"expires {entry['expires'][:10]}")
            lines.append(f"- {head}{text} _({'; '.join(meta)})_")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def to_json(entries: list[dict]) -> dict:
    portable = [
        {
            key: entry[key]
            for key in ("kind", "key", "content", "type", "tags", "expires")
            if key in entry
        }
        | {"created": entry.get("created", ""), "source": entry["source"].get("label", "")}
        for entry in entries
        if entry["kind"] in ("note", "preference")
    ]
    return {"format": FORMAT, "exported": _now(), "entries": portable}


async def import_entries(
    *, notes_store: Any, memory: Any, owner_id: str, data: dict
) -> dict[str, int]:
    """Bring in notes and preferences from an export; text is stored as data, never as instructions."""
    from tadbir import amanah

    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise ValueError(f"Not a {FORMAT} export")
    added = {"note": 0, "preference": 0, "skipped": 0}
    for item in (data.get("entries") or [])[:MAX_IMPORT]:
        if not isinstance(item, dict) or not str(item.get("content", "")).strip():
            added["skipped"] += 1
            continue
        content = str(item["content"])[:4000]
        if amanah.scan(content):
            added["skipped"] += 1  # an imported note never carries instructions to the AI
            continue
        if item.get("kind") == "preference" and item.get("key"):
            from memory.dhikr import CONSENT_PREFERENCES

            if str(item["key"]) in CONSENT_PREFERENCES:
                # A consent choice is made here, by its owner, never carried in a file.
                added["skipped"] += 1
                continue
            try:
                await memory.set_chat_preference(owner_id, str(item["key"]), content)
                added["preference"] += 1
            except ValueError:
                added["skipped"] += 1
            continue
        await notes_store.remember(
            content,
            memory_type=str(item.get("type") or "semantic")
            if item.get("type") in ("semantic", "episodic", "procedural")
            else "semantic",
            importance=0.6,
            tags=[str(tag)[:40] for tag in (item.get("tags") or [])][:20],
            source="import",
            expires=str(item.get("expires") or ""),
        )
        added["note"] += 1
    return added
