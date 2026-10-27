"""Muhasaba (محاسبة): MIZAN reviews its recent answers and corrects what it can prove wrong.

On a schedule, MIZAN re-reads the answers the language model gave in words
(not those MIZAN verified) and checks what it can check itself:

- arithmetic stated as ``expression = value``, recomputed exactly;
- Quran and hadith text quoted with a reference, compared with the text
  MIZAN reads from its authentic source.

When it finds a mistake it posts a correction (Tawbah) in the same chat,
marked as MIZAN's own review. A user turns this off with the chat preference
``muhasaba: off``. Each answer is reviewed once.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from . import calc, fahm, hadith, muqabala, quran
from .express import phrase

logger = logging.getLogger("mizan.muhasaba")

_STATED = re.compile(r"=\s*\**\s*(-?\d[\d,]*(?:\.\d+)?)")


def arithmetic(text: str) -> list[dict]:
    """``expression = value`` claims whose value MIZAN computes differently."""
    findings = []
    for line in (text or "").splitlines():
        for match in _STATED.finditer(line):
            # The expression is what stands right before this "=".
            left = line[: match.start()].rstrip(" *`")
            segment = re.split(r"[=,;:]|\band\b|\bso\b|\baur\b", left, flags=re.I)[-1]
            expression = calc.find_expression(segment[-200:])
            if not expression or not re.search(r"[+\-*/^%!×÷]", expression):
                continue
            try:
                value = calc.evaluate(calc.normalize(expression))
            except calc.CalcError:
                continue
            claimed = match.group(1).replace(",", "")
            correct = calc.render(value).split(" ")[0]
            if _agrees(claimed, value):
                continue
            findings.append(
                {
                    "kind": "arithmetic",
                    "expression": expression.strip(),
                    "claimed": claimed,
                    "correct": correct,
                }  # fmt: skip
            )
    return findings[:5]


def _agrees(claimed: str, value: calc.Number) -> bool:
    try:
        stated = float(claimed)
        exact = float(value)
    except (TypeError, ValueError, OverflowError):
        return False
    if "." in claimed:
        places = len(claimed.split(".")[1])
        return round(exact, places) == round(stated, places)
    return claimed == calc.render(value).split(" ")[0] or (
        abs(exact) > 1e15 and abs(stated - exact) <= abs(exact) * 1e-12
    )


async def scripture(text: str) -> list[dict]:
    """Quoted Quran or hadith text that differs from MIZAN's source."""
    if len(muqabala.fold_arabic(text)) < 4:
        return []
    try:
        reference = quran.parse_reference(text)
        if reference is not None:
            data = await quran.fetch(reference, "en")
            source = "\n".join(ayah["arabic"] for ayah in data.get("ayahs", []))
            label = data.get("reference", "")
        else:
            narration = hadith.parse_reference(text)
            if narration is None:
                return []
            data = await hadith.fetch(narration, "en")
            source = str(data.get("arabic") or "")
            label = data.get("reference", "")
    except Exception as exc:  # noqa: BLE001 - an unreachable source proves nothing
        logger.debug("Muhasaba could not read the source: %s", exc)
        return []
    if not source:
        return []
    quoted = "\n".join(f"> {line}" for line in source.splitlines() if line.strip())
    check = muqabala.quote_check(text, quoted)
    if check["status"] not in {"differs", "close"}:
        return []
    return [
        {
            "kind": "quote",
            "reference": label,
            "source": source[:3000],
            "status": check["status"],
            "changed": check.get("changed", []),
        }  # fmt: skip
    ]


async def review(text: str) -> list[dict]:
    return arithmetic(text) + await scripture(text)


