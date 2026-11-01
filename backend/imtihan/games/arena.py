"""A local arena of interactive grid games in the style of ARC-AGI-3.

Each game is played like an ARC-AGI-3 game: the agent sees only a grid of
colours (0-15) and the actions it may take, never the rules. ``reset`` starts
or restarts the current level, ``step`` takes ACTION1-5 and 7, or ACTION6 with
``x, y``; every frame reports ``state`` (NOT_FINISHED, WIN, GAME_OVER),
``levels_completed`` and ``win_levels``, as the official API does
(https://docs.arcprize.org). A level is lost (GAME_OVER) when its action
budget runs out; RESET restarts it.

The games test what ARC-AGI-3 tests: exploring, learning what each action does,
inferring the goal, and adapting when a later level changes the rules.

- **maze**: reach the exit; on level 2 the controls are mirrored
- **keys**: a door opens only after the key is taken
- **lights**: clicking a cell toggles it and its neighbours; turn every light off

Each game also knows its shortest solution (breadth-first search over its own
states), so an agent's action efficiency is measured against the optimum, as
ARC-AGI-3 measures it against human players.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Hashable
from typing import Any

WIN, GAME_OVER, NOT_FINISHED = "WIN", "GAME_OVER", "NOT_FINISHED"
FLOOR, PLAYER, EXIT, KEY, WALL, DOOR, LIGHT = 0, 2, 3, 4, 5, 6, 7
_MOVES = {1: (-1, 0), 2: (1, 0), 3: (0, -1), 4: (0, 1)}  # up, down, left, right


class Game:
    """One game: levels of hidden rules behind a grid."""

    name = "game"
    actions: tuple[int, ...] = (1, 2, 3, 4)
    budget = 120  # actions per level before GAME_OVER

    def __init__(self) -> None:
        self.level = 0
        self.completed = 0
        self.used = 0  # actions taken in this level (for the budget)
        self.total = 0  # every action, RESET included
        self.state: Hashable = None
        self.over = False

    # The rules, per game.
    def levels(self) -> int:
        raise NotImplementedError

    def start(self, level: int) -> Hashable:
        raise NotImplementedError

    def move(self, level: int, state: Any, action: int, x: int | None, y: int | None) -> Any:
        """The next state (the same state when the action does nothing)."""
        raise NotImplementedError

    def won(self, level: int, state: Any) -> bool:
        raise NotImplementedError

    def render(self, level: int, state: Any) -> list[list[int]]:
        raise NotImplementedError

    def clicks(self, level: int) -> list[tuple[int, int]]:
        return []

    # The ARC-AGI-3 interface.
    def frame(self) -> dict:
        finished = self.completed >= self.levels()
        state = WIN if finished else GAME_OVER if self.over else NOT_FINISHED
        level = min(self.level, self.levels() - 1)
        return {
            "game_id": self.name,
            "grid": self.render(level, self.state),
            "state": state,
            "levels_completed": self.completed,
            "win_levels": self.levels(),
            "available_actions": list(self.actions),
        }

    def reset(self) -> dict:
        self.total += 1
        if self.completed >= self.levels():
            return self.frame()
        self.state = self.start(self.level)
        self.used, self.over = 0, False
        return self.frame()

    def step(self, action: int, x: int | None = None, y: int | None = None) -> dict:
        if self.state is None:
            return self.reset()
        if self.over or self.completed >= self.levels() or action not in self.actions:
            return self.frame()
        self.total += 1
        self.used += 1
        self.state = self.move(self.level, self.state, action, x, y)
        if self.won(self.level, self.state):
            self.completed += 1
            self.level += 1
            if self.level < self.levels():
                self.state, self.used = self.start(self.level), 0
        elif self.used >= self.budget:
            self.over = True
        return self.frame()

    def optimal(self) -> list[int]:
        """The fewest actions that win each level (breadth-first search)."""
        lengths = []
        for level in range(self.levels()):
            begin = self.start(level)
            seen = {begin}
            queue: deque[tuple[Any, int]] = deque([(begin, 0)])
            best = -1
            choices: list[tuple[int, int | None, int | None]] = [
                (a, None, None) for a in self.actions if a != 6
            ]
            choices += [(6, x, y) for x, y in self.clicks(level)]
            while queue:
                state, depth = queue.popleft()
                if self.won(level, state):
                    best = depth
                    break
                for action, x, y in choices:
                    following = self.move(level, state, action, x, y)
                    if following not in seen:
                        seen.add(following)
                        queue.append((following, depth + 1))
            lengths.append(best)
        return lengths


def _parse(rows: list[str]) -> tuple[set[tuple[int, int]], dict[str, tuple[int, int]], int, int]:
    walls: set[tuple[int, int]] = set()
    marks: dict[str, tuple[int, int]] = {}
    for r, row in enumerate(rows):
        for c, char in enumerate(row):
            if char == "#":
                walls.add((r, c))
            elif char != ".":
                marks[char] = (r, c)
    return walls, marks, len(rows), len(rows[0])


class Maze(Game):
    """Reach the exit. Level 2 mirrors the controls: the agent must notice and adapt."""

    name = "maze"
    LAYOUTS = (
        ["#######", "#P..#.#", "#.#.#.#", "#.#...#", "#.###.#", "#....E#", "#######"],
        ["#########", "#P....#.#", "#.##.##.#", "#.#....E#", "#.#.##.##", "#...#...#", "#########"],
    )
    MIRRORED = (False, True)

    def levels(self) -> int:
        return len(self.LAYOUTS)

    def start(self, level: int) -> Hashable:
        return _parse(self.LAYOUTS[level])[1]["P"]

    def move(self, level, state, action, x, y):
        dr, dc = _MOVES[action]
        if self.MIRRORED[level]:
            dr, dc = -dr, -dc
        walls = _parse(self.LAYOUTS[level])[0]
        target = (state[0] + dr, state[1] + dc)
        return state if target in walls else target

    def won(self, level, state):
        return state == _parse(self.LAYOUTS[level])[1]["E"]

    def render(self, level, state):
        walls, marks, height, width = _parse(self.LAYOUTS[level])
        grid = [[WALL if (r, c) in walls else FLOOR for c in range(width)] for r in range(height)]
        grid[marks["E"][0]][marks["E"][1]] = EXIT
        grid[state[0]][state[1]] = PLAYER
        return grid


class Keys(Game):
    """The door opens only once the key is taken; then reach the exit."""

    name = "keys"
    LAYOUTS = (
        ["#######", "#P...K#", "#.#####", "#.D..E#", "#######"],
        ["########", "#K.#..E#", "#..#.#.#", "#..D.#.#", "#P.#...#", "########"],
    )

    def levels(self) -> int:
        return len(self.LAYOUTS)

    def start(self, level):
        return (_parse(self.LAYOUTS[level])[1]["P"], False)

    def move(self, level, state, action, x, y):
        (r, c), has_key = state
        walls, marks, _h, _w = _parse(self.LAYOUTS[level])
        dr, dc = _MOVES[action]
        target = (r + dr, c + dc)
        if target in walls or (target == marks["D"] and not has_key):
            return state
        return (target, has_key or target == marks["K"])

    def won(self, level, state):
        return state[0] == _parse(self.LAYOUTS[level])[1]["E"]

    def render(self, level, state):
        (r, c), has_key = state
        walls, marks, height, width = _parse(self.LAYOUTS[level])
        grid = [[WALL if (i, j) in walls else FLOOR for j in range(width)] for i in range(height)]
        grid[marks["E"][0]][marks["E"][1]] = EXIT
        if not has_key:
            grid[marks["K"][0]][marks["K"][1]] = KEY
            grid[marks["D"][0]][marks["D"][1]] = DOOR
        grid[r][c] = PLAYER
        return grid


class Lights(Game):
    """Clicking a light toggles it and its four neighbours; win when every light is off."""

    name = "lights"
    actions = (6,)
    budget = 40
    BOARDS = (
        ("0100", "1110", "0100", "0000"),  # one click at the centre of the cross
        ("11000", "10000", "00001", "00011", "00001"),
    )

    def levels(self) -> int:
        return len(self.BOARDS)

    def start(self, level):
        return tuple(tuple(int(ch) for ch in row) for row in self.BOARDS[level])

    def move(self, level, state, action, x, y):
        size = len(state)
        if x is None or y is None or not (0 <= x < size and 0 <= y < size):
            return state
        cells = [list(row) for row in state]
        for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
            cx, cy = x + dx, y + dy
            if 0 <= cx < size and 0 <= cy < size:
                cells[cy][cx] ^= 1
        return tuple(tuple(row) for row in cells)

    def won(self, level, state):
        return not any(any(row) for row in state)

    def render(self, level, state):
        return [[LIGHT if cell else FLOOR for cell in row] for row in state]

    def clicks(self, level):
        size = len(self.BOARDS[level])
        return [(x, y) for y in range(size) for x in range(size)]


GAMES: dict[str, type[Game]] = {cls.name: cls for cls in (Maze, Keys, Lights)}


def make(name: str) -> Game:
    return GAMES[name]()
