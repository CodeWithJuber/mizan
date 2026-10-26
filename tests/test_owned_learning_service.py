"""Service and HTTP boundaries for local owned-model learning."""

import asyncio
import signal
import sys
import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from mizan_owned.learning_service import OwnedLearningService, worker_environment


def test_worker_environment_excludes_provider_and_deployment_credentials(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "private-provider-fixture")
    monkeypatch.setenv("SECRET_KEY", "private-jwt-fixture")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "private-aws-fixture")
    monkeypatch.setenv("PYTHONPATH", "/untrusted/fixture")
    env = worker_environment()
    assert not {"OPENROUTER_API_KEY", "SECRET_KEY", "AWS_ACCESS_KEY_ID", "RANK"} & env.keys()
    assert "/untrusted/fixture" not in env["PYTHONPATH"]
    assert env["CUDA_VISIBLE_DEVICES"] == ""
    assert env["OMP_NUM_THREADS"] == "1"


@pytest.mark.asyncio
async def test_unconfigured_status_does_not_claim_training_or_model_readiness(monkeypatch):
    monkeypatch.delenv("MIZAN_OWNED_LEARNING_DIR", raising=False)
    monkeypatch.delenv("MIZAN_OWNED_LEARNING_AUTORUN", raising=False)
    result = await OwnedLearningService().snapshot()
    assert result["configured"] is False
    assert result["active"] is None
    assert result["ready_for_general_chat"] is False
    assert result["chat_capture_is_training_data"] is False
    assert result["automation_active"] is False


@pytest.mark.asyncio
async def test_chat_status_tracks_actual_watcher_lifecycle(tmp_path, monkeypatch):
    from api.commands import cmd_status

    monkeypatch.setenv("MIZAN_OWNED_LEARNING_DIR", str(tmp_path))
    monkeypatch.setenv("MIZAN_OWNED_LEARNING_AUTORUN", "true")
    service = OwnedLearningService()
    monkeypatch.setattr("mizan_owned.learning_service.learning_service", service)
    assert "**automatic_weight_training:** disabled" in await cmd_status()
    await service.start()
    try:
        report = await cmd_status()
        assert "watching for approved original-data bundles" in report
        assert "**owned_learning_worker_busy:** False" in report
        assert "does not update model weights" in report
        assert service.last_job is None
    finally:
        await service.stop()
    assert "**automatic_weight_training:** disabled" in await cmd_status()


@pytest.mark.asyncio
async def test_ready_bundle_is_queued_once_and_cancelled_on_shutdown(tmp_path, monkeypatch):
    from mizan_owned.learning_cycle import LearningBusy

    monkeypatch.setenv("MIZAN_OWNED_LEARNING_DIR", str(tmp_path))
    monkeypatch.setattr(
        "mizan_owned.learning_cycle.list_bundles",
        lambda root: [{"bundle_id": "reviewed-v1", "state": "ready"}],
    )
    service = OwnedLearningService()
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def run(root, bundle_id, job):
        job["state"] = "running"
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            job["state"] = "interrupted"
            cancelled.set()

    monkeypatch.setattr(service, "_run", run)
    result = await service.start_cycle("reviewed-v1", requested_by="authenticated-admin")
    assert result["state"] == "queued"
    assert result["requested_by"] == "authenticated-admin"
    await started.wait()
    with pytest.raises(LearningBusy):
        await service.start_cycle("reviewed-v1", requested_by="second-admin")
    await service.stop()
    assert cancelled.is_set()
    assert not service.busy
    assert service.last_job["state"] == "interrupted"


@pytest.mark.asyncio
@pytest.mark.parametrize("bundle_id", ["../outside", "name/child", "", "bundle\n"])
async def test_invalid_bundle_id_never_reaches_worker(bundle_id, monkeypatch):
    spawn = AsyncMock()
    monkeypatch.setattr("asyncio.create_subprocess_exec", spawn)
    with pytest.raises(ValueError):
        await OwnedLearningService().start_cycle(bundle_id, requested_by="admin")
    spawn.assert_not_called()


@pytest.mark.asyncio
async def test_processed_or_unapproved_bundle_is_not_resubmitted(tmp_path, monkeypatch):
    monkeypatch.setenv("MIZAN_OWNED_LEARNING_DIR", str(tmp_path))
    monkeypatch.setattr(
        "mizan_owned.learning_cycle.list_bundles",
        lambda root: [{"bundle_id": "old", "state": "processed"}],
    )
    service = OwnedLearningService()
    with pytest.raises(ValueError):
        await service.start_cycle("old", requested_by="admin")
    assert service.last_job is None


