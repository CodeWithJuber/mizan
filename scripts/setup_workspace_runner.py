#!/usr/bin/env python3
"""Provision only Mizan's dedicated rootless workspace worker on its known host.

No registry is used: the workflow builds each workspace image and sends it as a
`docker save` archive into the private directory it gives as --images-dir, and the image
is loaded into the daemon that runs it. All subprocess output is private; only stage
names and verified, non-secret receipts are printed. Run as root over
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
# Runner limits (memory bytes, nano-CPUs, pids) of the two reviewed override
# generations: the first install, and the one that also serves sessions.
LEGACY_LIMITS = (192 * 1024**2, 500000000, 128)
CURRENT_LIMITS = (384 * 1024**2, 500000000, 512)
JOB_FILTER = "name=^/mizan-workspace-[a-f0-9]{32}$"
SESSION_PREFIX = "mizan-session-"
SESSION_NETWORK = "mizan-session-net-"
SANDBOX_PROXY = "mizan-sandbox-egress"
RUNNER_ENV = {
    "DOCKER_HOST",
    "MIZAN_WORKSPACE_RUNNER_TOKEN",
    "MIZAN_WORKSPACE_RUNTIME_IMAGE",
    "MIZAN_WORKSPACE_BROWSER_IMAGE",
}
IMAGE_TAG = re.compile(
    rf"ghcr\.io/{re.escape(REPOSITORY)}/workspace-(runtime|runner|browser):[a-f0-9]{{40}}"
)
UPGRADE_SECONDS = 900
RESTORE_SECONDS = 600
# The site's public origin, checked after a change. It comes from MIZAN_PUBLIC_URL, which the
# deploy script and the operation workflows pass: no production domain is written here.
PUBLIC_URL = re.compile(r"https://[A-Za-z0-9.-]+(?::[0-9]{1,5})?")
# Exit codes of --upgrade, chosen apart from the shell's and ssh's own (1-2, 255).
NOT_UPGRADED = 75
NOT_VERIFIED = 76


class SetupError(RuntimeError):
    """A safe, deliberately credential-free diagnostic."""


class UpgradeRolledBack(SetupError):
    """The runner was not upgraded; the previous one is in place and verified."""


class UpgradeUnrecovered(SetupError):
    """The runner was not upgraded and the previous one could not be verified."""


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


def public_url() -> str:
    value = os.environ.get("MIZAN_PUBLIC_URL", "").rstrip("/")
    require(
        PUBLIC_URL.fullmatch(value) is not None,
        "Set MIZAN_PUBLIC_URL to the site's https:// origin (docs/runner-setup.md)",
    )
    return value


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


def images_directory_pattern() -> str:
    """Where a workflow may put image archives: its private directory under DEPLOY_STATE."""
    return rf"{re.escape(str(DEPLOY_STATE))}/(release|workspace-setup)\.[A-Za-z0-9]{{8}}"


def image_archive(directory: Path | None, role: str) -> Path | None:
    """The workflow's `docker save` of one workspace image, or None when it sent none."""
    require(
        directory is not None and bool(re.fullmatch(images_directory_pattern(), str(directory))),
        "No private images directory was given",
    )
    info = directory.lstat()
    require(
        stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid() and not info.st_mode & 0o022,
        "Unsafe images directory",
    )
    path = directory / f"workspace-{role}.tar.gz"
    if not path.exists() and not path.is_symlink():
        return None
    info = path.lstat()
    require(
        stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid() and not info.st_mode & 0o022,
        "Unsafe workspace image archive",
    )
    return path


def generation_wanted(
    state: dict, limits: tuple[int, int, int], inputs_digest: str | None, with_browser: bool
) -> bool:
    """False when the installed runner already runs what this commit's images are built from."""
    installed = state.get("images") or {}
    return not (
        inputs_digest
        and state.get("inputs_digest") == inputs_digest
        and limits == CURRENT_LIMITS
        and (installed.get("browser") or not with_browser)
    )


