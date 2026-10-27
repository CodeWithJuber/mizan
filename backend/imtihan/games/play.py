"""The interactive games in the AGI test: the base model plays turn by turn, MIZAN explores.

Both arms play the same fresh game from the local arena:

- **base**: the model sees each frame as rows of hex digits (as ARC-AGI-3
  shows numbers) and the actions it may take, and replies with up to eight
  actions per turn (``ACTION1 ACTION4`` or ``ACTION6 2 3``); it gets the same
  feedback as MIZAN and nothing else
- **mizan**: Mustakshif learns what the actions do and plans, with no model
  call; what it learns of a level is kept for the next attempt (per user)

A game passes when every level is won. Each row reports levels won, actions
taken, and action efficiency (the optimal number of actions over the number
used, at most 1), the measure ARC-AGI-3 scores.
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any

from . import arena
from .mustakshif import Mustakshif, describe, local

TASKS = [
    {"id": "game-maze", "block": "games", "category": "reasoning", "game": "maze",
     "prompt": "Interactive game: reach the goal (level 2 changes the controls)"},
    {"id": "game-keys", "block": "games", "category": "reasoning", "game": "keys",
     "prompt": "Interactive game: something must happen before the way opens"},
    {"id": "game-lights", "block": "games", "category": "reasoning", "game": "lights",
     "prompt": "Interactive game: clicks change the board; find the winning state"},
]  # fmt: skip
TURNS_PER_LEVEL = 10
BASE_SYSTEM = (
    "You are playing an unknown game on a grid of numbers (colours 0-f). You are not told the "
    "rules or the goal: find them by acting and watching the grid. Reply with up to 8 actions "
    "separated by spaces, using only the available ones: ACTION1 ... ACTION5, ACTION7, or "
    "ACTION6 x y (x is the column, y the row, both from 0). You may write one short line of "
    "reasoning first; the actions must be on the last line."
)
_ACTION = re.compile(r"ACTION([1-7])(?:\s+(\d{1,2})\s+(\d{1,2}))?", re.IGNORECASE)
_MEMORY: dict[str, dict] = {}  # what MIZAN learned of each level, per user, for this process


def is_game(task: dict) -> bool:
    return "game" in task


def parse_actions(text: str, available: list[int]) -> list[tuple[int, int | None, int | None]]:
    lines = [line for line in (text or "").strip().splitlines() if line.strip()]
    moves: list[tuple[int, int | None, int | None]] = []
    for match in _ACTION.finditer(lines[-1] if lines else ""):
        action = int(match.group(1))
        if action not in available:
            continue
        if action == 6:
            if match.group(2) is None:
                continue
            moves.append((6, int(match.group(2)), int(match.group(3))))
        else:
            moves.append((action, None, None))
    return moves[:8]


async def base_arm(agent: Any, game: arena.Game) -> dict:
    """The model alone, turn by turn, with the same feedback MIZAN gets."""
    from api.usage import build_usage_block, build_usage_summary
    from providers import effective_limits, provider_retry_delay

    provider, model = getattr(agent, "ai_client", None), getattr(agent, "ai_model", None)
    if provider is None:
        return {"error": "No hosted language model is configured", "frame": game.frame()}
    frame = game.reset()
    history: list[str] = []
    usage: list[dict] = []
    started = time.perf_counter()
    max_tokens = max(1, min(800, effective_limits(provider, model or "")[1]))
    turns = TURNS_PER_LEVEL * game.levels()
    error = None
    for _turn in range(turns):
        if frame["state"] == "WIN":
            break
        if frame["state"] == "GAME_OVER":
            frame = game.reset()
            history.append("RESET (the level was lost and restarted)")
        prompt = "\n\n".join(
            [*(["Your last turns:\n" + "\n".join(history[-6:])] if history else []),
             "Current frame:\n" + describe(frame), "Your actions:"]
        )  # fmt: skip
        response = None
        for attempt in range(2):
            sent = time.perf_counter()
            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        provider.create, model=model, max_tokens=max_tokens, system=BASE_SYSTEM,
                        messages=[{"role": "user", "content": prompt}],
                    ),
                    120,
                )  # fmt: skip
                usage.append(
                    {"response": response, "latency_ms": (time.perf_counter() - sent) * 1000}
                )
                break
            except Exception as exc:  # noqa: BLE001 - provider errors vary
                delay = provider_retry_delay(exc, attempt)
                if delay is None or attempt:
                    error = f"Model error: {type(exc).__name__}"
                    break
                await asyncio.sleep(delay)
        if response is None:
            break
        text = "".join(
            getattr(b, "text", "") for b in getattr(response, "content", []) or []
            if getattr(b, "type", "") == "text"
        )  # fmt: skip
        moves = parse_actions(text, frame["available_actions"])
        if not moves:
            history.append("(no valid action given)")
            continue
        before = frame["grid"]
        level = frame["levels_completed"]
        for action, x, y in moves:
            frame = game.step(action, x, y)
            if frame["state"] != "NOT_FINISHED" or frame["levels_completed"] != level:
                break
        said = " ".join(f"ACTION{a}" + (f" {x} {y}" if a == 6 else "") for a, x, y in moves)
        effect = (
            "a level was completed"
            if frame["levels_completed"] != level
            else "the grid changed"
            if frame["grid"] != before
            else "nothing changed"
        )
        history.append(f"{said} -> {effect}")
    return {
        "frame": game.frame(),
        "error": error,
        "model_calls": len(usage),
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        "usage": build_usage_summary(
            [
                build_usage_block(
                    {"response": u["response"], "latency_ms": round(u["latency_ms"], 1)}
                )
                for u in usage
            ]
        ),  # fmt: skip
    }


async def mizan_arm(game: arena.Game, owner: str) -> dict:
    started = time.perf_counter()
    explorer = Mustakshif(_MEMORY.setdefault(owner, {}), game=game.name)
    played = await explorer.play(await local(game), max_actions=game.budget * game.levels() * 3)
    from tadbir import sijill

    sijill.note(
        "game",
        {"detail": f"{game.name}: won {played['levels_completed']}/{played['win_levels']} levels "
                   f"in {played['actions']} actions; the winning paths are remembered"},
        owner=owner,
    )  # fmt: skip
    return {
        "frame": game.frame(),
        "error": None,
        "model_calls": 0,
        "learned": played["learned"],
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        "usage": {},
    }


async def run_task(agent: Any, task: dict, attempt: int, owner: str) -> dict:
    rows, details = [], {}
    optimal = arena.make(task["game"]).optimal()
    for arm in ("base", "mizan"):
        game = arena.make(task["game"])
        data = await base_arm(agent, game) if arm == "base" else await mizan_arm(game, owner)
        frame = data["frame"]
        won, levels = int(frame["levels_completed"]), int(frame["win_levels"])
        needed = sum(optimal[:won])
        efficiency = round(min(1.0, needed / game.total), 3) if won and game.total else 0.0
        usage = data.get("usage") or {}
        rows.append({
            "task_id": task["id"], "block": task["block"], "arm": arm, "attempt": attempt,
            "pass": won == levels, "score": round(won / levels, 3) if levels else 0.0,
            "detail": f"{won}/{levels} levels in {game.total} actions (optimal {sum(optimal)})",
            "latency_ms": data.get("latency_ms"), "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"), "cost_usd": usage.get("cost_usd"),
            "model_calls": data.get("model_calls"), "tool_calls": 0,
            "game": {"levels_completed": won, "win_levels": levels, "actions": game.total,
                     "optimal": sum(optimal), "efficiency": efficiency},
            **({"error": str(data["error"])[:300]} if data.get("error") and not won else {}),
        })  # fmt: skip
        details[arm] = {
            "text": f"{won}/{levels} levels won in {game.total} actions"
            + (
                "\n\nWhat MIZAN learned:\n- " + "\n- ".join(data["learned"])
                if data.get("learned")
                else ""
            ),
            "final": describe(frame),
        }
    return {"rows": rows, "compare": {"prompt": task["prompt"], "game": details}}


def summarize(results: list[dict]) -> dict:
    """Levels won and action efficiency per arm, over every game that ran."""
    summary: dict[str, Any] = {}
    for arm in ("base", "mizan"):
        rows = [r for r in results if r["arm"] == arm and r.get("game")]
        if not rows:
            continue
        summary[arm] = {
            "games": len(rows),
            "won": sum(1 for r in rows if r["pass"]),
            "levels": round(sum(r["score"] for r in rows) / len(rows), 3),
            "efficiency": round(sum(r["game"]["efficiency"] for r in rows) / len(rows), 3),
            "actions": sum(r["game"]["actions"] for r in rows),
            "model_calls": sum(int(r.get("model_calls") or 0) for r in rows),
        }
    return summary
