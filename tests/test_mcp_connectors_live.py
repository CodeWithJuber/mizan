"""MCP connectors against real servers: Streamable HTTP and SSE on 127.0.0.1 (the SDK's
own server, served by uvicorn), a local OAuth authorization server, host stdio
processes, and the API's new routes."""

import asyncio
import base64
import hashlib
import json
import logging
import os
import secrets as token_secrets
import signal
import socket
import sys
import threading
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import pytest
import uvicorn
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mcp import Client
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import Context, MCPServer
from mcp_types import ToolAnnotations
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.routing import Route

from connectors import manager as manager_module
from connectors import registry, secrets, store
from connectors import tools as tools_module
from connectors.manager import ConnectorManager, fingerprint, map_result
from security.auth import TokenPayload, bind_principal, reset_principal

ALICE = TokenPayload("alice", "Alice", ["user"], 9999999999, 0, "alice-token")
BOB = TokenPayload("bob", "Bob", ["user"], 9999999999, 0, "bob-token")


# ── local servers ─────────────────────────────────────────────────────────


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class Served:
    """An ASGI app served by uvicorn on 127.0.0.1 in a thread."""

    def __init__(self, app, port: int | None = None):
        self.port = port or free_port()
        self.server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="error", lifespan="on")
        )
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()
        deadline = time.time() + 10
        while not self.server.started:
            if time.time() > deadline:
                raise RuntimeError("server did not start")
            time.sleep(0.02)

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def stop(self) -> None:
        self.server.should_exit = True
        self.server.force_exit = True
        self.thread.join(10)


def tools_server(read_only: bool = True, instructions: str = "") -> MCPServer:
    server = MCPServer("demo", instructions=instructions or None)

    @server.tool()
    def add(a: int, b: int) -> int:
        """Add two numbers"""
        return a + b

    @server.tool(annotations=ToolAnnotations(read_only_hint=read_only))
    def lookup(term: str) -> str:
        """Look up a term"""
        return f"definition of {term}"

    @server.tool()
    async def slow(seconds: float, ctx: Context) -> str:
        """Wait, reporting progress"""
        await ctx.report_progress(0.5, 1.0, "half way")
        await asyncio.sleep(seconds)
        return "done"

    @server.tool()
    def big() -> dict:
        """A large structured answer"""
        return {"rows": ["x" * 100 for _ in range(400)]}

    @server.resource("note://welcome", name="welcome", description="A note")
    def welcome() -> str:
        return "Welcome to the demo"

    @server.prompt()
    def review(topic: str) -> str:
        """Review a topic"""
        return f"Please review {topic}"

    return server


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MIZAN_MCP_ALLOW_PRIVATE_HOSTS", "127.0.0.1")
    monkeypatch.setenv("MIZAN_DEV", "1")
    monkeypatch.delenv("MIZAN_CONNECTORS_KEY", raising=False)
    secrets.reset_cache()
    manager = ConnectorManager()
    monkeypatch.setattr(manager_module, "manager", manager)
    monkeypatch.setattr(tools_module, "manager", manager)
    import api.connectors as api

    monkeypatch.setattr(api, "manager", manager)
    yield manager
    secrets.reset_cache()


def add(user, name, transport, **config):
    return store.add_server(user.user_id, {"name": name, "transport": transport, **config})


# ── transports ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("transport", ["http", "sse"])
async def test_connect_list_and_call_over_http_and_sse(env, transport):
    manager = env
    mcp = tools_server(instructions="Use add for sums.")
    app = mcp.streamable_http_app() if transport == "http" else mcp.sse_app()
    served = Served(app)
    path = "/mcp" if transport == "http" else "/sse"
    try:
        record = add(ALICE, "Demo", transport, url=served.base + path)
        await manager.connect(ALICE.user_id, record["id"])
        result = await manager.call(ALICE.user_id, "mcp__demo__add", {"a": 2, "b": 3})
        assert result["content"] == "5" and result["structured"] == {"result": 5}
        saved = store.get_server(ALICE.user_id, record["id"])
        assert saved["status"] == "connected" and saved["instructions"] == "Use add for sums."
        assert saved["capabilities"]["resources"] is True
        names = {tool["name"] for tool in saved["tools"]}
        assert {"add", "lookup", "slow", "big"} <= names
        # Resources become two read-only tools; a resource link is readable through them.
        offered = {schema["name"] for schema in tools_module.user_tool_schemas(ALICE.user_id)}
        assert {"mcp__demo__resources_list", "mcp__demo__resources_read"} <= offered
        listed = await manager.call(ALICE.user_id, "mcp__demo__resources_list", {})
        assert listed["resources"][0]["uri"] == "note://welcome"
        read = await manager.call(
            ALICE.user_id, "mcp__demo__resources_read", {"uri": "note://welcome"}
        )
        assert read["content"] == "Welcome to the demo"
        # The server's instructions ride on its tools' descriptions only.
        add_schema = next(
            s
            for s in tools_module.user_tool_schemas(ALICE.user_id)
            if s["name"] == "mcp__demo__add"
        )
        assert "Server note: Use add for sums." in add_schema["description"]
        big = await manager.call(ALICE.user_id, "mcp__demo__big", {})
        assert big["truncated"] and len(big["content"]) == manager_module.MAX_RESULT_CHARS
        connection = manager.connections[(ALICE.user_id, record["id"])]
        http_client = connection.http_client
        test = await manager.test(ALICE.user_id, record["id"])
        assert test["ok"] and test["tools"] >= 4 and test["latency_ms"] >= 0
        if transport == "http":
            # The HTTP client MIZAN made is closed with its connection (the SDK
            # closes only clients it made itself).
            assert http_client is not None and http_client.is_closed
        await manager.shutdown()
        assert not manager.connections
        assert any("connected" in line for line in manager.log_lines(ALICE.user_id, record["id"]))
    finally:
        await manager.shutdown()
        served.stop()


