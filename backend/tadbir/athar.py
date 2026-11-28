"""Athar (أثر): MIZAN retraces the steps of a run it verified, with no model call.

"So they went back, retracing their footsteps" (18:64). Hifz re-runs one kept
program; Athar extends it to the multi-step tool trace of a repeated request (a
watcher's task, the same question about other numbers), porting ForgeKit's
replay/engine.js and mathcore/sequential.js:

- **Every argument has a known source.** The verified traces of one form are a
  family (the same tools in order, requests that differ only in numbers and
  spans of other words, read as Hifz templates read them). Each argument is a
  constant all of them used, the request's j-th number (plus an offset all
  agree on), a span of its own words, or a text that holds those; any other
  argument has no source and nothing is replayed. With one distinct request
  seen, only that exact request is replayed (nothing to generalise from).
- **Evidence clears a cost-derived bar.** Replaying a step pays when the chance
  p it is right exceeds q* = (L_wrong + c_cheap)/(L_wrong + c_fallback): in
  units of one normal run (c_fallback = 1), a replay costs c_cheap = 0.02 and a
  wrong step L_wrong = 4 (a read) or 20 (a checkpointed project write), so
  q* = 0.804 or 0.953. MIZAN replays only while an anytime-valid lower bound on
  p (``core.adaptive.anytime_lower``, α = 0.05, safe to read after every run)
  is at least the strictest step's q*. Evidence comes from the next verified
  run of the same form, test then train: MIZAN first predicts its steps, counts
  whether the run did exactly that, then learns from it.
- **An irreversible step is never replayed** (sending, paying, deleting, any
  tool that is not read-only or a checkpointed edit, a connector tool without
  a read-only hint): the trace stops there, and as nothing after it may run,
  none of it runs and the agent does the request normally.
- **Each replay is a regression check**: a step that fails, or a replayed answer
  the person corrects or undoes, drops the family.

``MIZAN_REPLAY`` = on (default) | off; off in tests unless a test turns it on.
Kept per person; stateless runs and learning off neither learn nor replay.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

KEY = "athar"
ALPHA = 0.05
COST_FALLBACK = 1.0  # a normal run: the unit
COST_REPLAY = 0.02
LOSS = {"read": 4.0, "write": 20.0}
MIN_SUPPORT = 2  # distinct requests before a family generalises
MAX_EXAMPLES = 8
MAX_FAMILIES = 50
MAX_STEPS = 12
MAX_TRACE_BYTES = 16_000
SHOWN_PER_STEP = 1500


def enabled() -> bool:
    return os.getenv("MIZAN_REPLAY", "on").strip().lower() not in {"off", "0", "false", "no"}


def threshold(effect: str) -> float:
    """The smallest chance of being right at which replaying this step pays."""
    if effect not in LOSS:
        return float("inf")  # irreversible: the person's authority, not an optimisation
    loss = LOSS[effect]
    return (loss + COST_REPLAY) / (loss + COST_FALLBACK)


def effect(tool: str, params: dict | None = None, owner: str = "") -> str:
    """read | write (a checkpointed project edit or the sandbox) | irreversible."""
    from security.approvals import SANDBOXED_TOOLS, tool_category

    hint = False
    if tool.startswith("mcp__"):
        try:
            from connectors.tools import read_only_hint

            hint = bool(read_only_hint(owner, tool))
        except Exception:  # noqa: BLE001 - an unreadable hint is not read-only
            hint = False
    category = tool_category(tool, hint, params)
    if category == "read":
        return "read"
    if category == "edit" or tool in SANDBOXED_TOOLS:
        return "write"
    return "irreversible"


# ── the run's own trace ──────────────────────────────────────────────────


@dataclass
class RunTrace:
    steps: list[dict] = field(default_factory=list)
    replay: str = ""  # the family this run replayed, if it did
    shown: list[str] = field(default_factory=list)  # Islah lessons the run was shown


_RUN: ContextVar[RunTrace | None] = ContextVar("mizan_athar_run", default=None)


@contextmanager
def bind() -> Iterator[RunTrace]:
    """Record every tool call of one top-level run (delegated runs included)."""
    run = RunTrace()
    token = _RUN.set(run)
    try:
        yield run
    finally:
        _RUN.reset(token)


def current() -> RunTrace | None:
    return _RUN.get()


def note(tool: str, params: Any, result: Any, receipt: dict | None) -> None:
    """One tool call of this run, as its Sakk receipt saw it."""
    run = _RUN.get()
    if run is None or len(run.steps) >= 50:
        return
    from agents.execution_contract import tool_result_failed
    from security import sakk

    state = sakk.outcome(result)
    params = dict(params) if isinstance(params, dict) else {}
    run.steps.append(
        {
            "tool": str(tool),
            "params": params,
            "outcome": state if not (state == "done" and tool_result_failed(result)) else "error",
            "receipt": str((receipt or {}).get("hash") or ""),
            "path": str(params.get("path") or "") if isinstance(params.get("path"), str) else "",
        }
    )


# ── reading a request against a family (Hifz's anti-unification) ─────────


def _request_key(text: str) -> tuple:
    from tadbir import hifz

    return tuple((key, text[start:end]) for key, start, end in hifz._tokens(text))


def _read(family: dict, request: str) -> dict | None:
    """The request's numbers and spans against the family's examples, when it
    has the family's form: the same words apart from numbers and spans."""
    from tadbir import hifz

    examples = family.get("examples") or []
    if not examples:
        return None
    mine = hifz._tokens(request)
    keys = [key for key, _s, _e in mine]
    numbers = hifz._ordered(request)
    rows = []
    for example in examples:
        theirs = hifz._tokens(example["request"])
        if len(hifz._ordered(example["request"])) != len(numbers):
            return None
        where = hifz._shared(keys, [key for key, _s, _e in theirs])
        if where is None:
            return None
        rows.append((example, theirs, where))
    frame = frozenset.intersection(*(frozenset(where) for _e, _t, where in rows))
    gaps = hifz._gaps(len(mine), frame)
    identity = {i: i for i in range(len(mine))}
    spans = [text for text, _n in hifz._spans(request, mine, gaps, identity, len(mine))]
    found = [
        {
            "numbers": hifz._ordered(example["request"]),
            "spans": [
                text for text, _n in hifz._spans(example["request"], theirs, gaps, where, len(mine))
            ],
        }
        for example, theirs, where in rows
    ]
    return {"numbers": numbers, "spans": spans, "examples": found}


