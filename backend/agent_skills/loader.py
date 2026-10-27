"""Discover and parse Agent Skills (https://agentskills.io/specification).

Validation is lenient like other clients: cosmetic problems become
diagnostics, while a skill without a description (or unreadable frontmatter)
is skipped. Precedence on a name clash: project > user > bundled.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("mizan.agent_skills")

BUNDLED_ROOT = Path(__file__).parent / "library"
PROJECT_SKILL_DIRS = (".agents/skills", ".claude/skills")
NAME = re.compile(r"^[a-z0-9](?:[a-z0-9]|-(?!-))*[a-z0-9]$|^[a-z0-9]$")
MAX_SKILLS_PER_SCOPE = 100
MAX_SKILL_MD_BYTES = 256 * 1024
MAX_RESOURCE_BYTES = 256 * 1024
MAX_LISTED_FILES = 100
SCOPE_ORDER = {"bundled": 0, "user": 1, "project": 2}


@dataclass
class AgentSkill:
    name: str
    description: str
    scope: str
    body: str
    directory: str
    license: str = ""
    compatibility: str = ""
    metadata: dict[str, str] = field(default_factory=dict)
    files: list[str] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)
    reader: Callable[[str], bytes] | None = None

    def summary(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "scope": self.scope,
            "directory": self.directory,
            "license": self.license,
            "compatibility": self.compatibility,
            "metadata": self.metadata,
            "files": self.files,
            "diagnostics": self.diagnostics,
        }

    def read(self, relative: str) -> bytes:
        parts = relative.replace("\\", "/").split("/")
        if not relative or any(p in {"", ".", ".."} for p in parts) or relative.startswith("/"):
            raise ValueError("Use a relative path inside the skill directory")
        if self.reader is None:
            raise ValueError("Skill files are unavailable")
        return self.reader(relative)


class SkillParseError(ValueError):
    pass


def _quote_unsafe_values(text: str) -> str:
    """Fix the common invalid YAML ``key: value: with colons`` written for other clients."""
    fixed = []
    for line in text.splitlines():
        match = re.match(r"^([A-Za-z0-9_-]+):\s+(.*)$", line)
        if match and ":" in match.group(2) and not match.group(2).startswith(("'", '"', "|", ">")):
            line = f"{match.group(1)}: {json.dumps(match.group(2))}"
        fixed.append(line)
    return "\n".join(fixed)


def parse_skill_md(text: str, directory_name: str) -> tuple[dict[str, Any], str, list[str]]:
    """Return (frontmatter, body, diagnostics) or raise SkillParseError."""
    text = text.lstrip("﻿")
    match = re.match(r"^---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)(.*)$", text, re.S)
    if not match:
        raise SkillParseError("SKILL.md must start with YAML frontmatter between --- lines")
    raw, body = match.group(1), match.group(2).strip()
    diagnostics: list[str] = []
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError:
        try:
            data = yaml.safe_load(_quote_unsafe_values(raw))
            diagnostics.append("frontmatter needed quoting fixes (unquoted colons)")
        except yaml.YAMLError as exc:
            raise SkillParseError(f"unreadable frontmatter: {exc}") from None
    if not isinstance(data, dict):
        raise SkillParseError("frontmatter must be a mapping")
    description = data.get("description")
    if not isinstance(description, str) or not description.strip():
        raise SkillParseError("a non-empty description is required")
    if len(description) > 1024:
        diagnostics.append("description exceeds 1024 characters; truncated")
        data["description"] = description[:1024]
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        diagnostics.append("name missing; using the directory name")
        data["name"] = directory_name
    else:
        name = name.strip()
        if len(name) > 64 or not NAME.match(name):
            diagnostics.append("name should be 1-64 lowercase letters, digits and single hyphens")
        if name != directory_name:
            diagnostics.append(f"name '{name}' does not match directory '{directory_name}'")
        data["name"] = name
    metadata = data.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        diagnostics.append("metadata must be a mapping; ignored")
        data["metadata"] = {}
    return data, body, diagnostics


def _skill_from_text(
    text: str,
    directory_name: str,
    scope: str,
    directory: str,
    files: list[str],
    reader: Callable[[str], bytes],
) -> AgentSkill | None:
    try:
        data, body, diagnostics = parse_skill_md(text, directory_name)
    except SkillParseError as exc:
        logger.warning("[SKILLS] Skipping %s skill %s: %s", scope, directory, exc)
        return None
    metadata = data.get("metadata") or {}
    return AgentSkill(
        name=str(data["name"])[:64],
        description=" ".join(str(data["description"]).split()),
        scope=scope,
        body=body,
        directory=directory,
        license=str(data.get("license") or "")[:200],
        compatibility=str(data.get("compatibility") or "")[:500],
        metadata={str(k)[:64]: str(v)[:500] for k, v in list(metadata.items())[:20]},
        files=files[:MAX_LISTED_FILES],
        diagnostics=diagnostics,
        reader=reader,
    )


def _disk_files(root: Path) -> list[str]:
    files: list[str] = []
    for current, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d != "node_modules")
        for name in sorted(names):
            path = Path(current) / name
            if path.is_symlink() or not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            if relative != "SKILL.md":
                files.append(relative)
            if len(files) >= MAX_LISTED_FILES:
                return files
    return files


def _disk_reader(root: Path) -> Callable[[str], bytes]:
    resolved_root = root.resolve()

    def read(relative: str) -> bytes:
        target = (root / relative).resolve()
        if resolved_root not in target.parents or target.is_symlink() or not target.is_file():
            raise ValueError("File not found in this skill")
        if target.stat().st_size > MAX_RESOURCE_BYTES:
            raise ValueError("Skill file is too large to read")
        return target.read_bytes()

    return read


def scan_directory(root: Path, scope: str) -> list[AgentSkill]:
    skills: list[AgentSkill] = []
    if not root.is_dir() or root.is_symlink():
        return skills
    for child in sorted(root.iterdir())[: MAX_SKILLS_PER_SCOPE * 2]:
        skill_md = child / "SKILL.md"
        if child.is_symlink() or not child.is_dir() or not skill_md.is_file():
            continue
        if skill_md.is_symlink() or skill_md.stat().st_size > MAX_SKILL_MD_BYTES:
            continue
        skill = _skill_from_text(
            skill_md.read_text("utf-8", errors="replace"),
            child.name,
            scope,
            f"{scope}:{child.name}",
            _disk_files(child),
            _disk_reader(child),
        )
        if skill:
            skills.append(skill)
        if len(skills) >= MAX_SKILLS_PER_SCOPE:
            break
    return skills


@lru_cache(maxsize=1)
def _bundled_cache(signature: tuple) -> tuple[AgentSkill, ...]:
    return tuple(scan_directory(BUNDLED_ROOT, "bundled"))


def bundled_skills() -> list[AgentSkill]:
    signature = tuple(
        (p.name, p.stat().st_mtime_ns) for p in sorted(BUNDLED_ROOT.glob("*/SKILL.md"))
    )
    return list(_bundled_cache(signature))


def user_root(user_id: str) -> Path:
    base = Path(os.getenv("MIZAN_DATA_DIR", "data")) / "agent_skills"
    return base / hashlib.sha256(user_id.encode()).hexdigest()


def user_skills(user_id: str) -> list[AgentSkill]:
    return scan_directory(user_root(user_id), "user") if user_id else []


def project_skills(user_id: str, workspace_id: str | None) -> list[AgentSkill]:
    """Skills inside the user's selected coding project (read through the store)."""
    if not user_id or not workspace_id or os.getenv("MIZAN_PROJECT_SKILLS", "true") != "true":
        return []
    from fastapi import HTTPException

    from workspace.store import WorkspaceStore

    try:
        store = WorkspaceStore(user_id)
        entries = store.tree(workspace_id)["files"]
    except HTTPException:
        return []
    skills: list[AgentSkill] = []
    for base in PROJECT_SKILL_DIRS:
        prefix = base + "/"
        for entry in entries:
            path = entry["path"]
            parts = path[len(prefix) :].split("/") if path.startswith(prefix) else []
            if len(parts) != 2 or parts[1] != "SKILL.md" or entry["kind"] != "file":
                continue
            directory = prefix + parts[0]
            files = [
                e["path"][len(directory) + 1 :]
                for e in entries
                if e["kind"] == "file"
                and e["path"].startswith(directory + "/")
                and e["path"] != path
            ]

            def reader(relative: str, directory: str = directory) -> bytes:
                data: bytes = store.read_bytes(workspace_id, f"{directory}/{relative}")
                return data

            try:
                text = store.read(workspace_id, path)["content"]
            except HTTPException:
                continue
            skill = _skill_from_text(
                text, parts[0], "project", f"project:{directory}", files, reader
            )
            if skill:
                skills.append(skill)
    return skills[:MAX_SKILLS_PER_SCOPE]


