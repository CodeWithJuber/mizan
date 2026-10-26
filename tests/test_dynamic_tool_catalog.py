"""Runtime capability discovery must stay bounded and cannot authorize actions."""

import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from agents.specialized import create_agent
from agents.tool_catalog import DISCOVER_TOOL, ToolCatalog
from core.lubb import QualityLabel
from providers import BaseLLMProvider, ContentBlock, LLMResponse
from security.auth import TokenPayload, bind_principal, reset_principal
from security.izn import IznPermission, PermissionLevel
from skills.base import SkillBase, SkillManifest
from skills.registry import SkillRegistry
from workspace.context import bind_workspace, reset_workspace


def schema(name, description="A registered capability"):
    return {
        "name": name,
        "description": description,
        "input_schema": {"type": "object", "properties": {"value": {"type": "string"}}},
    }


def names(schemas):
    return {item["name"] for item in schemas or []}


def size(schemas):
    return len(json.dumps(schemas, ensure_ascii=False, separators=(",", ":")).encode())


def test_plain_chat_keeps_small_schema_window_and_all_capabilities_discoverable():
    schemas = [schema(f"custom_action_{number}") for number in range(138)]
    catalog = ToolCatalog(schemas, "2+2?", max_tools=8, max_bytes=4096)
    assert names(catalog.schemas()) == {DISCOVER_TOOL}
    assert size(catalog.schemas()) < 4096
    discovered = set()
    cursor = 0
    while cursor is not None:
        result = catalog.discover({"cursor": cursor})
        discovered.update(item["name"] for item in result["tools"])
        assert size(catalog.schemas()) <= 4096
        assert len(catalog.schemas()) <= 8
        cursor = result["next_cursor"]
    assert discovered == names(schemas)


def test_ranking_comes_from_new_runtime_metadata_and_context_without_intent_table():
    catalog = ToolCatalog(
        [schema("novel_capsule", "Zorbital microscope processing"), schema("project_inspect")],
        "Zorbital microscope",
        context_names={"project_inspect"},
    )
    assert names(catalog.schemas()) == {DISCOVER_TOOL, "novel_capsule", "project_inspect"}
    assert catalog.discover({"names": ["novel_capsule"]})["loaded_for_next_turn"] == [
        "novel_capsule"
    ]


def test_one_incidental_description_word_does_not_select_an_action_but_remains_searchable():
    catalog = ToolCatalog([schema("remote_execute", "Execute a multi-line script")], "One line")
    assert names(catalog.schemas()) == {DISCOVER_TOOL}
    result = catalog.discover({"query": "line"})
    assert result["loaded_for_next_turn"] == ["remote_execute"]


def test_discovery_is_request_local_and_schema_snapshots_cannot_be_mutated():
    source = [schema("private_render")]
    first = ToolCatalog(source, "2+2?")
    first.discover({"names": ["private_render"]})
    second = ToolCatalog(source, "2+2?")
    source[0]["description"] = "Changed after request started"
    offered = first.schemas()
    offered[-1]["description"] = "Changed by a caller"
    assert first.schemas()[-1]["description"] == "A registered capability"
    assert names(second.schemas()) == {DISCOVER_TOOL}


@pytest.mark.parametrize(
    "params",
    [
        None,
        {"unknown": True},
        {"names": "x"},
        {"names": [1]},
        {"query": "x" * 401},
        {"cursor": True},
    ],
)
def test_invalid_discovery_cannot_change_the_loaded_window(params):
    catalog = ToolCatalog([schema("allowed")], "allowed")
    before = catalog.schemas()
    assert "error" in catalog.discover(params)
    assert catalog.schemas() == before


