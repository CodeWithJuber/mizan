"""Runner upgrades during deploys, exercised against a fake host (no Docker, SSH or root)."""

from __future__ import annotations

import copy
import fcntl
import hashlib
import http.server
import importlib.util
import io
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "workspace_runner_setup_upgrade",
    Path(__file__).resolve().parents[1] / "scripts/setup_workspace_runner.py",
)
setup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup)

OLD_SHA, NEW_SHA = "a" * 40, "b" * 40
TOKEN = "t" * 64
BACKEND_IMAGE = "sha256:" + "0" * 64
UID = 1002
WORKER = ["/usr/bin/docker", "--host", f"unix:///run/user/{UID}/docker.sock"]


def tag(role: str, sha: str) -> str:
    return f"ghcr.io/{setup.REPOSITORY}/workspace-{role}:{sha}"


def image_id(digit: str) -> str:
    return "sha256:" + digit * 64


def generation(sha: str, runner: str, runtime: str, browser: str | None = None) -> dict:
    images = {
        "runner": {"id": image_id(runner), "source_tag": tag("runner", sha), "repo_digests": []},
        "runtime": {"id": image_id(runtime), "source_tag": tag("runtime", sha), "repo_digests": []},
    }
    if browser:
        images["browser"] = {
            "id": image_id(browser),
            "source_tag": tag("browser", sha),
            "repo_digests": [],
        }
    return images


OLD = generation(OLD_SHA, "1", "2")
NEW = generation(NEW_SHA, "3", "4")


def legacy_override(images: dict = OLD) -> dict:
    """The override the first install wrote: 192M and 128 pids."""
    document = setup.workspace_override(
        UID,
        UID,
        TOKEN,
        runtime_image=images["runtime"]["id"],
        runner_image=images["runner"]["id"],
        browser_image=(images.get("browser") or {}).get("id"),
    )
    runner = document["services"]["workspace-runner"]
    runner["pids_limit"] = 128
    runner["deploy"]["resources"]["limits"] = {"cpus": "0.5", "memory": "192M"}
    return document


def runner_container(document: dict) -> dict:
    runner = document["services"]["workspace-runner"]
    memory, cpus, pids = setup.runner_limits(document)
    return {
        "Id": "f" * 64,
        "Image": runner["image"],
        "State": {"Running": True},
        "Config": {
            "User": runner["user"],
            "Env": [f"{key}={value}" for key, value in runner["environment"].items()],
        },
        "HostConfig": {
            "ReadonlyRootfs": True,
            "Privileged": False,
            "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges:true"],
            "Memory": memory,
            "NanoCpus": cpus,
            "PidsLimit": pids,
        },
        "Mounts": [
            {
                "Type": "bind",
                "Source": f"/run/user/{UID}/docker.sock",
                "Destination": "/var/run/docker.sock",
            }
        ],
        "NetworkSettings": {"Networks": {"mizan_mizan-net": {}}},
    }


def session_container(key: str, runtime: str) -> dict:
    return {
        "Id": "5" * 64,
        "Name": f"/mizan-session-{key}",
        "Image": runtime,
        "Config": {
            "User": "65534:65534",
            "Env": [
                "HTTPS_PROXY=http://egress:3128",
                "HTTP_PROXY=http://egress:3128",
                "MIZAN_PREVIEW_PREFIX=",
                "TERM=xterm-256color",
            ],
            "Labels": {
                "mizan.session": key,
                "mizan.egress": "allowlist",
                "mizan.kind": "workspace",
            },
        },
        "HostConfig": {
            "ReadonlyRootfs": True,
            "Privileged": False,
            "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges"],
            "NetworkMode": f"mizan-session-net-{key}",
            "Memory": 768 * 1024**2,
            "MemorySwap": 768 * 1024**2,
            "NanoCpus": 10**9,
            "PidsLimit": 256,
            "Binds": None,
            "Devices": [],
            "PortBindings": {},
        },
        "Mounts": [{"Type": "volume", "Name": f"mizan-session-{key}", "Destination": "/workspace"}],
    }


def proxy_container(runtime: str) -> dict:
    return {
        "Id": "6" * 64,
        "Image": runtime,
        "Config": {
            "User": "65534:65534",
            "Env": ["MIZAN_SANDBOX_EGRESS_ALLOW=", "PATH=/usr/bin"],
            "Labels": {"mizan.egress": "proxy"},
        },
        "HostConfig": {
            "ReadonlyRootfs": True,
            "Privileged": False,
            "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges"],
            "Memory": 128 * 1024**2,
            "PortBindings": {},
        },
        "Mounts": [],
    }