async def test_progress_reaches_the_live_chat(env):
    from agents.events import bind_event_sink

    manager = env
    served = Served(tools_server().streamable_http_app())
    events = []

    async def sink(kind, payload):
        events.append((kind, payload))

    try:
        record = add(ALICE, "Demo", "http", url=served.base + "/mcp")
        await manager.connect(ALICE.user_id, record["id"])
        with bind_event_sink(sink):
            result = await manager.call(ALICE.user_id, "mcp__demo__slow", {"seconds": 0})
        assert result["content"] == "done"
        progress = [payload for kind, payload in events if kind == "tool_progress"]
        assert progress and progress[0]["message"] == "half way"
        assert progress[0]["tool"] == "mcp__demo__slow"
    finally:
        await manager.shutdown()
        served.stop()


async def test_a_restarted_server_is_reconnected_and_the_call_retried(env):
    manager = env
    manager.client_mode = "legacy"  # a 2025-era session the server can forget
    served = Served(tools_server().streamable_http_app())
    port = served.port
    try:
        record = add(ALICE, "Demo", "http", url=served.base + "/mcp")
        await manager.connect(ALICE.user_id, record["id"])
        first = await manager.call(ALICE.user_id, "mcp__demo__add", {"a": 1, "b": 1})
        assert first["content"] == "2"
        old = manager.connections[(ALICE.user_id, record["id"])]
        served.stop()
        served = Served(tools_server().streamable_http_app(), port=port)
        # The new server does not know the old session ("Session not found"): the
        # request never ran, so MIZAN reconnects and sends it again once.
        again = await manager.call(ALICE.user_id, "mcp__demo__add", {"a": 2, "b": 2})
        assert again["content"] == "4", again
        fresh = manager.connections[(ALICE.user_id, record["id"])]
        assert fresh is not old and fresh.alive
        assert any(
            "reconnecting" in line for line in manager.log_lines(ALICE.user_id, record["id"])
        )
    finally:
        await manager.shutdown()
        served.stop()


async def test_a_restart_is_invisible_to_a_2026_session(env):
    manager = env
    served = Served(tools_server().streamable_http_app())
    port = served.port
    try:
        record = add(ALICE, "Demo", "http", url=served.base + "/mcp")
        await manager.connect(ALICE.user_id, record["id"])
        served.stop()
        served = Served(tools_server().streamable_http_app(), port=port)
        again = await manager.call(ALICE.user_id, "mcp__demo__add", {"a": 2, "b": 2})
        assert again["content"] == "4", again
    finally:
        await manager.shutdown()
        served.stop()


async def test_a_local_process_that_exits_is_started_again(env, monkeypatch, tmp_path):
    manager = env
    script = tmp_path / "local_server.py"
    script.write_text(STDIO_SERVER)
    monkeypatch.setenv("MIZAN_MCP_HOST_STDIO", "all")
    record = add(
        ALICE,
        "Local",
        "stdio",
        command=sys.executable,
        args=[str(script)],
        runtime="host",
        env={"PYTHONPATH": ":".join(sys.path)},
    )
    first = await manager.connect(ALICE.user_id, record["id"])
    pid = int((await manager.call(ALICE.user_id, "mcp__local__pid", {}))["content"])
    os.kill(pid, signal.SIGKILL)
    for _ in range(100):  # the owner notices the session ended
        if not first.alive:
            break
        await asyncio.sleep(0.05)
    assert not first.alive
    again = await manager.call(ALICE.user_id, "mcp__local__pid", {})
    assert int(again["content"]) != pid
    await manager.shutdown()


async def test_health_check_closes_a_connection_that_stopped_answering(env, monkeypatch):
    manager = env
    served = Served(tools_server().streamable_http_app())
    try:
        record = add(ALICE, "Demo", "http", url=served.base + "/mcp")
        await manager.connect(ALICE.user_id, record["id"])
        connection = manager.connections[(ALICE.user_id, record["id"])]
        monkeypatch.setattr(manager_module, "HEALTH_IDLE_SECONDS", -1)
        await manager.check_health()  # alive: the ping is answered
        assert connection.alive and (ALICE.user_id, record["id"]) in manager.connections

        async def unanswered():
            raise manager_module.ConnectorError("no answer")

        monkeypatch.setattr(connection.client.session, "send_ping", unanswered)
        await manager.check_health()
        assert (ALICE.user_id, record["id"]) not in manager.connections
        assert (
            manager.live_status(ALICE.user_id, store.get_server(ALICE.user_id, record["id"]))[0]
            == "disconnected"
        )
    finally:
        await manager.shutdown()
        served.stop()


# ── timeouts ─────────────────────────────────────────────────────────────


async def test_a_server_that_never_starts_gives_a_typed_timeout(env, monkeypatch):
    manager = env
    monkeypatch.setenv("MIZAN_MCP_HOST_STDIO", "all")
    record = add(
        ALICE,
        "Sleepy",
        "stdio",
        command=sys.executable,
        args=["-c", "import time; time.sleep(60)"],
        runtime="host",
        timeouts={"connect_s": 1},
    )
    store.update_server(
        ALICE.user_id,
        record["id"],
        tools=[{"name": "nap", "exposed": "mcp__sleepy__nap", "fingerprint": "x"}],
    )
    started = time.monotonic()
    result = await manager.call(ALICE.user_id, "mcp__sleepy__nap", {})
    assert result["code"] == "connector_timeout", result
    assert time.monotonic() - started < 10
    saved = store.get_server(ALICE.user_id, record["id"])
    assert saved["status"] == "error" and "within 1 seconds" in saved["last_error"]
    await manager.shutdown()


async def test_a_slow_tool_gives_a_typed_timeout(env):
    manager = env
    served = Served(tools_server().streamable_http_app())
    try:
        record = add(ALICE, "Demo", "http", url=served.base + "/mcp", timeouts={"call_s": 1})
        await manager.connect(ALICE.user_id, record["id"])
        result = await manager.call(ALICE.user_id, "mcp__demo__slow", {"seconds": 5})
        assert result["code"] == "connector_timeout" and "1 seconds" in result["error"]
    finally:
        await manager.shutdown()
        served.stop()


# ── host stdio ──────────────────────────────────────────────────────────


