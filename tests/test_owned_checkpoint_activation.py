"""Each owned request uses one verified registry selection; no restart or fallback."""

import hashlib
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

from mizan_owned.provider import MODEL, OwnedProvider, health
from mizan_owned.store import ReviewStore
from security.auth import TokenPayload, bind_principal, reset_principal

REQUEST = {"system": "fixture", "messages": [{"role": "user", "content": "hello"}]}


@pytest.fixture
def registry(tmp_path, monkeypatch):
    root = tmp_path / "learning"
    root.mkdir()
    legacy = tmp_path / "legacy.pt"
    legacy.write_bytes(b"legacy-weights")
    monkeypatch.setenv("MIZAN_OWNED_LEARNING_DIR", str(root))
    monkeypatch.setenv("MIZAN_REPLY_CHECKPOINT", str(legacy))
    monkeypatch.setenv("MIZAN_OWNED_DB", str(tmp_path / "owned.sqlite3"))
    module = ModuleType("mizan_owned.learning_cycle")
    state = SimpleNamespace(active=None, generation=0, invalid=False, initialized=False, calls=0)

    def resolve_active(selected_root):
        assert Path(selected_root) == root
        state.calls += 1
        if state.invalid:
            raise ValueError("private registry details must not reach chat")
        if state.active is None:
            return None
        selected = dict(state.active)
        if hashlib.sha256(Path(selected["path"]).read_bytes()).hexdigest() != selected["sha256"]:
            raise ValueError("tampered checkpoint")
        return selected

    def status(selected_root):
        try:
            active = resolve_active(selected_root)
        except ValueError:
            return {"configured": True, "status": "invalid", "active": None}
        return {
            "configured": True,
            "initialized": state.initialized,
            "generation": state.generation,
            "active": (
                {"sha256": active["sha256"], "generation": active["generation"]} if active else None
            ),
        }

    def activate(path):
        state.initialized = True
        state.generation += 1
        state.active = (
            {
                "path": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "generation": state.generation,
            }
            if path is not None
            else None
        )

    def checkpoint(name):
        path = root / (name + ".pt")
        path.write_bytes(name.encode())
        return path

    module.resolve_active = resolve_active
    module.registry_status = status
    module.status = Mock(side_effect=AssertionError("Provider health must not inspect bundles"))
    monkeypatch.setitem(sys.modules, module.__name__, module)
    hosted = Mock(side_effect=AssertionError("Owned inference must not construct a hosted adapter"))
    monkeypatch.setattr("providers.OpenAICompatibleProvider", hosted)
    return SimpleNamespace(
        root=root,
        legacy=legacy,
        state=state,
        module=module,
        activate=activate,
        checkpoint=checkpoint,
        hosted=hosted,
    )


@pytest.fixture
def local_runtime(monkeypatch):
    pytest.importorskip("torch")
    calls = []

    def load(path, device, *, include_sha256):
        assert include_sha256 is True
        data = Path(path).read_bytes()
        calls.append(str(path))
        model = SimpleNamespace(config=SimpleNamespace(max_seq_len=2048), marker=data.decode())
        return model, {}, hashlib.sha256(data).hexdigest()

    def generate(model, *args, **kwargs):
        return SimpleNamespace(text="answer from " + model.marker, eos=True)

    monkeypatch.setattr("mizan_reply.evaluate.load_inference_model", load)
    monkeypatch.setattr("mizan_reply.generation.generate", generate)
    return SimpleNamespace(load=load, calls=calls)


def request(provider):
    return provider.create(MODEL, 64, **REQUEST)


def test_same_provider_hot_promotes_and_rolls_back_verified_weights(registry, local_runtime):
    first, second = registry.checkpoint("first"), registry.checkpoint("second")
    registry.activate(first)
    provider = OwnedProvider()
    initial = request(provider)
    assert initial.content[0].text == "answer from first"
    assert initial.usage["owned_checkpoint"] == {
        "source": "registry",
        "sha256": registry.state.active["sha256"],
        "generation": 1,
    }
    assert request(provider).content[0].text == initial.content[0].text
    registry.activate(second)
    promoted = request(provider)
    assert promoted.content[0].text == "answer from second"
    assert promoted.usage["owned_checkpoint"]["generation"] == 2
    registry.activate(first)
    rollback = request(provider)
    assert rollback.content[0].text == "answer from first"
    assert rollback.usage["owned_checkpoint"]["generation"] == 3
    assert local_runtime.calls == [str(first), str(second), str(first)]
    registry.hosted.assert_not_called()


