"""Shahid: the browser goes only where the user's words point and changes nothing without a person."""

import importlib.util
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from workspace import browse_agent as agent  # noqa: E402

ORIGINS = ["shop.example", ".example.org"]


@pytest.mark.parametrize(
    "method, url, navigation, verdict",
    [
        ("GET", "https://shop.example/dates", True, "allow"),
        ("GET", "https://www.example.org/", True, "allow"),  # under .example.org
        ("GET", "https://example.org/", True, "allow"),
        ("GET", "https://elsewhere.example/", True, "block"),  # another origin
        ("GET", "https://cdn.elsewhere.example/app.js", False, "allow"),  # a page's script
        ("GET", "http://shop.example/", True, "block"),  # no TLS
        ("GET", "file:///etc/passwd", True, "block"),
        ("POST", "https://shop.example/order", True, "hold"),  # changes something
        ("PUT", "https://cdn.elsewhere.example/beacon", False, "hold"),
        ("GET", "data:text/plain,hi", False, "allow"),
    ],
)
def test_each_request_is_allowed_blocked_or_held(method, url, navigation, verdict):
    assert agent.decide(method, url, navigation, ORIGINS, []) == verdict


def test_an_approved_request_goes_through_and_only_that_one():
    approved = [agent.request_key("POST", "https://shop.example/order?x=1")]
    assert approved == ["POST https://shop.example/order"]
    assert agent.decide("POST", "https://shop.example/order", True, ORIGINS, approved) == "allow"
    assert agent.decide("POST", "https://shop.example/pay", True, ORIGINS, approved) == "hold"
    assert agent.decide("DELETE", "https://shop.example/order", True, ORIGINS, approved) == "hold"


@pytest.mark.parametrize(
    "job, problem",
    [
        (
            {
                "origins": ["shop.example"],
                "steps": [{"do": "goto", "url": "https://shop.example/"}],
            },
            None,
        ),
        ({"origins": [], "steps": [{"do": "read"}]}, "origins"),
        ({"origins": ["a.example"], "steps": []}, "steps"),
        (
            {"origins": ["a.example"], "steps": [{"do": "goto", "url": "https://b.example/"}]},
            "origins",
        ),
        (
            {"origins": ["a.example"], "steps": [{"do": "goto", "url": "http://a.example/"}]},
            "https",
        ),
        (
            {"origins": ["a.example"], "steps": [{"do": "click", "role": "script", "name": "x"}]},
            "role",
        ),
        ({"origins": ["a.example"], "steps": [{"do": "press", "key": "Control+W"}]}, "key"),
        ({"origins": ["a.example"], "steps": [{"do": "evaluate", "js": "fetch('/x')"}]}, "unknown"),
        ({"origins": ["a.example"], "steps": [{"do": "read"}] * 13}, "steps"),
    ],
)
def test_a_job_is_checked_before_the_browser_starts(job, problem):
    found = agent.valid(job)
    assert (found is None) if problem is None else (problem in (found or ""))


@pytest.mark.skipif(
    importlib.util.find_spec("playwright") is None, reason="Playwright is not installed here"
)
def test_a_real_browser_follows_the_rules():
    selftest = os.path.join(os.path.dirname(agent.__file__), "browse_selftest.py")
    done = subprocess.run([sys.executable, selftest], capture_output=True, text=True, timeout=180)
    assert done.returncode == 0, done.stdout + done.stderr


# ── MIZAN's side: where, what, and who decides ─────────────────────────────

from copy import deepcopy  # noqa: E402

from agents.specialized import create_agent  # noqa: E402
from providers import BaseLLMProvider, ContentBlock, LLMResponse  # noqa: E402
from security.approvals import ApprovalContext  # noqa: E402
from security.izn import IznPermission  # noqa: E402
from tadbir import fahm, shahid  # noqa: E402


def test_the_sites_are_the_hosts_of_the_users_own_links():
    assert shahid.origins_from(["https://shop.example/dates?q=1", "http://www.news.example/"]) == [
        "shop.example",
        "www.shop.example",
        "news.example",
        "www.news.example",
    ]
    assert shahid.origins_from(["https://localhost/"]) == []


