"""Exercise the controller's actual failure and interruption cleanup paths."""

import json

import pytest
from scripts import launch_runpod_training as controller


@pytest.mark.parametrize("failure", [RuntimeError("download failed"), KeyboardInterrupt()])
def test_controller_deletes_only_owned_pod_after_failure(monkeypatch, tmp_path, failure):
    monkeypatch.setenv("KAGGLE_API_TOKEN", "test-private-token")
    monkeypatch.setattr(
        controller,
        "graphql",
        lambda *args: {"podFindAndDeployOnDemand": {"id": "own-pod", "costPerHr": 1.6}},
    )

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"phase": "complete", "artifacts": {}}

    monkeypatch.setattr(controller.requests.Session, "get", lambda *args, **kwargs: Response())
    monkeypatch.setattr(
        controller, "download_artifacts", lambda *args: (_ for _ in ()).throw(failure)
    )
    deleted = []
    monkeypatch.setattr(
        controller, "delete_and_verify", lambda session, pod_id: deleted.append(pod_id)
    )
    with pytest.raises(type(failure)):
        controller.launch(None, "a" * 40, tmp_path / "run")
    assert deleted == ["own-pod"]
    recovery = json.loads((tmp_path / "run/pod-recovery.json").read_text())
    assert recovery["pod_deleted"] is True
    assert "test-private-token" not in json.dumps(recovery)


def test_controller_rejects_actual_price_and_deletes_before_poll(monkeypatch, tmp_path):
    monkeypatch.setenv("KAGGLE_API_TOKEN", "test-private-token")
    monkeypatch.setattr(
        controller,
        "graphql",
        lambda *args: {"podFindAndDeployOnDemand": {"id": "own-expensive-pod", "costPerHr": 3.49}},
    )
    deleted = []
    monkeypatch.setattr(
        controller, "delete_and_verify", lambda session, pod_id: deleted.append(pod_id)
    )
    with pytest.raises(ValueError, match="spending guard"):
        controller.launch(None, "a" * 40, tmp_path / "run")
    assert deleted == ["own-expensive-pod"]


def test_recovery_snapshot_survives_normal_snapshot_rotation(monkeypatch, tmp_path):
    from scripts import runpod_training_job as job

    monkeypatch.setattr(job, "ROOT", tmp_path)
    monkeypatch.setattr(job, "ARTIFACTS", {})
    monkeypatch.setattr(job, "RECOVERY_MANIFEST", {})
    snapshot = tmp_path / "run/continuation-000025"
    snapshot.joinpath("candidate").mkdir(parents=True)
    snapshot.joinpath("candidate/model.pt").write_bytes(b"private-test-weights")
    snapshot.joinpath("training_state.pt").write_bytes(b"test-optimizer-state")
    tmp_path.joinpath("run/latest-continuation.json").write_text(
        json.dumps({"path": snapshot.name})
    )
    manifest = job.recovery_artifacts()
    assert set(manifest) == {"recovery/candidate/model.pt", "recovery/training_state.pt"}
    import shutil

    shutil.rmtree(snapshot)
    assert job.ARTIFACTS["recovery/candidate/model.pt"].read_bytes() == b"private-test-weights"
