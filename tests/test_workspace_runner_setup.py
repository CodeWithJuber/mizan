"""Host-installer safeguards, exercised without Docker, SSH or host mutations."""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location(
    "workspace_runner_setup",
    Path(__file__).resolve().parents[1] / "scripts/setup_workspace_runner.py",
)
setup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup)
SHA = "a" * 40
IMAGE = "sha256:" + "b" * 64
RUNNER_IMAGE = "sha256:" + "c" * 64


@pytest.mark.parametrize(
    "sha,repo",
    [
        ("main", setup.REPOSITORY),
        ("a" * 39, setup.REPOSITORY),
        ("A" * 40, setup.REPOSITORY),
        (SHA, "other/mizan"),
        (SHA + ";id", setup.REPOSITORY),
    ],
)
def test_target_is_a_full_sha_in_the_reviewed_repository(sha, repo):
    with pytest.raises(setup.SetupError):
        setup.validate_target(sha, repo)


def test_safe_prerequisite_plan_accepts_only_new_rootless_dependencies():
    setup.validate_package_plan(
        "Inst uidmap (1.0 Ubuntu)\nInst libsubid4 (1.0 Ubuntu)\nInst slirp4netns (1.0 Ubuntu)\nInst libslirp0 (1.0 Ubuntu)"
    )


@pytest.mark.parametrize(
    "plan",
    [
        "Inst docker-ce (29.0 Ubuntu)",
        "Inst uidmap [1.0] (1.1 Ubuntu)",
        "Remv containerd.io [1.0]",
        "Inst systemd (256 Ubuntu)",
        "Inst curl (1.0 Ubuntu)",
    ],
)
def test_package_upgrades_removals_and_unrelated_installs_are_rejected(plan):
    with pytest.raises(setup.SetupError):
        setup.validate_package_plan(plan)


@pytest.mark.parametrize(
    "contents",
    [
        "mizan-workspace:100000:65535",
        "mizan-workspace:0:65536",
        "mizan-workspace:100000:65536\nother:110000:65536",
    ],
)
def test_subordinate_ids_are_large_non_root_and_exclusive(contents):
    with pytest.raises(setup.SetupError):
        setup.validate_subids(contents, setup.ACCOUNT)
    setup.validate_subids("mizan-workspace:100000:65536\nother:165536:65536", setup.ACCOUNT)


def daemon_info():
    return {
        "ID": "dedicated",
        "SecurityOptions": ["name=rootless"],
        "CgroupVersion": "2",
        "CgroupDriver": "systemd",
        "DockerRootDir": str(setup.ACCOUNT_HOME / ".local/share/docker"),
    }


@pytest.mark.parametrize(
    "changed",
    [
        {"ID": "production"},
        {"SecurityOptions": ["name=seccomp"]},
        {"CgroupVersion": "1"},
        {"CgroupDriver": "none"},
        {"DockerRootDir": "/var/lib/docker"},
    ],
)
def test_rootful_shared_or_unlimited_worker_daemon_is_rejected(changed):
    with pytest.raises(setup.SetupError):
        setup.validate_daemon({**daemon_info(), **changed}, "production", setup.ACCOUNT_HOME)
    setup.validate_daemon(daemon_info(), "production", setup.ACCOUNT_HOME)


def test_override_exposes_only_the_dedicated_socket_and_content_pinned_images():
    config = setup.workspace_override(
        1002, 1002, "t" * 64, runtime_image=IMAGE, runner_image=RUNNER_IMAGE
    )
    assert set(config["services"]) == {"backend", "workspace-runner"}
    backend, runner = config["services"]["backend"], config["services"]["workspace-runner"]
    assert "volumes" not in backend
    assert runner["image"] == RUNNER_IMAGE
    assert runner["volumes"] == [
        {
            "type": "bind",
            "source": "/run/user/1002/docker.sock",
            "target": "/var/run/docker.sock",
            "bind": {"create_host_path": False},
        }
    ]
    assert "ports" not in runner and runner["networks"] == ["mizan-net"]
    assert runner["read_only"] and runner["cap_drop"] == ["ALL"]
    assert runner["security_opt"] == ["no-new-privileges:true"]
    assert runner["environment"]["MIZAN_WORKSPACE_RUNTIME_IMAGE"] == IMAGE
    with pytest.raises(setup.SetupError, match="content IDs"):
        setup.workspace_override(
            1002, 1002, "t" * 64, runtime_image="runtime:latest", runner_image=RUNNER_IMAGE
        )


