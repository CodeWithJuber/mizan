"""
Izn (إِذْن) — Permission System
=================================

"None can intercede with Him except with His permission (Izn)" — Quran 2:255

Per-tool, per-agent permission model.
Solves OpenClaw's skill data exfiltration problem.
"""

import os
from datetime import datetime
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
import logging

logger = logging.getLogger("mizan.izn")


class PermissionLevel(Enum):
    """Permission levels for tool access"""
    DENIED = "denied"           # Tool blocked entirely
    APPROVAL_REQUIRED = "approval_required"  # Needs human approval each time
    RESTRICTED = "restricted"   # Allowed with constraints
    ALLOWED = "allowed"         # Fully allowed


# ── 7-Level Nafs Permission Mapping ──────────────────────────────
# Each Nafs level unlocks progressively more capabilities.
# Agents must earn trust through performance to access higher permissions.

NAFS_PERMISSION_TIERS: Dict[int, Dict[str, "PermissionLevel"]] = {
    1: {  # Ammara — Raw, untrained
        "bash": PermissionLevel.DENIED,
        "http_get": PermissionLevel.RESTRICTED,
        "http_post": PermissionLevel.DENIED,
        "read_file": PermissionLevel.RESTRICTED,
        "write_file": PermissionLevel.DENIED,
        "python_exec": PermissionLevel.DENIED,
    },
    2: {  # Lawwama — Self-correcting
        "bash": PermissionLevel.DENIED,
        "http_get": PermissionLevel.ALLOWED,
        "http_post": PermissionLevel.RESTRICTED,
        "read_file": PermissionLevel.ALLOWED,
        "write_file": PermissionLevel.APPROVAL_REQUIRED,
        "python_exec": PermissionLevel.DENIED,
    },
    3: {  # Mulhama — Inspired
        "bash": PermissionLevel.APPROVAL_REQUIRED,
        "http_get": PermissionLevel.ALLOWED,
        "http_post": PermissionLevel.RESTRICTED,
        "read_file": PermissionLevel.ALLOWED,
        "write_file": PermissionLevel.RESTRICTED,
        "python_exec": PermissionLevel.APPROVAL_REQUIRED,
    },
    4: {  # Mutmainna — Tranquil
        "bash": PermissionLevel.RESTRICTED,
        "http_get": PermissionLevel.ALLOWED,
        "http_post": PermissionLevel.ALLOWED,
        "read_file": PermissionLevel.ALLOWED,
        "write_file": PermissionLevel.ALLOWED,
        "python_exec": PermissionLevel.RESTRICTED,
    },
    5: {  # Radiya — Content
        "bash": PermissionLevel.ALLOWED,
        "http_get": PermissionLevel.ALLOWED,
        "http_post": PermissionLevel.ALLOWED,
        "read_file": PermissionLevel.ALLOWED,
        "write_file": PermissionLevel.ALLOWED,
        "python_exec": PermissionLevel.RESTRICTED,
    },
    6: {  # Mardiyya — Pleasing
        "bash": PermissionLevel.ALLOWED,
        "http_get": PermissionLevel.ALLOWED,
        "http_post": PermissionLevel.ALLOWED,
        "read_file": PermissionLevel.ALLOWED,
        "write_file": PermissionLevel.ALLOWED,
        "python_exec": PermissionLevel.ALLOWED,
    },
    7: {  # Kamila — Perfect
        "bash": PermissionLevel.ALLOWED,
        "http_get": PermissionLevel.ALLOWED,
        "http_post": PermissionLevel.ALLOWED,
        "read_file": PermissionLevel.ALLOWED,
        "write_file": PermissionLevel.ALLOWED,
        "python_exec": PermissionLevel.ALLOWED,
    },
}


@dataclass
class ToolPermission:
    """Permission definition for a specific tool"""
    tool_name: str
    level: PermissionLevel = PermissionLevel.RESTRICTED
    allowed_params: Dict[str, List[str]] = field(default_factory=dict)
    blocked_params: Dict[str, List[str]] = field(default_factory=dict)
    max_calls_per_minute: int = 30
    description: str = ""


@dataclass
class IznPolicy:
    """
    Permission policy for an agent or skill.
    Defines what tools can be used and with what constraints.
    """
    id: str = ""
    name: str = ""
    tool_permissions: Dict[str, ToolPermission] = field(default_factory=dict)
    allowed_file_paths: List[str] = field(default_factory=list)
    allowed_urls: List[str] = field(default_factory=list)
    blocked_urls: List[str] = field(default_factory=list)
    max_memory_mb: int = 100
    max_execution_seconds: int = 60
    can_create_files: bool = True
    can_network_access: bool = True
    can_execute_code: bool = False

    def get_tool_permission(self, tool_name: str) -> ToolPermission:
        if tool_name in self.tool_permissions:
            return self.tool_permissions[tool_name]
        # Default: restricted
        return ToolPermission(
            tool_name=tool_name,
            level=PermissionLevel.RESTRICTED,
        )