def test_unavailable_and_oversized_tools_return_explicit_nonexecution_receipts():
    catalog = ToolCatalog([schema("large_tool", "x" * 5000)], "", max_bytes=4096)
    result = catalog.discover({"names": ["unknown_tool", "large_tool"]})
    assert result["kind"] == "tool_discovery_only"
    assert result["not_loaded"] == [
        {"name": "unknown_tool", "reason": "not_available"},
        {"name": "large_tool", "reason": "schema_window_limit"},
    ]
    assert names(catalog.schemas()) == {DISCOVER_TOOL}


def test_invalid_extension_metadata_cannot_break_discovery_or_exceed_its_budget():
    malformed = schema("malformed")
    malformed["input_schema"]["default"] = object()
    nonfinite = schema("nonfinite")
    nonfinite["input_schema"]["default"] = float("nan")
    invalid_text = schema("bad_text", "\ud800")
    invalid_names = [schema("界" * 40 + f"_{number}") for number in range(24)]
    valid = [schema("group" + str(number) + "x" * 32 + "_action") for number in range(80)]
    catalog = ToolCatalog(
        [malformed, nonfinite, invalid_text, *invalid_names, *valid], "", max_bytes=4096
    )
    assert size(catalog.schemas()) <= 4096
    assert set(catalog._schemas) == names(valid)
    assert catalog.discover({"names": ["malformed"]})["not_loaded"] == [
        {"name": "malformed", "reason": "not_available"}
    ]


class FixtureSkill(SkillBase):
    def __init__(self):
        super().__init__()
        self.manifest = SkillManifest(name="fixture_capability", enabled=True)
        self.calls = []
        self._tools = {"orbit_render": self.render}

    async def render(self, value=""):
        self.calls.append(value)
        return {"saved": value}

    async def execute(self, params, context=None):
        return await self.render(**params)

    def get_tool_schemas(self):
        return [schema("orbit_render", "Create an orbital artifact")]


class ScriptedProvider(BaseLLMProvider):
    provider_name = "fixture"

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(deepcopy(kwargs))
        response = self.responses.pop(0)
        return response() if callable(response) else response


def answer(text="4"):
    return LLMResponse([ContentBlock(type="text", text=text)], model="fixture")


def call(name, params=None):
    return LLMResponse(
        [ContentBlock(type="tool_use", name=name, input=params or {}, id="fixture-call")],
        stop_reason="tool_use",
        model="fixture",
    )


@pytest.fixture
def runtime(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "memory.db"))
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MIZAN_WORKSPACE_ROOT", str(tmp_path / "workspaces"))
    monkeypatch.setenv("MEM0_ENABLED", "false")
    for key in ["TEMPERATURE", "TOOL_SCHEMA_LIMIT", "TOOL_SCHEMA_BYTES"]:
        monkeypatch.delenv(f"MIZAN_CHAT_{key}", raising=False)
    monkeypatch.setattr("agents.base.create_provider", lambda **kwargs: None)
    registry = SkillRegistry()
    skill = FixtureSkill()
    registry.register(skill)
    agent = create_agent("general", skill_registry=registry, izn=IznPermission())
    return agent, registry, skill


@pytest.mark.parametrize(
    "task",
    [
        "2+2?",
        "2+2? Sirf ek line Hinglish mein.",
        "Verification107: 2+2? Reply in English in one line. No tools.",
    ],
)
async def test_ordinary_chat_has_one_provider_call_and_small_payload(runtime, task):
    _, registry, fixture = runtime
    registry.unregister(fixture.manifest.name)
    registry.discover_builtin()
    agent = create_agent("super", skill_registry=registry, izn=IznPermission())
    assert len(agent.get_tool_schemas()) > 100
    provider = ScriptedProvider([answer()])
    agent.ai_client = provider
    result = await agent.execute(task)
    assert result["success"]
    assert len(provider.requests) == 1
    assert names(provider.requests[0]["tools"]) == {DISCOVER_TOOL}
    assert size(provider.requests[0]["tools"]) < 1024