STDIO_SERVER = """
import sys
from mcp.server.mcpserver import MCPServer
server = MCPServer("local")

@server.tool(annotations={"readOnlyHint": True})
def pid() -> str:
    '''The process id'''
    import os
    return str(os.getpid())

@server.tool()
def where() -> str:
    '''Where the process runs'''
    import os
    return os.getcwd() + "|" + os.environ.get("HOME", "") + "|" + os.environ.get("SECRET_X", "")

print("local server starting", file=sys.stderr, flush=True)
server.run("stdio")
"""


async def test_host_stdio_policy_is_checked_at_every_launch(env, monkeypatch, tmp_path):
    manager = env
    script = tmp_path / "local_server.py"
    script.write_text(STDIO_SERVER)
    monkeypatch.setenv("MIZAN_MCP_HOST_STDIO", "all")
    monkeypatch.setenv("SECRET_X", "from-the-backend")  # never inherited
    record = add(
        ALICE,
        "Local",
        "stdio",
        command=sys.executable,
        args=[str(script)],
        runtime="host",
        env={"PYTHONPATH": ":".join(sys.path)},
    )
    await manager.connect(ALICE.user_id, record["id"])
    result = await manager.call(ALICE.user_id, "mcp__local__where", {})
    cwd, home, leaked = result["content"].split("|")
    assert cwd == home and "connectors/home" in home and leaked == ""
    assert any("local server starting" in line for line in manager.log_lines("alice", record["id"]))
    await manager.shutdown()
    # The administrator turns host processes off: the next launch is refused.
    monkeypatch.setenv("MIZAN_MCP_HOST_STDIO", "off")
    refused = await manager.call(ALICE.user_id, "mcp__local__where", {})
    assert refused["code"] == "connector_not_allowed", refused
    saved = store.get_server(ALICE.user_id, record["id"])
    assert saved["error_permanent"] and not manager_module.offered(saved)
    # "admin": the owner's role now decides, not the role when it was added.
    monkeypatch.setenv("MIZAN_MCP_HOST_STDIO", "admin")
    store.update_server(ALICE.user_id, record["id"], status="disconnected", error_permanent=False)
    principal = bind_principal(ALICE)
    try:
        refused = await manager.call(ALICE.user_id, "mcp__local__where", {})
    finally:
        reset_principal(principal)
    assert refused["code"] == "connector_not_allowed"
    manager.role_lookup = lambda user_id: ["admin"]
    allowed = await manager.call(ALICE.user_id, "mcp__local__where", {})
    assert "connectors/home" in allowed["content"]
    await manager.shutdown()


# ── pinning ─────────────────────────────────────────────────────────────


async def test_a_read_only_tool_that_stops_saying_so_is_held(env):
    manager = env
    current = {"server": tools_server(read_only=True)}
    manager.client_factory = lambda connection: Client(current["server"])
    record = add(ALICE, "Demo", "http", url="https://demo.example/mcp")
    await manager.connect(ALICE.user_id, record["id"])
    lookup = next(
        t for t in store.get_server(ALICE.user_id, record["id"])["tools"] if t["name"] == "lookup"
    )
    assert lookup["read_only"] and not lookup.get("held")
    await manager.shutdown()
    current["server"] = tools_server(read_only=False)  # the rug pull
    await manager.connect(ALICE.user_id, record["id"])
    saved = store.get_server(ALICE.user_id, record["id"])
    lookup = next(t for t in saved["tools"] if t["name"] == "lookup")
    assert lookup["held"] == "changed"
    assert lookup["previous"]["annotations"] == {"readOnlyHint": True}
    view = store.public(saved)["tools"]
    shown = next(t for t in view if t["name"] == "lookup")
    assert shown["held"] is True and shown["held_reason"] == "changed"
    assert shown["previous"]["description"] == "Look up a term"
    offered = {s["name"] for s in tools_module.user_tool_schemas(ALICE.user_id)}
    assert "mcp__demo__lookup" not in offered and "mcp__demo__add" in offered
    manager_module.trust_tool(ALICE.user_id, record["id"], "lookup")
    assert "mcp__demo__lookup" in {s["name"] for s in tools_module.user_tool_schemas("alice")}
    await manager.shutdown()


async def test_pins_made_before_hints_counted_are_upgraded_not_held(env):
    manager = env
    server = tools_server()
    manager.client_factory = lambda connection: Client(server)
    record = add(ALICE, "Demo", "http", url="https://demo.example/mcp")
    await manager.connect(ALICE.user_id, record["id"])
    await manager.shutdown()
    saved = store.get_server(ALICE.user_id, record["id"])
    # As an older MIZAN stored them: first-version fingerprints, no pin_version.
    legacy = {
        t["name"]: fingerprint(t["raw_description"], t["input_schema"]) for t in saved["tools"]
    }
    old_tools = [
        {k: v for k, v in t.items() if k not in {"annotations", "raw_description"}}
        | {"fingerprint": legacy[t["name"]]}
        for t in saved["tools"]
    ]
    store.update_server(ALICE.user_id, record["id"], pins=legacy, pin_version=None, tools=old_tools)
    await manager.connect(ALICE.user_id, record["id"])
    upgraded = store.get_server(ALICE.user_id, record["id"])
    assert not [t["name"] for t in upgraded["tools"] if t.get("held")]
    assert not [t["name"] for t in upgraded["tools"] if t.get("new")]
    assert upgraded["pin_version"] == 2
    assert upgraded["pins"]["lookup"] == next(
        t["fingerprint"] for t in upgraded["tools"] if t["name"] == "lookup"
    )
    await manager.shutdown()


async def test_new_tools_are_offered_and_marked_until_seen(env):
    manager = env
    current = {"server": MCPServer("demo")}

    @current["server"].tool()
    def first() -> str:
        """First tool"""
        return "1"

    manager.client_factory = lambda connection: Client(current["server"])
    record = add(ALICE, "Demo", "http", url="https://demo.example/mcp")
    await manager.connect(ALICE.user_id, record["id"])
    assert not any(t.get("new") for t in store.get_server("alice", record["id"])["tools"])
    await manager.shutdown()

    @current["server"].tool()
    def second() -> str:
        """Second tool"""
        return "2"

    await manager.connect(ALICE.user_id, record["id"])
    view = store.public(store.get_server("alice", record["id"]))
    second_tool = next(t for t in view["tools"] if t["name"] == "second")
    assert second_tool["new"] and not second_tool["held"] and view["counts"]["new"] == 1
    assert "mcp__demo__second" in {s["name"] for s in tools_module.user_tool_schemas("alice")}
    manager_module.acknowledge_tools("alice", record["id"], ["second"])
    assert store.public(store.get_server("alice", record["id"]))["counts"]["new"] == 0
    await manager.shutdown()


