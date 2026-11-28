"""Talaqqi (تلقّي): what the teacher taught once, MIZAN keeps and answers alone.

"Then Adam received from his Lord [some] words" (2:37, fa-talaqqā); "Who taught
by the pen, taught man that which he knew not" (96:4-5). What is received is
written down and kept, so it need not be asked for again.

When the language model answers a question about the world, Ahl al-Dhikr asks
MIZAN's sources about each of its claims. What a source confirmed is kept, for
that user, as the teacher's lesson: the confirmed sentences of the answer, in
their order, and only these ("if a disobedient one brings you news, verify it",
49:6: what no source confirmed is never repeated without the teacher). A
confirmed sentence that does not name what it speaks of ("It is a famous novel
of hers", read with its subject, ``ahl_dhikr.contexts``) is not kept: apart
from its answer it says nothing, and it is re-checked alone. It is
kept only when no claim was contradicted and the confirmed sentences answer the
question (they hold most of its distinctive information, ``ahl_dhikr.about``).
Each lesson keeps its sanad: the question's words, the teacher (the model that
answered), how it was received (samāʿ, heard from the teacher), and the
sentence, title and link of the source that confirmed each claim.

A later question with the same content words, numbers and asking words, in the
same language, is answered from the kept answer with no language-model call.
Every reuse is checked first. A kept answer carries an FSRS strength
(``memory.tadhkir``): while its retrievability R(t) is at least FSRS's target
of 0.9, its claims stand on the sentences that confirmed them. Once R(t) falls
below, the claims are asked of the outside sources again (Wikipedia and the
web, read by the NLI model; no language model):

- every claim supported: the answer is given, and its strength grows (an FSRS
  Good review), so the next outside check comes later;
- any claim contradicted: the answer is dropped and the teacher is asked again;
- otherwise (a source unreachable, a sentence not found): the teacher is asked
  this time, and the new answer replaces the kept one if it is confirmed.

Only a question that opens its chat is kept, and only such a question is
answered from what was kept: one that leans on earlier messages ("who founded
it?") could name another topic in the same words. A religious question or a
ruling is never kept: deen answers come from the Quran, hadith and scholars,
never from a model's words. A stateless run neither keeps nor reuses, and with
``learning: off`` nothing is kept (``AdaptiveStateStore.put``). What a chat
taught goes with the chat (Mahw).
"""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from fsrs import Rating

from memory import tadhkir

from .ahl_dhikr import Finding, Passage, about, host_of, judge, sentences
from .hifz import _numbers
from .taallum import _ASKING, content_words

MAX_KEPT = 200
# The kept question must fit the new one as closely as a kept program must fit
# its request (Hifz): the same content words, apart from a fifth at most.
MIN_OVERLAP = 0.8
# FSRS's own default desired retention: below it, a review is due.
RETENTION = 0.9
MAX_ANSWER = 8000


def _key(user_id: str) -> str:
    return "talaqqi:" + hashlib.sha256((user_id or "anonymous").encode()).hexdigest()[:24]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _load(store: Any, user_id: str) -> list[dict]:
    try:
        data = store.get(_key(user_id)) or {}
    except Exception:  # noqa: BLE001 - no store: nothing kept
        return []
    return [item for item in data.get("answers", []) if isinstance(item, dict)]


def _save(store: Any, user_id: str, items: list[dict]) -> None:
    kept = sorted(items, key=lambda item: str(item.get("used", "")), reverse=True)[:MAX_KEPT]
    try:
        store.put(_key(user_id), {"answers": kept})
    except Exception:  # noqa: BLE001 - keeping is best effort
        pass


def opens_chat(history: list[dict] | None) -> bool:
    """No earlier message of the user's in this chat: the question stands alone."""
    return not any(isinstance(turn, dict) and turn.get("role") == "user" for turn in history or [])


