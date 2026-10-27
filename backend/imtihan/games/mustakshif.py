"""Mustakshif (مستكشف): MIZAN's explorer for games whose rules it is not told.

It plays the way a careful person does, with no language model:

1. **Remember**: a level MIZAN has won before (same opening grid) is replayed
   from memory, the shortest winning path it found (Hifz for games).
2. **Learn what the actions do**: it tries each action and compares the grids.
   An action that moves one object by a fixed step teaches the motion model
   (and which object is "me"); a click that toggles a pattern of cells teaches
   a toggle rule, which MIZAN states as a stencil and checks on the next click.
3. **Plan**: with a motion model it plans the shortest route (breadth-first
   search) to the things it has not yet understood, rarest colour first,
   learns which colours block and which open, and replans when a prediction
   fails (so mirrored controls on a later level are noticed and relearned).
   With a toggle rule it solves for the clicks that clear the board exactly
   (linear algebra over GF(2)).
4. **Explore systematically** when no model explains the game: every state
   it sees is a node, every action an edge; it tries untried actions, walks
   back to the nearest state that still has one, and restarts the level when
   needed.

Every transition it observes is kept, so a model that fails falls back to
exploration without losing what was seen. Works on the local arena and on
ARC-AGI-3 through the same ``reset`` / ``step`` interface.
"""

from __future__ import annotations

import hashlib
from collections import Counter, deque
from typing import Any, Protocol

Grid = list[list[int]]
Move = tuple[int, int | None, int | None]  # action, x, y


class Env(Protocol):
    async def reset(self) -> dict: ...

    async def step(self, action: int, x: int | None = None, y: int | None = None) -> dict: ...


def key(grid: Grid) -> str:
    return hashlib.blake2b(repr(grid).encode(), digest_size=8).hexdigest()


def positions(grid: Grid, colour: int) -> set[tuple[int, int]]:
    return {(r, c) for r, row in enumerate(grid) for c, value in enumerate(row) if value == colour}


def motion(before: Grid, after: Grid) -> tuple[int, tuple[int, int]] | None:
    """The one colour whose cells all moved by the same step, and that step."""
    changed = {
        before[r][c]
        for r in range(len(before))
        for c in range(len(before[0]))
        if before[r][c] != after[r][c]
    } | {
        after[r][c]
        for r in range(len(after))
        for c in range(len(after[0]))
        if before[r][c] != after[r][c]
    }
    for colour in sorted(changed):
        was, now = positions(before, colour), positions(after, colour)
        if not was or len(was) != len(now) or was == now:
            continue
        (r0, c0), (r1, c1) = min(was), min(now)
        step = (r1 - r0, c1 - c0)
        if {(r + step[0], c + step[1]) for r, c in was} == now:
            return colour, step
    return None