def test_generated_compose_preserves_literal_dollars_in_credentials():
    original = {"services": {"backend": {"environment": {"KEY": "literal$NAME${VALUE}$$tail"}}}}
    encoded = json.loads(setup.compose_document(original))
    assert encoded["services"]["backend"]["environment"]["KEY"] == "literal$$NAME$${VALUE}$$$$tail"
    assert original["services"]["backend"]["environment"]["KEY"] == "literal$NAME${VALUE}$$tail"


def rendered_fixture():
    env = {"KEY": "literal$secret", "MIZAN_WORKSPACE_RUNNER_URL": "http://workspace-runner:8080"}
    snapshot = {
        "backend_image": IMAGE,
        "backend_env": env,
        "backend_mounts": [
            {
                "Type": "volume",
                "Name": "mizan_mizan-data",
                "Source": "/var/lib/docker/volumes/mizan_mizan-data/_data",
                "Destination": "/data",
                "RW": True,
            }
        ],
        "backend_networks": ["mizan_mizan-net"],
        "backend_ports": {},
    }
    config = {
        "services": {
            "backend": {
                "image": IMAGE,
                "container_name": "mizan-backend",
                "environment": env.copy(),
                "volumes": [{"type": "volume", "source": "mizan-data", "target": "/data"}],
                "networks": {"mizan-net": None},
            }
        },
        "volumes": {"mizan-data": {"name": "mizan_mizan-data"}},
        "networks": {"mizan-net": {"name": "mizan_mizan-net"}},
    }
    return config, snapshot, env


@pytest.mark.parametrize("drift", ["environment", "volume", "network", "port", "image"])
def test_rendered_compose_drift_is_rejected_before_recreation(drift):
    config, snapshot, env = rendered_fixture()
    setup.validate_rendered_backend(config, snapshot, env)
    if drift == "environment":
        config["services"]["backend"]["environment"]["FROM_ENV_FILE"] = "unexpected"
    elif drift == "volume":
        config["volumes"]["mizan-data"]["name"] = "new-empty-volume"
    elif drift == "network":
        config["networks"]["mizan-net"]["name"] = "unrelated-network"
    elif drift == "port":
        config["services"]["backend"]["ports"] = [{"target": 8000, "published": "8000"}]
    else:
        config["services"]["backend"]["image"] = "other:latest"
    with pytest.raises(setup.SetupError):
        setup.validate_rendered_backend(config, snapshot, env)


def backend_metadata(running=True, image=IMAGE):
    return {
        "Image": image,
        "State": {"Running": running},
        "Config": {
            "Labels": {
                "com.docker.compose.project": "mizan",
                "com.docker.compose.project.working_dir": str(setup.PROJECT_ROOT),
            }
        },
        "NetworkSettings": {"Networks": {"mizan_mizan-net": {}}},
    }


class FakeCommands:
    def __init__(
        self, backend=None, *, missing=False, alias=False, rendered=None, fail_restore=False
    ):
        self.backend = backend or backend_metadata()
        self.missing = missing
        self.alias = alias
        self.rendered = rendered
        self.fail_restore = fail_restore
        self.calls = []

    def run(self, argv, **kwargs):
        self.calls.append(argv)
        if argv == [*setup.DOCKER, "inspect", "mizan-backend"]:
            return subprocess.CompletedProcess(
                argv,
                1 if self.missing else 0,
                "" if self.missing else json.dumps([self.backend]),
                "",
            )
        if argv[: len(setup.DOCKER) + 2] == [*setup.DOCKER, "image", "inspect"]:
            return subprocess.CompletedProcess(argv, 0, json.dumps([{"Id": IMAGE}]), "")
        if "ps" in argv:
            return subprocess.CompletedProcess(argv, 0, "unexpected" if self.alias else "", "")
        if argv[-3:] == ["config", "--format", "json"]:
            return subprocess.CompletedProcess(argv, 0, json.dumps(self.rendered), "")
        if self.fail_restore and "up" in argv and argv[-1] == "backend":
            raise setup.SetupError("simulated backend restore failure")
        return subprocess.CompletedProcess(argv, 0, "", "")


def test_backend_liveness_is_required_for_setup_but_not_rollback():
    installer = setup.Installer(SHA, FakeCommands(backend_metadata(running=False)))
    with pytest.raises(setup.SetupError, match="not running"):
        installer.backend()
    assert installer.backend(require_running=False)["State"]["Running"] is False


