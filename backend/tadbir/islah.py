"""Islah (إصلاح): lessons MIZAN draws from the person's corrections of any work.

"I only want to put things right as far as I am able" (11:88). Tajriba keeps
lessons from programs that failed and were repaired; Islah widens that to all
work. It ports ForgeKit's lessons.js and cortex.js:

- A lesson is learned from a **correction signal**, never from MIZAN's own say-so.
  Three independent families: ``human`` (the person's complaint or correction
  right after an answer), ``undo`` (a project checkpoint the person restored,
  an action they refused when asked or held) and ``outcome`` (a check that
  failed and then passed in the same run: a tool that failed and then worked,
  a claim Sidq corrected).
- Signals are weighed by noisy-OR, p = 1 − ∏(1 − wᵢ), so three weak signals
  cannot fake one strong one, and an episode **fires only with signals from at
  least two families**: a stray "no" or a lone failed tool never mints a lesson.
  p ≥ 0.7 distils a lesson; 0.4 ≤ p < 0.7 does only when the same context
  misfired before (recurrence); below 0.4 it is variation.
- A lesson moves candidate → active → quarantined → retired. It is trusted
  only because fresh outcomes keep confirming it (a later firing episode in the
  same context), never because it exists or was shown: showing is not
  confirmation. When the person undoes work done with a lesson in view, the
  lesson is contradicted, and a wrong lesson dies faster than a right one grows
  (its confidence, freshness × validity, under 0.3 quarantines it; a
  quarantined lesson contradicted again retires, confirmed twice is active
  again).
- Active lessons most relevant to the work (tools 0.6, files 1.0, keywords
  0.3 × overlap) are shown to the agent and to Lisan as background, like
  Tajriba's, three at most.

Everything is kept per person in their private store; a stateless run or a
person with learning off keeps nothing (the store's writes are no-ops), and
Mahw erases what an erased chat taught.
"""

from __future__ import annotations

import hashlib
import re
import time
from typing import Any

SIGNALS: dict[str, tuple[float, str]] = {
    "complaint": (0.35, "human"),  # weak and noisy: never enough alone
    "restored": (0.5, "undo"),  # the person brought a checkpoint back
    "denied": (0.4, "undo"),  # an action the person refused, asked or held
    "check_fixed": (0.45, "outcome"),  # a check failed, then passed, in the run
}
DISTILL = 0.7
ACCUMULATE = 0.4
QUARANTINE = 0.3
HALF_LIFE_DAYS = 45.0
MAX_LESSONS = 60
MAX_EPISODES = 200
SHOWN = 3
EPISODE_SECONDS = 7 * 86400  # a later signal reaches an answer of the last week
KEY = "islah"
DAY = 86400.0

# Conservative: an explicit correction at the start of a short message. MIZAN
# has no correction facet; Qasd's ``harder`` facet ("try again, think more
# carefully") is read too. The signal is weak (0.35) and never fires alone.
_CORRECTION = re.compile(
    r"^\s*(?:no[,.!]\s*\S|nope\b|wrong\b|incorrect\b|that'?s (?:wrong|not (?:right|correct|"
    r"what i (?:asked|meant|wanted)))|this is (?:wrong|not what i (?:asked|meant|wanted))|"
    r"not what i (?:asked|meant|wanted)|you (?:got it wrong|misunderstood)|"
    r"(?:ye|yeh|yah) (?:galat|ghalat) hai|galat\b|ghalat\b|غلط|गलत)",
    re.IGNORECASE,
)
_NOT_CORRECTION = re.compile(r"^\s*no\s+(?:thanks|thank you|problem|worries)\b", re.IGNORECASE)
MAX_CORRECTION_WORDS = 30


# ── the pure core (lessons.js) ───────────────────────────────────────────


def score(signals: list[str]) -> dict:
    """noisy-OR over the known signals and the families they come from."""
    known = [name for name in signals if name in SIGNALS]
    product = 1.0
    for name in known:
        product *= 1.0 - SIGNALS[name][0]
    families = sorted({SIGNALS[name][1] for name in known})
    return {"p": round(1.0 - product, 4), "families": families, "fires": len(families) >= 2}


def classify(signals: list[str]) -> str:
    found = score(signals)
    if found["fires"] and found["p"] >= DISTILL:
        return "distill"
    if found["fires"] and found["p"] >= ACCUMULATE:
        return "accumulate"
    return "discard"


def validity(lesson: dict) -> float:
    """Laplace-smoothed share of independent outcomes that upheld the lesson."""
    alpha = 1 + int(lesson.get("evidence", 0))
    beta = 1 + int(lesson.get("contradictions", 0))
    return alpha / (alpha + beta)