# ── secrets ─────────────────────────────────────────────────────────────


def test_key_rotation_and_a_loud_unreadable_secret(env, monkeypatch, caplog, tmp_path):
    first, second = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    monkeypatch.setenv("MIZAN_CONNECTORS_KEY", first)
    sealed = secrets.seal({"Authorization": "Bearer one"})
    record = add(ALICE, "Keyed", "http", url="https://k.example/mcp", headers={"X-Key": "v"})
    # Rotation: the new key first encrypts, the old one still decrypts.
    monkeypatch.setenv("MIZAN_CONNECTORS_KEY", f"{second},{first}")
    assert secrets.unseal(sealed) == {"Authorization": "Bearer one"}
    resealed = secrets.reseal(sealed)
    assert Fernet(second.encode()).decrypt(resealed.encode())
    # The old key gone: nothing is silently treated as "no secret".
    monkeypatch.setenv("MIZAN_CONNECTORS_KEY", second)
    with caplog.at_level(logging.ERROR, logger="mizan.connectors.secrets"):
        assert secrets.unseal(sealed, "default") == "default"
    assert "cannot be decrypted" in caplog.text
    with pytest.raises(secrets.SecretsUnreadable):
        secrets.unseal(sealed, strict=True)
    server = store.get_server(ALICE.user_id, record["id"])
    view = store.public(server)
    assert view["status"] == "error" and "cannot be decrypted" in view["last_error"]
    assert secrets.unseal(resealed) == {"Authorization": "Bearer one"}
    # Without the variable, the key file is used (created on first use, as before).
    monkeypatch.delenv("MIZAN_CONNECTORS_KEY")
    token = secrets.seal("file-key")
    assert (tmp_path / "connectors.key").exists() and secrets.unseal(token) == "file-key"


async def test_an_unreadable_connector_fails_with_a_typed_error(env, monkeypatch):
    manager = env
    monkeypatch.setenv("MIZAN_CONNECTORS_KEY", Fernet.generate_key().decode())
    record = add(ALICE, "Keyed", "http", url="https://k.example/mcp", headers={"X-Key": "v"})
    store.update_server(
        ALICE.user_id,
        record["id"],
        tools=[{"name": "t", "exposed": "mcp__keyed__t", "fingerprint": "x"}],
    )
    monkeypatch.setenv("MIZAN_CONNECTORS_KEY", Fernet.generate_key().decode())
    result = await manager.call(ALICE.user_id, "mcp__keyed__t", {})
    assert result["code"] == "secrets_unreadable"
    assert not manager_module.offered(store.get_server(ALICE.user_id, record["id"]))


# ── what the model is offered ───────────────────────────────────────────


async def test_a_connector_waiting_for_sign_in_is_not_offered(env):
    manager = env
    server = tools_server()
    manager.client_factory = lambda connection: Client(server)
    record = add(ALICE, "Demo", "http", url="https://demo.example/mcp")
    await manager.connect(ALICE.user_id, record["id"])
    await manager.shutdown()
    assert tools_module.user_tool_schemas("alice")
    store.update_server("alice", record["id"], status="auth_required")
    assert tools_module.user_tool_schemas("alice") == []
    store.update_server("alice", record["id"], status="error", error_at=time.time())
    assert tools_module.user_tool_schemas("alice") == []  # just failed: not offered for now
    store.update_server("alice", record["id"], error_at=time.time() - 3600)
    assert tools_module.user_tool_schemas("alice")  # later, offered again (a call retries)
    # The API still lists it, with its live status.
    view = manager.live_status("alice", store.get_server("alice", record["id"]))
    assert view[0] == "error"


async def test_policies_never_and_ask(env):
    from agents.specialized import create_agent
    from security.approvals import ApprovalContext, bind_approvals

    manager = env
    server = tools_server()
    manager.client_factory = lambda connection: Client(server)
    record = add(ALICE, "Demo", "http", url="https://demo.example/mcp")
    await manager.connect(ALICE.user_id, record["id"])
    manager_module.set_policy("alice", record["id"], "lookup", "never")
    assert "mcp__demo__lookup" not in {s["name"] for s in tools_module.user_tool_schemas("alice")}
    manager_module.set_policy("alice", record["id"], "add", "ask")
    view = {
        t["name"]: t["policy"]
        for t in store.public(store.get_server("alice", record["id"]))["tools"]
    }
    assert view["add"] == "ask" and view["lookup"] == "never" and view["big"] == "allow"
    izn = SimpleNamespace(
        check_permission=lambda *a, **k: {
            "allowed": True,
            "reason": "",
            "requires_approval": False,
        },
        get_policy=lambda *a, **k: None,
    )
    agent = create_agent("general", name="Connected", wali=SimpleNamespace(), izn=izn)
    principal = bind_principal(ALICE)
    try:
        # Auto mode never asks, except for a tool its owner set to "ask".
        with bind_approvals(ApprovalContext(ALICE.user_id, "s", "auto")):
            asked = await agent._execute_tool_safe("mcp__demo__add", {"a": 1, "b": 2})
            assert asked.get("declined") is True  # asked; no one here to answer → declined
            plain = await agent._execute_tool_safe("mcp__demo__big", {})
            assert plain.get("truncated") and "declined" not in plain
        refused = await agent._execute_tool_safe("mcp__demo__add", {"a": 1, "b": 2})
        assert refused.get("approval_required") is True
    finally:
        reset_principal(principal)
        await manager.shutdown()


