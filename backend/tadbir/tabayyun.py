"""Tabayyun (تبيّن): ask before guessing.

"If a report comes to you, verify it" (49:6) is read two ways: *fa-tathabbatu*
(make sure of it, Tathabbut, which checks a result) and *fa-tabayyanu* (make it
clear before acting on it). Tabayyun is the second: before an action a model
chose runs, MIZAN checks that what the action would touch is something the
person said, not a guess.

The rule (each part is a deterministic check; the model only proposes):

(a) Fahm read no decisive request for this action: no family of recipes was
    more probable than every other reading together (P > ½), the reading was
    the model's (Lisan's mapping), or the action is not one of the decisive
    family's own tools (a page was asked for, an email is being sent);
(b) the action changes something (``approvals.tool_category`` is not ``read``,
    with a connector's own read-only hint);
(c) a required argument holds a reference (an email address, a link, a
    handle, a phone number, a date or time, an id, a path, a number) that is
    not in the person's words in this chat, in MIZAN's earlier answers they
    read, in an answer they gave to Tabayyun, or in what this run's tools
    returned. Words the action writes (a message body, a program, a command)
    are not references and are never asked about.

When all three hold, MIZAN asks one question in an interactive chat (the
question card of ``connectors.elicitation``, answered through
``POST /api/chat/elicitations/{id}``); the answer joins the person's words for
this request and the model is told to try again with it. A run no one is
watching holds the action for its owner (``approvals.hold_action``); with no
one at all to ask, the model is told to ask in its answer. One question per
request; a read is never asked about. ``MIZAN_TABAYYUN`` = ask (default) | off
(``docs/tabayyun.md``).
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import unicodedata
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

MODES = ("ask", "off")
QUESTION_SECONDS = 300
# What this run's tools returned, kept for grounding (newest last).
SEEN_CHARS = 200_000
MAX_CALLS = 200


def mode() -> str:
    value = os.getenv("MIZAN_TABAYYUN", "ask").strip().lower()
    return value if value in MODES else "ask"


_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹०१२३४५६७८९", "0123456789" * 3)


def _norm(text: str) -> str:
    folded = unicodedata.normalize("NFKC", str(text or "")).casefold().translate(_DIGITS)
    return " ".join(folded.split())


@dataclass(eq=False)
class Inquiry:
    """One request's record: the person's words, what its tools returned and
    did, what Fahm read, and the one question asked."""

    task: str
    history: list[dict]
    words: str
    # What this request's tools returned when they worked: {"text", "raw", "clean"}.
    seen: list[dict] = field(default_factory=list)
    calls: list[dict] = field(default_factory=list)
    answers: list[str] = field(default_factory=list)
    understood: dict | None = None
    asked: dict | None = None
    # The id of the person's message this request answers, when the chat saved it.
    source: str = ""

    def own(self) -> str:
        """The person's words (with their answers) and the chat's own ids, normalized."""
        from workspace.context import bound_workspace_id, current_chat_session

        bound = " ".join(item for item in (bound_workspace_id(), current_chat_session()) if item)
        return "\n".join([self.words, *self.answers, _norm(bound)])


_run: ContextVar[Inquiry | None] = ContextVar("mizan_tabayyun", default=None)


def _chat_words(task: str, history: list[dict] | None) -> str:
    """The person's messages in this chat and MIZAN's answers they read."""
    said = [
        str(turn.get("content") or "")
        for turn in (history or [])
        if isinstance(turn, dict) and turn.get("role") in {"user", "assistant"}
    ]
    return _norm("\n".join([*said, task or ""]))


@contextmanager
def bind(task: str, history: list[dict] | None = None, source: str = "") -> Iterator[Inquiry]:
    """The record of one request. A delegated run inside it shares it: the
    person's words are the request's, whichever agent acts."""
    existing = _run.get()
    if existing is not None:
        yield existing
        return
    inquiry = Inquiry(
        str(task or ""),
        list(history or []),
        _chat_words(str(task or ""), history),
        source=str(source or "")[:100],
    )
    token = _run.set(inquiry)
    try:
        yield inquiry
    finally:
        _run.reset(token)


def current() -> Inquiry | None:
    return _run.get()


def observe(tool: str, params: Any, result: Any, category: str) -> None:
    """What a tool returned (a reference it shows is no guess) and what it did."""
    inquiry = _run.get()
    if inquiry is None:
        return
    from agents.execution_contract import tool_result_failed

    failed = tool_result_failed(result)
    if len(inquiry.calls) < MAX_CALLS:
        inquiry.calls.append(
            {
                "tool": tool,
                "category": category,
                "ok": not failed,
                "params": params if isinstance(params, dict) else {},
            }
        )
    if failed:
        # A refusal or an error often repeats the arguments it was given (Tabayyun's own
        # question names the guess): only what a tool returned when it worked is evidence.
        return
    try:
        text = json.dumps(result, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        text = str(result)
    raw = text[:20_000]
    inquiry.seen.append({"text": _norm(raw), "raw": raw, "clean": None})
    while sum(len(part["text"]) for part in inquiry.seen) > SEEN_CHARS and len(inquiry.seen) > 1:
        inquiry.seen.pop(0)


def _clean(entry: dict) -> bool:
    """A tool result is evidence only when Amanah finds no instruction to the AI in it
    (read once, when a reference would rest on it)."""
    if entry.get("clean") is None:
        from . import amanah

        entry["clean"] = not amanah.scan(str(entry.get("raw") or ""))
    return bool(entry["clean"])


# ── (c) references, and whether the person gave them ─────────────────────

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_URL = re.compile(r"https?://[^\s<>\"'`]+", re.IGNORECASE)
_DATE = re.compile(r"(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)")
_TIME = re.compile(r"(?<![\d:])\d{1,2}:\d{2}(?::\d{2})?(?![\d:])")
_PHONE = re.compile(r"(?<![\w+])\+?\d[\d ().-]{6,}\d(?!\w)")
_HANDLE = re.compile(r"(?<![\w@#/])[@#][^\W\d][\w.-]*")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_PLAIN_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_SLASHED = re.compile(r"[\w.-]+(?:/[\w.-]+)+")
_TRAILING = ".,;:!?)]}'\""


def particulars(value: Any) -> list[str]:
    """The references a value holds: what an action could get wrong by guessing.

    A number is one (an amount, an id, a count). In a one-line string: email
    addresses, links, dates, times, phone numbers and handles; and a value that
    is a single token with a digit or a slash (an id, ``owner/repo``). Text of
    more than one line is writing (a body, a program) and holds none."""
    if isinstance(value, bool) or value is None:
        return []
    if isinstance(value, int | float):
        return [_number_text(value)]
    if not isinstance(value, str):
        return []
    text = value.strip()
    if not text or "\n" in text:
        return []
    found: list[tuple[int, str]] = []
    working = text
    for pattern in (_URL, _EMAIL, _DATE, _TIME, _PHONE, _HANDLE):
        for match in pattern.finditer(working):
            piece = match.group().rstrip(_TRAILING)
            if piece:
                found.append((match.start(), piece))
            working = working[: match.start()] + " " * len(match.group()) + working[match.end() :]
    if (
        not found
        and " " not in text
        and (any(c.isdigit() for c in text) or _SLASHED.fullmatch(text))
    ):
        found.append((0, text))
    ordered: list[str] = []
    for _start, piece in sorted(found):
        if piece not in ordered:
            ordered.append(piece)
    return ordered


def _number_text(value: int | float) -> str:
    number = float(value)
    return str(int(number)) if number.is_integer() else repr(number)


def _numbers(text: str) -> set[float]:
    found: set[float] = set()
    for raw in _NUMBER.findall(text):
        for candidate in {raw.replace(",", ""), *re.split(r"[.,]", raw)}:
            try:
                found.add(float(candidate))
            except ValueError:
                continue
    return found


def _given(piece: str, grounded: str, numbers: set[float], digits: str) -> bool:
    """Whether a reference is in what the person said or MIZAN saw."""
    norm = _norm(piece)
    if _PLAIN_NUMBER.fullmatch(norm):
        return float(norm) in numbers
    if norm in grounded:
        return True
    if _URL.fullmatch(norm):
        bare = re.sub(r"^https?://(www\.)?", "", norm).rstrip("/")
        return bool(bare) and bare in grounded
    if norm[:1] in "@#" and len(norm) > 2:
        return re.search(rf"(?<!\w){re.escape(norm[1:])}(?!\w)", grounded) is not None
    phone = re.sub(r"\D", "", norm)
    if _PHONE.fullmatch(norm) and len(phone) >= 7:
        return phone in digits
    return False


class _Haystack:
    """One text references are looked for in, with its numbers and digits read once."""

    def __init__(self, text: str):
        self.text = text
        self.numbers = _numbers(text)
        self.digits = re.sub(r"\D", "", text)

    def has(self, piece: str) -> bool:
        return _given(piece, self.text, self.numbers, self.digits)


def _required(schema: dict | None) -> tuple[list[str], dict]:
    if not isinstance(schema, dict):
        return [], {}
    body = schema.get("input_schema") or schema.get("inputSchema") or schema.get("parameters")
    if not isinstance(body, dict):
        return [], {}
    required = body.get("required")
    properties = body.get("properties")
    names = [str(name) for name in required] if isinstance(required, list) else []
    return names, properties if isinstance(properties, dict) else {}


def _leaves(value: Any) -> Iterator[Any]:
    if isinstance(value, dict):
        for item in value.values():
            yield from _leaves(item)
    elif isinstance(value, list | tuple):
        for item in value:
            yield from _leaves(item)
    else:
        yield value


def ungrounded(params: Any, schema: dict | None, inquiry: Inquiry) -> list[tuple[str, Any]]:
    """The required arguments holding a reference nobody gave: (name, value)."""
    if not isinstance(params, dict):
        return []
    required, properties = _required(schema)
    if not required:
        return []
    own = _Haystack(inquiry.own())

    def given(piece: str) -> bool:
        if own.has(piece):
            return True
        for entry in inquiry.seen:
            found = entry.get("hay") or entry.setdefault("hay", _Haystack(entry["text"]))
            if found.has(piece) and _clean(entry):
                return True
        return False

    missing: list[tuple[str, Any]] = []
    for name in required:
        if name not in params:
            continue  # the tool's own check reports a missing argument
        value = params[name]
        offered = (properties.get(name) or {}).get("enum")
        if isinstance(offered, list) and value in offered:
            continue  # one of the tool's own choices
        pieces = [piece for leaf in _leaves(value) for piece in particulars(leaf)]
        if any(not given(piece) for piece in pieces):
            missing.append((name, value))
    return missing


# ── (a) a decisive reading that covers the action ────────────────────────

# The tools each family of MIZAN's recipes works with: a decisive reading of
# that family covers them, and only them.
FAMILY_TOOLS: dict[str, tuple[str, ...]] = {
    "make": ("workspace_",),
    "code": ("workspace_", "python_exec", "bash"),
    "workspace_agent": ("workspace_",),
    "page": ("shahid_", "web_"),
    "search": ("web_",),
    "hf_hub": ("hf_",),
}
_UNDECIDED = {"use_tool", "compound", "sarf", "salam", "converse"}


def decisive(understood: dict | None, tool_name: str) -> bool:
    """Fahm (not the model) read the request decisively (P > ½) as a kind of
    work that this tool belongs to."""
    if not isinstance(understood, dict):
        return False
    from . import fahm

    intent = str(understood.get("intent") or "")
    if intent in _UNDECIDED or intent in fahm._WORDS_ONLY:
        return False
    if understood.get("by") == "lisan":
        return False
    try:
        confidence = float(understood.get("confidence") or 0.0)
    except (TypeError, ValueError):
        return False
    if confidence <= 0.5:
        return False
    family = fahm._FAMILY.get(intent, intent)
    return tool_name.startswith(FAMILY_TOOLS.get(family, ())) if FAMILY_TOOLS.get(family) else False


async def _read(inquiry: Inquiry) -> dict | None:
    """Fahm's reading of the request when no orchestration read it (``llm`` mode)."""
    if inquiry.understood is not None:
        return inquiry.understood
    from . import fahm

    try:
        found = await asyncio.to_thread(fahm.understand, inquiry.task, inquiry.history)
    except Exception:  # noqa: BLE001 - no reading is no decisive reading
        inquiry.understood = {"intent": "converse", "confidence": 0.0, "by": "fahm"}
        return inquiry.understood
    inquiry.understood = {
        "intent": found.intent,
        "language": found.language,
        "confidence": found.confidence,
        "by": found.entities.get("understood_by", "fahm"),
    }
    return inquiry.understood


