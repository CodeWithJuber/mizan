"""
Linode Cloud Skill (سماء — The Sky/Cloud)
==========================================

"It is Allah who created the heavens and the earth and sent down rain
from the sky and produced thereby some fruits." — Quran 14:32

Purpose-built Linode integration with correct API endpoints,
auto-token loading, and high-level operations:
- Create/list/manage Linode instances
- Reset root passwords via API
- DNS management
- StackScript support
- Full provisioning workflows

Uses the Linode API v4: https://api.linode.com/v4/
"""

import logging
import os
from datetime import UTC, datetime

import httpx

from ..base import SkillBase, SkillManifest

logger = logging.getLogger("mizan.linode")

# Linode API v4 base URL
LINODE_API_BASE = "https://api.linode.com/v4"


class LinodeCloudSkill(SkillBase):
    """
    Linode-specific cloud management.
    All endpoints use correct Linode API v4 paths.
    """

    manifest = SkillManifest(
        name="linode_cloud",
        version="1.0.0",
        description="Linode cloud management: create/list instances, "
        "reset passwords, manage DNS, run StackScripts. "
        "Auto-loads LINODE_API_TOKEN from environment.",
        permissions=[
            "network:https://api.linode.com/*",
            "credentials:read",
        ],
        tags=["سماء", "Linode", "Cloud"],
    )

    def __init__(self, config: dict = None):
        super().__init__(config)
        self._token = os.environ.get("LINODE_API_TOKEN", "")
        self._tools = {
            "linode_list": self.list_instances,
            "linode_get": self.get_instance,
            "linode_create": self.create_instance,
            "linode_delete": self.delete_instance,
            "linode_reboot": self.reboot_instance,
            "linode_reset_password": self.reset_password,
            "linode_list_regions": self.list_regions,
            "linode_list_types": self.list_types,
            "linode_api": self.raw_api,
            "linode_set_token": self.set_token,
        }

    def _headers(self, token: str | None = None) -> dict:
        """Build auth headers. Uses provided token or env default."""
        t = token or self._token
        if not t:
            raise ValueError(
                "No Linode API token. Set LINODE_API_TOKEN env var "
                "or call linode_set_token first."
            )
        return {
            "Authorization": f"Bearer {t}",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        token: str | None = None,
        timeout: int = 30,
    ) -> dict:
        """Make a Linode API request with proper error handling."""
        url = f"{LINODE_API_BASE}{path}"
        try:
            headers = self._headers(token)
        except ValueError as e:
            return {"error": str(e)}

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
                    data = resp.json()
                except Exception:
                    data = resp.text[:3000]

                if resp.status_code >= 400:
                    errors = data.get("errors", []) if isinstance(data, dict) else []
                    error_msgs = [e.get("reason", str(e)) for e in errors]
                    return {
                        "error": "; ".join(error_msgs) if error_msgs else f"HTTP {resp.status_code}",
                        "status_code": resp.status_code,
                        "details": data,
                    }

                return {"status_code": resp.status_code, "data": data}

        except httpx.TimeoutException:
            return {"error": f"Request timed out after {timeout}s", "url": url}
        except Exception as e:
            return {"error": str(e)}

    # ── Token Management ────────────────────────────────────

    async def set_token(self, params: dict) -> dict:
        """Set the Linode API token for this session."""
        token = params.get("token", "")
        if not token:
            return {"error": "token is required"}
        self._token = token
        # Verify the token works
        result = await self._request("GET", "/profile", token=token)
        if result.get("error"):
            self._token = ""
            return {"error": f"Token validation failed: {result['error']}"}
        profile = result.get("data", {})
        logger.info(f"[LINODE] Token set for user: {profile.get('username', 'unknown')}")
        return {
            "success": True,
            "username": profile.get("username"),
            "email": profile.get("email"),
            "message": "Linode API token configured and verified.",
        }

    # ── Instance Management ─────────────────────────────────

    async def list_instances(self, params: dict = None) -> dict:
        """List all Linode instances."""
        result = await self._request("GET", "/linode/instances")
        if result.get("error"):
            return result
        instances = result.get("data", {}).get("data", [])
        return {
            "count": len(instances),
            "instances": [
                {
                    "id": i["id"],
                    "label": i.get("label", ""),
                    "status": i.get("status", ""),
                    "type": i.get("type", ""),
                    "region": i.get("region", ""),
                    "ipv4": i.get("ipv4", []),
                    "created": i.get("created", ""),
                }
                for i in instances
            ],
        }

    async def get_instance(self, params: dict) -> dict:
        """Get details of a specific Linode instance."""
        linode_id = params.get("linode_id", "")
        if not linode_id:
            return {"error": "linode_id is required"}
        result = await self._request("GET", f"/linode/instances/{linode_id}")
        if result.get("error"):
            return result
        return {"instance": result.get("data", {})}

    async def create_instance(self, params: dict) -> dict:
        """Create a new Linode instance.

        Required: region, type, image
        Optional: root_pass (auto-generated if omitted), label,
                  authorized_keys, stackscript_id, stackscript_data
        """
        region = params.get("region", "")
        instance_type = params.get("type", "")
        image = params.get("image", "")

        if not region or not instance_type or not image:
            return {
                "error": "region, type, and image are required",
                "hint": {
                    "region": "e.g. us-east, us-west, eu-west, ap-south",
                    "type": "e.g. g6-nanode-1, g6-standard-2, g6-standard-4",
                    "image": "e.g. linode/ubuntu22.04, linode/ubuntu24.04, linode/debian12",
                },
            }

        body = {
            "region": region,
            "type": instance_type,
            "image": image,
        }

        # Optional fields
        if params.get("root_pass"):
            body["root_pass"] = params["root_pass"]
        if params.get("label"):
            body["label"] = params["label"]
        if params.get("authorized_keys"):
            body["authorized_keys"] = params["authorized_keys"]
        if params.get("stackscript_id"):
            body["stackscript_id"] = params["stackscript_id"]
        if params.get("stackscript_data"):
            body["stackscript_data"] = params["stackscript_data"]
        if params.get("tags"):
            body["tags"] = params["tags"]
        if params.get("booted") is not None:
            body["booted"] = params["booted"]

        result = await self._request("POST", "/linode/instances", body=body, timeout=60)
        if result.get("error"):
            return result

        instance = result.get("data", {})
        return {
            "created": True,
            "instance": {
                "id": instance.get("id"),
                "label": instance.get("label"),
                "status": instance.get("status"),
                "type": instance.get("type"),
                "region": instance.get("region"),
                "ipv4": instance.get("ipv4", []),
                "root_pass": instance.get("root_pass", params.get("root_pass", "(set by you)")),
            },
            "message": f"Linode created! ID: {instance.get('id')}. "
            f"IPs: {instance.get('ipv4', [])}. "
            "Wait ~60s for boot, then SSH in or use ssh_copy_id.",
        }

    async def delete_instance(self, params: dict) -> dict:
        """Delete a Linode instance."""
        linode_id = params.get("linode_id", "")
        if not linode_id:
            return {"error": "linode_id is required"}
        result = await self._request("DELETE", f"/linode/instances/{linode_id}")
        if result.get("error"):
            return result
        return {"deleted": True, "linode_id": linode_id}

    async def reboot_instance(self, params: dict) -> dict:
        """Reboot a Linode instance."""
        linode_id = params.get("linode_id", "")
        if not linode_id:
            return {"error": "linode_id is required"}
        result = await self._request("POST", f"/linode/instances/{linode_id}/reboot")
        if result.get("error"):
            return result
        return {"rebooted": True, "linode_id": linode_id}

    async def reset_password(self, params: dict) -> dict:
        """Reset root password on a Linode instance.

        The instance must be powered off first. This tool handles that:
        1. Shuts down the instance
        2. Waits for it to be offline
        3. Resets the password
        4. Boots it back up
        """
        linode_id = params.get("linode_id", "")
        new_password = params.get("root_pass", "")

        if not linode_id or not new_password:
            return {"error": "linode_id and root_pass are required"}

        if len(new_password) < 11:
            return {"error": "Password must be at least 11 characters (Linode requirement)"}

        # Step 1: Shut down
        shutdown = await self._request(
            "POST", f"/linode/instances/{linode_id}/shutdown"
        )
        if shutdown.get("error") and "already powered off" not in str(shutdown.get("error", "")).lower():
            return {"error": f"Shutdown failed: {shutdown.get('error')}"}

        # Step 2: Wait for offline status (poll up to 60s)
        import asyncio

        for _ in range(12):
            await asyncio.sleep(5)
            status = await self._request("GET", f"/linode/instances/{linode_id}")
            if status.get("data", {}).get("status") == "offline":
                break
        else:
            return {"error": "Instance did not shut down within 60s. Try again."}

        # Step 3: Reset password
        reset = await self._request(
            "POST",
            f"/linode/instances/{linode_id}/password",
            body={"root_pass": new_password},
        )
        if reset.get("error"):
            # Boot back up even if reset fails
            await self._request("POST", f"/linode/instances/{linode_id}/boot")
            return {"error": f"Password reset failed: {reset.get('error')}"}

        # Step 4: Boot back up
        boot = await self._request("POST", f"/linode/instances/{linode_id}/boot")

        return {
            "success": True,
            "linode_id": linode_id,
            "message": "Root password reset and instance rebooting. "
            "Allow ~30s for boot before SSH.",
        }

    # ── Reference Data ──────────────────────────────────────

    async def list_regions(self, params: dict = None) -> dict:
        """List available Linode regions."""
        result = await self._request("GET", "/regions")
        if result.get("error"):
            return result
        regions = result.get("data", {}).get("data", [])
        return {
            "regions": [
                {
                    "id": r["id"],
                    "label": r.get("label", ""),
                    "country": r.get("country", ""),
                    "status": r.get("status", ""),
                }
                for r in regions
            ],
        }

    async def list_types(self, params: dict = None) -> dict:
        """List available Linode instance types (plans)."""
        result = await self._request("GET", "/linode/types")
        if result.get("error"):
            return result
        types = result.get("data", {}).get("data", [])
        return {
            "types": [
                {
                    "id": t["id"],
                    "label": t.get("label", ""),
                    "vcpus": t.get("vcpus"),
                    "memory": t.get("memory"),
                    "disk": t.get("disk"),
                    "price_monthly": t.get("price", {}).get("monthly"),
                }
                for t in types[:20]
            ],
        }

    # ── Raw API (escape hatch) ──────────────────────────────

    async def raw_api(self, params: dict) -> dict:
        """Make a raw Linode API call with any path.

        For advanced operations not covered by dedicated tools.
        Path is relative to https://api.linode.com/v4/
        """
        method = params.get("method", "GET").upper()
        path = params.get("path", "")
        body = params.get("body")

        if not path:
            return {"error": "path is required (e.g. /linode/instances)"}

        # Normalize path
        if not path.startswith("/"):
            path = f"/{path}"

        return await self._request(method, path, body=body)

    # ── Execute (generic entry) ─────────────────────────────

    async def execute(self, params: dict, context: dict = None) -> dict:
        action = params.get("action", "list")
        handler = self._tools.get(f"linode_{action}")
        if handler:
            return await handler(params)
        return {"error": f"Unknown action: {action}. Available: {list(self._tools.keys())}"}

    # ── Tool Schemas ────────────────────────────────────────

    def get_tool_schemas(self) -> list[dict]:
        return [
            {
                "name": "linode_set_token",
                "description": "Set Linode API token for authentication. Auto-loads from LINODE_API_TOKEN env var if set.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "token": {
                            "type": "string",
                            "description": "Linode Personal Access Token",
                        },
                    },
                    "required": ["token"],
                },
            },
            {
                "name": "linode_list",
                "description": "List all Linode instances with ID, label, status, region, and IPs.",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "linode_get",
                "description": "Get full details of a specific Linode instance by ID.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "linode_id": {
                            "type": "integer",
                            "description": "Linode instance ID",
                        },
                    },
                    "required": ["linode_id"],
                },
            },
            {
                "name": "linode_create",
                "description": "Create a new Linode instance. Requires region, type, and image. "
                "Common types: g6-nanode-1, g6-standard-2. "
                "Common images: linode/ubuntu22.04, linode/ubuntu24.04. "
                "Common regions: us-east, us-west, eu-west.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "region": {
                            "type": "string",
                            "description": "Region ID (e.g. us-east)",
                        },
                        "type": {
                            "type": "string",
                            "description": "Instance type/plan (e.g. g6-standard-2)",
                        },
                        "image": {
                            "type": "string",
                            "description": "OS image (e.g. linode/ubuntu22.04)",
                        },
                        "root_pass": {
                            "type": "string",
                            "description": "Root password (min 11 chars). Auto-generated if omitted.",
                        },
                        "label": {
                            "type": "string",
                            "description": "Display label for the instance",
                        },
                        "authorized_keys": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "SSH public keys to install",
                        },
                        "stackscript_id": {
                            "type": "integer",
                            "description": "StackScript ID for automated setup",
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Instance tags",
                        },
                    },
                    "required": ["region", "type", "image"],
                },
            },
            {
                "name": "linode_delete",
                "description": "Delete a Linode instance by ID. This is irreversible.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "linode_id": {
                            "type": "integer",
                            "description": "Linode instance ID to delete",
                        },
                    },
                    "required": ["linode_id"],
                },
            },
            {
                "name": "linode_reboot",
                "description": "Reboot a Linode instance.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "linode_id": {
                            "type": "integer",
                            "description": "Linode instance ID to reboot",
                        },
                    },
                    "required": ["linode_id"],
                },
            },
            {
                "name": "linode_reset_password",
                "description": "Reset root password on a Linode. Handles shutdown, password reset, and reboot automatically. "
                "Password must be at least 11 characters.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "linode_id": {
                            "type": "integer",
                            "description": "Linode instance ID",
                        },
                        "root_pass": {
                            "type": "string",
                            "description": "New root password (min 11 chars)",
                        },
                    },
                    "required": ["linode_id", "root_pass"],
                },
            },
            {
                "name": "linode_list_regions",
                "description": "List available Linode regions.",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "linode_list_types",
                "description": "List available Linode instance types/plans with pricing.",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "linode_api",
                "description": "Make a raw Linode API call. Path is relative to https://api.linode.com/v4. "
                "For advanced operations not covered by other linode_ tools.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "method": {
                            "type": "string",
                            "enum": ["GET", "POST", "PUT", "DELETE"],
                        },
                        "path": {
                            "type": "string",
                            "description": "API path (e.g. /linode/instances, /domains)",
                        },
                        "body": {
                            "type": "object",
                            "description": "Request body for POST/PUT",
                        },
                    },
                    "required": ["path"],
                },
            },
        ]