@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform != "linux", reason="The learning supervisor requires Linux")
@pytest.mark.parametrize("mode", ["shutdown", "timeout"])
async def test_worker_group_cleanup_reaches_term_ignoring_descendant(tmp_path, monkeypatch, mode):
    """A reaped leader cannot leave its child writing after the job finishes."""
    started = tmp_path / "descendant-started"
    late_write = tmp_path / "descendant-wrote-after-cleanup"
    child = (
        "import pathlib,signal,time;"
        "signal.signal(signal.SIGTERM,signal.SIG_IGN);"
        f"pathlib.Path({str(started)!r}).write_text('started');"
        "time.sleep(1.2);"
        f"pathlib.Path({str(late_write)!r}).write_text('unsafe')"
    )
    leader = (
        "import subprocess,sys,time;"
        f"subprocess.Popen([sys.executable,'-c',{child!r}]);"
        "time.sleep(30)"
    )
    service = OwnedLearningService()
    real_spawn = asyncio.create_subprocess_exec
    processes = []
    calls = []

    async def wait_for(predicate):
        async def ready():
            while not predicate():
                await asyncio.sleep(0.01)

        await asyncio.wait_for(ready(), timeout=3)

    async def controlled_spawn(*args, **kwargs):
        calls.append((args, kwargs))
        process = await real_spawn(sys.executable, "-c", leader, **kwargs)
        processes.append(process)
        try:
            # The supervisor's timeout starts only after the child has installed
            # SIG_IGN, so this proves cleanup rather than winning a startup race.
            await wait_for(started.exists)
        except BaseException:
            await service._terminate(process)
            raise
        return process

    monkeypatch.setattr("asyncio.create_subprocess_exec", controlled_spawn)
    monkeypatch.setattr(
        "mizan_owned.learning_service.SUPERVISOR_TIMEOUT", 0.2 if mode == "timeout" else 10
    )
    job = {"state": "queued"}
    task = asyncio.create_task(service._run(tmp_path, "fixture", job))
    service._task = task
    try:
        await wait_for(lambda: service._process is not None)
        assert started.exists()
        if mode == "shutdown":
            await service.stop()
            assert task.cancelled()
            assert job["state"] == "interrupted"
        else:
            await asyncio.wait_for(asyncio.shield(task), timeout=4)
            assert job["state"] == "timed_out"
        assert processes[0].returncode == -signal.SIGTERM
        assert service._process is None
        assert not service.busy
        assert calls[0][0][1:3] == ("-m", "mizan_owned.learning_cycle")
        assert calls[0][1]["start_new_session"] is True
        await asyncio.sleep(1.4)
        assert not late_write.exists(), "the TERM-ignoring descendant survived group cleanup"
    finally:
        if not task.done():
            await service.stop()


@pytest.fixture
def owned_api(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "owned-cycle-auth-test-fixture-key")
    monkeypatch.setenv("DB_PATH", ":memory:")
    monkeypatch.setenv("MIZAN_OWNED_DB", str(tmp_path / "reviews.db"))
    monkeypatch.delenv("MIZAN_OWNED_LEARNING_DIR", raising=False)
    monkeypatch.delenv("MIZAN_OWNED_LEARNING_AUTORUN", raising=False)
    from api.main import app, auth

    service = OwnedLearningService()
    monkeypatch.setattr("mizan_owned.learning_service.learning_service", service)
    client = TestClient(app)

    def identity(role):
        user = auth.create_user("cycle-" + uuid.uuid4().hex, "test-fixture-pass", roles=[role])
        return {"Authorization": "Bearer " + auth.create_token(user)}

    return client, identity("admin"), identity("user"), service


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("get", "/api/owned/learning", None),
        ("post", "/api/owned/learning/run", {"bundle_id": "reviewed-v1"}),
        ("post", "/api/owned/learning/rollback", {"expected_generation": 1}),
    ],
)
def test_learning_routes_require_admin(owned_api, method, path, body):
    client, admin, user, _ = owned_api
    kwargs = {"json": body} if body else {}
    call = getattr(client, method)
    assert call(path, **kwargs).status_code == 401
    assert call(path, headers=user, **kwargs).status_code == 403
    if method == "get":
        result = call(path, headers=admin)
        assert result.status_code == 200
        assert result.json()["configured"] is False


def test_api_queue_receipt_is_not_training_completion_and_actor_cannot_be_spoofed(
    owned_api, monkeypatch
):
    client, admin, _, service = owned_api
    start = AsyncMock(return_value={"id": "job", "state": "queued"})
    monkeypatch.setattr(service, "start_cycle", start)
    response = client.post(
        "/api/owned/learning/run", headers=admin, json={"bundle_id": "reviewed-v1"}
    )
    assert response.status_code == 202
    assert response.json()["training_complete"] is False
    assert start.call_args.kwargs["requested_by"]
    assert (
        client.post(
            "/api/owned/learning/run",
            headers=admin,
            json={"bundle_id": "reviewed-v1", "requested_by": "spoof"},
        ).status_code
        == 422
    )


def test_api_rollback_preserves_generation_guard_and_reports_conflict(
    owned_api, monkeypatch, tmp_path
):
    client, admin, _, _ = owned_api
    monkeypatch.setenv("MIZAN_OWNED_LEARNING_DIR", str(tmp_path))
    calls = []

    def rollback(root, generation):
        calls.append(generation)
        raise ValueError("stale generation")

    monkeypatch.setattr("mizan_owned.learning_cycle.rollback", rollback)
    response = client.post(
        "/api/owned/learning/rollback", headers=admin, json={"expected_generation": 5}
    )
    assert response.status_code == 409
    assert calls == [5]
    assert (
        client.post(
            "/api/owned/learning/rollback", headers=admin, json={"expected_generation": True}
        ).status_code
        == 422
    )
