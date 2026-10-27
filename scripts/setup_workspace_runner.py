#!/usr/bin/env python3
"""Provision only Mizan's dedicated rootless workspace worker on its known host.

The registry credential is read once from stdin. All subprocess output is private;
only stage names and verified, non-secret receipts are printed. Run as root over
the existing pinned SSH connection. See docs/runner-setup.md before executing.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import pwd
import re
import secrets
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

REPOSITORY = "codewithjuber/mizan"
ACCOUNT = "mizan-workspace"
ACCOUNT_HOME = Path("/var/lib/mizan-workspace")
PROJECT_ROOT = Path("/opt/mizan")
DEPLOY_STATE = Path("/var/lib/mizan-deploy")
STATE_ROOT = DEPLOY_STATE / "workspace-runner"
OVERRIDE = PROJECT_ROOT / "docker-compose.workspace-runtime.yml"
ROOT_SOCKET = Path("/var/run/docker.sock")
DOCKER = ["/usr/bin/docker", "--host", f"unix://{ROOT_SOCKET}"]
SAFE_ENV = {
    "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "LANG": "C.UTF-8",
}
MANAGER = "mizan-isolated-workspace-v1"
CAP_BYTES = 2 * 1024**3
RESEARCH_DIR = "/data/mizan/research"


class SetupError(RuntimeError):
    """A safe, deliberately credential-free diagnostic."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SetupError(message)


def report(message: str, *, error: bool = False) -> None:
    """An SSH/logging disconnect must never prevent a restoration command."""
    try:
        print(message, file=sys.stderr if error else sys.stdout, flush=True)
    except (OSError, ValueError):
        # EPIPE/closed streams are diagnostic failures, not deployment failures.
        pass


def validate_target(sha: str, repository: str) -> None:
    require(bool(re.fullmatch(r"[a-f0-9]{40}", sha)), "Expected a full lowercase commit SHA")
    require(repository == REPOSITORY, "This installer is scoped to codewithjuber/mizan")


def validate_research_option(directory: str | None) -> None:
    require(directory in (None, RESEARCH_DIR), "Research directory must be /data/mizan/research")


def validate_research_location(backend: dict, probe: dict, *, configured: bool = False) -> None:
    environment = dict(
        value.split("=", 1) for value in backend["Config"].get("Env", []) if "=" in value
    )
    require(
        environment.get("MIZAN_DATA_DIR") == "/data/mizan",
        "Existing backend data directory differs from the reviewed research parent",
    )
    require(
        probe.get("uid") == 999, "Research parent must be checked as the existing backend UID999"
    )
    require(
        probe.get("parent_directory")
        and probe.get("parent_resolved") == "/data/mizan"
        and probe.get("parent_writable"),
        "Research parent must already exist without symlinks and be writable by the backend",
    )
    resolved = Path(probe.get("resolved_target", "/"))
    require(
        resolved.is_relative_to("/data/mizan") and resolved != Path("/data/mizan"),
        "Research target resolves outside the persistent research parent",
    )
    require(
        not probe.get("target_exists") or probe.get("target_directory"),
        "Existing research target is not a directory",
    )
    for target in (Path(RESEARCH_DIR), resolved):
        candidates = [
            mount
            for mount in backend.get("Mounts", [])
            if target.is_relative_to(mount["Destination"])
        ]
        require(bool(candidates), "Research target has no existing persistent mount")
        mount = max(candidates, key=lambda item: len(Path(item["Destination"]).parts))
        require(
            mount.get("Destination") == "/data"
            and mount.get("RW") is True
            and mount.get("Type") in {"volume", "bind"},
            "Research target must use the existing writable persistent /data mount",
        )
        for temporary in backend.get("HostConfig", {}).get("Tmpfs", {}) or {}:
            require(
                not target.is_relative_to(temporary), "A tmpfs mount shadows the research target"
            )
    if configured:
        require(
            environment.get("MIZAN_RESEARCH_DIR") == RESEARCH_DIR,
            "Backend research directory was not applied",
        )


RESEARCH_PROBE = r"""
import json, os
from pathlib import Path
target = Path("/data/mizan/research")
parent = target.parent
print(json.dumps({"uid": os.geteuid(), "parent_directory": parent.is_dir(),
    "parent_resolved": str(parent.resolve()),
    "parent_writable": os.access(parent, os.W_OK | os.X_OK, effective_ids=True),
    "target_exists": os.path.lexists(target), "target_directory": target.is_dir(),
    "resolved_target": str(target.resolve())}))
"""


def protected_write(path: Path, content: str, *, mode: int = 0o600) -> None:
    """Atomically replace a file only inside an existing root-owned directory."""
    require(path.parent.resolve() == path.parent, "Refusing a symlinked state directory")
    info = path.parent.stat()
    require(info.st_uid == 0 and not info.st_mode & 0o022, "Unsafe state-directory ownership")
    require(not path.is_symlink(), "Refusing a symlinked managed file")
    if path.exists():
        require(path.is_file() and path.stat().st_uid == 0, "Refusing an unmanaged file")
    descriptor, temporary = tempfile.mkstemp(prefix=".mizan-", dir=path.parent)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "w") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def private_directory(path: Path) -> None:
    require(not path.is_symlink(), "Refusing a symlinked state directory")
    if not path.exists():
        path.mkdir(mode=0o700)
    info = path.stat()
    require(info.st_uid == 0 and not info.st_mode & 0o077, "State directory must be root-only")


def read_json(path: Path) -> dict:
    require(not path.is_symlink(), "Refusing a symlinked state file")
    info = path.stat()
    require(info.st_uid == 0 and not info.st_mode & 0o077, "State file must be root-only")
    value = json.loads(path.read_text())
    require(isinstance(value, dict), "Invalid managed state")
    return value


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compose_document(value: dict) -> str:
    """Compose interpolates JSON too: escape literal dollars in runtime values."""

    def literal(item):
        if isinstance(item, str):
            return item.replace("$", "$$")
        if isinstance(item, list):
            return [literal(child) for child in item]
        if isinstance(item, dict):
            return {key: literal(child) for key, child in item.items()}
        return item

    return json.dumps(literal(value), indent=2) + "\n"


