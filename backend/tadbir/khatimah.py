"""Khatimah (خاتمة): what MIZAN learns as a run ends.

"Deeds are by their endings" (Bukhari 6607). One place reads a finished run
for what follows from it, so the agent loop only calls in twice:

- before a top-level run: the person's message is heard as a possible
  correction of the answer before it (Islah), and the lessons relevant to the
  work are given to the agent (``guidance``);
- after it: the answer becomes an Islah episode (with the correction signals
  the run itself gave: a check that failed then passed, an action refused);
  a verified run with tool steps is offered to Athar (replay) and Itqan
  (earned skills); the agent's Martaba record counts it when MIZAN checked it.

Each person's learning lives in their own ``private/<sha256(owner)>/learning.db``.
Nothing is kept for a stateless run or a person with learning off (the store's
writes are no-ops there), and Mahw erases what an erased chat taught
(``forget_chat``).
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

from core.adaptive import AdaptiveStateStore

logger = logging.getLogger("mizan.khatimah")
_STORES: dict[str, AdaptiveStateStore] = {}
FILE = "learning.db"


def store(owner: str) -> AdaptiveStateStore:
    """This person's learning store (in memory when the data folder cannot be written)."""
    from memory.mahw import private_dir

    path = private_dir(owner) / FILE
    key = str(path)
    if key not in _STORES:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            _STORES[key] = AdaptiveStateStore(key)
        except (OSError, sqlite3.Error):
            _STORES[key] = AdaptiveStateStore(None)
    return _STORES[key]


def _learns() -> bool:
    from memory import stateless

    return not stateless.active() and stateless.learns()


def _owner() -> str:
    from security.auth import current_user_id

    return current_user_id() or ""


def _workspace() -> str:
    try:
        from workspace.context import bound_workspace_id

        return str(bound_workspace_id() or "")
    except Exception:  # noqa: BLE001 - no project bound
        return ""


def before_run(task: Any, context: dict | None) -> None:
    """The person's message, heard against the answer before it in this chat."""
    owner, chat = _owner(), str((context or {}).get("session_id") or "")
    if not owner or not chat or not isinstance(task, str) or not _learns():
        return
    from tadbir import athar, islah

    try:
        heard = islah.hear(store(owner), chat, task)
        if heard and heard.get("replay"):
            # A replayed answer the person corrected: the replay failed its check.
            athar.drop(store(owner), heard["replay"])
    except Exception:  # noqa: BLE001 - learning never stops a run
        logger.debug("Islah could not hear the message", exc_info=True)


def guidance(task: Any) -> str:
    """The active lessons for this work, rendered for the system prompt."""
    owner = _owner()
    if not owner or not isinstance(task, str) or not _learns():
        return ""
    from tadbir import athar, islah

    try:
        lessons = islah.relevant(store(owner), task)
    except Exception:  # noqa: BLE001
        return ""
    run = athar.current()
    if run is not None:
        run.shown = sorted({*run.shown, *(lesson["id"] for lesson in lessons)})
    text: str = islah.render(lessons)
    return text


def signal(owner: str, kind: str, *, chat: str = "", workspace: str = "") -> dict | None:
    """A correction from outside a run: a checkpoint restored, a held action refused."""
    if not owner or not _learns():
        return None
    from tadbir import athar, islah

    try:
        found: dict | None = islah.signal(store(owner), kind, chat=chat, workspace=workspace)
        if found and found.get("replay") and islah.SIGNALS.get(kind, ("", ""))[1] == "undo":
            athar.drop(store(owner), found["replay"])
        return found
    except Exception:  # noqa: BLE001
        logger.debug("Islah signal not kept", exc_info=True)
        return None


def _fixed_in_run(steps: list[dict]) -> bool:
    """A tool failed and the same tool then worked, in this run."""
    failed: set[str] = set()
    for step in steps:
        if step.get("outcome") == "error":
            failed.add(step["tool"])
        elif step.get("outcome") == "done" and step["tool"] in failed:
            return True
    return False


def _signals(steps: list[dict], result: dict) -> list[str]:
    found = []
    sidq = result.get("sidq") if isinstance(result.get("sidq"), dict) else {}
    if _fixed_in_run(steps) or (sidq and (sidq.get("corrected") or sidq.get("removed"))):
        found.append("check_fixed")
    if any(step.get("outcome") == "declined" for step in steps):
        found.append("denied")
    return found


def _tainted(result: dict) -> bool:
    amanah = result.get("amanah")
    return isinstance(amanah, dict) and bool(amanah.get("ignored"))


def after_run(agent: Any, task: Any, context: dict | None, result: dict, run: Any = None) -> dict:
    """What this finished top-level run teaches (``run``: its Athar trace). Never raises."""
    report: dict = {}
    try:
        from tadbir import martaba

        stage = martaba.record(agent, result)
        if stage is not None:
            report["martaba"] = stage["stage"]
    except Exception:  # noqa: BLE001
        logger.debug("Martaba record not kept", exc_info=True)
    owner = _owner()
    if not owner or not isinstance(task, str) or not _learns():
        return report
    from tadbir import athar, islah, itqan

    run = run if run is not None else athar.current()
    steps = list(run.steps) if run is not None else []
    chat = str((context or {}).get("session_id") or "")
    workspace = _workspace()
    kept = store(owner)
    try:
        if chat or workspace:
            report["episode"] = islah.observe(
                kept,
                chat=chat,
                request=task,
                tools=[step["tool"] for step in steps],
                files=[step["path"] for step in steps if step.get("path")],
                signals=_signals(steps, result),
                shown=list(run.shown) if run is not None else [],
                workspace=workspace,
                replay=run.replay if run is not None else "",
            )
        if run is not None and run.replay:
            return report  # a replayed run is no new evidence about itself
        if not result.get("task_verified") or not steps or _tainted(result):
            return report
        orchestration = result.get("orchestration") or {}
        intent = str(orchestration.get("intent") or result.get("orchestrator") or "agent")
        report["athar"] = athar.learn(kept, task, steps, intent=intent, chat=chat)
        report["itqan"] = itqan.observe(
            kept, owner, intent=intent, request=task, steps=steps, verified=True, chat=chat
        )
    except Exception:  # noqa: BLE001 - learning never loses an answer
        logger.debug("Run-end learning skipped", exc_info=True)
    return report


def forget_chat(owner: str, chat: str) -> dict[str, int]:
    """Mahw: what the erased chat taught Islah, Itqan and Athar."""
    from tadbir import athar, islah, itqan

    kept = store(owner)
    removed = {"lessons from corrections": 0, "earned skills and their runs": 0, "replay runs": 0}
    try:
        removed["lessons from corrections"] = islah.forget_chat(kept, chat)
        removed["earned skills and their runs"] = itqan.forget_chat(kept, owner, chat)
        removed["replay runs"] = athar.forget_chat(kept, chat)
    except Exception:  # noqa: BLE001 - reported as zero, never raised into Mahw
        logger.warning("Learning store could not be erased for a chat", exc_info=True)
    return removed


def summary(owner: str) -> dict:
    from tadbir import athar, islah, itqan

    kept = store(owner)
    return {
        "lessons": islah.summary(kept),
        "earned_skills": itqan.summary(kept),
        "replay": athar.summary(kept),
    }
