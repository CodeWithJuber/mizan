"""Wara' (Tirmidhi 2518): a package an install would fetch is vetted before it runs.

Refused only on first-hand evidence of harm (the registry does not have the name, or
OSV lists it as malicious); asked when the evidence gives doubt (a new, thin package
whose name is one slip from a popular one); allowed, with a note, when nothing could be
checked. Every network answer here is recorded (httpx.MockTransport): no test reaches
a registry.
"""

import json
import time
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import httpx
import pytest

from agents import events
from agents.specialized import create_agent
from security import approvals, wara
from security.approvals import ApprovalContext, bind_approvals, collecting_held

# ── The parser: which registry packages a command line would fetch ────────


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("pip install requests", [("pypi", "requests")]),
        ("pip3 install -U Flask==3.0.0 'django>=5'", [("pypi", "flask"), ("pypi", "django")]),
        ("python3 -m pip install --quiet numpy", [("pypi", "numpy")]),
        ("python -m pip install typing_extensions", [("pypi", "typing-extensions")]),
        ("uv pip install httpx[http2]", [("pypi", "httpx")]),
        ("uv add rich", [("pypi", "rich")]),
        ("pip install -r requirements.txt", []),
        ("pip install -r requirements.txt pydantic", [("pypi", "pydantic")]),
        ("pip install -e . ./local/pkg", []),
        ("pip install git+https://github.com/x/y.git https://x.org/a.tar.gz", []),
        ("pip install dist/thing-1.0-py3-none-any.whl", []),
        ("pip install --index-url https://private.example/simple internal-lib", []),
        ("pip install $PKG", []),
        ("npm install lodash", [("npm", "lodash")]),
        (
            "npm i -D typescript@^5.4 @types/node@22",
            [("npm", "typescript"), ("npm", "@types/node")],
        ),
        ("pnpm add zod", [("npm", "zod")]),
        ("yarn add react react-dom", [("npm", "react"), ("npm", "react-dom")]),
        ("yarn global add serve", [("npm", "serve")]),
        ("npm install", []),
        ("npm ci", []),
        ("yarn install", []),
        ("npm install ./lib file:../x github:user/repo user/repo x.tgz", []),
        ("npm install --registry https://npm.internal/ secret-thing", []),
        ("npm install my-alias@npm:real-pkg@1.0.0", [("npm", "real-pkg")]),
        ("cd app && npm install express 2>&1 | tail -5", [("npm", "express")]),
        (
            "pip install black > /tmp/log.txt; pip install isort",
            [("pypi", "black"), ("pypi", "isort")],
        ),
        ("pip install \\\n  requests\nnpm i chalk", [("pypi", "requests"), ("npm", "chalk")]),
        ("sudo -H pip install boto3", [("pypi", "boto3")]),
        ("PIP_NO_CACHE_DIR=1 pip install attrs", [("pypi", "attrs")]),
        ("bash -c 'pip install colorama && npm i debug'", [("pypi", "colorama"), ("npm", "debug")]),
        ("echo pip install requests", []),
        ("pip download requests", []),
        ("git commit -m 'pip install x'", []),
        ("pip install 'unterminated", []),
        ("", []),
    ],
)
def test_install_targets(command, expected):
    assert wara.install_targets(command) == expected


def test_tool_targets_read_each_command_tool():
    assert wara.tool_targets("bash", {"command": "pip install six"}) == [("pypi", "six")]
    assert wara.tool_targets("workspace_run", {"command": "npm i left-pad"}) == [
        ("npm", "left-pad")
    ]
    # Python code is a program, not a command line.
    assert (
        wara.tool_targets("workspace_run", {"command": "pip install x", "language": "python"}) == []
    )
    serve = {"action": "serve", "command": "npm install vite && npx vite"}
    assert wara.tool_targets("workspace_sandbox", serve) == [("npm", "vite")]
    assert wara.tool_targets("workspace_sandbox", {"action": "status"}) == []
    assert wara.tool_targets("install_package", {"package": "Requests==2.0"}) == [
        ("pypi", "requests")
    ]
    assert wara.tool_targets("install_package", {"package": "chalk", "manager": "npm"}) == [
        ("npm", "chalk")
    ]
    assert wara.tool_targets("web_search", {"query": "pip install requests"}) == []


# ── Typosquats: one slip from a popular name ───────────────────────────────


def test_close_to_popular():
    assert wara.close_to_popular("pypi", "reqeusts") == "requests"  # transposed
    assert wara.close_to_popular("pypi", "requestss") == "requests"
    assert wara.close_to_popular("npm", "lodahs") == "lodash"
    assert wara.close_to_popular("pypi", "requests") is None  # the popular name itself
    assert wara.close_to_popular("pypi", "rich") is None  # short names are too close to all
    assert wara.close_to_popular("pypi", "numba") is None  # two letters from numpy: unrelated
    assert wara.close_to_popular("pypi", "my-internal-tool") is None