def validate_rendered_backend(config: dict, snapshot: dict, environment: dict) -> None:
    """Fail before recreation if live Compose inputs drifted from the container."""
    backend = config["services"]["backend"]
    require(backend.get("image") == snapshot["backend_image"], "Rendered backend image changed")
    require(backend.get("environment", {}) == environment, "Rendered backend environment changed")
    require(
        not backend.get("secrets") and not backend.get("configs"),
        "Unexpected backend secret/config mounts",
    )
    mounts = {}
    for mount in backend.get("volumes", []):
        kind = mount["type"]
        source = mount.get("source", "")
        if kind == "volume":
            source = config.get("volumes", {}).get(source, {}).get("name", "")
        require(kind in {"volume", "bind"} and bool(source), "Unrecognized rendered backend mount")
        mounts[mount["target"]] = (kind, source, not mount.get("read_only", False))
    current = {
        mount["Destination"]: (
            mount["Type"],
            mount.get("Name") if mount["Type"] == "volume" else mount["Source"],
            mount["RW"],
        )
        for mount in snapshot["backend_mounts"]
    }
    require(mounts == current and not backend.get("tmpfs"), "Rendered backend data mounts changed")
    networks = {
        config.get("networks", {}).get(name, {}).get("name") for name in backend.get("networks", {})
    }
    require(networks == set(snapshot["backend_networks"]), "Rendered backend networks changed")
    require(
        backend.get("container_name") == "mizan-backend",
        "Rendered backend container ownership changed",
    )
    actual_ports = {
        (target, entry.get("HostIp") or "0.0.0.0", entry["HostPort"])
        for target, entries in snapshot.get("backend_ports", {}).items()
        for entry in (entries or [])
    }
    rendered_ports = {
        (
            f"{entry['target']}/{entry.get('protocol', 'tcp')}",
            entry.get("host_ip") or "0.0.0.0",
            str(entry.get("published", "")),
        )
        for entry in backend.get("ports", [])
    }
    require(rendered_ports == actual_ports, "Rendered backend published ports changed")
    require(
        not backend.get("privileged") and not backend.get("devices"),
        "Rendered backend host exposure changed",
    )
    require(
        not backend.get("pid") and not backend.get("network_mode"),
        "Rendered backend namespace changed",
    )


class Commands:
    @staticmethod
    def terminate_group(process: subprocess.Popen) -> None:
        # docker compose invokes a plugin child. Killing only the CLI parent can
        # leave that child changing containers while rollback starts.
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)

    def run(
        self,
        argv: list[str],
        *,
        stage: str,
        stdin: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int = 60,
        check: bool = True,
    ) -> subprocess.CompletedProcess:
        try:
            process = subprocess.Popen(
                argv,
                stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env={**SAFE_ENV, **(env or {})},
                start_new_session=True,
            )
            try:
                stdout, stderr = process.communicate(input=stdin, timeout=timeout)
            except BaseException:
                self.terminate_group(process)
                raise
            result = subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)
        except (OSError, subprocess.TimeoutExpired):
            raise SetupError(f"{stage}: command unavailable or deadline exceeded") from None
        if check and result.returncode:
            # Docker inspect/Compose/login output can contain credentials. Never
            # attach argv, input, stdout, stderr, or CalledProcessError here.
            raise SetupError(f"{stage}: command exited {result.returncode}")
        return result


def validate_package_plan(output: str) -> None:
    allowed = {"uidmap", "slirp4netns", "libslirp0", "libsubid4"}
    for line in output.splitlines():
        if line.startswith("Remv "):
            raise SetupError("Package plan would remove an installed package")
        if line.startswith("Inst "):
            package = line.split()[1].split(":", 1)[0]
            require(package in allowed, "Package plan exceeds the missing rootless prerequisites")
            require("[" not in line.split("(", 1)[0], "Package plan would upgrade a package")


def validate_subids(contents: str, account: str) -> None:
    ranges = []
    for line in contents.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        owner, start, count = line.split(":")
        ranges.append((owner, int(start), int(count)))
    own = [(start, count) for owner, start, count in ranges if owner == account]
    require(
        any(start >= 65536 and count >= 65536 for start, count in own),
        "Missing subordinate ID range",
    )
    for start, count in own:
        for owner, other, length in ranges:
            if owner != account:
                require(
                    start + count <= other or other + length <= start,
                    "Subordinate IDs overlap another account",
                )


def validate_daemon(info: dict, production_id: str, home: Path) -> None:
    require(
        any("rootless" in item for item in info.get("SecurityOptions", [])),
        "Worker daemon is not rootless",
    )
    require(
        info.get("ID") and info["ID"] != production_id,
        "Worker and production daemon identities overlap",
    )
    require(
        str(info.get("CgroupVersion")) == "2" and info.get("CgroupDriver") == "systemd",
        "Worker cgroup limits are unavailable",
    )
    require(
        Path(info.get("DockerRootDir", "/")) == home / ".local/share/docker",
        "Unexpected worker data directory",
    )


def workspace_override(
    uid: int,
    gid: int,
    token: str,
    *,
    runtime_image: str,
    runner_image: str,
    research_dir: str | None = None,
) -> dict:
    validate_research_option(research_dir)
    require(uid >= 1000 and gid > 0, "Worker must use an unprivileged service account")
    require(bool(re.fullmatch(r"[A-Za-z0-9_-]{64}", token)), "Invalid managed runner token")
    require(
        all(re.fullmatch(r"sha256:[a-f0-9]{64}", image) for image in (runtime_image, runner_image)),
        "Worker images must be pinned to locally pulled content IDs",
    )
    return {
        "services": {
            "backend": {
                "environment": {
                    "MIZAN_WORKSPACE_RUNNER_URL": "http://workspace-runner:8080",
                    "MIZAN_WORKSPACE_RUNNER_TOKEN": token,
                    **({"MIZAN_RESEARCH_DIR": research_dir} if research_dir else {}),
                }
            },
            "workspace-runner": {
                "image": runner_image,
                "restart": "unless-stopped",
                "user": f"{uid}:{gid}",
                "read_only": True,
                "cap_drop": ["ALL"],
                "security_opt": ["no-new-privileges:true"],
                "environment": {
                    "DOCKER_HOST": "unix:///var/run/docker.sock",
                    "MIZAN_WORKSPACE_RUNNER_TOKEN": token,
                    "MIZAN_WORKSPACE_RUNTIME_IMAGE": runtime_image,
                },
                "volumes": [
                    {
                        "type": "bind",
                        "source": f"/run/user/{uid}/docker.sock",
                        "target": "/var/run/docker.sock",
                        "bind": {"create_host_path": False},
                    }
                ],
                "tmpfs": ["/tmp:size=16m,noexec,nosuid,nodev"],
                "networks": ["mizan-net"],
                # Sessions keep docker exec relays (previews, terminals, MCP stdio) open.
                "pids_limit": 512,
                "logging": {"driver": "local", "options": {"max-size": "10m", "max-file": "3"}},
                "deploy": {"resources": {"limits": {"cpus": "0.5", "memory": "384M", "pids": 512}}},
            },
        }
    }


def validate_job(container: dict) -> None:
    host = container["HostConfig"]
    require(host.get("NetworkMode") == "none", "Job network isolation is missing")
    require(
        host.get("ReadonlyRootfs") and not host.get("Privileged"),
        "Job filesystem/privilege isolation is missing",
    )
    require(
        "ALL" in host.get("CapDrop", [])
        and "no-new-privileges" in " ".join(host.get("SecurityOpt", [])),
        "Job capabilities are not restricted",
    )
    require(not host.get("Binds") and not host.get("Devices"), "Job has host mounts or devices")
    require(
        all(mount.get("Type") == "tmpfs" for mount in container.get("Mounts", [])),
        "Job has a persistent/host mount",
    )
    require(
        host.get("Memory") == 384 * 1024**2 and host.get("MemorySwap") == 384 * 1024**2,
        "Job memory limit is missing",
    )
    require(
        host.get("NanoCpus") == 10**9 and host.get("PidsLimit") == 64,
        "Job CPU/process limit is missing",
    )
    require(
        container["Config"].get("User") == "65534:65534", "Job runs under an unexpected identity"
    )
    keys = {value.partition("=")[0] for value in container["Config"].get("Env", [])}
    require(
        not any(re.search(r"TOKEN|SECRET|PASSWORD|API_KEY", key) for key in keys),
        "Job received a credential variable",
    )


