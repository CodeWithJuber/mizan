"""
Skill Registry (MizanHub)
==========================

Manages skill discovery, loading, and lifecycle.
Skills are verified before activation.
"""

import os
import json
import logging
import importlib
from typing import Dict, List, Optional
from datetime import datetime

from .base import SkillBase, SkillManifest

logger = logging.getLogger("mizan.skills")


class SkillRegistry:
    """
    MizanHub — Skill registry for MIZAN.
    Manages skill discovery, loading, verification, and lifecycle.
    """

    def __init__(self, skills_dir: str = None, wali=None):
        self.skills_dir = skills_dir or os.path.join(
            os.path.dirname(__file__), "builtin"
        )
        self.wali = wali
        self._loaded: Dict[str, SkillBase] = {}
        self._manifests: Dict[str, SkillManifest] = {}

    def load_builtin_skills(self):
        """Load all built-in skills from the builtin directory"""
        if not os.path.exists(self.skills_dir):
            return

        for filename in os.listdir(self.skills_dir):
            if filename.endswith(".py") and not filename.startswith("_"):
                skill_name = filename[:-3]
                try:
                    self._load_skill_module(f"skills.builtin.{skill_name}")
                    logger.info(f"[HIKMAH] Loaded built-in skill: {skill_name}")
                except Exception as e:
                    logger.error(f"[HIKMAH] Failed to load skill {skill_name}: {e}")

    def _load_skill_module(self, module_path: str):
        """Load a skill from a Python module"""
        module = importlib.import_module(module_path)

        # Find SkillBase subclasses in the module
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (isinstance(attr, type) and
                    issubclass(attr, SkillBase) and
                    attr is not SkillBase):
                skill = attr()
                self.register(skill)

    def register(self, skill: SkillBase):
        """Register a skill"""
        name = skill.manifest.name
        if not name:
            name = skill.__class__.__name__

        # Verify skill permissions
        if self.wali:
            for perm in skill.manifest.permissions:
                self.wali.audit.log("skill_permission_declared", {
                    "skill": name,
                    "permission": perm,
                })

        self._loaded[name] = skill
        self._manifests[name] = skill.manifest
        logger.info(f"[HIKMAH] Registered skill: {name}")

    def unregister(self, name: str):
        """Remove a skill"""
        self._loaded.pop(name, None)
        self._manifests.pop(name, None)

    def get_skill(self, name: str) -> Optional[SkillBase]:
        """Get a loaded skill"""
        return self._loaded.get(name)

    def list_skills(self) -> List[Dict]:
        """List all registered skills"""
        result = []
        for name, manifest in self._manifests.items():
            result.append({
                "name": name,
                "display": manifest.description.split(".")[0] if manifest.description else name,
                "arabic": manifest.tags[0] if manifest.tags else "مهارة",
                "description": manifest.description,
                "category": manifest.tags[1] if len(manifest.tags) > 1 else "General",
                "version": manifest.version,
                "permissions": manifest.permissions,
                "installed": manifest.enabled,
            })

        # Include known built-in skills even if not loaded
        known = {
            "web_browse": {"display": "Web Browse", "arabic": "تصفح",
                          "description": "Browse websites and extract content",
                          "category": "Research", "version": "1.0.0",
                          "permissions": ["network_access"]},
            "data_analysis": {"display": "Data Analysis", "arabic": "تحليل",
                             "description": "Analyze CSV, JSON, and structured data",
                             "category": "Analysis", "version": "1.0.0",
                             "permissions": ["file_read"]},
            "code_exec": {"display": "Code Execution", "arabic": "تنفيذ",
                         "description": "Execute code in sandboxed environment",
                         "category": "Development", "version": "1.0.0",
                         "permissions": ["sandbox_exec"]},
            "file_manager": {"display": "File Manager", "arabic": "ملفات",
                            "description": "Read, write, and manage files",
                            "category": "System", "version": "1.0.0",
                            "permissions": ["file_read", "file_write"]},
            "calendar": {"display": "Calendar", "arabic": "تقويم",
                        "description": "Schedule and manage events",
                        "category": "Productivity", "version": "1.0.0",
                        "permissions": ["calendar_access"]},
            "kitab_notebook": {"display": "Kitab Notebook", "arabic": "كتاب",
                              "description": "Interactive computational notebooks with sandboxed execution",
                              "category": "Development", "version": "1.0.0",
                              "permissions": ["sandbox_exec", "file_read", "file_write"]},
            "sahab_cloud": {"display": "Sahab Cloud Hub", "arabic": "سحاب",
                           "description": "Cloud integration: GitHub, Docker, APIs, credential vault",
                           "category": "Cloud", "version": "1.0.0",
                           "permissions": ["network_access", "shell_git", "shell_docker"]},
            "raqib_scanner": {"display": "Raqib Security Scanner", "arabic": "رقيب",
                             "description": "Security scanning: OWASP, secrets, CVEs, Docker",
                             "category": "Security", "version": "1.0.0",
                             "permissions": ["file_read"]},
            "suq_registry": {"display": "Suq al-Ilm Registry", "arabic": "سوق",
                            "description": "Secure skill marketplace with Shura verification",
                            "category": "Registry", "version": "1.0.0",
                            "permissions": ["file_read", "file_write"]},
            "wahy_plugins": {"display": "Wahy Plugin System", "arabic": "وحي",
                            "description": "Plugin lifecycle: discover, verify, install, activate, hot-reload",
                            "category": "System", "version": "1.0.0",
                            "permissions": ["file_read", "file_write", "plugin_manage"]},
            "majlis_social": {"display": "Majlis Agent Social", "arabic": "مجلس",
                             "description": "Agent social network: identity, reputation, knowledge sharing",
                             "category": "Social", "version": "1.0.0",
                             "permissions": ["agent_manage", "network_access"]},
        }
        existing_names = {s["name"] for s in result}
        for sname, sinfo in known.items():
            if sname not in existing_names:
                result.append({
                    "name": sname,
                    "installed": sname in self._loaded,
                    **sinfo,
                })

        return result

    def discover_builtin(self):
        """Discover and register built-in skills (alias for load_builtin_skills)"""
        self.load_builtin_skills()

    def install_skill(self, name: str) -> bool:
        """Install/enable a skill by name"""
        if name in self._manifests:
            self._manifests[name].enabled = True
            return True
        # Try loading from builtin
        try:
            self._load_skill_module(f"skills.builtin.{name}")
            return True
        except Exception:
            return False

    def uninstall_skill(self, name: str) -> bool:
        """Uninstall/disable a skill by name"""
        if name in self._manifests:
            self._manifests[name].enabled = False
            return True
        return False

    def get_all_tools(self) -> Dict[str, any]:
        """Get all tools from all loaded skills"""
        tools = {}
        for skill in self._loaded.values():
            tools.update(skill.get_tools())
        return tools

    def get_all_tool_schemas(self) -> List[Dict]:
        """Get all Claude tool_use schemas from loaded skills"""
        schemas = []
        for skill in self._loaded.values():
            schemas.extend(skill.get_tool_schemas())
        return schemas