class Host:
    """A fake production host: the root daemon, the worker daemon and the runner API."""

    def __init__(self, root: Path):
        self.root = root
        self.calls: list[tuple[list[str], str]] = []
        self.tags = {item["source_tag"]: item["id"] for item in OLD.values()}
        self.registry = {item["source_tag"]: item["id"] for item in NEW.values()}
        self.runner = runner_container(json.loads(setup.OVERRIDE.read_text()))
        self.proxy: dict | None = None
        self.sessions_open: list[str] = []
        self.session: dict | None = None
        self.fail: set[str] = set()
        self.at_switch: dict | None = None
        self.phases: list[str] = []
        self.fail_phases: set[str] = set()
        self.files: list[Path] = []

    def done(self, argv, stdout="", code=0, stderr=""):
        return subprocess.CompletedProcess(argv, code, stdout, stderr)

    def runtime(self) -> str:
        env = dict(item.split("=", 1) for item in self.runner["Config"]["Env"])
        return env["MIZAN_WORKSPACE_RUNTIME_IMAGE"]

    def run(self, argv, *, stage, stdin=None, env=None, timeout=60, check=True):
        self.calls.append((argv, stage))
        for failure in self.fail:
            if failure in stage:
                if check:
                    raise setup.SetupError(f"{stage}: command exited 1")
                return self.done(argv, code=1)
        if argv[: len(setup.DOCKER)] == setup.DOCKER:
            return self.root_daemon(argv, argv[len(setup.DOCKER) :], stdin)
        if argv[:3] == WORKER:
            return self.worker_daemon(argv, argv[3:])
        return self.done(argv)

    def image_inspect(self, argv, rest):
        if "--format" in rest:
            found = self.tags.get(rest[-1])
            return self.done(argv, found or "", 0 if found else 1)
        name = rest[2]
        if name == f"ghcr.io/{setup.REPOSITORY}/backend:{NEW_SHA}":
            return self.done(argv, json.dumps([{"Id": BACKEND_IMAGE}]))
        found = self.tags.get(name)
        return self.done(argv, json.dumps([{"Id": found}]) if found else "", 0 if found else 1)

    def pull(self, argv, rest):
        if rest[1] not in self.registry:
            raise setup.SetupError("Pull: command exited 1")
        self.tags[rest[1]] = self.registry[rest[1]]
        return self.done(argv)

    def root_daemon(self, argv, rest, stdin):
        if rest == ["inspect", "mizan-backend"]:
            return self.done(argv, json.dumps([self.backend()]))
        if rest[:2] == ["image", "inspect"]:
            return self.image_inspect(argv, rest)
        if rest[:2] == ["image", "rm"]:
            self.tags.pop(rest[2], None)
            return self.done(argv)
        if rest[0] == "pull":
            return self.pull(argv, rest)
        if rest[0] == "compose":
            if "ps" in rest:
                return self.done(argv, self.runner["Id"])
            if "up" in rest:
                assert rest[-1] == "workspace-runner"
                if self.at_switch is None:
                    self.at_switch = {
                        "state": json.loads((setup.STATE_ROOT / "state.json").read_text()),
                        "previous": (setup.STATE_ROOT / "override.previous").read_text(),
                    }
                self.runner = runner_container(json.loads(setup.OVERRIDE.read_text()))
            return self.done(argv)
        if rest == ["inspect", self.runner["Id"]]:
            return self.done(argv, json.dumps([self.runner]))
        if rest[0] == "exec" and rest[1] == self.runner["Id"]:
            return self.done(argv, code=1, stderr="urllib.error.HTTPError: HTTP Error 401")
        if rest[:3] == ["exec", "-i", "mizan-backend"] and len(rest) > 5:
            return self.session_phase(argv, *rest[5:8])
        return self.done(argv)

    def session_phase(self, argv, phase, key, nonce):
        self.phases.append(phase)
        sessions = self.runner["Image"] == NEW["runner"]["id"]
        verdict: dict = {"ok": True}
        if phase in ("check", "start") and not sessions:
            verdict = {"ok": False, "step": "predates", "status": 404}
        elif phase == "start":
            self.session = session_container(key, self.runtime())
            self.proxy = self.proxy or proxy_container(self.runtime())
            limits = {"memory": "768m", "cpus": "1", "pids": "256"}
            verdict.update(kind="workspace", limits=limits)
        elif phase == "probe" and "probe" in self.fail_phases:
            verdict = {"ok": False, "step": "npm", "status": 0}
        elif phase == "stop":
            self.session = None
        return self.done(argv, json.dumps(verdict) + "\n")

    def worker_daemon(self, argv, rest):
        if rest[:3] == ["inspect", "--type", "container"]:
            name = rest[3]
            if name == setup.SANDBOX_PROXY:
                found = self.proxy
            else:
                found = self.session if self.session and name == self.session["Name"][1:] else None
            return self.done(argv, json.dumps([found]) if found else "", 0 if found else 1)
        if rest[:2] == ["network", "inspect"] and self.session:
            network = {
                "Name": rest[2],
                "Internal": True,
                "Containers": {self.session["Id"]: {}, self.proxy["Id"]: {}},
            }
            return self.done(argv, json.dumps([network]))
        if rest[0] in ("container", "volume", "network") and rest[1] == "inspect":
            return self.done(argv, code=1)
        if rest[:2] == ["ps", "--quiet"] and "label=mizan.session" in rest:
            return self.done(argv, "\n".join(self.sessions_open))
        if rest[:2] == ["rm", "--force"] and self.proxy and rest[2] == self.proxy["Id"]:
            self.proxy = None
            return self.done(argv)
        if rest[:2] == ["image", "inspect"]:
            return self.image_inspect(argv, rest)
        if rest[:2] == ["image", "rm"]:
            self.tags.pop(rest[2], None)
            return self.done(argv)
        if rest[0] == "pull":
            return self.pull(argv, rest)
        if rest[0] == "logs":
            return self.done(argv, "egress denied registry.npmjs.org\nunrelated line\n")
        return self.done(argv)

    def backend(self) -> dict:
        files = ",".join(map(str, self.files))
        return {
            "Id": "b" * 64,
            "Image": BACKEND_IMAGE,
            "State": {"Running": True},
            "Config": {
                "Labels": {
                    "com.docker.compose.project": "mizan",
                    "com.docker.compose.project.working_dir": str(setup.PROJECT_ROOT),
                    "com.docker.compose.project.config_files": files,
                }
            },
            "NetworkSettings": {"Networks": {"mizan_mizan-net": {}}},
        }


