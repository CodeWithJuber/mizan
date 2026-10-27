"""Shahid tools: MIZAN's browser sandbox, for every signed-in user.

``shahid_read`` runs a browsing job with nothing approved, so the page cannot be
changed (every form post is held). ``shahid_submit`` runs the same job with the
held requests the person approved; it is a mutating tool, so it waits for Allow
(and is held for the owner in an unattended run). See ``tadbir/shahid.py``.
"""

from __future__ import annotations

from typing import Any

from security.auth import current_user_id

from ..base import SkillBase, SkillManifest

_METHODS = {"shahid_read": "read", "shahid_submit": "submit"}


def allows_user_shahid_tool(tool_name: str, registry, *, native_tools: dict | None = None) -> bool:
    """The shipped Shahid tools are open to every signed-in user (their own jobs)."""
    method_name = _METHODS.get(tool_name)
    if registry is None or method_name is None or tool_name in (native_tools or {}):
        return False
    skill = registry.get_skill("shahid_browser")
    if type(skill) is not ShahidBrowserSkill:
        return False
    actual = registry.get_all_tools().get(tool_name)
    return (
        actual is not None
        and getattr(actual, "__self__", None) is skill
        and getattr(actual, "__func__", None) is getattr(ShahidBrowserSkill, method_name)
    )


class ShahidBrowserSkill(SkillBase):
    manifest = SkillManifest(
        name="shahid_browser",
        version="1.0.0",
        description="Use a web page in MIZAN's browser sandbox: go, click, fill, read, screenshot.",
        permissions=["network:public-web", "sandbox:browser"],
        tags=["browser", "web", "shahid"],
    )

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self._tools = {name: getattr(self, method) for name, method in _METHODS.items()}

    async def execute(self, params: dict, context: dict | None = None) -> dict:
        data = dict(params)
        tool = self._tools.get(f"shahid_{data.pop('action', 'read')}")
        if tool is None:
            return {"error": "Unknown browser action"}
        result: dict = await tool(**data)
        return result

    async def _run(self, origins: Any, steps: Any, approved: list[str]) -> dict:
        from tadbir import shahid

        owner = current_user_id()
        if not owner:
            return {"error": "Authentication required"}
        if not shahid.available():
            return {"error": "MIZAN's browser sandbox is not installed on this server"}
        if not isinstance(origins, list) or not all(isinstance(item, str) for item in origins):
            return {"error": "origins must be a list of host names"}
        from workspace.browse_agent import valid

        problem = valid({"origins": origins, "steps": steps})
        if problem:
            return {"error": problem}
        try:
            result: dict = await shahid.browse(owner, origins, steps, approved)
            return result
        except Exception as exc:  # noqa: BLE001 - a receipt, not a crash
            return {"error": str(getattr(exc, "detail", exc))[:300]}

    async def read(self, origins: Any = None, steps: Any = None) -> dict:
        """Run the steps; anything that would change the page is held, not sent."""
        return await self._run(origins, steps, [])

    async def submit(
        self, origins: Any = None, steps: Any = None, approved: list[str] | None = None
    ) -> dict:
        """Run the steps again with the held requests the person approved."""
        keys = [str(item) for item in approved or []][:8]
        if not keys:
            return {"error": "Name the held requests to send"}
        return await self._run(origins, steps, keys)

    def get_tool_schemas(self) -> list[dict]:
        steps = {
            "type": "array",
            "maxItems": 12,
            "items": {
                "type": "object",
                "properties": {
                    "do": {
                        "type": "string",
                        "enum": ["goto", "click", "fill", "press", "read", "screenshot", "wait"],
                    },
                    "url": {"type": "string"},
                    "role": {"type": "string"},
                    "name": {"type": "string"},
                    "label": {"type": "string"},
                    "value": {"type": "string"},
                    "key": {"type": "string"},
                },
                "required": ["do"],
            },
        }
        origins = {"type": "array", "items": {"type": "string"}, "maxItems": 8}
        return [
            {
                "name": "shahid_read",
                "description": "Use web pages in MIZAN's browser sandbox (go to, click, fill, read, screenshot) within the given sites; nothing is sent to a site.",
                "input_schema": {
                    "type": "object",
                    "properties": {"origins": origins, "steps": steps},
                    "required": ["origins", "steps"],
                },
            },
            {
                "name": "shahid_submit",
                "description": "Run browser steps again, sending the held requests the person approved (a form, an order).",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "origins": origins,
                        "steps": steps,
                        "approved": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
                    },
                    "required": ["origins", "steps", "approved"],
                },
            },
        ]
