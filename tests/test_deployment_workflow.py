"""Exercise the deployment shell's provider preservation and failure rollback."""

import json
import os
import subprocess
from pathlib import Path

import pytest

SHA = "a" * 40
SCRIPT = Path(__file__).parents[1] / "scripts" / "deploy_production.sh"
FAKE_DOCKER = r"""#!/usr/bin/env python3
import json, os, sys, time
from pathlib import Path
state_file = Path(os.environ['FAKE_DOCKER_STATE'])
state = json.loads(state_file.read_text())
args = sys.argv[1:]
state['commands'].append(args)
if args[0] == 'inspect':
    fmt, name = args[2:4]
    if name == 'mizan-nginx': print('true')
    elif 'working_dir' in fmt: print(state['root'])
    elif 'config_files' in fmt: print(state['root'] + '/compose.yml')
    elif 'project' in fmt: print('existing-project')
    elif 'Config.Env' in fmt:
        print(json.dumps([key + '=' + value for key, value in state['runtime_env'].items()]))
    else: print(state['images'][name])
elif args[0] == 'login':
    sys.stdin.read()
elif args[0] == 'compose' and 'up' in args:
    files = [args[i+1] for i, arg in enumerate(args) if arg == '-f']
    override = json.loads(Path(files[-1]).read_text())
    state['updates'].append(override)
    if state['fail_new'] and 'ghcr.io/' in override['services']['backend']['image']:
        state_file.write_text(json.dumps(state)); sys.exit(1)
    for service in ['backend', 'frontend']:
        state['images']['mizan-' + service] = override['services'][service]['image']
elif args[0] == 'exec' and '/api/status' in ' '.join(args):
    print('401', end='')
    if state.get('failed_status_client'):
        state_file.write_text(json.dumps(state)); sys.exit(7)
elif args[0] == 'exec' and '/api/health' in ' '.join(args) and state.get('hang_health'):
    state_file.write_text(json.dumps(state)); time.sleep(20)
state_file.write_text(json.dumps(state))
"""


def deploy_fixture(
    tmp_path,
    fail_new,
    fail_public=False,
    *,
    runtime_env=None,
    grace_override=None,
    hang_health=False,
    failed_status_client=False,
):
    root = tmp_path / "existing-project"
    root.mkdir()
    (root / "compose.yml").write_text("services: {}\n")
    data = root / "database-marker"
    data.write_text("existing data")
    state = tmp_path / "docker-state.json"
    runtime_env = {
        "RUNPOD_API_KEY": "synthetic-runpod-key",
        "RUNPOD_ENDPOINT_ID": "preserved-endpoint",
        "MIZAN_DATA_DIR": "/data/existing-users",
        **(runtime_env or {}),
    }
    state.write_text(
        json.dumps(
            {
                "root": str(root),
                "images": {"mizan-backend": "old-backend", "mizan-frontend": "old-frontend"},
                "commands": [],
                "updates": [],
                "runtime_env": runtime_env,
                "fail_new": fail_new,
                "hang_health": hang_health,
                "failed_status_client": failed_status_client,
            }
        )
    )
    binaries = tmp_path / "bin"
    binaries.mkdir()
    docker = binaries / "docker"
    docker.write_text(FAKE_DOCKER)
    docker.chmod(0o755)
    curl = binaries / "curl"
    curl.write_text(
        "#!/usr/bin/env python3\nimport os,sys\n"
        'if "/api/status" in " ".join(sys.argv):\n'
        '    print("200" if os.getenv("FAIL_PUBLIC") == "1" else "401", end="")\n'
    )
    curl.chmod(0o755)
    deployment_dir = tmp_path / "deployment-state"
    deployment_dir.mkdir()
    (deployment_dir / "current.yml").write_text('{"preserve":"previous current override"}')
    (deployment_dir / "rollback.yml").write_text('{"preserve":"previous rollback override"}')
    process_env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"MIZAN_GRACEFUL_SHUTDOWN_SECONDS", "UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN"}
    }
    if grace_override is not None:
        process_env["MIZAN_GRACEFUL_SHUTDOWN_SECONDS"] = grace_override
    result = subprocess.run(
        ["bash", str(SCRIPT), SHA, "codewithjuber/mizan"],
        input="synthetic-registry-token\n",
        capture_output=True,
        text=True,
        env={
            **process_env,
            "PATH": str(binaries) + os.pathsep + os.environ["PATH"],
            "FAKE_DOCKER_STATE": str(state),
            "MIZAN_DEPLOY_STATE_DIR": str(deployment_dir),
            "MIZAN_DEPLOY_HEALTH_ATTEMPTS": "1",
            "FAIL_PUBLIC": "1" if fail_public else "0",
        },
        timeout=30,
    )
    assert data.read_text() == "existing data"
    assert "synthetic-runpod-key" not in result.stdout + result.stderr
    assert "synthetic-registry-token" not in result.stdout + result.stderr
    for key, value in runtime_env.items():
        if value and key.endswith(("_KEY", "_TOKEN")):
            assert value not in result.stdout + result.stderr
    assert not list(deployment_dir.glob("pending.*"))
    return result, json.loads(state.read_text()), deployment_dir


