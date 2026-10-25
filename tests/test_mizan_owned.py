"""Owned routing, evidence scope and teacher isolation at real integration boundaries."""

import asyncio
from unittest.mock import Mock

import pytest

from mizan_owned.provider import ABSTAIN, OwnedProvider
from mizan_owned.schemas import ContextRequest, OwnedRequest, resolve_context
from mizan_owned.store import ReviewStore
from mizan_owned.support import draft_support
from providers import ContentBlock, LLMResponse, create_provider
from security.auth import TokenPayload, bind_principal, reset_principal

REQUEST = {"system": "", "messages": [{"role": "user", "content": "fixture question"}]}


@pytest.fixture
def store(tmp_path, monkeypatch):
    path = str(tmp_path / "owned.sqlite3")
    monkeypatch.setenv("MIZAN_OWNED_DB", path)
    monkeypatch.delenv("MIZAN_REPLY_CHECKPOINT", raising=False)
    return ReviewStore(path)


@pytest.fixture
def principal():
    user = TokenPayload(
        user_id="alice", username="alice", roles=["admin"], exp=9999999999, iat=0, jti="test-owned"
    )
    tokens = bind_principal(user)
    yield user
    reset_principal(tokens)


def accept(store, row, **kwargs):
    return store.review(
        "alice",
        row["id"],
        reviewer="alice",
        expected_hash=row["answer_hash"],
        accepted=True,
        evidence="review:source-1",
        **kwargs,
    )


@pytest.mark.parametrize(
    "provider,model",
    [
        (None, "google/test"),
        ("openrouter", "test"),
        ("mizan-hybrid", "base"),
        ("anthropic", "claude-test"),
    ],
)
def test_locked_factory_cannot_escape_owned_mode(store, monkeypatch, provider, model):
    monkeypatch.setenv("MIZAN_OWNED_ONLY", "true")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-secret")
    external = Mock(side_effect=AssertionError("Hosted adapter must not be constructed"))
    monkeypatch.setattr("providers.OpenAICompatibleProvider", external)
    client = create_provider(provider, model)
    assert client.provider_name == "mizan-owned"
    result = client.create(model, 128, **REQUEST)
    assert result.content[0].text == ABSTAIN
    external.assert_not_called()