def test_mizan_fills_a_field_only_with_the_users_own_words():
    origins = ["shop.example"]
    message = "Open https://shop.example and order Ajwa dates for Zubair"
    steps, problem = shahid.plan(
        [
            {"do": "goto", "url": "http://shop.example/"},
            {"do": "fill", "label": "Name", "value": "Zubair"},
            {"do": "click", "role": "button", "name": "Order"},
        ],
        origins,
        message,
    )
    assert problem == "" and steps[0]["url"] == "https://shop.example/"
    assert steps[-2:] == [{"do": "read"}, {"do": "screenshot"}]  # what the answer is written from
    _none, invented = shahid.plan(
        [{"do": "fill", "label": "Card number", "value": "4111 1111 1111 1111"}], origins, message
    )
    assert _none is None and "own words" in invented
    _none, elsewhere = shahid.plan(
        [{"do": "goto", "url": "https://evil.example/"}], origins, message
    )
    assert _none is None and "origins" in elsewhere


def test_sending_to_a_site_always_needs_a_person():
    for mode in ("auto", "auto_edits", "ask"):
        context = ApprovalContext("owner", "chat", mode=mode)
        assert context.needs_approval("shahid_submit")
        assert not context.needs_approval("shahid_read")
    unattended = ApprovalContext("owner", "chat", mode="auto", deferred=True)
    assert unattended.needs_approval("shahid_submit")


async def test_with_no_one_to_ask_nothing_is_sent(monkeypatch, tmp_path):
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("agents.base.create_provider", lambda **kwargs: None)
    agent = create_agent("general", izn=IznPermission())
    result = await agent._execute_tool_checked(
        "shahid_submit", {"origins": ["a.example"], "steps": [{"do": "read"}], "approved": ["x"]}
    )
    assert "no one is here to approve" in result["error"]


def test_a_page_request_with_clicks_is_browsing_and_a_summary_is_reading(monkeypatch):
    monkeypatch.setenv("MIZAN_WORKSPACE_RUNNER_URL", "http://runner:8080")
    monkeypatch.setenv("MIZAN_WORKSPACE_RUNNER_TOKEN", "t" * 40)
    browse = fahm.understand("Open https://halal-shop.example and click on Offers")
    assert browse.intent == "browse"
    assert browse.entities["origins"] == ["halal-shop.example", "www.halal-shop.example"]
    assert fahm.understand("Summarize https://example.com/article").intent == "web_read"
    # Without the private runner there is no browser: the page is read instead.
    monkeypatch.delenv("MIZAN_WORKSPACE_RUNNER_URL")
    assert fahm.understand("Open https://halal-shop.example and click on Offers").intent == (
        "web_read"
    )


class Scripted(BaseLLMProvider):
    provider_name = "fixture"

    def __init__(self, replies):
        self.replies, self.requests = list(replies), []

    def create(self, **kwargs):
        self.requests.append(deepcopy(kwargs))
        reply = self.replies.pop(0) if self.replies else "Ajwa dates cost 40 AED [1]."
        return LLMResponse([ContentBlock(type="text", text=reply)], model="fixture")


async def test_mizan_browses_asks_before_sending_and_shows_what_it_did(monkeypatch, tmp_path):
    monkeypatch.setenv("MIZAN_ORCHESTRATION", "mizan")
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "memory.db"))
    monkeypatch.setenv("MIZAN_WORKSPACE_RUNNER_URL", "http://runner:8080")
    monkeypatch.setenv("MIZAN_WORKSPACE_RUNNER_TOKEN", "t" * 40)
    monkeypatch.setattr("agents.base.create_provider", lambda **kwargs: None)
    agent = create_agent("general", izn=IznPermission())
    names = ["shahid_read", "shahid_submit", "web_browse"]
    monkeypatch.setattr(
        agent,
        "get_tool_schemas",
        lambda: [{"name": n, "description": "", "input_schema": {"type": "object"}} for n in names],
    )
    monkeypatch.setattr(agent, "_chat_tool_allowed", lambda name: True)
    plan = (
        '{"steps":[{"do":"goto","url":"https://shop.example/"},'
        '{"do":"fill","label":"Name","value":"Zubair"},'
        '{"do":"click","role":"button","name":"Order"},{"do":"read"}]}'
    )
    agent.ai_client = Scripted([plan])
    calls = []
    page = {
        "steps": [
            {"do": "goto", "ok": True, "url": "https://shop.example/", "title": "Dates shop"},
            {"do": "read", "ok": True, "url": "https://shop.example/", "title": "Dates shop"},
        ],
        "text": "Ajwa dates, 1 kg: 40 AED",
        "held": [{"key": "POST https://shop.example/order", "data": "name=Zubair"}],
        "final_url": "https://shop.example/",
        "screenshot_sha": "ab" * 32,
    }

    async def run_tool(name, params):
        calls.append((name, deepcopy(params)))
        if name == "shahid_read":
            return page
        return {"error": "The user declined this action", "declined": True}

    monkeypatch.setattr(agent, "_execute_tool_safe", run_tool)
    result = await agent.execute("Open https://shop.example and order Ajwa dates for Zubair")
    assert [name for name, _ in calls] == ["shahid_read", "shahid_submit"]
    assert calls[1][1]["approved"] == ["POST https://shop.example/order"]
    assert all(step.get("value") in (None, "Zubair") for step in calls[0][1]["steps"])
    assert "Nothing was sent to the site" in result["result"]
    assert result["images"] == [{"sha": "ab" * 32, "media_type": "image/png"}]
    assert result["orchestration"]["intent"] == "browse"