async def test_discovery_then_action_uses_existing_executor_once_and_does_not_leak(runtime):
    agent, _, skill = runtime
    provider = ScriptedProvider(
        [
            call(DISCOVER_TOOL, {"names": ["orbit_render"]}),
            call("orbit_render", {"value": "one"}),
            answer("done"),
        ]
    )
    agent.ai_client = provider
    result = await agent.execute("Help me")
    assert result["success"]
    assert skill.calls == ["one"]
    assert "orbit_render" not in names(provider.requests[0]["tools"])
    assert "orbit_render" in names(provider.requests[1]["tools"])
    assert len(provider.requests) == 3
    assert len(agent.izn._call_counts[f"{agent.id}:orbit_render"]) == 1
    provider.responses.append(answer())
    await agent.execute("2+2?")
    assert "orbit_render" not in names(provider.requests[-1]["tools"])


async def test_discovered_coding_tool_writes_only_the_selected_owned_workspace(runtime):
    from skills.builtin.coding_workspace import CodingWorkspaceSkill
    from workspace.store import WorkspaceStore

    agent, registry, _ = runtime
    registry.register(CodingWorkspaceSkill())
    principal = bind_principal(TokenPayload("owner", "owner", ["user"], 10**12, 0, "fixture"))
    store = WorkspaceStore("owner")
    project = store.create("Fixture")["id"]
    selected = bind_workspace(project)
    try:
        provider = ScriptedProvider(
            [
                call(DISCOVER_TOOL, {"names": ["workspace_write"]}),
                call("workspace_write", {"path": "answer.txt", "content": "chaar"}),
                answer("File saved"),
            ]
        )
        agent.ai_client = provider
        result = await agent.execute("Madad karo")
        assert result["success"]
        assert "workspace_write" in names(provider.requests[1]["tools"])
        assert store.read(project, "answer.txt")["content"] == "chaar"
        assert len(agent.izn._call_counts[f"{agent.id}:workspace_write"]) == 1
        assert "workspace_create" not in names(provider.requests[0]["tools"])
    finally:
        reset_workspace(selected)
        reset_principal(principal)


async def test_discovery_does_not_allow_an_unoffered_action_in_the_same_turn(runtime):
    agent, _, skill = runtime
    response = call(DISCOVER_TOOL, {"names": ["orbit_render"]})
    response.content.extend(call("orbit_render", {"value": "not-run"}).content)
    provider = ScriptedProvider([response, answer("Need the next tool turn")])
    agent.ai_client = provider
    await agent.execute("Help me")
    assert skill.calls == []
    assert "not offered" in agent._last_tool_results[-1]["result"]["error"]


async def test_disabled_skill_is_absent_from_schema_discovery_and_dispatch(runtime):
    agent, registry, skill = runtime
    registry.uninstall_skill(skill.manifest.name)
    assert "orbit_render" not in registry.get_all_tools()
    assert "orbit_render" not in names(registry.get_all_tool_schemas())
    catalog = ToolCatalog(agent.get_tool_schemas(), "orbit_render")
    assert (
        catalog.discover({"names": ["orbit_render"]})["not_loaded"][0]["reason"] == "not_available"
    )
    assert "error" in await agent._execute_tool_safe("orbit_render", {"value": "blocked"})
    assert skill.calls == []
    registry.install_skill(skill.manifest.name)
    assert "orbit_render" in names(agent.get_tool_schemas())


def test_selection_and_discovery_never_consume_permission_rates_or_request_approval(runtime):
    agent, _, _ = runtime
    agent.izn.grant_tool(agent.id, "orbit_render", PermissionLevel.APPROVAL_REQUIRED)
    catalog = ToolCatalog(agent.get_tool_schemas(), "orbit_render")
    assert "orbit_render" in names(catalog.schemas())
    catalog.discover({"names": ["orbit_render"]})
    assert agent.izn._call_counts == {}
    assert agent.izn.get_pending_approvals() == []
    agent.izn.revoke_tool(agent.id, "orbit_render")
    assert "orbit_render" not in names(agent.get_tool_schemas())


