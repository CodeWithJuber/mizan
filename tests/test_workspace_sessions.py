"""Server sandbox sessions: container helper, egress policy, sync, previews, runner API."""

import asyncio
import base64
import contextlib
import hashlib
import importlib.util
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from api import workspace_sessions
from security.auth import TokenPayload
from workspace import egress_proxy, session_agent, session_client, sessions
from workspace.runner import app as runner_app
from workspace.store import WorkspaceStore

USER = TokenPayload("alice", "Alice", ["user"], 9999999999, 0, "alice-token")
TOKEN = "t" * 48
AGENT = Path(session_agent.__file__)


def b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


@pytest.fixture
def agent_root(tmp_path, monkeypatch):
    root, state = tmp_path / "workspace", tmp_path / "state"
    root.mkdir()
    monkeypatch.setattr(session_agent, "ROOT", root)
    monkeypatch.setattr(session_agent, "STATE", state)
    return root


@pytest.fixture
def runner_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MIZAN_WORKSPACE_RUNNER_URL", "http://runner.test")
    monkeypatch.setenv("MIZAN_WORKSPACE_RUNNER_TOKEN", TOKEN)
    monkeypatch.setenv("MIZAN_WORKSPACE_ROOT", str(tmp_path / "projects"))
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    return tmp_path


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


# ── Container-side helper ────────────────────────────────────────────────


def test_sync_manifest_and_export_skip_dependency_folders(agent_root):
    session_agent.sync(
        {
            "files": {"src/app.py": b64("print(1)"), "node_modules/x/i.js": b64("no")},
            "directories": ["src", "empty"],
        }
    )
    assert (agent_root / "src/app.py").read_text() == "print(1)"
    assert not (agent_root / "node_modules").exists()
    (agent_root / "node_modules/pkg").mkdir(parents=True)
    (agent_root / "node_modules/pkg/index.js").write_text("big")
    (agent_root / "dist").mkdir()
    (agent_root / "dist/out.js").write_text("built")
    (agent_root / "new.txt").write_text("made")
    listing = session_agent.manifest({})
    assert set(listing["files"]) == {"src/app.py", "new.txt"}
    assert "empty" in listing["directories"]
    exported = session_agent.export(
        {"baseline": {"src/app.py": sha("print(1)"), "gone.txt": sha("x"), "dist/old.js": "0"}}
    )
    assert set(exported["files"]) == {"new.txt"}
    # Deleted outside dependency folders only; dist/ files stay with the project store.
    assert exported["deleted"] == ["gone.txt"]
    over = session_agent.export({"baseline": {}, "max_files": 2})
    assert over["error"] == "quota"


@pytest.mark.parametrize("path", ["../escape", "/abs", "a/../../b", "a\\b", "a//b"])
def test_sync_rejects_unsafe_paths(agent_root, path):
    with pytest.raises(ValueError):
        session_agent.sync({"files": {path: b64("x")}})


def test_sync_replaces_conflicting_entries_and_deletes(agent_root):
    (agent_root / "a").write_text("file where a folder is needed")
    session_agent.sync({"files": {"a/b.txt": b64("nested")}})
    assert (agent_root / "a/b.txt").read_text() == "nested"
    session_agent.sync({"delete": ["a/b.txt", "node_modules/keep"]})
    assert not (agent_root / "a/b.txt").exists()


def test_exec_and_service_lifecycle(agent_root):
    result = session_agent.run_command(
        {"command": "echo hi && echo err >&2 && exit 3", "language": "shell", "timeout_s": 10}
    )
    assert (result["stdout"], result["stderr"], result["exit_code"]) == ("hi\n", "err\n", 3)
    slow = session_agent.run_command({"command": "sleep 5", "language": "shell", "timeout_s": 1})
    assert slow["timed_out"] and slow["exit_code"] == 124
    port = free_port()
    started = session_agent.service_start(
        {"port": port, "command": "echo serving $PORT; sleep 30", "mode": "root"}
    )
    assert started["mode"] == "root"
    deadline = time.time() + 5
    while (
        time.time() < deadline
        and "serving" not in session_agent.service_logs({"port": port})["log"]
    ):
        time.sleep(0.2)
    assert f"serving {port}" in session_agent.service_logs({"port": port})["log"]
    assert session_agent.service_list()["services"][0]["alive"] is True
    assert session_agent.service_stop({"port": port})["stopped"] is True
    assert session_agent.service_list()["services"] == []
    with pytest.raises(ValueError):
        session_agent.service_start({"port": 80, "command": "x"})


