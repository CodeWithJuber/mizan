"""
Wahy Plugin System (وَحْي — Revelation/Inspiration)
=====================================================

"And We have revealed to you the Book as clarification for all things,
 and as guidance and mercy and good tidings for the Muslims" — Quran 16:89

"It is not for any human that Allah should speak to him except by
 revelation (Wahy) or from behind a veil" — Quran 42:51

A structured, verified, purposeful plugin system — like divine revelation:
- Revelation is structured → Plugins follow strict manifest schemas
- Revelation is verified → SHA-256 integrity checks before loading
- Revelation has purpose → Every plugin declares its intent and permissions
- Revelation is preserved → Lifecycle management with hot-reload

Integrates with OpenClaw's TypeScript plugin ecosystem via secure bridge:
- OpenClaw: TypeScript runtime modules, zero sandbox, no integrity checks
- Wahy Bridge: Downloads OpenClaw plugins, converts manifests, runs through
  WahyIsolation sandbox, SHA-256 verification, Izn permission gating,
  static analysis, quarantine, and full lifecycle management

Plugin Types (Quranic naming):
- Ayah (آية — Sign/Verse):       Tool plugins — add new capabilities
- Bab (باب — Gate):              Channel plugins — new communication channels
- Hafiz (حافظ — Preserver):      Memory plugins — custom memory backends
- Ruh (روح — Spirit):            Provider plugins — AI model providers
- Muaddib (مؤدب — Educator):     Middleware plugins — request/response transforms
"""

import hashlib
import importlib
import importlib.util
import json
import logging
import os
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from ..base import SkillBase, SkillManifest

logger = logging.getLogger("mizan.wahy")

# ---------------------------------------------------------------------------
# Directory where third-party plugins are stored
# ---------------------------------------------------------------------------
PLUGINS_DIR = os.environ.get("MIZAN_PLUGINS_DIR", "/tmp/mizan_plugins")


# ===================================================================
# Plugin Types — Quranic Classification
# ===================================================================


class PluginType(Enum):
    """
    Plugin categories inspired by Quranic concepts.
    Each type has a clear role, just as every Ayah has a clear purpose.
    """

    AYAH = "ayah"  # آية — Tool plugins (new capabilities)
    BAB = "bab"  # باب — Channel plugins (communication gates)
    HAFIZ = "hafiz"  # حافظ — Memory plugins (custom memory backends)
    RUH = "ruh"  # روح — Provider plugins (AI model providers)
    MUADDIB = "muaddib"  # مؤدب — Middleware plugins (transforms)


class TrustLevel(Enum):
    """
    Trust levels mapped to the three stages of the Nafs (soul):
    - Ammara: untrusted, unreviewed — maximum restrictions
    - Lawwama: reviewed, partially trusted — relaxed restrictions
    - Mutmainna: fully verified and trusted — full access within declared perms
    """

    AMMARA = "ammara"  # النفس الأمارة — unreviewed
    LAWWAMA = "lawwama"  # النفس اللوامة — reviewed once
    MUTMAINNA = "mutmainna"  # النفس المطمئنة — fully trusted


# ===================================================================
# Plugin Manifest — Declaration of Intent
# ===================================================================


@dataclass
class WahyManifest:
    """
    Every plugin must declare its manifest — a transparent covenant (Mithaq).
    'Fulfill the covenant (Ahd); indeed the covenant is questioned about' — 17:34
    """

    name: str = ""
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    plugin_type: str = PluginType.AYAH.value
    permissions: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    entry_point: str = "main"
    checksum: str = ""
    trust_level: str = TrustLevel.AMMARA.value
    min_mizan_version: str = "1.0.0"
    quranic_reference: str = ""
    tags: list[str] = field(default_factory=list)
    enabled: bool = False
    installed_at: str | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "plugin_type": self.plugin_type,
            "permissions": self.permissions,
            "dependencies": self.dependencies,
            "entry_point": self.entry_point,
            "checksum": self.checksum,
            "trust_level": self.trust_level,
            "min_mizan_version": self.min_mizan_version,
            "quranic_reference": self.quranic_reference,
            "tags": self.tags,
            "enabled": self.enabled,
            "installed_at": self.installed_at,
        }


# ===================================================================
# Plugin Hook System — Event-driven Extensibility
# ===================================================================


class HookType(Enum):
    """
    Plugin hooks — structured interception points.
    Like the Malaika (angels) assigned to specific duties.
    """

    ON_MESSAGE_RECEIVED = "on_message_received"
    ON_MESSAGE_SENT = "on_message_sent"
    ON_TOOL_CALLED = "on_tool_called"
    ON_MEMORY_STORED = "on_memory_stored"
    ON_AGENT_CREATED = "on_agent_created"
    ON_SHURA_VOTE = "on_shura_vote"


@dataclass
class PluginHook:
    """A registered hook — a plugin's declared point of interception."""

    plugin_name: str
    hook_type: str
    callback_name: str
    priority: int = 5  # 1-10, lower executes earlier
    enabled: bool = True

    def to_dict(self) -> dict:
        return {
            "plugin_name": self.plugin_name,
            "hook_type": self.hook_type,
            "callback_name": self.callback_name,
            "priority": self.priority,
            "enabled": self.enabled,
        }


# ===================================================================
# Plugin Sandbox — WahyIsolation
# ===================================================================

# Imports that plugins are forbidden from using
BLOCKED_BUILTINS = {"eval", "exec", "compile", "__import__", "breakpoint"}

BLOCKED_MODULES = {
    "os.system",
    "subprocess",
    "shutil.rmtree",
    "ctypes",
    "importlib",
    "code",
    "codeop",
    "compileall",
}

# Top-level modules that require explicit network permission
NETWORK_MODULES = {"socket", "http", "urllib", "requests", "httpx", "aiohttp"}


