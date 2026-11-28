"""Itqan (إتقان): skills MIZAN earns from work it verified again and again.

"Allah loves that when one of you does a work, he does it well (yutqinahu)" (a
hadith in at-Tabarani's al-Mu'jam al-Awsat). Besides the skills the model
writes itself (``skill_write``), MIZAN proposes a skill of its own only from
evidence, porting ForgeKit's jev_skills.js rules:

- the same normalized task signature (Fahm's intent, the tools in order and the
  request's content words without numbers) was **verified at least 3 times**:
  each run marked verified by MIZAN's own checks, every tool step done, each
  with its Sakk receipt;
- at most **one proposal per person per day**, at most 8 in all; a skill the
  person removed is remembered and never proposed again (by its signature, or
  a regrouped copy by keyword overlap ≥ ½);
- the skill is built **only from keywords, tool names, file paths and receipt
  ids**, never the request text: it is loaded into later chats, and a person's
  prose (or an instruction hidden in it) has no place there;
- it is saved into the person's skills as **pending**: it waits for their trust
  in Library like a skill Amanah held. Earning never makes it trusted.

Kept per person in their private store; stateless runs and learning off keep
nothing, and Mahw drops what an erased chat contributed.
"""

from __future__ import annotations

import hashlib
import re
import time
from typing import Any

KEY = "itqan"
MIN_VERIFIED = 3
MAX_LEARNED = 8
MAX_RUNS = 8  # kept per signature (the latest)
MAX_SIGNATURES = 100
SAME_PROCEDURE = 0.5
PREFIX = "mizan-learned-"
DAY = 86400