# ── the question ─────────────────────────────────────────────────────────

# The guess is named, never filled in: the person types the value, or the right one.
PHRASES = {
    "en": "Before {tool} runs: which {label} do you mean? You have not said it. Did you mean "
    "“{value}”? Type it to confirm, or write the right one.",
    "hi-latn": "{tool} chalane se pehle: kaunsa {label}? Aap ne yeh nahi bataya. Kya aap ka "
    "matlab “{value}” hai? Tasdeeq ke liye likhiye, ya sahi likhiye.",
    "ur": "{tool} چلانے سے پہلے: کون سا {label}؟ آپ نے یہ نہیں بتایا۔ کیا آپ کا مطلب “{value}” ہے؟ "
    "تصدیق کے لیے لکھیے، یا درست لکھیے۔",
    "hi": "{tool} चलाने से पहले: कौन सा {label}? आपने यह नहीं बताया। क्या आपका मतलब “{value}” "
    "है? पुष्टि के लिए लिखिए, या सही लिखिए।",
    "ar": "قبل تشغيل {tool}: أيّ {label} تقصد؟ لم تذكره. هل تقصد «{value}»؟ اكتبه للتأكيد، أو "
    "اكتب الصحيح.",
}


def question(tool: str, argument: str, value: Any, language: str = "en") -> str:
    shown = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    template = PHRASES.get(language, PHRASES["en"])
    return template.format(tool=tool, label=argument.replace("_", " "), value=str(shown)[:200])