def test_deployment_preserves_running_provider_and_data(tmp_path):
    result, state, directory = deploy_fixture(tmp_path, False)
    assert result.returncode == 0, result.stderr
    assert state["images"]["mizan-backend"] == f"ghcr.io/codewithjuber/mizan/backend:{SHA}"
    override = json.loads((directory / "current.yml").read_text())
    env = override["services"]["backend"]["environment"]
    assert env["RUNPOD_ENDPOINT_ID"] == "preserved-endpoint"
    assert env["MIZAN_DATA_DIR"] == "/data/existing-users"
    assert (directory / "deployed-sha").read_text().strip() == SHA
    updates = [args for args in state["commands"] if args[0] == "compose" and "up" in args]
    assert all("--no-deps" in args and args[-2:] == ["backend", "frontend"] for args in updates)
    assert all(args[args.index("--timeout") + 1] == "105" for args in updates)
    assert override["services"]["backend"]["stop_grace_period"] == "105s"
    assert env["MIZAN_GRACEFUL_SHUTDOWN_SECONDS"] == "90"
    assert env["UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN"] == "90"


def test_failed_start_restores_both_images(tmp_path):
    result, state, directory = deploy_fixture(tmp_path, True)
    assert result.returncode == 1
    assert state["images"] == {"mizan-backend": "old-backend", "mizan-frontend": "old-frontend"}
    assert not (directory / "deployed-sha").exists()
    updates = [args for args in state["commands"] if args[0] == "compose" and "up" in args]
    assert len(updates) == 2
    assert all(args[args.index("--timeout") + 1] == "105" for args in updates)


def test_public_auth_failure_restores_images_and_refreshes_proxy(tmp_path):
    result, state, directory = deploy_fixture(tmp_path, False, fail_public=True)
    assert result.returncode == 1
    assert state["images"] == {"mizan-backend": "old-backend", "mizan-frontend": "old-frontend"}
    assert not (directory / "deployed-sha").exists()
    reloads = [
        args
        for args in state["commands"]
        if args[:3] == ["exec", "mizan-nginx", "nginx"] and "reload" in args
    ]
    assert len(reloads) == 2


@pytest.mark.parametrize("old,new,timeout", [(30, 120, 135), (180, 10, 195), (10, 180, 195)])
def test_forward_and_rollback_use_both_bounded_deadlines(tmp_path, old, new, timeout):
    result, state, directory = deploy_fixture(
        tmp_path,
        False,
        fail_public=True,
        runtime_env={"MIZAN_GRACEFUL_SHUTDOWN_SECONDS": str(old)},
        grace_override=str(new),
    )
    assert result.returncode == 1
    assert state["images"] == {"mizan-backend": "old-backend", "mizan-frontend": "old-frontend"}
    assert len(state["updates"]) == 2
    for override, grace in zip(state["updates"], (new, old), strict=True):
        backend = override["services"]["backend"]
        assert backend["stop_grace_period"] == f"{grace + 15}s"
        assert backend["environment"]["MIZAN_GRACEFUL_SHUTDOWN_SECONDS"] == str(grace)
        assert backend["environment"]["UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN"] == str(grace)
        assert backend["environment"]["MIZAN_DATA_DIR"] == "/data/existing-users"
    updates = [args for args in state["commands"] if args[0] == "compose" and "up" in args]
    assert all(args[args.index("--timeout") + 1] == str(timeout) for args in updates)
    assert not (directory / "deployed-sha").exists()