class IznPermission:
    """
    Central permission manager.
    Checks every tool invocation against the agent's IznPolicy.
    """

    # Default policies by agent role
    DEFAULT_POLICIES = {
        "wakil": {
            "bash": PermissionLevel.RESTRICTED,
            "http_get": PermissionLevel.ALLOWED,
            "http_post": PermissionLevel.RESTRICTED,
            "read_file": PermissionLevel.RESTRICTED,
            "write_file": PermissionLevel.RESTRICTED,
            "list_files": PermissionLevel.ALLOWED,
            "python_eval": PermissionLevel.DENIED,
        },
        "mubashir": {
            "bash": PermissionLevel.DENIED,
            "browse_url": PermissionLevel.ALLOWED,
            "search_web": PermissionLevel.ALLOWED,
            "extract_content": PermissionLevel.ALLOWED,
            "take_screenshot": PermissionLevel.RESTRICTED,
            "http_get": PermissionLevel.ALLOWED,
            "read_file": PermissionLevel.RESTRICTED,
            "write_file": PermissionLevel.DENIED,
        },
        "mundhir": {
            "bash": PermissionLevel.DENIED,
            "analyze_text": PermissionLevel.ALLOWED,
            "synthesize_sources": PermissionLevel.ALLOWED,
            "fact_check": PermissionLevel.ALLOWED,
            "generate_report": PermissionLevel.ALLOWED,
            "arxiv_search": PermissionLevel.ALLOWED,
            "http_get": PermissionLevel.ALLOWED,
            "read_file": PermissionLevel.ALLOWED,
            "write_file": PermissionLevel.RESTRICTED,
        },
        "katib": {
            "bash": PermissionLevel.RESTRICTED,
            "generate_code": PermissionLevel.ALLOWED,
            "run_tests": PermissionLevel.ALLOWED,
            "lint_code": PermissionLevel.ALLOWED,
            "git_operation": PermissionLevel.RESTRICTED,
            "install_package": PermissionLevel.APPROVAL_REQUIRED,
            "read_file": PermissionLevel.ALLOWED,
            "write_file": PermissionLevel.RESTRICTED,
        },
        "rasul": {
            "bash": PermissionLevel.DENIED,
            "send_webhook": PermissionLevel.RESTRICTED,
            "check_email": PermissionLevel.RESTRICTED,
            "send_notification": PermissionLevel.ALLOWED,
            "http_post": PermissionLevel.RESTRICTED,
        },
    }

    def __init__(self):
        self._policies: Dict[str, IznPolicy] = {}
        self._call_counts: Dict[str, Dict[str, List[float]]] = {}
        self._pending_approvals: Dict[str, Dict] = {}

    def get_policy(self, agent_id: str, agent_role: str = "wakil") -> IznPolicy:
        """Get or create policy for an agent"""
        if agent_id in self._policies:
            return self._policies[agent_id]

        # Create default policy based on role
        policy = IznPolicy(
            id=agent_id,
            name=f"policy_{agent_role}",
        )

        defaults = self.DEFAULT_POLICIES.get(agent_role, self.DEFAULT_POLICIES["wakil"])
        for tool_name, level in defaults.items():
            policy.tool_permissions[tool_name] = ToolPermission(
                tool_name=tool_name,
                level=level,
            )

        self._policies[agent_id] = policy
        return policy

    def check_permission(self, agent_id: str, agent_role: str,
                         tool_name: str, params: Dict = None) -> Dict:
        """
        Check if an agent has permission to use a tool.

        Returns:
            {"allowed": bool, "reason": str, "requires_approval": bool}
        """
        policy = self.get_policy(agent_id, agent_role)
        tool_perm = policy.get_tool_permission(tool_name)

        # Check permission level
        if tool_perm.level == PermissionLevel.DENIED:
            logger.warning(f"[IZN] DENIED: agent={agent_id} tool={tool_name}")
            return {
                "allowed": False,
                "reason": f"Tool '{tool_name}' is denied for role '{agent_role}'",
                "requires_approval": False,
            }

        if tool_perm.level == PermissionLevel.APPROVAL_REQUIRED:
            approval_key = f"{agent_id}:{tool_name}"
            if approval_key not in self._pending_approvals:
                self._pending_approvals[approval_key] = {
                    "agent_id": agent_id,
                    "tool": tool_name,
                    "params": params,
                    "requested_at": datetime.utcnow().isoformat(),
                }
            return {
                "allowed": False,
                "reason": f"Tool '{tool_name}' requires human approval",
                "requires_approval": True,
            }

        # Check rate limit for tool
        if not self._check_tool_rate(agent_id, tool_name, tool_perm.max_calls_per_minute):
            return {
                "allowed": False,
                "reason": f"Rate limit exceeded for tool '{tool_name}'",
                "requires_approval": False,
            }

        # Check parameter restrictions
        if params and tool_perm.blocked_params:
            for param_name, blocked_values in tool_perm.blocked_params.items():
                if param_name in params:
                    param_val = str(params[param_name])
                    if any(bv in param_val for bv in blocked_values):
                        return {
                            "allowed": False,
                            "reason": f"Blocked parameter value in '{param_name}'",
                            "requires_approval": False,
                        }

        return {
            "allowed": True,
            "reason": "Permitted",
            "requires_approval": False,
        }

    def approve_pending(self, approval_key: str) -> bool:
        """Approve a pending tool execution"""
        if approval_key in self._pending_approvals:
            del self._pending_approvals[approval_key]
            return True
        return False

    def get_pending_approvals(self) -> List[Dict]:
        """Get all pending approvals"""
        return list(self._pending_approvals.values())

    def _check_tool_rate(self, agent_id: str, tool_name: str,
                         max_per_minute: int) -> bool:
        """Check tool-specific rate limit"""
        import time
        now = time.time()
        key = f"{agent_id}:{tool_name}"

        if key not in self._call_counts:
            self._call_counts[key] = []

        # Remove calls older than 60 seconds
        self._call_counts[key] = [
            t for t in self._call_counts[key]
            if now - t < 60
        ]

        if len(self._call_counts[key]) >= max_per_minute:
            return False

        self._call_counts[key].append(now)
        return True

    def set_policy(self, agent_id: str, policy: IznPolicy):
        """Override policy for an agent"""
        self._policies[agent_id] = policy

    def grant_tool(self, agent_id: str, tool_name: str,
                   level: PermissionLevel = PermissionLevel.ALLOWED):
        """Grant a specific tool permission"""
        if agent_id not in self._policies:
            self._policies[agent_id] = IznPolicy(id=agent_id)
        self._policies[agent_id].tool_permissions[tool_name] = ToolPermission(
            tool_name=tool_name,
            level=level,
        )

    def revoke_tool(self, agent_id: str, tool_name: str):
        """Revoke a specific tool permission"""
        if agent_id in self._policies:
            self._policies[agent_id].tool_permissions[tool_name] = ToolPermission(
                tool_name=tool_name,
                level=PermissionLevel.DENIED,
            )

    def check_nafs_permission(self, nafs_level: int, tool_name: str) -> Dict:
        """
        Check permission based on agent's Nafs level (1-7).
        Higher Nafs levels unlock more tool capabilities.
        """
        tier = NAFS_PERMISSION_TIERS.get(nafs_level, NAFS_PERMISSION_TIERS[1])
        level = tier.get(tool_name, PermissionLevel.RESTRICTED)

        if level == PermissionLevel.DENIED:
            return {
                "allowed": False,
                "reason": f"Nafs level {nafs_level} cannot use '{tool_name}'",
                "requires_approval": False,
                "nafs_level": nafs_level,
            }
        if level == PermissionLevel.APPROVAL_REQUIRED:
            return {
                "allowed": False,
                "reason": f"Nafs level {nafs_level} requires approval for '{tool_name}'",
                "requires_approval": True,
                "nafs_level": nafs_level,
            }
        return {
            "allowed": True,
            "reason": f"Permitted at Nafs level {nafs_level}",
            "requires_approval": False,
            "nafs_level": nafs_level,
        }

    def get_nafs_tier_info(self, nafs_level: int) -> Dict:
        """Get permission summary for a given Nafs level."""
        names = {
            1: "Ammara", 2: "Lawwama", 3: "Mulhama", 4: "Mutmainna",
            5: "Radiya", 6: "Mardiyya", 7: "Kamila",
        }
        tier = NAFS_PERMISSION_TIERS.get(nafs_level, NAFS_PERMISSION_TIERS[1])
        return {
            "nafs_level": nafs_level,
            "nafs_name": names.get(nafs_level, "Unknown"),
            "permissions": {t: lv.value for t, lv in tier.items()},
        }