# Sent through docker-exec stdin, not through a shell. It reads its token inside
# the backend/runner container and emits only a fixed success receipt.
SMOKE_SCRIPT = r'''
import base64, json, os, urllib.error, urllib.request
url = os.environ.get("MIZAN_WORKSPACE_RUNNER_URL", "http://127.0.0.1:8080").rstrip("/")
token = os.environ["MIZAN_WORKSPACE_RUNNER_TOKEN"]
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
def request(path, payload=None, authorized=True):
    headers = {"Content-Type": "application/json"}
    if authorized:
        headers["Authorization"] = "Bearer " + token
    body = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(url + path, data=body, headers=headers)
    with opener.open(req, timeout=40) as response:
        return json.loads(response.read(16 * 1024 * 1024 + 1))
try:
    request("/health", authorized=False)
    raise RuntimeError("unauthenticated runner access")
except urllib.error.HTTPError as error:
    assert error.code == 401
health = request("/health")
assert health.get("available") is True and health.get("isolated") is True
def run(language, command, timeout=10):
    return request("/run", {"language": language, "command": command,
        "timeout_s": timeout, "files": {}, "directories": []})
for language, command, expected in [
    ("python", "print(6 * 7)", "42"),
    ("javascript", "console.log(6 * 7)", "42"),
    ("shell", "git --version && printf 'shell works'", "shell works"),
]:
    result = run(language, command)
    assert result["exit_code"] == 0 and expected in result["stdout"]
    assert not result.get("timed_out") and not result.get("export_error")
isolation = run("python", """import os, pathlib, socket
assert not any(any(s in k for s in ('TOKEN', 'SECRET', 'PASSWORD', 'API_KEY')) for k in os.environ)
for name in ('/var/run/docker.sock', '/run/docker.sock', '/data/mizan.db', '/opt/mizan/.env'):
    assert not pathlib.Path(name).exists()
try:
    socket.create_connection(('1.1.1.1', 443), timeout=1)
except OSError:
    pass
else:
    raise AssertionError('unexpected network access')
pathlib.Path('result.txt').write_text('saved')
print('isolated')
""")
assert isolation["exit_code"] == 0 and "isolated" in isolation["stdout"]
assert base64.b64decode(isolation["files"]["result.txt"]) == b"saved"
timeout = run("python", "import time; print('x' * 300000, flush=True); time.sleep(30)", 3)
assert timeout["timed_out"] is True and timeout["exit_code"] == 124
assert timeout["truncated"] is True and len(timeout["stdout"]) <= 100000
escape = run("shell", "ln -s /etc/passwd leak")
assert escape.get("export_error") is True and not escape["files"]
print("workspace: python javascript shell export isolation timeout symlink checks passed")
'''


