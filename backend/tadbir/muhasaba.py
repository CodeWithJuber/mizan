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

import contextvars
import json
import logging
import re
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from . import calc, fahm, hadith, iqtibas, muqabala, quran
from .express import phrase

logger = logging.getLogger("mizan.muhasaba")

_STATED = re.compile(r"=\s*\**\s*(-?\d[\d,]*(?:\.\d+)?)")


# A Markdown list marker opening a line ("- ", "* ", "+ ", "1. "): structure, not a sign.
_LIST_MARK = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")


def computable(text: str) -> bool:
    """Whether the text states an equation MIZAN can compute: every side of an
    ``=`` is a number or an expression. Such a claim is settled by computing it
    (Sidq), never by asking a source."""
    for line in (text or "").splitlines():
        sides = [side.strip(" *`.") for side in _LIST_MARK.sub("", line).split("=")]
        if len(sides) < 2 or not all(sides):
            continue
        try:
            for side in sides:
                # A side is a whole expression or a plain number, nothing else.
                expression = calc.find_expression(side) or side
                if len(expression.strip()) < len(side.strip()) - 1:
                    raise calc.CalcError("not an expression")
                calc.evaluate(calc.normalize(expression))
        except calc.CalcError:
            continue
        return True
    return False


def arithmetic(text: str) -> list[dict]:
    """``expression = value`` claims whose value MIZAN computes differently."""
    findings = []
    for line in (text or "").splitlines():
        line = _LIST_MARK.sub("", line)
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


def _cited_lines(text: str) -> list[tuple[Any, list[int]]]:
    """Each reference the text gives, with the Arabic lines that follow it.

    A reference names a number, so a verse's own words are never read as one;
    each Arabic line belongs to the reference given most recently above it, or
    on the same line."""
    groups: list[tuple[Any, list[int]]] = []
    for index, line in enumerate(text.splitlines()):
        found = quran.parse_reference(line) or hadith.parse_reference(line)
        if found is not None:
            groups.append((found, []))
        if muqabala.fold_arabic(line) and groups:
            groups[-1][1].append(index)
    return [(reference, lines) for reference, lines in groups if lines]


# Consecutive words an Arabic passage given with no reference must share with
# an ayah before it is read as a quote of that ayah.
LEAST_SHARED = 4
MAX_PASSAGES = 4  # unreferenced passages read against the source per answer
_sources: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "muhasaba_sources", default=None
)


@contextmanager
def sources() -> Iterator[None]:
    """Each source text read once while bound (one answer's checks)."""
    token = _sources.set({})
    try:
        yield
    finally:
        _sources.reset(token)


async def _source(reference: Any) -> tuple[str, str]:
    """(label, Arabic text) of a Quran or hadith reference from MIZAN's source."""
    known = _sources.get()
    key = repr(reference)
    if known is not None and key in known:
        cached: tuple[str, str] = known[key]
        return cached
    if isinstance(reference, quran.Reference):
        data = await quran.fetch(reference, "en")
        source = "\n".join(ayah["arabic"] for ayah in data.get("ayahs", []))
    else:
        data = await hadith.fetch(reference, "en")
        source = str(data.get("arabic") or "")
    found = (str(data.get("reference", "")), source)
    if known is not None:
        known[key] = found
    return found


def _index() -> iqtibas.Quotes | None:
    """The Quran's text as quotes are read (Iqtibas's, from the editions Fihris
    downloads), or None before it is read: then nothing is claimed of a
    passage given without a reference."""
    quotes = iqtibas.available()
    return quotes if quotes is not None and quotes.mushaf else None


async def _read(text: str, lines: list[int], reference: Any) -> tuple[str, str, dict] | None:
    """The quote check of these lines of the text against the reference's source."""
    try:
        label, source = await _source(reference)
    except Exception as exc:  # noqa: BLE001 - an unreachable source proves nothing
        logger.debug("Muhasaba could not read the source: %s", exc)
        return None
    if not source:
        return None
    quoted = "\n".join(f"> {line}" for line in source.splitlines() if line.strip())
    every = text.splitlines()
    return label, source, muqabala.quote_check("\n".join(every[i] for i in lines), quoted)


async def scripture(text: str) -> list[dict]:
    """Quoted Quran or hadith text that differs from MIZAN's source.

    A passage given under a reference is checked against that reference (not
    the answer's first). An Arabic passage given with no reference that shares
    at least ``LEAST_SHARED`` consecutive words with an ayah, and is mostly
    that ayah (more than half of its words, and they more than half of the
    passage), is checked against the ayah (or consecutive ayahs) it quotes;
    MIZAN finds them in its own Quran text (``iqtibas``)."""
    if len(muqabala.fold_arabic(text)) < 4:
        return []
    findings: list[dict] = []
    read: set[int] = set()  # lines whose Arabic was read as a quote of a reference
    for reference, indexes in _cited_lines(text)[:4]:
        result = await _read(text, indexes, reference)
        if result is None:
            continue
        label, source, check = result
        quoted = [indexes[i] for i in check.get("lines", []) if i < len(indexes)]
        read.update(quoted)
        if check["status"] not in {"differs", "close"}:
            continue
        findings.append(_finding(label, source, check, quoted or indexes))
    return findings + await _unreferenced(text, read)