# ── Judgment: hard gates first, then the noisy-OR ──────────────────────────

NOW = time.time()
DAY = 86400.0


def evidence(**fields):
    base = {
        "exists": True,
        "canonical": None,
        "first_published": NOW - 3000 * DAY,
        "versions": 40,
        "malicious": [],
    }
    return wara.Evidence(**{**base, **fields})


def test_judge_refuses_only_on_first_hand_evidence():
    missing = wara.judge("pypi", "reqeusts", evidence(exists=False), NOW)
    assert missing.level == "refuse" and "not on PyPI" in missing.reasons[0]
    bad = wara.judge("npm", "evil-thing", evidence(malicious=["MAL-2025-1234"]), NOW)
    assert bad.level == "refuse" and "MAL-2025-1234" in bad.reasons[0]


def test_judge_asks_when_new_thin_and_close_to_a_popular_name():
    young = wara.judge("pypi", "reqeusts", evidence(first_published=NOW - 2 * DAY, versions=1), NOW)
    assert young.level == "ask" and young.score >= wara.THRESHOLDS["ask"]
    assert any("requests" in reason for reason in young.reasons)
    # Two months old, a few versions, one slip from a popular name: still doubtful.
    squat = wara.judge("npm", "lodahs", evidence(first_published=NOW - 60 * DAY, versions=3), NOW)
    assert squat.level == "ask"


def test_judge_allows_what_has_a_history():
    old = wara.judge("pypi", "requests", evidence(), NOW)
    assert old.level == "ok" and old.score < wara.THRESHOLDS["note"]
    # An old package close to a popular name is noted, not asked (attr vs attrs).
    near = wara.judge("pypi", "attr", evidence(), NOW)
    assert near.level == "note"


def test_judge_never_blocks_on_missing_evidence():
    unknown = wara.judge(
        "pypi",
        "reqeusts",
        evidence(exists=None, first_published=None, versions=None, malicious=None),
        NOW,
    )
    assert unknown.level in {"note", "unknown"}
    assert unknown.level != "refuse" and unknown.score < wara.THRESHOLDS["ask"]


# ── Probing: recorded registry and OSV answers ─────────────────────────────


def iso(days_ago: float) -> str:
    return (datetime.now(UTC) - timedelta(days=days_ago)).isoformat().replace("+00:00", "Z")


class Registry:
    """A recorded PyPI, npm and OSV: each name maps to its packument or 404."""

    def __init__(self, pypi=None, npm=None, malicious=(), fail=False, osv_down=False):
        self.pypi, self.npm = pypi or {}, npm or {}
        self.malicious = set(malicious)
        self.fail = fail
        self.osv_down = osv_down
        self.seen: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(f"{request.method} {request.url}")
        if self.fail:
            raise httpx.ConnectError("offline", request=request)
        url = str(request.url)
        if url.startswith("https://pypi.org/pypi/"):
            name = url.split("/pypi/")[1].split("/json")[0]
            doc = self.pypi.get(name)
            return httpx.Response(200, json=doc) if doc else httpx.Response(404)
        if url.startswith("https://registry.npmjs.org/"):
            name = httpx.URL(url).path.lstrip("/").replace("%2F", "/").replace("%2f", "/")
            doc = self.npm.get(name)
            return httpx.Response(200, json=doc) if doc else httpx.Response(404)
        if url == "https://api.osv.dev/v1/query":
            if self.osv_down:
                return httpx.Response(503)
            asked = json.loads(request.content)["package"]["name"]
            vulns = (
                [{"id": "MAL-2026-77", "summary": "malicious code"}]
                if asked in self.malicious
                else []
            )
            return httpx.Response(200, json={"vulns": vulns})
        return httpx.Response(500)


def pypi_doc(name, days_ago, versions=1):
    releases = {
        f"0.{i}.0": [{"upload_time_iso_8601": iso(days_ago - i * 0.01)}] for i in range(versions)
    }
    return {"info": {"name": name}, "releases": releases}


def npm_doc(days_ago, versions=1):
    return {
        "time": {"created": iso(days_ago), "modified": iso(0)},
        "versions": {f"1.0.{i}": {} for i in range(versions)},
    }


@pytest.fixture
def registry(monkeypatch):
    wara.clear_cache()
    holder: dict = {}

    def install(recorded: Registry) -> Registry:
        holder["registry"] = recorded
        return recorded

    monkeypatch.setattr(
        wara,
        "_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(lambda r: holder["registry"](r))),
    )
    yield install
    wara.clear_cache()