@pytest.fixture
def host(tmp_path, monkeypatch):
    project, deploy = tmp_path / "opt-mizan", tmp_path / "mizan-deploy"
    state_root = deploy / "workspace-runner"
    project.mkdir()
    state_root.mkdir(parents=True)
    monkeypatch.setattr(setup, "PROJECT_ROOT", project)
    monkeypatch.setattr(setup, "DEPLOY_STATE", deploy)
    monkeypatch.setattr(setup, "STATE_ROOT", state_root)
    monkeypatch.setattr(setup, "OVERRIDE", project / "docker-compose.workspace-runtime.yml")
    monkeypatch.setattr(setup, "read_json", lambda path: json.loads(path.read_text()))
    monkeypatch.setattr(setup, "private_directory", lambda _: None)
    monkeypatch.setattr(
        setup, "protected_write", lambda path, content, **_: path.write_text(content)
    )
    monkeypatch.setattr(
        setup.shutil, "disk_usage", lambda _: type("Usage", (), {"free": 50 * 1024**3})
    )
    monkeypatch.setattr(setup.pwd, "getpwnam", lambda _: object())
    (project / "docker-compose.yml").write_text("services: {}\n")
    (deploy / "current.yml").write_text("{}\n")
    setup.OVERRIDE.write_text(setup.compose_document(legacy_override()))
    (state_root / "runner-token").write_text(TOKEN + "\n")
    state = {
        "manager": setup.MANAGER,
        "sha": OLD_SHA,
        "production_id": "production",
        "phase": "ready",
        "account_creation_started": True,
        "uid": UID,
        "gid": UID,
        "images": copy.deepcopy(OLD),
        "override_sha256": setup.digest(setup.OVERRIDE),
    }
    (state_root / "state.json").write_text(json.dumps(state))
    fake = Host(tmp_path)
    fake.files = [project / "docker-compose.yml", setup.OVERRIDE, deploy / "current.yml"]
    return fake


def upgrade(host, monkeypatch, **options) -> setup.Upgrade:
    runner = setup.Upgrade(NEW_SHA, host, **options)
    checks: list[str] = []

    def preflight(**_):
        runner.production_id = "production"

    def account():
        runner.worker = WORKER

    monkeypatch.setattr(runner, "preflight", preflight)
    monkeypatch.setattr(runner, "account", account)
    monkeypatch.setattr(runner, "verify_daemon", lambda: None)

    def token(*, create=True):
        # An upgrade reads the managed token; creating one would lock the backend out.
        assert create is False
        return TOKEN

    monkeypatch.setattr(runner, "token", token)
    monkeypatch.setattr(runner, "smoke", lambda container: checks.append(f"smoke:{container}"))
    monkeypatch.setattr(runner, "health", lambda: checks.append("health"))
    monkeypatch.setattr(runner, "public_health", lambda: checks.append("public"))
    runner.checks = checks
    return runner


def state() -> dict:
    return json.loads((setup.STATE_ROOT / "state.json").read_text())


def stages(host) -> list[str]:
    return [stage for _, stage in host.calls]


# ── Pure checks ───────────────────────────────────────────────────────────


def test_runner_limits_accept_only_the_two_reviewed_generations():
    assert setup.runner_limits(legacy_override()) == setup.LEGACY_LIMITS
    current = setup.workspace_override(
        UID, UID, TOKEN, runtime_image=image_id("2"), runner_image=image_id("1")
    )
    assert setup.runner_limits(current) == setup.CURRENT_LIMITS
    for change in ({"memory": "256M"}, {"cpus": "1"}, {"memory": None}):
        drifted = copy.deepcopy(current)
        drifted["services"]["workspace-runner"]["deploy"]["resources"]["limits"].update(change)
        with pytest.raises(setup.SetupError, match="reviewed generation"):
            setup.runner_limits(drifted)
    mixed = copy.deepcopy(legacy_override())
    mixed["services"]["workspace-runner"]["pids_limit"] = 512
    with pytest.raises(setup.SetupError):
        setup.runner_limits(mixed)


