"""Admin chat tools for preserved research and explicitly declared context reasoning."""

import asyncio
import sqlite3

from pydantic import Field, ValidationError

from mizan_owned import research
from mizan_owned.schemas import ContextRequest, StrictModel, resolve_context
from security.auth import current_user_id, request_has_role

from ..base import SkillBase, SkillManifest


class ResearchSearchRequest(StrictModel):
    query: str = Field(min_length=1, max_length=300)


def _admin_error() -> dict | None:
    if not current_user_id() or not request_has_role("admin"):
        return {
            "status": "forbidden",
            "error": "Research tools require an authenticated administrator",
        }
    return None


def _invalid_input(exc: ValidationError | ValueError) -> dict:
    if isinstance(exc, ValidationError):
        issues = [
            {"path": ".".join(str(part) for part in item["loc"]), "message": item["msg"]}
            for item in exc.errors(include_url=False, include_input=False)[:8]
        ]
    else:
        issues = [{"path": "context", "message": str(exc)}]
    return {"status": "invalid_input", "error": "Invalid declared research input", "issues": issues}


class ResearchArchiveSkill(SkillBase):
    manifest = SkillManifest(
        name="research_archive",
        description="Search the pinned local research archive and resolve explicitly supplied context evidence.",
        permissions=["research:read:pinned", "research:resolve:declared"],
        tags=["بحث", "Research"],
    )

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self._tools = {
            "mizan_research_search": self.search,
            "mizan_context_resolve": self.context_resolve,
        }

    async def execute(self, params: dict, context: dict | None = None) -> dict:
        """Identity comes only from the bound principal, never from params/context."""
        denied = _admin_error()
        if denied:
            return denied
        data = dict(params)
        action = data.pop("action", "search")
        if action == "search":
            try:
                request = ResearchSearchRequest.model_validate(data)
            except ValidationError as exc:
                return _invalid_input(exc)
            return await self.search(request.query)
        if action == "resolve":
            return await self.context_resolve(**data)
        return {"status": "invalid_input", "error": "Unknown research action"}

    async def search(self, query: str) -> dict:
        """Return local source excerpts; never import, execute or certify archive text."""
        denied = _admin_error()
        if denied:
            return denied
        try:
            request = ResearchSearchRequest(query=query)
        except ValidationError as exc:
            return _invalid_input(exc)
        try:
            results = await asyncio.to_thread(research.search, request.query)
        except (ValueError, OSError, sqlite3.Error):
            return {
                "status": "unavailable",
                "error": (
                    "The pinned research archive is not available. An administrator must "
                    "import or repair the verified local bundle before searching."
                ),
                "results": [],
                "verified_claim": False,
                "training_gold": False,
            }
        return {
            "status": "ok",
            "results": [{"source": "pinned_research_archive", **item} for item in results],
            "source_attributed": True,
            "verified_claim": False,
            "training_gold": False,
            "archive_code_executed": False,
            "limits": "Historical source text is not a current or independently verified conclusion.",
        }

    async def context_resolve(self, **params) -> dict:
        """Resolve only the supplied schema/observations; no free-text interpretation."""
        denied = _admin_error()
        if denied:
            return denied
        try:
            request = ContextRequest.model_validate(params)
            result = await asyncio.to_thread(resolve_context, request)
        except (ValidationError, ValueError) as exc:
            return _invalid_input(exc)
        return {
            "status": result["status"],
            "result": result,
            "mode": request.mode,
            "source_attributed": True,
            "observation_sources": [
                {"id": row.id, "source": row.source} for row in request.observations
            ],
            "verified_claim": False,
            "training_gold": False,
            "stateless": True,
            "observations_persisted": False,
            "requires_observations_each_call": True,
            "limits": (
                "Conditional on caller-supplied ontology, senses and observations. "
                "No free-text, source-truth or religious verification is performed."
            ),
        }

    def get_tool_schemas(self) -> list[dict]:
        return [
            {
                "name": "mizan_research_search",
                "description": (
                    "Admin-only local search of the previously imported pinned Mizan research "
                    "archive. Returns attributed paths, hashes and exact excerpts, not verified "
                    "claims or training gold. Reports unavailable if no valid import exists."
                ),
                "input_schema": ResearchSearchRequest.model_json_schema(),
            },
            {
                "name": "mizan_context_resolve",
                "description": (
                    "Admin-only finite/episodic reasoning over explicitly supplied ontology, "
                    "senses, observations and retractions. Preserve ambiguity/conflicts. Do not "
                    "invent labels or source evidence from free text. Stateless: resupply all "
                    "observations each call; results are conditional, unverified and not training."
                ),
                "input_schema": ContextRequest.model_json_schema(),
            },
        ]
