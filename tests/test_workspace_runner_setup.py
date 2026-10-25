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
    assert runner["pids_limit"] == runner["deploy"]["resources"]["limits"]["pids"] == 128
    with pytest.raises(setup.SetupError, match="content IDs"):
        setup.workspace_override(
            1002, 1002, "t" * 64, runtime_image="runtime:latest", runner_image=RUNNER_IMAGE
        )


def test_research_override_is_optional_and_changes_only_the_backend_environment():
    original = setup.workspace_override(
        1002, 1002, "t" * 64, runtime_image=IMAGE, runner_image=RUNNER_IMAGE
    )
    configured = setup.workspace_override(
        1002,
        1002,
        "t" * 64,
        runtime_image=IMAGE,
        runner_image=RUNNER_IMAGE,
        research_dir=setup.RESEARCH_DIR,
    )
    expected = copy.deepcopy(original)
    expected["services"]["backend"]["environment"]["MIZAN_RESEARCH_DIR"] = setup.RESEARCH_DIR
    assert configured == expected
    with pytest.raises(setup.SetupError, match="Research directory"):
        setup.Installer(SHA, research_dir="/app/data/research")


def test_live_control_service_must_apply_the_matching_pid_limit(monkeypatch):
    installer = setup.Installer(SHA, FakeCommands())
    installer.state = {
        "uid": 1002,
        "gid": 1002,
        "images": {"runner": {"id": RUNNER_IMAGE}, "runtime": {"id": IMAGE}},
    }
    container = {
        "Image": RUNNER_IMAGE,
        "State": {"Running": True},
        "Config": {"User": "1002:1002", "Env": ["MIZAN_WORKSPACE_RUNTIME_IMAGE=" + IMAGE]},
        "HostConfig": {
            "ReadonlyRootfs": True,
            "Privileged": False,
            "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges"],
            "Memory": 192 * 1024**2,
            "NanoCpus": 500000000,
            "PidsLimit": 128,
        },
        "Mounts": [
            {
                "Type": "bind",
                "Source": "/run/user/1002/docker.sock",
                "Destination": "/var/run/docker.sock",
            }
        ],
        "NetworkSettings": {"Networks": {"mizan_mizan-net": {}}},
    }
    monkeypatch.setattr(installer, "runner_ids", lambda _: ["runner"])
    monkeypatch.setattr(installer, "docker_json", lambda *_: [container])
    assert installer.verify_runner([]) == "runner"
    container["HostConfig"]["PidsLimit"] = 0
    with pytest.raises(setup.SetupError, match="resource limits"):
        installer.verify_runner([])


def research_fixture():
    backend = {
        "Config": {"Env": ["MIZAN_DATA_DIR=/data/mizan"]},
        "Mounts": [
            {"Destination": "/data", "Type": "volume", "RW": True, "Name": "mizan_mizan-data"}
        ],
        "HostConfig": {},
    }
    probe = {
        "uid": 999,
        "parent_directory": True,
        "parent_resolved": "/data/mizan",
        "parent_writable": True,
        "resolved_target": setup.RESEARCH_DIR,
        "target_exists": False,
        "target_directory": False,
    }
    return backend, probe


@pytest.mark.parametrize(
    "drift",
    [
        "uid",
        "missing_parent",
        "parent_link",
        "not_writable",
        "missing_mount",
        "readonly_mount",
        "tmpfs_mount",
        "nested_mount",
        "target_mount",
        "hidden_tmpfs",
        "target_escape",
        "target_file",
        "different_data_root",
    ],
)
def test_research_path_requires_existing_backend_writable_persistent_mount(drift):
    backend, probe = research_fixture()
    setup.validate_research_location(backend, probe)
    if drift == "uid":
        probe["uid"] = 0
    elif drift == "missing_parent":
        probe["parent_directory"] = False
    elif drift == "parent_link":
        probe["parent_resolved"] = "/tmp/mizan"
    elif drift == "not_writable":
        probe["parent_writable"] = False
    elif drift == "missing_mount":
        backend["Mounts"] = []
    elif drift == "readonly_mount":
        backend["Mounts"][0]["RW"] = False
    elif drift == "tmpfs_mount":
        backend["Mounts"][0]["Type"] = "tmpfs"
    elif drift == "nested_mount":
        backend["Mounts"].append({"Destination": "/data/mizan", "Type": "volume", "RW": True})
    elif drift == "target_mount":
        backend["Mounts"].append({"Destination": setup.RESEARCH_DIR, "Type": "tmpfs", "RW": True})
    elif drift == "hidden_tmpfs":
        backend["HostConfig"]["Tmpfs"] = {"/data/mizan/research": "rw"}
    elif drift == "target_escape":
        probe["resolved_target"] = "/app/data/research"
    elif drift == "target_file":
        probe["target_exists"] = True
    else:
        backend["Config"]["Env"] = ["MIZAN_DATA_DIR=/other"]
    with pytest.raises(setup.SetupError):
        setup.validate_research_location(backend, probe)


