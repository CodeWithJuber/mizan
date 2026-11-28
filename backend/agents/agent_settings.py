"""Per-agent settings: what the person who owns an agent configured for it.

They live in ``agent.config["settings"]`` (saved with the agent profile) and are
mapped onto the config keys the agent loop already reads (``temperature``,
``max_steps``, ``max_output_tokens``). The rest is read where it applies: the
orchestration mode and Claude effort for each run (``BaseAgent._execute_run``),
the permission mode when a chat sends none (``api.main``), and the tool, connector
and skill filters when the agent's tools are chosen (``get_tool_schemas``).
Every key is always present; an empty list means no restriction, and ``None``
means the server's own setting.
"""

from __future__ import annotations

from fnmatch import fnmatchcase
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

EFFORTS = ("low", "medium", "high", "xhigh", "max")
ORCHESTRATIONS = ("mizan", "hybrid", "llm")
PERMISSION_MODES = ("auto_edits", "ask", "plan", "auto")

DEFAULTS: dict[str, Any] = {
    "temperature": None,
    "effort": None,
    "max_steps": None,
    "max_output_tokens": None,
    "orchestration": None,
    "permission_mode": None,
    "tools_allow": [],
    "tools_deny": [],
    "connectors": [],
    "skills": [],
    "starter_prompts": [],
    "avatar": None,
    "learn_skills": True,
}
# Settings that are the agent loop's own config keys.
_CONFIG_KEYS = ("temperature", "max_steps", "max_output_tokens")
_NAME = r"^[A-Za-z0-9_*?.\-]{1,128}$"


def _single_line(value: str, limit: int) -> str:
    text = str(value).strip()
    if not text or len(text) > limit or any(ch in text for ch in "\r\n\x00"):
        raise ValueError(f"Each entry is one line of 1-{limit} characters")
    return text


class AgentSettingsPatch(BaseModel):
    """Some settings of an agent; a key sent as null goes back to its default."""

    model_config = ConfigDict(extra="forbid")

    temperature: float | None = Field(None, ge=0, le=1)
    effort: Literal["low", "medium", "high", "xhigh", "max"] | None = None
    max_steps: int | None = Field(None, ge=1, le=1000)
    max_output_tokens: int | None = Field(None, ge=256, le=128_000)
    orchestration: Literal["mizan", "hybrid", "llm"] | None = None
    permission_mode: Literal["auto_edits", "ask", "plan", "auto"] | None = None
    tools_allow: list[str] | None = Field(None, max_length=200)
    tools_deny: list[str] | None = Field(None, max_length=200)
    connectors: list[str] | None = Field(None, max_length=100)
    skills: list[str] | None = Field(None, max_length=200)
    starter_prompts: list[str] | None = Field(None, max_length=12)
    avatar: str | None = Field(None, max_length=2048)
    learn_skills: bool | None = None

    @field_validator("tools_allow", "tools_deny", "connectors", "skills")
    @classmethod
    def _names(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        import re

        cleaned = []
        for item in value:
            name = _single_line(item, 128)
            if not re.match(_NAME, name):
                raise ValueError("Names use letters, digits and _ - . (and * ? as wildcards)")
            cleaned.append(name)
        return list(dict.fromkeys(cleaned))

    @field_validator("starter_prompts")
    @classmethod
    def _prompts(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return [_single_line(item, 500) for item in value]

    @field_validator("avatar")
    @classmethod
    def _avatar(cls, value: str | None) -> str | None:
        return None if value is None or not value.strip() else _single_line(value, 2048)


def of(config: dict | None) -> dict[str, Any]:
    """The agent's settings with every key present."""
    saved = (config or {}).get("settings")
    saved = saved if isinstance(saved, dict) else {}
    result = {}
    for key, default in DEFAULTS.items():
        value = saved.get(key, default)
        if key in _CONFIG_KEYS and key not in saved and isinstance(config, dict):
            # An agent saved before settings existed keeps its own config value.
            value = config.get(key, default)
        if isinstance(default, list):
            value = list(value) if isinstance(value, list) else []
        elif key == "learn_skills":
            value = default if value is None else bool(value)
        result[key] = value
    return result


def merge(current: dict | None, patch: dict[str, Any]) -> dict[str, Any]:
    """Merge a patch key by key (``None`` resets that key) into full settings."""
    merged = of({"settings": current or {}})
    for key, value in patch.items():
        if key not in DEFAULTS:
            continue
        merged[key] = (
            list(DEFAULTS[key])
            if value is None and isinstance(DEFAULTS[key], list)
            else (DEFAULTS[key] if value is None else value)
        )
    return merged


def apply(config: dict, settings: dict[str, Any]) -> None:
    """Store the settings and map them onto the config keys the agent loop reads."""
    config["settings"] = of({"settings": settings})
    for key in _CONFIG_KEYS:
        value = config["settings"].get(key)
        if value is None:
            config.pop(key, None)
        else:
            config[key] = value


def _matches(name: str, patterns: list[str]) -> bool:
    return any(fnmatchcase(name, pattern) for pattern in patterns)


def tool_allowed(settings: dict[str, Any], name: str) -> bool:
    """Whether the agent's own allow/deny lists and connector choice let it offer a tool.

    ``tools_deny`` applies to every tool. A connector tool (``mcp__<server>__<tool>``)
    is offered when ``connectors`` is empty or names its server (or the tool is in
    ``tools_allow``); any other tool when ``tools_allow`` is empty or matches it."""
    if _matches(name, settings.get("tools_deny") or []):
        return False
    allow = settings.get("tools_allow") or []
    if name.startswith("mcp__"):
        connectors = settings.get("connectors") or []
        server = name[5:].split("__", 1)[0]
        return not connectors or server in connectors or _matches(name, allow)
    return not allow or _matches(name, allow)


def skill_allowed(settings: dict[str, Any], name: str) -> bool:
    skills = settings.get("skills") or []
    return not skills or _matches(name, skills)
