"""Basar: an image attached in a chat reaches the model, is kept with the chat, and is the user's own."""

import base64
import io
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from PIL import Image as Pillow

from memory.dhikr import DhikrMemorySystem
from perception import basar
from providers import OpenAICompatibleProvider
from security.auth import MizanAuth


def picture(size=(3000, 2000), mode="RGB", gps=True, kind="JPEG") -> bytes:
    image = Pillow.new(mode, size, (200, 30, 30) if mode == "RGB" else (200, 30, 30, 128))
    out = io.BytesIO()
    if gps and kind == "JPEG":
        exif = Pillow.Exif()
        exif[0x010F] = "PhoneMaker"  # camera make
        exif[0x8825] = {2: (24.0, 51.0, 0.0)}  # a GPS position
        image.save(out, format=kind, exif=exif)
    else:
        image.save(out, format=kind)
    return out.getvalue()


def test_an_image_loses_its_metadata_and_is_scaled_down():
    raw = picture()
    assert Pillow.open(io.BytesIO(raw)).getexif()  # the camera wrote metadata
    image = basar.prepare(raw)
    kept = Pillow.open(io.BytesIO(image.data))
    assert not kept.getexif() and kept.info.get("exif") is None
    assert max(kept.size) == basar.MAX_SIDE and (image.width, image.height) == kept.size
    assert image.media_type == "image/jpeg" and len(image.sha) == 64


def test_transparency_is_kept_as_png():
    image = basar.prepare(picture((40, 40), mode="RGBA", kind="PNG"))
    assert image.media_type == "image/png"


@pytest.mark.parametrize(
    "raw",
    [b"%PDF-1.7 not an image", b"", b"GIF89a" + b"\x00" * 10],
    ids=["pdf", "empty", "broken-gif"],
)
def test_what_is_not_a_readable_image_is_refused(raw):
    with pytest.raises(basar.ImageError):
        basar.prepare(raw)


def test_an_image_too_large_to_decode_is_refused(monkeypatch):
    monkeypatch.setattr(basar, "MAX_PIXELS", 1000)
    with pytest.raises(basar.ImageError):
        basar.prepare(picture((100, 100)))