def test_new_generation_of_identical_checkpoint_does_not_reload(registry, local_runtime):
    path = registry.checkpoint("same")
    registry.activate(path)
    provider = OwnedProvider()
    request(provider)
    registry.activate(path)
    response = request(provider)
    assert response.usage["owned_checkpoint"]["generation"] == 2
    assert local_runtime.calls == [str(path)]


def test_uninitialized_registry_blocks_legacy_then_activation_works_without_restart(
    registry, local_runtime
):
    provider = OwnedProvider()
    response = request(provider)
    assert response.usage["owned_status"] == "abstained"
    assert response.usage["owned_reason"] == "registry_no_active_checkpoint"
    assert local_runtime.calls == []
    registry.activate(registry.checkpoint("activated"))
    assert request(provider).content[0].text == "answer from activated"
    assert str(registry.legacy) not in local_runtime.calls


@pytest.mark.parametrize("invalid", [False, True])
def test_empty_or_invalid_registry_cannot_reuse_previous_or_environment_model(
    registry, local_runtime, invalid
):
    path = registry.checkpoint("first")
    registry.activate(path)
    provider = OwnedProvider()
    request(provider)
    registry.activate(None)
    registry.state.invalid = invalid
    response = request(provider)
    assert response.usage["owned_status"] == "abstained"
    assert response.usage["owned_reason"] == (
        "registry_invalid" if invalid else "registry_no_active_checkpoint"
    )
    assert "private registry details" not in response.content[0].text
    assert "owned_checkpoint" not in response.usage
    assert local_runtime.calls == [str(path)]
    registry.hosted.assert_not_called()


def test_tampered_cached_checkpoint_is_rejected_before_reuse(registry, local_runtime):
    path = registry.checkpoint("first")
    registry.activate(path)
    provider = OwnedProvider()
    request(provider)
    path.write_bytes(b"tampered")
    response = request(provider)
    assert response.usage["owned_status"] == "abstained"
    assert response.usage["owned_reason"] == "registry_invalid"
    assert local_runtime.calls == [str(path)]


def test_loaded_snapshot_hash_must_match_selection_before_model_is_installed(
    registry, local_runtime, monkeypatch
):
    first, second = registry.checkpoint("first"), registry.checkpoint("second")
    registry.activate(first)
    provider = OwnedProvider()
    initial = request(provider)
    registry.activate(second)

    def changed_snapshot(path, device, *, include_sha256):
        loaded, metadata, _ = local_runtime.load(path, device, include_sha256=include_sha256)
        return loaded, metadata, "0" * 64

    monkeypatch.setattr("mizan_reply.evaluate.load_inference_model", changed_snapshot)
    rejected = request(provider)
    assert rejected.usage["owned_reason"] == "checkpoint_hash_mismatch"
    assert rejected.usage["owned_status"] == "abstained"
    assert "owned_checkpoint" not in rejected.usage
    assert provider._sha == initial.usage["owned_checkpoint"]["sha256"]
    registry.activate(first)
    rollback = request(provider)
    assert rollback.content[0].text == "answer from first"
    assert rollback.usage["owned_checkpoint"]["generation"] == 3
    assert local_runtime.calls == [str(first), str(second)]


def test_failed_checkpoint_load_is_clear_abstention_not_a_fallback(
    registry, local_runtime, monkeypatch
):
    registry.activate(registry.checkpoint("broken"))

    def broken_loader(*args, **kwargs):
        raise EOFError("private invalid tensor bytes")

    monkeypatch.setattr("mizan_reply.evaluate.load_inference_model", broken_loader)
    response = request(OwnedProvider())
    assert response.usage["owned_status"] == "abstained"
    assert response.usage["owned_reason"] == "checkpoint_load_failed"
    assert "private invalid" not in response.content[0].text
    registry.hosted.assert_not_called()