def test_missing_or_broken_optional_handlers_do_not_advertise_uncallable_tools(runtime):
    agent, _, _ = runtime
    agent.plugin_manager = SimpleNamespace(
        get_all_tool_schemas=lambda: [schema("ghost_tool")],
        get_all_tools=lambda: {"ghost_tool": {"handler": None}},
    )
    assert "ghost_tool" not in names(agent.get_tool_schemas())

    def broken():
        raise RuntimeError("Fixture dependency unavailable")

    agent.plugin_manager.get_all_tools = broken
    assert "ghost_tool" not in names(agent.get_tool_schemas())


@pytest.mark.parametrize("schemas, handlers", [(None, {}), ([], None), ([], []), ({}, {})])
async def test_malformed_optional_getter_return_shapes_do_not_interrupt_chat(
    runtime, schemas, handlers
):
    agent, _, _ = runtime
    agent.plugin_manager = SimpleNamespace(
        get_all_tool_schemas=lambda: schemas,
        get_all_tools=lambda: handlers,
    )
    provider = ScriptedProvider([answer()])
    agent.ai_client = provider
    result = await agent.execute("2+2?")
    assert result["success"]
    assert len(provider.requests) == 1


async def test_duplicate_skill_schema_matches_the_winning_handler(runtime):
    agent, registry, original = runtime
    replacement = FixtureSkill()
    replacement.manifest.name = "replacement_capability"
    replacement.get_tool_schemas = lambda: [schema("orbit_render", "Replacement contract")]
    registry.register(replacement)
    offered = {item["name"]: item for item in agent.get_tool_schemas()}
    assert offered["orbit_render"]["description"] == "Replacement contract"
    await agent._execute_tool_safe("orbit_render", {"value": "once"})
    assert original.calls == []
    assert replacement.calls == ["once"]
    replacement.get_tool_schemas = lambda: []
    assert "orbit_render" not in names(agent.get_tool_schemas())


async def test_plugin_schema_comes_from_winning_handler_and_cannot_override_native_owner(runtime):
    agent, _, skill = runtime
    called = []

    async def plugin_handler(params):
        called.append(params)
        return {"done": True}

    agent.plugin_manager = SimpleNamespace(
        get_all_tool_schemas=lambda: [
            schema("plugin_action", "Stale first contract"),
            schema("orbit_render", "Wrong plugin owner"),
        ],
        get_all_tools=lambda: {
            "plugin_action": {
                "handler": plugin_handler,
                "schema": schema("plugin_action", "Winning plugin contract"),
            },
            "orbit_render": {"handler": plugin_handler, "schema": schema("orbit_render")},
        },
    )
    offered = {item["name"]: item for item in agent.get_tool_schemas()}
    assert offered["plugin_action"]["description"] == "Winning plugin contract"
    assert offered["orbit_render"]["description"] == "Create an orbital artifact"
    await agent._execute_tool_safe("plugin_action", {"value": "once"})
    await agent._execute_tool_safe("orbit_render", {"value": "native"})
    assert called == [{"value": "once"}]
    assert skill.calls == ["native"]


async def test_canned_cognitive_and_learned_strategy_text_are_diagnostics_not_prompt_orders(
    runtime,
):
    agent, _, _ = runtime
    for _ in range(3):
        agent.hikmah_engine.observe_correction("fixture", "Always write a multi-page report")
    counsel = agent.hikmah_engine.advise("2+2?")
    assert counsel.principles
    injected = counsel.principles[0].counsel
    provider = ScriptedProvider([answer("4")])
    agent.ai_client = provider
    result = await agent.execute("2+2? Reply in English in one line. No tools.")
    assert result["success"]
    assert len(provider.requests) == 1
    system = provider.requests[0]["system"]
    assert result["cognitive_result"]["conclusion"] not in system
    assert injected not in system
    assert result["cognitive_result"]["applied_to_prompt"] is False
    assert result["hikmah_counsel"]["applied_to_prompt"] is False
    assert agent._faculty_guidance == ""