def test_structured_content_is_capped():
    class Result:
        content = []
        structured_content = {"rows": ["y" * 1000 for _ in range(100)]}
        is_error = False

    receipt = map_result(Result())
    assert "structured" not in receipt and receipt["structured_truncated"]
    assert len(receipt["structured_preview"]) == manager_module.MAX_RESULT_CHARS

    class Link:
        type, uri, name = "resource_link", "file:///report.txt", "report"

    class Linked:
        content, structured_content, is_error = [Link()], None, False

    assert "mcp__docs__resources_read" in map_result(Linked(), "docs")["content"]


# ── registry ────────────────────────────────────────────────────────────


def test_registry_entries_carry_install_commands():
    npm = registry.install_for(
        {
            "registryType": "npm",
            "identifier": "@acme/mcp",
            "version": "1.2.3",
            "transport": {"type": "stdio"},
            "runtimeArguments": [{"type": "named", "name": "--node-options", "value": "x"}],
            "packageArguments": [
                {"type": "positional", "valueHint": "root", "isRequired": True},
                {"type": "named", "name": "--verbose", "value": "true"},
                {"type": "named", "name": "--optional"},
            ],
            "environmentVariables": [
                {"name": "ACME_TOKEN", "isRequired": True, "isSecret": True, "description": "t"}
            ],
        }
    )
    assert npm["command"] == "npx" and npm["supported"]
    assert npm["args"] == [
        "-y",
        "--node-options",
        "x",
        "@acme/mcp@1.2.3",
        "<root>",
        "--verbose",
        "true",
    ]
    assert npm["env_vars"][0] | {} == {
        "name": "ACME_TOKEN",
        "description": "t",
        "required": True,
        "secret": True,
    }
    pypi = registry.install_for(
        {"registryType": "pypi", "identifier": "mcp-server-time", "version": "0.6.2"}
    )
    assert pypi["command"] == "uvx" and pypi["args"] == ["mcp-server-time==0.6.2"]
    oci = registry.install_for(
        {
            "registryType": "oci",
            "identifier": "ghcr.io/acme/mcp",
            "version": "2.0",
            "environmentVariables": [{"name": "API_KEY"}],
        }
    )
    assert oci["args"] == ["run", "-i", "--rm", "-e", "API_KEY", "ghcr.io/acme/mcp:2.0"]
    assert (
        registry.install_for({"registryType": "nuget", "identifier": "Acme"})["supported"] is False
    )
    http_only = registry.install_for(
        {"registryType": "npm", "identifier": "x", "transport": {"type": "streamable-http"}}
    )
    assert http_only["supported"] is False


async def test_registry_search_keeps_active_entries_and_marks_official(monkeypatch):
    meta = "io.modelcontextprotocol.registry/official"
    data = {
        "servers": [
            {
                "server": {
                    "name": "com.notion/notion",
                    "remotes": [{"type": "streamable-http", "url": "https://mcp.notion.com/mcp"}],
                },
                "_meta": {meta: {"status": "active"}},
            },
            {
                "server": {
                    "name": "io.github.someone/notion-proxy",
                    "remotes": [{"type": "streamable-http", "url": "https://mcp.notion.com/mcp"}],
                    "repository": {"url": "https://github.com/other/notion-proxy"},
                },
                "_meta": {meta: {"status": "active"}},
            },
            {"server": {"name": "com.old/thing"}, "_meta": {meta: {"status": "deprecated"}}},
            {"server": {"name": "com.gone/thing"}, "_meta": {meta: {"status": "deleted"}}},
        ],
        "metadata": {"nextCursor": "c2"},
    }
    asked = []

    async def fetch(client, params):
        asked.append(params)
        return data

    registry._cache.clear()
    monkeypatch.setattr(registry, "_fetch", fetch)
    result = await registry.search("no", 10)
    assert "search" not in asked[0]  # the registry refuses searches under 3 letters
    names = {server["name"]: server["official"] for server in result["servers"]}
    assert names == {"com.notion/notion": True, "io.github.someone/notion-proxy": False}
    assert result["next_cursor"] == "c2"
    assert registry.REGISTRY_URL.endswith("/v0.1/servers")


# ── API ─────────────────────────────────────────────────────────────────


def api_client(user):
    import api.connectors as api

    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[api.require_auth] = lambda: user
    return TestClient(app)