def test_the_installed_legacy_runner_verifies_with_its_own_limits(host, monkeypatch):
    runner = upgrade(host, monkeypatch)
    runner.state = state()
    files = [str(path) for path in host.files]
    assert runner.verify_runner(files, limits=setup.LEGACY_LIMITS) == "f" * 64
    with pytest.raises(setup.SetupError, match="resource limits"):
        runner.verify_runner(files)
    host.runner["Config"]["Env"].append(f"MIZAN_WORKSPACE_BROWSER_IMAGE={image_id('9')}")
    with pytest.raises(setup.SetupError, match="browser image"):
        runner.verify_runner(files, limits=setup.LEGACY_LIMITS)


def test_an_upgrade_may_change_only_the_runner():
    old = legacy_override()
    new = setup.workspace_override(
        UID, UID, TOKEN, runtime_image=image_id("4"), runner_image=image_id("3")
    )
    setup.validate_override_transition(old, new, TOKEN)
    for change in ("backend", "service", "token", "mount", "env"):
        drifted = copy.deepcopy(new)
        services = drifted["services"]
        if change == "backend":
            services["backend"]["environment"]["MIZAN_RESEARCH_DIR"] = setup.RESEARCH_DIR
        elif change == "service":
            services["frontend"] = {"image": "other"}
        elif change == "token":
            services["workspace-runner"]["environment"]["MIZAN_WORKSPACE_RUNNER_TOKEN"] = "x" * 64
        elif change == "mount":
            services["workspace-runner"]["volumes"].append(
                {"type": "bind", "source": "/", "target": "/host"}
            )
        else:
            services["workspace-runner"]["environment"]["MIZAN_SESSION_MEMORY"] = "8g"
        with pytest.raises(setup.SetupError):
            setup.validate_override_transition(old, drifted, TOKEN)


@pytest.mark.parametrize(
    "drift", ["user", "network", "bind", "secret", "proxy_env", "memory", "volume", "label"]
)
def test_sessions_without_confinement_are_rejected(drift):
    key = "c" * 32
    container = session_container(key, image_id("4"))
    limits = (768 * 1024**2, 10**9, 256)
    setup.validate_session_container(container, key, limits)
    host, config = container["HostConfig"], container["Config"]
    if drift == "user":
        config["User"] = "0:0"
    elif drift == "network":
        host["NetworkMode"] = "bridge"
    elif drift == "bind":
        host["Binds"] = ["/var/run/docker.sock:/var/run/docker.sock"]
    elif drift == "secret":
        config["Env"].append("OPENROUTER_API_KEY=x")
    elif drift == "proxy_env":
        config["Env"] = [item for item in config["Env"] if not item.startswith("HTTPS_PROXY")]
    elif drift == "memory":
        host["MemorySwap"] = -1
    elif drift == "volume":
        container["Mounts"][0]["Name"] = "mizan-session-" + "d" * 32
    else:
        config["Labels"]["mizan.egress"] = "off"
    with pytest.raises(setup.SetupError):
        setup.validate_session_container(container, key, limits)


def test_session_network_and_egress_proxy_must_be_confined():
    key = "c" * 32
    network = {
        "Name": f"mizan-session-net-{key}",
        "Internal": True,
        "Containers": {"5" * 64: {}, "6" * 64: {}},
    }
    setup.validate_session_network(network, key, {"5" * 64, "6" * 64})
    for change in ({"Internal": False}, {"Containers": {"5" * 64: {}, "7" * 64: {}}}):
        with pytest.raises(setup.SetupError):
            setup.validate_session_network({**network, **change}, key, {"5" * 64, "6" * 64})
    proxy = proxy_container(image_id("4"))
    setup.validate_egress_proxy(proxy, {image_id("4")})
    with pytest.raises(setup.SetupError, match="image"):
        setup.validate_egress_proxy(proxy, {image_id("2")})
    writable = copy.deepcopy(proxy)
    writable["HostConfig"]["ReadonlyRootfs"] = False
    with pytest.raises(setup.SetupError, match="isolation"):
        setup.validate_egress_proxy(writable, {image_id("4")})
    assert setup.session_limits({"memory": "384m", "cpus": "0.5", "pids": "128"}) == (
        384 * 1024**2,
        500000000,
        128,
    )
    with pytest.raises(setup.SetupError):
        setup.session_limits({"memory": "lots", "cpus": "1", "pids": "1"})


# ── The deploy's lock and arguments ──────────────────────────────────────