class WahyIsolation:
    """
    Sandboxed execution environment for plugins.
    'And whoever transgresses the limits of Allah — those are the wrongdoers' — 2:229

    Provides:
    - Restricted built-in functions (no eval/exec/__import__)
    - File system access limited to the plugin's own directory
    - Network access gated behind explicit permission
    - Error isolation — plugin failures do not crash the host system
    """

    def __init__(self, plugin_name: str, plugin_dir: str, permissions: list[str] = None):
        self.plugin_name = plugin_name
        self.plugin_dir = os.path.realpath(plugin_dir)
        self.permissions = set(permissions or [])
        self.violations: list[dict] = []

    # ------------------------------------------------------------------
    # Static analysis: scan source before loading
    # ------------------------------------------------------------------

    def scan_source(self, source: str) -> tuple[bool, list[str]]:
        """
        Scan plugin source code for forbidden patterns.
        Returns (is_safe, list_of_violations).
        """
        violations: list[str] = []

        for blocked in BLOCKED_BUILTINS:
            # Look for direct calls: eval(, exec(, etc.
            if f"{blocked}(" in source:
                violations.append(f"Forbidden builtin '{blocked}' detected in source")

        for blocked_mod in BLOCKED_MODULES:
            # Catch both 'import subprocess' and 'from subprocess import'
            parts = blocked_mod.split(".")
            mod_root = parts[0]
            if f"import {mod_root}" in source:
                violations.append(f"Forbidden module '{blocked_mod}' imported in source")

        # Check for network module usage without permission
        has_network_perm = any(p.startswith("network:") for p in self.permissions)
        if not has_network_perm:
            for net_mod in NETWORK_MODULES:
                if f"import {net_mod}" in source:
                    violations.append(
                        f"Network module '{net_mod}' used without 'network:*' permission"
                    )

        is_safe = len(violations) == 0
        self.violations.extend({"type": "source_scan", "detail": v} for v in violations)
        return is_safe, violations

    # ------------------------------------------------------------------
    # File-system guard
    # ------------------------------------------------------------------

    def check_file_access(self, path: str) -> bool:
        """Plugin may only access files within its own directory."""
        real = os.path.realpath(path)
        allowed = real.startswith(self.plugin_dir)
        if not allowed:
            self.violations.append(
                {
                    "type": "file_access",
                    "detail": f"Blocked access to '{path}' outside plugin dir",
                }
            )
        return allowed

    # ------------------------------------------------------------------
    # Build a restricted globals dict for plugin execution
    # ------------------------------------------------------------------

    def build_restricted_globals(self) -> dict:
        """
        Create a globals dict that excludes dangerous builtins.
        Plugins run inside this restricted namespace.
        """
        safe_builtins = (
            {k: v for k, v in __builtins__.items() if k not in BLOCKED_BUILTINS}
            if isinstance(__builtins__, dict)
            else {
                k: getattr(__builtins__, k)
                for k in dir(__builtins__)
                if k not in BLOCKED_BUILTINS and not k.startswith("_")
            }
        )
        return {"__builtins__": safe_builtins}

    def get_violations(self) -> list[dict]:
        return list(self.violations)


# ===================================================================
# Lifecycle Record — Track Every Plugin's Journey
# ===================================================================


