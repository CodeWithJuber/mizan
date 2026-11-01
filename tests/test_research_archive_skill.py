"""Research algorithms are reachable through normal, admin-gated chat tool dispatch."""

import hashlib
import json
import zipfile
from unittest.mock import Mock

import pytest

from mizan_owned import research
from providers import ContentBlock, LLMResponse
from security.auth import TokenPayload, bind_principal, reset_principal
from skills.builtin.research_archive import ResearchArchiveSkill
from skills.registry import SkillRegistry
from workspace.context import bind_workspace, reset_workspace

CONTEXT = {
    "ontology": {"place": ["river", "city"]},
    "senses": ["shore", "finance"],
    "language": "en",
    "symbol": "bank",
    "context": {"place": "river"},
    "observations": [
        {"id": "e1", "context": {"place": "river"}, "sense": "shore", "source": "fixture:1"}
    ],
}


@pytest.fixture
def admin():
    token = bind_principal(TokenPayload("alice", "Alice", ["admin"], 9999999999, 0, "test"))
    try:
        yield
    finally:
        reset_principal(token)


@pytest.fixture
def imported_archive(tmp_path, monkeypatch):
    bundle = tmp_path / "fixture.zip"
    source = "Historical result: unresolved metric inconsistency; not proof of general accuracy."
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr("history/research.md", source)
        archive.writestr("history/unsafe.py", "raise RuntimeError('research must not execute')")
    monkeypatch.setattr(research, "BUNDLE_SHA256", hashlib.sha256(bundle.read_bytes()).hexdigest())
    destination = tmp_path / "research"
    research.import_bundle(bundle, destination)
    monkeypatch.setenv("MIZAN_RESEARCH_DIR", str(destination))
    return destination, hashlib.sha256(source.encode()).hexdigest()


async def test_search_real_import_returns_attributed_unverified_excerpts(admin, imported_archive):
    _, expected_sha = imported_archive
    result = await ResearchArchiveSkill().search("metric inconsistency")
    assert result["status"] == "ok"
    assert result["source_attributed"] is True
    assert result["training_gold"] is False and result["verified_claim"] is False
    assert result["archive_code_executed"] is False
    hit = result["results"][0]
    assert hit["path"] == "history/research.md" and hit["sha256"] == expected_sha
    assert hit["source"] == "pinned_research_archive"
    assert "inconsistency" in hit["excerpt"] and hit["verified_claim"] is False


async def test_missing_or_wrong_pin_is_unavailable_not_a_fake_empty_success(
    admin, tmp_path, monkeypatch, imported_archive
):
    imported, _ = imported_archive
    receipt = imported / "IMPORT.json"
    receipt.write_text(json.dumps({"bundle_sha256": "0" * 64}))
    assert (await ResearchArchiveSkill().search("metric"))["status"] == "unavailable"
    monkeypatch.setenv("MIZAN_RESEARCH_DIR", str(tmp_path / "absent"))
    result = await ResearchArchiveSkill().search("metric")
    assert result["status"] == "unavailable"
    assert "import or repair" in result["error"]


@pytest.mark.parametrize("roles", [[], ["user"], ["viewer"]])
async def test_identity_cannot_be_spoofed_through_skill_params_or_context(roles, monkeypatch):
    token = bind_principal(TokenPayload("nonadmin", "User", roles, 9999999999, 0, "test"))
    search = Mock(side_effect=AssertionError("Unprivileged requests must not read the archive"))
    monkeypatch.setattr(research, "search", search)
    try:
        skill = ResearchArchiveSkill()
        assert (await skill.search("metric"))["status"] == "forbidden"
        assert (await skill.context_resolve(**CONTEXT))["status"] == "forbidden"
        result = await skill.execute(
            {"action": "search", "query": "metric", "user_id": "admin"},
            {"roles": ["admin"], "user_id": "admin"},
        )
        assert result["status"] == "forbidden"
        search.assert_not_called()
    finally:
        reset_principal(token)


