"""Interactive games (ARC-AGI-3 style): MIZAN learns the rules by acting, then plans."""

import json

import httpx
import pytest

from imtihan.games import arc3, arena, play
from imtihan.games.mustakshif import Mustakshif, local, motion, objects, solve_gf2
from providers import BaseLLMProvider, ContentBlock, LLMResponse


def test_every_game_is_winnable_and_knows_its_optimum():
    for name in arena.GAMES:
        assert all(length > 0 for length in arena.make(name).optimal()), name


def test_a_level_is_lost_when_its_budget_runs_out_and_reset_restarts_it():
    game = arena.make("maze")
    game.reset()
    for _ in range(game.budget):
        frame = game.step(3)  # into the wall: nothing happens, the budget still runs
    assert frame["state"] == "GAME_OVER" and game.step(4)["state"] == "GAME_OVER"
    assert game.reset()["state"] == "NOT_FINISHED"


@pytest.mark.parametrize("name", sorted(arena.GAMES))
async def test_mustakshif_wins_every_game_without_a_model(name):
    memory: dict = {}
    game = arena.make(name)
    first = await Mustakshif(memory, game=name).play(await local(game))
    assert first["state"] == "WIN" and first["levels_completed"] == first["win_levels"]
    again = arena.make(name)
    second = await Mustakshif(memory, game=name).play(await local(again))
    assert second["state"] == "WIN" and second["actions"] <= first["actions"]
    assert any("replayed" in line for line in second["learned"])


async def test_mirrored_controls_are_noticed_and_relearned():
    game = arena.make("maze")
    result = await Mustakshif(game="maze").play(await local(game))
    learned = " ".join(result["learned"])
    assert "action 1 moves colour 2 by (-1, 0)" in learned  # level 1: up is up
    assert "action 1 moves colour 2 by (1, 0)" in learned  # level 2: mirrored


def test_motion_and_objects_are_read_from_the_grid():
    before = [[0, 0, 0], [0, 2, 0], [0, 0, 0]]
    after = [[0, 0, 0], [0, 0, 2], [0, 0, 0]]
    assert motion(before, after) == (2, (0, 1))
    assert motion(before, before) is None
    assert objects([[0, 0, 0, 0], [0, 7, 0, 3], [0, 7, 0, 0]]) == [(3, 1), (1, 2)]


def test_lights_out_is_solved_over_gf2():
    effects = [{(0, 0), (0, 1)}, {(0, 1), (0, 2)}, {(0, 2)}]
    chosen = solve_gf2(effects, {(0, 0), (0, 2)})
    toggled: set = set()
    for index in chosen:
        toggled ^= effects[index]
    assert toggled == {(0, 0), (0, 2)}
    assert solve_gf2([{(0, 0)}], {(0, 1)}) is None


def test_the_models_actions_are_read_from_its_last_line():
    assert play.parse_actions("I will go right.\nACTION4 ACTION4 ACTION6 1 2", [4, 6]) == [
        (4, None, None),
        (4, None, None),
        (6, 1, 2),
    ]
    assert play.parse_actions("ACTION5", [1, 2]) == []


class Turns(BaseLLMProvider):
    provider_name = "fixture"

    def __init__(self, reply):
        self.reply = reply
        self.prompts = []

    def create(self, **kwargs):
        self.prompts.append(kwargs["messages"][0]["content"])
        return LLMResponse([ContentBlock(type="text", text=self.reply)], model="fixture")


class Agent:
    ai_model = "fixture"

    def __init__(self, reply):
        self.ai_client = Turns(reply)


async def test_a_game_task_scores_both_arms_by_levels_and_efficiency():
    agent = Agent("ACTION3")  # the base model keeps walking into a wall
    outcome = await play.run_task(agent, play.TASKS[0], 1, "u1")
    base, mizan = outcome["rows"]
    assert (
        not base["pass"]
        and base["score"] == 0.0
        and base["model_calls"] == play.TURNS_PER_LEVEL * 2
    )
    assert mizan["pass"] and mizan["model_calls"] == 0 and 0 < mizan["game"]["efficiency"] <= 1
    assert "nothing changed" in agent.ai_client.prompts[-1]  # the model saw the feedback
    summary = play.summarize(outcome["rows"])
    assert summary["mizan"]["won"] == 1 and summary["base"]["won"] == 0


async def test_arc3_adapter_follows_the_official_api(monkeypatch):
    calls = []
    grid = [[0] * 4 for _ in range(4)]
    won = {"done": False}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content or b"{}")
        calls.append((request.url.path, body, request.headers.get("X-API-Key")))
        path = request.url.path
        if path.endswith("/games"):
            return httpx.Response(200, json=[{"game_id": "ls20-abc", "title": "LS20"}])
        if path.endswith("/scorecard/open"):
            return httpx.Response(200, json={"card_id": "card-1"})
        if path.endswith("/scorecard/close"):
            return httpx.Response(200, json={"card_id": "card-1"})
        if path.endswith("/cmd/ACTION1"):
            won["done"] = True
        frame = [[row[:] for row in grid]]
        return httpx.Response(
            200,
            json={
                "game_id": "ls20-abc", "guid": "g-1", "frame": frame,
                "state": "WIN" if won["done"] else "NOT_FINISHED",
                "levels_completed": 1 if won["done"] else 0, "win_levels": 1,
                "action_input": {"id": 0}, "available_actions": [1, 2],
            },
        )  # fmt: skip

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    def client(**kwargs):
        return original(transport=transport, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client)
    monkeypatch.setenv("ARC_API_KEY", "test-key")
    result = await arc3.play(max_actions=20)
    assert result["state"] == "WIN" and result["card_id"] == "card-1"
    paths = [path for path, _body, _key in calls]
    assert paths[:3] == ["/api/games", "/api/scorecard/open", "/api/cmd/RESET"]
    assert paths[-1] == "/api/scorecard/close"
    reset = next(body for path, body, _ in calls if path == "/api/cmd/RESET")
    assert reset == {"game_id": "ls20-abc", "card_id": "card-1"}
    assert all(key == "test-key" for _path, _body, key in calls)


def test_arc3_needs_a_key(monkeypatch):
    monkeypatch.delenv("ARC_API_KEY", raising=False)
    assert not arc3.configured()