def objects(grid: Grid) -> list[tuple[int, int]]:
    """One (x, y) inside each object: connected cells of one colour other than the background."""
    background = Counter(value for row in grid for value in row).most_common(1)[0][0]
    seen: set[tuple[int, int]] = set()
    found: list[tuple[int, int, int]] = []
    for r, row in enumerate(grid):
        for c, value in enumerate(row):
            if value == background or (r, c) in seen:
                continue
            cells, queue = [], deque([(r, c)])
            seen.add((r, c))
            while queue:
                cr, cc = queue.popleft()
                cells.append((cr, cc))
                for nr, nc in ((cr + 1, cc), (cr - 1, cc), (cr, cc + 1), (cr, cc - 1)):
                    if (
                        0 <= nr < len(grid)
                        and 0 <= nc < len(row)
                        and (nr, nc) not in seen
                        and grid[nr][nc] == value
                    ):
                        seen.add((nr, nc))
                        queue.append((nr, nc))
            middle = sorted(cells)[len(cells) // 2]
            found.append((len(cells), middle[1], middle[0]))
    found.sort()  # small, distinct objects first: buttons more often than walls
    return [(x, y) for _size, x, y in found]


def solve_gf2(
    effects: list[set[tuple[int, int]]], target: set[tuple[int, int]]
) -> list[int] | None:
    """Which effects to apply once each so that together they toggle exactly ``target``."""
    cells = sorted(set().union(*effects, target)) if effects else sorted(target)
    index = {cell: i for i, cell in enumerate(cells)}
    rows = []
    for cell in cells:
        bits = 0
        for j, effect in enumerate(effects):
            if cell in effect:
                bits |= 1 << j
        rows.append([bits, 1 if cell in target else 0])
    pivots: list[int] = []
    rank = 0
    for column in range(len(effects)):
        pivot = next((i for i in range(rank, len(rows)) if rows[i][0] >> column & 1), None)
        if pivot is None:
            continue
        rows[rank], rows[pivot] = rows[pivot], rows[rank]
        for i in range(len(rows)):
            if i != rank and rows[i][0] >> column & 1:
                rows[i][0] ^= rows[rank][0]
                rows[i][1] ^= rows[rank][1]
        pivots.append(column)
        rank += 1
    if any(bits == 0 and value for bits, value in rows):
        return None  # no combination clears the board
    chosen = [column for row, column in zip(rows[:rank], pivots, strict=True) if row[1]]
    del index
    return chosen


class Mustakshif:
    def __init__(self, memory: dict[str, list[Move]] | None = None, *, game: str = "game"):
        self.memory = memory if memory is not None else {}
        self.game = game
        self.actions = 0
        self.log: list[str] = []  # what MIZAN learned, in words, for the report
        self.graph: dict[str, dict[Move, str]] = {}
        self.won_from: tuple[str, Move] | None = None
        self.frame: dict = {}

    # ── playing ──────────────────────────────────────────────────────────

    async def play(self, env: Env, max_actions: int = 800) -> dict:
        self.frame = await env.reset()
        self.actions += 1
        while self.frame.get("state") not in ("WIN",) and self.actions < max_actions:
            level = int(self.frame.get("levels_completed", 0))
            await self._level(env, max_actions)
            if int(self.frame.get("levels_completed", 0)) == level:
                break  # this level could not be won within the budget
        return {
            "state": self.frame.get("state"),
            "levels_completed": int(self.frame.get("levels_completed", 0)),
            "win_levels": int(self.frame.get("win_levels", 0)),
            "actions": self.actions,
            "learned": self.log[-20:],
        }

    async def _do(self, env: Env, move: Move) -> dict:
        before = key(self.frame["grid"])
        level = int(self.frame.get("levels_completed", 0))
        action, x, y = move
        self.frame = await env.step(action, x, y)
        self.actions += 1
        if int(self.frame.get("levels_completed", 0)) > level:
            self.won_from = (before, move)  # the move that won the level
        else:
            self.graph.setdefault(before, {})[move] = key(self.frame["grid"])
        return self.frame

    async def _reset(self, env: Env) -> None:
        self.frame = await env.reset()
        self.actions += 1

    def _level_won(self, level: int) -> bool:
        return (
            int(self.frame.get("levels_completed", 0)) > level or self.frame.get("state") == "WIN"
        )

    async def _level(self, env: Env, max_actions: int) -> None:
        level = int(self.frame.get("levels_completed", 0))
        start = key(self.frame["grid"])
        self.graph, self.won_from = {}, None
        remembered = self.memory.get(f"{self.game}:{start}")
        if remembered:
            for move in remembered:
                await self._do(env, move)
                if self._level_won(level):
                    self.log.append(f"level {level + 1}: replayed the path MIZAN found before")
                    return
            self.log.append(f"level {level + 1}: the remembered path no longer wins; exploring")
            await self._reset(env)
        available = [int(a) for a in self.frame.get("available_actions", [])]
        strategies = []
        if any(a in available for a in (1, 2, 3, 4, 5)):
            strategies.append(self._navigate)
        if 6 in available:
            strategies.append(self._toggle)
        strategies.append(self._explore)
        for strategy in strategies:
            if self._level_won(level) or self.actions >= max_actions:
                break
            await strategy(env, level, max_actions)
            if not self._level_won(level) and self.frame.get("state") == "GAME_OVER":
                await self._reset(env)
        if self._level_won(level):
            path = self._shortest(start)
            if path:
                self.memory[f"{self.game}:{start}"] = path

    def _shortest(self, start: str) -> list[Move] | None:
        """The shortest path in what MIZAN observed from the level's start to its win."""
        if self.won_from is None:
            return None
        parents: dict[str, tuple[str, Move] | None] = {start: None}
        queue = deque([start])
        while queue:
            state = queue.popleft()
            for move, nxt in self.graph.get(state, {}).items():
                if nxt not in parents:
                    parents[nxt] = (state, move)
                    queue.append(nxt)
        node, last = self.won_from
        if node not in parents:
            return None
        path = [last]
        while parents[node] is not None:
            node, move = parents[node]  # type: ignore[misc]
            path.append(move)
        return path[::-1]

    # ── 1. moving an object: learn the motion, then plan ─────────────────

    async def _navigate(self, env: Env, level: int, max_actions: int) -> None:
        moves = [a for a in (1, 2, 3, 4, 5) if a in self.frame.get("available_actions", [])]
        steps: dict[int, tuple[int, int]] = {}
        me: int | None = None
        floor: set[int] = set()
        blocked: Counter[int] = Counter()
        tried_from: dict[int, set[str]] = {a: set() for a in moves}
        cleared = ""
        budget = max_actions
        while not self._level_won(level) and self.actions < budget:
            if self.frame.get("state") == "GAME_OVER":
                await self._reset(env)
                continue
            grid = self.frame["grid"]
            here_key = key(grid)
            unknown = [
                a
                for a in moves
                if a not in steps and here_key not in tried_from[a] and len(tried_from[a]) < 6
            ]
            if unknown and (me is None or len(steps) < 4):
                action = unknown[0]
                tried_from[action].add(here_key)
                before = [row[:] for row in grid]
                await self._do(env, (action, None, None))
                seen = motion(before, self.frame["grid"])
                if seen:
                    me = seen[0] if me is None else me
                    if seen[0] == me:
                        steps[action] = seen[1]
                        r, c = min(positions(self.frame["grid"], me))
                        floor.add(before[r][c])
                        self.log.append(f"action {action} moves colour {me} by {seen[1]}")
                continue
            if me is None or not steps:
                return  # nothing moves: not a navigation game
            here = positions(grid, me)
            if not here:
                return
            position = min(here)
            counts = Counter(value for row in grid for value in row)
            targets = sorted(
                (
                    (counts[value], abs(r - position[0]) + abs(c - position[1]), (r, c))
                    for r, row in enumerate(grid)
                    for c, value in enumerate(row)
                    if value not in floor and value != me and blocked[value] < 2
                ),
            )
            route = None
            for _count, _distance, cell in targets:
                route = self._route(grid, position, cell, steps, floor)
                if route:
                    break
            if not route:
                if any(blocked.values()) and cleared != here_key:
                    blocked.clear()  # something may have opened since; look again
                    cleared = here_key
                    continue
                return
            for action in route:
                expected = (position[0] + steps[action][0], position[1] + steps[action][1])
                before = [row[:] for row in self.frame["grid"]]
                entering = before[expected[0]][expected[1]]
                await self._do(env, (action, None, None))
                if self._level_won(level) or self.frame.get("state") == "GAME_OVER":
                    break
                now = positions(self.frame["grid"], me)
                if not now or min(now) != expected:
                    seen = motion(before, self.frame["grid"])
                    if seen and seen[0] == me:
                        steps[action] = seen[1]  # the controls changed: relearn
                        self.log.append(f"action {action} now moves {me} by {seen[1]}")
                    else:
                        blocked[entering] += 1
                        self.log.append(f"colour {entering} blocks")
                    break
                floor.add(entering)
                position = expected

    @staticmethod
    def _route(
        grid: Grid,
        start: tuple[int, int],
        goal: tuple[int, int],
        steps: dict[int, tuple[int, int]],
        floor: set[int],
    ) -> list[int] | None:
        height, width = len(grid), len(grid[0])
        parents: dict[tuple[int, int], tuple[tuple[int, int], int] | None] = {start: None}
        queue = deque([start])
        while queue:
            cell = queue.popleft()
            if cell == goal:
                path = []
                while parents[cell] is not None:
                    cell, action = parents[cell]  # type: ignore[misc]
                    path.append(action)
                return path[::-1]
            for action, (dr, dc) in steps.items():
                nxt = (cell[0] + dr, cell[1] + dc)
                if not (0 <= nxt[0] < height and 0 <= nxt[1] < width) or nxt in parents:
                    continue
                if nxt != goal and grid[nxt[0]][nxt[1]] not in floor:
                    continue
                parents[nxt] = (cell, action)
                queue.append(nxt)
        return None

    # ── 2. clicks that toggle cells: learn the stencil, then solve ───────

    async def _toggle(self, env: Env, level: int, max_actions: int) -> None:
        grid = self.frame["grid"]
        height, width = len(grid), len(grid[0])
        if height * width > 400:
            return  # a large board: leave it to systematic exploration
        background = Counter(value for row in grid for value in row).most_common(1)[0][0]
        centre = (width // 2, height // 2)
        stencil = await self._click_effect(env, centre)
        if stencil is None:
            return
        offsets = {(r - centre[1], c - centre[0]) for r, c in stencil}
        # Test the rule on a second, different click before trusting it.
        probe = (0, 0) if centre != (0, 0) else (width - 1, height - 1)
        predicted = self._apply(offsets, probe, height, width)
        observed = await self._click_effect(env, probe)
        if observed != predicted:
            self.log.append("clicks do not follow one stencil; exploring instead")
            return
        self.log.append(f"a click toggles its cell and {len(offsets) - 1} neighbour(s)")
        clicks = [(x, y) for y in range(height) for x in range(width)]
        effects = [self._apply(offsets, click, height, width) for click in clicks]
        lit = {(r, c) for r in range(height) for c in range(width)
               if self.frame["grid"][r][c] != background}  # fmt: skip
        chosen = solve_gf2(effects, lit)
        if chosen is None:
            self.log.append("no set of clicks clears this board")
            return
        self.log.append(f"solved for {len(chosen)} click(s) that clear the board")
        for index in chosen:
            if self._level_won(level) or self.actions >= max_actions:
                return
            x, y = clicks[index]
            await self._do(env, (6, x, y))

    async def _click_effect(self, env: Env, at: tuple[int, int]) -> set[tuple[int, int]] | None:
        before = [row[:] for row in self.frame["grid"]]
        await self._do(env, (6, at[0], at[1]))
        after = self.frame["grid"]
        if len(after) != len(before) or len(after[0]) != len(before[0]):
            return None
        changed = {(r, c) for r in range(len(before)) for c in range(len(before[0]))
                   if before[r][c] != after[r][c]}  # fmt: skip
        return changed or None

    @staticmethod
    def _apply(offsets: set[tuple[int, int]], click: tuple[int, int], height: int, width: int):
        x, y = click
        return {
            (y + dr, x + dc) for dr, dc in offsets if 0 <= y + dr < height and 0 <= x + dc < width
        }

    # ── 3. no model fits: explore every state and action ─────────────────

    async def _explore(self, env: Env, level: int, max_actions: int) -> None:
        available = [int(a) for a in self.frame.get("available_actions", [])]
        while not self._level_won(level) and self.actions < max_actions:
            if self.frame.get("state") == "GAME_OVER":
                await self._reset(env)
            here = key(self.frame["grid"])
            options = self._options(self.frame["grid"], available)
            untried = [move for move in options if move not in self.graph.get(here, {})]
            if untried:
                await self._do(env, untried[0])
                continue
            path = self._to_frontier(here, available)
            if path is None:
                return  # everything reachable was tried
            for move in path:
                await self._do(env, move)
                if self._level_won(level) or self.frame.get("state") == "GAME_OVER":
                    break

    def _options(self, grid: Grid, available: list[int]) -> list[Move]:
        options: list[Move] = [(a, None, None) for a in available if a not in (0, 6, 7)]
        if 6 in available:
            if len(grid) * len(grid[0]) <= 256:
                options += [(6, x, y) for y in range(len(grid)) for x in range(len(grid[0]))]
            else:  # a large frame: one click on each object
                options += [(6, x, y) for x, y in objects(grid)[:40]]
        return options

    def _to_frontier(self, here: str, available: list[int]) -> list[Move] | None:
        parents: dict[str, tuple[str, Move] | None] = {here: None}
        queue = deque([here])
        while queue:
            state = queue.popleft()
            edges = self.graph.get(state, {})
            if state != here and (state not in self.graph or len(edges) < self._width(available)):
                path: list[Move] = []
                while parents[state] is not None:
                    state, move = parents[state]  # type: ignore[misc]
                    path.append(move)
                return path[::-1]
            for move, nxt in edges.items():
                if nxt not in parents:
                    parents[nxt] = (state, move)
                    queue.append(nxt)
        return None

    def _width(self, available: list[int]) -> int:
        return len(self._options(self.frame["grid"], available))


async def local(game: Any) -> Env:
    """The local arena behind the async interface Mustakshif and the API share."""

    class Local:
        async def reset(self) -> dict:
            return dict(game.reset())

        async def step(self, action: int, x: int | None = None, y: int | None = None) -> dict:
            return dict(game.step(action, x, y))

    return Local()


def describe(frame: dict) -> str:
    """A frame as text for a language model: rows of hex digits, as ARC-AGI-3 shows numbers."""
    rows = "\n".join("".join(f"{value:x}" for value in row) for row in frame["grid"])
    return (
        f"state: {frame.get('state')}  levels: {frame.get('levels_completed')}/"
        f"{frame.get('win_levels')}  actions: {frame.get('available_actions')}\n{rows}"
    )


__all__ = ["Mustakshif", "describe", "key", "local", "motion", "objects", "solve_gf2"]