@pytest.mark.parametrize(
    "value", ["", "9", "181", "090", "90.0", "-10", "10\n", "private-mistaken-value"]
)
def test_invalid_grace_refuses_before_container_stop_or_override_write(tmp_path, value):
    result, state, directory = deploy_fixture(tmp_path, False, grace_override=value)
    assert result.returncode != 0
    assert not state["updates"]
    assert not any(args[0] == "login" for args in state["commands"])
    assert (directory / "current.yml").read_text() == '{"preserve":"previous current override"}'
    assert (directory / "rollback.yml").read_text() == '{"preserve":"previous rollback override"}'
    assert "private-mistaken-value" not in result.stdout + result.stderr


def test_invalid_running_grace_refuses_before_stop(tmp_path):
    result, state, _ = deploy_fixture(
        tmp_path, False, runtime_env={"MIZAN_GRACEFUL_SHUTDOWN_SECONDS": "999"}
    )
    assert result.returncode != 0 and not state["updates"]


def test_running_uvicorn_grace_and_literal_credentials_are_preserved(tmp_path):
    key = "synthetic$private${credential}-value"
    result, state, directory = deploy_fixture(
        tmp_path,
        False,
        runtime_env={
            "UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN": "45",
            "RUNPOD_API_KEY": key,
        },
    )
    assert result.returncode == 0, result.stderr
    backend = json.loads((directory / "current.yml").read_text())["services"]["backend"]
    assert backend["environment"]["RUNPOD_API_KEY"] == key.replace("$", "$$")
    assert backend["environment"]["MIZAN_GRACEFUL_SHUTDOWN_SECONDS"] == "45"
    assert backend["stop_grace_period"] == "60s"
    assert key not in result.stdout + result.stderr


def test_existing_chat_runtime_tuning_is_preserved_in_forward_and_rollback(tmp_path):
    controls = {
        "MIZAN_LLM_FIRST_PROGRESS_SECONDS": "80",
        "MIZAN_LLM_PROGRESS_SECONDS": "55",
        "MIZAN_LLM_MAX_CALL_SECONDS": "240",
        "MIZAN_CHAT_RUN_SECONDS": "800",
        "MIZAN_CHAT_TOOL_SCHEMA_LIMIT": "5",
        "MIZAN_CHAT_TOOL_SCHEMA_BYTES": "8192",
        "MIZAN_CHAT_TEMPERATURE": "0.2",
    }
    result, state, _ = deploy_fixture(tmp_path, False, fail_public=True, runtime_env=controls)
    assert result.returncode == 1
    assert len(state["updates"]) == 2
    for override in state["updates"]:
        env = override["services"]["backend"]["environment"]
        assert {key: env[key] for key in controls} == controls


def test_absent_chat_tuning_does_not_override_installed_compose_settings(tmp_path):
    result, state, _ = deploy_fixture(tmp_path, False)
    assert result.returncode == 0
    env = state["updates"][0]["services"]["backend"]["environment"]
    assert "MIZAN_CHAT_TEMPERATURE" not in env
    assert "MIZAN_LLM_FIRST_PROGRESS_SECONDS" not in env


def test_workflow_reserves_time_for_lock_drain_health_and_rollback():
    workflow = SCRIPT.parents[1] / ".github/workflows/deploy.yml"
    assert "timeout-minutes: 25" in workflow.read_text()


def test_unresponsive_docker_health_exec_is_bounded_and_rolls_back(tmp_path):
    result, state, directory = deploy_fixture(tmp_path, False, hang_health=True)
    assert result.returncode == 1
    assert state["images"] == {"mizan-backend": "old-backend", "mizan-frontend": "old-frontend"}
    assert len(state["updates"]) == 2
    assert not (directory / "deployed-sha").exists()


def test_partial_auth_status_from_failed_client_does_not_pass_health(tmp_path):
    result, state, _ = deploy_fixture(tmp_path, False, failed_status_client=True)
    assert result.returncode == 1
    assert state["images"] == {"mizan-backend": "old-backend", "mizan-frontend": "old-frontend"}


def test_internal_health_clients_have_their_own_deadlines(tmp_path):
    result, state, _ = deploy_fixture(tmp_path, False)
    assert result.returncode == 0
    for args in state["commands"]:
        if args[:2] == ["exec", "mizan-backend"] and "curl" in args:
            assert args[args.index("--connect-timeout") + 1] == "2"
            assert args[args.index("--max-time") + 1] == "5"
        elif args[:2] == ["exec", "mizan-frontend"]:
            assert args[args.index("-T") + 1] == "5"