def test_research_reverification_accepts_import_release_inside_the_same_volume():
    backend, probe = research_fixture()
    backend["Config"]["Env"].append("MIZAN_RESEARCH_DIR=" + setup.RESEARCH_DIR)
    probe.update(
        target_exists=True,
        target_directory=True,
        resolved_target="/data/mizan/.mizan-research-reviewed-release",
    )
    setup.validate_research_location(backend, probe, configured=True)
    backend["Config"]["Env"].pop()
    with pytest.raises(setup.SetupError, match="not applied"):
        setup.validate_research_location(backend, probe, configured=True)


def test_research_probe_uses_existing_backend_identity_and_performs_no_directory_action():
    backend, probe = research_fixture()

    class ProbeCommands(FakeCommands):
        def run(self, argv, **kwargs):
            self.calls.append(argv)
            return subprocess.CompletedProcess(argv, 0, json.dumps(probe), "")

    commands = ProbeCommands()
    installer = setup.Installer(SHA, commands, research_dir=setup.RESEARCH_DIR)
    installer.research_location(backend)
    assert commands.calls == [
        [*setup.DOCKER, "exec", "mizan-backend", "python3", "-c", setup.RESEARCH_PROBE]
    ]
    assert "--user" not in commands.calls[0]
    assert not any(
        action in setup.RESEARCH_PROBE
        for action in ("mkdir", "chown", "write_text", "unlink", "import_bundle")
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
        "Id": "b" * 64,
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
        self.runner = None
        self.restored_mounts = []
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
        if self.runner and argv == [*setup.DOCKER, "inspect", self.runner["Id"]]:
            return subprocess.CompletedProcess(argv, 0, json.dumps([self.runner]), "")
        if argv[: len(setup.DOCKER) + 2] == [*setup.DOCKER, "image", "inspect"]:
            return subprocess.CompletedProcess(argv, 0, json.dumps([{"Id": IMAGE}]), "")
        if "ps" in argv:
            if "label=com.docker.compose.service=workspace-runner" in argv:
                return subprocess.CompletedProcess(
                    argv, 0, self.runner["Id"] if self.runner else "", ""
                )
            return subprocess.CompletedProcess(argv, 0, "unexpected" if self.alias else "", "")
        if argv[-3:] == ["config", "--format", "json"]:
            return subprocess.CompletedProcess(argv, 0, json.dumps(self.rendered), "")
        if self.fail_restore and "up" in argv and argv[-1] == "backend":
            raise setup.SetupError("simulated backend restore failure")
        if "up" in argv and argv[-1] == "backend":
            self.missing = False
            self.backend["State"]["Running"] = True
            self.backend["Config"]["Env"] = [
                f"{key}={value}"
                for key, value in self.rendered["services"]["backend"]["environment"].items()
            ]
            self.backend["Mounts"] = copy.deepcopy(self.restored_mounts)
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


def test_research_option_is_bound_to_retries_but_inherited_for_explicit_rollback(
    tmp_path, monkeypatch
):
    state = {
        "manager": setup.MANAGER,
        "sha": SHA,
        "production_id": "production",
        "research_dir": setup.RESEARCH_DIR,
        "phase": "ready",
    }
    (tmp_path / "state.json").write_text(json.dumps(state))
    monkeypatch.setattr(setup, "STATE_ROOT", tmp_path)
    monkeypatch.setattr(setup, "private_directory", lambda _: None)
    monkeypatch.setattr(setup, "read_json", lambda path: json.loads(path.read_text()))
    retry = setup.Installer(SHA, FakeCommands())
    retry.production_id = "production"
    with pytest.raises(setup.SetupError, match="Research option differs"):
        retry.load_state()
    explicit = setup.Installer(SHA, FakeCommands(), research_dir=setup.RESEARCH_DIR)
    explicit.production_id = "production"
    explicit.load_state()
    assert explicit.state == state
    retry.load_state(rollback=True)
    assert retry.research_dir == setup.RESEARCH_DIR
    assert not retry.commands.calls and not explicit.commands.calls


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
        backend_container_id="b" * 64,
    )
    (attempt / "snapshot.json").write_text(json.dumps(snapshot))
    fake = FakeCommands(rendered=config)
    fake.restored_mounts = snapshot["backend_mounts"]
    installer = setup.Installer(SHA, fake)
    installer.state = {
        "active_attempt": str(attempt),
        "phase": "applying",
        "override_sha256": setup.digest(override),
        "uid": 1002,
        "gid": 1002,
        "images": {"runner": {"id": RUNNER_IMAGE}},
    }
    monkeypatch.setattr(installer, "health", lambda: None)
    monkeypatch.setattr(installer, "proxy", lambda: None)
    monkeypatch.setattr(installer, "public_health", lambda: None)
    return installer, fake, base, override