def _finding(label: str, source: str, check: dict, lines: list[int], **extra: Any) -> dict:
    return {
        "kind": "quote",
        "reference": label,
        "source": source[:3000],
        "status": check["status"],
        "changed": check.get("changed", []),
        "lines": lines,
        **extra,
    }  # fmt: skip


def _place(stretch: muqabala.Stretch, index: iqtibas.Quotes) -> quran.Reference | None:
    """The ayah, or consecutive ayahs, around the longest run of at least
    ``LEAST_SHARED`` words of the stretch that MIZAN's Quran text holds."""
    found = [word.folded for word in stretch.words]
    place = index.passage(found, LEAST_SHARED, quran.MAX_AYAHS)
    return None if place is None else quran.Reference(*place)


def _mostly(check: dict, stretch: muqabala.Stretch) -> bool:
    """A passage is a quote of the ayahs when most of its words are theirs and
    most of their words are in it: a formula that shares a phrase with an ayah
    (لا إله إلا الله محمد رسول الله and 37:35) is not given as that ayah."""
    matched = int(check.get("matched", 0))
    return 2 * matched > len(stretch.words) and 2 * matched > int(check.get("words", 0))


async def _unreferenced(text: str, read: set[int]) -> list[dict]:
    """Quotes of the Quran given with no reference that differ from the ayah."""
    index = _index()
    if index is None:
        return []
    findings: list[dict] = []
    passages = 0
    for stretch in muqabala.stretches(text):
        if passages >= MAX_PASSAGES:
            break
        if read.intersection(stretch.lines) or len(stretch.words) < LEAST_SHARED:
            continue
        reference = _place(stretch, index)
        if reference is None:
            continue
        passages += 1
        result = await _read(text, list(stretch.lines), reference)
        if result is None or not _mostly(result[2], stretch):
            continue
        read.update(stretch.lines)
        label, source, check = result
        if check["status"] in {"differs", "close"}:
            findings.append(_finding(label, source, check, list(stretch.lines), unreferenced=True))
    return findings


async def mushaf_script(text: str, reported: Iterable[int] = ()) -> list[dict]:
    """Arabic written in the mushaf's script that is not the Quran's text.

    A stretch of Arabic carrying a mark only the mushaf writes (alif wasla,
    the Quranic signs: ``muqabala.MUSHAF_ONLY``) looks like the Quran. Each of
    its words with a mushaf mark (those, or the superscript alif) that is not
    the Quran's where it stands (not in a run of ``LEAST_SHARED`` words, or a
    whole stretch, that MIZAN's Quran text holds in order, nor part of a
    passage that matches its source) is reported. Lines already reported as
    an altered quote (``reported``) are not read again. Without MIZAN's Quran
    text nothing is claimed."""
    index = _index()
    if index is None or not muqabala.MUSHAF_ONLY.search(text):
        return []
    skip = set(reported)
    findings: list[dict] = []
    passages = 0
    for stretch in muqabala.stretches(text):
        if skip.intersection(stretch.lines) or not muqabala.MUSHAF_ONLY.search(
            text[stretch.start : stretch.end]
        ):
            continue
        marked = [bool(muqabala.MUSHAF_MARKS.search(word.written)) for word in stretch.words]
        covered = index.covered([word.folded for word in stretch.words], LEAST_SHARED)
        loose = [i for i, word in enumerate(stretch.words) if marked[i] and not covered[i]]
        if not loose:
            continue
        # A spelling the two scripts write differently (أَقْصَا, أَقْصَى) is
        # not held by the text MIZAN searches: a passage that is the Quran's
        # is read against its source before anything is said.
        reference = _place(stretch, index) if passages < MAX_PASSAGES else None
        if reference is not None:
            passages += 1
            result = await _read(text, list(stretch.lines), reference)
            if result is not None and result[2]["status"] in {"matches", "excerpt"}:
                continue
        shown = stretch.words[loose[0] : loose[-1] + 1]
        words = " ".join(word.written for word in shown[:12]) + (" …" if len(shown) > 12 else "")
        findings.append({"kind": "mushaf_script", "text": words, "lines": list(stretch.lines)})
        if len(findings) >= 5:
            break
    return findings


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