def test_the_inherited_deploy_lock_is_checked_and_never_released(tmp_path):
    lock = tmp_path / "deploy.lock"
    held = os.open(lock, os.O_WRONLY | os.O_CREAT, 0o600)
    fcntl.flock(held, fcntl.LOCK_EX)
    try:
        setup.verify_inherited_lock(held, lock)
        other = os.open(lock, os.O_RDONLY)
        try:
            # Still held by the deploy's open file after the check.
            with pytest.raises(BlockingIOError):
                fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with pytest.raises(setup.SetupError, match="Another process"):
                setup.verify_inherited_lock(other, lock)
        finally:
            os.close(other)
        unrelated = tmp_path / "other"
        unrelated.write_text("")
        wrong = os.open(unrelated, os.O_RDONLY)
        try:
            with pytest.raises(setup.SetupError, match="not the deployment lock"):
                setup.verify_inherited_lock(wrong, lock)
        finally:
            os.close(wrong)
        # A descriptor that was just closed, not a number that may be open here.
        closed = os.open(unrelated, os.O_RDONLY)
        os.close(closed)
        with pytest.raises(setup.SetupError, match="not open"):
            setup.verify_inherited_lock(closed, lock)
    finally:
        os.close(held)


def test_the_deploy_argv_is_accepted_and_mixed_modes_are_refused():
    args = setup.parse_arguments(
        [
            "--upgrade",
            "--sha",
            NEW_SHA,
            "--repository",
            setup.REPOSITORY,
            "--inherited-lock-fd",
            "9",
            "--inputs-digest",
            "e" * 64,
        ]
    )
    assert args.upgrade and args.inherited_lock_fd == 9 and args.inputs_digest == "e" * 64
    for argv in (
        ["--upgrade", "--rollback"],
        ["--upgrade", "--research-dir", setup.RESEARCH_DIR],
        ["--inherited-lock-fd", "9"],
        ["--with-browser"],
        ["--upgrade", "--inherited-lock-fd", "2"],
        ["--upgrade", "--inputs-digest", "E" * 64],
    ):
        with pytest.raises(SystemExit):
            setup.parse_arguments(["--sha", NEW_SHA, *argv])


@pytest.mark.parametrize(
    "raised,code",
    [
        (setup.UpgradeRolledBack("kept"), 75),
        (setup.UpgradeUnrecovered("lost"), 76),
        (setup.SetupError("unexpected"), 76),
        (None, 0),
    ],
)
def test_upgrade_exit_codes(monkeypatch, raised, code):
    seen = {}

    def run(self, credential):
        seen["credential"] = credential
        if raised:
            raise raised
        return "upgraded"

    @setup.contextlib.contextmanager
    def lock(descriptor):
        seen["fd"] = descriptor
        yield

    monkeypatch.setattr(setup.Upgrade, "run", run)
    monkeypatch.setattr(setup, "deployment_lock", lock)
    monkeypatch.setattr(setup.signal, "signal", lambda *_: None)
    monkeypatch.setattr(setup.os, "umask", lambda _: 0)
    monkeypatch.setattr(sys, "stdin", io.StringIO("registry-token\n"))
    argv = ["--upgrade", "--sha", NEW_SHA, "--inherited-lock-fd", "9"]
    assert setup.main(argv) == code
    assert seen == {"credential": "registry-token", "fd": 9}


# ── Upgrades on the fake host ─────────────────────────────────────────────


def test_no_managed_runner_means_nothing_to_upgrade(host, monkeypatch):
    (setup.STATE_ROOT / "state.json").unlink()
    assert upgrade(host, monkeypatch).run("token") == "absent"
    assert not host.calls


@pytest.mark.parametrize("phase", ["preparing", "rolled_back"])
def test_a_setup_that_never_completed_is_left_alone(host, monkeypatch, phase):
    current = state()
    current["phase"] = phase
    (setup.STATE_ROOT / "state.json").write_text(json.dumps(current))
    assert upgrade(host, monkeypatch).run("token") == "absent"
    assert not host.calls


def test_the_legacy_runner_is_upgraded_and_proves_sessions(host, monkeypatch):
    legacy = setup.OVERRIDE.read_text()
    runner = upgrade(host, monkeypatch, inputs_digest="e" * 64)
    assert runner.run("registry-token") == "upgraded"

    final = state()
    assert final["phase"] == "ready" and final["sha"] == NEW_SHA
    assert final["images"] == NEW and final["previous_images"] == OLD
    assert final["inputs_digest"] == "e" * 64
    assert final["last_upgrade"]["result"] == "upgraded"
    assert "upgrade" not in final and "pending_override_sha256" not in final
    document = json.loads(setup.OVERRIDE.read_text())
    assert setup.runner_limits(document) == setup.CURRENT_LIMITS
    assert final["override_sha256"] == setup.digest(setup.OVERRIDE)
    assert host.runner["Image"] == NEW["runner"]["id"]
    # The intent and the previous override were durable before the runner changed.
    assert host.at_switch["state"]["phase"] == "upgrading"
    assert host.at_switch["state"]["upgrade"]["stage"] == "switching"
    assert host.at_switch["previous"] == legacy
    assert (setup.STATE_ROOT / "override.previous").read_text() == legacy
    # Both smokes ran, the session through all its phases; the site was checked.
    assert host.phases == ["start", "probe", "stop"]
    assert runner.checks == ["smoke:mizan-backend", "health", "public"]
    # Only the runner service changed: no backend/frontend, account, systemd or packages.
    ups = [argv for argv, _ in host.calls if "up" in argv]
    assert len(ups) == 1 and ups[0][-1] == "workspace-runner"
    flat = " ".join(" ".join(argv) for argv, _ in host.calls)
    for forbidden in ("systemctl", "useradd", "apt-get", "loginctl", "frontend"):
        assert forbidden not in flat
    # The registry token reached only docker login, on stdin.
    assert "registry-token" not in flat