def test_api_presets_patch_merge_policy_and_logs(env, monkeypatch):
    alice = api_client(ALICE)
    presets = alice.get("/api/connectors/presets").json()["presets"]
    ids = {preset["id"] for preset in presets}
    assert {
        "github",
        "notion",
        "linear",
        "huggingface",
        "filesystem",
        "fetch",
        "forge-cortex",
    } <= ids
    for preset in presets:
        assert set(preset) >= {"id", "name", "description", "transport", "auth", "docs_url"}
        assert preset["auth"] in {"oauth", "headers", "none"}
        assert preset["docs_url"].startswith("https://")
        if preset["transport"] == "stdio":
            assert preset["command"] and preset["args"]
        else:
            assert preset["url"].startswith("https://")
    created = alice.post(
        "/api/connectors",
        json={
            "name": "Hub",
            "transport": "sse",
            "url": "https://127.0.0.1:9/sse",
            "headers": {"Authorization": "Bearer a", "X-Team": "t1"},
            "timeouts": {"connect_s": 12},
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["transport"] == "sse" and body["timeouts"] == {"connect_s": 12, "call_s": 120}
    assert body["auth"]["type"] == "headers" and body["status"] == "disconnected"
    server_id = body["id"]
    patched = alice.patch(
        f"/api/connectors/{server_id}",
        json={"headers": {"X-Team": None, "X-Extra": "e"}, "name": "Hub 2"},
    ).json()
    assert patched["header_names"] == ["Authorization", "X-Extra"] and patched["name"] == "Hub 2"
    headers = store.secrets_of(store.get_server(ALICE.user_id, server_id))[0]
    assert headers == {"Authorization": "Bearer a", "X-Extra": "e"}
    # A pre-registered OAuth client (no dynamic registration) with scopes.
    oauth = alice.patch(
        f"/api/connectors/{server_id}",
        json={
            "headers": {"Authorization": None},
            "oauth": {"client_id": "cid", "client_secret": "s3", "scopes": ["read", "write"]},
        },
    ).json()
    assert oauth["auth"] == {
        "type": "oauth",
        "signed_in": False,
        "expires_at": None,
        "client_id": "cid",
        "scopes": ["read", "write"],
    }
    raw = (store._path(ALICE.user_id)).read_text()
    assert "s3" not in json.dumps(json.loads(raw)["servers"][0].get("oauth_config"))
    assert store.oauth_client_secret(store.get_server(ALICE.user_id, server_id)) == "s3"
    listed = alice.get("/api/connectors").json()
    assert set(listed["capabilities"]) >= {"sandbox_stdio", "host_stdio", "runner_available"}
    assert listed["connectors"][0]["counts"] == {"total": 0, "enabled": 0, "held": 0, "new": 0}
    assert alice.get(f"/api/connectors/{server_id}/logs").json()["lines"]
    assert (
        alice.post(
            f"/api/connectors/{server_id}/tools/policy", json={"tool": "nope", "policy": "ask"}
        ).status_code
        == 404
    )
    bob = api_client(BOB)
    assert bob.get(f"/api/connectors/{server_id}/logs").status_code == 404
    assert alice.post(f"/api/connectors/{server_id}/signout").json() == {"ok": True}
    metadata = alice.get("/api/connectors/oauth/client-metadata.json").json()
    assert metadata["client_id"].endswith("/api/connectors/oauth/client-metadata.json")
    assert metadata["redirect_uris"][0].endswith("/api/connectors/oauth/callback")


def async_api(user):
    """The router in this test's own event loop (OAuth waits on this loop's futures)."""
    import api.connectors as api

    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[api.require_auth] = lambda: user
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


# ── OAuth against a local authorization server ──────────────────────────


class AuthorizationServer:
    """A tiny OAuth 2.1 authorization server: metadata, dynamic registration,
    authorize (approves at once), token (code with PKCE, refresh), revocation."""

    def __init__(self, lifetime: int = 1, registration: bool = True):
        self.lifetime = lifetime
        self.registration = registration
        self.clients: dict[str, dict] = {}
        self.codes: dict[str, dict] = {}
        self.tokens: dict[str, float] = {}
        self.refresh: dict[str, str] = {}
        self.grants: list[str] = []
        self.revoked: list[str] = []
        self.authorized: list[dict] = []
        self.served = Served(
            Starlette(
                routes=[
                    Route("/.well-known/oauth-authorization-server", self.metadata),
                    Route("/register", self.register, methods=["POST"]),
                    Route("/authorize", self.authorize),
                    Route("/token", self.token, methods=["POST"]),
                    Route("/revoke", self.revoke, methods=["POST"]),
                ]
            )
        )
        self.base = self.served.base

    async def metadata(self, request: Request):
        return JSONResponse(
            {
                "issuer": self.base,
                "authorization_endpoint": f"{self.base}/authorize",
                "token_endpoint": f"{self.base}/token",
                **({"registration_endpoint": f"{self.base}/register"} if self.registration else {}),
                "revocation_endpoint": f"{self.base}/revoke",
                "response_types_supported": ["code"],
                "grant_types_supported": ["authorization_code", "refresh_token"],
                "code_challenge_methods_supported": ["S256"],
                "token_endpoint_auth_methods_supported": ["none"],
            }
        )

    async def register(self, request: Request):
        body = await request.json()
        client_id = token_secrets.token_hex(8)
        self.clients[client_id] = body
        return JSONResponse({**body, "client_id": client_id}, status_code=201)

    async def authorize(self, request: Request):
        params = request.query_params
        code = token_secrets.token_hex(8)
        self.codes[code] = {
            "challenge": params["code_challenge"],
            "client_id": params["client_id"],
            "redirect_uri": params["redirect_uri"],
        }
        self.authorized.append({"client_id": params["client_id"], "scope": params.get("scope")})
        target = f"{params['redirect_uri']}?" + urlencode({"code": code, "state": params["state"]})
        return RedirectResponse(target, status_code=302)

    def _issue(self) -> dict:
        access, refresh = token_secrets.token_hex(12), token_secrets.token_hex(12)
        self.tokens[access] = time.time() + self.lifetime
        self.refresh[refresh] = access
        return {
            "access_token": access,
            "token_type": "Bearer",
            "expires_in": self.lifetime,
            "refresh_token": refresh,
        }

    async def token(self, request: Request):
        form = dict(await request.form())
        self.grants.append(form["grant_type"])
        if form["grant_type"] == "authorization_code":
            code = self.codes.pop(form["code"], None)
            verifier = form.get("code_verifier", "")
            digest = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            if code is None or digest.decode().rstrip("=") != code["challenge"]:
                return JSONResponse({"error": "invalid_grant"}, status_code=400)
            return JSONResponse(self._issue())
        if form["grant_type"] == "refresh_token" and form.get("refresh_token") in self.refresh:
            self.refresh.pop(form["refresh_token"])
            return JSONResponse(self._issue())
        return JSONResponse({"error": "invalid_grant"}, status_code=400)

    async def revoke(self, request: Request):
        form = dict(await request.form())
        self.revoked.append(form.get("token_type_hint", ""))
        self.tokens.pop(form.get("token", ""), None)
        self.refresh.pop(form.get("token", ""), None)
        return Response(status_code=200)

    def stop(self) -> None:
        self.served.stop()


class Verifier:
    def __init__(self, server: AuthorizationServer):
        self.server = server

    async def verify_token(self, token: str):
        expires = self.server.tokens.get(token)
        if expires is None or expires < time.time():
            return None
        return AccessToken(token=token, client_id="mizan", scopes=[], expires_at=int(expires) + 1)


def protected_server(authorization: AuthorizationServer, port: int):
    url = f"http://127.0.0.1:{port}/mcp"
    mcp = MCPServer(
        "secured",
        token_verifier=Verifier(authorization),
        auth=AuthSettings(
            issuer_url=authorization.base, resource_server_url=url, validate_token_resource=False
        ),
    )

    @mcp.tool()
    def whoami() -> str:
        """Who is calling"""
        return "signed in"

    return mcp.streamable_http_app(), url


async def sign_in(manager, record, user=ALICE):
    connection = await manager.connect(user.user_id, record["id"], interactive=True)
    assert connection.auth_url, "the protected server should ask for authorization"
    async with httpx.AsyncClient() as browser:
        page = await browser.get(connection.auth_url)  # the person approves
    query = parse_qs(urlsplit(page.headers["location"]).query)
    state, code = query["state"][0], query["code"][0]
    assert not manager.oauth.complete(state, code, user_id=BOB.user_id)  # bound to the starter
    assert manager.oauth.complete(state, code, user_id=user.user_id)
    result = await manager.wait_oauth(user.user_id, record["id"], timeout=20)
    assert result == {"state": "connected"}, result
    return connection


async def test_oauth_tokens_refresh_without_a_browser(env):
    manager = env
    authorization = AuthorizationServer(lifetime=1)
    port = free_port()
    app, url = protected_server(authorization, port)
    resource = Served(app, port=port)
    try:
        record = add(ALICE, "Secured", "http", url=url)
        store.update_server(
            ALICE.user_id,
            record["id"],
            callback_url="http://127.0.0.1:9/api/connectors/oauth/callback",
        )
        await sign_in(manager, record)
        saved = store.get_server(ALICE.user_id, record["id"])
        oauth = store.secrets_of(saved)[2]
        assert oauth["expires_at"] > time.time() - 5 and oauth["revocation_endpoint"].endswith(
            "/revoke"
        )
        assert (
            store.public(saved)["auth"]["signed_in"] and store.public(saved)["auth"]["expires_at"]
        )
        assert authorization.grants == ["authorization_code"]
        await manager.shutdown()
        await asyncio.sleep(1.5)  # the access token expires
        # A new connection knows the stored token expired: it refreshes first, no browser.
        result = await manager.call(ALICE.user_id, "mcp__secured__whoami", {})
        assert result["content"] == "signed in", result
        assert authorization.grants == ["authorization_code", "refresh_token"]
        await manager.shutdown()
        # A token stored before expiries were kept: the server's 401 is answered by a
        # refresh, not by a new authorization.
        await asyncio.sleep(1.5)
        store.change_oauth(ALICE.user_id, record["id"], lambda o: o.pop("expires_at", None))
        result = await manager.call(ALICE.user_id, "mcp__secured__whoami", {})
        assert result["content"] == "signed in", result
        assert authorization.grants[-1] == "refresh_token" and len(authorization.grants) == 3
        assert (
            manager.oauth_status(ALICE.user_id, store.get_server("alice", record["id"]))["state"]
            == "connected"
        )
        # Sign out: revoked at the server (RFC 7009) and forgotten here.
        await manager.signout(ALICE.user_id, record["id"])
        assert set(authorization.revoked) == {"refresh_token", "access_token"}
        assert not store.public(store.get_server("alice", record["id"]))["auth"]["signed_in"]
        refused = await manager.call(ALICE.user_id, "mcp__secured__whoami", {})
        assert refused["code"] == "auth_required"
        assert not tools_module.user_tool_schemas("alice")  # waiting for sign-in: not offered
    finally:
        await manager.shutdown()
        resource.stop()
        authorization.stop()


async def test_oauth_callback_is_finished_only_by_the_user_who_started_it(env):
    manager = env
    authorization = AuthorizationServer(lifetime=60)
    port = free_port()
    app, url = protected_server(authorization, port)
    resource = Served(app, port=port)
    try:
        record = add(ALICE, "Secured", "http", url=url)
        store.update_server(
            ALICE.user_id,
            record["id"],
            callback_url="http://127.0.0.1:9/api/connectors/oauth/callback",
        )
        connection = await manager.connect(ALICE.user_id, record["id"], interactive=True)
        async with httpx.AsyncClient() as browser:
            page = await browser.get(connection.auth_url)
        query = parse_qs(urlsplit(page.headers["location"]).query)
        state, code = query["state"][0], query["code"][0]
        async with async_api(ALICE) as alice, async_api(BOB) as bob:
            callback = await alice.get(
                "/api/connectors/oauth/callback", params={"state": state, "code": code}
            )
            assert callback.status_code == 200 and "/api/connectors/oauth/complete" in callback.text
            status = await alice.get(f"/api/connectors/{record['id']}/oauth/status")
            assert status.json()["state"] == "pending"
            stolen = await bob.post(
                "/api/connectors/oauth/complete", json={"state": state, "code": code}
            )
            assert stolen.status_code == 404
            done = await alice.post(
                "/api/connectors/oauth/complete", json={"state": state, "code": code}
            )
            assert done.json()["state"] == "connected", done.text
            status = await alice.get(f"/api/connectors/{record['id']}/oauth/status")
            assert status.json() == {"state": "connected"}
            used = await alice.get(
                "/api/connectors/oauth/callback", params={"state": state, "code": code}
            )
            assert used.status_code == 400
    finally:
        await manager.shutdown()
        resource.stop()
        authorization.stop()


async def test_oauth_endpoints_must_use_https(monkeypatch):
    from connectors import net_guard

    monkeypatch.delenv("MIZAN_DEV", raising=False)
    with pytest.raises(net_guard.BlockedDestination):
        await net_guard.check_oauth_url("http://127.0.0.1:8000/token")
    with pytest.raises(net_guard.BlockedDestination):
        await net_guard.check_oauth_url("http://auth.example/token")
    monkeypatch.setenv("MIZAN_DEV", "1")
    await net_guard.check_oauth_url("http://127.0.0.1:8000/token")
    with pytest.raises(net_guard.BlockedDestination):
        await net_guard.check_oauth_url("http://auth.example/token")
    hook = net_guard.connector_request_hook("https://mcp.example/mcp")
    with pytest.raises(net_guard.BlockedDestination):
        await hook(SimpleNamespace(url="http://login.example/token"))


async def test_pinned_transport_refuses_a_private_address(monkeypatch):
    import httpx2

    from connectors import net_guard

    monkeypatch.delenv("MIZAN_MCP_ALLOW_PRIVATE_HOSTS", raising=False)

    async def rebinding(host, port, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.7", port))]

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", rebinding)
    async with httpx2.AsyncClient(transport=net_guard.pinned_transport()) as client:
        with pytest.raises(net_guard.BlockedDestination):
            await client.get("https://rebind.example/mcp")


async def test_elicitation_is_asked_in_the_live_chat(env):
    import mcp_types as types

    from agents.events import bind_event_sink
    from connectors.elicitation import broker
    from security.approvals import ApprovalContext, bind_approvals

    manager = env
    server = MCPServer("asker")

    @server.tool()
    async def ask(ctx: Context) -> str | types.InputRequiredResult:
        """Ask the person their name"""
        if ctx.input_responses:
            answer = ctx.input_responses["name"]
            return f"{answer.action}:{(answer.content or {}).get('name', '')}"
        return types.InputRequiredResult(
            input_requests={
                "name": types.ElicitRequest(
                    params=types.ElicitRequestFormParams(
                        message="What is your name?",
                        requested_schema={
                            "type": "object",
                            "properties": {"name": {"type": "string"}},
                            "required": ["name"],
                        },
                    )
                )
            }
        )

    served = Served(server.streamable_http_app())
    asked = []

    async def sink(kind, payload):
        asked.append((kind, payload))
        if kind == "elicitation":
            assert broker.resolve(ALICE.user_id, payload["id"], "accept", {"name": "Zaid"})

    try:
        record = add(ALICE, "Asker", "http", url=served.base + "/mcp")
        await manager.connect(ALICE.user_id, record["id"])
        with (
            bind_event_sink(sink),
            bind_approvals(ApprovalContext(ALICE.user_id, "chat-1", "auto", interactive=True)),
        ):
            answered = await manager.call(ALICE.user_id, "mcp__asker__ask", {})
        assert answered["content"] == "accept:Zaid", answered
        question = next(payload for kind, payload in asked if kind == "elicitation")
        assert question["message"] == "What is your name?" and question["server"] == "Asker"
        # With no one watching, MIZAN declines for the person.
        unattended = await manager.call(ALICE.user_id, "mcp__asker__ask", {})
        assert unattended["content"].startswith("decline"), unattended
    finally:
        await manager.shutdown()
        served.stop()


async def test_a_pre_registered_client_signs_in_where_there_is_no_registration(env):
    manager = env
    authorization = AuthorizationServer(lifetime=60, registration=False)
    port = free_port()
    app, url = protected_server(authorization, port)
    resource = Served(app, port=port)
    try:
        record = add(
            ALICE,
            "Secured",
            "http",
            url=url,
            oauth={"client_id": "registered-by-hand", "scopes": ["files.read", "offline_access"]},
        )
        store.update_server(
            ALICE.user_id,
            record["id"],
            callback_url="http://127.0.0.1:9/api/connectors/oauth/callback",
        )
        await sign_in(manager, record)
        assert authorization.authorized[-1] == {
            "client_id": "registered-by-hand",
            "scope": "files.read offline_access",
        }
        assert not authorization.clients  # nothing was registered dynamically
        result = await manager.call(ALICE.user_id, "mcp__secured__whoami", {})
        assert result["content"] == "signed in"
    finally:
        await manager.shutdown()
        resource.stop()
        authorization.stop()


async def test_a_registration_for_an_old_callback_is_dropped(env):
    from connectors.manager import EncryptedTokenStorage

    record = add(ALICE, "Secured", "http", url="https://s.example/mcp")
    store.change_oauth(
        ALICE.user_id,
        record["id"],
        lambda o: o.update(
            client_info={
                "client_id": "old",
                "redirect_uris": ["https://old.example/api/connectors/oauth/callback"],
            }
        ),
    )
    storage = EncryptedTokenStorage(
        ALICE.user_id, record["id"], callback="https://new.example/api/connectors/oauth/callback"
    )
    assert await storage.get_client_info() is None  # MIZAN_PUBLIC_URL changed: register again
    assert "client_info" not in store.secrets_of(store.get_server("alice", record["id"]))[2]


async def test_prompts_tool_list_changes_and_server_logs(env):
    manager = env
    server = tools_server()
    manager.client_factory = lambda connection: Client(server)
    record = add(ALICE, "Demo", "http", url="https://demo.example/mcp")
    connection = await manager.connect(ALICE.user_id, record["id"])
    prompts = await manager.list_prompts(ALICE.user_id, record["id"])
    assert prompts[0]["name"] == "review" and prompts[0]["arguments"][0]["name"] == "topic"
    filled = await manager.get_prompt(ALICE.user_id, record["id"], "review", {"topic": "sabr"})
    assert filled["messages"][0]["text"] == "Please review sabr"
    resources = await manager.list_resources(ALICE.user_id, record["id"])
    assert resources == [
        {
            "uri": "note://welcome",
            "name": "welcome",
            "description": "A note",
            "mime_type": "text/plain",
        }
    ]

    @server.tool()
    def later() -> str:
        """Added while connected"""
        return "later"

    import mcp_types as types

    await connection.on_message(types.ToolListChangedNotification())
    for _ in range(50):
        if any(t["name"] == "later" for t in store.get_server("alice", record["id"])["tools"]):
            break
        await asyncio.sleep(0.05)
    later_tool = next(
        t for t in store.get_server("alice", record["id"])["tools"] if t["name"] == "later"
    )
    assert later_tool["new"] is True
    await connection.on_log(
        types.LoggingMessageNotificationParams(level="warning", logger="sync", data="quota low")
    )
    assert any(
        "[warning] sync: quota low" in line for line in manager.log_lines("alice", record["id"])
    )
    await manager.shutdown()


def test_moving_from_the_key_file_to_the_variable_keeps_old_values(env, monkeypatch, tmp_path):
    sealed = secrets.seal("sealed with the file")  # no variable: connectors.key is made
    assert (tmp_path / "connectors.key").exists()
    monkeypatch.setenv("MIZAN_CONNECTORS_KEY", Fernet.generate_key().decode())
    assert secrets.unseal(sealed, strict=True) == "sealed with the file"
    fresh = secrets.seal("sealed with the variable")
    (tmp_path / "connectors.key").unlink()  # the file key retired
    assert secrets.unseal(fresh, strict=True) == "sealed with the variable"
    with pytest.raises(secrets.SecretsUnreadable):
        secrets.unseal(sealed, strict=True)