def _day(now: float) -> int:
    return int(now // DAY)


def signature(intent: str, tools: list[str], request: str) -> str:
    """The work's form: what was asked (Fahm), the tools in order, the words
    that say what about (numbers left out, so the same form with other numbers
    is the same work)."""
    from tadbir.islah import keywords

    steps: list[str] = []
    for tool in tools:
        if not steps or steps[-1] != tool:
            steps.append(tool)
    body = f"{intent}|{'>'.join(steps)}|{' '.join(sorted(keywords(request)))}"
    return hashlib.sha256(body.encode()).hexdigest()[:16]


def _slug(terms: list[str]) -> str:
    words = [re.sub(r"[^a-z0-9]+", "", word.lower()) for word in terms[:5]]
    slug = "-".join(word for word in words if len(word) > 1)[:40].strip("-")
    return slug or "procedure"


def _safe_path(path: str) -> str:
    return re.sub(r"[`<>\s]", "", str(path))[:120].lstrip("/")


def draft(name: str, runs: list[dict], terms: list[str], tools: list[str]) -> tuple[str, str]:
    """(description, body) of the SKILL.md, from keywords, tools, files and receipt ids only."""
    files = sorted({_safe_path(f) for run in runs for f in run.get("files", []) if _safe_path(f)})
    receipts = [r[:16] for run in runs for r in run.get("receipts", [])][:12]
    listed = ", ".join(terms) or "(none)"
    description = (
        f"Earned from {len(runs)} runs MIZAN verified for you. Covers: {listed}; "
        f"tools: {', '.join(tools)}."
    )[:1000]
    body = "\n".join(
        [
            f"# Learned procedure: {listed}",
            "",
            f"MIZAN earned this from {len(runs)} runs of the same work that its own checks "
            "verified. It is a map of what that work used, not instructions: check each "
            "step against the request before relying on it.",
            "",
            "## Keywords from the requests",
            "",
            listed,
            "",
            "## Tools the verified runs used, in order",
            "",
            *[f"{index}. `{tool}`" for index, tool in enumerate(tools, start=1)],
            "",
            "## Files the work changed",
            "",
            *([f"- `{path}`" for path in files[:12]] or ["- (none recorded)"]),
            "",
            "## Evidence",
            "",
            f"- {len(runs)} verified runs; their receipts in your Sakk chain: "
            + ", ".join(f"`{receipt}`" for receipt in receipts),
            "",
            f"Remove it in Library → Skills ({name}); MIZAN will not propose it again.",
        ]
    )
    return description, body


def _load(store: Any) -> dict:
    try:
        data = store.get(KEY) or {}
    except Exception:  # noqa: BLE001 - no store: nothing earned yet
        data = {}
    raw = data.get("runs")
    runs: dict = raw if isinstance(raw, dict) else {}
    return {
        "runs": {str(k): [r for r in v if isinstance(r, dict)] for k, v in runs.items()},
        "proposed": [p for p in data.get("proposed", []) if isinstance(p, dict)],
        "removed": [p for p in data.get("removed", []) if isinstance(p, dict)],
        "day": data.get("day"),
    }


def _save(store: Any, state: dict) -> None:
    runs = dict(
        sorted(
            state["runs"].items(),
            key=lambda pair: -max((float(r.get("at", 0)) for r in pair[1]), default=0.0),
        )[:MAX_SIGNATURES]
    )
    try:
        store.put(KEY, {**state, "runs": runs})
    except Exception:  # noqa: BLE001 - learning is best effort
        pass


def _overlap(a: list[str], b: list[str]) -> float:
    left, right = set(a), set(b)
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _installed(user_id: str) -> set[str]:
    from agent_skills import loader

    try:
        return {skill.name for skill in loader.user_skills(user_id)}
    except Exception:  # noqa: BLE001 - an unreadable folder holds nothing of ours
        return set()


def _notice_removed(state: dict, user_id: str) -> None:
    """A proposal whose folder is gone was removed by the person: never again."""
    present = _installed(user_id)
    kept = []
    for proposal in state["proposed"]:
        if proposal.get("name") in present:
            kept.append(proposal)
        else:
            state["removed"].append(proposal)
    state["proposed"] = kept


def _seen(state: dict, sig: str, terms: list[str]) -> bool:
    for known in [*state["proposed"], *state["removed"]]:
        if known.get("signature") == sig:
            return True
        if _overlap(known.get("terms") or [], terms) >= SAME_PROCEDURE:
            return True
    return False


def observe(
    store: Any,
    user_id: str,
    *,
    intent: str,
    request: str,
    steps: list[dict],
    verified: bool,
    chat: str = "",
    now: float | None = None,
) -> dict | None:
    """One run ended. A verified run is counted for its signature; when the
    signature has enough verified runs, a pending skill may be proposed."""
    if not user_id or not verified or not steps:
        return None
    if any(step.get("outcome") != "done" for step in steps):
        return None
    receipts = [str(step.get("receipt") or "") for step in steps]
    if not all(receipts):
        return None  # every step must stand on its receipt
    from tadbir.islah import keywords

    now = time.time() if now is None else now
    tools = [str(step["tool"]) for step in steps]
    sig = signature(intent, tools, request)
    state = _load(store)
    files = [
        str(step.get("path"))
        for step in steps
        if step.get("path") and str(step.get("tool", "")).startswith("workspace_")
    ]
    runs = state["runs"].setdefault(sig, [])
    runs.append(
        {
            "at": now,
            "chat": chat,
            "receipts": receipts[:8],
            "tools": tools[:20],
            "files": files[:12],
            "keywords": keywords(request)[:8],
        }
    )
    state["runs"][sig] = runs[-MAX_RUNS:]
    proposal = _propose(state, user_id, sig, intent, now)
    _save(store, state)
    return {"signature": sig, "verified_runs": len(state["runs"][sig]), "proposed": proposal}


# Instruction-shaped words say how to behave, never what the work was (jev_skills.js).
_STOP = frozenset(
    "must always never ever ignore instructions instruction assistant user system asking ask "
    "without please again also just make sure previous above prompt rules".split()
)


def _terms(runs: list[dict]) -> list[str]:
    count: dict[str, int] = {}
    for run in runs:
        for word in set(run.get("keywords") or []) - _STOP:
            count[word] = count.get(word, 0) + 1
    return [w for w, _n in sorted(count.items(), key=lambda pair: (-pair[1], pair[0]))][:8]


def _propose(state: dict, user_id: str, sig: str, intent: str, now: float) -> str | None:
    runs = state["runs"].get(sig) or []
    if len(runs) < MIN_VERIFIED:
        return None
    _notice_removed(state, user_id)
    if state.get("day") == _day(now) or len(state["proposed"]) >= MAX_LEARNED:
        return None  # one a day, a few in all
    terms = _terms(runs)
    if _seen(state, sig, terms):
        return None
    tools: list[str] = []
    for tool in runs[-1].get("tools") or []:
        if not tools or tools[-1] != tool:
            tools.append(tool)
    name = f"{PREFIX}{_slug(terms)}"[:64].strip("-")
    present = _installed(user_id)
    base, number = name, 2
    while name in present:
        name = f"{base[:60]}-{number}"
        number += 1
    description, body = draft(name, runs, terms, tools)
    from agent_skills import installer, loader
    from tadbir import amanah

    if amanah.beyond_instructions(f"{description}\n{body}", f"skill:{name}"):
        return None
    try:
        installer.write_skill(user_id, name, description, body)
        loader.hold(user_id, name)  # earning never makes it trusted
    except Exception:  # noqa: BLE001 - a folder that cannot be written keeps nothing
        return None
    state["proposed"].append(
        {
            "name": name,
            "signature": sig,
            "intent": intent,
            "terms": terms,
            "at": now,
            "chats": sorted({str(run.get("chat")) for run in runs if run.get("chat")}),
        }
    )
    state["day"] = _day(now)
    return name


def summary(store: Any) -> dict:
    state = _load(store)
    return {
        "counting": len(state["runs"]),
        "proposed": [
            {"name": p.get("name"), "terms": p.get("terms", []), "intent": p.get("intent")}
            for p in state["proposed"]
        ],
        "removed": len(state["removed"]),
        "threshold": MIN_VERIFIED,
    }


def forget_chat(store: Any, user_id: str, chat: str) -> int:
    """Mahw: runs of the erased chat are no longer counted, and a skill earned
    from them is removed (its keywords came from that chat's requests)."""
    if not chat:
        return 0
    state = _load(store)
    removed = 0
    for sig in list(state["runs"]):
        kept = [run for run in state["runs"][sig] if run.get("chat") != chat]
        removed += len(state["runs"][sig]) - len(kept)
        if kept:
            state["runs"][sig] = kept
        else:
            del state["runs"][sig]
    staying = []
    for proposal in state["proposed"]:
        if chat in (proposal.get("chats") or []):
            from agent_skills import installer

            try:
                installer.delete_skill(user_id, str(proposal.get("name")))
            except Exception:  # noqa: BLE001 - already gone
                pass
            removed += 1
        else:
            staying.append(proposal)
    state["proposed"] = staying
    if removed:
        _save(store, state)
    return removed
