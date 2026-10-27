"""Muqabala (مقابلة): one message to the base model alone and to MIZAN, side by side.

The debug mode shows what MIZAN adds. The base arm sends the message to the
same provider and model with one plain system prompt, no tools and no
memory. The MIZAN arm runs the agent as a chat would, with a trace bound so
every step is recorded (``trace``). MIZAN then checks both answers against
what it established itself: numbers no fact supports, claims of actions with
no receipt, Quran and hadith quotes against the text MIZAN quoted from its
source, and whether either arm declined to answer.

Runs are kept per user (the last ``KEEP_RUNS``) in that user's private
directory, never in chat history or training data.
"""

from __future__ import annotations

import asyncio
import difflib
import hashlib
import json
import os
import re
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from agents.events import bind_event_sink, bounded

from . import isnad, trace
from .express import _ACTION_CLAIM, _NUMBER

BASE_SYSTEM = "You are a helpful assistant."
BASE_MAX_TOKENS = 4096
KEEP_RUNS = 50
MAX_STORED_TEXT = 6000
ACCESS = ("admins", "users", "off")

_ABSTAIN = re.compile(
    r"\b(?:i\s+(?:do\s+not|don't|cannot|can't)\s+(?:know|verify|confirm|access|browse|"
    r"check|be\s+sure)|i'?m\s+not\s+(?:sure|able|certain)|unable\s+to\s+(?:verify|answer|"
    r"access|confirm)|no\s+reliable\s+(?:information|source)|as\s+an\s+ai\b|i\s+have\s+no\s+"
    r"(?:access|way)|mujhe\s+(?:nahi|nahin)\s+pata|pata\s+nahi)",
    re.IGNORECASE,
)
_ARABIC_MARKS = re.compile("[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed\u0640]")
_ARABIC_WORD = re.compile("[\u0621-\u064a\u0671-\u06d3\u06fa-\u06ff]+")
_ARABIC_RUN = re.compile(
    "[\u0621-\u064a\u0671-\u06d3\u06fa-\u06ff\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed\u0640]+"
)
# Letter forms that differ between the Uthmani and the common script. The long
# alif is dropped because Uthmani writes it as a mark (السموت, السماوات).
_ARABIC_FOLD = str.maketrans(
    {
        "\u0671": "",  # alif wasla
        "\u0623": "",
        "\u0625": "",
        "\u0622": "",
        "\u0627": "",
        "\u0649": "\u064a",  # alif maqsura → ya
        "\u0629": "\u0647",  # ta marbuta → ha
        "\u0624": "\u0648",
        "\u0626": "",  # the hamza's seat differs between the scripts (\u064a\u0626\u0648\u062f\u0647, \u064a\u0640\u0654\u0648\u062f\u0647)
        "\u06e5": "",  # small waw
        "\u06e6": "",  # small ya
    }
)
_DIGITS = str.maketrans(
    "\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668\u0669"
    "\u06f0\u06f1\u06f2\u06f3\u06f4\u06f5\u06f6\u06f7\u06f8\u06f9",
    "01234567890123456789",
)


def access() -> str:
    value = os.getenv("MIZAN_DEBUG_MODE", "admins").strip().lower()
    return value if value in ACCESS else "admins"


def allowed(is_admin: bool) -> bool:
    mode = access()
    return mode == "users" or (mode == "admins" and is_admin)


# ── the two arms ─────────────────────────────────────────────────────────


def _text(response: Any) -> str:
    return "".join(
        getattr(block, "text", "")
        for block in getattr(response, "content", []) or []
        if getattr(block, "type", "") == "text"
    ).strip()


async def base_arm(agent: Any, prompt: str, history: list[dict]) -> dict:
    """The model alone: the same provider and model, no tools, no memory, no MIZAN."""
    from api.usage import build_usage_block
    from providers import effective_limits

    from .lisan import _call_seconds

    provider, model = getattr(agent, "ai_client", None), getattr(agent, "ai_model", None)
    if provider is None or getattr(provider, "provider_name", "") == "mizan-owned":
        return {"text": "", "error": "No hosted language model is configured", "usage": {}}
    max_tokens = max(1, min(BASE_MAX_TOKENS, effective_limits(provider, model or "")[1]))
    messages = [*history[-20:], {"role": "user", "content": prompt}]
    started = time.perf_counter()
    try:
        response = await asyncio.wait_for(
            asyncio.to_thread(
                provider.create,
                model=model,
                max_tokens=max_tokens,
                system=BASE_SYSTEM,
                messages=messages,
            ),
            _call_seconds(),
        )
    except TimeoutError:
        return {"text": "", "error": "The model did not answer in time", "usage": {}}
    except Exception as exc:  # noqa: BLE001 - provider errors vary
        return {"text": "", "error": f"Model error: {type(exc).__name__}", "usage": {}}
    latency = (time.perf_counter() - started) * 1000
    return {
        "text": _text(response),
        "error": None,
        "usage": build_usage_block({"response": response, "latency_ms": round(latency, 1)}),
        "latency_ms": round(latency, 1),
        "system": BASE_SYSTEM,
        "model_calls": 1,
        "tool_calls": 0,
    }