def test_commands_keep_caches_on_the_session_volume(agent_root):
    """/tmp is noexec in a session; a native addon unpacked into a cache must run."""
    result = session_agent.run_command(
        {
            "command": 'echo "$XDG_CACHE_HOME $npm_config_cache"',
            "language": "shell",
            "timeout_s": 10,
        }
    )
    assert result["stdout"].split() == [f"{agent_root}/.cache", f"{agent_root}/.cache/npm"]
    assert session_agent.heavy(".cache/swc-native-65534/v1/swc.node")


# ── Bridge: framed TCP over a child's stdio ───────────────────────────────


async def test_bridge_relays_http_requests(tmp_path, monkeypatch):
    port = free_port()
    (tmp_path / "hello.txt").write_text("bridged")
    server = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
        cwd=tmp_path,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(50):
            with contextlib.suppress(OSError), socket.create_connection(("127.0.0.1", port), 0.2):
                break
            await asyncio.sleep(0.1)
        bridge = sessions.Bridge("unused", port)

        async def local_start():
            bridge.process = await asyncio.create_subprocess_exec(
                sys.executable, "-I", str(AGENT), "bridge", str(port),
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                env={**os.environ, "MIZAN_SESSION_STATE": str(tmp_path / "s")},
            )  # fmt: skip
            bridge.reader = asyncio.create_task(bridge._read())

        monkeypatch.setattr(bridge, "start", local_start)
        await bridge.start()
        responses = await asyncio.gather(
            *[
                sessions.http_through(bridge, "GET", "/hello.txt", [("Accept", "*/*")], b"")
                for _ in range(3)
            ]
        )
        for status, _headers, body in responses:
            assert status == 200
            assert b"".join([chunk async for chunk in body]) == b"bridged"
        status, _, body = await sessions.http_through(bridge, "GET", "/missing", [], b"")
        assert status == 404
        [chunk async for chunk in body]
        await bridge.close()
    finally:
        server.kill()
        server.wait()


# ── Egress proxy policy ───────────────────────────────────────────────────


def test_egress_allowlist_rules():
    rules = egress_proxy.allowlist("registry.npmjs.org, .githubusercontent.com")
    assert egress_proxy.host_allowed("registry.npmjs.org", rules)
    assert egress_proxy.host_allowed("objects.githubusercontent.com", rules)
    assert not egress_proxy.host_allowed("evil-registry.npmjs.org.attacker.com", rules)
    assert not egress_proxy.host_allowed("githubusercontent.com.evil", rules)
    assert egress_proxy.host_allowed("pypi.org", egress_proxy.allowlist(""))
    assert egress_proxy.parse_connect("CONNECT pypi.org:443 HTTP/1.1") == ("pypi.org", 443)
    assert egress_proxy.parse_connect("GET http://pypi.org/ HTTP/1.1") is None