async def test_context_reasoning_is_stateless_and_requires_actual_declared_inputs(admin):
    skill = ResearchArchiveSkill()
    first = await skill.context_resolve(**CONTEXT)
    assert first["status"] == "EVIDENCE_ENTAILED"
    assert first["result"]["sense"] == "shore" and first["result"]["verified"] is False
    assert first["stateless"] is True and first["observations_persisted"] is False
    assert first["requires_observations_each_call"] is True
    assert first["observation_sources"] == [{"id": "e1", "source": "fixture:1"}]
    absent = await skill.context_resolve(**{**CONTEXT, "observations": []})
    assert absent["status"] == "AMBIGUOUS_FINITE_MEANING"
    retracted = await skill.context_resolve(**CONTEXT, retract_ids=["e1"])
    assert retracted["status"] == "AMBIGUOUS_FINITE_MEANING"
    invalid = await skill.context_resolve(**CONTEXT, verified=True, user_id="admin")
    assert invalid["status"] == "invalid_input"
    natural_language = await skill.context_resolve(text="bank means shore here")
    assert natural_language["status"] == "invalid_input"


async def test_context_conflicts_and_explicit_existential_unknowns_survive(admin):
    skill = ResearchArchiveSkill()
    contradictory = [
        *CONTEXT["observations"],
        {"id": "e2", "context": {"place": "river"}, "sense": "finance", "source": "fixture:2"},
    ]
    conflict = await skill.context_resolve(**{**CONTEXT, "observations": contradictory})
    assert conflict["status"] == "INCONSISTENT_EVIDENCE"
    partial = await skill.context_resolve(
        **{
            **CONTEXT,
            "mode": "episodic_exists",
            "observations": [{"id": "e1", "context": {}, "sense": "shore", "source": "fixture"}],
        }
    )
    assert partial["result"]["answered"] is False
    assert partial["verified_claim"] is False


async def test_bounded_search_and_context_validation(admin):
    skill = ResearchArchiveSkill()
    assert (await skill.search("x" * 301))["status"] == "invalid_input"
    oversized = {**CONTEXT, "ontology": {"place": [str(n) for n in range(257)]}}
    assert (await skill.context_resolve(**oversized))["status"] == "invalid_input"
    unknown = await skill.execute({"action": "search", "query": "metric", "root": "/elsewhere"})
    assert unknown["status"] == "invalid_input"


async def test_normal_agent_dispatches_research_tools_and_keeps_existing_role_workspace_gates(
    admin, imported_archive, monkeypatch, tmp_path, mock_wali
):
    from agents.base import BaseAgent
    from security.izn import IznPermission

    registry = SkillRegistry()
    registry._load_skill_module("skills.builtin.research_archive")
    assert registry.get_skill("research_archive") is not None
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("agents.base.create_provider", lambda **kwargs: None)
    agent = BaseAgent(
        name="research-test", skill_registry=registry, izn=IznPermission(), wali=mock_wali
    )

    class ScriptedLocalProvider:
        provider_name = "fixture"
        supports_tools = True

        def __init__(self):
            self.calls = 0

        def create(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                assert "mizan_research_search" in {row["name"] for row in kwargs["tools"]}
                return LLMResponse(
                    [
                        ContentBlock(
                            type="tool_use",
                            id="r1",
                            name="mizan_research_search",
                            input={"query": "metric"},
                        )
                    ],
                    stop_reason="tool_use",
                    model="fixture",
                )
            receipt = json.loads(kwargs["messages"][-1]["content"][0]["content"])
            assert receipt["results"][0]["source"] == "pinned_research_archive"
            assert receipt["verified_claim"] is False
            return LLMResponse(
                [ContentBlock(type="text", text="Historical source found; unverified.")]
            )

    provider = ScriptedLocalProvider()
    agent.ai_client = provider
    # Use the default developmental level and real Izn dispatch policy.
    chunks = [chunk async for chunk in agent.think("Inspect research on metric inconsistency.")]
    assert chunks[-1] == "Historical source found; unverified."
    assert provider.calls == 2
    resolved = await agent._execute_tool_safe("mizan_context_resolve", CONTEXT)
    assert resolved["result"]["sense"] == "shore"
    selected = bind_workspace("selected-project")
    try:
        assert "mizan_research_search" not in {row["name"] for row in agent.get_tool_schemas()}
        assert "error" in await agent._execute_tool_safe(
            "mizan_research_search", {"query": "metric"}
        )
    finally:
        reset_workspace(selected)
    nonadmin = bind_principal(TokenPayload("bob", "Bob", ["user"], 9999999999, 0, "test"))
    try:
        assert "mizan_context_resolve" not in {row["name"] for row in agent.get_tool_schemas()}
        assert "error" in await agent._execute_tool_safe("mizan_context_resolve", CONTEXT)
    finally:
        reset_principal(nonadmin)