async def mizan_arm(agent: Any, prompt: str, context: dict) -> dict:
    """MIZAN as a chat runs it, with every step traced and every live event kept."""
    events: list[dict] = []

    async def sink(kind: str, payload: dict) -> None:
        events.append({"kind": kind, **payload})

    started = time.perf_counter()
    error = None
    result: dict = {}
    with trace.bind() as recorded, bind_event_sink(sink):
        try:
            result = await agent.execute(prompt, context)
        except Exception as exc:  # noqa: BLE001 - the comparison reports it
            error = f"{type(exc).__name__}"
    latency = (time.perf_counter() - started) * 1000
    text = result.get("result", "")
    if isinstance(text, dict):
        text = text.get("response", json.dumps(text, ensure_ascii=False, default=str))
    spans = recorded.to_list()
    usage = result.get("usage", {}) if isinstance(result.get("usage"), dict) else {}
    return {
        "text": str(text or ""),
        "error": error or (None if result.get("success", True) else result.get("error_code")),
        "usage": usage,
        "latency_ms": round(latency, 1),
        "spans": spans,
        "events": bounded(events[-200:]),
        "orchestrator": result.get("orchestrator", "language_model"),
        "orchestration": bounded(result.get("orchestration", {})),
        "completion_status": result.get("completion_status"),
        "verified": bool(result.get("task_verified")),
        "isnad": result.get("isnad"),
        # Observed provider calls; a Lisan span wraps the provider call it made.
        "model_calls": sum(
            1 for span in spans if span["op"] == "chat" and not span["name"].startswith("lisan.")
        ),
        "lisan_calls": sum(1 for span in spans if span["name"].startswith("lisan.")),
        "tool_calls": sum(1 for span in spans if span["op"] == "execute_tool"),
    }


# ── MIZAN's checks on both answers ───────────────────────────────────────


def arabic_words(text: str) -> list[tuple[str, str]]:
    """(folded, as written) for each Arabic word: marks removed and letter forms folded."""
    words = []
    for written in _ARABIC_RUN.findall(text):
        folded = "".join(
            _ARABIC_WORD.findall(_ARABIC_MARKS.sub("", written).translate(_ARABIC_FOLD))
        )
        if folded:
            words.append((folded, written))
    return words


def fold_arabic(text: str) -> list[str]:
    """Arabic words folded for comparing quotes across scripts and editions."""
    return [folded for folded, _written in arabic_words(text)]


def _facts_text(spans: list[dict], prompt: str) -> str:
    parts = [prompt]
    for span in spans:
        attributes = span.get("attributes", {})
        if span["op"] == "execute_tool":
            parts.append(str(attributes.get("result", "")))
        elif span["op"] == "plan" and span["name"] == "result":
            parts.append(json.dumps(attributes.get("facts", {}), ensure_ascii=False, default=str))
    return "\n".join(parts)


def _numbers(text: str) -> list[str]:
    plain = text.translate(_DIGITS)
    return sorted({number.replace(",", "") for number in _NUMBER.findall(plain)})


def _quoted(text: str) -> str:
    """The text MIZAN quoted from its source: its blockquote lines, when it has them."""
    lines = [line[1:] for line in text.splitlines() if line.startswith(">")]
    return "\n".join(lines) if lines else text


# A stretch of Arabic: words, spaces, Arabic digits and the ayah ornaments,
# broken by anything else (Latin text, a colon, brackets).
_ARABIC_SPAN = re.compile(
    r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]"
    r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF\s\u200c\u200d﴾﴿]*"
)