def _leaves(value: Any, path: tuple = ()) -> Iterator[tuple[tuple, Any]]:
    if isinstance(value, dict):
        for key in sorted(value):
            yield from _leaves(value[key], (*path, key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _leaves(item, (*path, index))
    else:
        yield path, value


def _shape(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _shape(item) for key, item in sorted(value.items())}
    if isinstance(value, list):
        return [_shape(item) for item in value]
    return None


def _set(target: Any, path: tuple, value: Any) -> None:
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value


def _source(values: list[Any], read: dict, request: str, requests: list[str]) -> Any:
    """Where one argument comes from: ("const", v) | ("number", j, b) | ("words",
    parts) | ("text", pieces, inner) (Hifz's slots); None when it has no known source."""
    from tadbir import hifz

    first = values[0]
    if all(json.dumps(v, sort_keys=True) == json.dumps(first, sort_keys=True) for v in values):
        if isinstance(first, str) and requests:
            # A word every earlier request said and this one does not: written for
            # their word, not this one's (Hifz's ``_unsaid``).
            said = set.intersection(*(hifz._said(text) for text in requests))
            if (hifz._said(first) & said) - hifz._said(request):
                return None
        return ("const", first)
    numbers = [example["numbers"] for example in read["examples"]]
    if all(isinstance(v, int | float) and not isinstance(v, bool) for v in values):
        slot = hifz._number_slot(values, numbers)
        return ("number", slot[0], slot[1]) if slot is not None else None
    if not all(isinstance(v, str) for v in values):
        return None
    spans = [dict(enumerate(example["spans"])) for example in read["examples"]]
    if any(spans):
        made = hifz._words_slot(values, numbers, spans)
        if made is not None:
            return made
    if numbers and numbers[0]:
        made = hifz._text_slot(values, numbers)
        if made is not None:
            return made
    return None


def _fill(slot: Any, read: dict) -> Any:
    from tadbir import hifz

    if slot[0] == "const":
        return slot[1]
    if slot[0] == "number":
        number = read["numbers"][slot[1]]
        return hifz._value(number) + slot[2]
    if slot[0] == "words":
        return "".join(
            read["numbers"][value]
            if kind == "number"
            else read["spans"][value]
            if kind == "word"
            else value
            for kind, value in slot[1]
        )
    _kind, pieces, inner = slot
    text = pieces[0]
    for index, part in enumerate(inner):
        text += (read["numbers"][part] if isinstance(part, int) else part) + pieces[index + 1]
    return text


def plan(family: dict, request: str) -> tuple[list[dict] | None, str]:
    """The steps this request's run would take, or why it cannot be told."""
    examples = family.get("examples") or []
    distinct = {_request_key(example["request"]) for example in examples}
    if len(distinct) < MIN_SUPPORT:
        exact = [e for e in examples if _request_key(e["request"]) == _request_key(request)]
        if not exact:
            if _read(family, request) is None:
                return None, "other_form"
            return None, "seen_too_rarely_to_generalise"
        return [{"tool": s["tool"], "params": s["params"]} for s in exact[-1]["steps"]], ""
    read = _read(family, request)
    if read is None:
        return None, "other_form"
    requests = [example["request"] for example in examples]
    steps = []
    for index, tool in enumerate(family["tools"]):
        all_params = [example["steps"][index]["params"] for example in examples]
        shapes = {json.dumps(_shape(params), sort_keys=True) for params in all_params}
        if len(shapes) != 1:
            return None, "argument_without_source"
        made = json.loads(json.dumps(all_params[-1]))
        for path, _value in _leaves(all_params[0]):
            values = [dict_at(params, path) for params in all_params]
            slot = _source(values, read, request, requests)
            if slot is None:
                return None, "argument_without_source"
            if path:
                _set(made, path, _fill(slot, read))
            else:
                made = _fill(slot, read)
        steps.append({"tool": tool, "params": made})
    return steps, ""


def dict_at(value: Any, path: tuple) -> Any:
    for key in path:
        value = value[key]
    return value


# ── the family store ─────────────────────────────────────────────────────


def _load(store: Any) -> list[dict]:
    try:
        data = store.get(KEY) or {}
    except Exception:  # noqa: BLE001 - nothing learned yet
        data = {}
    return [family for family in data.get("families", []) if isinstance(family, dict)]


def _save(store: Any, families: list[dict]) -> None:
    families = sorted(families, key=lambda f: -float(f.get("used", 0)))[:MAX_FAMILIES]
    try:
        store.put(KEY, {"families": families})
    except Exception:  # noqa: BLE001 - learning is best effort
        pass


def _canonical(steps: list[dict]) -> str:
    return json.dumps(
        [{"tool": s["tool"], "params": s.get("params") or {}} for s in steps], sort_keys=True
    )


_SENSITIVE_KEY = re.compile(r"(?i)authori[sz]ation|token|secret|password|passwd|api[_-]?key|cookie")


def _sensitive(steps: list[dict]) -> bool:
    """An argument that is, or looks like, a credential: such a trace is never kept
    (Sakk keeps only keyed digests of arguments; the replay store must not keep more)."""
    from tadbir.martaba import _SECRET

    for step in steps:
        for path, value in _leaves(step.get("params") or {}):
            if any(isinstance(key, str) and _SENSITIVE_KEY.search(key) for key in path):
                return True
            if isinstance(value, str) and _SECRET.search(value):
                return True
    return False


def learn(
    store: Any,
    request: str,
    steps: list[dict],
    *,
    intent: str = "",
    chat: str = "",
    now: float | None = None,
) -> dict | None:
    """One verified run: first test the family's prediction for it, then learn from it."""
    if not steps or len(steps) > MAX_STEPS or any(s.get("outcome") != "done" for s in steps):
        return None
    kept = [{"tool": s["tool"], "params": s.get("params") or {}} for s in steps]
    if _sensitive(kept):
        return None
    try:
        if len(json.dumps(kept)) > MAX_TRACE_BYTES:
            return None
    except (TypeError, ValueError):
        return None  # arguments that are not plain data cannot be replayed
    now = time.time() if now is None else now
    tools = [s["tool"] for s in kept]
    families = _load(store)
    example = {"request": request[:500], "steps": kept, "chat": chat, "at": now}
    for family in families:
        if family.get("tools") != tools:
            continue
        predicted, why = plan(family, request)
        if predicted is not None:
            agreed = _canonical(predicted) == _canonical(kept)
            family["s" if agreed else "f"] = int(family.get("s" if agreed else "f", 0)) + 1
        elif why == "other_form":
            continue
        family["examples"] = [*family["examples"], example][-MAX_EXAMPLES:]
        family["used"] = now
        _save(store, families)
        return {"family": family["id"], "tested": predicted is not None}
    family = {
        "id": "f" + hashlib.sha256(f"{tools}|{request}|{now}".encode()).hexdigest()[:12],
        "intent": intent,
        "tools": tools,
        "examples": [example],
        "s": 0,
        "f": 0,
        "replayed": 0,
        "used": now,
    }
    families.append(family)
    _save(store, families)
    return {"family": family["id"], "tested": False}


def decide(store: Any, request: str, owner: str = "") -> dict:
    """Whether this request may be replayed now: the plan, or why not."""
    from core.adaptive import anytime_lower

    best: dict = {"replay": False, "reason": "no_family"}
    for family in _load(store):
        steps, why = plan(family, request)
        if steps is None:
            if why != "other_form" and best["reason"] == "no_family":
                best = {"replay": False, "reason": why, "family": family["id"]}
            continue
        effects = [effect(step["tool"], step["params"], owner) for step in steps]
        bar = max(threshold(kind) for kind in effects)
        lower = anytime_lower(int(family.get("s", 0)), int(family.get("f", 0)), ALPHA)
        found = {
            "family": family["id"],
            "intent": family.get("intent", ""),
            "steps": steps,
            "effects": effects,
            "threshold": round(bar, 4) if bar != float("inf") else None,
            "lower_bound": round(lower, 4),
            "evidence": {"agreed": family.get("s", 0), "disagreed": family.get("f", 0)},
        }
        if "irreversible" in effects:
            stop = effects.index("irreversible")
            return {**found, "replay": False, "reason": "irreversible_step", "stops_at": stop}
        if lower < bar:
            return {**found, "replay": False, "reason": "not_enough_evidence"}
        return {**found, "replay": True, "reason": ""}
    return best


def drop(store: Any, family_id: str) -> bool:
    """A failed replay: the family's evidence and examples are void."""
    families = _load(store)
    kept = [family for family in families if family.get("id") != family_id]
    if len(kept) != len(families):
        _save(store, kept)
        return True
    return False


def replayed(store: Any, family_id: str, now: float | None = None) -> None:
    families = _load(store)
    for family in families:
        if family.get("id") == family_id:
            family["replayed"] = int(family.get("replayed", 0)) + 1
            family["used"] = time.time() if now is None else now
    _save(store, families)


def _shown(result: Any) -> str:
    if isinstance(result, dict):
        for key in (
            "output",
            "stdout",
            "text",
            "content",
            "result",
            "results",
            "answer",
            "summary",
        ):
            if result.get(key):
                value = result[key]
                text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
                return text[:SHOWN_PER_STEP]
    text = (
        result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
    )
    return str(text)[:SHOWN_PER_STEP]


def render(steps: list[dict], results: list[Any]) -> str:
    parts = [
        "MIZAN repeated the steps of a run it verified before for this request, with no "
        "model call (Athar). What each step returned:"
    ]
    for index, (step, result) in enumerate(zip(steps, results, strict=True), start=1):
        parts.append(f"{index}. `{step['tool']}`\n{_shown(result)}")
    return "\n\n".join(parts)


async def replay(agent: Any, task: str, stream_callback: Any = None) -> dict | None:
    """Answer a repeated request from a verified trace, or None (the agent runs)."""
    from memory import stateless
    from security.auth import current_user_id
    from tadbir import khatimah, trace

    if not enabled() or stateless.active() or not stateless.learns() or not isinstance(task, str):
        return None
    owner = current_user_id() or ""
    if not owner:
        return None
    store = khatimah.store(owner)
    found = decide(store, task, owner)
    if not found.get("replay"):
        if found.get("family"):
            trace.event("plan", "athar", replay=False, reason=found.get("reason"))
        return None
    from agents.execution_contract import tool_result_failed

    started = time.time()
    results = []
    for step in found["steps"]:
        result = await agent._execute_tool_safe(step["tool"], step["params"])
        if tool_result_failed(result) or (isinstance(result, dict) and result.get("declined")):
            drop(store, found["family"])
            trace.event("learn", "athar", dropped=found["family"], at=step["tool"])
            return None
        results.append(result)
    replayed(store, found["family"])
    run = current()
    if run is not None:
        run.replay = found["family"]
    text = render(found["steps"], results)
    if stream_callback is not None:
        try:
            await stream_callback(text)
        except Exception:  # noqa: BLE001 - the answer is still returned
            pass
    trace.event("plan", "athar", replay=True, family=found["family"], steps=len(results))
    return {
        "success": True,
        "result": text,
        "duration_ms": (time.time() - started) * 1000,
        "agent": getattr(agent, "name", ""),
        "metrics_kind": "mizan_orchestration",
        # The steps ran and returned; the answer itself is not re-verified.
        "completion_status": "evidence_observed",
        "answer_delivered": True,
        "task_verified": False,
        "capture_eligible": False,
        "orchestrator": "mizan",
        "replay": {
            "family": found["family"],
            "steps": len(results),
            "lower_bound": found["lower_bound"],
            "threshold": found["threshold"],
            "evidence": found["evidence"],
        },
        "orchestration": {
            "by": "mizan",
            "mode": "replay",
            "intent": found.get("intent", ""),
            "plan": [step["tool"] for step in found["steps"]],
            "verified": False,
            "language_model_calls": 0,
            "agents": [],
        },
    }


def summary(store: Any) -> dict:
    from core.adaptive import anytime_lower

    return {
        "families": [
            {
                "intent": family.get("intent", ""),
                "tools": family.get("tools", []),
                "requests": len({_request_key(e["request"]) for e in family.get("examples", [])}),
                "agreed": family.get("s", 0),
                "disagreed": family.get("f", 0),
                "lower_bound": round(
                    anytime_lower(int(family.get("s", 0)), int(family.get("f", 0)), ALPHA), 4
                ),
                "replayed": family.get("replayed", 0),
            }
            for family in _load(store)[:30]
        ],
        "thresholds": {kind: round(threshold(kind), 4) for kind in LOSS},
        "enabled": enabled(),
    }


def forget_chat(store: Any, chat: str) -> int:
    """Mahw: the erased chat's runs leave every family; a family with none left goes."""
    if not chat:
        return 0
    families = _load(store)
    removed = 0
    kept = []
    for family in families:
        examples = [e for e in family.get("examples", []) if e.get("chat") != chat]
        removed += len(family.get("examples", [])) - len(examples)
        if examples:
            # What its evidence was measured on included the erased runs.
            if len(examples) != len(family.get("examples", [])):
                family = {**family, "examples": examples, "s": 0, "f": 0}
            kept.append(family)
    if removed:
        _save(store, kept)
    return removed