def standing(findings: list[Finding]) -> list[Finding]:
    """The confirmed claims that stand alone: a claim read with what it refers
    to ("It is a famous novel of hers", ``ahl_dhikr.contexts``) says nothing
    once kept apart from the answer, so it is not kept."""
    return [
        finding
        for finding in findings
        if finding.verdict == "supported" and finding.passage is not None and not finding.context
    ]


def lesson(findings: list[Finding]) -> str:
    """The confirmed sentences of an answer that stand alone, in their order,
    as one text."""
    parts = []
    for finding in standing(findings):
        sentence = finding.claim.strip()
        if sentence and not sentence.endswith((".", "!", "?", "۔", "؟", "।")):
            sentence += "."
        parts.append(sentence)
    return " ".join(parts)


def keep(
    store: Any,
    user_id: str,
    question: str,
    language: str,
    findings: list[Finding],
    *,
    teacher: str = "",
    chat: str = "",
) -> bool:
    """Keep what the sources confirmed of an answer, the claims that stand
    alone, when nothing was contradicted and the confirmed part answers the
    question."""
    supported = standing(findings)
    tokens = content_words(question)
    if not supported or not tokens or any(f.verdict == "contradicted" for f in findings):
        return False
    answer = lesson(findings)
    if len(answer) > MAX_ANSWER or not about(question, answer):
        return False
    from security import satr

    # Satr: an answer that would be given again holds no secret; covering it would
    # hand out the placeholder instead, so it is simply not kept.
    if satr.holds(answer) or any(satr.holds(f.passage.text) for f in supported if f.passage):
        return False
    now = _now()
    claims = []
    for finding in supported:
        passage = finding.passage
        assert passage is not None
        claims.append(
            {
                "claim": finding.claim,
                "p": round(float(finding.probability or 0.0), 3),
                "says": passage.text[:600],
                "title": passage.title,
                "url": passage.url,
                "host": host_of(passage.url),
                "source": passage.source,
                "checked": passage.at or now,
            }
        )
    items = [
        item
        for item in _load(store, user_id)
        if not (item.get("tokens") == tokens and item.get("language") == language)
    ]
    items.append(
        {
            "tokens": tokens,
            "numbers": _numbers(question),
            "asking": sorted(_ASKING & set(tokens)),
            "language": language,
            "answer": answer,
            "claims": claims,
            "teacher": teacher,
            # How it was received (tahammul): heard from the teacher, then each
            # claim confirmed by a source MIZAN read itself.
            "received": "sama",
            "kept": now,
            "used": now,
            "reused": 0,
            "strength": tadhkir.review(None, Rating.Good),
            # Mahw drops what a deleted chat taught.
            "chat": chat,
        }
    )
    _save(store, user_id, items)
    return True


def recall(store: Any, user_id: str, question: str, language: str) -> dict | None:
    """The kept answer to this question, if one fits it closely enough to give."""
    words = content_words(question)
    if not words:
        return None
    best, best_overlap = None, 0.0
    for item in _load(store, user_id):
        if item.get("language") != language or not item.get("claims"):
            continue
        tokens = set(item.get("tokens") or [])
        overlap = len(tokens & set(words)) / max(1, len(tokens | set(words)))
        if overlap > best_overlap:
            best, best_overlap = item, overlap
    if best is None or best_overlap < MIN_OVERLAP:
        return None
    if best.get("numbers", []) != _numbers(question):
        return None  # "population in 2010" is not "population in 2020"
    if (_ASKING & set(words)) != set(best.get("asking", [])):
        return None  # "what is X" is not "why is X"
    return best


def due(item: dict, now: datetime | None = None) -> bool:
    """Whether the kept answer's claims are to be asked of the sources again."""
    held = tadhkir.retrievability(item.get("strength"), now)
    return held is None or held < RETENTION


def _standing(item: dict) -> list[Finding]:
    """Each claim on the sentence that confirmed it when it was last checked."""
    return [
        Finding(
            claim["claim"],
            "supported",
            float(claim.get("p") or 0.0),
            Passage(claim["says"], claim["title"], claim["url"], claim["source"], claim["checked"]),
        )
        for claim in item.get("claims", [])
    ]


