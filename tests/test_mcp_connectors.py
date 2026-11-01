"""MCP connectors: naming, storage, live calls against an in-process server, isolation."""

import asyncio
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mcp import Client
from mcp.server.mcpserver import MCPServer

from agents.specialized import create_agent
from connectors import naming, net_guard, secrets, store
from connectors.manager import ConnectorManager, OAuthBroker, map_result, resolve_tool
from security.approvals import ApprovalContext, bind_approvals
from security.auth import TokenPayload, bind_principal, reset_principal

ALICE = TokenPayload("alice", "Alice", ["user"], 9999999999, 0, "alice-token")
BOB = TokenPayload("bob", "Bob", ["user"], 9999999999, 0, "bob-token")


def demo_server() -> MCPServer:
    server = MCPServer("demo")

    @server.tool()
    def add(a: int, b: int) -> int:
        """Add two numbers"""
        return a + b

    @server.tool(annotations={"readOnlyHint": True})
    def lookup(term: str) -> str:
        """Look up a term"""
        return f"definition of {term}"

    @server.tool()
    def explode() -> str:
        """Always fails"""
        raise ValueError("boom")

    return server


@pytest.fixture
def connectors(tmp_path, monkeypatch):
    import connectors.manager as manager_module
    import connectors.tools as tools_module

    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    manager = ConnectorManager()
    server = demo_server()
    manager.client_factory = lambda connection: Client(server)
    monkeypatch.setattr(manager_module, "manager", manager)
    monkeypatch.setattr(tools_module, "manager", manager)
    record = store.add_server(
        ALICE.user_id,
        {
            "name": "Demo Tools",
            "transport": "http",
            "url": "https://demo.example/mcp",
            "headers": {"Authorization": "Bearer secret-token"},
        },
    )
    return manager, record


def test_tool_naming_and_schema_sanitize():
    assert naming.tool_name("github", "list_issues") == "mcp__github__list_issues"
    long = naming.tool_name("server_sixteen_c", "a" * 80)
    assert len(long) <= 64 and long.startswith("mcp__server_sixteen_c__")
    assert naming.tool_name("x", "weird name/with.dots") == "mcp__x__weird_name_with_dots"
    schema = naming.input_schema({"$schema": "x", "type": "string"})
    assert schema == {"type": "object", "properties": {}}
    huge = {
        "properties": {f"p{i}": {"description": "d" * 300} for i in range(60)},
        "required": ["p1"],
    }
    assert len(str(naming.input_schema(huge))) < 20_000
    assert naming.slug("GitHub (Official)!") == "github_official"


def test_secrets_are_sealed_and_public_view_hides_them(tmp_path, monkeypatch):
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    record = store.add_server(
        ALICE.user_id,
        {
            "name": "Notion",
            "transport": "http",
            "url": "https://x.example/mcp",
            "headers": {"Authorization": "Bearer abc123"},
        },
    )
    raw = (tmp_path / "connectors").glob("*.json").__next__().read_text()
    assert "abc123" not in raw
    assert store.secrets_of(record)[0] == {"Authorization": "Bearer abc123"}
    view = store.public(record)
    assert view["header_names"] == ["Authorization"] and "abc123" not in str(view)
    assert secrets.unseal("not-a-token", "fallback") == "fallback"
    duplicate = store.add_server(
        ALICE.user_id, {"name": "Notion", "transport": "http", "url": "https://y.example"}
    )
    assert duplicate["slug"] != record["slug"]


async def test_owner_task_connects_lists_and_calls(connectors):
    manager, record = connectors
    connection = await manager.connect(ALICE.user_id, record["id"])
    assert connection.alive
    saved = store.get_server(ALICE.user_id, record["id"])
    assert saved["status"] == "connected"
    exposed = {tool["name"]: tool for tool in saved["tools"]}
    assert exposed["lookup"]["read_only"] is True and exposed["add"]["read_only"] is False
    results = await asyncio.gather(
        manager.call(ALICE.user_id, "mcp__demo_tools__add", {"a": 2, "b": 3}),
        manager.call(ALICE.user_id, "mcp__demo_tools__lookup", {"term": "sabr"}),
    )
    assert results[0]["content"] == "5" and results[0]["structured"] == {"result": 5}
    assert "definition of sabr" in results[1]["content"]
    failure = await manager.call(ALICE.user_id, "mcp__demo_tools__explode", {})
    assert "explode" in failure["error"]  # the server reports its own error text
    await manager.shutdown()
    assert not manager.connections


async def test_idle_connections_close_and_reconnect(connectors, monkeypatch):
    import connectors.manager as manager_module

    manager, record = connectors
    await manager.connect(ALICE.user_id, record["id"])
    monkeypatch.setattr(manager_module, "IDLE_SECONDS", -1)
    await manager.reap_idle()
    assert not manager.connections
    again = await manager.call(ALICE.user_id, "mcp__demo_tools__add", {"a": 1, "b": 1})
    assert again["content"] == "2"
    await manager.shutdown()