def _schema_of(agent: Any, tool_name: str) -> dict | None:
    try:
        schemas = agent.get_tool_schemas()
    except Exception:  # noqa: BLE001 - no schema: no required argument to read
        return None
    return next(
        (s for s in schemas or [] if isinstance(s, dict) and s.get("name") == tool_name), None
    )


async def _ask(approvals: Any, record: dict) -> tuple[str, str]:
    """The question card; returns (outcome, the person's answer)."""
    from agents.events import emit
    from connectors import elicitation

    # No default: the model's guess is named in the question, never prefilled, so an
    # empty Send is no yes; the person types the value themselves.
    schema = {
        "type": "object",
        "properties": {
            "answer": {
                "type": "string",
                "title": record["argument"].replace("_", " "),
                "description": "Your answer is read as your own words in this request.",
                "minLength": 1,
                "maxLength": 500,
            }
        },
        "required": ["answer"],
    }
    asked_id, future = elicitation.broker.open(approvals.user_id, approvals.session_id, "MIZAN")
    try:
        await emit(
            "elicitation",
            {
                "id": asked_id,
                "kind": "question",
                "server": "MIZAN",
                "tool": record["tool"],
                "argument": record["argument"],
                "message": record["question"],
                "schema": schema,
                "expires_in": QUESTION_SECONDS,
            },
        )
        try:
            reply = await asyncio.wait_for(future, timeout=QUESTION_SECONDS)
        except TimeoutError:
            reply = {"action": "cancel", "content": {}}
        except asyncio.CancelledError:
            if not future.cancelled():
                raise
            reply = {"action": "cancel", "content": {}}
        await emit("elicitation_resolved", {"id": asked_id, "action": reply.get("action")})
    finally:
        elicitation.broker.close(asked_id)
    content = reply.get("content") if isinstance(reply.get("content"), dict) else {}
    answer = " ".join(str((content or {}).get("answer") or "").split())[:500]
    if reply.get("action") != "accept" or not answer:
        return "declined", ""
    return "answered", answer


