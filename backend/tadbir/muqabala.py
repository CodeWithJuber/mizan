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
import unicodedata
import uuid
from pathlib import Path
from typing import Any, NamedTuple

from agents.events import bind_event_sink, bounded

from . import isnad, quran, trace
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
_ARABIC_RUN = re.compile(
    "[\u0621-\u064a\u0671-\u06d3\u06fa-\u06ff\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed\u0640]+"
)
# ── reading Arabic across scripts ────────────────────────────────────────
#
# The Uthmani (mushaf) script and the common script spell some words
# differently: the long alif is a mark in one and a letter in the other
# (ٱلسَّمَٰوَٰتِ, السَّمَاوَاتِ), hamza sits on different seats (يَسْتَهْزِءُونَ,
# يَسْتَهْزِئُونَ), the vocative is joined (يَٰٓأَيُّهَا, يَا أَيُّهَا). A word is
# read as its letters with these differences folded away, so a quote is
# compared word for word in whichever script it is written. Over all 6236
# ayahs of the Tanzil Uthmani and simple texts the folded words of 6222 are
# the same; the other 14 differ in a word such as أَقْصَا/أَقْصَى (a final
# alif against alif maqsura), so a quote of them in the common script is
# read as one word changed.
#
# A letter, with the small waw and ya the Uthmani writes for a letter it omits.
_LETTER = re.compile("[\u0621-\u064a\u0671-\u06d3\u06fa-\u06ff\u0640\u06e5\u06e6]")
# Alif in every form, hamza and its seats, tatweel: never compared.
_UNREAD = frozenset("\u0627\u0623\u0625\u0622\u0671\u0621\u0626\u0624\u0640")
_HAMZA = frozenset("\u0621\u0623\u0625\u0626\u0624")
_SMALL = "\u06e5\u06e6"  # small waw, small ya
_ALIF_MARK, _SILENT, _MADDA = "\u0670", "\u06df", "\u0653"
_YA, _LAM, _HA = "\u064a", "\u0644", "\u0647"
_KASRA = "\u0650"
# The vowels: fatha, damma, kasra and their tanween. Shadda and sukun are not
# compared: the Uthmani marks idgham across words with a shadda the common
# script does not write (مِّن رَّبِّهِمْ, مِنْ رَبِّهِمْ). Over the same texts,
# one word in more than 77,000 has other vowels in the two (the saktah of 18:1).
_VOWELS = frozenset("\u064b\u064c\u064d\u064e\u064f\u0650")
# The vocative and the ha of attention: one word with the next in the Uthmani.
_JOINED = frozenset({"\u064a\u0627", "\u0648\u064a\u0627", "\u0641\u064a\u0627", "\u0647\u0627"})
# The mushaf's marks: alif wasla, the superscript alif and the Quranic signs
# (pause marks, small letters, iqlab). All but the superscript alif are
# written nowhere else; Urdu spells with it (تعالیٰ, زکوٰۃ: 315 of the 6236
# sentences of the Jalandhry translation), so text is in the mushaf's script
# only when it carries one of the others (``MUSHAF_ONLY``).
MUSHAF_MARKS = re.compile("[\u0671\u0670\u06d6-\u06ed]")
MUSHAF_ONLY = re.compile("[\u0671\u06d6-\u06ed]")


class Word(NamedTuple):
    folded: str  # its letters, read across scripts
    written: str  # as the text writes it
    # The vowels on each folded letter, one set per letter it stands for (a
    # doubled ya or lam is read as one letter).
    vowels: tuple[tuple[frozenset[str], ...], ...]