def test_unchanged_inputs_only_check_the_running_runner(host, monkeypatch):
    current = state()
    current.update(images=copy.deepcopy(NEW), inputs_digest="e" * 64, sha=NEW_SHA)
    document = setup.workspace_override(
        UID, UID, TOKEN, runtime_image=NEW["runtime"]["id"], runner_image=NEW["runner"]["id"]
    )
    setup.OVERRIDE.write_text(setup.compose_document(document))
    current["override_sha256"] = setup.digest(setup.OVERRIDE)
    (setup.STATE_ROOT / "state.json").write_text(json.dumps(current))
    host.runner = runner_container(document)
    host.tags.update(host.registry)
    assert upgrade(host, monkeypatch, inputs_digest="e" * 64).run("token") == "current"
    assert host.phases == ["check"]
    assert not any("pull" in argv or "up" in argv for argv, _ in host.calls)


@pytest.mark.parametrize(
    "failure",
    ["Start the upgraded private runner", "probe", "Sandbox session check: start", "public"],
)
def test_a_failure_after_the_switch_restores_the_previous_runner(host, monkeypatch, failure):
    legacy = setup.OVERRIDE.read_text()
    runner = upgrade(host, monkeypatch)
    if failure == "probe":
        host.fail_phases = {"probe"}
    elif failure == "public":

        def broken():
            raise setup.SetupError("Public health failed")

        monkeypatch.setattr(runner, "public_health", broken)
    else:
        host.fail = {failure}
    with pytest.raises(setup.UpgradeRolledBack, match="restored and verified"):
        runner.run("token")
    assert setup.OVERRIDE.read_text() == legacy
    final = state()
    assert final["phase"] == "ready" and final["images"] == OLD and final["sha"] == OLD_SHA
    assert final["override_sha256"] == setup.digest(setup.OVERRIDE)
    assert final["last_upgrade"]["result"] == "rolled_back" and "upgrade" not in final
    assert host.runner["Image"] == OLD["runner"]["id"]
    assert setup.runner_limits(json.loads(legacy)) == setup.LEGACY_LIMITS
    # The failed generation is removed by tag; the installed one is kept.
    assert all(item["source_tag"] not in host.tags for item in NEW.values())
    assert all(item["source_tag"] in host.tags for item in OLD.values())
    assert host.session is None
    if failure == "probe":
        assert "stop" in host.phases


def test_an_unverified_restore_is_resumed_by_the_next_deploy(host, monkeypatch):
    legacy = setup.OVERRIDE.read_text()
    host.fail_phases = {"probe"}
    host.fail = {"Restore the previous private runner"}
    with pytest.raises(setup.UpgradeUnrecovered, match="next deploy"):
        upgrade(host, monkeypatch).run("token")
    assert state()["phase"] == "upgrading"

    host.fail = set()
    with pytest.raises(setup.UpgradeRolledBack, match="interrupted upgrade was restored"):
        upgrade(host, monkeypatch).run("token")
    assert setup.OVERRIDE.read_text() == legacy
    assert state()["phase"] == "ready" and host.runner["Image"] == OLD["runner"]["id"]


def test_a_failure_before_the_switch_changes_nothing_live(host, monkeypatch):
    legacy = setup.OVERRIDE.read_text()
    del host.registry[NEW["runtime"]["source_tag"]]
    with pytest.raises(setup.UpgradeRolledBack, match="kept and verified"):
        upgrade(host, monkeypatch).run("token")
    assert setup.OVERRIDE.read_text() == legacy
    assert not any("up" in argv for argv, _ in host.calls)
    final = state()
    assert final["phase"] == "ready" and "upgrade" not in final and final["images"] == OLD
    # The runner image that did pull is not left behind.
    assert NEW["runner"]["source_tag"] not in host.tags


def test_a_drifted_install_is_not_touched(host, monkeypatch):
    setup.OVERRIDE.write_text(setup.OVERRIDE.read_text() + "\n")
    with pytest.raises(setup.UpgradeUnrecovered, match="changed outside"):
        upgrade(host, monkeypatch).run("token")
    assert not any("pull" in argv or "up" in argv for argv, _ in host.calls)