def correction(findings: list[dict], language: str) -> str:
    lines = [f"**{phrase('muhasaba_head', language)}**", ""]
    for finding in findings:
        if finding["kind"] == "arithmetic":
            lines.append(
                "- "
                + phrase(
                    "muhasaba_arithmetic",
                    language,
                    expression=finding["expression"],
                    correct=finding["correct"],
                    claimed=finding["claimed"],
                )
            )
        else:
            lines.append("- " + phrase("muhasaba_quote", language, reference=finding["reference"]))
            lines.extend(f"> {line}" for line in finding["source"].splitlines() if line.strip())
    lines += ["", f"_{phrase('muhasaba_tail', language)}_"]
    return "\n".join(lines)


def _reviewable(metadata: dict) -> bool:
    usage = metadata.get("usage")
    if not isinstance(usage, dict):
        usage = {}
    if metadata.get("muhasaba") or usage.get("orchestrator") == "mizan":
        return False
    status = metadata.get("completion_status") or usage.get("completion_status")
    return status != "verified_by_mizan" and metadata.get("status", "complete") == "complete"


async def run(memory: Any, *, hours: float = 24, limit: int = 300) -> dict:
    """Review the recent unreviewed answers in ``memory``; returns what was found."""
    since = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
    conn = memory._get_conn()
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS muhasaba_reviews (message_id TEXT PRIMARY KEY, "
            "reviewed_at TEXT NOT NULL, findings INTEGER NOT NULL)"
        )
        rows = conn.execute(
            "SELECT m.id, m.session_id, m.content, m.metadata, m.created_at FROM agent_messages m "
            "LEFT JOIN muhasaba_reviews r ON r.message_id = m.id "
            "WHERE m.role = 'assistant' AND m.created_at >= ? AND r.message_id IS NULL "
            "ORDER BY m.created_at LIMIT ?",
            (since, limit),
        ).fetchall()
        conn.commit()
    finally:
        memory._release_conn(conn)
    reviewed = corrected = 0
    for message_id, session_id, content, raw, created_at in rows:
        try:
            metadata = json.loads(raw or "{}")
        except ValueError:
            metadata = {}
        findings: list[dict] = []
        if _reviewable(metadata) and content:
            owner = await memory.session_owner(session_id)
            if owner and not await _opted_out(memory, owner):
                findings = await review(content)
        if findings:
            # Correct in the language the user asked in, not the answer's script.
            asked = _question(memory, session_id, created_at)
            language = fahm.detect_language(asked or content)
            correction_id = await memory.save_message(
                session_id,
                "assistant",
                correction(findings, language),
                metadata={
                    "muhasaba": True,
                    "corrects": metadata.get("message_id") or message_id,
                    "findings": findings,
                    "status": "complete",
                    "completion_status": "verified_by_mizan",
                    "task_verified": True,
                    "answer_delivered": True,
                },
            )
            corrected += 1
            _mark(memory, correction_id, 0)  # MIZAN's own correction needs no review
        _mark(memory, message_id, len(findings))
        reviewed += 1
    if corrected:
        logger.info("[MUHASABA] Reviewed %s answers, corrected %s", reviewed, corrected)
    return {"reviewed": reviewed, "corrected": corrected}


def _question(memory: Any, session_id: str, before: str) -> str:
    conn = memory._get_conn()
    try:
        row = conn.execute(
            "SELECT content FROM agent_messages WHERE session_id = ? AND role = 'user' "
            "AND created_at <= ? ORDER BY created_at DESC LIMIT 1",
            (session_id, before),
        ).fetchone()
    finally:
        memory._release_conn(conn)
    return str(row[0]) if row else ""


def _mark(memory: Any, message_id: str, findings: int) -> None:
    conn = memory._get_conn()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO muhasaba_reviews VALUES (?, ?, ?)",
            (message_id, datetime.now(UTC).isoformat(), findings),
        )
        conn.commit()
    finally:
        memory._release_conn(conn)


async def _opted_out(memory: Any, owner: str) -> bool:
    try:
        preferences = await memory.get_chat_preferences(owner)
    except Exception:  # noqa: BLE001
        return False
    return any(
        item.get("key") == "muhasaba" and str(item.get("value", "")).strip().lower() == "off"
        for item in preferences
    )