class Installer:
    def __init__(
        self, sha: str, commands: Commands | None = None, *, research_dir: str | None = None
    ):
        validate_research_option(research_dir)
        self.sha = sha
        self.research_dir = research_dir
        self.commands = commands or Commands()
        self.state: dict = {}
        self.worker: list[str] = []
        self.reported_stages: set[str] = set()
        self.deadline = time.monotonic() + 1800

    def run_command(self, argv: list[str], **kwargs) -> subprocess.CompletedProcess:
        stage = kwargs["stage"]
        if stage not in self.reported_stages:
            report(f"Workspace runner: {stage}.")
            self.reported_stages.add(stage)
        remaining = int(self.deadline - time.monotonic())
        require(remaining > 0, "Setup operation budget exceeded; rollback budget is reserved")
        kwargs["timeout"] = min(kwargs.get("timeout", 60), remaining)
        return self.commands.run(argv, **kwargs)

    def docker_json(self, *args: str, worker: bool = False) -> dict | list:
        docker = self.worker if worker else DOCKER
        return json.loads(self.run_command([*docker, *args], stage="Read daemon metadata").stdout)

    def save(self) -> None:
        protected_write(STATE_ROOT / "state.json", json.dumps(self.state, indent=2) + "\n")

    def compose(self, files: list[str]) -> list[str]:
        command = [*DOCKER, "compose", "--project-directory", str(PROJECT_ROOT), "-p", "mizan"]
        for filename in dict.fromkeys(files):
            command.extend(["-f", filename])
        return command

    def backend(self, *, require_running: bool = True, allow_missing: bool = False) -> dict | None:
        found = self.run_command(
            [*DOCKER, "inspect", "mizan-backend"],
            stage="Inspect production backend identity",
            check=False,
        )
        if found.returncode:
            require(allow_missing, "Production backend cannot be inspected")
            # A successful empty ps distinguishes a missing container from an
            # inaccessible daemon. Do not take over a renamed/unexpected backend.
            related = self.run_command(
                [
                    *DOCKER,
                    "ps",
                    "--all",
                    "--quiet",
                    "--filter",
                    "label=com.docker.compose.project=mizan",
                    "--filter",
                    "label=com.docker.compose.service=backend",
                ],
                stage="Confirm missing backend before rollback",
            )
            require(not related.stdout.strip(), "An unexpected backend container prevents rollback")
            named = self.run_command(
                [*DOCKER, "ps", "--all", "--quiet", "--filter", "name=^/mizan-backend$"],
                stage="Confirm backend name is unused",
            )
            require(not named.stdout.strip(), "Backend name is occupied but cannot be inspected")
            return None
        backend = json.loads(found.stdout)[0]
        expected = self.docker_json("image", "inspect", f"ghcr.io/{REPOSITORY}/backend:{self.sha}")[
            0
        ]
        require(
            backend["Image"] == expected["Id"],
            "Backend changed or expected tested image is not deployed",
        )
        require(
            not require_running or backend["State"]["Running"], "Production backend is not running"
        )
        labels = backend["Config"].get("Labels", {})
        require(labels.get("com.docker.compose.project") == "mizan", "Unexpected Compose project")
        require(
            labels.get("com.docker.compose.project.working_dir") == str(PROJECT_ROOT),
            "Unexpected Compose working directory",
        )
        if require_running:
            require(
                "mizan_mizan-net" in backend["NetworkSettings"]["Networks"],
                "Expected private network missing",
            )
        return backend

    def config_files(self, backend: dict) -> list[str]:
        files = (
            backend["Config"]["Labels"]
            .get("com.docker.compose.project.config_files", "")
            .split(",")
        )
        require(bool(files) and all(files), "Missing Compose ownership labels")
        for filename in files:
            path = Path(filename)
            require(
                path.is_absolute() and path.is_file() and not path.is_symlink(),
                "Invalid Compose configuration path",
            )
            require(
                path.resolve().is_relative_to(PROJECT_ROOT)
                or path.resolve().is_relative_to(DEPLOY_STATE),
                "Compose configuration is outside the reviewed project",
            )
        return list(dict.fromkeys(files))

    def research_location(self, backend: dict, *, configured: bool = False) -> None:
        if self.research_dir is None:
            return
        probe = json.loads(
            self.run_command(
                [*DOCKER, "exec", "mizan-backend", "python3", "-c", RESEARCH_PROBE],
                stage="Check persistent research parent as backend user",
            ).stdout
        )
        validate_research_location(backend, probe, configured=configured)

    def preflight(self, *, recovering: bool = False) -> dict | None:
        require(os.geteuid() == 0, "Installer requires the existing root deployment connection")
        require(
            PROJECT_ROOT.is_dir() and PROJECT_ROOT.resolve() == PROJECT_ROOT,
            "Expected project directory missing",
        )
        info = self.docker_json("info", "--format", "{{json .}}")
        require(
            not any("rootless" in value for value in info.get("SecurityOptions", [])),
            "Unexpected production Docker context",
        )
        require(
            str(info.get("CgroupVersion")) == "2" and info.get("CgroupDriver") == "systemd",
            "Host requires cgroup v2 and systemd",
        )
        require(bool(info.get("ID")), "Production daemon identity unavailable")
        if not recovering:
            available = next(
                (
                    int(line.split()[1]) * 1024
                    for line in Path("/proc/meminfo").read_text().splitlines()
                    if line.startswith("MemAvailable:")
                ),
                0,
            )
            require(
                available >= 3 * 1024**3,
                "Less than 3 GiB host memory is available for a 2 GiB worker",
            )
            require(
                shutil.disk_usage("/var/lib").free >= 4 * 1024**3,
                "Less than 4 GiB disk space is available",
            )
        self.production_id = info["ID"]
        backend = self.backend(require_running=not recovering, allow_missing=recovering)
        if backend is not None:
            self.config_files(backend)
            if not recovering:
                self.research_location(backend)
        if not recovering:
            for binary in (
                "/usr/bin/dockerd-rootless-setuptool.sh",
                "/usr/bin/rootlesskit",
                "/usr/bin/systemctl",
                "/usr/bin/loginctl",
                "/usr/sbin/runuser",
            ):
                require(Path(binary).is_file(), "Required packaged rootless/systemd tool missing")
        return backend

    def load_state(self, *, rollback: bool = False) -> None:
        path = STATE_ROOT / "state.json"
        if path.exists():
            private_directory(STATE_ROOT)
            self.state = read_json(path)
            require(
                self.state.get("manager") == MANAGER and self.state.get("sha") == self.sha,
                "Existing setup belongs to another version; review it first",
            )
            require(
                self.state.get("production_id") == self.production_id,
                "Production daemon identity changed",
            )
            if rollback:
                self.research_dir = self.state.get("research_dir")
                validate_research_option(self.research_dir)
            else:
                require(
                    self.state.get("research_dir") == self.research_dir,
                    "Research option differs from this setup's managed checkpoint",
                )
            return
        try:
            pwd.getpwnam(ACCOUNT)
        except KeyError:
            pass
        else:
            raise SetupError("Refusing to take over a pre-existing service account")
        require(
            not ACCOUNT_HOME.exists() and not ACCOUNT_HOME.is_symlink(),
            "Refusing a pre-existing worker home",
        )
        require(
            not OVERRIDE.exists() and not OVERRIDE.is_symlink(),
            "Refusing a pre-existing runner override",
        )
        existing = self.run_command(
            [
                *DOCKER,
                "ps",
                "--all",
                "--quiet",
                "--filter",
                "label=com.docker.compose.project=mizan",
                "--filter",
                "label=com.docker.compose.service=workspace-runner",
            ],
            stage="Check for unmanaged runner containers",
        ).stdout.strip()
        require(not existing, "Refusing to take over an existing runner service")
        current_config = json.loads(
            self.run_command(
                [*self.compose(self.config_files(self.backend())), "config", "--format", "json"],
                stage="Check for unmanaged runner configuration",
            ).stdout
        )
        require(
            "workspace-runner" not in current_config.get("services", {}),
            "Refusing an existing runner service definition",
        )
        private_directory(STATE_ROOT)
        self.state = {
            "manager": MANAGER,
            "sha": self.sha,
            "production_id": self.production_id,
            "phase": "preparing",
            "account_creation_started": False,
            "research_dir": self.research_dir,
        }
        self.save()

    def install_packages(self) -> None:
        missing = []
        for package in ("uidmap", "slirp4netns"):
            result = self.run_command(
                ["dpkg-query", "-W", "-f=${Status}", package],
                stage="Inspect prerequisite package",
                check=False,
            )
            if result.returncode or result.stdout.strip() != "install ok installed":
                missing.append(package)
        if not missing:
            return
        environment = {"DEBIAN_FRONTEND": "noninteractive", "NEEDRESTART_MODE": "l"}
        self.run_command(
            ["apt-get", "update", "-qq"],
            stage="Update prerequisite package index",
            env=environment,
            timeout=180,
        )
        args = ["apt-get", "--no-install-recommends", "--no-upgrade", "install", *missing]
        plan = self.run_command(
            [*args[:1], "--simulate", *args[1:]],
            stage="Check prerequisite-only package plan",
            env=environment,
        )
        validate_package_plan(plan.stdout)
        self.run_command(
            [*args[:1], "--yes", *args[1:]],
            stage="Install missing rootless prerequisites",
            env=environment,
            timeout=180,
        )

    def account(self):
        try:
            account = pwd.getpwnam(ACCOUNT)
        except KeyError:
            require(not ACCOUNT_HOME.exists(), "Unclaimed worker home exists")
            self.state["account_creation_started"] = True
            self.save()
            self.run_command(
                [
                    "useradd",
                    "--create-home",
                    "--home-dir",
                    str(ACCOUNT_HOME),
                    "--shell",
                    "/usr/sbin/nologin",
                    "--user-group",
                    ACCOUNT,
                ],
                stage="Create locked dedicated service account",
            )
            account = pwd.getpwnam(ACCOUNT)
        require(
            self.state.get("account_creation_started"), "Account was not created by this installer"
        )
        require(
            account.pw_uid >= 1000
            and account.pw_gid > 0
            and account.pw_dir == str(ACCOUNT_HOME)
            and account.pw_shell == "/usr/sbin/nologin",
            "Service-account identity differs from managed settings",
        )
        require(
            self.state.get("uid", account.pw_uid) == account.pw_uid
            and self.state.get("gid", account.pw_gid) == account.pw_gid,
            "Service-account IDs changed",
        )
        require(
            not ACCOUNT_HOME.is_symlink() and ACCOUNT_HOME.stat().st_uid == account.pw_uid,
            "Worker home ownership changed",
        )
        shadow = next(
            (
                line.split(":")[1]
                for line in Path("/etc/shadow").read_text().splitlines()
                if line.startswith(ACCOUNT + ":")
            ),
            "",
        )
        require(shadow.startswith(("!", "*")), "Service-account password must remain locked")
        groups = self.run_command(
            ["id", "-G", ACCOUNT], stage="Verify dedicated account groups"
        ).stdout.split()
        require(
            groups == [str(account.pw_gid)], "Service account has unexpected supplementary groups"
        )
        require(
            not (ACCOUNT_HOME / ".ssh").exists(), "Service account must not have SSH configuration"
        )
        for filename in ("/etc/subuid", "/etc/subgid"):
            validate_subids(Path(filename).read_text(), ACCOUNT)
        os.chmod(ACCOUNT_HOME, 0o700)
        self.state.update(uid=account.pw_uid, gid=account.pw_gid)
        self.save()
        self.worker = [
            "/usr/bin/docker",
            "--host",
            f"unix:///run/user/{account.pw_uid}/docker.sock",
        ]
        return account

    def user_command(self, *args: str, **kwargs) -> subprocess.CompletedProcess:
        uid = self.state["uid"]
        # runuser initializes HOME/USER from passwd; no production environment is inherited.
        return self.run_command(
            [
                "/usr/sbin/runuser",
                "-u",
                ACCOUNT,
                "--",
                "env",
                f"XDG_RUNTIME_DIR=/run/user/{uid}",
                f"DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus",
                *args,
            ],
            **kwargs,
        )

    def setup_daemon(self) -> None:
        uid = self.state["uid"]
        for unit, content in {
            f"user@{uid}.service": "[Service]\nDelegate=cpu cpuset io memory pids\n",
            f"user-{uid}.slice": "[Slice]\nMemoryMax=2G\nMemorySwapMax=0\nCPUQuota=200%\nTasksMax=1024\n",
        }.items():
            directory = Path("/etc/systemd/system") / f"{unit}.d"
            require(not directory.is_symlink(), "Unexpected symlinked systemd drop-in directory")
            directory.mkdir(mode=0o755, exist_ok=True)
            path = directory / "90-mizan-workspace.conf"
            require(
                all(item == path for item in directory.iterdir()),
                "Unexpected pre-existing per-user systemd configuration",
            )
            if path.exists():
                require(
                    path.read_text() == content, "Managed per-user resource settings were changed"
                )
            else:
                protected_write(path, content, mode=0o644)
        config = ACCOUNT_HOME / ".config/docker/daemon.json"
        require(
            not config.exists() and not config.is_symlink(),
            "Unexpected custom worker daemon configuration",
        )
        self.run_command(
            ["systemctl", "daemon-reload"], stage="Load dedicated-user resource limits"
        )
        self.run_command(
            ["loginctl", "enable-linger", ACCOUNT],
            stage="Enable dedicated-user service persistence",
        )
        self.run_command(
            ["systemctl", "start", f"user@{uid}.service"],
            stage="Start dedicated user service manager",
        )
        self.user_command(
            "/usr/bin/dockerd-rootless-setuptool.sh",
            "install",
            "--force",
            stage="Install packaged rootless Docker user service",
            timeout=120,
        )
        self.user_command(
            "systemctl",
            "--user",
            "enable",
            "--now",
            "docker.service",
            stage="Start rootless Docker user service",
        )
        deadline = time.monotonic() + 45
        while True:
            try:
                self.verify_daemon()
                break
            except SetupError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(1)
        self.state["daemon_ready"] = True
        self.save()

    def verify_daemon(self) -> None:
        uid = self.state["uid"]
        socket = Path(f"/run/user/{uid}/docker.sock")
        require(
            socket.exists()
            and stat.S_ISSOCK(socket.stat().st_mode)
            and socket.stat().st_uid == uid,
            "Worker socket ownership or type is invalid",
        )
        require(
            socket.resolve() != ROOT_SOCKET.resolve(),
            "Worker socket resolves to the production socket",
        )
        info = self.docker_json("info", "--format", "{{json .}}", worker=True)
        validate_daemon(info, self.production_id, ACCOUNT_HOME)
        limits = self.run_command(
            [
                "systemctl",
                "show",
                f"user-{uid}.slice",
                "--property=MemoryMax,MemorySwapMax,CPUQuotaPerSecUSec,TasksMax",
                "--no-pager",
            ],
            stage="Verify aggregate worker resource budget",
        ).stdout
        values = dict(line.split("=", 1) for line in limits.splitlines() if "=" in line)
        require(
            values.get("MemoryMax") == str(CAP_BYTES) and values.get("MemorySwapMax") == "0",
            "Aggregate worker memory budget is missing",
        )
        require(
            values.get("CPUQuotaPerSecUSec") == "2s" and values.get("TasksMax") == "1024",
            "Aggregate worker CPU/process budget is missing",
        )
        control = self.run_command(
            [
                "systemctl",
                "show",
                f"user@{uid}.service",
                "--property=DelegateControllers",
                "--value",
            ],
            stage="Verify delegated cgroup controllers",
        ).stdout.split()
        require(
            {"cpu", "cpuset", "io", "memory", "pids"}.issubset(control),
            "Required worker cgroup controllers are not delegated",
        )

    def pull_images(self, registry_token: str) -> None:
        with tempfile.TemporaryDirectory(prefix="registry-", dir=STATE_ROOT) as directory:
            env = {"DOCKER_CONFIG": directory}
            self.run_command(
                [
                    *DOCKER,
                    "login",
                    "ghcr.io",
                    "--username",
                    REPOSITORY.split("/")[0],
                    "--password-stdin",
                ],
                stage="Authenticate private image pulls",
                stdin=registry_token + "\n",
                env=env,
            )
            images = self.state.setdefault("images", {})
            for role, daemon in (("runtime", self.worker), ("runner", DOCKER)):
                source = f"ghcr.io/{REPOSITORY}/workspace-{role}:{self.sha}"
                previous = images.get(role)
                if previous:
                    present = self.run_command(
                        [*daemon, "image", "inspect", previous["id"]],
                        stage="Check previously pinned image",
                        check=False,
                    )
                    if present.returncode == 0:
                        continue
                self.run_command(
                    [*daemon, "pull", source],
                    stage=f"Pull tested workspace {role} image",
                    env=env,
                    timeout=600,
                )
                image = json.loads(
                    self.run_command(
                        [*daemon, "image", "inspect", source],
                        stage=f"Pin workspace {role} image content",
                    ).stdout
                )[0]
                require(
                    bool(re.fullmatch(r"sha256:[a-f0-9]{64}", image["Id"])),
                    "Unexpected pulled image identity",
                )
                require(
                    not previous or previous["id"] == image["Id"],
                    "Registry tag changed since this setup began",
                )
                images[role] = {
                    "id": image["Id"],
                    "source_tag": source,
                    "repo_digests": image.get("RepoDigests", []),
                }
                self.save()

    def token(self) -> str:
        path = STATE_ROOT / "runner-token"
        if not path.exists():
            protected_write(path, secrets.token_urlsafe(48) + "\n")
        info = path.lstat()
        require(
            stat.S_ISREG(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o077,
            "Unsafe runner token file",
        )
        token = path.read_text().strip()
        require(bool(re.fullmatch(r"[A-Za-z0-9_-]{64}", token)), "Invalid managed runner token")
        return token

    def runner_ids(self, files: list[str]) -> list[str]:
        return self.run_command(
            [*self.compose(files), "ps", "--all", "--quiet", "workspace-runner"],
            stage="Inspect managed runner service",
        ).stdout.split()

    def snapshot(self, backend: dict) -> dict:
        files = self.config_files(backend)
        original_override = None
        if OVERRIDE.exists():
            require(
                self.state.get("override_sha256") == digest(OVERRIDE),
                "Runner override changed outside this installer",
            )
            original_override = OVERRIDE.read_text()
        frontend = self.docker_json("inspect", "mizan-frontend")[0]
        directory = Path(tempfile.mkdtemp(prefix="attempt-", dir=STATE_ROOT))
        snapshot = {
            "directory": str(directory),
            "files": files,
            "hashes": {filename: digest(Path(filename)) for filename in files},
            "backend_image": backend["Image"],
            "backend_container_id": backend["Id"],
            "backend_env": dict(
                value.split("=", 1) for value in backend["Config"]["Env"] if "=" in value
            ),
            "backend_mounts": backend["Mounts"],
            "backend_networks": list(backend["NetworkSettings"]["Networks"]),
            "backend_ports": backend["HostConfig"].get("PortBindings") or {},
            "frontend_id": frontend["Id"],
            "override_before": original_override,
        }
        rollback = {
            "services": {
                "backend": {
                    "image": snapshot["backend_image"],
                    "environment": snapshot["backend_env"],
                }
            }
        }
        protected_write(directory / "rollback.yml", compose_document(rollback))
        protected_write(directory / "snapshot.json", json.dumps(snapshot))
        self.state["active_attempt"] = str(directory)
        self.state["backend_switch_started"] = False
        self.state["phase"] = "applying"
        self.save()
        return snapshot

    def verify_runner(self, files: list[str]) -> str:
        ids = self.runner_ids(files)
        require(len(ids) == 1, "Expected exactly one managed runner service")
        container = self.docker_json("inspect", ids[0])[0]
        require(
            container["Image"] == self.state["images"]["runner"]["id"]
            and container["State"]["Running"],
            "Runner image or running state is incorrect",
        )
        environment = dict(
            value.split("=", 1) for value in container["Config"].get("Env", []) if "=" in value
        )
        require(
            environment.get("MIZAN_WORKSPACE_RUNTIME_IMAGE")
            == self.state["images"]["runtime"]["id"],
            "Runner runtime image is not the pinned image",
        )
        require(
            container["Config"].get("User") == f"{self.state['uid']}:{self.state['gid']}",
            "Runner socket identity is incorrect",
        )
        host = container["HostConfig"]
        require(
            host.get("ReadonlyRootfs") and not host.get("Privileged"),
            "Runner root filesystem or privilege settings are incorrect",
        )
        require(
            "ALL" in host.get("CapDrop", [])
            and "no-new-privileges" in " ".join(host.get("SecurityOpt", [])),
            "Runner capabilities are not restricted",
        )
        require(
            not host.get("PortBindings") and not host.get("Devices"),
            "Runner must not expose host ports/devices",
        )
        require(
            host.get("Memory") == 384 * 1024**2
            and host.get("NanoCpus") == 500000000
            and host.get("PidsLimit") == 512,
            "Runner control-service resource limits are missing",
        )
        mounts = [mount for mount in container.get("Mounts", []) if mount.get("Type") != "tmpfs"]
        require(
            len(mounts) == 1
            and mounts[0].get("Source") == f"/run/user/{self.state['uid']}/docker.sock"
            and mounts[0].get("Destination") == "/var/run/docker.sock",
            "Runner has an unexpected host mount",
        )
        require(
            set(container["NetworkSettings"]["Networks"]) == {"mizan_mizan-net"},
            "Runner has an unexpected network",
        )
        return ids[0]

    def health(self) -> None:
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            health = self.run_command(
                [
                    *DOCKER,
                    "exec",
                    "mizan-backend",
                    "curl",
                    "--fail",
                    "--silent",
                    "--max-time",
                    "5",
                    "http://127.0.0.1:8000/api/health",
                ],
                stage="Check production backend health",
                check=False,
            )
            auth = self.run_command(
                [
                    *DOCKER,
                    "exec",
                    "mizan-backend",
                    "curl",
                    "--silent",
                    "--max-time",
                    "5",
                    "--output",
                    "/dev/null",
                    "--write-out",
                    "%{http_code}",
                    "http://127.0.0.1:8000/api/status",
                ],
                stage="Check backend authentication",
                check=False,
            )
            if health.returncode == 0 and auth.returncode == 0 and auth.stdout == "401":
                return
            time.sleep(2)
        raise SetupError("Backend health/authentication did not recover")

    def proxy(self) -> None:
        result = self.run_command(
            [*DOCKER, "inspect", "--format", "{{.State.Running}}", "mizan-nginx"],
            stage="Inspect existing reverse proxy",
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip() == "true":
            self.run_command(
                [*DOCKER, "exec", "mizan-nginx", "nginx", "-t"],
                stage="Validate existing reverse proxy",
            )
            self.run_command(
                [*DOCKER, "exec", "mizan-nginx", "nginx", "-s", "reload"],
                stage="Refresh backend address in existing reverse proxy",
            )

    def public_health(self) -> None:
        self.run_command(
            [
                "curl",
                "--fail",
                "--silent",
                "--connect-timeout",
                "10",
                "--max-time",
                "30",
                "--retry",
                "2",
                "https://mizan.example.com/api/health",
            ],
            stage="Check public health after setup",
            timeout=100,
        )
        result = self.run_command(
            [
                "curl",
                "--silent",
                "--connect-timeout",
                "10",
                "--max-time",
                "30",
                "--output",
                "/dev/null",
                "--write-out",
                "%{http_code}",
                "https://mizan.example.com/api/status",
            ],
            stage="Check public anonymous-auth denial",
        )
        require(result.stdout == "401", "Public authentication denial failed")

    def smoke(self, container: str) -> None:
        self.verify_daemon()
        stop = threading.Event()
        observed, failures = set(), []

        def monitor():
            while not stop.is_set():
                try:
                    result = self.run_command(
                        [
                            *self.worker,
                            "ps",
                            "--quiet",
                            "--filter",
                            "name=^/mizan-workspace-[a-f0-9]{32}$",
                        ],
                        stage="Observe real job isolation",
                    )
                    for identifier in result.stdout.split():
                        if identifier in observed:
                            continue
                        found = self.run_command(
                            [*self.worker, "inspect", identifier],
                            stage="Inspect live job isolation",
                            check=False,
                        )
                        if found.returncode == 0:
                            validate_job(json.loads(found.stdout)[0])
                            observed.add(identifier)
                except (SetupError, KeyError, ValueError):
                    failures.append("Live job isolation check failed")
                    return
                stop.wait(0.15)

        thread = threading.Thread(target=monitor, daemon=True)
        thread.start()
        try:
            self.run_command(
                [*DOCKER, "exec", "-i", container, "python3", "-"],
                stage="Run authenticated real-language and isolation probes",
                stdin=SMOKE_SCRIPT,
                timeout=150,
            )
        finally:
            stop.set()
            thread.join(timeout=65)
        require(
            not thread.is_alive() and observed and not failures,
            "Could not verify live job isolation and limits",
        )
        remaining = self.run_command(
            [*self.worker, "ps", "--all", "--quiet"], stage="Verify job cleanup"
        ).stdout.strip()
        require(not remaining, "Dedicated daemon still has job containers; no cleanup was forced")

    def remove_new_runner(self) -> None:
        """Clean up by verified container identity, never by parsing a failed override."""
        found = self.run_command(
            [
                *DOCKER,
                "ps",
                "--all",
                "--quiet",
                "--filter",
                "label=com.docker.compose.project=mizan",
                "--filter",
                "label=com.docker.compose.service=workspace-runner",
            ],
            stage="Find only the new runner control service",
        ).stdout.split()
        require(len(found) <= 1, "Multiple runner containers require manual cleanup review")
        for identifier in found:
            container = self.docker_json("inspect", identifier)[0]
            labels = container["Config"].get("Labels", {})
            require(
                labels.get("com.docker.compose.project") == "mizan"
                and labels.get("com.docker.compose.service") == "workspace-runner"
                and labels.get("com.docker.compose.project.working_dir") == str(PROJECT_ROOT),
                "Runner cleanup ownership differs from this setup",
            )
            require(
                container["Image"] == self.state["images"]["runner"]["id"]
                and container["Config"].get("User") == f"{self.state['uid']}:{self.state['gid']}",
                "Runner cleanup image or account differs from this setup",
            )
            mounts = [
                mount for mount in container.get("Mounts", []) if mount.get("Type") != "tmpfs"
            ]
            require(
                len(mounts) == 1
                and mounts[0].get("Type") == "bind"
                and mounts[0].get("Source") == f"/run/user/{self.state['uid']}/docker.sock"
                and mounts[0].get("Destination") == "/var/run/docker.sock",
                "Runner cleanup socket differs from this setup",
            )
            require(
                bool(re.fullmatch(r"[a-f0-9]{64}", container["Id"])),
                "Invalid runner cleanup identity",
            )
            self.run_command(
                [*DOCKER, "rm", "--force", container["Id"]],
                stage="Remove only the verified new runner control service",
                timeout=60,
            )

    def rollback(self) -> None:
        self.deadline = time.monotonic() + 600
        attempt = Path(self.state.get("active_attempt", ""))
        require(
            attempt.parent == STATE_ROOT and attempt.name.startswith("attempt-"),
            "No managed rollback snapshot",
        )
        snapshot = read_json(attempt / "snapshot.json")
        # A failed Compose recreation may leave no backend, or one that exited.
        # Validate identity independently of liveness so recovery still works.
        current_backend = self.backend(require_running=False, allow_missing=True)
        expected = self.docker_json("image", "inspect", f"ghcr.io/{REPOSITORY}/backend:{self.sha}")[
            0
        ]
        require(
            expected["Id"] == snapshot["backend_image"],
            "Saved rollback image no longer matches the expected deployed SHA",
        )
        if OVERRIDE.exists():
            require(
                digest(OVERRIDE)
                in {self.state.get("override_sha256"), self.state.get("pending_override_sha256")},
                "Runner override changed; refusing to overwrite it during rollback",
            )
        for filename, checksum in snapshot["hashes"].items():
            if Path(filename) != OVERRIDE:
                require(
                    Path(filename).is_file() and digest(Path(filename)) == checksum,
                    "Original Compose configuration changed; manual review required",
                )
        prior = snapshot["override_before"]
        if prior is None:
            # Restore the original backend before stopping its new control service.
            files = [*snapshot["files"], str(attempt / "rollback.yml")]
        else:
            protected_write(OVERRIDE, prior)
            self.state["override_sha256"] = digest(OVERRIDE)
            files = [*snapshot["files"], str(attempt / "rollback.yml")]
        # Only a literal persisted False proves the switch never began. Legacy
        # or malformed checkpoints retain conservative image/config restoration.
        if self.state.get("backend_switch_started") is False:
            require(
                current_backend is not None
                and current_backend["State"]["Running"]
                and current_backend.get("Id") == snapshot.get("backend_container_id"),
                "Backend changed before the planned switch; preserve state for manual review",
            )
            self.verify_saved_backend(current_backend, snapshot)
            report("Backend switch never began; preserving the original live container.")
        else:
            self.run_command(
                [*self.compose(files), "config", "--quiet"], stage="Validate exact backend rollback"
            )
            rendered = json.loads(
                self.run_command(
                    [*self.compose(files), "config", "--format", "json"],
                    stage="Compare rollback configuration privately",
                ).stdout
            )
            validate_rendered_backend(rendered, snapshot, snapshot["backend_env"])
            self.run_command(
                [
                    *self.compose(files),
                    "up",
                    "-d",
                    "--no-deps",
                    "--no-build",
                    "--pull",
                    "never",
                    "backend",
                ],
                stage="Restore original backend image and configuration",
                timeout=180,
            )
        # Restored application reachability must not depend on runner cleanup,
        # which may be exactly the configuration that failed initial validation.
        self.health()
        restored = self.backend()
        self.verify_saved_backend(restored, snapshot)
        self.proxy()
        self.public_health()
        if prior is None and OVERRIDE.exists():
            self.remove_new_runner()
            OVERRIDE.unlink()
            self.state.pop("override_sha256", None)
        elif prior is not None:
            self.run_command(
                [
                    *self.compose(files),
                    "up",
                    "-d",
                    "--no-deps",
                    "--no-build",
                    "--pull",
                    "never",
                    "workspace-runner",
                ],
                stage="Restore prior managed runner",
                timeout=180,
            )
        self.state["phase"] = "rolled_back"
        self.state.pop("pending_override_sha256", None)
        self.save()
        report("Rollback verified: original backend restored; volumes and worker data retained.")

    @staticmethod
    def verify_saved_backend(restored: dict, snapshot: dict) -> None:
        restored_environment = dict(
            value.split("=", 1) for value in restored["Config"].get("Env", []) if "=" in value
        )
        require(
            restored_environment == snapshot["backend_env"],
            "Restored backend environment differs from the saved snapshot",
        )
        require(
            sorted(restored["Mounts"], key=lambda value: value["Destination"])
            == sorted(snapshot["backend_mounts"], key=lambda value: value["Destination"]),
            "Restored backend data mounts differ from the saved snapshot",
        )
        require(
            set(restored["NetworkSettings"]["Networks"]) == set(snapshot["backend_networks"]),
            "Restored backend networks differ from the saved snapshot",
        )

    def apply(self) -> None:
        backend = self.backend()
        self.research_location(backend)
        snapshot = self.snapshot(backend)
        token = self.token()
        override = workspace_override(
            self.state["uid"],
            self.state["gid"],
            token,
            runtime_image=self.state["images"]["runtime"]["id"],
            runner_image=self.state["images"]["runner"]["id"],
            research_dir=self.research_dir,
        )
        content = compose_document(override)
        self.state["pending_override_sha256"] = hashlib.sha256(content.encode()).hexdigest()
        self.save()
        protected_write(OVERRIDE, content)
        self.state["override_sha256"] = digest(OVERRIDE)
        self.save()
        attempt = Path(snapshot["directory"])
        # This one-time environment/image preservation file is deliberately in
        # deploy state. A future normal release discards it, but keeps OVERRIDE.
        environment = {**snapshot["backend_env"], **override["services"]["backend"]["environment"]}
        current = {
            "services": {
                "backend": {"image": snapshot["backend_image"], "environment": environment}
            }
        }
        protected_write(attempt / "current-backend.yml", compose_document(current))
        files = [*snapshot["files"], str(OVERRIDE), str(attempt / "current-backend.yml")]
        self.run_command(
            [*self.compose(files), "config", "--quiet"],
            stage="Validate scoped runner configuration",
        )
        rendered = json.loads(
            self.run_command(
                [*self.compose(files), "config", "--format", "json"],
                stage="Compare running configuration privately",
            ).stdout
        )
        validate_rendered_backend(rendered, snapshot, environment)
        self.backend()
        self.run_command(
            [
                *self.compose(files),
                "up",
                "-d",
                "--no-deps",
                "--no-build",
                "--pull",
                "never",
                "workspace-runner",
            ],
            stage="Start private control service",
            timeout=180,
        )
        runner = self.verify_runner(files)
        # Do not switch backend configuration until the isolated control service
        # can actually run code. Uvicorn may need a short startup window.
        for attempt_number in range(15):
            health = self.run_command(
                [
                    *DOCKER,
                    "exec",
                    runner,
                    "python3",
                    "-c",
                    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health')",
                ],
                stage="Wait for private control API",
                check=False,
            )
            if health.returncode != 0 and "HTTP Error 401" in health.stderr:
                break
            if attempt_number == 14:
                raise SetupError("Private control API did not start")
            time.sleep(1)
        self.smoke(runner)
        self.backend()
        self.switch_backend(files)
        self.health()
        after = self.backend()
        self.research_location(after, configured=True)
        require(after["Mounts"] == snapshot["backend_mounts"], "Backend data mounts changed")
        require(
            self.docker_json("inspect", "mizan-frontend")[0]["Id"] == snapshot["frontend_id"],
            "Frontend unexpectedly changed",
        )
        self.verify_runner(self.config_files(after))
        self.smoke("mizan-backend")
        self.proxy()
        self.public_health()
        self.state["phase"] = "ready"
        self.state.pop("pending_override_sha256", None)
        self.state["verified_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.save()
        report(
            f"Workspace runner verified for {self.sha}: rootless, resource-limited, authenticated; Python/JS/shell, files, isolation, timeout and cleanup passed."
        )

    def switch_backend(self, files: list[str]) -> None:
        # Save intent before Compose can mutate anything, including partial
        # failures/timeouts. A failed checkpoint must prevent the command.
        missing = object()
        previous = self.state.get("backend_switch_started", missing)
        self.state["backend_switch_started"] = True
        try:
            self.save()
        except BaseException:
            # No backend command has started. Keep immediate recovery on its
            # pre-switch path even if the failed write committed before erroring.
            if previous is missing:
                self.state.pop("backend_switch_started", None)
            else:
                self.state["backend_switch_started"] = previous
            raise
        self.run_command(
            [
                *self.compose(files),
                "up",
                "-d",
                "--no-deps",
                "--no-build",
                "--pull",
                "never",
                "backend",
            ],
            stage="Connect backend to the verified private runner",
            timeout=180,
        )

    def setup(self, registry_token: str) -> None:
        state_path = STATE_ROOT / "state.json"
        recovering = state_path.exists() and read_json(state_path).get("phase") == "applying"
        self.preflight(recovering=recovering)
        self.load_state()
        if self.state.get("phase") == "applying":
            report("Resuming interrupted setup: restoring its saved backend before retry.")
            self.rollback()
            self.deadline = time.monotonic() + 1800
            self.preflight()
        if self.state.get("phase") == "ready":
            self.worker = [
                "/usr/bin/docker",
                "--host",
                f"unix:///run/user/{self.state['uid']}/docker.sock",
            ]
            self.account()
            require(
                OVERRIDE.exists() and digest(OVERRIDE) == self.state.get("override_sha256"),
                "Managed override changed",
            )
            current = self.backend()
            self.research_location(current, configured=True)
            self.verify_runner(self.config_files(current))
            self.smoke("mizan-backend")
            self.health()
            self.public_health()
            report("Existing managed workspace runner reverified; no service replacement needed.")
            return
        report("Provisioning only the dedicated rootless workspace account and daemon.")
        self.install_packages()
        self.account()
        self.setup_daemon()
        self.pull_images(registry_token)
        try:
            self.apply()
        except (SetupError, OSError, ValueError, KeyError) as setup_error:
            if self.state.get("phase") == "applying":
                try:
                    self.rollback()
                except (SetupError, OSError, ValueError, KeyError) as rollback_error:
                    reason = (
                        str(rollback_error)
                        if isinstance(rollback_error, SetupError)
                        else type(rollback_error).__name__
                    )
                    cause = (
                        str(setup_error)
                        if isinstance(setup_error, SetupError)
                        else type(setup_error).__name__
                    )
                    raise SetupError(
                        f"Setup failed: {cause}; automatic rollback could not be verified: {reason}; use the protected snapshot and runbook"
                    ) from None
            raise


@contextlib.contextmanager
def deployment_lock():
    require(os.geteuid() == 0, "Installer requires root")
    if not DEPLOY_STATE.exists():
        DEPLOY_STATE.mkdir(mode=0o700)
    require(
        not DEPLOY_STATE.is_symlink() and DEPLOY_STATE.stat().st_uid == 0,
        "Unsafe deployment state directory",
    )
    descriptor = os.open(
        DEPLOY_STATE / "deploy.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600
    )
    try:
        deadline = time.monotonic() + 600
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                require(
                    time.monotonic() < deadline,
                    "Timed out waiting for the existing deployment lock",
                )
                time.sleep(1)
        yield
    finally:
        os.close(descriptor)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--repository", default=REPOSITORY)
    parser.add_argument("--rollback", action="store_true")
    parser.add_argument(
        "--research-dir",
        choices=[RESEARCH_DIR],
        help="Also persist research configuration during the same backend recreation",
    )
    args = parser.parse_args()

    def interrupted(_signal, _frame):
        raise SetupError("Setup interrupted; resume from the managed checkpoint")

    try:
        validate_target(args.sha, args.repository)
        credential = "" if args.rollback else sys.stdin.readline(8192).rstrip("\r\n")
        require(
            args.rollback or bool(credential) and len(credential) < 8190,
            "Registry credential must arrive on stdin",
        )
        os.umask(0o077)
        for signal_number in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
            signal.signal(signal_number, interrupted)
        with deployment_lock():
            installer = Installer(args.sha, research_dir=args.research_dir)
            if args.rollback:
                installer.preflight(recovering=True)
                installer.load_state(rollback=True)
                installer.rollback()
            else:
                installer.setup(credential)
    except (SetupError, OSError, ValueError, KeyError) as error:
        message = str(error) if isinstance(error, SetupError) else type(error).__name__
        report(f"Workspace runner setup stopped: {message}", error=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