async def test_cross_user_isolation_and_disabled_tools(connectors):
    manager, record = connectors
    await manager.connect(ALICE.user_id, record["id"])
    assert resolve_tool(BOB.user_id, "mcp__demo_tools__add") is None
    assert (
        "Unknown connector tool"
        in (await manager.call(BOB.user_id, "mcp__demo_tools__add", {}))["error"]
    )
    store.update_server(ALICE.user_id, record["id"], disabled_tools=["add"])
    assert resolve_tool(ALICE.user_id, "mcp__demo_tools__add") is None
    assert resolve_tool(ALICE.user_id, "mcp__demo_tools__lookup") is not None
    await manager.shutdown()


async def test_agent_sees_connector_tools_and_readonly_skips_approval(connectors):
    manager, record = connectors
    await manager.connect(ALICE.user_id, record["id"])
    izn = MagicMock()
    izn.check_permission.return_value = {"allowed": True, "reason": "", "requires_approval": False}
    agent = create_agent("general", name="Connected", wali=MagicMock(), izn=izn)
    agent.ai_client = MagicMock(supports_tools=True)
    principal = bind_principal(ALICE)
    try:
        names = {schema["name"] for schema in agent.get_tool_schemas()}
        assert {"mcp__demo_tools__add", "mcp__demo_tools__lookup"} <= names
        assert agent._chat_tool_allowed("mcp__demo_tools__add")
        assert not agent._chat_tool_allowed("mcp__someone_else__add")
        with bind_approvals(ApprovalContext(ALICE.user_id, "s", "ask")):
            # Read-only connector tools run; changing ones would wait (no sink → declined).
            result = await agent._execute_tool_safe("mcp__demo_tools__lookup", {"term": "ilm"})
            assert "definition of ilm" in result["content"]
            declined = await agent._execute_tool_safe("mcp__demo_tools__add", {"a": 1, "b": 2})
            assert declined["declined"] is True
        with bind_approvals(ApprovalContext(ALICE.user_id, "s", "plan")):
            plan_names = {schema["name"] for schema in agent.get_tool_schemas()}
            assert (
                "mcp__demo_tools__lookup" in plan_names and "mcp__demo_tools__add" not in plan_names
            )
        assert (await agent._execute_tool_safe("mcp__demo_tools__add", {"a": 4, "b": 4}))[
            "content"
        ] == "8"
    finally:
        reset_principal(principal)
        await manager.shutdown()


def test_result_mapping_is_error():
    class Text:
        type, text = "text", "nope"

    class Result:
        content, structured_content, is_error = [Text()], None, True

    assert map_result(Result()) == {"error": "nope", "content": "nope"}


async def test_guard_blocks_private_ips():
    for url in (
        "http://127.0.0.1:9000/mcp",
        "https://169.254.169.254/x",
        "https://user:pw@example.com",
    ):
        with pytest.raises(net_guard.BlockedDestination):
            await net_guard.check_url(url)
    with pytest.raises(net_guard.BlockedDestination):
        await net_guard.check_url("http://example.com/mcp", require_https=True)


async def test_oauth_state_single_use_callback():
    broker = OAuthBroker()
    future = broker.open("state-1", "alice", "srv")
    assert broker.complete("state-1", "code-xyz")
    assert (await future).code == "code-xyz"
    assert not broker.complete("state-1", "again")
    assert not broker.complete("unknown", "x")


def test_connectors_api_owner_scope_and_validation(tmp_path, monkeypatch):
    from api import connectors as api

    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))

    def client(user):
        app = FastAPI()
        app.include_router(api.router)
        app.dependency_overrides[api.require_auth] = lambda: user
        return TestClient(app)

    alice, bob = client(ALICE), client(BOB)
    blocked = alice.post(
        "/api/connectors", json={"name": "x", "transport": "http", "url": "https://127.0.0.1/mcp"}
    )
    assert blocked.status_code == 422
    stdio = alice.post(
        "/api/connectors",
        json={"name": "files", "transport": "stdio", "command": "uvx", "args": ["mcp-server-time"]},
    )
    assert stdio.status_code == 200 and stdio.json()["runtime"] == "sandbox"
    server_id = stdio.json()["id"]
    assert bob.get(f"/api/connectors/{server_id}").status_code == 404
    assert bob.delete(f"/api/connectors/{server_id}").status_code == 404
    assert (
        alice.patch(f"/api/connectors/{server_id}", json={"env": {"BAD NAME": "x"}}).status_code
        == 422
    )
    listed = alice.get("/api/connectors").json()
    assert listed["capabilities"]["host_stdio"] is False and len(listed["connectors"]) == 1
    page = alice.get("/api/connectors/oauth/callback", params={"state": "nope", "code": "c"})
    assert page.status_code == 400 and "expired" in page.text
    assert alice.delete(f"/api/connectors/{server_id}").status_code == 200