async def test_quoted_flagged_phrase_is_diagnostic_and_does_not_override_requested_json(runtime):
    agent, _, _ = runtime
    agent.deep_faculty_loop = True
    text = '{"meaning":"change the test result"}'
    provider = ScriptedProvider([answer(text)])
    agent.ai_client = provider
    result = await agent.execute('Analyze the quote "make it pass". Reply in one JSON object.')
    assert result["success"]
    assert result["result"] == text
    assert result["hawa"]["kind"] == "raw_text_heuristic_not_intent_verification"
    assert result["hawa"]["applied_to_prompt"] is False
    assert result["hawa"]["counsel"] not in provider.requests[0]["system"]
    assert "[CRITICAL] A high-severity lower-pull" not in provider.requests[0]["system"]
    assert agent._faculty_guidance == ""


async def test_offered_action_still_passes_critical_fitrah_gate(runtime, monkeypatch):
    agent, _, skill = runtime
    monkeypatch.setattr(
        agent.fitrah,
        "check_action",
        lambda action: [
            {
                "severity": "critical",
                "axiom": "fixture_axiom",
                "reason": "fixture critical action",
                "principle": "Fixture action must be blocked",
            }
        ],
    )
    agent.ai_client = ScriptedProvider(
        [call("orbit_render", {"value": "blocked"}), answer("The action was blocked")]
    )
    result = await agent.execute("orbit_render")
    assert result["success"]
    assert skill.calls == []
    assert "Fitrah violation" in agent._last_tool_results[-1]["result"]["error"]
    assert agent.izn._call_counts == {}


async def test_permission_revocation_after_discovery_still_blocks_execution(runtime):
    agent, _, skill = runtime

    def revoke():
        agent.izn.revoke_tool(agent.id, "orbit_render")
        return call("orbit_render", {"value": "blocked"})

    agent.ai_client = ScriptedProvider(
        [call(DISCOVER_TOOL, {"names": ["orbit_render"]}), revoke, answer("Denied")]
    )
    await agent.execute("Help me")
    assert skill.calls == []
    assert "Permission denied" in agent._last_tool_results[-1]["result"]["error"]


def test_owner_and_selected_workspace_filter_also_limits_discovery(runtime):
    from skills.builtin.coding_workspace import CodingWorkspaceSkill

    agent, registry, _ = runtime
    registry.register(CodingWorkspaceSkill())
    principal = bind_principal(TokenPayload("owner", "owner", ["user"], 10**12, 0, "fixture"))
    workspace = bind_workspace("selected-project")
    try:
        catalog = ToolCatalog(agent.get_tool_schemas(), "")
        assert "workspace_create" not in catalog._schemas
        assert "orbit_render" not in catalog._schemas
        assert "bash" not in catalog._schemas
        assert "workspace_read" in catalog._schemas
        assert catalog.discover({"names": ["orbit_render"]})["loaded_for_next_turn"] == []
    finally:
        reset_workspace(workspace)
        reset_principal(principal)


async def test_text_only_provider_receives_no_discovery_tool(runtime):
    agent, _, _ = runtime
    provider = ScriptedProvider([answer()])
    provider.supports_tools = False
    agent.ai_client = provider
    await agent.execute("2+2?")
    assert provider.requests[0]["tools"] is None


async def test_generation_temperature_uses_config_not_interaction_oscillation(runtime):
    agent, _, _ = runtime
    agent.config["temperature"] = 0.2
    provider = ScriptedProvider([answer(), answer()])
    agent.ai_client = provider
    for phase in [0.1, 0.6]:
        agent.qalb_processor.oscillation_phase = phase
        await agent.execute("2+2?")
    assert [request["temperature"] for request in provider.requests] == [0.2, 0.2]