async def test_egress_proxy_refuses_unlisted_hosts_ports_and_private_addresses():
    assert await egress_proxy.public_address("localhost", 443) is None
    proxy = egress_proxy.Proxy(egress_proxy.allowlist("localhost,pypi.org"))
    server = await asyncio.start_server(proxy.handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        for request in (
            b"CONNECT example.com:443 HTTP/1.1\r\n\r\n",
            b"CONNECT pypi.org:80 HTTP/1.1\r\n\r\n",
            b"CONNECT localhost:443 HTTP/1.1\r\n\r\n",
            b"GET http://pypi.org/ HTTP/1.1\r\nHost: pypi.org\r\n\r\n",
        ):
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(request)
            await writer.drain()
            assert (await reader.read(100)).startswith(b"HTTP/1.1 403")
            writer.close()


# ── Backend client: capabilities and three-way sync ──────────────────────


def test_preview_capability_binds_key_nonce_and_runner_secret(runner_env, monkeypatch):
    key, nonce = "a" * 32, "b" * 32
    cap = session_client.capability(key, nonce)
    assert session_client.parse_capability(cap) == (key, nonce)
    assert session_client.parse_capability(cap[:-1] + ("0" if cap[-1] != "0" else "1")) is None
    assert session_client.parse_capability("c" * 32 + nonce + cap[64:]) is None
    monkeypatch.setenv("MIZAN_WORKSPACE_RUNNER_TOKEN", "u" * 48)
    assert session_client.parse_capability(cap) is None
    assert session_client.preview_url(key, nonce, 5173).endswith("/5173/")


class FakeRunner:
    """The runner's session endpoints over an in-memory working copy."""

    def __init__(self):
        self.files: dict[str, str] = {}
        self.nonce = "n" * 32
        self.running = False

    async def call(self, method, path, body=None, timeout=60):
        action = path.rsplit("/", 1)[-1]
        if method == "PUT":
            self.running, self.nonce = True, body["nonce"]
            return {"running": True, "nonce": self.nonce, "egress": True}
        if method == "GET":
            return {"running": self.running, "nonce": self.nonce, "services": []}
        if method == "DELETE":
            self.running = False
            return {"running": False}
        if action == "manifest":
            data = {
                p: hashlib.sha256(base64.b64decode(v)).hexdigest() for p, v in self.files.items()
            }
            return {"files": data, "directories": []}
        if action == "sync":
            for path in body["delete"]:
                self.files.pop(path, None)
            self.files.update(body["files"])
            return {"written": len(body["files"])}
        if action == "export":
            baseline = body["baseline"]
            changed = {
                p: v
                for p, v in self.files.items()
                if baseline.get(p) != hashlib.sha256(base64.b64decode(v)).hexdigest()
            }
            return {"files": changed, "deleted": [p for p in baseline if p not in self.files]}
        if action == "exec":
            self.files["out.txt"] = b64("generated")
            return {"stdout": "ok", "stderr": "", "exit_code": 0}
        raise AssertionError(path)


async def test_reconcile_merges_editor_and_session_changes(runner_env, monkeypatch):
    fake = FakeRunner()
    monkeypatch.setattr(session_client, "call", fake.call)
    store = WorkspaceStore(USER.user_id)
    workspace = store.create("demo")["id"]
    store.write(workspace, "a.txt", "one")
    store.write(workspace, "b.txt", "two")
    started = await session_client.start(USER.user_id, workspace)
    assert started["sync"]["pushed"] == ["a.txt", "b.txt"]
    assert base64.b64decode(fake.files["a.txt"]) == b"one"
    # Editor changes a.txt; the session changes b.txt, adds c.txt and edits a.txt too.
    store.write(workspace, "a.txt", "editor")
    fake.files.update({"b.txt": b64("session"), "c.txt": b64("new"), "a.txt": b64("stale")})
    fake.files["node_modules/x.js"] = b64("dependency")
    result = await session_client.reconcile(USER.user_id, workspace)
    assert result["pushed"] == ["a.txt"] and result["conflicts"] == ["a.txt"]
    assert sorted(result["pulled"]) == ["b.txt", "c.txt"]
    assert store.read(workspace, "a.txt")["content"] == "editor"
    assert store.read(workspace, "b.txt")["content"] == "session"
    assert base64.b64decode(fake.files["a.txt"]) == b"editor"
    # A deletion in the session reaches the store; nothing changes when idle.
    fake.files.pop("c.txt")
    assert (await session_client.reconcile(USER.user_id, workspace))["pulled"] == ["c.txt"]
    idle = await session_client.reconcile(USER.user_id, workspace)
    assert idle["pushed"] == [] and idle["pulled"] == []
    ran = await session_client.execute(USER.user_id, workspace, "make", "shell", 30)
    assert ran["changed_files"] == ["out.txt"] and ran["sandbox"] == "session"
    assert store.read(workspace, "out.txt")["content"] == "generated"


async def test_reconcile_requires_a_running_session(runner_env, monkeypatch):
    fake = FakeRunner()
    monkeypatch.setattr(session_client, "call", fake.call)
    store = WorkspaceStore(USER.user_id)
    workspace = store.create("demo")["id"]
    with pytest.raises(HTTPException) as error:
        await session_client.reconcile(USER.user_id, workspace)
    assert error.value.status_code == 409


# ── Public preview route ─────────────────────────────────────────────────


def fake_runner_app() -> FastAPI:
    app = FastAPI()

    @app.api_route("/sessions/{key}/proxy/{port}/{path:path}", methods=["GET", "POST"])
    async def proxy(key: str, port: int, path: str, request: Request):

        if request.headers.get("authorization") != f"Bearer {TOKEN}":
            return JSONResponse({"detail": "no"}, 401)
        if request.headers.get("x-mizan-nonce") != "b" * 32:
            return JSONResponse(
                {"detail": "No running sandbox session"}, 404, {"X-Mizan-Runner": "error"}
            )
        return Response(
            f"target={request.headers['x-mizan-target']}",
            headers={
                "content-type": "text/html",
                "set-cookie": "steal=1",
                "clear-site-data": '"storage"',
                "x-frame-options": "ALLOWALL",
            },
        )

    return app


def test_preview_route_is_public_sandboxed_and_strips_unsafe_headers(runner_env, monkeypatch):
    transport = httpx.ASGITransport(app=fake_runner_app())
    real = httpx.AsyncClient
    monkeypatch.setattr(
        workspace_sessions.httpx,
        "AsyncClient",
        lambda **kwargs: real(
            transport=transport, **{k: v for k, v in kwargs.items() if k != "trust_env"}
        ),
    )
    app = FastAPI()
    app.include_router(workspace_sessions.router)
    client = TestClient(app, raise_server_exceptions=False)
    url = session_client.preview_url("a" * 32, "b" * 32, 5173)
    response = client.get(url + "src/main.tsx?v=1%202")
    assert response.status_code == 200
    assert response.text == f"target={url}src/main.tsx?v=1%202"
    assert response.headers["content-security-policy"].startswith("sandbox allow-scripts")
    assert "allow-same-origin" not in response.headers["content-security-policy"]
    assert response.headers["access-control-allow-origin"] == "*"
    assert "set-cookie" not in response.headers and "clear-site-data" not in response.headers
    assert "x-frame-options" not in response.headers
    stale = session_client.preview_url("a" * 32, "c" * 32, 5173)
    assert client.get(stale).status_code == 404
    assert client.get(url[:-30] + "0" * 30 + "/").status_code == 404
    assert client.get(url.rstrip("/"), follow_redirects=False).status_code == 307


def runner_client(monkeypatch, app: FastAPI) -> None:
    transport = httpx.ASGITransport(app=app)
    real = httpx.AsyncClient
    monkeypatch.setattr(
        session_client.httpx,
        "AsyncClient",
        lambda **kwargs: real(
            transport=transport, **{k: v for k, v in kwargs.items() if k != "trust_env"}
        ),
    )


def test_a_runner_older_than_sessions_reads_as_unavailable_not_missing(runner_env, monkeypatch):
    # The first managed install served only these two routes.
    old = FastAPI()
    old.get("/health")(lambda: {"available": True, "isolated": True})
    old.post("/run")(lambda: {})
    runner_client(monkeypatch, old)
    for method, path, words in (
        ("GET", f"/sessions/{'a' * 32}", "predates sandbox sessions"),
        ("POST", "/browse", "predates the browser sandbox"),
    ):
        with pytest.raises(HTTPException) as refused:
            asyncio.run(session_client.call(method, path, {} if method == "POST" else None))
        assert refused.value.status_code == 503
        assert words in refused.value.detail and "next deploy" in refused.value.detail


def test_a_real_missing_session_stays_a_404(runner_env, monkeypatch):
    current = FastAPI()

    @current.get("/sessions/{key}/manifest")
    async def manifest(key: str):
        return JSONResponse(
            {"detail": "No running sandbox session"}, 404, {"X-Mizan-Runner": "error"}
        )

    runner_client(monkeypatch, current)
    with pytest.raises(HTTPException) as refused:
        asyncio.run(session_client.call("GET", f"/sessions/{'a' * 32}/manifest"))
    assert refused.value.status_code == 404
    assert refused.value.detail == "No running sandbox session"


# ── Runner API and agent tool wiring ─────────────────────────────────────


def test_runner_session_routes_require_the_runner_token(monkeypatch):
    monkeypatch.setenv("MIZAN_WORKSPACE_RUNNER_TOKEN", TOKEN)
    client = TestClient(runner_app)
    assert client.get(f"/sessions/{'a' * 32}").status_code == 401
    assert client.put(f"/sessions/{'a' * 32}", json={"nonce": "b" * 32}).status_code == 401
    wrong = {"Authorization": "Bearer " + "x" * 48}
    assert client.get(f"/sessions/{'a' * 32}/services/1/logs", headers=wrong).status_code == 401
    for path in ("terminal", "stdio"):
        with (
            pytest.raises(WebSocketDisconnect) as closed,
            client.websocket_connect(f"/sessions/{'a' * 32}/{path}", headers=wrong) as socket_,
        ):
            socket_.receive_bytes()
        assert closed.value.code == 4401


def test_sandbox_tool_is_a_shipped_workspace_tool():
    from skills.builtin.coding_workspace import CodingWorkspaceSkill

    skill = CodingWorkspaceSkill()
    schemas = {item["name"]: item for item in skill.get_tool_schemas()}
    sandbox = schemas["workspace_sandbox"]["input_schema"]
    assert sandbox["required"] == ["action"]
    assert "serve" in sandbox["properties"]["action"]["enum"]
    assert schemas["workspace_run"]["input_schema"]["properties"]["timeout_s"]["maximum"] == 900
    assert "workspace_sandbox" in skill.get_tools()


# ── Real Docker sessions (CI builds the runtime image) ───────────────────


def docker_ready() -> bool:
    try:
        return (
            subprocess.run(
                ["docker", "image", "inspect", sessions.runtime_image()],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            ).returncode
            == 0
        )
    except (OSError, subprocess.TimeoutExpired):
        return False


@pytest.mark.skipif(
    not docker_ready(), reason="Build the workspace runtime image for Docker checks"
)
class TestRealSessions:
    KEY = hashlib.sha256(b"pytest-session").hexdigest()[:32]
    NONCE = "f" * 32

    @pytest.fixture
    def runner(self, monkeypatch):
        monkeypatch.setenv("MIZAN_WORKSPACE_RUNNER_TOKEN", TOKEN)
        headers = {"Authorization": f"Bearer {TOKEN}"}
        with TestClient(runner_app, headers=headers) as client:
            started = client.put(
                f"/sessions/{self.KEY}",
                json={"nonce": self.NONCE, "preview_prefix": "/api/workspaces/preview/cap"},
            )
            assert started.status_code == 200, started.text
            try:
                yield client
            finally:
                client.delete(f"/sessions/{self.KEY}")

    def run(self, client, command, timeout=60):
        response = client.post(
            f"/sessions/{self.KEY}/exec",
            json={"command": command, "language": "shell", "timeout_s": timeout},
        )
        assert response.status_code == 200, response.text
        return response.json()

    def test_hardening_sync_and_export(self, runner):
        probe = (
            "id -u; test -S /var/run/docker.sock && echo SOCKET; "
            "touch /etc/x 2>/dev/null && echo WRITABLE_ROOT; "
            "python3 -c \"import socket\ntry:\n socket.create_connection(('1.1.1.1',443),timeout=2); print('DIRECT')\nexcept OSError: print('no-direct')\"; "
            "node -e 'console.log(6*7)'"
        )
        out = self.run(runner, probe)["stdout"].split()
        assert out == ["65534", "no-direct", "42"]
        sync = runner.post(
            f"/sessions/{self.KEY}/sync",
            json={"files": {"a.txt": b64("one")}, "directories": ["src"]},
        )
        assert sync.json()["written"] == 1
        self.run(runner, "echo two > b.txt && mkdir -p node_modules/q && echo q > node_modules/q/i")
        exported = runner.post(
            f"/sessions/{self.KEY}/export", json={"baseline": {"a.txt": sha("one")}}
        )
        assert set(exported.json()["files"]) == {"b.txt"}

    def test_project_tools_and_an_executable_cache(self, runner):
        probe = (
            "command -v curl; npm config get allow-scripts; "
            'mkdir -p "$XDG_CACHE_HOME" && cp /bin/true "$XDG_CACHE_HOME/t" && cp /bin/true /tmp/t; '
            '"$XDG_CACHE_HOME/t" && echo cache-runs; /tmp/t 2>/dev/null || echo tmp-noexec'
        )
        out = self.run(runner, probe)["stdout"].split()
        assert out == ["/usr/bin/curl", "esbuild,@swc/core", "cache-runs", "tmp-noexec"]

    def test_service_preview_terminal_and_stdio(self, runner):
        runner.post(
            f"/sessions/{self.KEY}/sync",
            json={"files": {"index.html": b64("<h1>served</h1>")}},
        )
        started = runner.post(
            f"/sessions/{self.KEY}/services",
            json={
                "port": 8000,
                "command": "python3 -m http.server $PORT --bind 127.0.0.1",
                "mode": "root",
            },
        )
        assert started.status_code == 200
        headers = {
            "X-Mizan-Nonce": self.NONCE,
            "X-Mizan-Prefix": "/api/workspaces/preview/cap/8000",
            "X-Mizan-Target": "/api/workspaces/preview/cap/8000/index.html",
        }
        body = ""
        for _ in range(30):
            response = runner.get(f"/sessions/{self.KEY}/proxy/8000/x", headers=headers)
            body = response.text
            if response.status_code == 200:
                break
            time.sleep(0.3)
        assert body == "<h1>served</h1>"
        local = self.run(runner, "curl -sS http://localhost:8000/index.html")
        assert local["stdout"] == "<h1>served</h1>", local["stderr"]
        wrong = runner.get(
            f"/sessions/{self.KEY}/proxy/8000/x", headers={**headers, "X-Mizan-Nonce": "0" * 32}
        )
        assert wrong.status_code == 404
        with runner.websocket_connect(f"/sessions/{self.KEY}/terminal?cols=80&rows=20") as term:
            term.send_bytes(b"echo TERM_$((6*7)) CACHE_$XDG_CACHE_HOME\n")
            seen = b""
            deadline = time.time() + 10
            while b"CACHE_/workspace/.cache" not in seen and time.time() < deadline:
                seen += term.receive_bytes()
        assert b"TERM_42 CACHE_/workspace/.cache" in seen
        with runner.websocket_connect(f"/sessions/{self.KEY}/stdio") as pipe:
            pipe.send_text(
                json.dumps(
                    {
                        "argv": [
                            "python3",
                            "-c",
                            "import sys\nfor l in sys.stdin: print(l.strip()[::-1], flush=True)",
                        ]
                    }
                )
            )
            pipe.send_text('{"x":1}')
            assert pipe.receive_text() == '}1:"x"{'

    def test_egress_proxy_refuses_unlisted_hosts(self, runner):
        script = (
            "python3 - <<'PY'\nimport urllib.request\n"
            "for url in ['https://example.com/', 'https://169.254.169.254/']:\n"
            "    try:\n        urllib.request.urlopen(url, timeout=15); print('OPEN')\n"
            "    except Exception as exc: print('blocked' if '403' in str(exc) else exc)\nPY"
        )
        assert self.run(runner, script)["stdout"].split() == ["blocked", "blocked"]
        if os.getenv("MIZAN_TEST_EGRESS_INTERNET") == "1":
            npm = self.run(runner, "npm view left-pad@1.3.0 version", timeout=120)
            assert npm["stdout"].strip() == "1.3.0", npm["stderr"][-500:]


@pytest.mark.skipif(
    not docker_ready(), reason="Build the workspace runtime image for Docker checks"
)
def test_the_deploy_session_check_passes_against_the_real_runner(monkeypatch):
    """The check every deploy runs after a runner upgrade, here on CI's Docker."""
    import uvicorn

    spec = importlib.util.spec_from_file_location(
        "runner_setup_for_session_check",
        Path(__file__).resolve().parents[1] / "scripts/setup_workspace_runner.py",
    )
    setup = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(setup)
    monkeypatch.setenv("MIZAN_WORKSPACE_RUNNER_TOKEN", TOKEN)
    port = free_port()
    server = uvicorn.Server(
        uvicorn.Config(runner_app, host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    key, nonce = hashlib.sha256(b"deploy-session-check").hexdigest()[:32], "e" * 32

    def phase(name: str) -> dict:
        result = subprocess.run(
            [sys.executable, "-I", "-", name, key, nonce],
            input=setup.SESSION_SMOKE_SCRIPT,
            capture_output=True,
            text=True,
            timeout=600,
            env={
                "PATH": os.environ["PATH"],
                "MIZAN_WORKSPACE_RUNNER_URL": f"http://127.0.0.1:{port}",
                "MIZAN_WORKSPACE_RUNNER_TOKEN": TOKEN,
            },
            check=False,
        )
        return json.loads(result.stdout.strip().splitlines()[-1])

    def inspect(*args: str) -> dict:
        found = subprocess.run(["docker", *args], capture_output=True, text=True, check=True)
        return json.loads(found.stdout)[0]

    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.1)
        started = phase("start")
        try:
            assert started["ok"] is True, started
            runtime = inspect("image", "inspect", sessions.runtime_image())["Id"]
            container = inspect("inspect", "--type", "container", f"mizan-session-{key}")
            setup.validate_session_container(
                container, key, setup.session_limits(started["limits"])
            )
            proxy = inspect("inspect", "--type", "container", setup.SANDBOX_PROXY)
            setup.validate_egress_proxy(proxy, {runtime})
            network = inspect("network", "inspect", f"mizan-session-net-{key}")
            setup.validate_session_network(network, key, {container["Id"], proxy["Id"]})
            if os.getenv("MIZAN_TEST_EGRESS_INTERNET") == "1":
                assert phase("probe") == {"ok": True}
        finally:
            assert phase("stop") == {"ok": True}
        for kind, name in (
            ("container", f"mizan-session-{key}"),
            ("volume", f"mizan-session-{key}"),
            ("network", f"mizan-session-net-{key}"),
        ):
            gone = subprocess.run(["docker", kind, "inspect", name], capture_output=True)
            assert gone.returncode != 0, f"{kind} {name} was left behind"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_terminal_requires_a_subprotocol_token(runner_env, monkeypatch):
    async def fake_auth(authorization=None, x_api_key=None):
        if authorization != "Bearer good-token":
            raise HTTPException(401, "Authentication required")
        return USER

    monkeypatch.setattr(workspace_sessions, "require_auth", fake_auth)
    app = FastAPI()
    app.include_router(workspace_sessions.ws_router)
    client = TestClient(app)
    path = f"/ws/workspaces/{'a' * 32}/terminal"
    for protocols in ([], ["mizan.terminal", "bearer.wrong"]):
        with (
            pytest.raises(WebSocketDisconnect) as closed,
            client.websocket_connect(path, subprotocols=protocols) as socket_,
        ):
            socket_.receive_bytes()
        assert closed.value.code == 4401
    # A valid token passes authentication; the missing project is the next refusal.
    with (
        pytest.raises(WebSocketDisconnect) as closed,
        client.websocket_connect(
            path, subprotocols=["mizan.terminal", "bearer.good-token"]
        ) as socket_,
    ):
        socket_.receive_bytes()
    assert closed.value.code == 4404


@pytest.mark.skipif(
    not docker_ready(), reason="Build the workspace runtime image for Docker checks"
)
def test_sessions_cannot_reach_each_other(monkeypatch):
    monkeypatch.setenv("MIZAN_WORKSPACE_RUNNER_TOKEN", TOKEN)
    first, second = (hashlib.sha256(name).hexdigest()[:32] for name in (b"tenant-a", b"tenant-b"))
    headers = {"Authorization": f"Bearer {TOKEN}"}
    with TestClient(runner_app, headers=headers) as client:
        try:
            for key in (first, second):
                started = client.put(f"/sessions/{key}", json={"nonce": "a" * 32})
                assert started.status_code == 200, started.text
            client.post(
                f"/sessions/{first}/services",
                json={"port": 8000, "command": "python3 -m http.server 8000 --bind 0.0.0.0"},
            )
            address = subprocess.run(
                [
                    "docker",
                    "inspect",
                    "--format",
                    "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}",
                    sessions.PREFIX + first,
                ],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.split()[0]
            probe = (
                "import socket,sys\n"
                "def ok(host, port):\n"
                "    try:\n        socket.create_connection((host, port), timeout=3).close(); return 'open'\n"
                "    except OSError: return 'closed'\n"
                f"print(ok('{address}', 8000), ok('egress', 3128))"
            )
            time.sleep(1)
            seen = client.post(
                f"/sessions/{second}/exec",
                json={"command": probe, "language": "python", "timeout_s": 20},
            ).json()
            assert seen["stdout"].split() == ["closed", "open"], seen
        finally:
            for key in (first, second):
                client.delete(f"/sessions/{key}")