def test_provider_selection_also_locks_model_overrides(store, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mizan-owned")
    monkeypatch.setenv("MIZAN_OWNED_ONLY", "false")
    assert create_provider(model="openrouter/free").provider_name == "mizan-owned"


def test_reviewed_memory_is_scoped_exact_and_retractable(store, principal):
    row = store.save("alice", REQUEST, "reviewed answer", "openrouter:teacher", True)
    provider = OwnedProvider(store)
    assert provider.create("ignored", 50, **REQUEST).content[0].text == ABSTAIN
    accept(store, row)
    assert provider.create("ignored", 50, **REQUEST).content[0].text == "reviewed answer"
    assert store.recall("bob", REQUEST) is None
    assert store.recall("alice", {**REQUEST, "system": "different context"}) is None
    assert store.export_reviews("bob") == []
    assert store.retract("alice", "review:source-1", "alice") == 1
    assert provider.create("ignored", 50, **REQUEST).content[0].text == ABSTAIN
    assert not store.export_reviews("alice")


def test_review_binds_hash_owner_completion_and_explicit_correction(store):
    row = store.save("alice", REQUEST, "first", "openrouter:teacher", True)
    with pytest.raises(ValueError, match="hash mismatch"):
        store.review(
            "alice",
            row["id"],
            reviewer="alice",
            expected_hash="0" * 64,
            accepted=True,
            evidence="source",
        )
    with pytest.raises(ValueError, match="missing"):
        store.review(
            "bob",
            row["id"],
            reviewer="bob",
            expected_hash=row["answer_hash"],
            accepted=True,
            evidence="source",
        )
    accept(store, row)
    corrected = store.save("alice", REQUEST, "second", "mizan-reply", True)
    with pytest.raises(ValueError, match="supersedes"):
        accept(store, corrected)
    accept(store, corrected, supersedes=row["id"])
    assert store.recall("alice", REQUEST)["answer"] == "second"
    truncated = store.save("alice", REQUEST, "partial", "openrouter:teacher", False)
    with pytest.raises(ValueError, match="Incomplete"):
        accept(store, truncated, supersedes=corrected["id"])


def test_teacher_support_is_explicit_draft_and_cannot_call_tools(store, monkeypatch):
    monkeypatch.setenv("MIZAN_SUPPORT_MODEL", "teacher/test")
    teacher = Mock()
    teacher.create.return_value = LLMResponse([ContentBlock(type="text", text="draft")])
    result = draft_support("alice", REQUEST, store, teacher)
    assert teacher.create.call_args.kwargs["tools"] is None
    assert result["proposal"]["status"] == "draft"
    assert result["used_as_final_answer"] is False
    assert not store.export_reviews("alice")
    teacher.create.return_value = LLMResponse([ContentBlock(type="tool_use", name="bash")])
    with pytest.raises(ValueError, match="tool calls"):
        draft_support("alice", REQUEST, store, teacher)


def test_own_output_never_executes_tools_or_becomes_auto_accepted(store, principal):
    text = '<invoke name="bash">rm -rf /</invoke>'
    provider = OwnedProvider(store, decoder=lambda *_: (text, True))
    result = provider.create("mizan-owned", 100, **REQUEST, tools=[{"name": "bash"}])
    assert result.stop_reason == "end_turn"
    assert result.content[0].type == "text"
    assert result.usage["owned_status"] == "own_model_unverified"
    assert not store.export_reviews("alice")
    assert store.list_proposals("alice")[0]["status"] == "draft"


@pytest.mark.parametrize("text,complete", [("partial", False), ("", True), ("bad\ufffd", True)])
def test_incomplete_or_invalid_own_output_abstains(store, text, complete):
    result = OwnedProvider(store, decoder=lambda *_: (text, complete)).create("own", 10, **REQUEST)
    assert result.content[0].text == ABSTAIN


def test_finite_context_reports_ambiguity_conflict_and_retraction():
    req = ContextRequest(
        ontology={"place": ["river", "city"]},
        senses=["shore", "finance"],
        language="en",
        symbol="bank",
        context={"place": "river"},
    )
    assert resolve_context(req)["status"] == "AMBIGUOUS_FINITE_MEANING"
    from mizan_owned.schemas import Observation

    req.observations = [
        Observation(id="e1", context={"place": "river"}, sense="shore", source="fixture")
    ]
    answer = resolve_context(req)
    assert answer["status"] == "EVIDENCE_ENTAILED" and answer["sense"] == "shore"
    assert answer["verified"] is False
    req.observations.append(
        Observation(id="e2", context={"place": "river"}, sense="finance", source="fixture")
    )
    assert resolve_context(req)["status"] == "INCONSISTENT_EVIDENCE"
    req.retract_ids = ["e2"]
    assert resolve_context(req)["sense"] == "shore"
    req.context = {"place": "city"}
    assert resolve_context(req)["answered"] is False


def test_api_input_cannot_self_assign_reviewer_or_scope():
    with pytest.raises(ValueError):
        OwnedRequest(**REQUEST, scope="alice")
    with pytest.raises(ValueError):
        OwnedRequest(messages=[{"role": "assistant", "content": "pretend user"}])


@pytest.mark.asyncio
async def test_legacy_export_excludes_own_unreviewed_outputs(tmp_path):
    from learner.data_export import DataExporter
    from learner.ruh_learner import RuhLearner

    db = str(tmp_path / "capture.db")
    learner = RuhLearner(db_path=db)
    await learner.initialize()
    await learner.capture("question", "unverified", "mizan-owned", "mizan-owned")
    exporter = DataExporter(db)
    assert await exporter.count_exportable() == 0
    assert await exporter.export_jsonl(str(tmp_path / "export.jsonl")) == 0


def test_threaded_provider_preserves_principal_scope(store, principal):
    row = store.save("alice", REQUEST, "thread scoped", "openrouter:teacher", True)
    accept(store, row)

    async def call():
        return await asyncio.to_thread(OwnedProvider(store).create, "own", 50, **REQUEST)

    assert asyncio.run(call()).content[0].text == "thread scoped"