def test_the_turns_images_become_content_blocks_for_every_provider():
    image = basar.prepare(picture((20, 20)))
    with basar.bind([image]):
        content = basar.content("What is in this picture?")
    assert content[0] == {"type": "text", "text": "What is in this picture?"}
    assert content[1]["type"] == "image" and content[1]["source"]["media_type"] == "image/jpeg"
    assert basar.content("no images now") == "no images now"
    converted = OpenAICompatibleProvider._convert_messages_to_openai(
        SimpleNamespace(), "system", [{"role": "user", "content": content}]
    )
    parts = converted[1]["content"]
    assert parts[0] == {"type": "text", "text": "What is in this picture?"}
    assert parts[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_kept_images_belong_to_their_owner(tmp_path, monkeypatch):
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    image = basar.prepare(picture((20, 20)))
    basar.store("alice", image)
    assert basar.load("alice", image.sha).data == image.data
    assert basar.load("bob", image.sha) is None
    assert basar.load("alice", "../../etc/passwd") is None
    assert basar.erase("alice", [image.sha]) == 1 and basar.load("alice", image.sha) is None


# ── in a chat ─────────────────────────────────────────────────────────────


class SeeingAgent:
    id = "seeing-agent"
    name = "Khalifah"
    ai_model = "vision-model"
    max_tool_turns = 10

    def __init__(self):
        self.seen = []
        self._llm_calls = []
        self._last_tool_results = []

    async def execute(self, content, context, **callbacks):
        self.seen.append([image.sha for image in basar.current()])
        await callbacks["stream_callback"]("It is a red square.")
        return {"success": True, "result": "It is a red square.", "usage": {}}


@pytest.fixture
def api(tmp_path, monkeypatch):
    import api.main as main

    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    memory = DhikrMemorySystem(str(tmp_path / "memory.db"))
    auth = MizanAuth("basar-test-signing-key-" * 4, data_dir=str(tmp_path / "users"))
    users = {
        name: auth.create_user(name, "test-password", roles=["user"]) for name in ("alice", "bob")
    }
    tokens = {name: auth.create_token(user) for name, user in users.items()}
    monkeypatch.setattr(main, "auth", auth)
    monkeypatch.setattr(main, "memory", memory)
    monkeypatch.setenv("DB_PATH", memory.db_path)
    monkeypatch.setattr(main, "active_sessions", {})
    monkeypatch.setattr(main, "_stream_sessions", set())
    monkeypatch.setattr(main, "_stream_runs", {})
    monkeypatch.setattr(main, "chat_agent_for", AsyncMock(side_effect=lambda user, agent: agent))
    monkeypatch.setattr(main, "manager", SimpleNamespace(broadcast=AsyncMock(), send=AsyncMock()))
    agent = SeeingAgent()
    agent.memory = DhikrMemorySystem(str(tmp_path / "alice-private.db"))
    monkeypatch.setattr(main, "active_agents", {agent.id: agent})
    return main, TestClient(main.app), tokens, memory, agent


def send(client, token, content, images=(), session="pics"):
    body = {"session_id": session, "content": content, "request_id": str(uuid.uuid4())}
    if images:
        body["images"] = [
            {"media_type": "image/jpeg", "data": base64.b64encode(raw).decode()} for raw in images
        ]
    return client.post("/api/chat/stream", json=body, headers={"Authorization": f"Bearer {token}"})


async def test_an_attached_image_reaches_the_model_and_is_kept_with_the_chat(api):
    main, client, tokens, memory, agent = api
    response = send(client, tokens["alice"], "Design an HTML page for this", [picture((60, 40))])
    assert response.status_code == 200 and "red square" in response.text
    (shas,) = agent.seen
    assert len(shas) == 1
    stored = await memory.get_messages("pics")
    user = next(m for m in stored if m["role"] == "user")
    assert user["metadata"]["images"][0]["sha"] == shas[0]
    # The receipt of the request names the image but does not hold it.
    receipt = main.ChatStreamLedger(memory._get_conn, memory._release_conn)
    assert receipt is not None
    # Only the owner can see it.
    alice = client.get(
        f"/api/media/{shas[0]}", headers={"Authorization": f"Bearer {tokens['alice']}"}
    )
    assert alice.status_code == 200 and alice.headers["content-type"] == "image/jpeg"
    bob = client.get(f"/api/media/{shas[0]}", headers={"Authorization": f"Bearer {tokens['bob']}"})
    assert bob.status_code == 404


async def test_the_next_message_still_sees_the_image_and_the_one_after_does_not(api):
    _, client, tokens, _, agent = api
    send(client, tokens["alice"], "What is this?", [picture((60, 40))])
    send(client, tokens["alice"], "Image ka html banana tha")
    send(client, tokens["alice"], "Thanks, and what is 2+2?")
    assert [len(shas) for shas in agent.seen] == [1, 1, 0]
    assert agent.seen[0] == agent.seen[1]


async def test_a_file_that_is_not_an_image_is_refused_before_anything_runs(api):
    _, client, tokens, _, agent = api
    response = send(client, tokens["alice"], "look", [b"%PDF-1.7 not an image"])
    assert response.status_code == 400 and agent.seen == []


async def test_deleting_the_chat_deletes_its_images(api):
    _, client, tokens, memory, agent = api
    send(client, tokens["alice"], "What is this?", [picture((60, 40))])
    (shas,) = agent.seen
    erased = client.delete("/api/chat/pics", headers={"Authorization": f"Bearer {tokens['alice']}"})
    assert erased.status_code == 200, erased.text
    assert erased.json()["removed"]["images"] == 1
    gone = client.get(
        f"/api/media/{shas[0]}", headers={"Authorization": f"Bearer {tokens['alice']}"}
    )
    assert gone.status_code == 404


def test_the_models_request_carries_the_image_with_the_current_message(monkeypatch, tmp_path):
    from agents.specialized import create_agent

    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("agents.base.create_provider", lambda **kwargs: None)
    agent = create_agent("general")
    image = basar.prepare(picture((20, 20)))
    with basar.bind([image]):
        last = agent._build_messages("Design an HTML page for this")[-1]
    assert last["role"] == "user" and last["content"][1]["type"] == "image"
    assert "Design an HTML page for this" in last["content"][0]["text"]
    assert isinstance(agent._build_messages("no image")[-1]["content"], str)


# ── models that cannot see ─────────────────────────────────────────────────


def test_a_model_that_cannot_read_images_is_told_so_instead_of_failing(monkeypatch):
    import providers

    monkeypatch.setitem(providers._OPENROUTER_CATALOG, "vendor/text-only", {"images": False})
    monkeypatch.setitem(providers._OPENROUTER_CATALOG, "vendor/seeing", {"images": True})
    assert providers.accepts_images("vendor/text-only") is False
    assert providers.accepts_images("vendor/seeing") is True
    assert providers.accepts_images("vendor/unknown") is None
    image = basar.prepare(picture((20, 20)))
    messages = [{"role": "user", "content": basar.content("What is this?", [image])}]
    blind = OpenAICompatibleProvider._convert_messages_to_openai(
        SimpleNamespace(), "system", messages, images=False
    )
    assert isinstance(blind[1]["content"], str) and "cannot read images" in blind[1]["content"]
    assert "base64" not in blind[1]["content"]


def test_lisan_chooses_a_model_that_sees_when_the_turn_has_an_image(monkeypatch):
    import random

    import providers
    from tadbir import wazn

    monkeypatch.setenv("MIZAN_LISAN_MODELS", "vendor/text-only,vendor/seeing")
    monkeypatch.setitem(providers._OPENROUTER_CATALOG, "vendor/text-only", {"images": False})
    monkeypatch.setitem(providers._OPENROUTER_CATALOG, "vendor/seeing", {"images": True})
    rng = random.Random(1)
    image = basar.prepare(picture((20, 20)))
    with basar.bind([image]):
        assert wazn.choose("code", 0, None, rng) == "vendor/seeing"
    assert wazn._candidates() == ["vendor/text-only", "vendor/seeing"]


@pytest.mark.parametrize(
    "message, intent",
    [
        ("Design a htnl page fpr this and preview", "build_project"),
        ("Image ka html banana tha", "build_project"),
        ("What is in this picture?", "converse"),
    ],
)
def test_a_page_from_an_image_is_built_and_a_question_about_it_is_answered(message, intent):
    from tadbir import qasd

    assert qasd.ranked(message)[0][0] == intent


async def test_mizans_own_recipes_show_lisan_the_picture(monkeypatch):
    from tadbir.lisan import Lisan

    sent = []

    class Seeing:
        provider_name = "openrouter"

        def create(self, **request):
            sent.append(request["messages"])
            reply = SimpleNamespace(type="text", text="<!doctype html><h1>Red</h1>")
            return SimpleNamespace(content=[reply], usage=None)

    agent = SimpleNamespace(
        ai_client=Seeing(),
        ai_model="vendor/seeing",
        _record_llm_call=lambda *args: None,
        _add_execution_time=lambda *args: None,
    )
    monkeypatch.delenv("MIZAN_LISAN_MODELS", raising=False)
    image = basar.prepare(picture((20, 20)))
    with basar.bind([image]):
        await Lisan(agent).ask("Write the page", "Design an HTML page for this")
    await Lisan(agent).ask("Write the page", "A page with a red heading")
    with_image, without = sent
    assert with_image[0]["content"][1]["type"] == "image"
    assert without[0]["content"] == "A page with a red heading"