async def test_a_name_no_registry_has_is_refused_and_told_to_no_one_else(registry):
    recorded = registry(Registry())
    verdict = await wara.vet([("pypi", "reqeusts")])
    assert verdict.decision == "refuse" and "reqeusts" in verdict.reason
    # The registry is asked first and alone: OSV never hears of an invented name.
    assert all("osv.dev" not in line for line in recorded.seen)


async def test_a_malicious_package_is_refused(registry):
    registry(Registry(npm={"evil-pkg": npm_doc(400, 9)}, malicious={"evil-pkg"}))
    verdict = await wara.vet([("npm", "evil-pkg")])
    assert verdict.decision == "refuse" and "MAL-2026-77" in verdict.reason


async def test_a_new_package_one_slip_from_a_popular_name_asks(registry):
    registry(Registry(pypi={"reqeusts": pypi_doc("reqeusts", 2)}))
    verdict = await wara.vet([("pypi", "reqeusts")])
    assert verdict.decision == "ask"
    assert "requests" in verdict.reason and "first published" in verdict.reason


async def test_an_established_package_is_allowed_and_remembered(registry):
    recorded = registry(Registry(pypi={"requests": pypi_doc("requests", 4000, 30)}))
    first = await wara.vet([("pypi", "requests")])
    assert first.decision == "allow" and not first.notes
    asked = len(recorded.seen)
    again = await wara.vet([("pypi", "requests")])
    assert again.decision == "allow" and len(recorded.seen) == asked  # from the cache


async def test_an_unreachable_registry_allows_with_a_note(registry):
    registry(Registry(fail=True))
    verdict = await wara.vet([("pypi", "reqeusts"), ("npm", "lodash")])
    assert verdict.decision == "allow"
    assert verdict.notes and "could not be checked" in verdict.notes[0]
    # Missing evidence is not remembered: the next install asks the registry again.
    recorded = registry(Registry(pypi={"reqeusts": pypi_doc("reqeusts", 2)}))
    assert (await wara.vet([("pypi", "reqeusts")])).decision == "ask"
    assert recorded.seen


async def test_a_slow_registry_is_missing_evidence(registry, monkeypatch):
    monkeypatch.setattr(wara, "TIMEOUT_SECONDS", 0.05)

    def slow(request):
        raise httpx.ReadTimeout("slow", request=request)

    registry(slow)
    verdict = await wara.vet([("npm", "lodash")])
    assert verdict.decision == "allow" and verdict.notes


async def test_a_registry_answer_without_osv_is_noted_and_not_remembered(registry):
    recorded = registry(Registry(pypi={"requests": pypi_doc("requests", 4000, 30)}, osv_down=True))
    first = await wara.vet([("pypi", "requests")])
    assert first.decision == "allow"
    assert first.notes and "OSV" in first.notes[0]
    asked = len(recorded.seen)
    again = await wara.vet([("pypi", "requests")])
    assert again.notes and len(recorded.seen) > asked  # partial evidence is asked again


async def test_an_unread_history_is_noted_and_not_remembered(registry, monkeypatch):
    monkeypatch.setattr(wara, "MAX_BODY_BYTES", 16)  # every packument is "too large"
    recorded = registry(Registry(pypi={"requests": pypi_doc("requests", 4000, 30)}))
    first = await wara.vet([("pypi", "requests")])
    assert first.decision == "allow"
    assert first.notes and "age" in first.notes[0]
    asked = len(recorded.seen)
    await wara.vet([("pypi", "requests")])
    assert len(recorded.seen) > asked


@pytest.mark.parametrize(
    "command",
    [
        "pip install --index-url https://private.example/simple internal-lib",
        "pip install --extra-index-url=https://private.example/simple internal-lib",
        "PIP_INDEX_URL=https://private.example/simple pip install internal-lib",
        "export PIP_INDEX_URL=https://private.example/simple && pip install internal-lib",
        "npm install --registry https://npm.internal/ internal-lib",
        "npm_config_registry=https://npm.internal/ npm i internal-lib",
    ],
)
async def test_another_index_is_noted_never_refused(registry, monkeypatch, tmp_path, command):
    monkeypatch.setenv("MIZAN_WARA", "on")
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    recorded = registry(Registry())  # the public registries have no such name
    ran = []
    agent = agent_running(ran)
    result = await agent._execute_tool_safe("bash", {"command": command})
    assert result["ok"] is True and ran
    assert "another index" in result["wara"]["notes"][0]
    assert recorded.seen == []  # a private name is told to no one


def test_install_lists_what_another_index_serves():
    found = wara.tool_install(
        "bash", {"command": "pip install -i https://p/simple a && pip install b"}
    )
    assert found.checked == [("pypi", "b")] and found.elsewhere == [("pypi", "a")]