def _state_path(user_id: str) -> Path:
    return user_root(user_id) / ".state.json"


def disabled_skills(user_id: str) -> set[str]:
    try:
        data = json.loads(_state_path(user_id).read_text())
    except (OSError, ValueError):
        return set()
    disabled = data.get("disabled") if isinstance(data, dict) else None
    return {str(name) for name in disabled} if isinstance(disabled, list) else set()


def set_enabled(user_id: str, name: str, enabled: bool) -> set[str]:
    disabled = disabled_skills(user_id)
    (disabled.discard if enabled else disabled.add)(name)
    path = _state_path(user_id)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"disabled": sorted(disabled)}))
    os.replace(temporary, path)
    return disabled


def all_skills(user_id: str, workspace_id: str | None = None) -> list[AgentSkill]:
    """Every discovered skill, shadowed duplicates included (for the settings page)."""
    return [*bundled_skills(), *user_skills(user_id), *project_skills(user_id, workspace_id)]


def available_skills(
    user_id: str, workspace_id: str | None = None, *, include_disabled: bool = False
) -> dict[str, AgentSkill]:
    chosen: dict[str, AgentSkill] = {}
    for skill in all_skills(user_id, workspace_id):
        current = chosen.get(skill.name)
        if current is None or SCOPE_ORDER[skill.scope] >= SCOPE_ORDER[current.scope]:
            if current is not None:
                logger.info(
                    "[SKILLS] %s skill %s shadows %s", skill.scope, skill.name, current.scope
                )
            chosen[skill.name] = skill
    if not include_disabled:
        for name in disabled_skills(user_id):
            chosen.pop(name, None)
    return dict(sorted(chosen.items()))