@pytest.mark.parametrize("case", ["off", "asked", "installed"])
def test_the_browser_is_pulled_only_when_installed_or_asked_for(host, monkeypatch, case):
    browser = tag("browser", NEW_SHA)
    host.registry[browser] = image_id("7")
    if case == "installed":
        installed = generation(OLD_SHA, "1", "2", browser="8")
        setup.OVERRIDE.write_text(setup.compose_document(legacy_override(installed)))
        current = state()
        current.update(images=installed, override_sha256=setup.digest(setup.OVERRIDE))
        (setup.STATE_ROOT / "state.json").write_text(json.dumps(current))
        host.runner = runner_container(legacy_override(installed))
        host.tags[installed["browser"]["source_tag"]] = installed["browser"]["id"]
    assert upgrade(host, monkeypatch, with_browser=case == "asked").run("token") == "upgraded"
    pulled = any(argv[-2:] == ["pull", browser] for argv, _ in host.calls)
    assert pulled is (case != "off")
    environment = json.loads(setup.OVERRIDE.read_text())["services"]["workspace-runner"][
        "environment"
    ]
    assert ("MIZAN_WORKSPACE_BROWSER_IMAGE" in environment) is (case != "off")


def test_an_installed_browser_that_cannot_be_pulled_keeps_the_previous_runner(host, monkeypatch):
    installed = generation(OLD_SHA, "1", "2", browser="8")
    setup.OVERRIDE.write_text(setup.compose_document(legacy_override(installed)))
    current = state()
    current.update(images=installed, override_sha256=setup.digest(setup.OVERRIDE))
    (setup.STATE_ROOT / "state.json").write_text(json.dumps(current))
    host.runner = runner_container(legacy_override(installed))
    with pytest.raises(setup.UpgradeRolledBack, match="kept and verified"):
        upgrade(host, monkeypatch).run("token")
    assert not any("up" in argv for argv, _ in host.calls)


def test_pruning_keeps_two_generations_and_removes_only_recorded_tags(host, monkeypatch):
    runner = upgrade(host, monkeypatch)
    runner.worker = WORKER
    runner.state = state()
    older = generation("c" * 40, "8", "9")
    runner.state["previous_images"] = older
    host.tags[older["runner"]["source_tag"]] = older["runner"]["id"]
    # This tag was re-pointed at another image since: it must stay.
    host.tags[older["runtime"]["source_tag"]] = image_id("5")
    runner.prune_previous()
    assert older["runner"]["source_tag"] not in host.tags
    assert host.tags[older["runtime"]["source_tag"]] == image_id("5")
    assert "previous_images" not in runner.state
    removals = [argv for argv, _ in host.calls if argv[-2:-1] == ["rm"]]
    assert all("--force" not in argv for argv in removals)
    tampered = {"runner": {"id": image_id("8"), "source_tag": "docker.io/library/alpine:3"}}
    with pytest.raises(setup.SetupError, match="not reviewed"):
        runner.discard_generation(tampered)


def test_the_egress_proxy_is_replaced_only_when_idle(host, monkeypatch):
    runner = upgrade(host, monkeypatch)
    runner.worker = WORKER
    host.proxy = proxy_container(OLD["runtime"]["id"])
    host.sessions_open = ["9" * 12]
    assert runner.retire_proxy(keep=NEW["runtime"]["id"]) is False
    assert host.proxy is not None
    host.sessions_open = []
    assert runner.retire_proxy(keep=NEW["runtime"]["id"]) is True
    assert host.proxy is None
    host.proxy = {**proxy_container(OLD["runtime"]["id"]), "Config": {"Labels": {}}}
    with pytest.raises(setup.SetupError, match="unmanaged"):
        runner.retire_proxy(keep=NEW["runtime"]["id"])


def test_the_one_shot_smoke_cleanup_ignores_sessions_and_their_proxy(monkeypatch):
    calls = []

    class Daemon:
        def run(self, argv, *, stage, **kwargs):
            calls.append(argv)
            if argv[-2:] == ["--filter", setup.JOB_FILTER] and "--all" in argv:
                return subprocess.CompletedProcess(argv, 0, "", "")
            if "ps" in argv and "--all" in argv:
                return subprocess.CompletedProcess(argv, 0, "proxy\nsession\n", "")
            if "ps" in argv:
                return subprocess.CompletedProcess(argv, 0, "job", "")
            if argv[-2:] == ["inspect", "job"]:
                return subprocess.CompletedProcess(argv, 0, json.dumps([valid_job()]), "")
            if "exec" in argv:
                threading.Event().wait(0.5)
            return subprocess.CompletedProcess(argv, 0, "", "")

    installer = setup.Installer(NEW_SHA, Daemon())
    installer.worker = WORKER
    monkeypatch.setattr(installer, "verify_daemon", lambda: None)
    installer.smoke("mizan-backend")
    assert [*WORKER, "ps", "--all", "--quiet"] not in calls


def valid_job() -> dict:
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


def test_setup_rollback_is_refused_once_a_deploy_upgraded_the_runner():
    installer = setup.Installer(NEW_SHA)
    installer.state = {"last_upgrade": {"result": "upgraded"}}
    with pytest.raises(setup.SetupError, match="upgraded this runner"):
        installer.rollback()


# ── The session smoke script against a stdlib fake runner ─────────────────


