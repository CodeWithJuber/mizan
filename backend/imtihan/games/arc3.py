"""ARC-AGI-3 through its official REST API: MIZAN's explorer plays the real games.

Set ``ARC_API_KEY`` (from the ARC-AGI-3 console) to enable it. The client
follows https://docs.arcprize.org: every request carries ``X-API-Key``; a
scorecard is opened first and its ``card_id`` goes into every RESET; the
session cookies the server sets are sent back on every call; ACTION6 takes
``x`` and ``y`` (0-63). A frame's grids are 64x64 colours 0-15; MIZAN plays on
the last grid of each frame. The scorecard is closed at the end and its id is
returned, so the result can be checked on arcprize.org.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from .mustakshif import Mustakshif

BASE_URL = "https://three.arcprize.org/api"


class Arc3Error(RuntimeError):
    pass


def configured() -> bool:
    return bool(os.getenv("ARC_API_KEY", "").strip())


class Arc3:
    """One game on one scorecard, behind the reset/step interface Mustakshif plays."""

    def __init__(self, client: httpx.AsyncClient, game_id: str, card_id: str):
        self.client, self.game_id, self.card_id = client, game_id, card_id
        self.guid: str | None = None

    async def _post(self, path: str, body: dict) -> dict:
        response = await self.client.post(f"{BASE_URL}{path}", json=body)
        if response.status_code >= 400:
            raise Arc3Error(
                f"ARC-AGI-3 {path} answered {response.status_code}: {response.text[:200]}"
            )
        return dict(response.json())

    @staticmethod
    def _frame(data: dict) -> dict:
        frames = data.get("frame") or [[[0]]]
        return {
            "grid": frames[-1],
            "state": data.get("state", "NOT_FINISHED"),
            "levels_completed": int(data.get("levels_completed", 0)),
            "win_levels": int(data.get("win_levels", 0)),
            "available_actions": [a for a in data.get("available_actions", []) if a],
        }

    async def reset(self) -> dict:
        body: dict[str, Any] = {"game_id": self.game_id, "card_id": self.card_id}
        if self.guid:
            body["guid"] = self.guid
        data = await self._post("/cmd/RESET", body)
        self.guid = data.get("guid") or self.guid
        return self._frame(data)

    async def step(self, action: int, x: int | None = None, y: int | None = None) -> dict:
        body: dict[str, Any] = {"game_id": self.game_id, "guid": self.guid}
        if action == 6:
            body.update({"x": int(x or 0), "y": int(y or 0)})
        data = await self._post(f"/cmd/ACTION{action}", body)
        return self._frame(data)


async def games(client: httpx.AsyncClient) -> list[dict]:
    response = await client.get(f"{BASE_URL}/games")
    if response.status_code >= 400:
        raise Arc3Error(f"ARC-AGI-3 /games answered {response.status_code}")
    return [dict(item) for item in response.json()]


async def play(game_id: str | None = None, max_actions: int = 400) -> dict:
    """Play one ARC-AGI-3 game (the first listed when none is named) with Mustakshif."""
    key = os.getenv("ARC_API_KEY", "").strip()
    if not key:
        raise Arc3Error("Set ARC_API_KEY to play ARC-AGI-3 games")
    async with httpx.AsyncClient(timeout=30, headers={"X-API-Key": key}) as client:
        listed = await games(client)
        if not listed:
            raise Arc3Error("ARC-AGI-3 lists no games for this key")
        chosen = game_id or str(listed[0].get("game_id"))
        opened = await client.post(
            f"{BASE_URL}/scorecard/open", json={"tags": ["mizan", "mustakshif"]}
        )
        if opened.status_code >= 400:
            raise Arc3Error(f"Could not open a scorecard ({opened.status_code})")
        card_id = str(opened.json().get("card_id"))
        try:
            explorer = Mustakshif(game=chosen)
            result = await explorer.play(Arc3(client, chosen, card_id), max_actions=max_actions)
        finally:
            await client.post(f"{BASE_URL}/scorecard/close", json={"card_id": card_id})
        return {
            "game_id": chosen,
            "card_id": card_id,
            "games": [str(item.get("game_id")) for item in listed][:50],
            **result,
        }