def test_each_concurrent_request_pins_its_generation_during_promotion(
    registry, local_runtime, monkeypatch
):
    first, second = registry.checkpoint("first"), registry.checkpoint("second")
    registry.activate(first)
    provider = OwnedProvider()
    started, release = threading.Event(), threading.Event()
    seen = []

    def generate(model, *args, **kwargs):
        seen.append(model.marker)
        if model.marker == "first":
            started.set()
            assert release.wait(5), "test did not release the pinned generation"
        return SimpleNamespace(text="answer from " + model.marker, eos=True)

    monkeypatch.setattr("mizan_reply.generation.generate", generate)
    with ThreadPoolExecutor(max_workers=2) as executor:
        old_request = executor.submit(request, provider)
        try:
            assert started.wait(5), "first request did not begin generation"
            registry.activate(second)
            new_request = executor.submit(request, provider)
        finally:
            release.set()
        old, new = old_request.result(timeout=5), new_request.result(timeout=5)
    assert old.content[0].text == "answer from first"
    assert old.usage["owned_checkpoint"]["generation"] == 1
    assert new.content[0].text == "answer from second"
    assert new.usage["owned_checkpoint"]["generation"] == 2
    assert seen == ["first", "second"]
    assert local_runtime.calls == [str(first), str(second)]


def test_legacy_environment_loading_is_preserved_when_registry_unset(
    registry, local_runtime, monkeypatch
):
    monkeypatch.delenv("MIZAN_OWNED_LEARNING_DIR")
    provider = OwnedProvider()
    first, second = request(provider), request(provider)
    assert first.content[0].text == second.content[0].text == "answer from legacy-weights"
    assert first.usage["owned_checkpoint"]["source"] == "environment"
    assert "generation" not in first.usage["owned_checkpoint"]
    assert local_runtime.calls == [str(registry.legacy)]
    assert registry.state.calls == 0


def test_custom_decoder_cannot_bypass_configured_registry(registry):
    decoder = Mock(return_value=("unregistered model reply", True))
    response = request(OwnedProvider(decoder=decoder))
    assert response.usage["owned_reason"] == "registry_decoder_override"
    assert response.usage["owned_status"] == "abstained"
    decoder.assert_not_called()


def test_unexpected_registry_fault_is_reported_without_fallback(registry, monkeypatch):
    def broken(*args):
        raise AttributeError("private malformed registry state")

    monkeypatch.setattr(registry.module, "resolve_active", broken)
    monkeypatch.setattr(registry.module, "registry_status", broken)
    response = request(OwnedProvider())
    assert response.usage["owned_reason"] == "registry_invalid"
    assert response.usage["owned_status"] == "abstained"
    assert "private malformed" not in response.content[0].text
    assert health()["status"] == "invalid"
    registry.hosted.assert_not_called()


def test_reviewed_replay_stays_owner_bound_even_when_registry_is_invalid(registry):
    store = ReviewStore(str(registry.root / "reviews.sqlite3"))
    row = store.save("alice", REQUEST, "Reviewed owner answer", "teacher", True)
    store.review(
        "alice",
        row["id"],
        reviewer="alice",
        expected_hash=row["answer_hash"],
        accepted=True,
        evidence="reviewed-source",
    )
    registry.state.invalid = True
    provider = OwnedProvider(store)
    for owner in ("alice", "bob"):
        binding = bind_principal(TokenPayload(owner, owner, ["user"], 9999999999, 0, owner))
        try:
            response = request(provider)
        finally:
            reset_principal(binding)
        if owner == "alice":
            assert response.content[0].text == "Reviewed owner answer"
            assert response.usage["owned_status"] == "reviewed_memory"
        else:
            assert response.usage["owned_status"] == "abstained"
            assert response.usage["owned_reason"] == "registry_invalid"