class FakeRunner(http.server.BaseHTTPRequestHandler):
    server: FakeRunnerServer

    def log_message(self, *_):
        pass

    def reply(self, status: int, body: dict, *, ours: bool = True):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        if ours and status >= 400:
            self.send_header("X-Mizan-Runner", "error")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def handle_any(self, method: str):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}") if length else {}
        state = self.server.state
        state.requests.append((method, self.path, body))
        if self.headers.get("Authorization") != f"Bearer {TOKEN}":
            return self.reply(401, {"detail": "Runner authentication required"})
        if self.path == "/health":
            return self.reply(200, {"available": True, "isolated": True})
        if state.old:
            return self.reply(404, {"detail": "Not Found"}, ours=False)
        base, _, action = self.path.partition("/sessions/")[2].partition("/")
        assert len(base) == 32
        if method == "GET":
            return self.reply(
                200,
                {
                    "running": state.running,
                    "nonce": state.nonce,
                    "kind": "workspace",
                    "egress": True,
                    "services": [],
                    "limits": {"memory": "768m", "cpus": "1", "pids": "256", "max": "2"},
                },
            )
        if method == "PUT":
            state.running, state.nonce = True, body["nonce"]
            return self.reply(
                200, {"running": True, "nonce": body["nonce"], "kind": body["kind"], "egress": True}
            )
        if method == "DELETE":
            state.running = False
            return self.reply(200, {"running": False})
        if action == "sync":
            state.files.update(body["files"])
            return self.reply(200, {"written": len(body["files"]), "removed": 0})
        if action == "manifest":
            import base64

            files = {
                name: hashlib.sha256(base64.b64decode(data)).hexdigest()
                for name, data in state.files.items()
            }
            return self.reply(200, {"files": files, "directories": []})
        if action == "exec":
            command = body["command"]
            if "npm view left-pad@1.3.0 version" in command:
                out = state.npm
            elif "pypi.org/simple/pip/" in command:
                out = "pypi\n"
            elif "egress-confined" in command and "169.254.169.254" in command:
                out = "egress-confined\n"
            else:
                out = ""
            return self.reply(200, {"stdout": out, "stderr": "", "exit_code": 0})
        return self.reply(404, {"detail": "Not Found"}, ours=False)

    def do_GET(self):
        self.handle_any("GET")

    def do_PUT(self):
        self.handle_any("PUT")

    def do_DELETE(self):
        self.handle_any("DELETE")

    def do_POST(self):
        self.handle_any("POST")


class FakeRunnerServer(http.server.ThreadingHTTPServer):
    state: object


@pytest.fixture
def fake_runner():
    server = FakeRunnerServer(("127.0.0.1", 0), FakeRunner)
    server.state = type(
        "State",
        (),
        {
            "requests": [],
            "running": False,
            "nonce": "",
            "files": {},
            "old": False,
            "npm": "1.3.0\n",
        },
    )()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()


def smoke_phase(server, phase: str, key: str = "a" * 32, nonce: str = "b" * 32) -> dict:
    result = subprocess.run(
        [sys.executable, "-I", "-", phase, key, nonce],
        input=setup.SESSION_SMOKE_SCRIPT,
        capture_output=True,
        text=True,
        timeout=60,
        env={
            "PATH": os.environ.get("PATH", "/usr/bin"),
            "MIZAN_WORKSPACE_RUNNER_URL": f"http://127.0.0.1:{server.server_address[1]}/",
            "MIZAN_WORKSPACE_RUNNER_TOKEN": TOKEN,
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "HTTP_PROXY": "http://127.0.0.1:9",
        },
        check=False,
    )
    assert result.returncode == 0, result.stderr[-500:]
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_the_session_smoke_script_drives_a_whole_session(fake_runner):
    state = fake_runner.state
    started = smoke_phase(fake_runner, "start")
    assert started == {
        "ok": True,
        "kind": "workspace",
        "limits": {"memory": "768m", "cpus": "1", "pids": "256"},
    }
    assert smoke_phase(fake_runner, "probe") == {"ok": True}
    assert smoke_phase(fake_runner, "stop") == {"ok": True}
    session = "/sessions/" + "a" * 32
    assert [(method, path) for method, path, _ in state.requests] == [
        ("GET", "/health"),
        ("GET", session),
        ("PUT", session),
        ("GET", session),
        ("POST", session + "/sync"),
        ("POST", session + "/manifest"),
        ("POST", session + "/exec"),
        ("POST", session + "/exec"),
        ("POST", session + "/exec"),
        ("DELETE", session),
        ("GET", session),
    ]
    assert state.requests[2][2] == {"nonce": "b" * 32, "kind": "workspace", "preview_prefix": ""}
    assert [body.get("language") for _, _, body in state.requests[6:9]] == [
        "shell",
        "python",
        "python",
    ]
    assert not state.running


def test_the_session_smoke_names_npm_and_old_runners(fake_runner):
    smoke_phase(fake_runner, "start")
    fake_runner.state.npm = "npm error network\n"
    assert smoke_phase(fake_runner, "probe") == {"ok": False, "step": "npm", "status": 0}
    fake_runner.state.old = True
    assert smoke_phase(fake_runner, "check", "c" * 32) == {
        "ok": False,
        "step": "predates",
        "status": 404,
    }