def _letters(written: str) -> tuple[list[str], list[frozenset[str]]]:
    """The letters a written word is read as, each with its vowels."""
    units: list[tuple[str, set[str]]] = []
    for char in written:
        if _LETTER.match(char):
            units.append((char, set()))
        elif units:
            units[-1][1].add(char)
    # A small waw or ya at the end is a pronoun's long vowel (بِهِۦ, لَهُۥ),
    # not a letter, unless it carries a vowel (ءَاتَىٰنِۦَ).
    last = max(
        (
            index
            for index, (base, marks) in enumerate(units)
            if base != "\u0640" and (base not in _SMALL or marks & _VOWELS)
        ),
        default=-1,
    )
    letters: list[str] = []
    vowels: list[frozenset[str]] = []
    for index, (base, marks) in enumerate(units):
        if base in _UNREAD:
            continue
        if base == "\u0649":  # alif maqsura, or the Uthmani's undotted final ya
            if _SILENT in marks:
                continue
            if (
                index == last
                and index
                and not marks & _VOWELS
                and units[index - 1][0] in _HAMZA
                and _KASRA not in units[index - 1][1]
            ):
                continue  # an alif after hamza: رَأَى in the common script, رَءَا in the mushaf
            if _ALIF_MARK in marks and index < last:
                continue  # ىٰ inside a word is an alif (ءَاتَىٰهُمُ, آتَاهُمُ)
            base = _YA
        elif base == "\u0648" and _ALIF_MARK in marks and marks <= {_ALIF_MARK, _MADDA}:
            continue  # a waw that only seats an alif (ٱلصَّلَوٰةَ, الصَّلَاةَ)
        elif base == _YA and _SILENT in marks:
            continue  # a ya that is not read (مَلَإِي۟هِۦ, مَلَئِهِ)
        elif base in _SMALL:
            if index > last:
                continue
            base = "\u0648" if base == "\u06e5" else _YA  # إِبْرَٰهِۦمَ, إِبْرَاهِيمَ
        elif base == "\u0635" and "\u06dc" in marks:
            base = "\u0633"  # sad read as sin (يَبْصُۜطُ, يَبْسُطُ)
        elif base == "\u0629":
            base = _HA
        letters.append(base)
        vowels.append(frozenset(marks & _VOWELS))
    return letters, vowels


def _word(letters: list[str], vowels: list[frozenset[str]], written: str) -> Word:
    """A doubled ya or lam is read once: one script writes both letters where
    the other writes one (يُحْيِي, يُحْىِ; اللَّيْل, ٱلَّيْل). The lam of Allah's
    name stays double, so الله and إله are two words."""
    folded: list[str] = []
    grouped: list[list[frozenset[str]]] = []
    for index, letter in enumerate(letters):
        after = letters[index + 1] if index + 1 < len(letters) else ""
        if folded and folded[-1] == letter and (letter == _YA or (letter == _LAM and after != _HA)):
            grouped[-1].append(vowels[index])
            continue
        folded.append(letter)
        grouped.append([vowels[index]])
    return Word("".join(folded), written, tuple(tuple(group) for group in grouped))


def words(text: str) -> list[Word]:
    """The Arabic words of a text, read across scripts. The text is read in
    NFKC first, so the presentation forms of the letters (ﻟﻪ, ﷲ) are letters."""
    found: list[tuple[list[str], list[frozenset[str]], str]] = []
    pending: tuple[list[str], list[frozenset[str]], str] | None = None
    for written in _ARABIC_RUN.findall(unicodedata.normalize("NFKC", text)):
        letters, vowels = _letters(written)
        if not letters:
            continue
        item = (letters, vowels, written)
        if pending is not None:
            item = (pending[0] + letters, pending[1] + vowels, f"{pending[2]} {written}")
            pending = None
        bare = "".join(c for c in written if _LETTER.match(c) and c not in _SMALL + "\u0640")
        if bare in _JOINED:
            pending = item
            continue
        found.append(item)
    if pending is not None:
        found.append(pending)
    return [_word(letters, vowels, written) for letters, vowels, written in found]


def _vowels_differ(source: Word, given: Word) -> bool:
    """Whether a word given with vowels has other vowels than the source's.
    Only letters both write a vowel on are compared: a quote written without
    vowels, or with some of them, is not penalised for those it leaves out."""
    for kept, said in zip(source.vowels, given.vowels, strict=False):
        if len(kept) != len(said):
            continue
        for a, b in zip(kept, said, strict=True):
            if a and b and a != b:
                return True
    return False


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


