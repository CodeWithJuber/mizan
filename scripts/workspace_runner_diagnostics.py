#!/usr/bin/env python3
"""Read-only, secret-free diagnostics for an interrupted workspace setup."""

import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

DOCKER = ["/usr/bin/docker", "--host", "unix:///var/run/docker.sock"]
ROOT = Path("/opt/mizan")
STATE = Path("/var/lib/mizan-deploy/workspace-runner")


def run(args, timeout=30, stdin=None):
    try:
        result = subprocess.run(
            args,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
            input=stdin,
            env={
                "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                "LANG": "C.UTF-8",
            },
        )
        return result.returncode, result.stdout, result.stderr
    except (OSError, subprocess.TimeoutExpired):
        return -1, "", "command unavailable or timed out"


def error_class(stderr):
    # Never print raw Compose errors: some validators quote configuration values.
    patterns = {
        "undefined network": ("undefined network", "network not found"),
        "invalid image reference": ("invalid reference format", "invalid image"),
        "interpolation": ("interpolation", "required variable"),
        "schema validation": ("additional propert", "must be a", "invalid type", "is not allowed"),
        "missing file": ("no such file", "not found"),
    }
    return [
        name
        for name, needles in patterns.items()
        if any(needle in stderr.lower() for needle in needles)
    ] or ["unclassified; raw output withheld"]


def environment_values(config):
    values = []
    for service in config.get("services", {}).values():
        environment = service.get("environment", {})
        if isinstance(environment, dict):
            values.extend(str(value) for value in environment.values() if value is not None)
        elif isinstance(environment, list):
            values.extend(value.partition("=")[2] for value in environment if "=" in value)
    return values


def safe_error_detail(stderr, values):
    """Bounded diagnostic after redacting values AND every quoted string."""
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", stderr)
    variants = set()
    for value in values:
        if value:
            variants.update(
                (value, value.replace("$", "$$"), json.dumps(value)[1:-1], repr(value)[1:-1])
            )
    for value in sorted(variants, key=len, reverse=True):
        text = text.replace(value, "<redacted>")
    for pattern in (r'"(?:[^"\\]|\\.)*"', r"'(?:[^'\\]|\\.)*'", r"`[^`]*`", r"“[^”]*”", r"‘[^’]*’"):
        text = re.sub(pattern, "<quoted>", text, flags=re.DOTALL)
    text = re.sub(r"[A-Za-z][A-Za-z0-9+.-]{1,20}://[^\s\"'<>]+", "<url>", text)
    text = re.sub(r"(?i)bearer\s+\S+", "Bearer <credential>", text)
    text = re.sub(
        r"(?i)(token|password|secret|api[_-]?key)\s*[:=]\s*[^\s,;]+", r"\1=<credential>", text
    )
    text = re.sub(r"(?:gh[pousr]_|github_pat_|sk[-_])[A-Za-z0-9_-]+", "<credential>", text)
    text = re.sub(r"[A-Za-z0-9_+/=-]{24,}", "<opaque>", text)
    text = "".join(character for character in text if character in "\n\t" or ord(character) >= 32)
    return "\n".join(text.splitlines()[:8])[:1200]