async def test_the_worst_package_decides(registry):
    registry(
        Registry(
            pypi={"requests": pypi_doc("requests", 4000, 30)},
            npm={"lodahs": npm_doc(1)},
        )
    )
    verdict = await wara.vet([("pypi", "requests"), ("npm", "lodahs"), ("pypi", "nope-zzz")])
    assert verdict.decision == "refuse" and "nope-zzz" in verdict.reason


# ── The gate: refused, asked (even in auto), held, or run ──────────────────


def agent_running(ran, kind="general"):
    izn = MagicMock()
    izn.check_permission.return_value = {"allowed": True, "reason": "", "requires_approval": False}
    agent = create_agent(kind, name="Wara", wali=MagicMock(), izn=izn)
    agent._chat_tool_allowed = lambda name: True

    def tool(name):
        async def handler(**params):
            ran.append((name, params))
            return {"ok": True, "tool": name}

        return handler

    for name in ("bash", "workspace_run", "install_package"):
        agent.tools[name] = tool(name)
    return agent


@pytest.fixture
def gate(registry, monkeypatch, tmp_path):
    monkeypatch.setenv("MIZAN_WARA", "on")
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    approvals._HELD_STORES.clear()
    registry(
        Registry(
            pypi={"requests": pypi_doc("requests", 4000, 30), "reqeusts": pypi_doc("reqeusts", 1)},
        )
    )


async def answer(decision, context, call):
    asked = []

    async def sink(kind, payload):
        if kind == "approval_request":
            asked.append(payload)
            approvals.broker.resolve(context.user_id, payload["approval_id"], decision)

    with events.bind_event_sink(sink), bind_approvals(context):
        return await call(), asked


async def test_an_invented_package_never_installs(gate):
    ran = []
    agent = agent_running(ran)
    with bind_approvals(ApprovalContext("alice", "chat", "auto", interactive=True)):
        result = await agent._execute_tool_safe("bash", {"command": "pip install no-such-pkg-zz"})
    assert "Wara'" in result["error"] and "no-such-pkg-zz" in result["error"]
    assert result["wara"]["decision"] == "refuse"
    assert ran == []


async def test_a_doubtful_package_asks_even_in_auto_mode(gate):
    ran = []
    agent = agent_running(ran)
    context = ApprovalContext("alice", "chat", "auto", interactive=True)
    call = lambda: agent._execute_tool_safe("bash", {"command": "pip install reqeusts"})  # noqa: E731
    declined, asked = await answer("deny", context, call)
    assert declined.get("declined") and ran == []
    assert "requests" in asked[0]["reason"]
    allowed, asked = await answer("allow", context, call)
    assert allowed == {"ok": True, "tool": "bash"} and len(ran) == 1


async def test_a_doubtful_package_is_held_when_no_one_watches(gate):
    ran = []
    agent = agent_running(ran)
    with approvals.unattended("alice", "watch-1", "watcher"), collecting_held() as held:
        # workspace_run is sandboxed and normally runs unattended; the doubt holds it.
        result = await agent._execute_tool_safe(
            "workspace_run", {"command": "pip install reqeusts"}
        )
    assert result["held_for_approval"] and ran == []
    assert "requests" in held[0]["reason"]


async def test_a_doubtful_package_with_no_one_to_ask_is_refused(gate):
    ran = []
    agent = agent_running(ran)
    result = await agent._execute_tool_safe("bash", {"command": "pip install reqeusts"})
    assert result.get("approval_required") and ran == []


async def test_an_established_package_runs_as_before(gate):
    ran = []
    agent = agent_running(ran)
    with bind_approvals(ApprovalContext("alice", "chat", "auto", interactive=True)):
        result = await agent._execute_tool_safe("bash", {"command": "pip install requests"})
        plain = await agent._execute_tool_safe("bash", {"command": "ls -la"})
    assert result == {"ok": True, "tool": "bash"} and plain == {"ok": True, "tool": "bash"}
    assert len(ran) == 2


async def test_the_install_package_tool_is_vetted(gate):
    ran = []
    agent = agent_running(ran, kind="code")
    result = await agent._execute_tool_safe("install_package", {"package": "no-such-pkg-zz"})
    assert "Wara'" in result["error"] and ran == []


async def test_off_checks_nothing(gate, monkeypatch):
    monkeypatch.setenv("MIZAN_WARA", "off")
    ran = []
    agent = agent_running(ran)
    result = await agent._execute_tool_safe("bash", {"command": "pip install no-such-pkg-zz"})
    assert result == {"ok": True, "tool": "bash"}


async def test_unreachable_registries_never_block_an_install(registry, monkeypatch, tmp_path):
    monkeypatch.setenv("MIZAN_WARA", "on")
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    registry(Registry(fail=True))
    ran = []
    agent = agent_running(ran)
    result = await agent._execute_tool_safe("bash", {"command": "pip install reqeusts"})
    assert result["ok"] is True and ran
    assert "could not be checked" in result["wara"]["notes"][0]
