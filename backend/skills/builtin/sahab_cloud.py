"""
Sahab Cloud Hub Skill (سَحَاب — The Clouds)
=============================================

"Have you not seen how Allah drives the clouds (Sahab),
 then joins them together, then makes them into a mass,
 and you see the rain emerge from within it?" — Quran 24:43

Cloud integration hub inspired by the Quranic metaphor of Sahab (clouds):
- Allah orchestrates clouds → We orchestrate cloud services
- Clouds gather and merge → Services integrate and compose
- Rain provides sustenance → Data flows nourish the system

Like CloudHub but with:
- Unified cloud service management (GitHub, Docker, APIs)
- Secure credential vault (Amanah — trust/safekeeping)
- Service health monitoring (Basir — All-Seeing)
- API composition and chaining
- Git repository management
"""

import hashlib
import logging
import os
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from ..base import SkillBase, SkillManifest

logger = logging.getLogger("mizan.sahab")


@dataclass
class CloudService:
    """A registered cloud service — like a Sahab (cloud) in the sky"""

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    name: str = ""
    service_type: str = ""  # github, docker, api, database, storage
    base_url: str = ""
    status: str = "disconnected"  # connected, disconnected, error
    last_check: str | None = None
    metadata: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "service_type": self.service_type,
            "base_url": self.base_url,
            "status": self.status,
            "last_check": self.last_check,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }


@dataclass
class ApiEndpoint:
    """A registered API endpoint for composition"""

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    method: str = "GET"
    url: str = ""
    headers: dict = field(default_factory=dict)
    body_template: str | None = None
    service_id: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "method": self.method,
            "url": self.url,
            "service_id": self.service_id,
        }


class AmanahVault:
    """
    Credential Vault — inspired by Amanah (أَمَانَة — Trust)
    "Indeed, Allah commands you to return trusts (Amanah) to their owners" — 4:58

    Secure in-memory credential storage with encryption references.
    Never logs or exposes secrets. Only returns masked versions.
    """

    def __init__(self):
        self._secrets: dict[str, str] = {}  # key -> value
        self._metadata: dict[str, dict] = {}

    def store(self, key: str, value: str, meta: dict = None) -> str:
        """Store a secret — returns masked reference"""
        secret_id = hashlib.sha256(key.encode()).hexdigest()[:12]
        self._secrets[secret_id] = value
        self._metadata[secret_id] = {
            "key": key,
            "stored_at": datetime.now(UTC).isoformat(),
            "masked": value[:4] + "****" + value[-4:] if len(value) > 8 else "****",
            **(meta or {}),
        }
        logger.info(f"[AMANAH] Secret stored: {key} -> {secret_id}")
        return secret_id

    def retrieve(self, secret_id: str) -> str | None:
        """Retrieve a secret by ID — never log the value"""
        return self._secrets.get(secret_id)

    def list_secrets(self) -> list[dict]:
        """List stored secrets (masked, never the actual values)"""
        return [
            {
                "id": sid,
                "key": meta["key"],
                "masked": meta["masked"],
                "stored_at": meta["stored_at"],
            }
            for sid, meta in self._metadata.items()
        ]

    def delete(self, secret_id: str) -> bool:
        if secret_id in self._secrets:
            del self._secrets[secret_id]
            del self._metadata[secret_id]
            return True
        return False


