"""Exercise the deployment shell's provider preservation and failure rollback."""

import json
import os
import subprocess
from pathlib import Path

SHA = "a" * 40
SCRIPT = Path(__file__).parents[1] / "scripts" / "deploy_production.sh"
FAKE_DOCKER = r"""#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
state_file = Path(os.environ['FAKE_DOCKER_STATE'])
state = json.loads(state_file.read_text())
args = sys.argv[1:]
state['commands'].append(args)
if args[0] == 'inspect':
    fmt, name = args[2:4]
    if 'working_dir' in fmt: print(state['root'])
    elif 'config_files' in fmt: print(state['root'] + '/compose.yml')
    elif 'project' in fmt: print('existing-project')
    elif 'Config.Env' in fmt:
        print(json.dumps(['RUNPOD_API_KEY=synthetic-runpod-key',
                          'RUNPOD_ENDPOINT_ID=preserved-endpoint',
                          'MIZAN_DATA_DIR=/data/existing-users']))
    else: print(state['images'][name])
elif args[0] == 'login':
    sys.stdin.read()
elif args[0] == 'compose' and 'up' in args:
    files = [args[i+1] for i, arg in enumerate(args) if arg == '-f']
    override = json.loads(Path(files[-1]).read_text())
    if state['fail_new'] and 'ghcr.io/' in override['services']['backend']['image']:
        state_file.write_text(json.dumps(state)); sys.exit(1)
    for service in ['backend', 'frontend']:
        state['images']['mizan-' + service] = override['services'][service]['image']
elif args[0] == 'exec' and '/api/status' in ' '.join(args):
    print('401', end='')
state_file.write_text(json.dumps(state))
"""


def deploy_fixture(tmp_path, fail_new):
    root = tmp_path / "existing-project"
    root.mkdir()
    (root / "compose.yml").write_text("services: {}\n")
    data = root / "database-marker"
    data.write_text("existing data")
    state = tmp_path / "docker-state.json"
    state.write_text(
        json.dumps(
            {
                "root": str(root),
                "images": {"mizan-backend": "old-backend", "mizan-frontend": "old-frontend"},
                "commands": [],
                "fail_new": fail_new,
            }
        )
    )
    binaries = tmp_path / "bin"
    binaries.mkdir()
    docker = binaries / "docker"
    docker.write_text(FAKE_DOCKER)
    docker.chmod(0o755)
    deployment_dir = tmp_path / "deployment-state"
    result = subprocess.run(
        ["bash", str(SCRIPT), SHA, "codewithjuber/mizan"],
        input="synthetic-registry-token\n",
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PATH": str(binaries) + os.pathsep + os.environ["PATH"],
            "FAKE_DOCKER_STATE": str(state),
            "MIZAN_DEPLOY_STATE_DIR": str(deployment_dir),
            "MIZAN_DEPLOY_HEALTH_ATTEMPTS": "1",
        },
        timeout=15,
    )
    assert data.read_text() == "existing data"
    assert "synthetic-runpod-key" not in result.stdout + result.stderr
    assert "synthetic-registry-token" not in result.stdout + result.stderr
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


def test_failed_start_restores_both_images(tmp_path):
    result, state, directory = deploy_fixture(tmp_path, True)
    assert result.returncode == 1
    assert state["images"] == {"mizan-backend": "old-backend", "mizan-frontend": "old-frontend"}
    assert not (directory / "deployed-sha").exists()