@pytest.mark.parametrize("missing", [False, True])
def test_failed_or_missing_backend_restores_before_new_runner_is_removed(rollback_case, missing):
    installer, fake, _, override = rollback_case
    fake.backend = backend_metadata(running=False)
    fake.missing = missing
    fake.runner = {
        "Id": "d" * 64,
        "Image": RUNNER_IMAGE,
        "Config": {
            "User": "1002:1002",
            "Labels": {
                "com.docker.compose.project": "mizan",
                "com.docker.compose.service": "workspace-runner",
                "com.docker.compose.project.working_dir": str(setup.PROJECT_ROOT),
            },
        },
        "Mounts": [
            {
                "Type": "bind",
                "Source": "/run/user/1002/docker.sock",
                "Destination": "/var/run/docker.sock",
            }
        ],
    }
    installer.rollback()
    restore = next(
        i for i, command in enumerate(fake.calls) if "up" in command and command[-1] == "backend"
    )
    remove = next(i for i, command in enumerate(fake.calls) if "rm" in command)
    assert restore < remove
    assert fake.calls[remove] == [*setup.DOCKER, "rm", "--force", "d" * 64]
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


def test_invalid_runner_override_and_absent_runner_cannot_block_rollback(
    rollback_case, monkeypatch
):
    installer, fake, _, override = rollback_case
    original_run = fake.run

    def reject_invalid_override(argv, **kwargs):
        if str(override) in argv:
            raise setup.SetupError("invalid runner override must not be parsed during rollback")
        return original_run(argv, **kwargs)

    monkeypatch.setattr(fake, "run", reject_invalid_override)
    installer.rollback()
    assert installer.state["phase"] == "rolled_back" and not override.exists()
    assert not any("rm" in command for command in fake.calls)


@pytest.mark.parametrize("runner_present", [False, True])
def test_pre_switch_failure_preserves_original_backend_without_compose_recreation(
    rollback_case, monkeypatch, runner_present
):
    installer, fake, _, override = rollback_case
    installer.state["backend_switch_started"] = False
    fake.backend["Config"]["Env"] = [
        f"{key}={value}"
        for key, value in fake.rendered["services"]["backend"]["environment"].items()
    ]
    fake.backend["Mounts"] = fake.restored_mounts
    if runner_present:
        fake.runner = {
            "Id": "d" * 64,
            "Image": RUNNER_IMAGE,
            "Config": {
                "User": "1002:1002",
                "Labels": {
                    "com.docker.compose.project": "mizan",
                    "com.docker.compose.service": "workspace-runner",
                    "com.docker.compose.project.working_dir": str(setup.PROJECT_ROOT),
                },
            },
            "Mounts": [
                {
                    "Type": "bind",
                    "Source": "/run/user/1002/docker.sock",
                    "Destination": "/var/run/docker.sock",
                }
            ],
        }
    original_id = fake.backend["Id"]
    original_run = fake.run

    def forbid_compose(argv, **kwargs):
        if "compose" in argv:
            raise setup.SetupError("Pre-switch recovery must not recreate the healthy backend")
        return original_run(argv, **kwargs)

    monkeypatch.setattr(fake, "run", forbid_compose)
    installer.rollback()
    assert fake.backend["Id"] == original_id
    assert installer.state["phase"] == "rolled_back" and not override.exists()
    assert not any("up" in command for command in fake.calls)
    assert any("rm" in command for command in fake.calls) is runner_present


@pytest.mark.parametrize("flag", [None, 0, "false", True])
def test_unknown_or_started_switch_checkpoints_restore_conservatively(rollback_case, flag):
    installer, fake, _, _ = rollback_case
    installer.state["backend_switch_started"] = flag
    installer.rollback()
    assert any("up" in command and command[-1] == "backend" for command in fake.calls)