class SahabCloudSkill(SkillBase):
    """
    Sahab — Cloud Integration Hub
    "He sends down from the sky rain (provision)" — 24:43
    """

    manifest = SkillManifest(
        name="sahab_cloud",
        version="1.0.0",
        description="Cloud integration hub for GitHub, Docker, APIs, and services. "
        "Manage repositories, containers, credentials, and API chains.",
        permissions=[
            "network:https://*",
            "shell:git",
            "shell:docker",
            "credentials:read",
            "credentials:write",
        ],
        tags=["سحاب", "Cloud"],
    )

    def __init__(self, config: dict = None):
        super().__init__(config)
        self.services: dict[str, CloudService] = {}
        self.endpoints: dict[str, ApiEndpoint] = {}
        self.vault = AmanahVault()
        self._tools = {
            "cloud_register_service": self.register_service,
            "cloud_list_services": self.list_services,
            "cloud_check_health": self.check_health,
            "cloud_git_clone": self.git_clone,
            "cloud_git_status": self.git_status,
            "cloud_git_commit": self.git_commit,
            "cloud_git_push": self.git_push,
            "cloud_docker_list": self.docker_list,
            "cloud_docker_build": self.docker_build,
            "cloud_docker_run": self.docker_run,
            "cloud_docker_stop": self.docker_stop,
            "cloud_api_call": self.api_call,
            "cloud_api_chain": self.api_chain,
            "cloud_vault_store": self.vault_store,
            "cloud_vault_list": self.vault_list,
            "cloud_vault_delete": self.vault_delete,
        }

    async def execute(self, params: dict, context: dict = None) -> dict:
        action = params.get("action", "list_services")
        handler = self._tools.get(f"cloud_{action}")
        if handler:
            return await handler(params)
        return {"error": f"Unknown action: {action}"}

    # === SERVICE MANAGEMENT ===

    async def register_service(self, params: dict) -> dict:
        """Register a cloud service"""
        svc = CloudService(
            name=params.get("name", ""),
            service_type=params.get("service_type", "api"),
            base_url=params.get("base_url", ""),
            metadata=params.get("metadata", {}),
        )
        self.services[svc.id] = svc
        logger.info(f"[SAHAB] Service registered: {svc.name} ({svc.service_type})")
        return svc.to_dict()

    async def list_services(self, params: dict = None) -> dict:
        return {"services": [s.to_dict() for s in self.services.values()]}

    async def check_health(self, params: dict) -> dict:
        """Check service health — Basir (All-Seeing) monitoring"""
        import httpx

        results = []
        for svc in self.services.values():
            if svc.base_url:
                try:
                    async with httpx.AsyncClient(timeout=10) as client:
                        resp = await client.get(svc.base_url)
                        svc.status = "connected" if resp.status_code < 500 else "error"
                        svc.last_check = datetime.now(UTC).isoformat()
                        results.append(
                            {
                                "service": svc.name,
                                "status": svc.status,
                                "status_code": resp.status_code,
                            }
                        )
                except Exception as e:
                    svc.status = "error"
                    svc.last_check = datetime.now(UTC).isoformat()
                    results.append({"service": svc.name, "status": "error", "error": str(e)})
        return {"health_checks": results, "timestamp": datetime.now(UTC).isoformat()}

    # === GIT OPERATIONS — "By the pen and what they inscribe" (68:1) ===

    async def git_clone(self, params: dict) -> dict:
        """Clone a repository"""
        url = params.get("url", "")
        dest = params.get("destination", "")
        if not url:
            return {"error": "URL required"}

        # Security: validate URL
        if not url.startswith(("https://", "git@")):
            return {"error": "Only HTTPS and SSH git URLs allowed"}

        # Sanitize destination
        safe_dest = dest.replace("..", "").replace("~", "") if dest else ""
        if not safe_dest:
            safe_dest = f"/tmp/mizan_repos/{url.split('/')[-1].replace('.git', '')}"

        os.makedirs(os.path.dirname(safe_dest), exist_ok=True)

        try:
            proc = subprocess.run(
                ["git", "clone", "--depth=1", url, safe_dest],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if proc.returncode == 0:
                return {"cloned": url, "destination": safe_dest, "success": True}
            return {"error": proc.stderr, "success": False}
        except subprocess.TimeoutExpired:
            return {"error": "Clone timed out"}

    async def git_status(self, params: dict) -> dict:
        """Check git status of a repository"""
        repo_path = params.get("repo_path", "")
        if not repo_path or ".." in repo_path:
            return {"error": "Invalid path"}
        try:
            proc = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=repo_path,
            )
            branch = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=repo_path,
            )
            return {
                "path": repo_path,
                "branch": branch.stdout.strip(),
                "changes": proc.stdout.strip().split("\n") if proc.stdout.strip() else [],
                "clean": proc.stdout.strip() == "",
            }
        except Exception as e:
            return {"error": str(e)}

    async def git_commit(self, params: dict) -> dict:
        """Create a git commit"""
        repo_path = params.get("repo_path", "")
        message = params.get("message", "Update via MIZAN")
        if not repo_path:
            return {"error": "repo_path required"}
        try:
            subprocess.run(["git", "add", "-A"], cwd=repo_path, timeout=30)
            proc = subprocess.run(
                ["git", "commit", "-m", message],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=repo_path,
            )
            return {"success": proc.returncode == 0, "output": proc.stdout + proc.stderr}
        except Exception as e:
            return {"error": str(e)}

    async def git_push(self, params: dict) -> dict:
        """Push to remote"""
        repo_path = params.get("repo_path", "")
        remote = params.get("remote", "origin")
        branch = params.get("branch", "")
        if not repo_path:
            return {"error": "repo_path required"}
        try:
            cmd = ["git", "push", remote]
            if branch:
                cmd.append(branch)
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                cwd=repo_path,
            )
            return {"success": proc.returncode == 0, "output": proc.stdout + proc.stderr}
        except Exception as e:
            return {"error": str(e)}

    # === DOCKER OPERATIONS — Cloud container orchestration ===

    async def docker_list(self, params: dict = None) -> dict:
        """List Docker containers"""
        try:
            proc = subprocess.run(
                ["docker", "ps", "-a", "--format", "{{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            containers = []
            for line in proc.stdout.strip().split("\n"):
                if line.strip():
                    parts = line.split("\t")
                    if len(parts) >= 4:
                        containers.append(
                            {
                                "id": parts[0],
                                "name": parts[1],
                                "image": parts[2],
                                "status": parts[3],
                            }
                        )
            return {"containers": containers}
        except FileNotFoundError:
            return {"error": "Docker not installed", "containers": []}
        except Exception as e:
            return {"error": str(e)}

    async def docker_build(self, params: dict) -> dict:
        """Build a Docker image"""
        context_path = params.get("context_path", ".")
        tag = params.get("tag", "mizan-app:latest")
        if ".." in context_path:
            return {"error": "Invalid path"}
        try:
            proc = subprocess.run(
                ["docker", "build", "-t", tag, context_path],
                capture_output=True,
                text=True,
                timeout=300,
            )
            return {
                "success": proc.returncode == 0,
                "output": proc.stdout[-2000:] + proc.stderr[-2000:],
            }
        except FileNotFoundError:
            return {"error": "Docker not installed"}
        except Exception as e:
            return {"error": str(e)}

    async def docker_run(self, params: dict) -> dict:
        """Run a Docker container"""
        image = params.get("image", "")
        name = params.get("name", "")
        ports = params.get("ports", {})
        envs = params.get("env", {})
        if not image:
            return {"error": "image required"}
        try:
            cmd = ["docker", "run", "-d"]
            if name:
                cmd.extend(["--name", name])
            for host_port, container_port in ports.items():
                cmd.extend(["-p", f"{host_port}:{container_port}"])
            for k, v in envs.items():
                cmd.extend(["-e", f"{k}={v}"])
            cmd.append(image)
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            return {
                "success": proc.returncode == 0,
                "container_id": proc.stdout.strip()[:12],
                "output": proc.stderr,
            }
        except FileNotFoundError:
            return {"error": "Docker not installed"}
        except Exception as e:
            return {"error": str(e)}

    async def docker_stop(self, params: dict) -> dict:
        """Stop a Docker container"""
        container = params.get("container", "")
        if not container:
            return {"error": "container name/id required"}
        try:
            proc = subprocess.run(
                ["docker", "stop", container],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return {"success": proc.returncode == 0, "stopped": container}
        except Exception as e:
            return {"error": str(e)}

    # === API OPERATIONS — Data flows like rain ===

    async def api_call(self, params: dict) -> dict:
        """Make an API call — 'He sends down rain from the sky' (24:43)"""
        import httpx

        method = params.get("method", "GET").upper()
        url = params.get("url", "")
        headers = params.get("headers", {})
        body = params.get("body")
        timeout = min(params.get("timeout", 30), 60)

        if not url:
            return {"error": "URL required"}
        if not url.startswith("https://"):
            return {"error": "Only HTTPS URLs allowed for security"}

        # Inject credentials from vault if referenced
        for key, val in headers.items():
            if isinstance(val, str) and val.startswith("vault:"):
                secret_id = val[6:]
                secret = self.vault.retrieve(secret_id)
                if secret:
                    headers[key] = secret
                else:
                    return {"error": f"Vault secret not found: {secret_id}"}

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                if method == "GET":
                    resp = await client.get(url, headers=headers)
                elif method == "POST":
                    resp = await client.post(url, headers=headers, json=body)
                elif method == "PUT":
                    resp = await client.put(url, headers=headers, json=body)
                elif method == "DELETE":
                    resp = await client.delete(url, headers=headers)
                else:
                    return {"error": f"Unsupported method: {method}"}

                try:
                    response_body = resp.json()
                except Exception:
                    response_body = resp.text[:5000]

                return {
                    "status_code": resp.status_code,
                    "headers": dict(resp.headers),
                    "body": response_body,
                }
        except Exception as e:
            return {"error": str(e)}

    async def api_chain(self, params: dict) -> dict:
        """Chain multiple API calls — like clouds gathering into rain"""
        steps = params.get("steps", [])
        results = []
        context = {}

        for i, step in enumerate(steps):
            # Replace {prev.field} references with previous results
            url = step.get("url", "")
            for key, val in context.items():
                url = url.replace(f"{{{key}}}", str(val))

            step["url"] = url
            result = await self.api_call(step)
            results.append({"step": i, "result": result})

            # Store result fields for next step
            if isinstance(result.get("body"), dict):
                for k, v in result["body"].items():
                    context[f"step{i}.{k}"] = v

            if result.get("error"):
                break

        return {"chain_results": results, "steps_completed": len(results)}

    # === VAULT OPERATIONS — Amanah (Trust) ===

    async def vault_store(self, params: dict) -> dict:
        """Store a secret in the vault"""
        key = params.get("key", "")
        value = params.get("value", "")
        if not key or not value:
            return {"error": "key and value required"}
        secret_id = self.vault.store(key, value)
        return {"stored": True, "secret_id": secret_id, "key": key}

    async def vault_list(self, params: dict = None) -> dict:
        """List vault secrets (masked)"""
        return {"secrets": self.vault.list_secrets()}

    async def vault_delete(self, params: dict) -> dict:
        """Delete a secret from vault"""
        secret_id = params.get("secret_id", "")
        if self.vault.delete(secret_id):
            return {"deleted": secret_id}
        return {"error": "Secret not found"}

    def get_tool_schemas(self) -> list[dict]:
        return [
            {
                "name": "cloud_register_service",
                "description": "Register a cloud service (GitHub, Docker, API, etc.)",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "service_type": {
                            "type": "string",
                            "enum": ["github", "docker", "api", "database", "storage"],
                        },
                        "base_url": {"type": "string"},
                    },
                    "required": ["name", "service_type"],
                },
            },
            {
                "name": "cloud_list_services",
                "description": "List all registered cloud services",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "cloud_check_health",
                "description": "Check health of all registered services",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "cloud_git_clone",
                "description": "Clone a git repository",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                        "destination": {"type": "string"},
                    },
                    "required": ["url"],
                },
            },
            {
                "name": "cloud_git_status",
                "description": "Check git status of a repository",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "repo_path": {"type": "string"},
                    },
                    "required": ["repo_path"],
                },
            },
            {
                "name": "cloud_docker_list",
                "description": "List Docker containers",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "cloud_docker_run",
                "description": "Run a Docker container",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "image": {"type": "string"},
                        "name": {"type": "string"},
                        "ports": {"type": "object"},
                        "env": {"type": "object"},
                    },
                    "required": ["image"],
                },
            },
            {
                "name": "cloud_api_call",
                "description": "Make an HTTP API call",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE"]},
                        "url": {"type": "string"},
                        "headers": {"type": "object"},
                        "body": {"type": "object"},
                    },
                    "required": ["url"],
                },
            },
            {
                "name": "cloud_api_chain",
                "description": "Chain multiple API calls together",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "steps": {"type": "array", "items": {"type": "object"}},
                    },
                    "required": ["steps"],
                },
            },
            {
                "name": "cloud_vault_store",
                "description": "Store a credential securely in the vault",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string"},
                        "value": {"type": "string"},
                    },
                    "required": ["key", "value"],
                },
            },
            {
                "name": "cloud_vault_list",
                "description": "List stored credentials (masked values)",
                "input_schema": {"type": "object", "properties": {}},
            },
        ]
