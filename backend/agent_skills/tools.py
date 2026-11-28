"""Model-facing skill tools: ``activate_skill`` (catalog in its description) and
``read_skill_file``. Both act only on the signed-in user's own skills.
"""

from __future__ import annotations

import html
from typing import Any

from agent_skills.loader import AgentSkill, available_skills

ACTIVE_KEY = "skills"
MAX_ACTIVE_CHARS = 24_000


def _scope() -> tuple[str, str | None, str | None]:
    from security.auth import current_user_id
    from workspace.context import bound_workspace_id, current_chat_session

    return current_user_id() or "", bound_workspace_id(), current_chat_session()


def skill_content(skill: AgentSkill) -> str:
    resources = "".join(f"\n  <file>{html.escape(f)}</file>" for f in skill.files)
    return (
        f'<skill_content name="{html.escape(skill.name)}">\n{skill.body}\n\n'
        f"Skill directory: {skill.directory}. Read listed files with read_skill_file; "
        "run bundled scripts by copying them into the project with workspace_write.\n"
        f"<skill_resources>{resources}\n</skill_resources>\n</skill_content>"
    )


def tool_schemas(user_id: str, workspace_id: str | None, only=None) -> list[dict]:
    """Schemas for this user, or none at all when no skill is available. ``only``
    (a predicate on the skill's name) keeps the skills an agent is set to use."""
    skills = available_skills(user_id, workspace_id)
    if only is not None:
        skills = {name: skill for name, skill in skills.items() if only(name)}
    if not skills:
        return []
    catalog = "\n".join(f"- {name}: {skill.description}" for name, skill in skills.items())
    return [
        {
            "name": "activate_skill",
            "description": (
                "Load a skill's full instructions when the task matches its description, "
                "then follow them. Available skills:\n" + catalog
            )[:6000],
            "input_schema": {
                "type": "object",
                "properties": {"name": {"type": "string", "enum": sorted(skills)}},
                "required": ["name"],
            },
        },
        {
            "name": "read_skill_file",
            "description": "Read a file bundled with an activated skill (path relative to it).",
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "enum": sorted(skills)},
                    "path": {"type": "string", "maxLength": 300},
                },
                "required": ["name", "path"],
            },
        },
    ]


def activate(name: str, *, record: bool = True) -> dict[str, Any]:
    from agents import session_state

    user_id, workspace_id, session_id = _scope()
    skill = available_skills(user_id, workspace_id).get(str(name))
    if skill is None:
        return {"error": f"No available skill named {name!r}"}
    if record and user_id and session_id:
        active = session_state.load(user_id, session_id).get(ACTIVE_KEY) or []
        if skill.name not in active:
            session_state.update(user_id, session_id, ACTIVE_KEY, [*active, skill.name][-10:])
    return {"skill": skill.name, "scope": skill.scope, "instructions": skill_content(skill)}


def read_file(name: str, path: str) -> dict[str, Any]:
    user_id, workspace_id, _session = _scope()
    skill = available_skills(user_id, workspace_id).get(str(name))
    if skill is None:
        return {"error": f"No available skill named {name!r}"}
    try:
        data = skill.read(str(path))
    except Exception as exc:  # noqa: BLE001 - the receipt explains the refusal
        return {"error": str(getattr(exc, "detail", exc))[:200]}
    if b"\x00" in data[:4096]:
        return {"error": "Binary file; copy it into the project to use it"}
    return {"skill": skill.name, "path": path, "content": data.decode("utf-8", "replace")}


def active_block(user_id: str, workspace_id: str | None, session_id: str | None) -> str:
    """Instructions of skills activated earlier in this chat, for later turns."""
    from agents import session_state

    if not user_id or not session_id:
        return ""
    names = session_state.load(user_id, session_id).get(ACTIVE_KEY) or []
    if not names:
        return ""
    skills = available_skills(user_id, workspace_id)
    parts, used = [], 0
    for name in names:
        skill = skills.get(name)
        if skill is None:
            continue
        content = skill_content(skill)
        if used + len(content) > MAX_ACTIVE_CHARS:
            break
        parts.append(content)
        used += len(content)
    if not parts:
        return ""
    return "[ACTIVE SKILLS — instructions loaded earlier in this chat]\n" + "\n".join(parts)


def resolve_slash_skill(
    content: str, user_id: str, workspace_id: str | None
) -> tuple[str, str] | None:
    """``/skill-name rest`` → (skill name, rest) when the user has that skill."""
    if not content.startswith("/"):
        return None
    head, _, rest = content[1:].partition(" ")
    name = head.strip().lower()
    if not name or name not in available_skills(user_id, workspace_id):
        return None
    return name, rest.strip()