def test_pre_switch_identity_drift_preserves_evidence_without_recreating_backend(rollback_case):
    installer, fake, _, override = rollback_case
    installer.state["backend_switch_started"] = False
    fake.backend["Id"] = "f" * 64
    with pytest.raises(setup.SetupError, match="changed before"):
        installer.rollback()
    assert override.exists() and installer.state["phase"] == "applying"
    assert not any("up" in command or "rm" in command for command in fake.calls)


def test_backend_switch_intent_is_saved_before_compose_can_run(rollback_case, monkeypatch):
    installer, fake, base, _ = rollback_case
    installer.state["backend_switch_started"] = False

    def fail_after_durable_intent(argv, **_kwargs):
        assert (
            json.loads((setup.STATE_ROOT / "state.json").read_text())["backend_switch_started"]
            is True
        )
        assert argv[-1] == "backend" and "up" in argv
        fake.calls.append(argv)
        raise setup.SetupError("simulated partial backend switch")

    monkeypatch.setattr(fake, "run", fail_after_durable_intent)
    with pytest.raises(setup.SetupError, match="partial backend switch"):
        installer.switch_backend([str(base)])
    assert installer.state["backend_switch_started"] is True and len(fake.calls) == 1


def test_backend_switch_cannot_run_if_checkpoint_write_fails(rollback_case, monkeypatch):
    installer, fake, base, _ = rollback_case

    def fail_save():
        raise OSError("state unavailable")

    monkeypatch.setattr(installer, "save", fail_save)
    with pytest.raises(OSError):
        installer.switch_backend([str(base)])
    assert not fake.calls


def test_application_health_and_proxy_are_restored_before_cleanup_failure(
    rollback_case, monkeypatch
):
    installer, _, _, override = rollback_case
    events = []
    monkeypatch.setattr(installer, "health", lambda: events.append("health"))
    monkeypatch.setattr(installer, "proxy", lambda: events.append("proxy"))
    monkeypatch.setattr(installer, "public_health", lambda: events.append("public"))

    def cleanup_failure():
        events.append("cleanup")
        raise setup.SetupError("cleanup identity mismatch")

    monkeypatch.setattr(installer, "remove_new_runner", cleanup_failure)
    with pytest.raises(setup.SetupError, match="cleanup identity"):
        installer.rollback()
    assert events == ["health", "proxy", "public", "cleanup"]
    assert override.exists() and installer.state["phase"] == "applying"


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


@pytest.mark.parametrize("original", [None, "/app/data/previous-research"])
def test_rollback_uses_captured_research_environment_instead_of_new_location(
    rollback_case, original
):
    installer, fake, _, _ = rollback_case
    installer.research_dir = setup.RESEARCH_DIR
    path = Path(installer.state["active_attempt"]) / "snapshot.json"
    snapshot = json.loads(path.read_text())
    if original is not None:
        snapshot["backend_env"]["MIZAN_RESEARCH_DIR"] = original
    path.write_text(json.dumps(snapshot))
    fake.rendered["services"]["backend"]["environment"] = snapshot["backend_env"].copy()
    fake.backend["Config"]["Env"] = ["MIZAN_RESEARCH_DIR=" + setup.RESEARCH_DIR]
    installer.rollback()
    assert fake.rendered["services"]["backend"]["environment"].get("MIZAN_RESEARCH_DIR") == original
    assert installer.state["phase"] == "rolled_back"


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
    started = tmp_path / "child-started"
    marker = tmp_path / "child-survived"
    child = f"import pathlib,time; pathlib.Path({str(started)!r}).write_text('started'); time.sleep(2); pathlib.Path({str(marker)!r}).write_text('unsafe')"
    parent = f"import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',{child!r}]); time.sleep(30)"
    with pytest.raises(setup.SetupError, match="deadline"):
        setup.Commands().run([sys.executable, "-c", parent], stage="Deadline test", timeout=1)
    assert started.exists(), "The child must actually start for the cleanup check to be meaningful"
    # Nested executors can expose /proc from a different PID namespace: the same
    # numeric PID may name an unrelated host service. Observe the child-specific
    # delayed mutation instead, waiting beyond its complete delay after timeout.
    deadline = time.monotonic() + 2.2
    while time.monotonic() < deadline and not marker.exists():
        time.sleep(0.05)
    assert not marker.exists()
