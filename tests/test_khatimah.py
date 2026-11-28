"""Khatimah: what a finished run teaches, wired through the agent and the routes
(Islah lessons for all work reaching the agent, correction signals from a
restored checkpoint and a refused action; docs/automatic-learning.md)."""

from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agents.specialized import create_agent
from api import coding_workspace
from providers import BaseLLMProvider, ContentBlock, LLMResponse
from security.auth import TokenPayload, bind_principal, reset_principal
from security.izn import IznPermission
from tadbir import athar, islah, khatimah
from workspace.context import bind_workspace, reset_workspace

ALICE = TokenPayload("alice", "Alice", ["user"], 9999999999, 0, "alice-token")


class ScriptedProvider(BaseLLMProvider):
    provider_name = "fixture"

    def __init__(self):
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(deepcopy(kwargs))
        return LLMResponse([ContentBlock(type="text", text="Done.")], model="fixture")


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "memory.db"))
    monkeypatch.setenv("MIZAN_WORKSPACE_ROOT", str(tmp_path / "projects"))
    monkeypatch.delenv("MIZAN_WORKSPACE_RUNNER_URL", raising=False)
    monkeypatch.setattr("agents.base.create_provider", lambda **kwargs: None)
    return tmp_path


@pytest.fixture
def alice(data):
    token = bind_principal(ALICE)
    yield
    reset_principal(token)


def active_lesson():
    return {
        "id": "L7",
        "trigger": {"keywords": ["recipe", "metric"], "tools": [], "files": []},
        "corrected": 'For recipe, metric: the person said "use grams, never cups".',
        "status": "active",
        "evidence": 2,
        "contradictions": 0,
        "confirmed": 4_000_000_000.0,
        "chats": ["c0"],
    }


async def test_active_lessons_reach_the_agents_system_prompt(alice):
    khatimah.store("alice").put(islah.KEY, {"episodes": [], "lessons": [active_lesson()]})
    agent = create_agent("general", izn=IznPermission())
    agent.ai_client = ScriptedProvider()
    await agent.execute("Convert this recipe to metric please", {"session_id": "c9"})
    system = str(agent.ai_client.requests[0]["system"])
    assert "Lessons MIZAN learned" in system and "use grams, never cups" in system
    # The run records which lessons it was shown (showing is not confirmation).
    (episode,) = islah._load(khatimah.store("alice"))["episodes"]
    assert episode["shown"] == ["L7"]
    assert islah._load(khatimah.store("alice"))["lessons"][0]["evidence"] == 2


async def test_an_unrelated_request_is_not_shown_the_lesson(alice):
    khatimah.store("alice").put(islah.KEY, {"episodes": [], "lessons": [active_lesson()]})
    agent = create_agent("general", izn=IznPermission())
    agent.ai_client = ScriptedProvider()
    await agent.execute("What is the weather in Lahore?", {"session_id": "c9"})
    assert "Lessons MIZAN learned" not in str(agent.ai_client.requests[0]["system"])


async def test_a_run_that_fixed_a_failed_tool_then_a_restore_teaches_a_lesson(alice, data):
    agent = create_agent("general", izn=IznPermission())
    tries = iter([{"error": "SyntaxError"}, {"written": True}])

    async def checked(name, params):
        return next(tries)

    async def impl(task, context, *args):
        await agent._execute_tool_safe("workspace_write", {"path": "recipe.md", "content": "x"})
        await agent._execute_tool_safe("workspace_write", {"path": "recipe.md", "content": "y"})
        return {"success": True, "result": "Converted.", "task_verified": False}

    agent._execute_tool_checked = checked
    agent._execute_impl = impl
    bound = bind_workspace("proj-1")
    try:
        await agent.execute("Convert my recipe file to metric", {"session_id": "c1"})
    finally:
        reset_workspace(bound)
    (episode,) = islah._load(khatimah.store("alice"))["episodes"]
    assert episode["signals"] == ["check_fixed"] and episode["workspace"] == "proj-1"
    assert episode["context"]["files"] == ["recipe.md"]

    # The person rewinds the project: a second family, so a lesson is distilled.
    app = FastAPI()
    app.include_router(coding_workspace.router)
    app.dependency_overrides[coding_workspace.require_auth] = lambda: ALICE
    client = TestClient(app, raise_server_exceptions=False)
    project = client.post("/api/workspaces", json={"name": "Recipes"}).json()["id"]
    base = f"/api/workspaces/{project}"
    client.put(base + "/file", json={"path": "recipe.md", "content": "1 cup flour\n"})
    saved = client.post(base + "/checkpoint", json={"message": "before"}).json()
    client.put(base + "/file", json={"path": "recipe.md", "content": "120 g flour\n"})
    state = islah._load(khatimah.store("alice"))
    state["episodes"][0]["workspace"] = project
    khatimah.store("alice").put(islah.KEY, state)
    restored = client.post(f"{base}/checkpoints/{saved['id']}/restore", json={})
    assert restored.status_code == 200
    (lesson,) = islah._load(khatimah.store("alice"))["lessons"]
    assert lesson["status"] == "candidate" and lesson["trigger"]["files"] == ["recipe.md"]
    assert "undid this kind of change" in lesson["corrected"]


async def test_a_declined_action_is_a_denied_signal(alice):
    agent = create_agent("general", izn=IznPermission())

    async def checked(name, params):
        return {"declined": True}

    async def impl(task, context, *args):
        await agent._execute_tool_safe("http_post", {"url": "https://example.com"})
        return {"success": True, "result": "I could not send it."}

    agent._execute_tool_checked = checked
    agent._execute_impl = impl
    await agent.execute("Send the form", {"session_id": "c2"})
    (episode,) = islah._load(khatimah.store("alice"))["episodes"]
    assert episode["signals"] == ["denied"]
    # A held action refused later reaches the same answer by its chat.
    assert khatimah.signal("alice", "denied", chat="c2")["episode"] == episode["id"]


async def test_nested_runs_add_to_the_top_level_trace(alice):
    seen = []

    async def impl(task, context, *args):
        seen.append(athar.current())
        return {"success": True, "result": "ok"}

    agent = create_agent("general", izn=IznPermission())
    agent._execute_impl = impl
    await agent.execute("hello", {"session_id": "c3"})
    assert seen and seen[0] is not None and athar.current() is None


def test_an_erase_and_a_learning_write_never_interleave(tmp_path, monkeypatch):
    # Mahw erases in a worker thread while a run learns on the event loop: each
    # read-change-write of the store holds one lock, so neither undoes the other.
    import threading

    from tadbir import athar, khatimah

    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    entered = threading.Event()
    release = threading.Event()
    order = []
    forget = athar.forget_chat

    def slow_forget(store, chat):
        entered.set()
        release.wait(5)
        order.append("erased")
        return forget(store, chat)

    monkeypatch.setattr(athar, "forget_chat", slow_forget)
    eraser = threading.Thread(target=khatimah.forget_chat, args=("amina", "c1"))
    eraser.start()
    assert entered.wait(5)
    got = threading.Event()

    def writer():
        with khatimah.LOCK:
            order.append("learned")
        got.set()

    other = threading.Thread(target=writer)
    other.start()
    assert not got.wait(0.2)  # the learning write waits for the erase
    release.set()
    eraser.join(5)
    other.join(5)
    assert order == ["erased", "learned"]