def main():
    if os.geteuid() != 0:
        raise SystemExit("Existing root deployment connection required")
    report = {"scope": "read-only; no config, services, files or data changed"}
    code, output, _ = run([*DOCKER, "compose", "version", "--short"])
    report["compose_version"] = output.strip()[:80] if code == 0 else "unavailable"
    for name in ("mizan-backend", "mizan-nginx"):
        code, output, _ = run([*DOCKER, "inspect", name])
        if code:
            report[name] = {"inspect_exit": code}
            continue
        item = json.loads(output)[0]
        report[name] = {
            "id": item["Id"],
            "image_id": item["Image"],
            "status": item["State"].get("Status"),
            "running": item["State"].get("Running"),
            "health": item["State"].get("Health", {}).get("Status"),
            "project": item["Config"].get("Labels", {}).get("com.docker.compose.project"),
            "network_names": list(item["NetworkSettings"]["Networks"]),
        }
    for label, command in {
        "backend_health_http": [
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
            "http://127.0.0.1:8000/api/health",
        ],
        "backend_anonymous_status_http": [
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
        "public_health_http": [
            "curl",
            "--silent",
            "--connect-timeout",
            "10",
            "--max-time",
            "20",
            "--output",
            "/dev/null",
            "--write-out",
            "%{http_code}",
            "https://mizan.example.com/api/health",
        ],
    }.items():
        code, output, _ = run(command)
        report[label] = {
            "exit": code,
            "http_status": output.strip() if output.strip().isdigit() else "unavailable",
        }
    code, _, _ = run([*DOCKER, "exec", "mizan-nginx", "nginx", "-t"])
    report["nginx_config_test_exit"] = code
    code, output, _ = run(
        [
            *DOCKER,
            "ps",
            "--all",
            "--quiet",
            "--filter",
            "label=com.docker.compose.project=mizan",
            "--filter",
            "label=com.docker.compose.service=workspace-runner",
        ]
    )
    report["runner_container_ids"] = output.split() if code == 0 else "unavailable"
    state = json.loads((STATE / "state.json").read_text())
    report["checkpoint"] = {
        key: state.get(key)
        for key in (
            "manager",
            "sha",
            "phase",
            "uid",
            "gid",
            "daemon_ready",
            "research_dir",
            "verified_at",
        )
    }
    attempt = Path(state.get("active_attempt", ""))
    if attempt.parent != STATE or not attempt.name.startswith("attempt-"):
        report["snapshot"] = "no valid managed attempt"
    else:
        snapshot = json.loads((attempt / "snapshot.json").read_text())
        report["snapshot"] = {
            "backend_image": snapshot["backend_image"],
            "override_existed_before": snapshot["override_before"] is not None,
            "original_file_hashes_match": all(
                Path(name).is_file()
                and hashlib.sha256(Path(name).read_bytes()).hexdigest() == value
                for name, value in snapshot["hashes"].items()
            ),
        }
        command = [*DOCKER, "compose", "--project-directory", str(ROOT), "-p", "mizan"]
        for filename in snapshot["files"]:
            path = Path(filename)
            if not path.is_absolute() or not (
                path.is_relative_to(ROOT) or path.is_relative_to(STATE.parent)
            ):
                raise SystemExit("Snapshot includes an unexpected Compose path")
            command.extend(["-f", filename])
        code, output, stderr = run([*command, "config", "--format", "json"])
        report["original_compose_exit"] = code
        known_values = list(snapshot["backend_env"].values())
        original_parsed = code == 0
        if code == 0:
            config = json.loads(output)
            known_values.extend(environment_values(config))
            report["original_networks"] = {
                key: {"name": value.get("name"), "external": value.get("external", False)}
                for key, value in config.get("networks", {}).items()
            }
            report["original_backend_network_keys"] = list(
                config["services"]["backend"].get("networks", {})
            )
        else:
            report["original_error_classes"] = error_class(stderr)
        override = ROOT / "docker-compose.workspace-runtime.yml"
        candidate_content = None
        if override.is_file():
            known_values.extend(environment_values(json.loads(override.read_text())))
            report["override_hash_matches_managed"] = hashlib.sha256(
                override.read_bytes()
            ).hexdigest() in {state.get("override_sha256"), state.get("pending_override_sha256")}
            candidate = [*command, "-f", str(override)]
        else:
            # Recovery removes the invalid override. Reconstruct it in memory
            # using only the adjacent reviewed installer and protected state.
            installer_path = Path(__file__).with_name("setup_workspace_runner.py")
            if installer_path.is_file():
                spec = importlib.util.spec_from_file_location(
                    "reviewed_runner_setup", installer_path
                )
                installer = importlib.util.module_from_spec(spec)
                previous = sys.dont_write_bytecode
                sys.dont_write_bytecode = True
                try:
                    spec.loader.exec_module(installer)
                finally:
                    sys.dont_write_bytecode = previous
                token = (STATE / "runner-token").read_text().strip()
                document = installer.workspace_override(
                    state["uid"],
                    state["gid"],
                    token,
                    runtime_image=state["images"]["runtime"]["id"],
                    runner_image=state["images"]["runner"]["id"],
                    research_dir=state.get("research_dir"),
                )
                candidate_content = installer.compose_document(document)
                known_values.extend(environment_values(document))
                known_values.append(token)
                candidate = [*command, "-f", "-"]
                report["candidate_reconstructed_from_reviewed_installer"] = hashlib.sha256(
                    installer_path.read_bytes()
                ).hexdigest()
            else:
                candidate = None
                report["candidate_unavailable"] = (
                    "Upload reviewed setup_workspace_runner.py beside this diagnostic to reconstruct without writing server configuration"
                )
        if candidate is not None:
            current = attempt / "current-backend.yml"
            if current.is_file():
                known_values.extend(environment_values(json.loads(current.read_text())))
                candidate.extend(["-f", str(current)])
            code, _, stderr = run([*candidate, "config", "--quiet"], stdin=candidate_content)
            report["candidate_compose_exit"] = code
            report["candidate_error_classes"] = error_class(stderr) if code else []
            if code and original_parsed:
                report["candidate_error_detail_redacted"] = safe_error_detail(stderr, known_values)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
