"""Learning lifecycle invariants on temporary machine fixtures, never corpus gold.

The test-only authors/reviewers and human_original labels exercise the strict
schema. They are not assertions of real human authorship or useful AI quality.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from mizan_owned import learning_cycle as learning

REAL_CAPACITY = learning._capacity


def fixture_capacity(_limits):
    # The shared test host's cgroup includes unrelated parallel agent activity.
    # Capacity parsing/admission is tested independently below; these tiny CPU
    # fixtures exercise the actual worker/resource/training/evaluation pipeline.
    return {
        "admitted": True,
        "available_bytes": 8 * 1024**3,
        "required_bytes": 5 * 1024**3,
        "api_reserve_bytes": 512 * 1024**2,
        "reason": "test_fixture_capacity",
    }


@pytest.fixture(autouse=True)
def fixture_admission(monkeypatch):
    monkeypatch.setattr(learning, "_capacity", fixture_capacity)


def write_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def policy(*, first=True):
    return {
        "schema_version": learning.POLICY_SCHEMA,
        "enabled": True,
        "allow_first_model": first,
        "gates": {
            "min_train_examples": 2,
            "min_dev_examples": 1,
            "max_dev_hinge": 0.1,
            "min_dev_byte_accuracy": 1.0,
            "min_generation_exact_match": 1.0,
            "min_generation_eos_rate": 1.0,
            "max_hinge_regression": 0.0,
            "max_byte_accuracy_drop": 0.0,
            "max_generation_exact_drop": 0.0,
        },
        "limits": {
            "max_new_tokens": 2,
            "train_seconds": 30,
            "evaluation_seconds": 30,
            "preflight_seconds": 30,
            "cycle_seconds": 120,
        },
    }


def make_bundle(root, name="fixture", *, first=True, origin="human_original"):
    root.mkdir(exist_ok=True)
    write_json(root / "policy.json", policy(first=first))
    bundle = root / "bundles" / name
    assets = bundle / "assets"
    assets.mkdir(parents=True)
    sources = []
    for split, prompts in (("train", ["a", "b"]), ("dev", ["c"])):
        text = f"Artificial {split} machine fixture, never an original corpus."
        (assets / f"{split}.txt").write_text(text)
        sources.append(
            {
                "source_id": split,
                "source_family": split,
                "kind": "other",
                "title": "Machine invariant fixture",
                "edition": "unit",
                "locator": split,
                "uri": f"urn:unit:{split}",
                "rights": "Ephemeral machine test only",
                "sha256": hashlib.sha256(text.encode()).hexdigest(),
                "local_path": f"assets/{split}.txt",
            }
        )
        rows = [
            {
                "schema_version": "mizan.reply.v1",
                "id": f"{split}-{i}",
                "split": split,
                "group_id": split,
                "language": "en",
                "task": "dialogue",
                "messages": [{"role": "user", "content": prompt}],
                "evidence": [],
                "target": {"text": "x", "citations": [], "answer_status": "answer"},
                "provenance": {
                    "origin": origin,
                    "source_ids": [split],
                    "rights": "Test-only schema declarations, not real original-data gold",
                    "author_ids": ["fixture-code"],
                    "reviewer_ids": ["fixture-test"],
                    "review_status": "accepted",
                },
            }
            for i, prompt in enumerate(prompts)
        ]
        (bundle / f"{split}.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    (bundle / "sources.jsonl").write_text("".join(json.dumps(row) + "\n" for row in sources))
    write_json(
        bundle / "config.json",
        {
            "model": {
                "dim": 8,
                "layers": 3,
                "kernel_size": 3,
                "max_seq_len": 15,
                "root_dim": 2,
                "root_mode": "none",
                "margin": 1.0,
            },
            "training": {
                "epochs": 100,
                "device": "cpu",
                "amp": "none",
                "seed": 17,
                "learning_rate": 0.03,
            },
        },
    )
    approve(bundle)
    return bundle


def approve(bundle):
    write_json(
        bundle / "approval.json",
        {
            "schema_version": learning.APPROVAL_SCHEMA,
            "bundle_sha256": learning.bundle_digest(bundle),
            "approved": True,
            "original_data_attested": True,
            "reviewer_id": "fixture-test",
            "evidence": "Machine invariant fixture declaration only; never used outside this test directory.",
        },
    )


@pytest.fixture(scope="module")
def trained(tmp_path_factory):
    pytest.importorskip("torch")
    root = tmp_path_factory.mktemp("owned-learning-machine-fixture")
    make_bundle(root)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(learning, "_capacity", fixture_capacity)
        receipt = learning.run_cycle(root, "fixture")
    assert receipt["status"] == "accepted", receipt
    assert receipt["activated"] is True
    return root, receipt


def copy_trained(trained, tmp_path):
    original, receipt = trained
    root = tmp_path / "learning"
    shutil.copytree(original, root)
    return root, receipt


def test_real_cpu_train_evaluate_and_activate(trained):
    root, receipt = trained
    selection = learning.resolve_active(root)
    assert selection["generation"] == 1
    assert selection["sha256"] == learning._hash_file(Path(selection["path"]))
    assert receipt["metrics"]["candidate"]["generation_exact_match"] == 1
    assert receipt["metrics"]["candidate"]["factual_accuracy_established"] is False
    assert receipt["ready_for_general_chat"] is False
    from mizan_reply.checkpoint import load_checkpoint

    checkpoint = load_checkpoint(selection["path"])
    assert checkpoint["runtime"]["device_type"] == "cpu"
    assert checkpoint["runtime"]["cpu_threads"] == 1
    assert checkpoint["world_size"] == 1
    assert checkpoint["optimizer_steps"] == 200
    assert checkpoint["epoch_completed"] == 100
    import torch
    from mizan_reply.model import MizanReplyModel, ModelConfig

    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(checkpoint["training_config"]["seed"])
        initial = MizanReplyModel(ModelConfig.from_dict(checkpoint["model_config"]))
    assert any(
        not torch.equal(checkpoint["model_state"][name], parameter)
        for name, parameter in initial.named_parameters()
    )
    assert stat_mode(Path(selection["path"])) == 0o400
    assert learning.status(root)["active"]["sha256"] == selection["sha256"]


def stat_mode(path):
    return path.stat().st_mode & 0o777


def test_repeat_bundle_is_idempotent_after_rollback(trained, tmp_path, monkeypatch):
    root, receipt = copy_trained(trained, tmp_path)
    before = learning._hash_file(Path(learning.resolve_active(root)["path"]))
    monkeypatch.setattr(learning, "_stage", lambda *a, **k: pytest.fail("must not retrain"))
    assert learning.run_cycle(root, "fixture")["generation"] == 1
    result = learning.rollback(root, expected_generation=1)
    assert result["generation"] == 2 and result["active"] is None
    assert learning.resolve_active(root) is None
    repeated = learning.run_cycle(root, "fixture")
    assert repeated["activated"] is False
    assert repeated["generation"] == 2
    assert (
        learning._hash_file(root / "candidates" / receipt["bundle_sha256"] / "checkpoint.pt")
        == before
    )


def test_generation_guard_and_busy_cycle(trained, tmp_path):
    root, _ = copy_trained(trained, tmp_path)
    with pytest.raises(learning.LearningError, match="generation_changed"):
        learning.rollback(root, expected_generation=0)
    with learning._writer(root):
        with pytest.raises(learning.LearningBusy):
            learning.run_cycle(root, "fixture")
        with pytest.raises(learning.LearningBusy):
            learning.rollback(root, expected_generation=1)
        assert learning.status(root)["busy"] is True


@pytest.mark.parametrize("which", ["checkpoint.pt", "receipt.json"])
def test_tampered_active_artifacts_fail_closed(trained, tmp_path, which):
    root, receipt = copy_trained(trained, tmp_path)
    path = root / "candidates" / receipt["bundle_sha256"] / which
    path.chmod(0o600)
    path.write_bytes(b"tampered")
    with pytest.raises(learning.LearningError):
        learning.resolve_active(root)
    assert learning.status(root)["status"] == "invalid"
    # Retreat to empty is safe even when the current artifact is unusable.
    assert learning.rollback(root, expected_generation=1)["active"] is None


def test_missing_initialized_registry_does_not_mean_no_model(trained, tmp_path):
    root, _ = copy_trained(trained, tmp_path)
    (root / "registry.json").unlink()
    with pytest.raises(learning.LearningError, match="registry_missing"):
        learning.resolve_active(root)


@pytest.mark.parametrize("mutation", ["approval", "asset", "symlink", "config", "test_file"])
def test_preflight_refusals_do_not_start_training(tmp_path, monkeypatch, mutation):
    root = tmp_path / "learning"
    bundle = make_bundle(root)
    if mutation == "approval":
        (bundle / "approval.json").unlink()
    elif mutation == "asset":
        (bundle / "assets/train.txt").write_text("changed original bytes")
    elif mutation == "symlink":
        (bundle / "assets/train.txt").unlink()
        (bundle / "assets/train.txt").symlink_to(root / "policy.json")
    elif mutation == "config":
        value = json.loads((bundle / "config.json").read_text())
        value["model"]["dim"] = 1_000_000
        write_json(bundle / "config.json", value)
    else:
        (bundle / "test.jsonl").write_text("not used for model selection")
    monkeypatch.setattr(learning, "_stage", lambda *a, **k: pytest.fail("worker must not start"))
    with pytest.raises(learning.LearningError):
        learning.run_cycle(root, "fixture")
    assert learning.resolve_active(root) is None


def test_accepted_machine_authored_data_is_refused_by_real_preflight(tmp_path):
    pytest.importorskip("torch")
    root = tmp_path / "learning"
    make_bundle(root, origin="machine_draft")
    result = learning.run_cycle(root, "fixture")
    assert result["status"] == "failed"
    assert result["gates"]["reasons"] == ["preflight_failed"]
    assert not list((root / "candidates").glob("*/training/latest.pt"))
    assert learning.resolve_active(root) is None


def test_failed_or_interrupted_job_does_not_activate(tmp_path, monkeypatch):
    root = tmp_path / "learning"
    make_bundle(root)

    def interrupt(*_args):
        raise learning.LearningInterrupted("test_interruption")

    monkeypatch.setattr(learning, "_stage", interrupt)
    with pytest.raises(learning.LearningInterrupted):
        learning.run_cycle(root, "fixture")
    assert learning.resolve_active(root) is None
    result = learning.run_cycle(root, "fixture")
    assert result["status"] == "interrupted" and result["activated"] is False
    assert learning.status(root)["busy"] is False


def test_crashed_unfinished_attempt_is_not_restarted(tmp_path, monkeypatch):
    root = tmp_path / "learning"
    bundle = make_bundle(root)
    digest = learning.bundle_digest(bundle)
    (root / "candidates" / digest).mkdir(parents=True)
    monkeypatch.setattr(
        learning, "_stage", lambda *a, **k: pytest.fail("must not restart orphan attempt")
    )
    result = learning.run_cycle(root, "fixture")
    assert result["status"] == "interrupted"
    assert result["gates"]["reasons"] == ["previous_attempt_interrupted"]
    assert learning.resolve_active(root) is None


def test_first_model_and_generation_quality_are_real_gates():
    good = {
        "dev_examples": 1,
        "hinge_per_target_token": 0.0,
        "byte_accuracy": 1.0,
        "generation_exact_match": 1.0,
        "generation_eos_rate": 1.0,
    }
    result = learning._gates(good, None, policy(first=False), 2)
    assert result["reasons"] == ["first_model_requires_operator_policy"]
    bad = good | {"generation_exact_match": 0.0}
    assert "generation_exact_below_limit" in learning._gates(bad, None, policy(), 2)["reasons"]
    assert "generation_exact_regression" in learning._gates(bad, good, policy(), 2)["reasons"]


def test_benchmark_includes_generation_budget_and_source_identity(tmp_path):
    bundle = make_bundle(tmp_path / "learning")
    before = learning._evaluation_identity(bundle, learning.LIMITS)
    assert learning._evaluation_identity(bundle, learning.LIMITS | {"max_new_tokens": 3}) != before
    sources = [json.loads(line) for line in (bundle / "sources.jsonl").read_text().splitlines()]
    sources[-1]["edition"] = "different original declaration"
    (bundle / "sources.jsonl").write_text("".join(json.dumps(row) + "\n" for row in sources))
    assert learning._evaluation_identity(bundle, learning.LIMITS) != before


def test_cumulative_snapshot_cannot_drop_previous_original_rows(tmp_path):
    bundle = make_bundle(tmp_path / "learning")
    old = tmp_path / "old"
    shutil.copytree(bundle, old)
    digest = learning.bundle_digest(old)
    rows = (bundle / "train.jsonl").read_text().splitlines()
    (bundle / "train.jsonl").write_text(rows[0] + "\n")
    with pytest.raises(learning.LearningError, match="accumulated_original"):
        learning._require_accumulated(old, bundle, learning.LIMITS, digest)


def test_timeout_reaps_worker_and_descendant_before_releasing_lock(tmp_path, monkeypatch):
    real_popen = subprocess.Popen
    started = tmp_path / "child-started"
    unsafe = tmp_path / "late-child-mutation"
    child = f"import pathlib,time;pathlib.Path({str(started)!r}).write_text('started');time.sleep(2);pathlib.Path({str(unsafe)!r}).write_text('unsafe')"
    parent = f"import subprocess,sys,time;subprocess.Popen([sys.executable,'-c',{child!r}]);time.sleep(10)"
    captured = {}

    def popen(_args, **kwargs):
        captured.update(kwargs)
        return real_popen([sys.executable, "-c", parent], **kwargs)

    monkeypatch.setattr(learning.subprocess, "Popen", popen)
    with learning._writer(tmp_path) as fd:
        with pytest.raises(learning.LearningError, match="train_timeout"):
            learning._stage(
                "train",
                tmp_path,
                {},
                learning.LIMITS | {"train_seconds": 1},
                time.monotonic() + 5,
                fd,
            )
    assert started.exists(), "child fixture must really have started"
    time.sleep(2.2)
    assert not unsafe.exists()
    assert captured["start_new_session"] is True
    assert "OPENROUTER_API_KEY" not in captured["env"]
    assert captured["env"]["CUDA_VISIBLE_DEVICES"] == ""
    with learning._writer(tmp_path):
        pass


def test_cli_status_and_invalid_bundle_are_bounded_json(tmp_path):
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "backend.mizan_owned.learning_cycle",
            "status",
            "--root",
            str(tmp_path),
        ],
        cwd=learning.SOURCE_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(process.stdout)["active"] is None
    with pytest.raises(learning.LearningError, match="invalid_bundle_id"):
        learning.run_cycle(tmp_path, "../outside")


def test_bundles_are_ready_only_with_bound_approval(tmp_path):
    root = tmp_path / "learning"
    bundle = make_bundle(root)
    assert learning.list_bundles(root)[0]["state"] == "ready"
    (bundle / "approval.json").unlink()
    assert learning.list_bundles(root)[0]["state"] == "pending"


def test_worker_resource_limits_refuse_non_linux(monkeypatch):
    from mizan_owned import learning_worker

    monkeypatch.setattr(learning_worker.sys, "platform", "unsupported")
    with pytest.raises(learning.LearningError, match="linux_resource_control_required"):
        learning_worker._limits({})


@pytest.mark.parametrize(
    "maximum,current,admitted,reason",
    [
        (2 * 1024**3, 512 * 1024**2, False, "insufficient_memory_headroom"),
        (8 * 1024**3, 1024**3, True, "sufficient_bounded_headroom"),
        ("max", 0, False, "memory_budget_unknown"),
    ],
)
def test_capacity_uses_cgroup_limit_current_and_api_reserve(
    monkeypatch, maximum, current, admitted, reason
):
    values = {
        "/proc/self/cgroup": b"0::/\n",
        "/sys/fs/cgroup/memory.max": str(maximum).encode(),
        "/sys/fs/cgroup/memory.current": str(current).encode(),
    }
    monkeypatch.setattr(learning, "_read", lambda path, *a: values[str(path)])
    result = REAL_CAPACITY(learning.LIMITS)
    assert result["admitted"] is admitted
    assert result["reason"] == reason
    assert result["required_bytes"] == (4096 + 512) * 1024**2


def test_capacity_refuses_before_worker_and_keeps_bundle_retryable(tmp_path, monkeypatch):
    root = tmp_path / "learning"
    make_bundle(root)
    monkeypatch.setattr(
        learning,
        "_capacity",
        lambda _: {"admitted": False, "reason": "insufficient_memory_headroom"},
    )
    monkeypatch.setattr(learning, "_stage", lambda *a, **k: pytest.fail("must not launch worker"))
    with pytest.raises(learning.LearningError, match="insufficient_memory_headroom"):
        learning.run_cycle(root, "fixture")
    assert not list((root / "candidates").iterdir())
    assert learning.list_bundles(root)[0]["state"] == "pending"
    result = learning.status(root)
    assert result["last_run"]["status"] == "refused"
    assert result["capacity"]["admitted"] is False


def fake_stages_from(trained):
    original, receipt = trained
    directory = original / "candidates" / receipt["bundle_sha256"]

    def stage(kind, _directory, payload, *_args):
        if kind == "train":
            output = Path(payload["output_dir"])
            output.mkdir()
            shutil.copyfile(directory / "checkpoint.pt", output / "latest.pt")
            return {"status": "training_complete"}
        return json.loads((directory / f"{kind}-result.json").read_text())

    return stage


def test_exception_after_atomic_activation_reconciles_real_selection(
    trained, tmp_path, monkeypatch
):
    root = tmp_path / "learning"
    make_bundle(root)
    monkeypatch.setattr(learning, "_stage", fake_stages_from(trained))
    atomic = learning._atomic
    interrupted = False

    def interrupt_after_commit(path, value, **kwargs):
        nonlocal interrupted
        atomic(path, value, **kwargs)
        if path.name == "registry.json" and value["generation"] == 1 and not interrupted:
            interrupted = True
            raise learning.LearningInterrupted("injected_after_registry_replace")

    monkeypatch.setattr(learning, "_atomic", interrupt_after_commit)
    result = learning.run_cycle(root, "fixture")
    assert result["status"] == "accepted" and result["activated"] is True
    assert result["completion_note"] == "activation_observed_before_exception"
    assert learning.status(root)["last_run"]["status"] == "accepted"
    assert learning.resolve_active(root)["sha256"] == result["checkpoint_sha256"]


def test_revoked_approval_before_commit_prevents_activation(trained, tmp_path, monkeypatch):
    root = tmp_path / "learning"
    bundle = make_bundle(root)
    stage = fake_stages_from(trained)

    def revoke(kind, *args):
        result = stage(kind, *args)
        if kind == "evaluate":
            approval = json.loads((bundle / "approval.json").read_text())
            approval["approved"] = False
            write_json(bundle / "approval.json", approval)
        return result

    monkeypatch.setattr(learning, "_stage", revoke)
    result = learning.run_cycle(root, "fixture")
    assert result["status"] == "failed" and result["activated"] is False
    assert result["gates"]["reasons"] == ["unapproved_original_data"]
    assert learning.resolve_active(root) is None


@pytest.mark.parametrize("rejection", ["first_model", "generation_quality"])
def test_completed_candidate_cannot_bypass_admission_gates(
    trained, tmp_path, monkeypatch, rejection
):
    root = tmp_path / "learning"
    make_bundle(root, first=rejection != "first_model")
    stage = fake_stages_from(trained)

    def measured(kind, *args):
        result = stage(kind, *args)
        if kind == "evaluate" and rejection == "generation_quality":
            result["generation"][0]["reference_exact_match"] = False
        return result

    monkeypatch.setattr(learning, "_stage", measured)
    result = learning.run_cycle(root, "fixture")
    assert result["status"] == "rejected" and result["activated"] is False
    assert result["gates"]["passed"] is False
    assert learning.resolve_active(root) is None
    assert learning.run_cycle(root, "fixture")["status"] == "rejected"


def test_existing_accepted_candidate_with_missing_checkpoint_is_not_success(trained, tmp_path):
    root, receipt = copy_trained(trained, tmp_path)
    learning.rollback(root, expected_generation=1)
    (root / "candidates" / receipt["bundle_sha256"] / "checkpoint.pt").unlink()
    with pytest.raises(learning.LearningError):
        learning.run_cycle(root, "fixture")
    result = learning.status(root)
    assert result["active"] is None
    assert result["runs"][0]["status"] == "invalid"


def test_real_accumulated_cycle_compares_baseline_and_rolls_back_to_prior(
    trained, tmp_path, monkeypatch
):
    root, first = copy_trained(trained, tmp_path)
    bundle = root / "bundles" / "second"
    shutil.copytree(root / "bundles/fixture", bundle)
    rows = [json.loads(line) for line in (bundle / "train.jsonl").read_text().splitlines()]
    extra = json.loads(json.dumps(rows[0]))
    extra.update(id="train-2", messages=[{"role": "user", "content": "d"}])
    (bundle / "train.jsonl").write_text("".join(json.dumps(row) + "\n" for row in [*rows, extra]))
    approve(bundle)
    result = learning.run_cycle(root, "second")
    assert result["status"] == "accepted", result
    assert result["generation"] == 2
    assert result["metrics"]["baseline"]["generation_exact_match"] == 1
    assert result["data"]["train_examples"] == 3
    rolled = learning.rollback(root, expected_generation=2)
    assert rolled["generation"] == 3
    assert rolled["active"]["sha256"] == first["checkpoint_sha256"]
    assert learning.resolve_active(root)["sha256"] == first["checkpoint_sha256"]


def test_real_provider_uses_registry_then_abstains_after_empty_rollback(
    trained, tmp_path, monkeypatch
):
    from mizan_owned.provider import OwnedProvider
    from mizan_owned.store import ReviewStore

    root, receipt = copy_trained(trained, tmp_path)
    monkeypatch.setenv("MIZAN_OWNED_LEARNING_DIR", str(root))
    provider = OwnedProvider(store=ReviewStore(str(tmp_path / "reviews.sqlite3")))
    arguments = {
        "model": "mizan-owned",
        "max_tokens": 2,
        "system": "",
        "messages": [{"role": "user", "content": "c"}],
    }
    before = provider.create(**arguments)
    assert before.usage["owned_checkpoint"]["sha256"] == receipt["checkpoint_sha256"]
    assert before.content[0].text == "x"
    learning.rollback(root, expected_generation=1)
    after = provider.create(**arguments)
    assert after.usage["owned_status"] == "abstained"
    assert after.usage["owned_reason"] == "registry_no_active_checkpoint"


def test_compact_registry_health_does_not_scan_learning_inputs(trained, tmp_path, monkeypatch):
    root, receipt = copy_trained(trained, tmp_path)
    monkeypatch.setattr(
        learning, "_inventory", lambda *a: pytest.fail("health must not scan corpora")
    )
    result = learning.registry_status(root)
    assert result["active"]["sha256"] == receipt["checkpoint_sha256"]
    assert result["generation"] == 1
    assert "path" not in result["active"]
    learning.rollback(root, expected_generation=1)
    result = learning.registry_status(root)
    assert result["active"] is None and result["generation"] == 2


def test_flattened_image_layout_runs_real_worker_preflight(tmp_path):
    pytest.importorskip("torch")
    image = tmp_path / "image"
    module = image / "mizan_owned"
    module.mkdir(parents=True)
    (module / "__init__.py").write_text("")
    for name in ("learning_cycle.py", "learning_worker.py"):
        shutil.copyfile(learning.BACKEND_ROOT / "mizan_owned" / name, module / name)
    for name in ("mizan_reply", "mizan_research"):
        shutil.copytree(learning.SOURCE_ROOT / name, image / name)
    registry = image / "research/registry"
    registry.mkdir(parents=True)
    shutil.copyfile(
        learning.SOURCE_ROOT / "research/registry/runtime_sources.json",
        registry / "runtime_sources.json",
    )
    root = tmp_path / "outside-image-learning"
    make_bundle(root)
    script = """
import json,sys
from mizan_owned import learning_cycle as cycle
cycle._capacity=lambda _: {'admitted': True}
stage=cycle._stage
def preflight_only(kind, *args):
    if kind != 'preflight':
        raise cycle.LearningError('test_stopped_after_real_preflight')
    return stage(kind,*args)
cycle._stage=preflight_only
print(json.dumps(cycle.run_cycle(sys.argv[1], 'fixture')))
"""
    process = subprocess.run(
        [sys.executable, "-c", script, str(root)],
        cwd=tmp_path,
        env={"PYTHONPATH": str(image), "PATH": os.defpath, "PYTHONUTF8": "1"},
        capture_output=True,
        text=True,
        timeout=45,
        check=True,
    )
    receipt = json.loads(process.stdout)
    assert receipt["gates"]["reasons"] == ["test_stopped_after_real_preflight"], receipt
    preflight = json.loads(
        (root / "candidates" / receipt["bundle_sha256"] / "preflight-result.json").read_text()
    )
    assert preflight["status"] == "validated_untrained"
    assert preflight["train_examples"] == 2