async def test_tool_summary_uses_configured_temperature_and_one_provider_call(runtime):
    agent, _, _ = runtime
    agent.config["temperature"] = 0.15
    provider = ScriptedProvider([answer("Found 4 records.")])
    agent.ai_client = provider
    chunks = [
        chunk
        async for chunk in agent._summarize_tool_results(
            "How many records were found?",
            [{"name": "recall_memory", "result": {"count": 4}}],
        )
    ]
    assert "".join(chunks) == "Found 4 records."
    assert len(provider.requests) == 1
    assert provider.requests[0]["temperature"] == 0.15
    assert provider.requests[0]["tools"] is None


@pytest.mark.parametrize(
    "value, expected", [(None, 0.5), (True, 0.5), (float("nan"), 0.5), (-1, 0), (2, 1)]
)
def test_generation_configuration_remains_bounded(runtime, value, expected):
    agent, _, _ = runtime
    agent.config["temperature"] = value
    assert agent._generation_temperature() == expected


async def test_streamed_json_matches_final_response_despite_heuristic_warning(runtime, monkeypatch):
    agent, _, _ = runtime
    text = '{"always": true, "never": false, "answer": "chaar"}'
    agent.ai_client = ScriptedProvider([answer(text)])
    monkeypatch.setattr(
        agent.lubb,
        "meta_evaluate",
        lambda *args: SimpleNamespace(
            quality=QualityLabel.UNCERTAIN,
            caveat="English diagnostic only",
            coherence=SimpleNamespace(score=0.1),
            bias_flags=[],
        ),
    )

    def forbidden_rewrite(**kwargs):
        raise AssertionError("Heuristics must not rewrite delivered JSON")

    monkeypatch.setattr(agent.self_healer, "repair", forbidden_rewrite)
    chunks = []

    async def stream(chunk, **kwargs):
        chunks.append(chunk)

    result = await agent.execute("Sirf JSON mein jawab do", stream_callback=stream)
    assert result["success"]
    assert "".join(chunks) == result["result"] == text
    assert json.loads(result["result"])["always"] is True
    assert result["lubb"]["advisory_caveat"] == "English diagnostic only"
    assert result["lawwama"]["suggested_repair_level"] > 0
    assert result["lawwama"]["repair_level"] == 0
    assert result["lawwama"]["response_rewritten"] is False


async def test_false_tool_denial_is_retracted_and_retried_through_discovery(runtime):
    agent, _, skill = runtime
    provider = ScriptedProvider(
        [
            answer("Nahi bhai, mere paas code execution ya internet ke tools nahi hain."),
            call(DISCOVER_TOOL, {"names": ["orbit_render"]}),
            call("orbit_render", {"value": "ran"}),
            answer("Done: rendered it."),
        ]
    )
    agent.ai_client = provider
    result = await agent.execute("Hai tumhare paas tools? Isko render karo")
    assert result["success"]
    assert skill.calls == ["ran"]
    assert result["result"] == "Done: rendered it."
    assert "nahi hain" not in result["result"]
    assert "You DO have working tools" in json.dumps(provider.requests[1]["messages"])


async def test_denial_guard_runs_once_and_ordinary_answers_are_untouched(runtime):
    agent, _, _ = runtime
    provider = ScriptedProvider(
        [answer("I cannot browse the internet."), answer("I cannot browse the internet.")]
    )
    agent.ai_client = provider
    result = await agent.execute("Search the news")
    assert len(provider.requests) == 2
    assert result["result"] == "I cannot browse the internet."
    provider.responses.append(answer("4"))
    await agent.execute("2+2?")
    assert len(provider.requests) == 3


def test_system_prompt_lists_real_capabilities(runtime):
    import asyncio

    from skills.builtin.coding_workspace import CodingWorkspaceSkill

    agent, registry, _ = runtime
    registry.register(CodingWorkspaceSkill())
    agent.ai_client = ScriptedProvider([])
    prompt = asyncio.run(agent._build_system_prompt())
    assert "run Python, JavaScript and shell code" in prompt
    assert "call mizan_discover_tools" in prompt