async def before_action(
    agent: Any, tool_name: str, params: dict, approvals: Any, *, read_only: bool = False
) -> dict | None:
    """None when the action may go on; otherwise the result the model sees
    (a question answered, declined, a held action, or "ask in your answer")."""
    if mode() == "off":
        return None
    inquiry = _run.get()
    if inquiry is None:
        return None  # no request to read the action against
    from security.approvals import tool_category

    if tool_category(tool_name, read_only, params) == "read":
        return None
    if approvals is not None and (
        approvals.blocks(tool_name, read_only, params) or approvals.was_granted(tool_name, params)
    ):
        return None  # plan mode refuses it anyway; a held action its owner allowed runs as held
    # (c) first: most actions name what the person said, and then Fahm need not read.
    missing = ungrounded(params, _schema_of(agent, tool_name), inquiry)
    if not missing:
        return None
    understood = getattr(agent, "_understood", None) or await _read(inquiry)
    if decisive(understood, tool_name):
        return None
    argument, value = missing[0]
    language = str((understood or {}).get("language") or "en")
    record = {
        "tool": tool_name,
        "argument": argument,
        "question": question(tool_name, argument, value, language),
    }
    if approvals is not None and approvals.deferred:
        from security.approvals import hold_action

        inquiry.asked = inquiry.asked or {**record, "outcome": "held"}
        held_id = hold_action(approvals, tool_name, params, f"Tabayyun: {record['question']}")
        return {
            "error": "Held for the owner: MIZAN would have asked first, and no one is watching "
            "this run",
            "held_for_approval": held_id,
            "tabayyun": record,
        }
    if inquiry.asked is not None:
        return {
            "error": f"Not run: “{argument}” is still not in the person's words, and MIZAN asks "
            "one question per request. Ask them in your answer instead of guessing.",
            "tabayyun": record,
        }
    from agents.events import has_event_sink

    if approvals is None or not approvals.interactive or not has_event_sink():
        inquiry.asked = {**record, "outcome": "unasked"}
        return {
            "error": f"Not run: MIZAN would ask the person first ({record['question']}) and no "
            "one can answer here. Ask them in your answer instead of guessing.",
            "tabayyun": record,
        }
    outcome, answer = await _ask(approvals, record)
    inquiry.asked = {**record, "outcome": outcome}
    if outcome != "answered":
        return {
            "error": f"The person did not answer MIZAN's question, so {tool_name} did not run. "
            f"Do not guess the {argument.replace('_', ' ')}.",
            "declined": True,
            "tabayyun": record,
        }
    inquiry.answers.append(_norm(answer))
    return {
        "error": f"Not run yet: MIZAN asked the person first. {record['question']} Their "
        f"answer, in their own words: “{answer}”. Call {tool_name} again using it.",
        "clarified": {"question": record["question"], "argument": argument, "answer": answer},
    }


def summary(inquiry: Inquiry | None) -> dict | None:
    """What Tabayyun did in this request, for ``usage.tabayyun`` (no answer text)."""
    if inquiry is None or inquiry.asked is None:
        return None
    asked = inquiry.asked
    return {
        "asked": 1,
        "tool": asked["tool"],
        "argument": asked["argument"],
        "outcome": asked["outcome"],
    }
