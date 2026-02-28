"""
Jisr Remote Execution Skill (جِسْر — The Bridge)
==================================================

"And We made from water every living thing" — Quran 21:30

Jisr (Bridge) connects MIZAN to remote servers via SSH:
- Execute commands on remote servers
- Transfer files (upload/download)
- Multi-server orchestration
- Server health monitoring
- Automated setup scripts

Uses subprocess ssh/scp for maximum compatibility (no paramiko needed).
Falls back to paramiko if available for persistent connections.
"""

import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime

from ..base import SkillBase, SkillManifest

logger = logging.getLogger("mizan.jisr")


@dataclass
class ServerConnection:
    """A registered remote server"""

    id: str = ""
    host: str = ""
    port: int = 22
    user: str = "root"
    key_path: str | None = None
    password: str | None = None
    label: str = ""
    status: str = "unknown"
    last_connected: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "host": self.host,
            "port": self.port,
            "user": self.user,
            "label": self.label,
            "status": self.status,
            "has_key": bool(self.key_path),
            "last_connected": self.last_connected,
        }


class JisrRemoteSkill(SkillBase):
    """
    Jisr — Remote Server Bridge
    SSH execution, file transfer, and server management.
    """

    manifest = SkillManifest(
        name="jisr_remote",
        version="1.0.0",
        description="Remote server management via SSH. Execute commands, "
        "transfer files, run setup scripts on remote servers.",
        permissions=[
            "network:ssh:*",
            "shell:ssh",
            "shell:scp",
            "shell:sshpass",
        ],
        tags=["جسر", "Remote"],
    )

    # Default key location inside the container
    DEFAULT_KEY_DIR = "/data/.ssh"
    DEFAULT_KEY_PATH = "/data/.ssh/mizan_id_ed25519"

    def __init__(self, config: dict = None):
        super().__init__(config)
        self.servers: dict[str, ServerConnection] = {}
        self._tools = {
            "ssh_register_server": self.register_server,
            "ssh_exec": self.ssh_exec,
            "ssh_exec_script": self.ssh_exec_script,
            "ssh_upload": self.ssh_upload,
            "ssh_download": self.ssh_download,
            "ssh_check_server": self.check_server,
            "ssh_list_servers": self.list_servers,
            "ssh_keygen": self.ssh_keygen,
            "ssh_copy_id": self.ssh_copy_id,
        }

    async def execute(self, params: dict, context: dict = None) -> dict:
        action = params.get("action", "list_servers")
        handler = self._tools.get(f"ssh_{action}")
        if handler:
            return await handler(params)
        return {"error": f"Unknown SSH action: {action}"}

    def _build_ssh_cmd(self, server: ServerConnection, command: str) -> list[str]:
        """Build the SSH command with proper options."""
        cmd = ["ssh"]
        cmd.extend(["-o", "StrictHostKeyChecking=no"])
        cmd.extend(["-o", "UserKnownHostsFile=/dev/null"])
        cmd.extend(["-o", "ConnectTimeout=10"])
        cmd.extend(["-o", "LogLevel=ERROR"])
        cmd.extend(["-p", str(server.port)])

        if server.key_path:
            cmd.extend(["-i", server.key_path])

        cmd.append(f"{server.user}@{server.host}")
        cmd.append(command)
        return cmd

    def _build_scp_cmd(
        self, server: ServerConnection, local: str, remote: str, upload: bool = True
    ) -> list[str]:
        """Build the SCP command."""
        cmd = ["scp"]
        cmd.extend(["-o", "StrictHostKeyChecking=no"])
        cmd.extend(["-o", "UserKnownHostsFile=/dev/null"])
        cmd.extend(["-o", "ConnectTimeout=10"])
        cmd.extend(["-P", str(server.port)])

        if server.key_path:
            cmd.extend(["-i", server.key_path])

        remote_path = f"{server.user}@{server.host}:{remote}"
        if upload:
            cmd.extend([local, remote_path])
        else:
            cmd.extend([remote_path, local])
        return cmd

    def _wrap_with_sshpass(self, cmd: list[str], password: str) -> list[str]:
        """Wrap command with sshpass for password auth."""
        return ["sshpass", "-p", password] + cmd

    def _get_server(self, params: dict) -> ServerConnection | None:
        """Resolve server from params (by id or host)."""
        server_id = params.get("server_id", "")
        host = params.get("host", "")

        if server_id and server_id in self.servers:
            return self.servers[server_id]

        # Try by host
        for srv in self.servers.values():
            if srv.host == host or srv.label == host:
                return srv

        # Auto-create from params if host provided
        if host:
            srv = ServerConnection(
                id=host,
                host=host,
                port=params.get("port", 22),
                user=params.get("user", "root"),
                key_path=params.get("key_path"),
                password=params.get("password"),
                label=params.get("label", host),
            )
            self.servers[srv.id] = srv
            return srv

        return None

    async def register_server(self, params: dict) -> dict:
        """Register a remote server for SSH access."""
        host = params.get("host", "")
        if not host:
            return {"error": "host is required"}

        import uuid

        server_id = str(uuid.uuid4())[:8]
        server = ServerConnection(
            id=server_id,
            host=host,
            port=params.get("port", 22),
            user=params.get("user", "root"),
            key_path=params.get("key_path"),
            password=params.get("password"),
            label=params.get("label", host),
        )
        self.servers[server_id] = server
        logger.info(f"[JISR] Server registered: {server.label} ({server.host})")
        return {
            "registered": True,
            "server": server.to_dict(),
            "message": f"Server '{server.label}' registered. Use server_id='{server_id}' for commands.",
        }

    async def ssh_exec(self, params: dict) -> dict:
        """Execute a command on a remote server via SSH."""
        server = self._get_server(params)
        if not server:
            return {"error": "Server not found. Register with ssh_register_server first, or provide 'host' in params."}

        command = params.get("command", "")
        if not command:
            return {"error": "command is required"}

        timeout = min(params.get("timeout", 60), 300)

        ssh_cmd = self._build_ssh_cmd(server, command)
        if server.password:
            ssh_cmd = self._wrap_with_sshpass(ssh_cmd, server.password)

        try:
            result = subprocess.run(
                ssh_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            server.status = "connected" if result.returncode == 0 else "error"
            server.last_connected = datetime.now(UTC).isoformat()
            return {
                "stdout": result.stdout[:20000],
                "stderr": result.stderr[:5000],
                "returncode": result.returncode,
                "server": server.host,
                "success": result.returncode == 0,
            }
        except subprocess.TimeoutExpired:
            server.status = "timeout"
            return {"error": f"SSH command timed out after {timeout}s", "server": server.host}
        except FileNotFoundError:
            return {
                "error": "SSH client not found. Install openssh-client.",
                "hint": "apt-get install -y openssh-client sshpass",
            }
        except Exception as e:
            server.status = "error"
            return {"error": str(e), "server": server.host}

    async def ssh_exec_script(self, params: dict) -> dict:
        """
        Execute a multi-line script on a remote server.
        Writes script to temp file, uploads and executes it.
        """
        server = self._get_server(params)
        if not server:
            return {"error": "Server not found. Register first or provide 'host'."}

        script = params.get("script", "")
        if not script:
            return {"error": "script content is required"}

        interpreter = params.get("interpreter", "/bin/bash")
        timeout = min(params.get("timeout", 300), 600)

        # Write script to temp file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".sh", delete=False, prefix="mizan_"
        ) as tmp:
            tmp.write(f"#!/bin/bash\nset -e\n{script}")
            tmp_path = tmp.name

        try:
            # Upload script
            remote_script = "/tmp/mizan_remote_script.sh"
            scp_cmd = self._build_scp_cmd(server, tmp_path, remote_script, upload=True)
            if server.password:
                scp_cmd = self._wrap_with_sshpass(scp_cmd, server.password)

            upload_result = subprocess.run(
                scp_cmd, capture_output=True, text=True, timeout=30
            )
            if upload_result.returncode != 0:
                return {
                    "error": f"Failed to upload script: {upload_result.stderr[:500]}",
                    "server": server.host,
                }

            # Execute it
            exec_cmd = f"chmod +x {remote_script} && {interpreter} {remote_script}"
            ssh_cmd = self._build_ssh_cmd(server, exec_cmd)
            if server.password:
                ssh_cmd = self._wrap_with_sshpass(ssh_cmd, server.password)

            result = subprocess.run(
                ssh_cmd, capture_output=True, text=True, timeout=timeout
            )

            # Cleanup remote script
            cleanup_cmd = self._build_ssh_cmd(server, f"rm -f {remote_script}")
            if server.password:
                cleanup_cmd = self._wrap_with_sshpass(cleanup_cmd, server.password)
            subprocess.run(cleanup_cmd, capture_output=True, timeout=10)

            server.status = "connected" if result.returncode == 0 else "error"
            server.last_connected = datetime.now(UTC).isoformat()
            return {
                "stdout": result.stdout[:20000],
                "stderr": result.stderr[:5000],
                "returncode": result.returncode,
                "server": server.host,
                "success": result.returncode == 0,
            }
        except subprocess.TimeoutExpired:
            return {"error": f"Script execution timed out after {timeout}s"}
        except Exception as e:
            return {"error": str(e)}
        finally:
            os.unlink(tmp_path)

    async def ssh_upload(self, params: dict) -> dict:
        """Upload a file to a remote server."""
        server = self._get_server(params)
        if not server:
            return {"error": "Server not found."}

        local_path = params.get("local_path", "")
        remote_path = params.get("remote_path", "")

        # Support inline content → write to temp then upload
        content = params.get("content", "")
        if content and not local_path:
            with tempfile.NamedTemporaryFile(
                mode="w", delete=False, prefix="mizan_upload_"
            ) as tmp:
                tmp.write(content)
                local_path = tmp.name

        if not local_path or not remote_path:
            return {"error": "local_path (or content) and remote_path required"}

        scp_cmd = self._build_scp_cmd(server, local_path, remote_path, upload=True)
        if server.password:
            scp_cmd = self._wrap_with_sshpass(scp_cmd, server.password)

        try:
            result = subprocess.run(
                scp_cmd, capture_output=True, text=True, timeout=120
            )
            # Clean up temp file if we created one from content
            if content:
                os.unlink(local_path)

            return {
                "success": result.returncode == 0,
                "remote_path": remote_path,
                "server": server.host,
                "error": result.stderr[:500] if result.returncode != 0 else None,
            }
        except Exception as e:
            return {"error": str(e)}

    async def ssh_download(self, params: dict) -> dict:
        """Download a file from a remote server."""
        server = self._get_server(params)
        if not server:
            return {"error": "Server not found."}

        remote_path = params.get("remote_path", "")
        local_path = params.get("local_path", "")
        if not remote_path:
            return {"error": "remote_path required"}
        if not local_path:
            local_path = f"/tmp/mizan_download_{os.path.basename(remote_path)}"

        scp_cmd = self._build_scp_cmd(server, local_path, remote_path, upload=False)
        if server.password:
            scp_cmd = self._wrap_with_sshpass(scp_cmd, server.password)

        try:
            result = subprocess.run(
                scp_cmd, capture_output=True, text=True, timeout=120
            )
            return {
                "success": result.returncode == 0,
                "local_path": local_path,
                "server": server.host,
                "error": result.stderr[:500] if result.returncode != 0 else None,
            }
        except Exception as e:
            return {"error": str(e)}

    async def check_server(self, params: dict) -> dict:
        """Check if a server is reachable."""
        server = self._get_server(params)
        if not server:
            return {"error": "Server not found."}

        # Quick SSH connectivity test
        ssh_cmd = self._build_ssh_cmd(server, "echo 'MIZAN_PING_OK' && uname -a && uptime")
        if server.password:
            ssh_cmd = self._wrap_with_sshpass(ssh_cmd, server.password)

        try:
            result = subprocess.run(
                ssh_cmd, capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0 and "MIZAN_PING_OK" in result.stdout:
                server.status = "connected"
                server.last_connected = datetime.now(UTC).isoformat()
                lines = result.stdout.strip().split("\n")
                return {
                    "reachable": True,
                    "server": server.host,
                    "system": lines[1] if len(lines) > 1 else "",
                    "uptime": lines[2] if len(lines) > 2 else "",
                }
            server.status = "error"
            return {
                "reachable": False,
                "server": server.host,
                "error": result.stderr[:500],
            }
        except subprocess.TimeoutExpired:
            server.status = "timeout"
            return {"reachable": False, "server": server.host, "error": "Connection timed out"}
        except Exception as e:
            return {"reachable": False, "server": server.host, "error": str(e)}

    async def list_servers(self, params: dict = None) -> dict:
        """List all registered servers."""
        return {
            "servers": [s.to_dict() for s in self.servers.values()],
            "count": len(self.servers),
        }

    async def ssh_keygen(self, params: dict = None) -> dict:
        """Generate an SSH key pair for MIZAN to use for passwordless auth.

        Creates an ed25519 key at /data/.ssh/mizan_id_ed25519.
        If key already exists, returns the existing public key.
        """
        params = params or {}
        key_path = params.get("key_path", self.DEFAULT_KEY_PATH)
        key_dir = os.path.dirname(key_path)
        pub_path = f"{key_path}.pub"

        # Return existing key if present
        if os.path.exists(pub_path):
            with open(pub_path) as f:
                pub_key = f.read().strip()
            return {
                "exists": True,
                "key_path": key_path,
                "public_key": pub_key,
                "message": "Key already exists. Use ssh_copy_id to install on a server.",
            }

        # Create directory
        os.makedirs(key_dir, mode=0o700, exist_ok=True)

        # Generate key pair
        try:
            result = subprocess.run(
                [
                    "ssh-keygen",
                    "-t", "ed25519",
                    "-f", key_path,
                    "-N", "",  # No passphrase
                    "-C", "mizan-agent",
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode != 0:
                return {"error": f"ssh-keygen failed: {result.stderr[:500]}"}

            # Lock down permissions
            os.chmod(key_path, 0o600)
            os.chmod(pub_path, 0o644)

            with open(pub_path) as f:
                pub_key = f.read().strip()

            logger.info(f"[JISR] SSH key pair generated at {key_path}")
            return {
                "generated": True,
                "key_path": key_path,
                "public_key": pub_key,
                "message": "Key pair generated. Use ssh_copy_id to install on a server.",
            }
        except FileNotFoundError:
            return {"error": "ssh-keygen not found. Install openssh-client."}
        except Exception as e:
            return {"error": str(e)}

    async def ssh_copy_id(self, params: dict) -> dict:
        """Install MIZAN's public key on a remote server for passwordless access.

        Requires either:
        - A registered server with password auth, OR
        - host + password in params

        After success, updates the server entry to use key auth.
        """
        server = self._get_server(params)
        if not server:
            return {"error": "Server not found. Provide 'host' and 'password'."}

        if not server.password:
            password = params.get("password", "")
            if not password:
                return {
                    "error": "Password required to copy SSH key. "
                    "Provide 'password' in params or register server with password first."
                }
            server.password = password

        key_path = params.get("key_path", self.DEFAULT_KEY_PATH)
        pub_path = f"{key_path}.pub"

        # Generate key if it doesn't exist
        if not os.path.exists(pub_path):
            gen_result = await self.ssh_keygen({"key_path": key_path})
            if gen_result.get("error"):
                return gen_result

        with open(pub_path) as f:
            pub_key = f.read().strip()

        # Copy public key to remote server's authorized_keys
        install_cmd = (
            f"mkdir -p ~/.ssh && chmod 700 ~/.ssh && "
            f"echo '{pub_key}' >> ~/.ssh/authorized_keys && "
            f"chmod 600 ~/.ssh/authorized_keys && "
            f"echo 'MIZAN_KEY_INSTALLED'"
        )

        ssh_cmd = self._build_ssh_cmd(server, install_cmd)
        ssh_cmd = self._wrap_with_sshpass(ssh_cmd, server.password)

        try:
            result = subprocess.run(
                ssh_cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0 and "MIZAN_KEY_INSTALLED" in result.stdout:
                # Update server to use key auth going forward
                server.key_path = key_path
                old_password = server.password
                server.password = None
                server.status = "connected"
                server.last_connected = datetime.now(UTC).isoformat()

                # Verify key auth works
                verify_cmd = self._build_ssh_cmd(server, "echo 'MIZAN_KEY_AUTH_OK'")
                verify = subprocess.run(
                    verify_cmd, capture_output=True, text=True, timeout=15
                )

                if verify.returncode == 0 and "MIZAN_KEY_AUTH_OK" in verify.stdout:
                    logger.info(
                        f"[JISR] SSH key installed and verified on {server.host}"
                    )
                    return {
                        "success": True,
                        "server": server.host,
                        "key_path": key_path,
                        "message": f"SSH key auth configured for {server.host}. Password no longer needed.",
                    }
                else:
                    # Key auth failed, restore password
                    server.password = old_password
                    server.key_path = None
                    return {
                        "success": False,
                        "server": server.host,
                        "error": "Key was installed but verification failed. Password auth still active.",
                        "stderr": verify.stderr[:500],
                    }

            return {
                "success": False,
                "server": server.host,
                "error": f"Failed to install key: {result.stderr[:500]}",
            }
        except subprocess.TimeoutExpired:
            return {"error": "Connection timed out during key installation"}
        except FileNotFoundError:
            return {"error": "sshpass not found. Install: apt-get install sshpass"}
        except Exception as e:
            return {"error": str(e)}

    def get_tool_schemas(self) -> list[dict]:
        return [
            {
                "name": "ssh_register_server",
                "description": "Register a remote server for SSH access. Store connection details for reuse.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "host": {"type": "string", "description": "Server IP or hostname"},
                        "port": {"type": "integer", "description": "SSH port", "default": 22},
                        "user": {"type": "string", "description": "SSH username", "default": "root"},
                        "key_path": {"type": "string", "description": "Path to SSH private key file"},
                        "password": {"type": "string", "description": "SSH password (if no key)"},
                        "label": {"type": "string", "description": "Friendly name for this server"},
                    },
                    "required": ["host"],
                },
            },
            {
                "name": "ssh_exec",
                "description": "Execute a single command on a remote server via SSH.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "server_id": {"type": "string", "description": "Registered server ID"},
                        "host": {"type": "string", "description": "Server host (if not registered)"},
                        "user": {"type": "string", "description": "SSH user (default: root)"},
                        "password": {"type": "string", "description": "SSH password"},
                        "key_path": {"type": "string", "description": "SSH key path"},
                        "command": {"type": "string", "description": "Command to execute"},
                        "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 60},
                    },
                    "required": ["command"],
                },
            },
            {
                "name": "ssh_exec_script",
                "description": "Execute a multi-line bash script on a remote server. Uploads and runs the script.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "server_id": {"type": "string", "description": "Registered server ID"},
                        "host": {"type": "string", "description": "Server host"},
                        "user": {"type": "string", "description": "SSH user"},
                        "password": {"type": "string", "description": "SSH password"},
                        "script": {"type": "string", "description": "Multi-line bash script to execute"},
                        "interpreter": {"type": "string", "description": "Script interpreter", "default": "/bin/bash"},
                        "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 300},
                    },
                    "required": ["script"],
                },
            },
            {
                "name": "ssh_upload",
                "description": "Upload a file or content to a remote server via SCP.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "server_id": {"type": "string", "description": "Registered server ID"},
                        "host": {"type": "string", "description": "Server host"},
                        "local_path": {"type": "string", "description": "Local file path to upload"},
                        "content": {"type": "string", "description": "File content to upload (alternative to local_path)"},
                        "remote_path": {"type": "string", "description": "Remote destination path"},
                    },
                    "required": ["remote_path"],
                },
            },
            {
                "name": "ssh_download",
                "description": "Download a file from a remote server via SCP.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "server_id": {"type": "string", "description": "Registered server ID"},
                        "host": {"type": "string", "description": "Server host"},
                        "remote_path": {"type": "string", "description": "Remote file path"},
                        "local_path": {"type": "string", "description": "Local destination path"},
                    },
                    "required": ["remote_path"],
                },
            },
            {
                "name": "ssh_check_server",
                "description": "Check if a remote server is reachable via SSH.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "server_id": {"type": "string", "description": "Registered server ID"},
                        "host": {"type": "string", "description": "Server host"},
                    },
                },
            },
            {
                "name": "ssh_list_servers",
                "description": "List all registered remote servers.",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "ssh_keygen",
                "description": "Generate an SSH key pair for MIZAN. Creates ed25519 key at /data/.ssh/mizan_id_ed25519. Returns public key.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "key_path": {
                            "type": "string",
                            "description": "Custom key file path (default: /data/.ssh/mizan_id_ed25519)",
                        },
                    },
                },
            },
            {
                "name": "ssh_copy_id",
                "description": "Install MIZAN's SSH public key on a remote server for passwordless access. Requires password for first-time setup.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "server_id": {"type": "string", "description": "Registered server ID"},
                        "host": {"type": "string", "description": "Server IP or hostname"},
                        "port": {"type": "integer", "description": "SSH port", "default": 22},
                        "user": {"type": "string", "description": "SSH username", "default": "root"},
                        "password": {"type": "string", "description": "Current server password (required for first-time key setup)"},
                        "key_path": {"type": "string", "description": "SSH key path (default: /data/.ssh/mizan_id_ed25519)"},
                    },
                    "required": ["password"],
                },
            },
        ]