def test_missing_backend_can_be_recovered_only_if_no_other_backend_owns_project():
    installer = setup.Installer(SHA, FakeCommands(missing=True))
    assert installer.backend(require_running=False, allow_missing=True) is None
    with pytest.raises(setup.SetupError):
        installer.backend()
    installer.commands.alias = True
    with pytest.raises(setup.SetupError, match="unexpected backend"):
        installer.backend(require_running=False, allow_missing=True)


def test_recovery_preflight_does_not_require_free_resources_or_rootless_tools(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(setup, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(setup.os, "geteuid", lambda: 0)
    installer = setup.Installer(SHA, FakeCommands(missing=True))
    info = {
        "ID": "production",
        "SecurityOptions": ["name=seccomp"],
        "CgroupVersion": "2",
        "CgroupDriver": "systemd",
    }
    monkeypatch.setattr(installer, "docker_json", lambda *_: info)

    def no_resource_probe(*_):
        raise AssertionError("Recovery must not require fresh provisioning capacity")

    monkeypatch.setattr(setup.shutil, "disk_usage", no_resource_probe)
    monkeypatch.setattr(setup.Path, "is_file", no_resource_probe)
    assert installer.preflight(recovering=True) is None
    assert installer.production_id == "production"


def test_newer_backend_is_never_rolled_back():
    fake = FakeCommands(backend_metadata(image=RUNNER_IMAGE))
    with pytest.raises(setup.SetupError, match="changed"):
        setup.Installer(SHA, fake).backend(require_running=False, allow_missing=True)
    assert not any("up" in command for command in fake.calls)


def test_preexisting_account_is_not_adopted(tmp_path, monkeypatch):
    monkeypatch.setattr(setup, "STATE_ROOT", tmp_path / "state")
    monkeypatch.setattr(setup.pwd, "getpwnam", lambda _: SimpleNamespace(pw_uid=1002))
    installer = setup.Installer(SHA, FakeCommands())
    installer.production_id = "production"
    with pytest.raises(setup.SetupError, match="pre-existing service account"):
        installer.load_state()
    assert not (tmp_path / "state").exists()
    assert not installer.commands.calls


@pytest.fixture
def rollback_case(tmp_path, monkeypatch):
    root = tmp_path / "project"
    root.mkdir()
    state = tmp_path / "state"
    state.mkdir()
    attempt = state / "attempt-test"
    attempt.mkdir()
    base = root / "base.yml"
    base.write_text("services: {}\n")
    override = root / "docker-compose.workspace-runtime.yml"
    override.write_text("services: {}\n")
    (attempt / "rollback.yml").write_text("services: {}\n")
    monkeypatch.setattr(setup, "PROJECT_ROOT", root)
    monkeypatch.setattr(setup, "STATE_ROOT", state)
    monkeypatch.setattr(setup, "OVERRIDE", override)
    # Transaction tests exercise decisions/argv only; root file ownership is not
    # changed and no host commands run, including on non-root GitHub runners.
    monkeypatch.setattr(setup, "read_json", lambda path: json.loads(path.read_text()))
    monkeypatch.setattr(
        setup, "protected_write", lambda path, content, **_: path.write_text(content)
    )
    config, snapshot, _ = rendered_fixture()
    snapshot.update(
        directory=str(attempt),
        files=[str(base)],
        hashes={str(base): setup.digest(base)},
        override_before=None,
    )
    (attempt / "snapshot.json").write_text(json.dumps(snapshot))
    fake = FakeCommands(rendered=config)
    installer = setup.Installer(SHA, fake)
    installer.state = {
        "active_attempt": str(attempt),
        "phase": "applying",
        "override_sha256": setup.digest(override),
    }
    monkeypatch.setattr(installer, "health", lambda: None)
    monkeypatch.setattr(installer, "proxy", lambda: None)
    return installer, fake, base, override


@pytest.mark.parametrize("missing", [False, True])
def test_failed_or_missing_backend_restores_before_new_runner_is_removed(rollback_case, missing):
    installer, fake, _, override = rollback_case
    fake.backend = backend_metadata(running=False)
    fake.missing = missing
    installer.rollback()
    restore = next(
        i for i, command in enumerate(fake.calls) if "up" in command and command[-1] == "backend"
    )
    remove = next(i for i, command in enumerate(fake.calls) if "rm" in command)
    assert restore < remove
    assert fake.calls[remove][-4:] == ["rm", "--stop", "--force", "workspace-runner"]
    assert not override.exists() and installer.state["phase"] == "rolled_back"
    assert not any(
        "down" in command or "prune" in command or "--volumes" in command for command in fake.calls
    )


def test_restore_failure_does_not_remove_runner_or_erase_recovery_state(rollback_case):
    installer, fake, _, override = rollback_case
    fake.fail_restore = True
    with pytest.raises(setup.SetupError, match="restore failure"):
        installer.rollback()
    assert override.exists() and installer.state["phase"] == "applying"
    assert not any("rm" in command for command in fake.calls)


@pytest.mark.parametrize("failure", [BrokenPipeError, OSError, ValueError])
def test_closed_ssh_output_cannot_interrupt_backend_restoration(
    rollback_case, monkeypatch, failure
):
    installer, fake, _, override = rollback_case

    def closed_stream(*_args, **_kwargs):
        raise failure("SSH output disconnected")

    monkeypatch.setattr(setup, "print", closed_stream, raising=False)
    installer.rollback()
    assert any("up" in command and command[-1] == "backend" for command in fake.calls)
    assert not override.exists() and installer.state["phase"] == "rolled_back"


def test_changed_original_compose_blocks_rollback_mutations(rollback_case):
    installer, fake, base, _ = rollback_case
    base.write_text("changed externally")
    with pytest.raises(setup.SetupError, match="configuration changed"):
        installer.rollback()
    assert not any("up" in command or "rm" in command for command in fake.calls)


def test_changed_runner_override_is_not_overwritten_by_rollback(rollback_case):
    installer, fake, _, override = rollback_case
    override.write_text("external configuration")
    with pytest.raises(setup.SetupError, match="override changed"):
        installer.rollback()
    assert override.read_text() == "external configuration"
    assert not any("up" in command or "rm" in command for command in fake.calls)


def valid_job():
    return {
        "HostConfig": {
            "NetworkMode": "none",
            "ReadonlyRootfs": True,
            "Privileged": False,
            "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges"],
            "Memory": 384 * 1024**2,
            "MemorySwap": 384 * 1024**2,
            "NanoCpus": 10**9,
            "PidsLimit": 64,
        },
        "Config": {"User": "65534:65534", "Env": ["PATH=/usr/bin"]},
        "Mounts": [{"Type": "tmpfs"}],
    }


@pytest.mark.parametrize("drift", ["network", "secret", "mount", "memory"])
def test_live_jobs_with_missing_isolation_are_rejected(drift):
    job = valid_job()
    setup.validate_job(job)
    altered = copy.deepcopy(job)
    if drift == "network":
        altered["HostConfig"]["NetworkMode"] = "bridge"
    elif drift == "secret":
        altered["Config"]["Env"].append("OPENROUTER_API_KEY=must-not-leak")
    elif drift == "mount":
        altered["Mounts"].append({"Type": "bind", "Source": "/var/run/docker.sock"})
    else:
        altered["HostConfig"]["Memory"] = 0
    with pytest.raises(setup.SetupError):
        setup.validate_job(altered)


def test_command_errors_never_expose_stdin_output_or_inherited_secrets(monkeypatch, capsys):
    monkeypatch.setenv("PRODUCTION_TOKEN", "must-not-be-inherited")
    code = "import os,sys; assert 'PRODUCTION_TOKEN' not in os.environ; print(sys.stdin.read()); sys.stderr.write('private output'); sys.exit(7)"
    with pytest.raises(setup.SetupError) as error:
        setup.Commands().run(
            [sys.executable, "-c", code], stage="Safe stage", stdin="private registry token"
        )
    assert str(error.value) == "Safe stage: command exited 7"
    assert not capsys.readouterr().out and "private" not in str(error.value)


def test_command_timeout_terminates_compose_style_child_processes(tmp_path):
    pidfile = tmp_path / "child.pid"
    marker = tmp_path / "child-survived"
    child = (
        f"import pathlib,time; time.sleep(1); pathlib.Path({str(marker)!r}).write_text('unsafe')"
    )
    parent = f"import pathlib,subprocess,sys,time; p=subprocess.Popen([sys.executable,'-c',{child!r}]); pathlib.Path({str(pidfile)!r}).write_text(str(p.pid)); time.sleep(30)"
    with pytest.raises(setup.SetupError, match="deadline"):
        setup.Commands().run([sys.executable, "-c", parent], stage="Deadline test", timeout=0.3)
    assert pidfile.exists()
    pid = int(pidfile.read_text())
    proc = Path(f"/proc/{pid}/stat")
    for _ in range(20):
        if not proc.exists() or proc.read_text().split()[2] == "Z":
            break
        time.sleep(0.05)
    assert not proc.exists() or proc.read_text().split()[2] == "Z"
    assert not marker.exists()