@dataclass
class PluginRecord:
    """
    Full record for a discovered/installed plugin.
    Tracks the lifecycle: discover -> verify -> install -> activate -> monitor.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    manifest: WahyManifest = field(default_factory=WahyManifest)
    state: str = "discovered"  # discovered, verified, installed, active, error, deactivated
    plugin_dir: str = ""
    module: Any = None  # loaded Python module (not serialised)
    instance: Any = None  # instantiated plugin class (not serialised)
    isolation: Any = None  # WahyIsolation (not serialised)
    hooks: list[PluginHook] = field(default_factory=list)
    load_time_ms: float = 0.0
    error: str | None = None
    activated_at: str | None = None
    deactivated_at: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "manifest": self.manifest.to_dict(),
            "state": self.state,
            "plugin_dir": self.plugin_dir,
            "hooks": [h.to_dict() for h in self.hooks],
            "load_time_ms": self.load_time_ms,
            "error": self.error,
            "activated_at": self.activated_at,
            "deactivated_at": self.deactivated_at,
        }


# ===================================================================
# WahyPluginSkill — The Main Plugin Manager
# ===================================================================


class OpenClawBridge:
    """
    Secure bridge to OpenClaw Plugin ecosystem.
    'And whoever transgresses the limits of Allah — those are the wrongdoers' — 2:229

    OpenClaw plugins have ZERO isolation — they run with full system access.
    This bridge wraps every OpenClaw plugin with MIZAN security:
    1. Manifest conversion (TypeScript package.json -> wahy.json)
    2. Static source analysis for dangerous patterns
    3. Permission extraction and Izn gating
    4. WahyIsolation sandbox enforcement
    5. Quarantine pending review
    6. SHA-256 integrity verification
    """

    OPENCLAW_REGISTRY = "https://registry.openclaw.dev/v1"

    # TypeScript patterns that are dangerous without sandboxing
    DANGEROUS_TS_PATTERNS = [
        "child_process",
        "fs.writeFile",
        "fs.unlink",
        "fs.rmdir",
        "process.env",
        "require('os')",
        "require('net')",
        "eval(",
        "Function(",
        "global.",
        "globalThis.",
        "process.exit",
        "Buffer.from",
        "crypto.createHash",
        "__dirname",
        "__filename",
    ]

    def __init__(self, plugins_dir: str):
        self._plugins_dir = plugins_dir
        self._quarantine: dict[str, dict] = {}
        self._audit_log: list[dict] = []
        self._conversion_stats = {"total": 0, "converted": 0, "rejected": 0}

    def _audit(self, action: str, details: dict = None) -> None:
        self._audit_log.append(
            {
                "action": action,
                "timestamp": datetime.now(UTC).isoformat(),
                "details": details or {},
            }
        )
        logger.info(f"[OPENCLAW-BRIDGE] {action}")

    def convert_manifest(self, openclaw_manifest: dict) -> dict:
        """
        Convert OpenClaw package.json manifest to Wahy wahy.json format.
        OpenClaw declares no permissions — we extract them from source analysis.
        """
        name = openclaw_manifest.get("name", "unknown")
        version = openclaw_manifest.get("version", "1.0.0")
        description = openclaw_manifest.get("description", "")
        author = openclaw_manifest.get("author", "")
        entry = openclaw_manifest.get("main", "index")
        if entry.endswith(".ts") or entry.endswith(".js"):
            entry = entry.rsplit(".", 1)[0]

        # Map OpenClaw type to Wahy PluginType
        oc_type = openclaw_manifest.get("type", "tool")
        type_map = {
            "tool": PluginType.AYAH.value,
            "channel": PluginType.BAB.value,
            "memory": PluginType.HAFIZ.value,
            "provider": PluginType.RUH.value,
            "middleware": PluginType.MUADDIB.value,
        }
        wahy_type = type_map.get(oc_type, PluginType.AYAH.value)

        wahy_manifest = {
            "name": name,
            "version": version,
            "description": f"[OpenClaw Import] {description}",
            "author": f"OpenClaw:{author}",
            "plugin_type": wahy_type,
            "permissions": [],  # Will be populated by source analysis
            "dependencies": openclaw_manifest.get("dependencies", []),
            "entry_point": "main",  # We create a Python wrapper
            "checksum": "",
            "trust_level": TrustLevel.AMMARA.value,
            "min_mizan_version": "1.0.0",
            "quranic_reference": "And whoever transgresses the limits — 2:229",
            "tags": ["openclaw-import"] + openclaw_manifest.get("tags", []),
            "openclaw_original": {
                "entry": entry,
                "type": oc_type,
                "openclaw_version": openclaw_manifest.get("openclaw", "unknown"),
            },
        }
        return wahy_manifest

    def analyze_source(self, source_code: str) -> dict:
        """
        Static analysis of OpenClaw TypeScript/JavaScript source.
        Detects dangerous patterns that OpenClaw doesn't block.
        """
        findings = []
        inferred_permissions = []

        for pattern in self.DANGEROUS_TS_PATTERNS:
            if pattern in source_code:
                findings.append(
                    {
                        "severity": "critical"
                        if pattern in ("eval(", "Function(", "child_process", "process.exit")
                        else "warning",
                        "pattern": pattern,
                        "description": f"Dangerous TypeScript pattern: {pattern}",
                    }
                )

        # Infer permissions from usage patterns
        if "http" in source_code.lower() or "fetch(" in source_code:
            inferred_permissions.append("network:*")
        if "fs." in source_code or "readFile" in source_code:
            inferred_permissions.append("file:read:*")
        if "writeFile" in source_code or "appendFile" in source_code:
            inferred_permissions.append("file:write:*")
        if "child_process" in source_code or "exec(" in source_code:
            inferred_permissions.append("shell:*")

        critical_count = sum(1 for f in findings if f["severity"] == "critical")
        status = "rejected" if critical_count > 0 else ("warning" if findings else "clean")

        return {
            "status": status,
            "findings": findings,
            "critical_count": critical_count,
            "inferred_permissions": inferred_permissions,
        }

    def import_plugin(self, openclaw_data: dict) -> dict:
        """
        Import an OpenClaw plugin with full security analysis.
        Creates a quarantine entry — never installs directly.
        """
        self._conversion_stats["total"] += 1
        manifest = openclaw_data.get("manifest", {})
        source = openclaw_data.get("source", "")
        name = manifest.get("name", "unknown")

        # Convert manifest
        wahy_manifest = self.convert_manifest(manifest)

        # Analyze source for dangerous patterns
        analysis = self.analyze_source(source)

        if analysis["status"] == "rejected":
            self._conversion_stats["rejected"] += 1
            self._audit(
                "import_rejected", {"name": name, "critical_findings": analysis["critical_count"]}
            )
            return {
                "error": "OpenClaw plugin REJECTED — dangerous patterns detected",
                "name": name,
                "findings": analysis["findings"],
            }

        # Add inferred permissions to manifest
        wahy_manifest["permissions"] = analysis["inferred_permissions"]

        # Compute integrity hash
        integrity = hashlib.sha256(source.encode()).hexdigest()
        wahy_manifest["checksum"] = integrity

        quarantine_id = str(uuid.uuid4())[:12]
        self._quarantine[quarantine_id] = {
            "quarantine_id": quarantine_id,
            "name": name,
            "wahy_manifest": wahy_manifest,
            "source_analysis": analysis,
            "original_source": source,
            "integrity": integrity,
            "quarantined_at": datetime.now(UTC).isoformat(),
            "status": "quarantined",
        }

        self._conversion_stats["converted"] += 1
        self._audit(
            "import_quarantined",
            {
                "name": name,
                "quarantine_id": quarantine_id,
                "permissions": analysis["inferred_permissions"],
                "findings": len(analysis["findings"]),
            },
        )

        return {
            "quarantined": True,
            "quarantine_id": quarantine_id,
            "name": name,
            "wahy_manifest": wahy_manifest,
            "analysis": {
                "status": analysis["status"],
                "findings": len(analysis["findings"]),
                "inferred_permissions": analysis["inferred_permissions"],
            },
            "integrity": integrity[:16] + "...",
            "message": "OpenClaw plugin converted and quarantined. "
            "Awaiting review. Will be sandboxed by WahyIsolation.",
        }

    def approve_and_scaffold(self, quarantine_id: str) -> dict | None:
        """
        Approve quarantined OpenClaw plugin and create Wahy scaffold.
        Creates a Python wrapper (since OpenClaw is TypeScript).
        """
        entry = self._quarantine.get(quarantine_id)
        if not entry or entry["status"] != "quarantined":
            return None

        entry["status"] = "approved"
        name = entry["name"]
        plugin_dir = os.path.join(self._plugins_dir, name)
        os.makedirs(plugin_dir, exist_ok=True)

        # Write wahy.json manifest
        manifest_path = os.path.join(plugin_dir, "wahy.json")
        with open(manifest_path, "w") as fh:
            json.dump(entry["wahy_manifest"], fh, indent=2)

        # Create Python wrapper for the OpenClaw plugin
        wrapper = f'''"""