def quoted_runs(text: str, authentic: list[str]) -> list[tuple[str, str]]:
    """The Arabic words of the answer that are attempts to give this text.

    Each stretch of Arabic is judged on its own: it is a quote of the text when
    most of its words are the text's, or when it is at least half as long as the
    text (a passage given as the text, however different). Arabic terms used in
    an explanation (يوم، يوم القيامة) are neither, so they are not checked
    against the ayah as if they were quoting it."""
    vocabulary = set(authentic)
    found: list[tuple[str, str]] = []
    for span in _ARABIC_SPAN.findall(text):
        run = arabic_words(span)
        shared = sum(1 for folded, _ in run if folded in vocabulary)
        if run and (2 * shared > len(run) or 2 * len(run) >= len(authentic)):
            found.extend(run)
    return found


def quote_check(base: str, mizan: str) -> dict:
    """How faithfully the base answer reproduces the source text MIZAN quoted.

    ``coverage`` is the share of the source's words the base answer gives in
    order; ``precision`` is the share of words in the passage it quoted that
    are the source's. A correct excerpt has high precision and lower coverage.
    Only the answer's attempts to quote the text are read (``quoted_runs``).
    """
    source_words = arabic_words(_quoted(mizan))
    authentic = [folded for folded, _ in source_words]
    base_words = quoted_runs(base, authentic)
    given = [folded for folded, _ in base_words]
    if not given or not authentic:
        return {"status": "missing", "coverage": 0.0, "precision": 0.0, "words": len(authentic)}
    matcher = difflib.SequenceMatcher(None, authentic, given, autojunk=False)
    blocks = [block for block in matcher.get_matching_blocks() if block.size]
    matched = sum(block.size for block in blocks)
    if not blocks:
        return {"status": "differs", "coverage": 0.0, "precision": 0.0, "words": len(authentic)}
    # The passage the base answer gave as the text: its matched words and any
    # words it put in place of the source's.
    replaced = [op for op in matcher.get_opcodes() if op[0] == "replace"]
    first = min([blocks[0].b, *(op[3] for op in replaced)])
    last = max([blocks[-1].b + blocks[-1].size, *(op[4] for op in replaced)])
    coverage = matched / len(authentic)
    precision = matched / max(1, last - first)
    changed = [
        {
            "source": " ".join(written for _, written in source_words[i1:i2]),
            "given": " ".join(written for _, written in base_words[j1:j2]),
        }
        for _tag, i1, i2, j1, j2 in replaced
    ][:5]
    if coverage >= 0.97 and precision >= 0.97:
        status = "matches"
    elif precision >= 0.97:
        status = "excerpt"  # part of the text, word for word
    elif precision >= 0.85:
        status = "close"
    else:
        status = "differs"
    return {
        "status": status,
        "coverage": round(coverage, 3),
        "precision": round(precision, 3),
        "words": len(authentic),
        "changed": changed,
    }


def checks(prompt: str, base: dict, mizan: dict) -> dict:
    spans = mizan.get("spans", [])
    facts = _facts_text(spans, prompt).replace(",", "")
    grounded = mizan.get("verified") or any(span["op"] == "execute_tool" for span in spans)
    understood = next((span for span in spans if span["op"] == "understand"), None)
    intent = understood["name"] if understood else "converse"
    base_text, mizan_text = base.get("text", ""), mizan.get("text", "")

    def arm(text: str, has_receipts: bool) -> dict:
        unsupported = [n for n in _numbers(text) if n not in facts] if grounded else []
        claims = [m.group(0) for m in _ACTION_CLAIM.finditer(text)] if not has_receipts else []
        return {
            "unsupported_numbers": unsupported[:20],
            "unbacked_action_claims": claims[:5],
            "abstained": bool(_ABSTAIN.search(text)),
            "characters": len(text),
        }

    report: dict[str, Any] = {
        "intent": intent,
        "grounded": bool(grounded),
        "base": arm(base_text, False),
        "mizan": arm(mizan_text, mizan.get("tool_calls", 0) > 0),
    }
    if mizan.get("verified"):
        # Results MIZAN established, not numbers the user wrote in the request.
        asked = set(_numbers(prompt))
        verified_numbers = [n for n in _numbers(mizan_text) if n in facts and n not in asked]
        if verified_numbers:
            plain = base_text.translate(_DIGITS).replace(",", "")
            found = [n for n in verified_numbers if n in plain]
            report["agreement"] = {
                "verified_values": verified_numbers[:20],
                "base_states": found[:20],
                "share": round(len(found) / len(verified_numbers), 3),
            }
        if intent in {"quran", "hadith"} and fold_arabic(mizan_text):
            report["quote"] = quote_check(base_text, mizan_text)
    # Isnad for both answers: the base model's claims weighed against MIZAN's evidence.
    report["isnad"] = {
        "base": isnad.summary(
            isnad.ledger(base_text, evidence=_facts_text(spans, prompt) if grounded else "")
        ),
        "mizan": mizan.get("isnad") or isnad.summary(isnad.ledger(mizan_text)),
    }
    report["similarity"] = round(
        difflib.SequenceMatcher(None, base_text, mizan_text, autojunk=False).ratio(), 3
    )
    report["diff"] = list(
        difflib.unified_diff(
            base_text.splitlines(),
            mizan_text.splitlines(),
            "base model",
            "MIZAN",
            lineterm="",
            n=1,
        )
    )[:400]
    return report


