"""Manual training must declare data origin and wait for process success."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import training_manager as module


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "ruh_model").mkdir()
    monkeypatch.setattr(module, "_HISTORY_FILE", tmp_path / "history.json")
    return module.TrainingManager()


@pytest.mark.asyncio
async def test_prepared_data_does_not_generate_seeds_or_claim_original_provenance(
    manager, tmp_path, monkeypatch
):
    dataset = tmp_path / "prepared.jsonl"
    dataset.write_text(json.dumps({"text": "Prepared fixture for command validation"}) + "\n")
    launch = AsyncMock(return_value=SimpleNamespace(returncode=None))
    monkeypatch.setattr(module.asyncio, "create_subprocess_exec", launch)
    monkeypatch.setattr(manager, "_monitor_output", AsyncMock())
    status = await manager.start_training(data_dir=str(dataset))
    await manager._monitor_task
    assert "--generate-data" not in launch.call_args.args
    assert status["data_source"] == "supplied_unverified"
    assert status["original_data_verified"] is False
    assert status["automatic_weight_training"] is False


@pytest.mark.asyncio
async def test_missing_empty_and_known_seed_data_need_explicit_choice(
    manager, tmp_path, monkeypatch
):
    launch = AsyncMock()
    monkeypatch.setattr(module.asyncio, "create_subprocess_exec", launch)
    empty = tmp_path / "empty.jsonl"
    empty.touch()
    for dataset in [tmp_path / "missing", empty]:
        with pytest.raises(ValueError, match="No prepared JSONL"):
            await manager.start_training(data_dir=str(dataset))
    seed = tmp_path / "seed_roots.jsonl"
    seed.write_text('{"text":"generated fixture"}\n')
    with pytest.raises(ValueError, match="generated seed files"):
        await manager.start_training(data_dir=str(seed))
    launch.assert_not_called()
    assert manager.get_status()["running"] is False


@pytest.mark.asyncio
async def test_seed_generation_requires_explicit_flag_and_is_labeled(
    manager, tmp_path, monkeypatch
):
    launch = AsyncMock(return_value=SimpleNamespace(returncode=None))
    monkeypatch.setattr(module.asyncio, "create_subprocess_exec", launch)
    monkeypatch.setattr(manager, "_monitor_output", AsyncMock())
    with pytest.raises(ValueError, match="boolean"):
        await manager.start_training(generate_seed_data="true")
    status = await manager.start_training(
        data_dir=str(tmp_path / "generated"), generate_seed_data=True
    )
    await manager._monitor_task
    assert "--generate-data" in launch.call_args.args
    assert status["data_source"] == "generated_seed_examples"
    assert status["original_data_verified"] is False
    assert not (tmp_path / "generated").exists()  # No training was actually launched.


@pytest.mark.asyncio
async def test_spawn_failure_does_not_leave_training_running(manager, monkeypatch):
    monkeypatch.setattr(
        module.asyncio, "create_subprocess_exec", AsyncMock(side_effect=OSError("spawn failed"))
    )
    with pytest.raises(OSError, match="spawn failed"):
        await manager.start_training(generate_seed_data=True)
    assert manager.get_status()["running"] is False
    assert manager.get_history()[-1]["status"] == "failed"
    assert manager.get_history()[-1]["data_source"] == "generated_seed_examples"


@pytest.mark.asyncio
async def test_complete_event_waits_for_exit_and_does_not_write_success(manager):
    manager._state.running = True
    await manager._handle_progress({"type": "complete", "final_loss": 0.0})
    assert manager.get_status()["running"] is True
    assert manager.get_status()["loss"] == 0.0
    assert "waiting for process exit" in manager.get_status()["message"]
    assert manager.get_history() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("exit_code, status", [(0, "completed"), (1, "failed")])
async def test_exit_code_controls_final_status_even_after_complete_event(
    manager, exit_code, status
):
    stdout = asyncio.StreamReader()
    stdout.feed_data(b'{"type":"complete","final_loss":0.25}\n')
    stdout.feed_eof()
    stderr = asyncio.StreamReader()
    stderr.feed_eof()
    manager._process = SimpleNamespace(
        stdout=stdout, stderr=stderr, wait=AsyncMock(return_value=exit_code), returncode=exit_code
    )
    manager._state.running = True
    manager._state.data_source = "supplied_unverified"
    await manager._monitor_output()
    assert manager.get_status()["running"] is False
    assert [run["status"] for run in manager.get_history()] == [status]
    assert manager.get_history()[0]["original_data_verified"] is False
    assert manager.get_history()[0]["data_source"] == "supplied_unverified"