async def recheck(
    item: dict, outside: Callable[[str], Awaitable[list[Passage]]]
) -> tuple[str, list[Finding]]:
    """Whether the kept answer still holds: "held" (not due, its claims stand on
    their sources), "confirmed" (asked again; every claim supported),
    "contradicted" (a source now says otherwise) or "unsettled"."""
    if not due(item):
        return "held", _standing(item)
    claims = [claim["claim"] for claim in item.get("claims", [])]
    try:
        pool = await outside(" ".join(item.get("tokens", [])))
    except Exception:  # noqa: BLE001 - a source that cannot be read settles nothing
        pool = []
    findings = await judge(claims, sentences(pool)) if pool else []
    verdicts = [finding.verdict for finding in findings]
    if "contradicted" in verdicts:
        return "contradicted", findings
    if findings and len(findings) == len(claims) and set(verdicts) == {"supported"}:
        return "confirmed", findings
    return "unsettled", findings


def _confirm(item: dict, findings: list[Finding]) -> None:
    """The sources confirmed the answer again: an FSRS Good review, and each
    claim now stands on the sentence that confirmed it this time."""
    item["strength"] = tadhkir.review(item.get("strength"), Rating.Good)
    fresh = {f.claim: f for f in findings if f.passage is not None}
    for claim in item.get("claims", []):
        finding = fresh.get(claim["claim"])
        if finding is not None and finding.passage is not None:
            claim.update(
                says=finding.passage.text[:600],
                title=finding.passage.title,
                url=finding.passage.url,
                host=host_of(finding.passage.url),
                source=finding.passage.source,
                checked=finding.passage.at or _now(),
                p=round(float(finding.probability or 0.0), 3),
            )


def _same(item: dict, kept: dict) -> bool:
    return bool(
        item.get("tokens") == kept.get("tokens") and item.get("language") == kept.get("language")
    )


def reused(
    store: Any, user_id: str, kept: dict, findings: list[Finding], *, confirmed: bool
) -> dict:
    """Record a reuse; a reuse the sources confirmed again strengthens the answer."""
    items = _load(store, user_id)
    for item in items:
        if _same(item, kept):
            item["used"] = _now()
            item["reused"] = int(item.get("reused", 0)) + 1
            if confirmed:
                _confirm(item, findings)
            _save(store, user_id, items)
            return item
    return kept


def refreshed(store: Any, user_id: str, kept: dict, findings: list[Finding]) -> None:
    """The sources confirmed a kept answer again while no one asked for it
    (Nawm): its strength grows, and it is not counted as given."""
    items = _load(store, user_id)
    for item in items:
        if _same(item, kept):
            _confirm(item, findings)
            item["refreshed"] = _now()
            _save(store, user_id, items)
            return


def answers(store: Any, user_id: str) -> list[dict]:
    """Every answer kept for this user."""
    return _load(store, user_id)


def drop(store: Any, user_id: str, kept: dict) -> None:
    items = _load(store, user_id)
    remaining = [item for item in items if not _same(item, kept)]
    if len(remaining) != len(items):
        _save(store, user_id, remaining)


def summary(store: Any, user_id: str) -> dict:
    items = _load(store, user_id)
    return {
        "answers": len(items),
        "reuses": sum(int(item.get("reused", 0)) for item in items),
        "items": [
            {
                "request": " ".join(item.get("tokens", []))[:120],
                "language": item.get("language", ""),
                "teacher": item.get("teacher", ""),
                "kept": item.get("kept", ""),
                "reused": int(item.get("reused", 0)),
                "sources": sorted({claim.get("host", "") for claim in item.get("claims", [])}),
                "next_check_days": round(
                    float(tadhkir.interval_days(item.get("strength")) or 0), 1
                ),
            }
            for item in items[:50]
        ],
    }


def forget(store: Any, user_id: str) -> None:
    try:
        store.put(_key(user_id), {"answers": []})
    except Exception:  # noqa: BLE001
        pass