# ── On the runner: a one-shot hardened container, always cleaned up ───────


async def test_a_job_runs_in_a_hardened_container_and_nothing_outlives_it(monkeypatch):
    import json as _json

    from workspace import browse

    monkeypatch.setenv("MIZAN_WORKSPACE_BROWSER_IMAGE", "mizan-workspace-browser:v1")
    calls = []

    async def docker(*args, payload=None, timeout=30, limit=0):
        calls.append((args, payload))
        if args[:2] == ("inspect", "--format"):
            return 1, b"", b"no such container"
        if args[0] == "run" and "--rm" in args:
            return 0, _json.dumps({"steps": [], "held": [], "text": "ok"}).encode(), b""
        return 0, b"", b""

    monkeypatch.setattr(browse, "docker", docker)
    result = await browse.run({"origins": ["a.example"], "steps": [{"do": "read"}]}, 30)
    assert result["text"] == "ok"
    proxy = next(
        args for args, _ in calls if "--label" in args and "mizan.egress=browse-proxy" in args
    )
    assert "MIZAN_EGRESS_MODE=public" in proxy
    job_args, payload = next((args, p) for args, p in calls if args[0] == "run" and "--rm" in args)
    for flag in ("--read-only", "no-new-privileges", "65534:65534", "/browse_agent.py"):
        assert flag in job_args
    assert job_args[job_args.index("--cap-drop") + 1] == "ALL"
    network = job_args[job_args.index("--network") + 1]
    assert network.startswith("mizan-browse-net-")
    assert ("network", "create", "--internal", network) in [args for args, _ in calls]
    assert _json.loads(payload)["origins"] == ["a.example"]
    cleanup = [args for args, _ in calls][-3:]
    assert cleanup[0][:2] == ("rm", "-f") and cleanup[2] == ("network", "rm", network)


async def test_the_container_is_removed_even_when_the_job_fails(monkeypatch):
    from workspace import browse
    from workspace.sessions import SessionError

    monkeypatch.setenv("MIZAN_WORKSPACE_BROWSER_IMAGE", "mizan-workspace-browser:v1")
    calls = []

    async def docker(*args, payload=None, timeout=30, limit=0):
        calls.append(args)
        if args[0] == "run" and "--rm" in args:
            return 125, b"", b"boom"
        return 0, b"true", b""

    monkeypatch.setattr(browse, "docker", docker)
    with pytest.raises(SessionError):
        await browse.run({"origins": ["a.example"], "steps": [{"do": "read"}]}, 30)
    assert calls[-1][:2] == ("network", "rm") and calls[-3][:2] == ("rm", "-f")


def test_the_runner_checks_a_job_before_any_container_starts(monkeypatch):
    from fastapi.testclient import TestClient

    from workspace import runner

    token = "r" * 40
    monkeypatch.setenv("MIZAN_WORKSPACE_RUNNER_TOKEN", token)
    client = TestClient(runner.app)
    headers = {"Authorization": f"Bearer {token}"}
    good = {"origins": ["a.example"], "steps": [{"do": "goto", "url": "https://a.example/"}]}
    assert client.post("/browse", json=good).status_code == 401
    assert (
        client.post("/browse", json={**good, "origins": ["127.0.0.1"]}, headers=headers).status_code
        == 422
    )
    bad_step = {**good, "steps": [{"do": "goto", "url": "https://b.example/"}]}
    assert client.post("/browse", json=bad_step, headers=headers).status_code == 422
    monkeypatch.delenv("MIZAN_WORKSPACE_BROWSER_IMAGE", raising=False)
    assert client.post("/browse", json=good, headers=headers).status_code == 503


def test_the_browse_proxy_takes_any_public_host_and_still_refuses_private_ones(monkeypatch):
    import asyncio

    from workspace import egress_proxy

    monkeypatch.setenv("MIZAN_EGRESS_MODE", "public")
    assert egress_proxy.host_allowed("any-site.example", egress_proxy.allowlist())
    assert asyncio.run(egress_proxy.public_address("127.0.0.1", 443)) is None
