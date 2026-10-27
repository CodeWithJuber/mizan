"""Shahid on the runner: one browsing job in a one-shot, hardened container.

The browser container (``workspace-browser`` image) gets its own internal Docker
network whose only peer is the browse egress proxy. That proxy runs in public
mode: it connects to any host on port 443 whose every address is globally
routable, never to the host, other containers, private networks or metadata
services. Which pages may be visited and which requests may change something is
enforced inside the container by ``browse_agent`` (the job's origins, held
non-GET requests). The container is removed and its network deleted after the
job, so nothing (cookies, cache, history) outlives it.
"""

from __future__ import annotations

import json
import logging
import os
import uuid

from .sessions import SessionError, docker

logger = logging.getLogger("mizan.workspace.browse")
EGRESS = "mizan-browse-egress"
NETWORK_PREFIX = "mizan-browse-net-"
MAX_REPLY = 16 * 1024 * 1024


def browser_image() -> str:
    return os.getenv("MIZAN_WORKSPACE_BROWSER_IMAGE", "")


def enabled() -> bool:
    return bool(browser_image())


async def image_present() -> bool:
    if not enabled():
        return False
    code, _, _ = await docker("image", "inspect", browser_image(), timeout=10)
    return code == 0


async def ensure_proxy() -> None:
    code, out, _ = await docker("inspect", "--format", "{{.State.Running}}", EGRESS)
    if code == 0 and out.strip() == b"true":
        return
    await docker("rm", "-f", EGRESS)
    code, _, err = await docker(
        "run", "-d", "--pull", "never", "--name", EGRESS, "--restart", "unless-stopped",
        "--init", "--user", "65534:65534", "--cap-drop", "ALL", "--read-only",
        "--security-opt", "no-new-privileges", "--memory", "128m", "--memory-swap", "128m",
        "--pids-limit", "64", "--network", "bridge",
        "--env", "MIZAN_EGRESS_MODE=public",
        "--label", "mizan.egress=browse-proxy",
        browser_image(), "python3", "-I", "/egress_proxy.py", "3128",
    )  # fmt: skip
    if code != 0:
        logger.warning("browse egress proxy failed: %s", err[:300])
        raise SessionError(503, "Could not start the browser's egress proxy")


async def run(job: dict, timeout_s: int) -> dict:
    """Run one validated job; the container and its network are always removed."""
    if not enabled():
        raise SessionError(503, "The browser sandbox is not installed on this runner")
    await ensure_proxy()
    token = uuid.uuid4().hex
    network, name = NETWORK_PREFIX + token, f"mizan-browse-{token}"
    code, _, err = await docker("network", "create", "--internal", network)
    if code != 0:
        raise SessionError(503, "Could not create the browser's network")
    try:
        code, _, err = await docker("network", "connect", "--alias", "egress", network, EGRESS)
        if code != 0:
            raise SessionError(503, "Could not attach the browser's egress proxy")
        proxy = "http://egress:3128"
        code, out, err = await docker(
            "run", "--rm", "--pull", "never", "--name", name, "--init",
            "--user", "65534:65534", "--cap-drop", "ALL", "--read-only",
            "--security-opt", "no-new-privileges", "--network", network,
            "--cpus", "1", "--memory", "1g", "--memory-swap", "1g", "--pids-limit", "256",
            "--shm-size", "256m",
            "--tmpfs", "/tmp:rw,nosuid,nodev,size=256m,mode=1777",
            "--env", "HOME=/tmp", "--env", f"HTTPS_PROXY={proxy}", "--env", f"HTTP_PROXY={proxy}",
            "--label", "mizan.browse=job",
            "-i", browser_image(), "python3", "-I", "/browse_agent.py",
            payload=json.dumps({**job, "timeout_s": timeout_s}).encode(),
            timeout=timeout_s + 30, limit=MAX_REPLY,
        )  # fmt: skip
        if code != 0:
            logger.warning("browse job failed: %s", err[:300])
            raise SessionError(503, "The browser sandbox failed")
        try:
            result = json.loads(out)
        except ValueError:
            raise SessionError(503, "The browser sandbox returned an invalid reply") from None
        if not isinstance(result, dict):
            raise SessionError(503, "The browser sandbox returned an invalid reply")
        return result
    finally:
        await docker("rm", "-f", name, timeout=30)
        await docker("network", "disconnect", "-f", network, EGRESS)
        await docker("network", "rm", network)
