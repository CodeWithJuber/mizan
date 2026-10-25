#!/usr/bin/env bash
# Read-only production inventory for an isolated Mizan coding worker.
set -euo pipefail
python3 - <<'PY'
import glob
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone


def probe(*args):
    try:
        result = subprocess.run(args, text=True, capture_output=True, timeout=20)
        return {"exit_code": result.returncode, "output": result.stdout.strip()[:4000],
                "error": result.stderr.strip()[:300]}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"error": type(error).__name__}


print(json.dumps({
    "observed_at": datetime.now(timezone.utc).isoformat(),
    "scope": "Mizan production host; no configuration or services changed",
    "os": probe("cat", "/etc/os-release"),
    "kernel": probe("uname", "-sr"),
    "memory": probe("free", "-m"),
    "disk": probe("df", "-h", "/", "/var/lib/docker"),
    "docker": probe("docker", "version", "--format", "{{.Server.Version}}"),
    "docker_security": probe("docker", "info", "--format", "{{json .SecurityOptions}}"),
    "docker_cgroups": probe("docker", "info", "--format", "{{.CgroupVersion}} {{.CgroupDriver}}"),
    "backend": probe("docker", "inspect", "--format", "{{.State.Status}} {{.Config.Image}} {{.HostConfig.Memory}}", "mizan-backend"),
    "compose_owner": probe("docker", "inspect", "--format", '{{index .Config.Labels "com.docker.compose.project"}} {{index .Config.Labels "com.docker.compose.project.working_dir"}}', "mizan-backend"),
    "backend_networks": probe("docker", "inspect", "--format", '{{range $name, $network := .NetworkSettings.Networks}}{{$name}} {{end}}', "mizan-backend"),
    "runner_account": probe("id", "mizan-workspace"),
    "rootless_sockets": [{"path": path, "uid": os.stat(path).st_uid, "gid": os.stat(path).st_gid}
                         for path in glob.glob("/run/user/[0-9]*/docker.sock")[:10]],
    "tools": {name: shutil.which(name) for name in ["dockerd-rootless-setuptool.sh", "dockerd-rootless.sh", "rootlesskit", "newuidmap", "slirp4netns", "loginctl", "systemctl"]},
    "rootless_packages": probe("dpkg-query", "-W", "uidmap", "slirp4netns", "docker-ce-rootless-extras"),
    "user_namespaces": probe("sysctl", "user.max_user_namespaces", "kernel.unprivileged_userns_clone", "kernel.apparmor_restrict_unprivileged_userns"),
}, indent=2))
PY