def freshness(lesson: dict, now: float) -> float:
    age_days = max(0.0, now - float(lesson.get("confirmed", now))) / DAY
    return float(0.5 ** (age_days / HALF_LIFE_DAYS))


def confidence(lesson: dict, now: float) -> float:
    return freshness(lesson, now) * validity(lesson)


def confirm(lesson: dict, now: float) -> dict:
    """A fresh outcome showed the mistake again: the lesson is real."""
    lesson = {**lesson, "evidence": int(lesson.get("evidence", 0)) + 1, "confirmed": now}
    if lesson.get("status") == "quarantined":
        back = int(lesson.get("reconfirms", 0)) + 1
        lesson["reconfirms"] = 0 if back >= 2 else back
        lesson["status"] = "active" if back >= 2 else "quarantined"
    elif lesson.get("status") != "retired":
        lesson["status"] = "active"
    return lesson


def contradict(lesson: dict, now: float) -> dict:
    """The person undid work done with the lesson in view."""
    lesson = {**lesson, "contradictions": int(lesson.get("contradictions", 0)) + 1}
    if lesson.get("status") == "quarantined":
        lesson["status"] = "retired"
    elif lesson.get("status") != "retired" and confidence(lesson, now) < QUARANTINE:
        lesson["status"] = "quarantined"
    return lesson