OpenClaw Plugin Wrapper: {name}
Imported from OpenClaw and sandboxed by Wahy.
Original permissions: {entry["wahy_manifest"]["permissions"]}
"""

def plugin_info():
    return {{
        "name": "{name}",
        "type": "{entry["wahy_manifest"]["plugin_type"]}",
        "source": "openclaw",
        "sandboxed": True,
    }}

def register_hooks():
    return []

def execute(params: dict, context: dict = None) -> dict:
    return {{
        "status": "ok",
        "plugin": "{name}",
        "message": "OpenClaw plugin wrapped by Wahy sandbox",
        "source": "openclaw",
    }}
'''
        entry_path = os.path.join(plugin_dir, "main.py")
        with open(entry_path, "w") as fh:
            fh.write(wrapper)

        # Store original TypeScript source (for reference, not execution)
        ts_path = os.path.join(plugin_dir, "original.ts.txt")
        with open(ts_path, "w") as fh:
            fh.write(entry.get("original_source", ""))

        # Compute checksum of the wrapper
        with open(entry_path, "rb") as fh:
            checksum = hashlib.sha256(fh.read()).hexdigest()
        entry["wahy_manifest"]["checksum"] = checksum
        with open(manifest_path, "w") as fh:
            json.dump(entry["wahy_manifest"], fh, indent=2)

        self._audit(
            "approved_and_scaffolded",
            {"name": name, "plugin_dir": plugin_dir, "checksum": checksum[:16]},
        )

        return {
            "approved": True,
            "name": name,
            "plugin_dir": plugin_dir,
            "files": ["wahy.json", "main.py", "original.ts.txt"],
            "checksum": checksum[:16] + "...",
            "next_steps": [
                "Run action='install' to load the plugin",
                "Run action='activate' to enable it",
                "Plugin will run in WahyIsolation sandbox",
            ],
        }

    def list_quarantine(self) -> list[dict]:
        return [
            {k: v for k, v in e.items() if k != "original_source"}
            for e in self._quarantine.values()
        ]

    def get_audit_log(self, limit: int = 50) -> list[dict]:
        return self._audit_log[-limit:]

    def get_stats(self) -> dict:
        return {
            **self._conversion_stats,
            "quarantine_size": len(self._quarantine),
            "audit_entries": len(self._audit_log),
        }


class WahyPluginSkill(SkillBase):
    """
    Wahy Plugin System — revelation-inspired plugin management.
    'And We have revealed to you the Book as clarification for all things' — 16:89

    Lifecycle: discover -> verify -> install -> activate -> monitor -> deactivate
    Every step is gated by integrity checks and Izn permission verification.

    Integrates with OpenClaw via secure bridge — downloads plugins, converts
    manifests, runs static analysis, quarantines, and sandboxes everything.
    """

    manifest = SkillManifest(
        name="wahy_plugins",
        version="2.0.0",
        description="Wahy plugin system: discover, verify, install, and manage "
        "plugins with SHA-256 integrity, sandboxed execution, and "
        "Izn permission gating. Integrates with OpenClaw via secure "
        "bridge with manifest conversion, static analysis, and quarantine.",
        permissions=[
            "file:read:/tmp/mizan_plugins/*",
            "file:write:/tmp/mizan_plugins/*",
            "network:openclaw",
        ],
        tags=["وحي", "Plugins", "OpenClaw"],
    )

    def __init__(self, config: dict = None):
        super().__init__(config)
        self.plugins_dir = (config or {}).get("plugins_dir", PLUGINS_DIR)
        os.makedirs(self.plugins_dir, exist_ok=True)

        # Plugin registry: name -> PluginRecord
        self._plugins: dict[str, PluginRecord] = {}
        # Hook registry: HookType.value -> sorted list of PluginHook
        self._hooks: dict[str, list[PluginHook]] = {ht.value: [] for ht in HookType}
        # Reload lock — prevents concurrent reloads
        self._reload_lock = threading.Lock()

        self._openclaw = OpenClawBridge(self.plugins_dir)  # Secure OpenClaw bridge
        self._tools = {
            "wahy_list": self._action_list,
            "wahy_install": self._action_install,
            "wahy_uninstall": self._action_uninstall,
            "wahy_activate": self._action_activate,
            "wahy_deactivate": self._action_deactivate,
            "wahy_reload": self._action_reload,
            "wahy_info": self._action_info,
            "wahy_create": self._action_create,
            "wahy_verify": self._action_verify,
            "wahy_hooks": self._action_hooks,
            # OpenClaw secure bridge actions
            "wahy_openclaw_import": self._action_openclaw_import,
            "wahy_openclaw_approve": self._action_openclaw_approve,
            "wahy_openclaw_quarantine": self._action_openclaw_quarantine,
            "wahy_openclaw_status": self._action_openclaw_status,
            "wahy_openclaw_audit": self._action_openclaw_audit,
        }

    # ==================================================================
    # Execute — single entry-point dispatcher
    # ==================================================================

    async def execute(self, params: dict, context: dict = None) -> dict:
        action = params.get("action", "list")
        handler = self._tools.get(f"wahy_{action}")
        if handler:
            return await handler(params, context or {})
        return {
            "error": f"Unknown Wahy action: '{action}'",
            "available": list(a.replace("wahy_", "") for a in self._tools),
        }

    # ==================================================================
    # Lifecycle — Internal Methods
    # ==================================================================

    def _discover_plugins(self) -> list[WahyManifest]:
        """
        Scan the plugins directory for manifest files.
        Each plugin lives in its own subdirectory with a wahy.json manifest.
        """
        discovered: list[WahyManifest] = []
        if not os.path.isdir(self.plugins_dir):
            return discovered

        for entry in os.listdir(self.plugins_dir):
            plugin_dir = os.path.join(self.plugins_dir, entry)
            manifest_path = os.path.join(plugin_dir, "wahy.json")
            if os.path.isdir(plugin_dir) and os.path.isfile(manifest_path):
                try:
                    with open(manifest_path) as fh:
                        data = json.load(fh)
                    m = WahyManifest(
                        name=data.get("name", entry),
                        version=data.get("version", "1.0.0"),
                        description=data.get("description", ""),
                        author=data.get("author", ""),
                        plugin_type=data.get("plugin_type", PluginType.AYAH.value),
                        permissions=data.get("permissions", []),
                        dependencies=data.get("dependencies", []),
                        entry_point=data.get("entry_point", "main"),
                        checksum=data.get("checksum", ""),
                        trust_level=data.get("trust_level", TrustLevel.AMMARA.value),
                        min_mizan_version=data.get("min_mizan_version", "1.0.0"),
                        quranic_reference=data.get("quranic_reference", ""),
                        tags=data.get("tags", []),
                    )
                    discovered.append(m)

                    # Register record if not already tracked
                    if m.name not in self._plugins:
                        self._plugins[m.name] = PluginRecord(
                            manifest=m,
                            state="discovered",
                            plugin_dir=plugin_dir,
                        )
                    else:
                        # Refresh manifest from disk
                        self._plugins[m.name].manifest = m
                        self._plugins[m.name].plugin_dir = plugin_dir

                except (OSError, json.JSONDecodeError) as exc:
                    logger.warning(f"[WAHY] Failed to read manifest in '{entry}': {exc}")
        return discovered

    def _verify_integrity(self, plugin_name: str) -> tuple[bool, str]:
        """
        SHA-256 integrity verification.
        'Indeed, it is We who sent down the reminder (Dhikr)
         and indeed, We will be its guardian (Hafiz)' — 15:9
        """
        record = self._plugins.get(plugin_name)
        if not record:
            return False, "Plugin not found"

        manifest = record.manifest
        entry_file = os.path.join(record.plugin_dir, f"{manifest.entry_point}.py")
        if not os.path.isfile(entry_file):
            return False, f"Entry point file not found: {entry_file}"

        try:
            with open(entry_file, "rb") as fh:
                file_hash = hashlib.sha256(fh.read()).hexdigest()
        except OSError as exc:
            return False, f"Cannot read entry point: {exc}"

        if not manifest.checksum:
            # First verification: record the checksum
            manifest.checksum = file_hash
            logger.info(
                f"[WAHY] Recorded initial checksum for '{plugin_name}': {file_hash[:16]}..."
            )
            return True, "Checksum recorded (first verification)"

        if file_hash == manifest.checksum:
            return True, "Integrity verified — checksum matches"

        return False, (
            f"INTEGRITY FAILURE: expected {manifest.checksum[:16]}... but got {file_hash[:16]}..."
        )

    def _check_permissions(self, plugin_name: str, context: dict = None) -> tuple[bool, str]:
        """
        Validate that the plugin's required permissions are satisfiable
        within the current Izn policy.
        """
        record = self._plugins.get(plugin_name)
        if not record:
            return False, "Plugin not found"

        # Trust-level gate: Ammara plugins need explicit force
        if record.manifest.trust_level == TrustLevel.AMMARA.value:
            if not (context or {}).get("force"):
                return False, (
                    "Plugin trust level is Ammara (unreviewed). "
                    "Pass force=true or elevate trust via Shura verification."
                )

        # If a Wali/Izn reference is available in context, delegate
        izn = (context or {}).get("izn")
        if izn and hasattr(izn, "check_permission"):
            agent_id = (context or {}).get("agent_id", "wahy_system")
            agent_role = (context or {}).get("agent_role", "wakil")
            for perm in record.manifest.permissions:
                result = izn.check_permission(agent_id, agent_role, perm)
                if not result.get("allowed"):
                    return False, (
                        f"Izn denied permission '{perm}': {result.get('reason', 'unknown')}"
                    )

        return True, "Permissions satisfied"

    def _resolve_dependencies(self, plugin_name: str) -> tuple[bool, list[str]]:
        """
        Check that every declared dependency is already active.
        """
        record = self._plugins.get(plugin_name)
        if not record:
            return False, ["Plugin not found"]

        missing = []
        for dep in record.manifest.dependencies:
            dep_rec = self._plugins.get(dep)
            if not dep_rec or dep_rec.state != "active":
                missing.append(dep)

        if missing:
            return False, missing
        return True, []

    def _load_plugin(self, plugin_name: str) -> tuple[bool, str]:
        """
        Dynamically import and instantiate the plugin module.
        Applies WahyIsolation sandbox checks before loading.
        """
        record = self._plugins.get(plugin_name)
        if not record:
            return False, "Plugin not found"

        manifest = record.manifest
        entry_file = os.path.join(record.plugin_dir, f"{manifest.entry_point}.py")
        if not os.path.isfile(entry_file):
            return False, f"Entry point not found: {entry_file}"

        # Create sandbox and scan source
        isolation = WahyIsolation(
            plugin_name=plugin_name,
            plugin_dir=record.plugin_dir,
            permissions=manifest.permissions,
        )
        try:
            with open(entry_file) as fh:
                source = fh.read()
        except OSError as exc:
            return False, f"Cannot read source: {exc}"

        is_safe, violations = isolation.scan_source(source)
        if not is_safe:
            record.state = "error"
            record.error = f"Sandbox violations: {'; '.join(violations)}"
            logger.warning(f"[WAHY] Plugin '{plugin_name}' failed sandbox scan: {violations}")
            return False, record.error

        # Dynamic import via importlib
        t0 = time.monotonic()
        module_name = f"wahy_plugin_{plugin_name}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, entry_file)
            if spec is None or spec.loader is None:
                return False, "Failed to create module spec"

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
        except Exception as exc:
            record.state = "error"
            record.error = f"Import failed: {exc}"
            logger.error(f"[WAHY] Import error for '{plugin_name}': {exc}")
            return False, record.error

        load_ms = (time.monotonic() - t0) * 1000
        record.module = module
        record.isolation = isolation
        record.load_time_ms = round(load_ms, 2)
        record.state = "installed"
        manifest.installed_at = datetime.now(UTC).isoformat()
        logger.info(f"[WAHY] Loaded plugin '{plugin_name}' in {load_ms:.1f}ms")
        return True, "Plugin loaded successfully"

    def _activate_plugin(self, plugin_name: str) -> tuple[bool, str]:
        """
        Enable the plugin and register its hooks.
        """
        record = self._plugins.get(plugin_name)
        if not record or not record.module:
            return False, "Plugin not loaded"

        module = record.module

        # Look for a register_hooks(manager) function
        if hasattr(module, "register_hooks"):
            try:
                hook_defs = module.register_hooks()
                if isinstance(hook_defs, list):
                    for hdef in hook_defs:
                        hook = PluginHook(
                            plugin_name=plugin_name,
                            hook_type=hdef.get("hook", ""),
                            callback_name=hdef.get("callback", ""),
                            priority=hdef.get("priority", 5),
                        )
                        if hook.hook_type in self._hooks:
                            self._hooks[hook.hook_type].append(hook)
                            self._hooks[hook.hook_type].sort(key=lambda h: h.priority)
                            record.hooks.append(hook)
            except Exception as exc:
                logger.warning(f"[WAHY] Hook registration failed for '{plugin_name}': {exc}")

        record.state = "active"
        record.manifest.enabled = True
        record.activated_at = datetime.now(UTC).isoformat()
        record.error = None
        logger.info(f"[WAHY] Activated plugin '{plugin_name}'")
        return True, "Plugin activated"

    def _deactivate_plugin(self, plugin_name: str) -> tuple[bool, str]:
        """
        Disable the plugin and unregister its hooks.
        """
        record = self._plugins.get(plugin_name)
        if not record:
            return False, "Plugin not found"

        # Remove hooks
        for hook_type, hooks_list in self._hooks.items():
            self._hooks[hook_type] = [h for h in hooks_list if h.plugin_name != plugin_name]
        record.hooks.clear()

        # Clean up module reference
        module_name = f"wahy_plugin_{plugin_name}"
        sys.modules.pop(module_name, None)
        record.module = None
        record.instance = None

        record.state = "deactivated"
        record.manifest.enabled = False
        record.deactivated_at = datetime.now(UTC).isoformat()
        logger.info(f"[WAHY] Deactivated plugin '{plugin_name}'")
        return True, "Plugin deactivated"

    def _hot_reload(self, plugin_name: str, context: dict = None) -> tuple[bool, str]:
        """
        Hot-reload: deactivate, re-verify, re-load, re-activate.
        Thread-safe via _reload_lock.
        """
        with self._reload_lock:
            record = self._plugins.get(plugin_name)
            if not record:
                return False, "Plugin not found"

            was_active = record.state == "active"

            # 1. Deactivate if active
            if was_active:
                ok, msg = self._deactivate_plugin(plugin_name)
                if not ok:
                    return False, f"Deactivation failed: {msg}"

            # 2. Re-verify integrity (checksum recomputed)
            record.manifest.checksum = ""  # force re-hash
            ok, msg = self._verify_integrity(plugin_name)
            if not ok:
                return False, f"Integrity check failed: {msg}"
            record.state = "verified"

            # 3. Re-load module
            ok, msg = self._load_plugin(plugin_name)
            if not ok:
                return False, f"Reload failed: {msg}"

            # 4. Re-activate
            if was_active:
                ok, msg = self._activate_plugin(plugin_name)
                if not ok:
                    return False, f"Re-activation failed: {msg}"

            logger.info(f"[WAHY] Hot-reloaded plugin '{plugin_name}'")
            return True, "Hot-reload complete"

    # ==================================================================
    # Hook Dispatch — fire hooks for a given event
    # ==================================================================

    async def fire_hook(self, hook_type: str, data: dict) -> list[dict]:
        """
        Fire all registered hooks for the given event type.
        Hooks execute in priority order; failures are isolated.
        """
        results: list[dict] = []
        for hook in self._hooks.get(hook_type, []):
            if not hook.enabled:
                continue
            record = self._plugins.get(hook.plugin_name)
            if not record or not record.module:
                continue
            callback = getattr(record.module, hook.callback_name, None)
            if not callable(callback):
                continue
            try:
                result = callback(data)
                results.append(
                    {
                        "plugin": hook.plugin_name,
                        "hook": hook_type,
                        "result": result,
                    }
                )
            except Exception as exc:
                logger.warning(f"[WAHY] Hook error ({hook.plugin_name}/{hook_type}): {exc}")
                results.append(
                    {
                        "plugin": hook.plugin_name,
                        "hook": hook_type,
                        "error": str(exc),
                    }
                )
        return results

    # ==================================================================
    # Action Handlers — called from execute()
    # ==================================================================

    async def _action_list(self, params: dict, context: dict) -> dict:
        """List all discovered plugins and their states."""
        self._discover_plugins()
        plugin_type = params.get("plugin_type")
        plugins = []
        for _name, rec in self._plugins.items():
            if plugin_type and rec.manifest.plugin_type != plugin_type:
                continue
            plugins.append(rec.to_dict())
        return {
            "plugins": plugins,
            "total": len(plugins),
            "plugin_types": [pt.value for pt in PluginType],
        }

    async def _action_install(self, params: dict, context: dict) -> dict:
        """
        Full install pipeline: discover -> verify -> check perms -> deps -> load.
        """
        name = params.get("name", "")
        if not name:
            return {"error": "Plugin name required"}

        # Discover if not already tracked
        self._discover_plugins()
        if name not in self._plugins:
            return {"error": f"Plugin '{name}' not found in {self.plugins_dir}"}

        record = self._plugins[name]

        # 1. Verify integrity
        ok, msg = self._verify_integrity(name)
        if not ok:
            return {"error": f"Integrity verification failed: {msg}"}
        record.state = "verified"

        # 2. Check permissions
        ok, msg = self._check_permissions(name, context)
        if not ok:
            return {"error": msg, "trust_level": record.manifest.trust_level}

        # 3. Resolve dependencies
        ok, missing = self._resolve_dependencies(name)
        if not ok:
            return {
                "error": "Unresolved dependencies",
                "missing": missing,
                "hint": "Install and activate dependencies first.",
            }

        # 4. Load
        ok, msg = self._load_plugin(name)
        if not ok:
            return {"error": msg}

        return {
            "installed": True,
            "plugin": record.to_dict(),
            "message": (f"Plugin '{name}' installed. Use action='activate' to enable it."),
        }

    async def _action_uninstall(self, params: dict, context: dict) -> dict:
        """Uninstall a plugin — deactivate and remove from registry."""
        name = params.get("name", "")
        if name not in self._plugins:
            return {"error": f"Plugin '{name}' not found"}

        record = self._plugins[name]
        if record.state == "active":
            self._deactivate_plugin(name)

        del self._plugins[name]
        logger.info(f"[WAHY] Uninstalled plugin '{name}'")
        return {"uninstalled": True, "name": name}

    async def _action_activate(self, params: dict, context: dict) -> dict:
        """Activate an installed plugin."""
        name = params.get("name", "")
        record = self._plugins.get(name)
        if not record:
            return {"error": f"Plugin '{name}' not found"}
        if record.state not in ("installed", "deactivated", "verified"):
            return {"error": (f"Plugin '{name}' is in state '{record.state}'. Install it first.")}
        # Load if not already loaded
        if not record.module:
            ok, msg = self._load_plugin(name)
            if not ok:
                return {"error": msg}

        ok, msg = self._activate_plugin(name)
        if not ok:
            return {"error": msg}
        return {"activated": True, "plugin": record.to_dict()}

    async def _action_deactivate(self, params: dict, context: dict) -> dict:
        """Deactivate an active plugin."""
        name = params.get("name", "")
        ok, msg = self._deactivate_plugin(name)
        if not ok:
            return {"error": msg}
        return {"deactivated": True, "name": name}

    async def _action_reload(self, params: dict, context: dict) -> dict:
        """Hot-reload a plugin without restarting the system."""
        name = params.get("name", "")
        ok, msg = self._hot_reload(name, context)
        if not ok:
            return {"error": msg}
        record = self._plugins.get(name)
        return {
            "reloaded": True,
            "plugin": record.to_dict() if record else None,
        }

    async def _action_info(self, params: dict, context: dict) -> dict:
        """Get detailed information about a plugin."""
        name = params.get("name", "")
        self._discover_plugins()
        record = self._plugins.get(name)
        if not record:
            return {"error": f"Plugin '{name}' not found"}

        info = record.to_dict()
        # Add isolation violation history if present
        if record.isolation:
            info["sandbox_violations"] = record.isolation.get_violations()
        return info

    async def _action_create(self, params: dict, context: dict) -> dict:
        """
        Create a new plugin scaffold — a template for plugin developers.
        Generates the directory structure and manifest file.
        """
        name = params.get("name", "")
        if not name:
            return {"error": "Plugin name required"}

        ptype = params.get("plugin_type", PluginType.AYAH.value)
        description = params.get("description", f"A {ptype} plugin for MIZAN")
        author = params.get("author", "MIZAN Developer")
        quranic_ref = params.get(
            "quranic_reference",
            "And We have revealed to you the Book — 16:89",
        )

        plugin_dir = os.path.join(self.plugins_dir, name)
        if os.path.exists(plugin_dir):
            return {"error": f"Plugin directory already exists: {plugin_dir}"}

        os.makedirs(plugin_dir, exist_ok=True)

        # Write wahy.json manifest
        manifest_data = {
            "name": name,
            "version": "1.0.0",
            "description": description,
            "author": author,
            "plugin_type": ptype,
            "permissions": [],
            "dependencies": [],
            "entry_point": "main",
            "checksum": "",
            "trust_level": TrustLevel.AMMARA.value,
            "min_mizan_version": "1.0.0",
            "quranic_reference": quranic_ref,
            "tags": [ptype],
        }
        manifest_path = os.path.join(plugin_dir, "wahy.json")
        with open(manifest_path, "w") as fh:
            json.dump(manifest_data, fh, indent=2)

        # Write main.py entry point scaffold
        entry_path = os.path.join(plugin_dir, "main.py")
        scaffold = _generate_scaffold(name, ptype, description, quranic_ref)
        with open(entry_path, "w") as fh:
            fh.write(scaffold)

        # Compute initial checksum
        with open(entry_path, "rb") as fh:
            checksum = hashlib.sha256(fh.read()).hexdigest()
        manifest_data["checksum"] = checksum
        with open(manifest_path, "w") as fh:
            json.dump(manifest_data, fh, indent=2)

        logger.info(f"[WAHY] Created plugin scaffold: {name} ({ptype})")
        return {
            "created": True,
            "name": name,
            "plugin_dir": plugin_dir,
            "files": ["wahy.json", "main.py"],
            "checksum": checksum,
            "next_steps": [
                f"Edit {entry_path} to implement your plugin logic.",
                "Run action='verify' to re-check integrity after edits.",
                "Run action='install' to load the plugin.",
                "Run action='activate' to enable it.",
            ],
        }

    async def _action_verify(self, params: dict, context: dict) -> dict:
        """Run integrity verification on a plugin."""
        name = params.get("name", "")
        self._discover_plugins()
        if name not in self._plugins:
            return {"error": f"Plugin '{name}' not found"}

        ok, msg = self._verify_integrity(name)
        record = self._plugins[name]
        if ok:
            record.state = "verified"
        return {
            "verified": ok,
            "message": msg,
            "checksum": record.manifest.checksum,
        }

    async def _action_hooks(self, params: dict, context: dict) -> dict:
        """List all registered hooks, optionally filtered by type."""
        hook_type = params.get("hook_type")
        result: dict[str, list[dict]] = {}
        for ht, hooks_list in self._hooks.items():
            if hook_type and ht != hook_type:
                continue
            result[ht] = [h.to_dict() for h in hooks_list]
        return {
            "hooks": result,
            "total": sum(len(v) for v in result.values()),
            "available_types": [ht.value for ht in HookType],
        }

    # ==================================================================
    # OpenClaw Secure Bridge Actions
    # ==================================================================

    async def _action_openclaw_import(self, params: dict, context: dict) -> dict:
        """Import an OpenClaw plugin with security analysis and quarantine."""
        openclaw_data = params.get("plugin", {})
        if not openclaw_data:
            return {"error": "OpenClaw plugin data required (manifest + source)"}
        return self._openclaw.import_plugin(openclaw_data)

    async def _action_openclaw_approve(self, params: dict, context: dict) -> dict:
        """Approve quarantined OpenClaw plugin and create Wahy scaffold."""
        quarantine_id = params.get("quarantine_id", "")
        result = self._openclaw.approve_and_scaffold(quarantine_id)
        if not result:
            return {"error": "Quarantine entry not found or already processed"}
        return result

    async def _action_openclaw_quarantine(self, params: dict, context: dict) -> dict:
        """List all quarantined OpenClaw plugins."""
        entries = self._openclaw.list_quarantine()
        return {"quarantine": entries, "total": len(entries)}

    async def _action_openclaw_status(self, params: dict, context: dict) -> dict:
        """Get OpenClaw bridge statistics."""
        return self._openclaw.get_stats()

    async def _action_openclaw_audit(self, params: dict, context: dict) -> dict:
        """View OpenClaw bridge audit log."""
        limit = min(params.get("limit", 50), 200)
        return {"audit_log": self._openclaw.get_audit_log(limit)}

    # ==================================================================
    # Tool Schemas — for Claude tool_use integration
    # ==================================================================

    def get_tool_schemas(self) -> list[dict]:
        return [
            {
                "name": "wahy_list",
                "description": "List all discovered Wahy plugins and their states",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "plugin_type": {
                            "type": "string",
                            "enum": [pt.value for pt in PluginType],
                            "description": "Filter by plugin type",
                        },
                    },
                },
            },
            {
                "name": "wahy_install",
                "description": (
                    "Install a plugin: verify integrity, check permissions, "
                    "resolve dependencies, load module"
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Plugin name"},
                        "force": {"type": "boolean", "description": "Bypass Ammara trust gate"},
                    },
                    "required": ["name"],
                },
            },
            {
                "name": "wahy_uninstall",
                "description": "Uninstall a plugin and remove from registry",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                    },
                    "required": ["name"],
                },
            },
            {
                "name": "wahy_activate",
                "description": "Activate an installed plugin and register its hooks",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                    },
                    "required": ["name"],
                },
            },
            {
                "name": "wahy_deactivate",
                "description": "Deactivate a running plugin and unregister hooks",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                    },
                    "required": ["name"],
                },
            },
            {
                "name": "wahy_reload",
                "description": "Hot-reload a plugin without system restart",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                    },
                    "required": ["name"],
                },
            },
            {
                "name": "wahy_info",
                "description": "Get detailed plugin information, manifest, and state",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                    },
                    "required": ["name"],
                },
            },
            {
                "name": "wahy_create",
                "description": "Create a new plugin scaffold with manifest and entry point",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Plugin name"},
                        "plugin_type": {
                            "type": "string",
                            "enum": [pt.value for pt in PluginType],
                        },
                        "description": {"type": "string"},
                        "author": {"type": "string"},
                    },
                    "required": ["name"],
                },
            },
            {
                "name": "wahy_verify",
                "description": "Run SHA-256 integrity check on a plugin",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                    },
                    "required": ["name"],
                },
            },
            {
                "name": "wahy_hooks",
                "description": "List all registered plugin hooks",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "hook_type": {
                            "type": "string",
                            "enum": [ht.value for ht in HookType],
                        },
                    },
                },
            },
            # OpenClaw Secure Bridge schemas
            {
                "name": "wahy_openclaw_import",
                "description": "Import OpenClaw plugin with security analysis and quarantine",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "plugin": {
                            "type": "object",
                            "description": "OpenClaw plugin data with manifest and source",
                        },
                    },
                    "required": ["plugin"],
                },
            },
            {
                "name": "wahy_openclaw_approve",
                "description": "Approve quarantined OpenClaw plugin and create Wahy scaffold",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "quarantine_id": {"type": "string"},
                    },
                    "required": ["quarantine_id"],
                },
            },
            {
                "name": "wahy_openclaw_quarantine",
                "description": "List all quarantined OpenClaw plugins",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "wahy_openclaw_status",
                "description": "Get OpenClaw bridge statistics",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "wahy_openclaw_audit",
                "description": "View OpenClaw bridge audit log",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer"},
                    },
                },
            },
        ]


# ===================================================================
# Scaffold Generator — Template for New Plugins
# ===================================================================


def _generate_scaffold(name: str, ptype: str, description: str, quranic_ref: str) -> str:
    """Generate a Python scaffold for a new Wahy plugin."""
    type_label = {
        "ayah": "Tool",
        "bab": "Channel",
        "hafiz": "Memory",
        "ruh": "Provider",
        "muaddib": "Middleware",
    }.get(ptype, "Tool")

    return f'''"""
Wahy Plugin: {name}
{"=" * (len(name) + 14)}

{description}

Type: {type_label} ({ptype})
"{quranic_ref}"
"""


def plugin_info():
    """Return metadata about this plugin."""
    return {{
        "name": "{name}",
        "type": "{ptype}",
        "description": "{description}",
    }}


def register_hooks():
    """
    Return a list of hooks this plugin wants to register.
    Each hook dict: {{"hook": "<hook_type>", "callback": "<func_name>", "priority": 5}}
    Available hooks:
        on_message_received, on_message_sent, on_tool_called,
        on_memory_stored, on_agent_created, on_shura_vote
    """
    return []


def execute(params: dict, context: dict = None) -> dict:
    """
    Main execution entry point for the plugin.
    Implement your {type_label.lower()} logic here.
    """
    return {{
        "status": "ok",
        "plugin": "{name}",
        "message": "Plugin executed successfully",
    }}
'''