def needed_images(inputs_digest: str | None, with_browser: bool) -> list[str]:
    """The workspace images an --upgrade to this commit would load: the deploy sends only these."""
    path = STATE_ROOT / "state.json"
    if not path.exists() and not path.is_symlink():
        return []
    state = read_json(path)
    if state.get("manager") != MANAGER or state.get("phase") != "ready":
        # No managed runner, or one an upgrade restores or leaves alone without new images.
        return []
    roles = ["runner", "runtime"]
    if (state.get("images") or {}).get("browser") or with_browser:
        roles.append("browser")
    try:
        limits = runner_limits(json.loads(OVERRIDE.read_text()))
    except (SetupError, OSError, ValueError, KeyError, TypeError):
        return roles  # The upgrade itself reports a drifted install.
    return roles if generation_wanted(state, limits, inputs_digest, with_browser) else []


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
    browser_image: str | None = None,
) -> dict:
    validate_research_option(research_dir)
    require(uid >= 1000 and gid > 0, "Worker must use an unprivileged service account")
    require(bool(re.fullmatch(r"[A-Za-z0-9_-]{64}", token)), "Invalid managed runner token")
    pinned = (runtime_image, runner_image, *((browser_image,) if browser_image else ()))
    require(
        all(re.fullmatch(r"sha256:[a-f0-9]{64}", image) for image in pinned),
        "Worker images must be pinned to locally loaded content IDs",
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
                    # Shahid, MIZAN's browser sandbox, when its image was loaded.
                    **({"MIZAN_WORKSPACE_BROWSER_IMAGE": browser_image} if browser_image else {}),
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


def runner_limits(document: dict) -> tuple[int, int, int]:
    """The runner limits an override sets, if they are one reviewed generation's."""
    runner = document["services"]["workspace-runner"]
    limits = runner.get("deploy", {}).get("resources", {}).get("limits", {})
    memory = {"192M": 192 * 1024**2, "384M": 384 * 1024**2}.get(limits.get("memory"))
    try:
        cpus = round(float(limits.get("cpus", "0")) * 10**9)
    except (TypeError, ValueError):
        cpus = 0
    found = (memory, cpus, runner.get("pids_limit"))
    require(
        found in (LEGACY_LIMITS, CURRENT_LIMITS),
        "Runner override limits are not a reviewed generation",
    )
    return found  # type: ignore[return-value]


def validate_override_transition(old: dict, new: dict, token: str) -> None:
    """An upgrade may change only the runner's images, limits and browser setting."""
    for document in (old, new):
        services = document.get("services", {})
        require(
            set(document) == {"services"} and set(services) == {"backend", "workspace-runner"},
            "Runner override holds services other than the backend and runner",
        )
        runner_environment = services["workspace-runner"].get("environment", {})
        require(
            services["backend"].get("environment", {}).get("MIZAN_WORKSPACE_RUNNER_TOKEN") == token
            and runner_environment.get("MIZAN_WORKSPACE_RUNNER_TOKEN") == token,
            "Runner override token differs from the managed token",
        )
        require(
            set(runner_environment) <= RUNNER_ENV,
            "Runner override has an unexpected runner environment",
        )
    require(
        old["services"]["backend"] == new["services"]["backend"],
        "An upgrade must not change the backend's configuration",
    )
    runners = [document["services"]["workspace-runner"] for document in (old, new)]
    fixed = (
        "restart",
        "user",
        "read_only",
        "cap_drop",
        "security_opt",
        "volumes",
        "tmpfs",
        "networks",
        "logging",
    )
    require(
        all(runners[0].get(key) == runners[1].get(key) for key in fixed),
        "An upgrade must not change the runner's identity, mounts or network",
    )


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


def session_limits(limits: dict) -> tuple[int, int, int]:
    """The runner's reported session budget as Docker inspect numbers."""
    memory = re.fullmatch(r"([1-9][0-9]{0,5})([kmg])", str(limits.get("memory", "")).lower())
    require(bool(memory), "Runner reported an unreadable session memory limit")
    try:
        cpus = round(float(limits.get("cpus", "")) * 10**9)
        pids = int(limits.get("pids", ""))
    except (TypeError, ValueError):
        raise SetupError("Runner reported unreadable session limits") from None
    unit = 1024 ** ("kmg".index(memory[2]) + 1)  # type: ignore[index]
    return int(memory[1]) * unit, cpus, pids  # type: ignore[index]


def validate_session_container(container: dict, key: str, limits: tuple[int, int, int]) -> None:
    host, config = container["HostConfig"], container["Config"]
    require(container.get("Name") == f"/{SESSION_PREFIX}{key}", "Unexpected session container")
    require(config.get("User") == "65534:65534", "Session runs under an unexpected identity")
    require(
        host.get("ReadonlyRootfs") and not host.get("Privileged"),
        "Session filesystem/privilege isolation is missing",
    )
    require(
        "ALL" in (host.get("CapDrop") or [])
        and "no-new-privileges" in " ".join(host.get("SecurityOpt") or []),
        "Session capabilities are not restricted",
    )
    require(
        host.get("NetworkMode") == SESSION_NETWORK + key,
        "Session is not on its own internal network",
    )
    memory, cpus, pids = limits
    require(
        host.get("Memory") == memory
        and host.get("MemorySwap") == memory
        and host.get("NanoCpus") == cpus
        and host.get("PidsLimit") == pids,
        "Session resource limits differ from the runner's budget",
    )
    require(
        not host.get("Binds") and not host.get("Devices") and not host.get("PortBindings"),
        "Session has host mounts, devices or ports",
    )
    mounts = [mount for mount in container.get("Mounts", []) if mount.get("Type") != "tmpfs"]
    require(
        len(mounts) == 1
        and mounts[0].get("Type") == "volume"
        and mounts[0].get("Name") == SESSION_PREFIX + key
        and mounts[0].get("Destination") == "/workspace",
        "Session has a mount other than its own volume",
    )
    environment = dict(value.split("=", 1) for value in config.get("Env", []) if "=" in value)
    require(
        not any(re.search(r"TOKEN|SECRET|PASSWORD|API_KEY", name) for name in environment),
        "Session received a credential variable",
    )
    require(
        environment.get("HTTPS_PROXY") == "http://egress:3128",
        "Session egress does not go through the allowlist proxy",
    )
    labels = config.get("Labels") or {}
    require(
        labels.get("mizan.session") == key and labels.get("mizan.egress") == "allowlist",
        "Session labels differ from the runner's",
    )


def validate_session_network(network: dict, key: str, members: set[str]) -> None:
    require(
        network.get("Name") == SESSION_NETWORK + key and network.get("Internal") is True,
        "Session network is not internal",
    )
    require(
        set(network.get("Containers") or {}) == members,
        "Session network holds containers other than the session and its proxy",
    )


def validate_egress_proxy(container: dict, runtime_images: set[str]) -> None:
    host, config = container["HostConfig"], container["Config"]
    require(container.get("Image") in runtime_images, "Egress proxy runs an unexpected image")
    require(config.get("User") == "65534:65534", "Egress proxy runs under an unexpected identity")
    require(
        host.get("ReadonlyRootfs")
        and not host.get("Privileged")
        and "ALL" in (host.get("CapDrop") or [])
        and "no-new-privileges" in " ".join(host.get("SecurityOpt") or []),
        "Egress proxy isolation is missing",
    )
    require(
        host.get("Memory") == 128 * 1024**2
        and not host.get("Binds")
        and not host.get("Devices")
        and not host.get("PortBindings")
        and not [m for m in container.get("Mounts", []) if m.get("Type") != "tmpfs"],
        "Egress proxy has host access or no memory limit",
    )
    keys = {value.partition("=")[0] for value in config.get("Env", [])}
    require(
        not any(re.search(r"TOKEN|SECRET|PASSWORD|API_KEY", key) for key in keys),
        "Egress proxy received a credential variable",
    )
    require(
        (config.get("Labels") or {}).get("mizan.egress") == "proxy",
        "Egress proxy labels differ from the runner's",
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

# Sandbox sessions, run in the backend as ``python3 - <phase> <key> <nonce>``.
# Phases: check (runner answers sessions), start, probe (files, npm, PyPI,
# confinement) and stop. It prints only a JSON verdict naming a fixed step.
SESSION_SMOKE_SCRIPT = r'''
import hashlib, json, os, sys, urllib.error, urllib.request
phase, key, nonce = sys.argv[1:4]
url = os.environ["MIZAN_WORKSPACE_RUNNER_URL"].rstrip("/")
token = os.environ["MIZAN_WORKSPACE_RUNNER_TOKEN"]
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
PYPI = """import urllib.request
with urllib.request.urlopen('https://pypi.org/simple/pip/', timeout=30) as response:
    assert response.status == 200
print('pypi')
"""
CONFINED = """import os, pathlib, socket, urllib.request
assert not any(s in k for k in os.environ for s in ('TOKEN', 'SECRET', 'PASSWORD', 'API_KEY'))
for name in ('/var/run/docker.sock', '/run/docker.sock'):
    assert not pathlib.Path(name).exists()
for address in ('https://example.com/', 'https://169.254.169.254/'):
    try:
        urllib.request.urlopen(address, timeout=15)
    except Exception as error:
        assert '403' in str(error), 'not refused by the proxy'
    else:
        raise AssertionError('reached a host off the allowlist')
try:
    socket.create_connection(('1.1.1.1', 443), timeout=3)
except OSError:
    pass
else:
    raise AssertionError('direct network access')
print('egress-confined')
"""
class Failed(Exception):
    pass
def call(method, path, payload=None, timeout=60):
    body = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(url + path, data=body, method=method, headers={
        "Authorization": "Bearer " + token, "Content-Type": "application/json"})
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status, json.loads(response.read(8 * 1024 * 1024) or b"{}"), True
    except urllib.error.HTTPError as error:
        return error.code, {}, error.headers.get("X-Mizan-Runner") == "error"
def expect(step, condition, status=0):
    if not condition:
        raise Failed(step, status)
def run(step, command, language="shell", timeout=120):
    status, reply, _ = call("POST", session + "/exec", {
        "command": command, "language": language, "timeout_s": timeout}, timeout + 60)
    expect(step, status == 200 and reply.get("exit_code") == 0, status)
    return reply.get("stdout", "")
session = "/sessions/" + key
verdict = {"ok": True}
try:
    if phase in ("check", "start"):
        status, health, _ = call("GET", "/health")
        expect("health", status == 200 and health.get("available") is True, status)
        status, info, ours = call("GET", session)
        expect("predates" if status == 404 and not ours else "status",
               status == 200 and info.get("running") is False
               and isinstance(info.get("limits"), dict), status)
    if phase == "start":
        for kind in ("workspace", "mcp"):
            status, started, _ = call("PUT", session, {
                "nonce": nonce, "kind": kind, "preview_prefix": ""}, 120)
            if status != 429:
                break
        expect("busy" if status == 429 else "start", status == 200, status)
        expect("started", started.get("running") is True and started.get("egress") is True
               and started.get("nonce") == nonce)
        status, info, _ = call("GET", session)
        expect("started", status == 200 and info.get("running") is True
               and info.get("nonce") == nonce and info.get("kind") == kind, status)
        verdict.update(kind=kind, limits={
            name: str(info["limits"].get(name, "")) for name in ("memory", "cpus", "pids")})
    elif phase == "probe":
        status, reply, _ = call("POST", session + "/sync", {
            "files": {"mizan-smoke.txt": "b2s="}, "directories": [], "delete": []})
        expect("sync", status == 200 and reply.get("written") == 1, status)
        status, reply, _ = call("POST", session + "/manifest", {})
        expect("manifest", status == 200 and (reply.get("files") or {}).get("mizan-smoke.txt")
               == hashlib.sha256(b"ok").hexdigest(), status)
        npm = run("npm", "npm view left-pad@1.3.0 version --fetch-retries=2")
        expect("npm", npm.strip() == "1.3.0")
        expect("pypi", "pypi" in run("pypi", PYPI, "python", 60))
        expect("confined", "egress-confined" in run("confined", CONFINED, "python", 60))
    elif phase == "stop":
        status, reply, _ = call("DELETE", session, timeout=90)
        expect("stop", status == 200 and reply.get("running") is False, status)
        status, info, _ = call("GET", session)
        expect("stop", status == 200 and info.get("running") is False, status)
except Failed as failure:
    verdict = {"ok": False, "step": failure.args[0], "status": failure.args[1]}
except Exception:
    verdict = {"ok": False, "step": "error", "status": 0}
print(json.dumps(verdict))
'''
SESSION_STEPS = {
    "health": "the runner's health check failed",
    "predates": "the runner predates sandbox sessions",
    "status": "the session status request failed",
    "busy": "all sandbox sessions are busy",
    "start": "the session did not start",
    "started": "the session did not report running with allowlisted egress",
    "sync": "copying a file into the session failed",
    "manifest": "the session's file manifest differs from what was written",
    "npm": "the npm registry was not reachable through the egress proxy",
    "pypi": "PyPI was not reachable through the egress proxy",
    "confined": "the session reached a host or credential it must not",
    "stop": "the session did not stop",
    "error": "the probe could not reach the runner",
}


class Installer:
    def __init__(
        self,
        sha: str,
        commands: Commands | None = None,
        *,
        research_dir: str | None = None,
        images_dir: Path | None = None,
    ):
        validate_research_option(research_dir)
        self.sha = sha
        self.research_dir = research_dir
        # Where the workflow put this commit's workspace image archives (--images-dir).
        self.images_dir = images_dir
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

    def load_image(self, role: str, daemon: list[str], *, optional: bool) -> dict | None:
        """Load the workflow's archive of one workspace image into the daemon that runs it."""
        source = f"ghcr.io/{REPOSITORY}/workspace-{role}:{self.sha}"
        archive = image_archive(self.images_dir, role)
        if archive is None:
            require(optional, f"The deploy sent no workspace {role} image for this commit")
            report("Workspace runner: browser image not available; Shahid stays off.")
            return None
        try:
            loaded = self.run_command(
                [*daemon, "load", "--quiet", "--input", str(archive)],
                stage=f"Load tested workspace {role} image",
                timeout=900 if role == "browser" else 600,
                check=not optional,
            )
        except SetupError:
            if not optional:
                raise
            loaded = subprocess.CompletedProcess([], 1, "", "")
        if loaded.returncode:
            report("Workspace runner: browser image not available; Shahid stays off.")
            return None
        # Only this commit's image may arrive: the archive must not tag anything else here.
        names = [line for line in loaded.stdout.splitlines() if line.startswith("Loaded image")]
        require(names == [f"Loaded image: {source}"], "The archive held another image")
        image = json.loads(
            self.run_command(
                [*daemon, "image", "inspect", source],
                stage=f"Pin workspace {role} image content",
            ).stdout
        )[0]
        require(
            bool(re.fullmatch(r"sha256:[a-f0-9]{64}", image["Id"])),
            "Unexpected loaded image identity",
        )
        return {
            "id": image["Id"],
            "source_tag": source,
            "repo_digests": image.get("RepoDigests", []),
        }

    def load_images(self) -> None:
        images = self.state.setdefault("images", {})
        roles = (("runtime", self.worker), ("runner", DOCKER), ("browser", self.worker))
        for role, daemon in roles:
            previous = images.get(role)
            if previous:
                present = self.run_command(
                    [*daemon, "image", "inspect", previous["id"]],
                    stage="Check previously pinned image",
                    check=False,
                )
                if present.returncode == 0:
                    continue
            # Optional: without its image MIZAN reads pages but has no browser.
            image = self.load_image(role, daemon, optional=role == "browser")
            if image is None:
                continue
            require(
                not previous or previous["id"] == image["id"],
                "This commit's image changed since this setup began",
            )
            images[role] = image
            self.save()

    def token(self, *, create: bool = True) -> str:
        path = STATE_ROOT / "runner-token"
        if not path.exists():
            # An upgrade keeps the backend's token; a new one would lock it out.
            require(create, "Managed runner token is missing")
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

    def verify_runner(
        self,
        files: list[str],
        *,
        images: dict | None = None,
        limits: tuple[int, int, int] = CURRENT_LIMITS,
    ) -> str:
        images = images or self.state["images"]
        ids = self.runner_ids(files)
        require(len(ids) == 1, "Expected exactly one managed runner service")
        container = self.docker_json("inspect", ids[0])[0]
        require(
            container["Image"] == images["runner"]["id"] and container["State"]["Running"],
            "Runner image or running state is incorrect",
        )
        environment = dict(
            value.split("=", 1) for value in container["Config"].get("Env", []) if "=" in value
        )
        require(
            environment.get("MIZAN_WORKSPACE_RUNTIME_IMAGE") == images["runtime"]["id"],
            "Runner runtime image is not the pinned image",
        )
        require(
            environment.get("MIZAN_WORKSPACE_BROWSER_IMAGE")
            == (images.get("browser") or {}).get("id"),
            "Runner browser image is not the pinned image",
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
            (host.get("Memory"), host.get("NanoCpus"), host.get("PidsLimit")) == limits,
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
                f"{public_url()}/api/health",
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
                f"{public_url()}/api/status",
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
        # Only one-shot jobs end with the smoke: sessions and their egress proxy
        # live on the same daemon. The runner removes a job just after it answers.
        deadline = time.monotonic() + 30
        while self.run_command(
            [*self.worker, "ps", "--all", "--quiet", "--filter", JOB_FILTER],
            stage="Verify job cleanup",
        ).stdout.strip():
            require(
                time.monotonic() < deadline,
                "Dedicated daemon still has job containers; no cleanup was forced",
            )
            time.sleep(1)

    def wait_for_control_api(self, runner: str) -> None:
        # Uvicorn may need a short startup window; 401 without a token means it answers.
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
                return
            if attempt_number == 14:
                raise SetupError("Private control API did not start")
            time.sleep(1)

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
        require(
            not self.state.get("last_upgrade"),
            "A deploy upgraded this runner since setup; the setup snapshot no longer applies "
            "(see docs/runbook.md, workspace runner)",
        )
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
            browser_image=(self.state["images"].get("browser") or {}).get("id"),
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
        # can actually run code.
        self.wait_for_control_api(runner)
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

    def setup(self) -> None:
        state_path = STATE_ROOT / "state.json"
        recovering = state_path.exists() and read_json(state_path).get("phase") == "applying"
        self.preflight(recovering=recovering)
        self.load_state()
        require(
            self.state.get("phase") != "upgrading",
            "A runner upgrade was interrupted; the next deploy restores the previous runner",
        )
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
            limits = runner_limits(json.loads(OVERRIDE.read_text()))
            self.verify_runner(self.config_files(current), limits=limits)
            self.smoke("mizan-backend")
            self.health()
            self.public_health()
            report("Existing managed workspace runner reverified; no service replacement needed.")
            return
        report("Provisioning only the dedicated rootless workspace account and daemon.")
        self.install_packages()
        self.account()
        self.setup_daemon()
        self.load_images()
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


def error_text(error: BaseException) -> str:
    return str(error) if isinstance(error, SetupError) else type(error).__name__


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class Upgrade(Installer):
    """Move the managed runner to the deployed commit's images, or keep the previous one.

    deploy_production.sh runs this after the new backend is live, under its own
    deploy.lock. Only the workspace-runner service, its override and its images
    change; the account, daemon, systemd limits, backend and frontend are
    verified, never edited. After the switch the runner must pass the one-shot
    smoke and a real sandbox session (files, npm, PyPI, confinement); anything
    less restores the previous override and verifies the previous runner.
    """

    def __init__(
        self,
        sha: str,
        commands: Commands | None = None,
        *,
        inputs_digest: str | None = None,
        with_browser: bool = False,
        images_dir: Path | None = None,
    ):
        super().__init__(sha, commands, images_dir=images_dir)
        self.inputs_digest = inputs_digest
        self.with_browser = with_browser
        self.deadline = time.monotonic() + UPGRADE_SECONDS
        # True once the installed runner verified, before anything changed.
        self.verified = False
        self.pending_override = STATE_ROOT / "override.pending"
        # The override before the last upgrade: what a failed one is restored to.
        self.previous_override = STATE_ROOT / "override.previous"

    def run(self) -> str:
        """``absent``, ``current`` or ``upgraded``; otherwise UpgradeRolledBack/Unrecovered."""
        path = STATE_ROOT / "state.json"
        if not path.exists() and not path.is_symlink():
            report("Workspace runner: no managed runner on this host; nothing to upgrade.")
            return "absent"
        try:
            return self.upgrade()
        except (UpgradeRolledBack, UpgradeUnrecovered):
            raise
        except (SetupError, OSError, ValueError, KeyError) as error:
            cause = error_text(error)
            self.discard_loaded()
            if self.verified:
                raise UpgradeRolledBack(
                    f"Runner not upgraded: {cause}; the previous runner was kept and verified"
                ) from None
            raise UpgradeUnrecovered(
                f"Runner not upgraded: {cause}; the installed runner was not verified"
            ) from None

    def upgrade(self) -> str:
        private_directory(STATE_ROOT)
        self.state = read_json(STATE_ROOT / "state.json")
        require(self.state.get("manager") == MANAGER, "Runner state belongs to another installer")
        phase = self.state.get("phase")
        if phase in ("preparing", "rolled_back"):
            report("Workspace runner: its setup never completed here; nothing to upgrade.")
            return "absent"
        require(phase != "applying", "An interrupted setup is pending; see docs/runner-setup.md")
        require(phase in ("ready", "upgrading"), "Unknown runner state")
        self.preflight(recovering=True)
        require(
            self.state.get("production_id") == self.production_id,
            "Production daemon identity changed",
        )
        self.research_dir = self.state.get("research_dir")
        validate_research_option(self.research_dir)
        try:
            pwd.getpwnam(ACCOUNT)
        except KeyError:
            raise SetupError("The managed service account is missing") from None
        self.account()
        self.verify_daemon()
        files = self.config_files(self.backend())
        require(str(OVERRIDE) in files, "The backend no longer uses the managed runner override")
        if phase == "upgrading":
            report("Workspace runner: an earlier upgrade was interrupted; restoring its runner.")
            try:
                self.restore_previous(files)
            except (SetupError, OSError, ValueError, KeyError) as error:
                raise UpgradeUnrecovered(
                    f"Restoring the runner after an interrupted upgrade was not verified: "
                    f"{error_text(error)}"
                ) from None
            raise UpgradeRolledBack(
                "An interrupted upgrade was restored and verified; this deploy did not upgrade"
            )
        self.discard_loaded()
        require(
            OVERRIDE.is_file()
            and not OVERRIDE.is_symlink()
            and digest(OVERRIDE) == self.state.get("override_sha256"),
            "Runner override changed outside the installer",
        )
        old_document = json.loads(OVERRIDE.read_text())
        old_limits = runner_limits(old_document)
        old_images = self.state["images"]
        self.verify_runner(files, images=old_images, limits=old_limits)
        self.verified = True
        if not generation_wanted(self.state, old_limits, self.inputs_digest, self.with_browser):
            self.session_phase("check", secrets.token_hex(16), secrets.token_hex(16))
            report(
                f"Workspace runner current ({self.state.get('sha', '')[:12]}): its inputs did "
                "not change; health and sessions answered."
            )
            return "current"
        self.prune_previous()
        browser = bool(old_images.get("browser")) or self.with_browser
        require(
            shutil.disk_usage("/var/lib").free >= (6 if browser else 4) * 1024**3,
            "Not enough free disk for the new runner images",
        )
        new_images = self.load_generation(
            browser=browser, browser_required=bool(old_images.get("browser"))
        )
        token = self.token(create=False)
        new_document = workspace_override(
            self.state["uid"],
            self.state["gid"],
            token,
            runtime_image=new_images["runtime"]["id"],
            runner_image=new_images["runner"]["id"],
            research_dir=self.research_dir,
            browser_image=(new_images.get("browser") or {}).get("id"),
        )
        validate_override_transition(old_document, new_document, token)
        content = compose_document(new_document)
        protected_write(self.pending_override, content)
        pending = [str(self.pending_override) if name == str(OVERRIDE) else name for name in files]
        self.run_command(
            [*self.compose(pending), "config", "--quiet"],
            stage="Validate the upgraded runner configuration",
        )
        self.switch(files, content, new_images)
        previous_sha = self.state.get("sha")
        self.state.update(
            sha=self.sha,
            images=new_images,
            previous_images=old_images,
            inputs_digest=self.inputs_digest,
            phase="ready",
            override_sha256=digest(OVERRIDE),
            verified_at=now(),
            last_upgrade={"result": "upgraded", "from": previous_sha, "to": self.sha, "at": now()},
        )
        self.state.pop("upgrade", None)
        self.state.pop("pending_override_sha256", None)
        self.save()
        self.pending_override.unlink(missing_ok=True)
        report(
            f"Workspace runner upgraded to {self.sha}: sandbox sessions, npm and PyPI egress, "
            "confinement and one-shot isolation verified."
        )
        return "upgraded"

    def switch(self, files: list[str], content: str, new_images: dict) -> None:
        previous = OVERRIDE.read_text()
        protected_write(self.previous_override, previous)
        # The intent is durable before the live override changes: an interrupted
        # run is restored from this checkpoint by the next deploy.
        self.state["upgrade"].update(
            stage="switching",
            previous_override_sha256=hashlib.sha256(previous.encode()).hexdigest(),
        )
        self.state["pending_override_sha256"] = hashlib.sha256(content.encode()).hexdigest()
        self.state["phase"] = "upgrading"
        self.save()
        try:
            protected_write(OVERRIDE, content)
            self.up_runner(files, "Start the upgraded private runner")
            runner = self.verify_runner(files, images=new_images, limits=CURRENT_LIMITS)
            self.wait_for_control_api(runner)
            self.smoke("mizan-backend")
            runtime = new_images["runtime"]["id"]
            proxies = {runtime}
            if not self.retire_proxy(keep=runtime):
                proxies.add(self.state["images"]["runtime"]["id"])
            self.session_smoke({runtime}, proxies)
            self.health()
            self.public_health()
        except (SetupError, OSError, ValueError, KeyError) as error:
            cause = error_text(error)
            report(f"Workspace runner upgrade failed: {cause}; restoring the previous runner.")
            try:
                self.restore_previous(files)
            except (SetupError, OSError, ValueError, KeyError) as restore_error:
                raise UpgradeUnrecovered(
                    f"Runner upgrade failed ({cause}); restoring the previous runner was not "
                    f"verified ({error_text(restore_error)}); the next deploy retries the restore"
                ) from None
            raise UpgradeRolledBack(
                f"Runner upgrade failed ({cause}); the previous runner was restored and verified"
            ) from None

    def restore_previous(self, files: list[str]) -> None:
        self.deadline = time.monotonic() + RESTORE_SECONDS
        upgrade = self.state.get("upgrade") or {}
        if upgrade.get("smoke_key"):
            self.remove_smoke_session(upgrade["smoke_key"])
        require(
            self.previous_override.is_file() and not self.previous_override.is_symlink(),
            "The saved previous runner override is missing",
        )
        previous = self.previous_override.read_text()
        saved = upgrade.get("previous_override_sha256")
        require(
            hashlib.sha256(previous.encode()).hexdigest() == saved,
            "The saved previous runner override changed",
        )
        if OVERRIDE.exists() or OVERRIDE.is_symlink():
            require(
                not OVERRIDE.is_symlink()
                and digest(OVERRIDE) in {saved, self.state.get("pending_override_sha256")},
                "Runner override changed during the upgrade; refusing to overwrite it",
            )
        protected_write(OVERRIDE, previous)
        self.state["override_sha256"] = digest(OVERRIDE)
        self.save()
        self.up_runner(files, "Restore the previous private runner")
        runner = self.verify_runner(
            files, images=self.state["images"], limits=runner_limits(json.loads(previous))
        )
        self.wait_for_control_api(runner)
        self.smoke("mizan-backend")
        self.retire_proxy(keep=self.state["images"]["runtime"]["id"])
        self.discard_generation(upgrade.get("images") or {})
        self.state["phase"] = "ready"
        self.state.pop("upgrade", None)
        self.state.pop("pending_override_sha256", None)
        self.state["last_upgrade"] = {"result": "rolled_back", "to": self.sha, "at": now()}
        self.save()
        self.pending_override.unlink(missing_ok=True)
        report("Workspace runner: previous runner restored; one-shot runs and isolation verified.")

    def up_runner(self, files: list[str], stage: str) -> None:
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
            stage=stage,
            timeout=180,
        )

    def load_generation(self, *, browser: bool, browser_required: bool) -> dict:
        images: dict = {}
        self.state["upgrade"] = {"stage": "loading", "sha": self.sha, "images": images}
        self.save()
        roles = [("runner", DOCKER), ("runtime", self.worker)]
        if browser:
            roles.append(("browser", self.worker))
        for role, daemon in roles:
            optional = role == "browser" and not browser_required
            image = self.load_image(role, daemon, optional=optional)
            if image is not None:
                images[role] = image
                self.save()
        self.state["upgrade"]["stage"] = "loaded"
        self.save()
        return images

    def kept_ids(self) -> set[str]:
        return {
            item["id"]
            for generation in (self.state.get("images"), self.state.get("previous_images"))
            for item in (generation or {}).values()
        }

    def discard_generation(self, images: dict, *, keep: set[str] | None = None) -> None:
        """Remove a generation's images by their recorded tags; never one still kept."""
        keep = self.kept_ids() if keep is None else keep
        for role, item in images.items():
            if item.get("id") in keep:
                continue
            tag = item.get("source_tag", "")
            require(bool(IMAGE_TAG.fullmatch(tag)), "Recorded runner image tag is not reviewed")
            daemon = DOCKER if role == "runner" else self.worker
            found = self.run_command(
                [*daemon, "image", "inspect", "--format", "{{.Id}}", tag],
                stage="Check a runner image before removing it",
                check=False,
            )
            if found.returncode or found.stdout.strip() != item.get("id"):
                continue  # Gone already, or the tag names another image now.
            removed = self.run_command(
                [*daemon, "image", "rm", tag],
                stage="Remove an unused runner image generation",
                check=False,
            )
            if removed.returncode:
                report(f"Workspace runner: the {role} image {tag} is still in use; kept.")

    def prune_previous(self) -> None:
        """Before a load, drop the generation older than the installed one (two stay)."""
        previous = self.state.get("previous_images")
        if not previous:
            return
        installed = {item["id"] for item in self.state["images"].values()}
        self.discard_generation(previous, keep=installed)
        self.state.pop("previous_images")
        self.save()

    def discard_loaded(self) -> None:
        """Images loaded by a run that stopped before the switch are not kept."""
        upgrade = self.state.get("upgrade")
        if not upgrade or self.state.get("phase") != "ready" or not self.worker:
            return
        try:
            self.discard_generation(upgrade.get("images") or {})
        except (SetupError, OSError, ValueError, KeyError):
            report("Workspace runner: unused loaded images could not be removed; kept.")
        self.state.pop("upgrade", None)
        with contextlib.suppress(SetupError, OSError):
            self.save()
        with contextlib.suppress(OSError):
            self.pending_override.unlink(missing_ok=True)

    def retire_proxy(self, *, keep: str) -> bool:
        """Remove an idle egress proxy running another image; the runner recreates it."""
        found = self.run_command(
            [*self.worker, "inspect", "--type", "container", SANDBOX_PROXY],
            stage="Inspect the sandbox egress proxy",
            check=False,
        )
        if found.returncode:
            return True
        proxy = json.loads(found.stdout)[0]
        if proxy.get("Image") == keep:
            return True
        require(
            (proxy["Config"].get("Labels") or {}).get("mizan.egress") == "proxy"
            and bool(re.fullmatch(r"[a-f0-9]{64}", proxy.get("Id", ""))),
            "An unmanaged container holds the egress proxy's name",
        )
        if self.run_command(
            [*self.worker, "ps", "--quiet", "--filter", "label=mizan.session"],
            stage="Check for open sandbox sessions",
        ).stdout.split():
            report("Workspace runner: sessions are open; their egress proxy keeps its image.")
            return False
        self.run_command(
            [*self.worker, "rm", "--force", proxy["Id"]],
            stage="Replace the idle sandbox egress proxy",
        )
        return True

    def session_phase(self, phase: str, key: str, nonce: str) -> dict:
        result = self.run_command(
            [*DOCKER, "exec", "-i", "mizan-backend", "python3", "-", phase, key, nonce],
            stage=f"Sandbox session check: {phase}",
            stdin=SESSION_SMOKE_SCRIPT,
            timeout=540 if phase == "probe" else 200,
            check=False,
        )
        try:
            verdict = json.loads(result.stdout.strip().splitlines()[-1])
        except (IndexError, ValueError):
            verdict = None
        if not isinstance(verdict, dict):
            verdict = {}
        if verdict.get("ok") is True and result.returncode == 0:
            return verdict
        message = SESSION_STEPS.get(str(verdict.get("step")), "the session check gave no verdict")
        status = verdict.get("status")
        suffix = f" (HTTP {status})" if isinstance(status, int) and status else ""
        raise SetupError(f"Sandbox sessions: {message}{suffix}")

    def session_smoke(self, runtimes: set[str], proxies: set[str]) -> None:
        """A real session: confinement checked from outside, files and egress from inside."""
        key, nonce = secrets.token_hex(16), secrets.token_hex(16)
        self.state["upgrade"]["smoke_key"] = key
        self.save()
        try:
            started = self.session_phase("start", key, nonce)
            (container,) = self.docker_json(
                "inspect", "--type", "container", SESSION_PREFIX + key, worker=True
            )
            require(container.get("Image") in runtimes, "Session runs an unexpected image")
            limits = session_limits(started.get("limits") or {})
            validate_session_container(container, key, limits)
            (proxy,) = self.docker_json(
                "inspect", "--type", "container", SANDBOX_PROXY, worker=True
            )
            validate_egress_proxy(proxy, proxies)
            (network,) = self.docker_json("network", "inspect", SESSION_NETWORK + key, worker=True)
            validate_session_network(network, key, {container["Id"], proxy["Id"]})
            self.session_phase("probe", key, nonce)
        except SetupError:
            self.report_egress_refusals()
            raise
        finally:
            clean = self.remove_smoke_session(key)
        require(clean, "The session check left its container, volume or network behind")
        self.state["upgrade"].pop("smoke_key", None)
        self.save()

    def remove_smoke_session(self, key: str) -> bool:
        """Stop the check's session through the runner; remove by name what it left."""
        require(bool(re.fullmatch(r"[a-f0-9]{32}", key)), "Invalid session check key")
        with contextlib.suppress(SetupError):
            self.session_phase("stop", key, "0" * 32)
        name, network = SESSION_PREFIX + key, SESSION_NETWORK + key
        try:
            left = [
                (kind, target)
                for kind, target in (("container", name), ("volume", name), ("network", network))
                if self.run_command(
                    [*self.worker, kind, "inspect", target],
                    stage="Verify the session check's cleanup",
                    check=False,
                ).returncode
                == 0
            ]
            for kind, target in left:
                if kind == "network":
                    self.run_command(
                        [*self.worker, "network", "disconnect", "--force", target, SANDBOX_PROXY],
                        stage="Remove what the session check left",
                        check=False,
                    )
                    self.run_command(
                        [*self.worker, "network", "rm", target],
                        stage="Remove what the session check left",
                        check=False,
                    )
                else:
                    self.run_command(
                        [*self.worker, kind, "rm", "--force", target],
                        stage="Remove what the session check left",
                        check=False,
                    )
        except SetupError:
            return False
        return not left

    def report_egress_refusals(self) -> None:
        """The proxy logs one line per refused or unreachable host; nothing else."""
        try:
            logs = self.run_command(
                [*self.worker, "logs", "--tail", "40", SANDBOX_PROXY],
                stage="Read the egress proxy's refusals",
                check=False,
            )
        except SetupError:
            return
        lines: list[str] = []
        for line in (logs.stdout + logs.stderr).splitlines():
            line = line.strip()
            if re.fullmatch(r"egress (denied|unreachable) [A-Za-z0-9.:-]{1,253}", line):
                if line not in lines:
                    lines.append(line)
        if lines:
            report("Workspace runner: " + "; ".join(lines[-6:]), error=True)


def verify_inherited_lock(descriptor: int, path: Path) -> None:
    """The deploy script holds deploy.lock on this descriptor for its whole run.

    Taking the lock again on the same open file succeeds only for its holder; it
    is never released here, since that would release the deploy's lock too.
    """
    try:
        held = os.fstat(descriptor)
        named = os.stat(path, follow_symlinks=False)
    except OSError:
        raise SetupError("The inherited deployment lock is not open") from None
    require(
        stat.S_ISREG(named.st_mode)
        and stat.S_ISREG(held.st_mode)
        and (held.st_dev, held.st_ino) == (named.st_dev, named.st_ino),
        "The inherited descriptor is not the deployment lock",
    )
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        raise SetupError("Another process holds the deployment lock") from None


@contextlib.contextmanager
def deployment_lock(inherited_fd: int | None = None):
    require(os.geteuid() == 0, "Installer requires root")
    if inherited_fd is not None:
        verify_inherited_lock(inherited_fd, DEPLOY_STATE / "deploy.lock")
        yield
        return
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


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--repository", default=REPOSITORY)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--rollback", action="store_true")
    mode.add_argument(
        "--upgrade",
        action="store_true",
        help="Move an installed runner to this commit's images (run by deploy_production.sh)",
    )
    mode.add_argument(
        "--needed-images",
        action="store_true",
        help="Print the workspace images an --upgrade would load; the deploy sends only these",
    )
    parser.add_argument(
        "--images-dir",
        help="The private directory where the workflow put this commit's image archives",
    )
    parser.add_argument(
        "--research-dir",
        choices=[RESEARCH_DIR],
        help="Also persist research configuration during the same backend recreation",
    )
    parser.add_argument(
        "--inherited-lock-fd",
        type=int,
        help="With --upgrade: the descriptor on which the caller holds deploy.lock",
    )
    parser.add_argument(
        "--inputs-digest",
        help="With --upgrade: digest of the runner's inputs; an unchanged one loads nothing",
    )
    parser.add_argument(
        "--with-browser",
        action="store_true",
        help="With --upgrade: also load the browser sandbox image (Shahid)",
    )
    args = parser.parse_args(argv)
    if (args.upgrade or args.needed_images) and args.research_dir:
        parser.error("--upgrade keeps the installed research setting")
    if not (args.upgrade or args.needed_images) and (args.inputs_digest or args.with_browser):
        parser.error("--inputs-digest and --with-browser need --upgrade or --needed-images")
    if not args.upgrade and args.inherited_lock_fd is not None:
        parser.error("--inherited-lock-fd needs --upgrade")
    if args.rollback or args.needed_images:
        if args.images_dir is not None:
            parser.error("--images-dir is only for a setup or an --upgrade")
    elif args.images_dir is None or not re.fullmatch(images_directory_pattern(), args.images_dir):
        parser.error(f"--images-dir must be a directory matching {images_directory_pattern()}")
    if args.inherited_lock_fd is not None and not 3 <= args.inherited_lock_fd <= 255:
        parser.error("--inherited-lock-fd must be a descriptor from 3 to 255")
    if args.inputs_digest is not None and not re.fullmatch(r"[a-f0-9]{64}", args.inputs_digest):
        parser.error("--inputs-digest must be 64 lowercase hex characters")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)

    def interrupted(_signal, _frame):
        raise SetupError("Setup interrupted; resume from the managed checkpoint")

    try:
        validate_target(args.sha, args.repository)
        if not args.needed_images:
            public_url()  # before any change: every other mode checks the public site
        images_dir = Path(args.images_dir) if args.images_dir else None
        os.umask(0o077)
        for signal_number in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
            signal.signal(signal_number, interrupted)
        with deployment_lock(args.inherited_lock_fd):
            if args.needed_images:
                print(" ".join(needed_images(args.inputs_digest, args.with_browser)), flush=True)
                return 0
            if args.upgrade:
                Upgrade(
                    args.sha,
                    inputs_digest=args.inputs_digest,
                    with_browser=args.with_browser,
                    images_dir=images_dir,
                ).run()
                return 0
            installer = Installer(args.sha, research_dir=args.research_dir, images_dir=images_dir)
            if args.rollback:
                installer.preflight(recovering=True)
                installer.load_state(rollback=True)
                installer.rollback()
            else:
                installer.setup()
    except UpgradeRolledBack as error:
        report(f"Workspace runner NOT upgraded: {error}", error=True)
        return NOT_UPGRADED
    except UpgradeUnrecovered as error:
        report(f"Workspace runner needs attention: {error}", error=True)
        return NOT_VERIFIED
    except (SetupError, OSError, ValueError, KeyError) as error:
        report(f"Workspace runner setup stopped: {error_text(error)}", error=True)
        return NOT_VERIFIED if args.upgrade else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