async def compare(agent: Any, prompt: str, context: dict, history: list[dict]) -> dict:
    """Both arms at once; the base arm never shares MIZAN's trace or usage.
    A comparison is an evaluation: MIZAN learns nothing from it and recalls no
    other chat (memory/stateless.py)."""
    from memory import stateless

    with stateless.bind():
        # Created before MIZAN's trace is bound, so the base arm records nothing there.
        base_task = asyncio.create_task(base_arm(agent, prompt, history))
        mizan = await mizan_arm(agent, prompt, context)
        base = await base_task
    return {
        "id": uuid.uuid4().hex,
        "created_at": time.time(),
        "prompt": prompt,
        "model": getattr(agent, "ai_model", None),
        "agent": getattr(agent, "name", None),
        "base": base,
        "mizan": mizan,
        "checks": checks(prompt, base, mizan),
    }


# ── per-user history of comparisons ──────────────────────────────────────


def _db_path(user_id: str) -> Path:
    root = Path(os.getenv("MIZAN_DATA_DIR", "/data/mizan")) / "private"
    directory = root / hashlib.sha256(user_id.encode()).hexdigest()
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "debug_runs.db"


def _connect(user_id: str) -> sqlite3.Connection:
    connection = sqlite3.connect(_db_path(user_id))
    connection.execute(
        "CREATE TABLE IF NOT EXISTS debug_runs (id TEXT PRIMARY KEY, created_at REAL, "
        "prompt TEXT, summary TEXT, data TEXT)"
    )
    return connection


def _trimmed(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _trimmed(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_trimmed(item) for item in value]
    if isinstance(value, str) and len(value) > MAX_STORED_TEXT:
        return value[:MAX_STORED_TEXT] + "… (trimmed)"
    return value


def summary(run: dict) -> dict:
    report = run.get("checks", {})
    return {
        "id": run["id"],
        "created_at": run["created_at"],
        "prompt": run["prompt"][:200],
        "intent": report.get("intent"),
        "mizan_verified": run.get("mizan", {}).get("verified", False),
        "base_unsupported": len(report.get("base", {}).get("unsupported_numbers", [])),
        "quote": report.get("quote", {}).get("status"),
    }


def _save(user_id: str, run: dict) -> None:
    with _connect(user_id) as connection:
        connection.execute(
            "INSERT OR REPLACE INTO debug_runs VALUES (?, ?, ?, ?, ?)",
            (
                run["id"],
                run["created_at"],
                run["prompt"][:2000],
                json.dumps(summary(run), ensure_ascii=False),
                json.dumps(_trimmed(run), ensure_ascii=False, default=str),
            ),
        )
        connection.execute(
            "DELETE FROM debug_runs WHERE id NOT IN "
            "(SELECT id FROM debug_runs ORDER BY created_at DESC LIMIT ?)",
            (KEEP_RUNS,),
        )


def _list(user_id: str) -> list[dict]:
    with _connect(user_id) as connection:
        rows = connection.execute(
            "SELECT summary FROM debug_runs ORDER BY created_at DESC LIMIT ?", (KEEP_RUNS,)
        ).fetchall()
    return [json.loads(row[0]) for row in rows]


def _get(user_id: str, run_id: str) -> dict | None:
    with _connect(user_id) as connection:
        row = connection.execute("SELECT data FROM debug_runs WHERE id = ?", (run_id,)).fetchone()
    return json.loads(row[0]) if row else None


def _clear(user_id: str) -> None:
    with _connect(user_id) as connection:
        connection.execute("DELETE FROM debug_runs")


async def save(user_id: str, run: dict) -> None:
    await asyncio.to_thread(_save, user_id, run)


async def runs(user_id: str) -> list[dict]:
    return await asyncio.to_thread(_list, user_id)


async def get(user_id: str, run_id: str) -> dict | None:
    return await asyncio.to_thread(_get, user_id, run_id)


async def clear(user_id: str) -> None:
    await asyncio.to_thread(_clear, user_id)