def base_system() -> str:
    """The base model's one plain prompt, with the same clock MIZAN's arm reads
    (the user's zone): a date question is a fair comparison, not a test of
    whether the model knows today's date."""
    from .waqt import now

    moment, zone = now()
    return (
        f"{BASE_SYSTEM} The current date and time is {moment:%A %d %B %Y, %H:%M} ({zone or 'UTC'})."
    )


async def base_arm(agent: Any, prompt: str, history: list[dict]) -> dict:
    """The model alone: the same provider and model, no tools, no memory, no MIZAN."""
    from api.usage import build_usage_block
    from providers import effective_limits

    from .lisan import _call_seconds

    provider, model = getattr(agent, "ai_client", None), getattr(agent, "ai_model", None)
    if provider is None or getattr(provider, "provider_name", "") == "mizan-owned":
        return {"text": "", "error": "No hosted language model is configured", "usage": {}}
    # The same output limit per call as MIZAN's own agent loop, so a reasoning
    # model has the same room in both arms (the 27 October benchmark compared
    # 4,096 tokens for the base model with MIZAN's larger budget).
    budget = getattr(agent, "_output_token_budget", None)
    limit = int(budget()) if callable(budget) else BASE_MAX_TOKENS
    max_tokens = max(1, min(limit, effective_limits(provider, model or "")[1]))
    messages = [*history[-20:], {"role": "user", "content": prompt}]
    system = base_system()
    started = time.perf_counter()
    try:
        response = await asyncio.wait_for(
            asyncio.to_thread(
                provider.create,
                model=model,
                max_tokens=max_tokens,
                system=system,
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
        # A reasoning model can spend the whole output limit before it answers.
        "stop_reason": getattr(response, "stop_reason", None),
        "max_tokens": max_tokens,
        "system": system,
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
    """(folded, as written) for each Arabic word, read across scripts (``words``)."""
    return [(word.folded, word.written) for word in words(text)]


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


class Stretch(NamedTuple):
    """A stretch of Arabic in a text, and where it stands."""

    words: list[Word]
    start: int  # offsets in the text, without trailing space
    end: int
    lines: tuple[int, ...]  # the text's lines it is on
    # It is given as a passage (it opens its line, or follows a colon, a dash
    # or a quote mark) and words of another script follow it on the same line,
    # as its continuation.
    continued: str


def stretches(text: str) -> list[Stretch]:
    """Each stretch of Arabic in the text, with its words."""
    found = []
    for match in _ARABIC_SPAN.finditer(text):
        run = words(match.group())
        if not run:
            continue
        start = match.start()
        end = start + len(match.group().rstrip())
        first, last = text.count("\n", 0, start), text.count("\n", 0, end)
        line_end = text.find("\n", end)
        rest = text[end : len(text) if line_end < 0 else line_end].strip()
        before = text[text.rfind("\n", 0, start) + 1 : start].rstrip()
        presented = first < last or not before or not before[-1].isalnum()
        continued = (
            rest if presented and rest[:1].isalpha() and quran.parse_reference(rest) is None else ""
        )
        found.append(Stretch(run, start, end, tuple(range(first, last + 1)), continued))
    return found


def _attempt(run: list[Word], vocabulary: set[str], size: int) -> bool:
    """A stretch is an attempt to give the text when most of its words are the
    text's, or when it is at least half as long as the text (a passage given
    as the text, however different)."""
    shared = sum(1 for word in run if word.folded in vocabulary)
    return bool(run) and (2 * shared > len(run) or 2 * len(run) >= size)


def quoted_runs(text: str, authentic: list[str]) -> list[tuple[str, str]]:
    """The Arabic words of the answer that are attempts to give this text.

    Each stretch of Arabic is judged on its own (``_attempt``). Arabic terms
    used in an explanation (يوم، يوم القيامة) are not attempts, so they are not
    checked against the ayah as if they were quoting it."""
    vocabulary = set(authentic)
    return [
        (word.folded, word.written)
        for stretch in stretches(text)
        if _attempt(stretch.words, vocabulary, len(authentic))
        for word in stretch.words
    ]


def _shown(found: list[Word], limit: int = 12) -> str:
    text = " ".join(word.written for word in found[:limit])
    return text + (" …" if len(found) > limit else "")


def quote_check(base: str, mizan: str) -> dict:
    """How faithfully the base answer reproduces the source text MIZAN quoted.

    Only the answer's attempts to quote the text are read (``quoted_runs``),
    word for word across scripts (``words``). The passage it gives as the text
    runs from the first of the source's words it gives to the last:

    - ``matches``: every word of the source, in order, nothing changed, added
      or dropped, and where both write a vowel on a letter it is the same;
    - ``excerpt``: the same for a contiguous part of the source, which does not
      end inside an ayah with other words given as its continuation;
    - ``close``: anything else that is mostly the source's words (``precision``
      at least 0.85), such as one word or one vowel changed;
    - ``differs``: the rest.

    ``coverage`` is the share of the source's words given in order;
    ``precision`` the share of the passage's words that are the source's.
    """
    quoted = _quoted(mizan)
    source = words(quoted)
    authentic = [word.folded for word in source]
    # Where each ayah ends (MIZAN quotes one ayah per line).
    ends, count = set(), 0
    for line in quoted.splitlines():
        count += len(words(line))
        ends.add(count)
    vocabulary = set(authentic)
    attempts = [
        stretch
        for stretch in stretches(base)
        if _attempt(stretch.words, vocabulary, len(authentic))
    ]
    given = [word for stretch in attempts for word in stretch.words]
    owner = [stretch for stretch in attempts for _word in stretch.words]
    lines = sorted({line for stretch in attempts for line in stretch.lines})
    empty = {"coverage": 0.0, "precision": 0.0, "words": len(authentic), "lines": lines}
    if not given or not authentic:
        return {"status": "missing", **empty}
    matcher = difflib.SequenceMatcher(
        None, authentic, [word.folded for word in given], autojunk=False
    )
    opcodes = matcher.get_opcodes()
    equal = [index for index, op in enumerate(opcodes) if op[0] == "equal"]
    if not equal:
        return {"status": "differs", **empty, "changed": []}
    changed: list[dict] = []
    for index, (tag, i1, i2, j1, j2) in enumerate(opcodes):
        if tag == "equal":
            changed += [
                {"kind": "vowels", "source": source[i].written, "given": given[j].written}
                for i, j in zip(range(i1, i2), range(j1, j2), strict=True)
                if _vowels_differ(source[i], given[j])
            ]
        elif tag == "replace":
            # Words put in place of the source's, inside the passage or at its edge.
            changed.append(
                {"kind": "changed", "source": _shown(source[i1:i2]), "given": _shown(given[j1:j2])}
            )
        elif equal[0] < index < equal[-1]:
            # A word dropped from inside the passage, or one added to it.
            kind = "dropped" if tag == "delete" else "added"
            changed.append(
                {"kind": kind, "source": _shown(source[i1:i2]), "given": _shown(given[j1:j2])}
            )
    first, last = opcodes[equal[0]], opcodes[equal[-1]]
    stop = last[2]  # the source's word after the last one given
    if not changed and stop < len(authentic) and stop not in ends:
        # The passage stops inside an ayah and the answer goes on in other
        # words on the same line: the rest is given in place of the ayah's.
        continuation = owner[last[4] - 1].continued
        if continuation and owner[last[4] - 1].words[-1] is given[last[4] - 1]:
            changed.append(
                {
                    "kind": "continued",
                    "source": _shown(source[stop:]),
                    "given": continuation[:120],
                }
            )
    replaced = [op for op in opcodes if op[0] == "replace"]
    start = min([first[3], *(op[3] for op in replaced)])
    finish = max([last[4], *(op[4] for op in replaced)])
    matched = sum(i2 - i1 for tag, i1, i2, _j1, _j2 in opcodes if tag == "equal")
    coverage = matched / len(authentic)
    precision = matched / max(1, finish - start)
    if not changed:
        status = "matches" if matched == len(authentic) else "excerpt"
    elif precision >= 0.85:
        status = "close"
    else:
        status = "differs"
    return {
        "status": status,
        "coverage": round(coverage, 3),
        "precision": round(precision, 3),
        "words": len(authentic),
        "matched": matched,
        "changed": changed[:5],
        "lines": lines,
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