def test_health_reports_registry_generation_without_loading_or_general_readiness(registry):
    empty = health()
    assert empty["controller_healthy"] is True
    assert empty["checkpoint_source"] == "registry"
    assert empty["checkpoint_exists"] is False
    assert empty["checkpoint_ready"] is False
    assert empty["registry_generation"] == 0
    registry.activate(registry.checkpoint("ready-for-load"))
    active = health()
    assert active["registry_generation"] == 1
    assert active["checkpoint_ready"] is True
    assert active["ready_for_general_chat"] is False
    assert active["external_inference"] is False
    assert str(registry.root) not in json.dumps(active)
    registry.state.invalid = True
    invalid = health()
    assert invalid["status"] == "invalid"
    assert invalid["controller_healthy"] is True
    assert invalid["checkpoint_ready"] is False
    assert invalid["ready_for_general_chat"] is False
    registry.module.status.assert_not_called()


def test_health_uses_real_compact_snapshot_without_bundle_inventory(tmp_path, monkeypatch):
    from mizan_owned import learning_cycle

    root = tmp_path / "learning"
    root.mkdir()
    state = {
        "schema_version": learning_cycle.SCHEMA,
        "generation": 7,
        "active": None,
        "rollback_chain": [],
    }
    (root / "registry.json").write_text(json.dumps(state), encoding="utf-8")
    legacy = tmp_path / "legacy.pt"
    legacy.write_bytes(b"must not become the active model")
    monkeypatch.setenv("MIZAN_OWNED_LEARNING_DIR", str(root))
    monkeypatch.setenv("MIZAN_REPLY_CHECKPOINT", str(legacy))
    forbidden = Mock(side_effect=AssertionError("Routine health must not scan training data"))
    for name in ("status", "list_bundles", "_inventory", "_policy"):
        monkeypatch.setattr(learning_cycle, name, forbidden)

    observed = health()
    assert observed["status"] == "ok"
    assert observed["registry_generation"] == 7
    assert observed["checkpoint_source"] == "registry"
    assert observed["checkpoint_ready"] is False
    assert observed["ready_for_general_chat"] is False
    assert observed["controller_healthy"] is True
    (root / "registry.json").write_bytes(b"invalid registry")
    invalid = health()
    assert invalid["status"] == "invalid"
    assert invalid["checkpoint_exists"] is False
    assert invalid["ready_for_general_chat"] is False
    forbidden.assert_not_called()


def test_real_cpu_snapshots_activate_without_reloading_unchanged_weights(registry, monkeypatch):
    torch = pytest.importorskip("torch")
    from mizan_reply.checkpoint import FORMAT, atomic_save, capture_rng
    from mizan_reply.evaluate import load_inference_model
    from mizan_reply.model import MizanReplyModel, ModelConfig
    from mizan_reply.train import TrainingConfig

    torch.set_num_threads(1)
    paths = []
    for name, value in (("cpu-first", 0.125), ("cpu-second", 0.25)):
        model = MizanReplyModel(ModelConfig(dim=8, layers=8, max_seq_len=256, root_dim=3))
        with torch.no_grad():
            next(model.parameters()).fill_(value)
        path = registry.root / (name + ".pt")
        atomic_save(
            path,
            {
                "format": FORMAT,
                "checkpoint_boundary": "complete_epoch",
                "model_config": model.config.to_dict(),
                "training_config": asdict(TrainingConfig(device="cpu")),
                "model_state": model.state_dict(),
                "optimizer_state": {},
                "scaler_state": {},
                "data_manifest": {},
                "epoch_completed": 0,
                "optimizer_steps": 0,
                "world_size": 1,
                "runtime": {},
                "rng_by_rank": [capture_rng()],
            },
        )
        paths.append(path)
    loader = Mock(wraps=load_inference_model)
    monkeypatch.setattr("mizan_reply.evaluate.load_inference_model", loader)

    def generate(model, *args, **kwargs):
        return SimpleNamespace(
            text=f"weight {next(model.parameters()).flatten()[0].item()}", eos=True
        )

    monkeypatch.setattr("mizan_reply.generation.generate", generate)
    provider = OwnedProvider()
    registry.activate(paths[0])
    assert request(provider).content[0].text == "weight 0.125"
    request(provider)
    registry.activate(paths[1])
    changed = request(provider)
    assert changed.content[0].text == "weight 0.25"
    assert (
        changed.usage["owned_checkpoint"]["sha256"]
        == hashlib.sha256(paths[1].read_bytes()).hexdigest()
    )
    assert loader.call_count == 2