def _overlap(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def match_score(lesson: dict, context: dict) -> float:
    """Relevance in [0, 1]: a shared file beats a shared tool beats shared words."""
    trigger = lesson.get("trigger") or {}
    if set(trigger.get("files") or []) & set(context.get("files") or []):
        return 1.0
    if set(trigger.get("tools") or []) & set(context.get("tools") or []):
        return 0.6
    return 0.3 * _overlap(set(trigger.get("keywords") or []), set(context.get("keywords") or []))


def select(lessons: list[dict], context: dict, now: float, k: int = SHOWN) -> list[dict]:
    """The active lessons for this work: relevance × freshness × validity."""
    ranked = []
    for lesson in lessons:
        if lesson.get("status") != "active":
            continue
        relevance = match_score(lesson, context)
        if relevance <= 0:
            continue
        recent = 1.2 if now - float(lesson.get("confirmed", 0)) <= 14 * DAY else 1.0
        ranked.append((relevance * freshness(lesson, now) * validity(lesson) * recent, lesson))
    ranked.sort(key=lambda pair: -pair[0])
    return [lesson for _score, lesson in ranked[:k]]


def render(lessons: list[dict]) -> str:
    if not lessons:
        return ""
    rows = [
        "Lessons MIZAN learned from this person's corrections of earlier work "
        "(background: check them against the request before relying on them):"
    ]
    rows += [f"- {lesson['corrected'][:240]}" for lesson in lessons]
    return "\n".join(rows)


def keywords(text: str, limit: int = 12) -> list[str]:
    """The content words of a request, without numbers: what the work was about."""
    from tadbir.taallum import content_words

    seen: list[str] = []
    for word in content_words(text or ""):
        if any(ch.isdigit() for ch in word) or len(word) < 3 or word in seen:
            continue
        seen.append(word)
        if len(seen) == limit:
            break
    return seen


def complaint(message: str) -> bool:
    """The person corrects or complains about the answer just given (conservative)."""
    text = (message or "").strip()
    if not text or len(text.split()) > MAX_CORRECTION_WORDS:
        return False
    if _NOT_CORRECTION.match(text):
        return False
    if _CORRECTION.match(text):
        return True
    try:
        from tadbir import qasd

        return bool(qasd.facet("harder", text))
    except Exception:  # noqa: BLE001 - no facet model: only the explicit form counts
        return False


def _own_words(message: str) -> str:
    """The correction, kept to show later only when Amanah finds nothing in it."""
    from tadbir import amanah

    text = " ".join((message or "").split())[:200]
    try:
        if amanah.scan(text, "correction"):
            return ""
    except Exception:  # noqa: BLE001 - unreadable: keep nothing
        return ""
    return text


def distil(episode: dict) -> dict:
    """What went wrong and what to do instead, from the episode alone (no model)."""
    context = episode.get("context") or {}
    about = ", ".join((context.get("keywords") or [])[:5]) or "this kind of request"
    where = ", ".join((context.get("files") or context.get("tools") or [])[:3])
    said = [name for name in episode.get("signals", []) if name in SIGNALS]
    happened = []
    if "complaint" in said:
        happened.append("the person corrected the answer")
    if "restored" in said:
        happened.append("the person restored the project to before it")
    if "denied" in said:
        happened.append("the person refused an action it needed")
    if "check_fixed" in said:
        happened.append("a check failed before it passed")
    wrong = f"Work on {about} was corrected: " + "; ".join(happened) + "."
    words = episode.get("correction") or ""
    if words:
        corrected = f'For {about}: the person said "{words}". Take that into account.'
    elif "restored" in said or "denied" in said:
        target = f" ({where})" if where else ""
        corrected = (
            f"For {about}: the person undid this kind of change{target}. Confirm what they "
            "want changed before acting."
        )
    else:
        corrected = f"For {about}: check the result before answering; the first attempt failed."
    return {"wrong": wrong, "corrected": corrected}


# ── the stateful part (cortex.js), per person ────────────────────────────


def _load(store: Any) -> dict:
    try:
        data = store.get(KEY) or {}
    except Exception:  # noqa: BLE001 - no store: nothing learned yet
        data = {}
    return {
        "episodes": [item for item in data.get("episodes", []) if isinstance(item, dict)],
        "lessons": [item for item in data.get("lessons", []) if isinstance(item, dict)],
    }


def _save(store: Any, state: dict) -> None:
    lessons = sorted(
        state["lessons"],
        key=lambda item: (item.get("status") == "retired", -float(item.get("confirmed", 0))),
    )[:MAX_LESSONS]
    try:
        store.put(KEY, {"episodes": state["episodes"][-MAX_EPISODES:], "lessons": lessons})
    except Exception:  # noqa: BLE001 - learning is best effort
        pass


def _overlaps(a: dict, b: dict) -> bool:
    return bool(
        set(a.get("files") or []) & set(b.get("files") or [])
        or set(a.get("tools") or []) & set(b.get("tools") or [])
        or _overlap(set(a.get("keywords") or []), set(b.get("keywords") or [])) >= 0.5
    )


def _settle(state: dict, episode: dict, now: float) -> dict | None:
    """Score an episode's signals; a firing episode creates or confirms a lesson."""
    if episode.get("fired"):
        return None
    verdict = classify(episode.get("signals", []))
    if verdict == "discard":
        return None
    context = episode.get("context") or {}
    if verdict == "accumulate":
        recurred = any(
            other is not episode
            and other.get("misfired")
            and _overlaps(other.get("context") or {}, context)
            for other in state["episodes"]
        )
        if not recurred:
            episode["misfired"] = True
            return None
    episode["fired"] = episode["misfired"] = True
    shown = set(episode.get("shown") or [])
    for index, lesson in enumerate(state["lessons"]):
        # A recurrence where the lesson was not in view confirms it.
        if lesson["id"] in shown or lesson.get("status") == "retired":
            continue
        if match_score(lesson, context) > 0 and _overlaps(lesson.get("trigger") or {}, context):
            updated = confirm(lesson, now)
            updated["chats"] = sorted({*lesson.get("chats", []), episode.get("chat", "")} - {""})
            state["lessons"][index] = updated
            return updated
    made = distil(episode)
    lesson = {
        "id": hashlib.sha256(f"{episode['id']}|{made['corrected']}".encode()).hexdigest()[:12],
        "trigger": {
            "keywords": list(context.get("keywords") or []),
            "tools": list(context.get("tools") or []),
            "files": list(context.get("files") or []),
        },
        "wrong": made["wrong"],
        "corrected": made["corrected"],
        "status": "candidate",
        "evidence": 0,
        "contradictions": 0,
        "reconfirms": 0,
        "created": now,
        "confirmed": now,
        "signals": list(episode.get("signals", [])),
        "chats": [episode["chat"]] if episode.get("chat") else [],
    }
    state["lessons"].append(lesson)
    return lesson


def _contradict_shown(state: dict, episode: dict, now: float) -> int:
    """The person undid work done with these lessons in view (once per episode)."""
    if episode.get("contradicted"):
        return 0
    shown = set(episode.get("shown") or [])
    count = 0
    for index, lesson in enumerate(state["lessons"]):
        if lesson["id"] in shown and lesson.get("status") in {"active", "quarantined"}:
            state["lessons"][index] = contradict(lesson, now)
            count += 1
    episode["contradicted"] = bool(count)
    return count


def observe(
    store: Any,
    *,
    chat: str,
    request: str,
    tools: list[str],
    files: list[str],
    signals: list[str],
    shown: list[str],
    workspace: str = "",
    replay: str = "",
    now: float | None = None,
) -> dict:
    """One answer has ended: keep it as an episode (later signals reach it) and
    settle the signals the run itself gave."""
    now = time.time() if now is None else now
    state = _load(store)
    context = {
        "keywords": keywords(request),
        "tools": sorted(set(tools))[:12],
        "files": sorted(set(files))[:12],
    }
    episode = {
        "id": hashlib.sha256(f"{chat}|{now}|{request[:80]}".encode()).hexdigest()[:12],
        "chat": chat,
        "workspace": workspace,
        "at": now,
        "context": context,
        "signals": [name for name in signals if name in SIGNALS],
        "shown": list(shown),
        "heard": False,
        "replay": replay,  # the Athar family this answer replayed, if it did
    }
    state["episodes"].append(episode)
    lesson = _settle(state, episode, now)
    _save(store, state)
    return {"episode": episode["id"], "lesson": lesson["id"] if lesson else None}


def _latest(state: dict, now: float, chat: str = "", workspace: str = "") -> dict | None:
    for episode in reversed(state["episodes"]):
        if now - float(episode.get("at", 0)) > EPISODE_SECONDS:
            return None
        if (chat and episode.get("chat") == chat) or (
            workspace and episode.get("workspace") == workspace
        ):
            found: dict = episode  # the stored episode itself: callers change it in place
            return found
    return None


def signal(
    store: Any,
    kind: str,
    *,
    chat: str = "",
    workspace: str = "",
    now: float | None = None,
) -> dict | None:
    """A correction signal from outside the run (a restore, a refused held
    action) reaches the latest answer of its chat or project."""
    if kind not in SIGNALS:
        return None
    now = time.time() if now is None else now
    state = _load(store)
    episode = _latest(state, now, chat=chat, workspace=workspace)
    if episode is None:
        return None
    episode.setdefault("signals", []).append(kind)
    contradicted = _contradict_shown(state, episode, now) if SIGNALS[kind][1] == "undo" else 0
    lesson = _settle(state, episode, now)
    _save(store, state)
    return {
        "episode": episode["id"],
        "lesson": lesson["id"] if lesson else None,
        "contradicted": contradicted,
        "replay": episode.get("replay", ""),
    }


def hear(store: Any, chat: str, message: str, now: float | None = None) -> dict | None:
    """The person's next message after an answer: a complaint is a human signal
    on that answer. Only the first message after an answer is read."""
    now = time.time() if now is None else now
    state = _load(store)
    episode = _latest(state, now, chat=chat)
    if episode is None or episode.get("heard"):
        return None
    episode["heard"] = True
    found = complaint(message)
    lesson = None
    if found:
        episode.setdefault("signals", []).append("complaint")
        episode["correction"] = _own_words(message)
        lesson = _settle(state, episode, now)
    _save(store, state)
    return {
        "complaint": found,
        "lesson": lesson["id"] if lesson else None,
        "replay": episode.get("replay", "") if found else "",
    }


def relevant(store: Any, request: str, tools: list[str] | None = None, now: float | None = None):
    now = time.time() if now is None else now
    context = {"keywords": keywords(request), "tools": list(tools or []), "files": []}
    return select(_load(store)["lessons"], context, now)


def summary(store: Any, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    lessons = _load(store)["lessons"]
    counts = {
        status: sum(1 for item in lessons if item.get("status") == status)
        for status in ("candidate", "active", "quarantined", "retired")
    }
    return {
        "lessons": len(lessons),
        **counts,
        "items": [
            {
                "id": item["id"],
                "status": item.get("status"),
                "corrected": item.get("corrected", "")[:240],
                "confidence": round(confidence(item, now), 3),
                "evidence": item.get("evidence", 0),
                "contradictions": item.get("contradictions", 0),
            }
            for item in lessons[:30]
        ],
    }


def forget_chat(store: Any, chat: str) -> int:
    """Mahw: the erased chat's answers, and every lesson it taught, go."""
    if not chat:
        return 0
    state = _load(store)
    episodes = [item for item in state["episodes"] if item.get("chat") != chat]
    lessons = [item for item in state["lessons"] if chat not in (item.get("chats") or [])]
    removed = len(state["lessons"]) - len(lessons)
    if removed or len(episodes) != len(state["episodes"]):
        _save(store, {"episodes": episodes, "lessons": lessons})
    return removed


def forget(store: Any) -> None:
    try:
        store.put(KEY, {"episodes": [], "lessons": []})
    except Exception:  # noqa: BLE001
        pass
