"""
MIZAN API Gateway (باب - Bab)
==============================

"And Allah is the Guardian (Wali) over His servants" - Quran 42:6

RESTful + WebSocket API for the MIZAN AGI System
Secured with Wali Guardian, Izn Permissions, and Input Validation
"""

import asyncio
import contextlib
import functools
import json
import logging
import os
import sys
import time
import unicodedata
import uuid
from contextlib import asynccontextmanager, nullcontext
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, cast

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, Response, StreamingResponse
from pydantic import BaseModel, Field, field_validator, model_validator
from starlette.datastructures import UploadFile as StarletteUploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import HTTPConnection

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Administrator-saved settings reach the environment before any module reads it.
import runtime_settings
import runtime_settings_bootstrap  # noqa: F401
from _version import __version__
from agents.agent_settings import AgentSettingsPatch
from agents.federation import AgentFederation
from agents.specialized import create_agent
from api.chat_stream import (
    HEARTBEAT_SECONDS,
    MAX_RESPONSE_CHARACTERS,
    TEXT_CHUNK_CHARACTERS,
    ChatEventChannel,
    ChatRunLease,
    ChatStreamingResponse,
    ChatStreamLedger,
    ChatTransportGuard,
    StreamDeliveryError,
)
from api.commands import handle_command
from automation.qadr import QadrScheduler
from automation.triggers import TriggerManager
from cognitive.thinking_stream import ThinkingPhase, ThinkingStream
from core.architecture import MizanBalancer, ShuraCouncil
from core.events import EVENTS, event_bus
from core.hooks import HOOKS, hook_registry
from core.middleware import middleware_pipeline
from core.plugins import plugin_manager
from core.qalb import QalbEngine
from memory.dhikr import CONSENT_PREFERENCES, DhikrMemorySystem
from memory.knowledge_graph import KnowledgeGraph
from mizan_owned.schemas import (
    ContextRequest,
    LearningRollbackRequest,
    LearningRunRequest,
    OwnedRequest,
    RetractionRequest,
    ReviewRequest,
    resolve_context,
)
from perception import basar
from providers import (
    COMPATIBLE_ENDPOINTS,
    check_provider_health,
    create_provider,
    fetch_compatible_models,
    fetch_ollama_models,
    fetch_openrouter_models,
    get_default_model,
    get_provider_status,
    normalize_model_for_provider,
    set_active_state,
)
from qca.cognitive_methods import select_method

# New Quranic systems
from qca.yaqin_engine import YaqinEngine
from reasoning.context_manager import ContextManager
from reasoning.planner import TafakkurPlanner
from security.auth import (
    MizanAuth,
    TokenPayload,
    bind_principal,
    current_user_id,
    reset_principal,
    set_request_roles,
)
from security.izn import IznPermission
from security.validation import InputValidator
from security.wali import RateLimiter, SecurityConfig, WaliGuardian
from skills.registry import SkillRegistry
from task_queue.priorities import TaskPriority
from task_queue.task_queue import MizanTaskQueue, QueuedTask
from task_queue.worker import TaskWorker
from training_manager import training_manager

logger = logging.getLogger("mizan.api")

# ===== LIFESPAN =====


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown logic."""
    import time as _time

    app.state.start_time = _time.time()
    logger.info("MIZAN (ميزان) Starting...")
    logger.info("   'And the heaven He raised and imposed the balance' - 55:7")

    try:
        interrupted = ChatStreamLedger(
            memory._get_conn, memory._release_conn
        ).interrupt_unfinished()
        if interrupted:
            logger.info(
                "Marked %d chat request(s) cut off by the restart as cancelled", interrupted
            )
    except Exception as exc:  # noqa: BLE001 - startup must not fail on a receipt table
        logger.warning("Chat receipts could not be checked at startup: %s", exc)

    # Create default agents if none exist
    existing = await memory.get_all_agents()
    if not existing:
        default_agents = [
            {"name": "Khalifah", "type": "super", "role": "Universal"},
            {"name": "Mubashir", "type": "browser", "role": "Browser"},
            {"name": "Mundhir", "type": "research", "role": "Researcher"},
            {"name": "Katib", "type": "code", "role": "Coder"},
        ]

        for da in default_agents:
            agent = create_agent(
                da["type"],
                name=da["name"],
                config={"model": os.getenv("DEFAULT_MODEL", "")},
                **_agent_services(),
            )
            agent.owner_id, agent.shared = None, True
            _publish_agent(agent)

            await memory.save_agent_profile(
                {
                    "id": agent.id,
                    "name": agent.name,
                    "role": da["type"],
                    "nafs_level": 1,
                    "capabilities": list(agent.tools.keys()),
                    "config": {"model": os.getenv("DEFAULT_MODEL", "")},
                    "owner_id": None,
                    "shared": True,
                }
            )
    else:
        for profile in existing:
            agent = create_agent(
                profile.get("role", "general"),
                agent_id=profile["id"],
                name=profile["name"],
                config=profile.get("config", {}),
                **_agent_services(),
            )
            agent.owner_id = profile.get("owner_id")
            agent.shared = bool(profile.get("shared", True))
            agent.total_tasks = profile.get("total_tasks", 0) or 0
            agent.learning_iterations = profile.get("learning_iterations", 0)
            # Restore the evidence Nafs evolution weighs, not just the count.
            agent.success_count = round(
                float(profile.get("success_rate") or 0.0) * agent.total_tasks
            )
            agent.error_count = profile.get("error_count", 0) or 0
            agent.nafs_level = max(1, min(7, int(profile.get("nafs_level") or 1)))
            agent._created_at = profile.get("created_at")
            try:
                agent.hikmah_count = await memory.count_hikmah(agent.id)
            except Exception:
                agent.hikmah_count = 0
            _publish_agent(agent)
            if isinstance(agent.config.get("provider_override"), dict) and agent.ai_client is None:
                # Its own provider cannot start (a key removed): it follows the default
                # provider now, and says so, instead of keeping a choice that never works.
                await _drop_stale_override(agent)

    logger.info(f"{len(active_agents)} agents initialized")

    # Inject global registry references into agents
    for agent in active_agents.values():
        _wire_agent(agent)

    # Restore persisted provider/model choice
    try:
        saved_provider = await memory.get_preference("active_provider")
        saved_model = await memory.get_preference("active_model")
        if saved_provider and saved_model:
            restored = create_provider(provider=saved_provider, model=saved_model)
            if restored:
                restored_model = normalize_model_for_provider(saved_model, restored.provider_name)
                for agent in active_agents.values():
                    override = agent.config.get("provider_override")
                    if isinstance(override, dict):
                        selected = create_provider(
                            provider=override.get("provider"), model=override.get("model")
                        )
                        if selected is not None:
                            agent.ai_client = selected
                            agent.ai_model = normalize_model_for_provider(
                                override["model"], selected.provider_name
                            )
                            continue
                        await _drop_stale_override(agent, save=False)
                    agent.ai_client, agent.ai_model = restored, restored_model
                    agent.config["model"] = restored_model
                    if getattr(agent, "provider_warning", None):
                        await memory.save_agent_profile(_agent_profile(agent))
                set_active_state(restored.provider_name, restored_model)
                logger.info(f"Restored provider: {saved_provider}/{saved_model}")
    except Exception as exc:
        logger.warning(f"Could not restore provider preference: {exc}")

    # Initialize scheduler executor
    async def execute_scheduled_task(task: str, agent_id: str | None = None):
        aid = agent_id or (choose_agent_for_task(task) if active_agents else None)
        if aid and aid in active_agents:
            agent = active_agents[aid]
            return await _run_unattended(agent, task, None, "schedule")
        return {"error": "No agent available"}

    scheduler.set_executor(execute_scheduled_task)
    trigger_manager.set_executor(execute_scheduled_task)
    await scheduler.start()

    # Load built-in skills
    try:
        skill_registry.discover_builtin()
    except Exception as e:
        logger.warning(f"Skill discovery: {e}")

    # Load plugins
    try:
        await plugin_manager.load_all()
        logger.info(f"[WASILAH] {len(plugin_manager._loaded)} plugins loaded")
    except Exception as e:
        logger.warning(f"Plugin loading: {e}")

    # Emit system startup event
    await event_bus.emit(
        "system.startup",
        {
            "agents": len(active_agents),
            "skills": len(skill_registry.list_skills()),
            "plugins": len(plugin_manager.list_plugins()),
        },
    )

    # Wire training manager to WebSocket broadcast
    training_manager.set_broadcast(manager.broadcast)

    # Initialize task queue + start worker
    global task_worker
    await task_queue.initialize()

    async def handle_queued_task(payload: dict) -> dict:
        """Route queued tasks to agents and broadcast results."""
        task_text = payload.get("task", "")
        agent_id = payload.get("agent_id")
        if not agent_id and active_agents:
            agent_id = choose_agent_for_task(task_text)
        if not agent_id or agent_id not in active_agents:
            return {"error": "No agent available"}
        agent = active_agents[agent_id]
        result = await _run_unattended(agent, task_text, payload.get("owner_id"), "queue")
        await manager.broadcast(
            {
                "type": "queue_task_complete",
                "task": task_text,
                "agent": agent.name,
                "result": result.get("response", str(result)),
            }
        )
        return cast(dict, result)

    task_worker = TaskWorker(task_queue, handle_queued_task, max_concurrent=3)
    asyncio.create_task(task_worker.start())
    logger.info("[QUEUE] Task queue initialized, worker started")

    from mizan_owned.learning_service import learning_service

    await learning_service.start()

    async def keep_model_limits_fresh() -> None:
        # Context windows and output caps drive history budgets and output
        # limits; refresh them from the providers' own catalogs hourly.
        from providers import refresh_model_limits

        while True:
            try:
                await refresh_model_limits()
            except Exception as exc:
                logger.debug("Model limit refresh failed: %s", exc)
            await asyncio.sleep(3600)

    async def maintain_memory() -> None:
        # Offline consolidation (Tafakkur/Nisyan, dream replay, living-memory
        # upkeep) on a fixed cadence instead of only on a manual request.
        try:
            interval = max(60.0, float(os.getenv("MIZAN_MEMORY_MAINTENANCE_SECONDS", "3600")))
        except ValueError:
            interval = 3600.0
        while True:
            await asyncio.sleep(interval)
            try:
                result = await memory.consolidate()
                logger.info("[DHIKR] Scheduled consolidation pruned %s", result["records_pruned"])
            except Exception as exc:
                logger.warning("Scheduled memory consolidation failed: %s", exc)
            for agent in list(active_agents.values()):
                for job in (
                    getattr(getattr(agent, "dream_engine", None), "run_consolidation", None),
                    getattr(getattr(agent, "living_memory", None), "run_maintenance", None),
                ):
                    if callable(job):
                        try:
                            await asyncio.to_thread(job)
                        except Exception as exc:
                            logger.debug("Agent memory maintenance failed: %s", exc)

    memory_maintenance_task = (
        asyncio.create_task(maintain_memory())
        if os.getenv("MIZAN_MEMORY_MAINTENANCE", "true").lower() not in {"0", "false", "no"}
        else None
    )

    model_limits_task = (
        asyncio.create_task(keep_model_limits_fresh())
        if os.getenv("MIZAN_MODEL_LIMITS_REFRESH", "true").lower() not in {"0", "false", "no"}
        else None
    )

    # Iqtibas reads the Quran's texts (fetched once, as Fihris fetches them) so a
    # message that quotes the Quran is recognised from the first chat; best effort.
    from tadbir import iqtibas

    iqtibas_task = asyncio.create_task(iqtibas.warm()) if iqtibas.enabled() else None

    async def self_review() -> None:
        # Muhasaba: MIZAN re-checks the answers the model gave in words and
        # posts a correction where it can prove one wrong.
        from tadbir import muhasaba

        await asyncio.sleep(600)
        while True:
            if os.getenv("MIZAN_MUHASABA", "on").lower() not in {"off", "0", "false", "no"}:
                try:
                    await muhasaba.run(memory)
                except Exception as exc:
                    logger.warning("Muhasaba review failed: %s", exc)
            try:
                interval = max(600.0, float(os.getenv("MIZAN_MUHASABA_SECONDS", "86400")))
            except ValueError:
                interval = 86400.0
            await asyncio.sleep(interval)

    self_review_task = asyncio.create_task(self_review())

    async def rest() -> None:
        # Nawm: while no request runs, the answers MIZAN learned from a teacher
        # are replayed by Need × Gain and asked of their sources again.
        from tadbir import nawm

        await asyncio.sleep(900)
        while True:
            if nawm.enabled():
                try:
                    await nawm_night()
                except Exception as exc:  # noqa: BLE001 - one night's failure ends that night
                    logger.warning("Nawm replay failed: %s", exc)
            try:
                interval = max(600.0, float(os.getenv("MIZAN_NAWM_SECONDS", "86400")))
            except ValueError:
                interval = 86400.0
            await asyncio.sleep(interval)

    rest_task = asyncio.create_task(rest())
    # Tadrib: the reader learns each lesson while no request runs.
    from tadbir import tadrib

    tadrib.configure(_no_run_active)

    async def watch_for_users() -> None:
        # Muraqabah: each user's watchers, judged against salah and attention.
        from automation import muraqabah

        await asyncio.sleep(30)
        while True:
            if os.getenv("MIZAN_MURAQABAH", "on").lower() not in {"off", "0", "false", "no"}:
                try:
                    await muraqabah.tick(
                        _muraqabah_store(),
                        datetime.now(UTC),
                        run_task=_watcher_task,
                        deliver=_watcher_deliver,
                        read_page=_watcher_page,
                    )
                except Exception as exc:
                    logger.warning("Muraqabah pass failed: %s", exc)
            await asyncio.sleep(60)

    watch_task = asyncio.create_task(watch_for_users())

    # Bab: the Telegram bot, when a token is set (long polling, no webhook).
    telegram_stop = asyncio.Event()
    telegram_task = None
    if os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("MIZAN_TELEGRAM", "on").lower() not in {
        "off",
        "0",
        "false",
        "no",
    }:
        global _telegram_bot
        from gateway import store as bab_store
        from gateway.telegram import TelegramBot

        _telegram_bot = TelegramBot(
            os.environ["TELEGRAM_BOT_TOKEN"],
            bab_store.store(),
            _bab_turn,
            _bab_decide,
            hear=_bab_hear,
        )
        telegram_task = asyncio.create_task(_telegram_bot.run(telegram_stop))

    # Bab: email, when MIZAN's own mailbox is configured (IMAP polling + SMTP).
    mail_task = None
    if os.getenv("MIZAN_EMAIL", "on").lower() not in {"off", "0", "false", "no"}:
        from gateway import mail as bab_mail

        mail_config = bab_mail.MailConfig.from_env()
        if mail_config is not None:
            global _mail_bot
            from gateway import store as bab_mail_store

            _mail_bot = bab_mail.MailBot(
                mail_config,
                bab_mail_store.store(),
                functools.partial(_bab_turn, channel="email"),
            )
            mail_task = asyncio.create_task(_mail_bot.run(telegram_stop))

    # Bab: WhatsApp (official Cloud API, webhook), when Meta's credentials are set.
    from gateway import whatsapp as bab_whatsapp

    whatsapp_config = bab_whatsapp.WhatsAppConfig.from_env()
    if whatsapp_config is not None and os.getenv("MIZAN_WHATSAPP", "on").lower() not in {
        "off",
        "0",
        "false",
        "no",
    }:
        global _whatsapp_bot
        from gateway import store as bab_whatsapp_store

        _whatsapp_bot = bab_whatsapp.WhatsAppBot(
            whatsapp_config,
            bab_whatsapp_store.store(),
            functools.partial(_bab_turn, channel="whatsapp"),
        )

    from connectors.manager import manager as connector_manager

    def _connector_owner_roles(user_id: str) -> list[str] | None:
        # Launch-time checks (a host stdio server) read the owner's roles now.
        record = auth.get_user(user_id)
        return list(record.roles) if record is not None and record.enabled else None

    connector_manager.role_lookup = _connector_owner_roles
    connector_manager.start()
    sakk_task = asyncio.create_task(_sakk_daily())

    logger.info("MIZAN ready - Bismillah!")

    yield  # App is running

    # Shutdown
    await connector_manager.shutdown()
    if model_limits_task is not None:
        model_limits_task.cancel()
    if iqtibas_task is not None:
        iqtibas_task.cancel()
    if memory_maintenance_task is not None:
        memory_maintenance_task.cancel()
    self_review_task.cancel()
    rest_task.cancel()
    watch_task.cancel()
    sakk_task.cancel()
    telegram_stop.set()
    if mail_task is not None:
        mail_task.cancel()
    if _whatsapp_bot is not None:
        await _whatsapp_bot.close()
    if telegram_task is not None and _telegram_bot is not None:
        telegram_task.cancel()
        await _telegram_bot.close()
    await learning_service.stop()
    if task_worker:
        await task_worker.stop()
        logger.info("[QUEUE] Task worker stopped")
    await event_bus.emit("system.shutdown", {})

    # Persist Masalik neural pathways to disk before shutdown
    try:
        if hasattr(memory, "masalik"):
            memory.masalik.save_to_disk()
            logger.info("[MASALIK] Neural pathways persisted to disk")
    except Exception as e:
        logger.warning(f"[MASALIK] Failed to save pathways: {e}")

    # Persist agent profiles
    try:
        for agent in active_agents.values():
            await memory.save_agent_profile(
                {
                    "id": agent.id,
                    "name": agent.name,
                    "role": agent.role,
                    "nafs_level": agent.nafs_level,
                    "capabilities": list(agent.tools.keys()),
                    "total_tasks": agent.total_tasks,
                    "success_rate": agent.success_rate,
                    "error_count": agent.error_count,
                    "learning_iterations": agent.learning_iterations,
                    "config": agent.config or {},
                }
            )
        logger.info(f"[AGENTS] {len(active_agents)} agent profiles persisted")
    except Exception as e:
        logger.warning(f"[AGENTS] Failed to persist profiles: {e}")

    await plugin_manager.unload_all()
    await scheduler.stop()
    logger.info("MIZAN shutdown complete")


# ===== APP INITIALIZATION =====

# Every shipped API route requires a principal unless explicitly public.
_PUBLIC_API = {
    "/",
    "/api/health",
    "/api/auth/login",
    "/api/auth/register",
    "/api/v1/root-analyze",
    "/api/v1/tokenize",
    "/api/v1/q28-features",
    "/api/openapi.json",
    "/api/docs",
    # Authorization servers redirect the browser here; the single-use OAuth
    # state (not a session) identifies the waiting connector, and the page
    # finishes with the person's own credential (/api/connectors/oauth/complete).
    "/api/connectors/oauth/callback",
    # MIZAN's OAuth client metadata document (its URL is MIZAN's client ID).
    "/api/connectors/oauth/client-metadata.json",
}
# Dev-server previews: the capability in the path is the credential, and every
# response carries a CSP sandbox (opaque origin), so no session is involved.
_PUBLIC_API_PREFIXES = ("/api/workspaces/preview/",)
# Read-only pages anyone may see (the reliability scorecard, signed Sakk roots).
_OPEN_API_PREFIXES = ("/api/public/",)
_ADMIN_PREFIXES = (
    "/api/status",
    "/api/integrations",
    "/api/nafs",
    "/api/settings",
    "/api/security",
    "/api/plugins",
    "/api/training",
    "/api/owned/support",
    "/api/owned/reviews",
    "/api/owned/retract",
    "/api/owned/export",
    "/api/owned/research",
    "/api/owned/learning",
    "/api/automation",
    "/api/channels",
    "/api/gateway",
    "/api/doctor",
    "/api/events",
    "/api/hooks",
    "/api/middleware",
    "/api/extensibility",
    "/api/tasks",
    "/api/memory",
    "/api/queue",
    "/api/federation",
    "/api/plan",
    "/api/perception",
    "/api/knowledge",
    "/api/shura",
)


async def enforce_api_access(request: HTTPConnection):
    if request.scope["type"] == "websocket":
        yield
        return
    if request.url.path in _PUBLIC_API or request.url.path.startswith(
        _PUBLIC_API_PREFIXES + _OPEN_API_PREFIXES
    ):
        yield
        return
    principal = await require_auth(
        request.headers.get("authorization"), request.headers.get("x-api-key")
    )
    path = request.url.path
    administrative = path.startswith(_ADMIN_PREFIXES) or path == "/api/version"
    if request.scope.get("method") not in {"GET", "HEAD", "OPTIONS"}:
        # /api/agents is not here: everyone may make agents of their own, and each
        # agent route checks that the caller owns the agent (or is an administrator).
        administrative |= path.startswith(
            (
                "/api/providers",
                "/api/preferences",
                "/api/skills",
                "/api/sandbox",
                "/api/memory",
            )
        )
    if administrative and not principal.has_role("admin"):
        raise HTTPException(403, "Administrator role required")
    binding = bind_principal(principal)
    try:
        yield
    finally:
        reset_principal(binding)


app = FastAPI(
    title="MIZAN (ميزان) - Agentic Personal AI",
    description=(
        "MIZAN's API. Sign in with POST /api/auth/login and send "
        "`Authorization: Bearer <token>` (or `X-API-Key`). Who may call each route: "
        "docs/api-reference.md. Measured reliability: /api/public/reliability."
    ),
    version=__version__,
    lifespan=lifespan,
    dependencies=[Depends(enforce_api_access)],
    # Under /api/, where the proxy sends requests to the backend (the site's own
    # /docs is the web app).
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
    redoc_url=None,
)

# ===== SECURITY INITIALIZATION =====

security_config = SecurityConfig.from_env()
wali = WaliGuardian(security_config)
auth = MizanAuth(
    secret_key=security_config.secret_key,
    expiry_hours=security_config.jwt_expiry_hours,
)
izn = IznPermission()
validator = InputValidator(max_input_length=security_config.max_input_length)


class _OriginBoundCORS(CORSMiddleware):
    """Starlette sends Access-Control-Allow-Credentials on every response that
    has an Origin header, matched or not; it is sent here only together with
    a matched, echoed origin."""

    async def simple_response(self, scope, receive, send, request_headers) -> None:
        origin = request_headers.get("origin", "")
        if self.is_allowed_origin(origin):
            await super().simple_response(scope, receive, send, request_headers)
            return

        async def without_credentials(message):
            if message["type"] == "http.response.start":
                message["headers"] = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower() != b"access-control-allow-credentials"
                ]
            await send(message)

        await super().simple_response(scope, receive, without_credentials, request_headers)


# CORS - configurable, not wildcard
app.add_middleware(
    _OriginBoundCORS,
    allow_origins=security_config.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "PUT"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)

# ===== GLOBAL STATE =====
memory = DhikrMemorySystem(db_path=os.getenv("DB_PATH", "/data/mizan_memory.db"))
knowledge_graph = KnowledgeGraph(db_path=os.getenv("DB_PATH", "/data/mizan_memory.db"))
context_manager = ContextManager()
planner = TafakkurPlanner()
balancer = MizanBalancer()
shura = ShuraCouncil()
active_agents: dict[str, Any] = {}
active_sessions: dict[str, dict] = {}
scheduler = QadrScheduler()
trigger_manager = TriggerManager()
skill_registry = SkillRegistry()

# New Quranic system instances
yaqin_engine = YaqinEngine()
qalb_engine = QalbEngine()
federation = AgentFederation()
thinking_stream = ThinkingStream()

# Task queue + worker
task_queue = MizanTaskQueue(db_path=os.getenv("QUEUE_DB_PATH", "/data/mizan_queue.db"))
task_worker: TaskWorker | None = None


# ===== AUTHENTICATION BEFORE THE BODY =====


@app.middleware("http")
async def credentials_first(request: Request, call_next):
    """A request with no valid credential is answered 401 before its body is
    read, so a malformed body from an unknown caller is never parsed (route
    dependencies run only after the body). Roles are still checked by
    ``enforce_api_access``."""
    path = request.url.path
    if (
        request.method == "OPTIONS"
        or not path.startswith("/api/")
        or path in _PUBLIC_API
        or path.startswith(_PUBLIC_API_PREFIXES + _OPEN_API_PREFIXES)
        or auth.extract_token(
            request.headers.get("authorization"), request.headers.get("x-api-key")
        )
    ):
        return await call_next(request)
    return JSONResponse(status_code=401, content=error_body(401, "Authentication required"))


# ===== SECURITY HEADERS MIDDLEWARE =====


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Add security headers to all responses"""
    response = await call_next(request)

    if request.url.path.startswith(_PUBLIC_API_PREFIXES):
        # Previews are framed by Mizan itself and keep their own sandbox policy.
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    # Prevent clickjacking attacks
    response.headers["X-Frame-Options"] = "DENY"

    # Prevent MIME type sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"

    # Enable browser XSS protection
    response.headers["X-XSS-Protection"] = "1; mode=block"

    # Strict transport security (HTTPS only)
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    # Content Security Policy (the API's docs page loads Swagger UI from jsDelivr)
    cdn = " https://cdn.jsdelivr.net" if request.url.path == "/api/docs" else ""
    response.headers["Content-Security-Policy"] = (
        f"default-src 'self'; script-src 'self' 'unsafe-inline'{cdn}; "
        f"style-src 'self' 'unsafe-inline'{cdn}; img-src 'self' data:{cdn and ' https://fastapi.tiangolo.com'}"
    )

    # Referrer policy
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    # Permissions policy
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

    return response


# ===== GLOBAL EXCEPTION HANDLER =====


# One error shape on every route: FastAPI's `detail` (what clients already
# read) and a stable `error` object: a machine code, the status, a sentence.
_ERROR_CODES = {
    400: "bad_request",
    401: "unauthenticated",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "too_large",
    422: "invalid_request",
    429: "rate_limited",
    500: "internal",
    502: "upstream_failed",
    503: "unavailable",
}


def error_body(status: int, detail: Any) -> dict:
    message = detail if isinstance(detail, str) else "The request is not valid"
    return {
        "detail": detail,
        "error": {
            "code": _ERROR_CODES.get(status, "error" if status >= 400 else "ok"),
            "status": status,
            "message": message,
        },
    }


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(exc.status_code, exc.detail),
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    # Where and why, never the input itself: a 10 MB image must not come back
    # as a 14 MB error, and a rejected value is not echoed to the caller.
    errors = [
        {key: value for key, value in error.items() if key not in ("input", "ctx", "url")}
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content=error_body(422, jsonable_encoder(errors)))


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler - never expose stack traces"""
    import traceback

    logger.error(f"Unhandled exception: {exc}\n{traceback.format_exc()}")
    detail = str(exc) if os.getenv("DEBUG") else "An unexpected error occurred"
    return JSONResponse(status_code=500, content=error_body(500, detail))


# ===== AUTH DEPENDENCY =====


async def get_current_user(
    authorization: str | None = Header(None),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
) -> TokenPayload | None:
    """
    Extract user from auth headers.
    Returns None if no auth (allows open access with optional auth).
    For protected endpoints, use require_auth instead.
    """
    return await require_auth(authorization, x_api_key)


async def require_auth(
    authorization: str | None = Header(None),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
) -> TokenPayload:
    """Require authentication - raises 401 if not authenticated"""
    token = auth.extract_token(authorization, x_api_key)
    if not token:
        raise HTTPException(401, "Authentication required")
    set_request_roles(token.roles)
    return token


# ===== PYDANTIC MODELS (with validation) =====

AGENT_PROVIDER_PATTERN = r"^(anthropic|openrouter|openai|xai|meta|ollama|ruh|ruh-remote|qwen3|mizan-hybrid|mizan-owned|mizan-minimind)$"


AGENT_TYPE_PATTERN = (
    r"^(super|khalifah|general|browser|research|code|communication|wakil|mubashir|mundhir|"
    r"katib|rasul)$"
)


class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    type: str = Field(default="super", pattern=AGENT_TYPE_PATTERN)
    provider: str | None = Field(default=None, pattern=AGENT_PROVIDER_PATTERN)
    model: str | None = Field(default=None, min_length=1, max_length=200)
    system_prompt: str | None = Field(None, max_length=10000)
    # The tools this agent is made for: its settings.tools_allow when that is not given.
    capabilities: list[str] = Field(default_factory=list, max_length=200)
    settings: AgentSettingsPatch | None = None
    # Shared with everyone (administrators only; anyone else's agent is their own).
    shared: bool | None = None


class AgentUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    model: str | None = Field(None, max_length=200)
    system_prompt: str | None = Field(None, max_length=10000)
    # Merged key by key; a key sent as null goes back to its default.
    settings: AgentSettingsPatch | None = None


class AgentExportBody(BaseModel):
    """One agent in ``mizan-agent/1``: no keys, no memory, no record."""

    name: str = Field(..., min_length=1, max_length=100)
    type: str = Field(default="general", pattern=AGENT_TYPE_PATTERN)
    provider: str | None = Field(default=None, pattern=AGENT_PROVIDER_PATTERN)
    model: str | None = Field(default=None, min_length=1, max_length=200)
    system_prompt: str | None = Field(None, max_length=10000)
    settings: AgentSettingsPatch | None = None


class TaskRequest(BaseModel):
    task: str = Field(..., min_length=1, max_length=50000)
    agent_id: str | None = None
    context: dict | None = None
    parallel: bool = False


class ChatMessage(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    content: str = Field(..., min_length=1, max_length=50000)
    agent_id: str | None = None
    model_override: str | None = Field(None, max_length=200)
    # The browser's IANA timezone, for dates MIZAN states itself (Tadbir Waqt).
    timezone: str | None = Field(None, max_length=64, pattern=r"^[A-Za-z0-9_+\-/]+$")


class ImageIn(BaseModel):
    media_type: str = Field("image/png", pattern=r"^image/(png|jpeg|jpg|webp|gif)$")
    # base64 of the file, with or without a data: prefix (10 MB of image at most)
    data: str = Field(..., min_length=8, max_length=14_000_000)


class CodingFix(BaseModel):
    """An error the person asked MIZAN to fix ("Fix with MIZAN" on the preview)."""

    source: str = Field("preview", pattern=r"^(preview|server|terminal)$")
    error: str = Field(..., min_length=1, max_length=8000)


class StreamChatMessage(ChatMessage):
    # One UUID per user action: a client that resends it after an ambiguous
    # network failure never creates a second model call. A client that omits
    # it gets one made here (sent back in every event), and its retries are
    # new requests.
    request_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    workspace_id: str | None = Field(None, min_length=1, max_length=100)
    # Izn for interactive chats: auto | auto_edits | ask | plan. Omitted keeps
    # the legacy behaviour (no prompts) for older clients.
    permission_mode: str | None = Field(None, pattern=r"^(auto|auto_edits|ask|plan)$")
    # Images the user attached (Basar): shown to the model with this message.
    images: list[ImageIn] = Field(default_factory=list, max_length=4)
    # The agents' internal telemetry ("thinking" events, cognitive scores) is
    # sent only when asked for (the web app's thinking panel); by default the
    # stream carries the answer, its status and its receipts.
    thinking: bool = False
    # An evaluation: no recall of other chats, nothing learned, nothing captured
    # as a training candidate (memory/stateless.py). Reported in usage.memory.
    stateless: bool = False
    # Buttons, never words (Fahm reads "go ahead" as conversation): the person approved
    # the plan the last answer made, or asks MIZAN to fix an error its project showed.
    # Either gives the request to the model with the project's tools (Tadbir).
    plan_approved: bool = False
    fix: CodingFix | None = None

    @model_validator(mode="after")
    def _coding_button(self) -> "StreamChatMessage":
        if (self.plan_approved or self.fix) and self.permission_mode in (None, "plan"):
            raise ValueError("plan_approved and fix need a permission_mode that allows changes")
        if self.plan_approved and self.fix:
            raise ValueError("Send plan_approved or fix, not both")
        return self


class IntegrationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    type: str = Field(..., pattern=r"^(mcp|openai|anthropic|openrouter|ollama|webhook|email)$")
    config: dict = {}
    enabled: bool = True


class MemoryQuery(BaseModel):
    query: str = Field(..., min_length=1, max_length=5000)
    memory_type: str | None = Field(None, pattern=r"^(episodic|semantic|procedural)$")
    agent_id: str | None = None
    limit: int = Field(default=10, ge=1, le=100)


class MemoryStore(BaseModel):
    content: str = Field(..., min_length=1, max_length=50000)
    memory_type: str = Field(default="semantic", pattern=r"^(episodic|semantic|procedural)$")
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    tags: list[str] = []
    expires: str = Field(default="", max_length=40)


class DaftarEdit(BaseModel):
    content: str | None = Field(None, min_length=1, max_length=50000)
    tags: list[str] | None = None
    expires: str | None = Field(None, max_length=40)


class DaftarForget(BaseModel):
    ids: list[str] = Field(default_factory=list, max_length=500)
    topic: str = Field(default="", max_length=200)
    confirm: bool = False


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=200)


MINIMUM_AGE = 16  # the owner's decision of 30 Oct 2026 (docs/consent.md)


class RegisterRequest(LoginRequest):
    age_16_or_older: bool = Field(
        False, description=f"The person confirms they are {MINIMUM_AGE} or older."
    )


class ShuraRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=10000)
    context: dict = {}


class ScheduleJobRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    cron: str = Field(..., min_length=1, max_length=100)
    task: str = Field(..., min_length=1, max_length=10000)
    agent_id: str | None = None


class WebhookCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    task_template: str = Field(..., min_length=1, max_length=10000)
    agent_id: str | None = None
    secret: str | None = None


class SkillInstallRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)


class MultimodalInput(BaseModel):
    """Input for multimodal perception analysis (text + image + audio)."""

    text: str = Field(default="", max_length=50000)
    image_base64: str | None = None  # base64-encoded image
    audio_base64: str | None = None  # base64-encoded audio
    media_type: str = Field(default="image/png", max_length=50)
    agent_id: str | None = None
    qalb_state: str = Field(default="", max_length=50)

    # NOTE: Startup and shutdown logic is handled by the lifespan context manager above.


# ===== WEBSOCKET MANAGER =====


class ConnectionManager:
    def __init__(self, max_connections: int = 50):
        self.connections: dict[str, WebSocket] = {}
        self.max_connections = max_connections
        self.owners: dict[str, str] = {}

    async def connect(self, ws_id: str, websocket: WebSocket) -> bool:
        if len(self.connections) >= self.max_connections:
            await websocket.close(code=1013, reason="Max connections reached")
            return False
        await websocket.accept()
        self.connections[ws_id] = websocket
        return True

    def disconnect(self, ws_id: str):
        self.connections.pop(ws_id, None)
        self.owners.pop(ws_id, None)

    async def send(self, ws_id: str, data: dict) -> bool:
        ws = self.connections.get(ws_id)
        if ws:
            try:
                await ws.send_json(json.loads(json.dumps(data, default=str)))
                return True
            except Exception:
                logger.error("WebSocket send failed for %s", ws_id, exc_info=True)
                self.disconnect(ws_id)
        return False

    async def send_required(self, ws_id: str, data: dict):
        if not await self.send(ws_id, data):
            raise asyncio.CancelledError("WebSocket delivery stopped")

    async def broadcast(self, data: dict):
        owner = current_user_id()
        session_id = data.get("session_id")
        if session_id:
            owner = await memory.session_owner(session_id)
            if not owner:
                return
        disconnected = []
        for ws_id, ws in list(self.connections.items()):
            if not owner or self.owners.get(ws_id) != owner:
                continue
            try:
                await ws.send_json(json.loads(json.dumps(data, default=str)))
            except Exception:
                logger.error("WebSocket broadcast failed for %s", ws_id, exc_info=True)
                disconnected.append(ws_id)
        for ws_id in disconnected:
            self.disconnect(ws_id)


manager = ConnectionManager(max_connections=security_config.ws_max_connections)


# ===== AUTH ROUTES =====


# Failed sign-ins, counted per client and per account name: five a minute,
# then 429 with Retry-After (a forwarded client address can be forged, the
# account name cannot be spread). A successful sign-in costs nothing.
_login_failures = RateLimiter(per_minute=5, burst=5)


class _SettingLimiter(RateLimiter):
    """A token bucket whose rate is an administrator's setting, read on every check."""

    def __init__(self, setting: str, default: int):
        super().__init__(per_minute=default, burst=max(10, default // 3))
        self.setting, self.default = setting, default

    def _sync(self) -> None:
        try:
            rate = int(float(os.getenv(self.setting, str(self.default))))
        except (TypeError, ValueError, OverflowError):
            rate = self.default
        self.per_minute = max(1, min(rate, 10_000))
        self.burst = max(10, self.per_minute // 3)

    def check(self, key: str) -> bool:
        self._sync()
        return bool(super().check(key))

    def peek(self, key: str) -> float:
        self._sync()
        return float(super().peek(key))


# Chat messages per signed-in user (each message may start model work):
# MIZAN_CHAT_PER_MINUTE, default 60.
_chat_messages = _SettingLimiter("MIZAN_CHAT_PER_MINUTE", 60)


def _rate_headers(limiter: RateLimiter, key: str) -> dict[str, str]:
    remaining = max(0, int(limiter.peek(key)))
    headers = {"RateLimit-Limit": str(limiter.per_minute), "RateLimit-Remaining": str(remaining)}
    wait = limiter.wait_seconds(key)
    if wait:
        headers["Retry-After"] = str(wait)
        headers["RateLimit-Reset"] = str(wait)
    return headers


@app.post("/api/auth/login")
async def login(req: LoginRequest, request: Request):
    """Authenticate and get JWT token"""
    client = request.client.host if request.client else "unknown"
    keys = (f"ip:{client}", f"user:{req.username.casefold()}")
    for key in keys:
        if _login_failures.peek(key) < 1:
            raise HTTPException(
                429,
                "Too many failed sign-ins; try again later",
                headers=_rate_headers(_login_failures, key),
            )
    user = auth.authenticate(req.username, req.password)
    if not user:
        for key in keys:
            _login_failures.check(key)
        wali.audit.log("login_failed", {"username": req.username}, severity="warning")
        # Add delay on failed login to prevent brute force attacks
        await asyncio.sleep(1)
        raise HTTPException(
            401, "Invalid credentials", headers=_rate_headers(_login_failures, keys[1])
        )

    token = auth.create_token(user)
    wali.audit.log("login_success", {"username": req.username, "user_id": user.id})
    return {"token": token, "user_id": user.id, "username": user.username, "roles": user.roles}


@app.post("/api/auth/register")
async def register(req: RegisterRequest):
    """Register a new user aged 16 or older (docs/consent.md): chats with an
    Islamic assistant reveal religious belief, a special category of personal
    data, and a younger child needs a parent's consent."""
    if not req.age_16_or_older:
        raise HTTPException(
            422, f"MIZAN is for people aged {MINIMUM_AGE} or older; confirm your age to sign up"
        )
    # Check if username already exists
    for u in auth._users.values():
        if u.username == req.username:
            raise HTTPException(409, "Username already exists")

    user = auth.create_user(req.username, req.password, roles=["user"])
    token = auth.create_token(user)
    wali.audit.log(
        "user_registered",
        {"username": req.username, "user_id": user.id, "age_attested": MINIMUM_AGE},
    )
    return {"token": token, "user_id": user.id, "username": user.username}


@app.get("/api/auth/me")
async def auth_me(user: TokenPayload = Depends(require_auth)):
    """Who this credential belongs to, its roles, when the token expires, and the
    server's default permission mode for chats."""
    from datetime import UTC, datetime

    from security.approvals import default_mode as default_permission_mode

    def moment(value: float) -> str:
        return datetime.fromtimestamp(value, UTC).isoformat(timespec="seconds")

    api_key = user.jti.startswith("apikey_")
    return {
        "user_id": user.user_id,
        "username": user.username,
        "roles": user.roles,
        "credential": "api_key" if api_key else "token",
        "issued_at": None if api_key else moment(user.iat),
        "expires_at": None if api_key else moment(user.exp),
        # What a chat does before an action when it sends no mode of its own.
        "default_permission_mode": default_permission_mode(),
    }


class LogoutRequest(BaseModel):
    # Also end every other token this account was given before now.
    everywhere: bool = False


@app.post("/api/auth/logout")
async def logout(req: LogoutRequest | None = None, user: TokenPayload = Depends(require_auth)):
    """End this token now (it stays revoked across restarts); with
    ``everywhere``, every token the account was given before now."""
    if user.jti.startswith("apikey_"):
        raise HTTPException(400, "An API key is not a session: remove the key instead")
    auth.revoke_token(user.jti, user.exp)
    everywhere = bool(req and req.everywhere)
    if everywhere:
        auth.revoke_all(user.user_id)
    wali.audit.log("logout", {"user_id": user.user_id, "everywhere": everywhere})
    return {"logged_out": True, "everywhere": everywhere}


@app.post("/api/auth/api-key")
async def create_api_key(user: TokenPayload = Depends(require_auth)):
    """Create an API key for the authenticated user"""
    key = auth.create_api_key(user.user_id)
    if not key:
        raise HTTPException(404, "User not found")
    return {"api_key": key}


# ===== ROUTES =====


@app.get("/")
async def root():
    return {
        "system": "MIZAN (ميزان)",
        "verse": "And the heaven He raised and imposed the balance (Mizan) - 55:7",
        "version": __version__,
        "agents": len(active_agents),
        "status": "active",
    }


# === AGENTS ===


_AGENT_SUMMARY = ("id", "name", "role", "state", "nafs_level", "current_task", "model", "load")
# A person may keep this many agents of their own (each is a full agent in memory).
MAX_AGENTS_PER_USER = 50
AGENT_EXPORT_FORMAT = "mizan-agent/1"


def _agent_summary(found: dict) -> dict:
    """An agent in a few fields (the full profile is several kilobytes)."""
    return {key: found.get(key) for key in _AGENT_SUMMARY if key in found}


# ── Personal agents (docs/personal-agents.md) ─────────────────────────────


def _agent_services(**overrides: Any) -> dict:
    """What every agent is built with: at startup, a new agent and a user's own copy."""
    services: dict[str, Any] = {
        "memory": memory,
        "wali": wali,
        "izn": izn,
        "skill_registry": skill_registry,
        "plugin_manager": plugin_manager,
        "knowledge_graph": knowledge_graph,
        "context_manager": context_manager,
        "planner": planner,
    }
    services.update(overrides)
    return services


def _wire_agent(agent, registry: dict | None = None):
    """Give an agent the registry it delegates in (all agents, or a user's own team),
    the balancer and the Shura council."""
    agent._agent_registry = active_agents if registry is None else registry
    agent._balancer = balancer
    agent._shura = shura
    return agent


def _publish_agent(agent) -> None:
    active_agents[agent.id] = agent
    balancer.register(agent.id)
    shura.members[agent.id] = agent
    _wire_agent(agent)


def _agent_profile(agent) -> dict:
    """The agent as saved: its live record too, so an edit never resets its counters."""
    return {
        "id": agent.id,
        "name": agent.name,
        "role": agent.role,
        "nafs_level": agent.nafs_level,
        "capabilities": list(agent.tools),
        "config": agent.config,
        "created_at": getattr(agent, "_created_at", None),
        "total_tasks": agent.total_tasks,
        "success_rate": agent.success_rate,
        "error_count": agent.error_count,
        "learning_iterations": agent.learning_iterations,
        "owner_id": getattr(agent, "owner_id", None),
        "shared": bool(getattr(agent, "shared", True)),
    }


async def _drop_stale_override(agent, *, save: bool = True) -> None:
    """An agent whose own provider cannot start follows the default one, and says so."""
    override = agent.config.pop("provider_override", None) or {}
    name = str(override.get("provider") or "its provider")
    agent.provider_warning = (
        f"{name} could not start (check its API key in Settings), so this agent now uses "
        "the default provider. Choose a model for it again to set its own."
    )
    if agent.ai_client is None:
        agent.ai_client = create_provider()
        if agent.ai_client is not None:
            agent.ai_model = get_default_model(agent.ai_client.provider_name)
            agent.config["model"] = agent.ai_model
    agent._config_revision = getattr(agent, "_config_revision", 0) + 1
    logger.warning("Agent %s: %s", agent.name, agent.provider_warning)
    if save:
        await memory.save_agent_profile(_agent_profile(agent))


def _permission_mode(agent) -> str:
    """The permission mode of a chat that sends none: the agent's own, else the
    server's default (MIZAN_DEFAULT_PERMISSION_MODE)."""
    from agents import agent_settings
    from security.approvals import default_mode

    own = agent_settings.of(getattr(agent, "config", None)).get("permission_mode")
    return str(own) if own in agent_settings.PERMISSION_MODES else default_mode()


def _broadcast_view(agent) -> dict:
    """What every open WebSocket is told of an agent: a shared agent without its
    persona; nothing of someone's own agent (empty: not broadcast)."""
    if not getattr(agent, "shared", True):
        return {}
    data: dict = dict(agent.to_dict())
    data.pop("system_prompt", None)
    return data


def _settings_allowed(user: Any, settings: dict | None) -> None:
    """Orchestration "llm" turns MIZAN's own recipes off, so the model would answer
    Quran and hadith requests itself: only an administrator may choose it for an agent."""
    if settings and settings.get("orchestration") == "llm" and not _agent_admin(user):
        raise HTTPException(
            403, "Only an administrator may let the model drive every request (llm)"
        )


def _caller(user: Any) -> TokenPayload | None:
    """The signed-in caller; None for an internal call (never from a request: every
    agent route requires a credential)."""
    return user if isinstance(user, TokenPayload) else None


def _agent_admin(user: Any) -> bool:
    caller = _caller(user)
    return caller is None or caller.has_role("admin")


def _agent_visible(user: Any, agent) -> bool:
    """Administrators see every agent; everyone else the shared ones and their own."""
    caller = _caller(user)
    if caller is None or caller.has_role("admin"):
        return True
    return bool(getattr(agent, "shared", True)) or getattr(agent, "owner_id", None) == (
        caller.user_id
    )


def _agent_editable(user: Any, agent) -> bool:
    caller = _caller(user)
    if caller is None or caller.has_role("admin"):
        return True
    return bool(getattr(agent, "owner_id", None) == caller.user_id)


def _visible_agents(user: Any) -> dict:
    """The agents this caller may see, by id (slash commands list only these)."""
    return {key: agent for key, agent in active_agents.items() if _agent_visible(user, agent)}


def _visible_agent(user: Any, agent_id: str):
    agent = active_agents.get(agent_id)
    if agent is None or not _agent_visible(user, agent):
        raise HTTPException(404, "Agent not found")
    return agent


def _editable_agent(user: Any, agent_id: str):
    agent = _visible_agent(user, agent_id)
    if not _agent_editable(user, agent):
        raise HTTPException(403, "Only this agent's owner or an administrator may change it")
    return agent


def _default_agent_key(user_id: str) -> str:
    return f"default_agent:{user_id}"


async def _default_agent_id(user_id: str) -> str | None:
    """The person's own default agent, when it still exists and they may use it."""
    if not user_id:
        return None
    try:
        chosen = await memory.get_preference(_default_agent_key(user_id))
    except Exception:  # noqa: BLE001 - a preference read must not stop a chat
        return None
    agent = active_agents.get(chosen) if chosen else None
    if agent is None:
        return None
    if not getattr(agent, "shared", True) and getattr(agent, "owner_id", None) != user_id:
        principal = _owner_token(user_id)
        if principal is None or not principal.has_role("admin"):
            return None  # no longer theirs to use
    return str(chosen)


async def _default_agent_for(user_id: str):
    """The agent channels (Telegram, email, WhatsApp) and watchers use for this person:
    their default agent, else Khalifah."""
    chosen = await _default_agent_id(user_id)
    return active_agents.get(chosen) if chosen else _tadbir_coordinator()


_UNSET: Any = object()


async def _agent_view(user: Any, agent, *, template=None, default_id: Any = _UNSET) -> dict:
    """An agent as this caller sees it: whether they may change it, whether it is their
    default, and its persona only when they may change it."""
    template = template or agent
    data: dict = dict(agent.to_dict())
    data["id"] = template.id
    data["owner_id"] = getattr(template, "owner_id", None)
    data["shared"] = bool(getattr(template, "shared", True))
    data["provider_warning"] = getattr(template, "provider_warning", None)
    editable = _agent_editable(user, template)
    data["editable"] = editable
    caller = _caller(user)
    if default_id is _UNSET:
        default_id = await _default_agent_id(caller.user_id) if caller is not None else None
    data["is_default"] = bool(default_id and default_id == template.id)
    if not editable:
        data.pop("system_prompt", None)
    from tadbir import martaba

    # The trust stage its record earned (report only: it restricts nothing).
    data["martaba"] = martaba.view(agent)
    return data


def _new_agent_config(
    model: str, system_prompt: str | None, settings: dict | None, capabilities: list[str]
) -> dict[str, Any]:
    from agents import agent_settings

    config: dict[str, Any] = {"model": model, "system_prompt": system_prompt}
    patch = dict(settings or {})
    if capabilities and not patch.get("tools_allow"):
        # AgentCreate.capabilities: the tools this agent is made for.
        patch["tools_allow"] = list(capabilities)
    agent_settings.apply(config, agent_settings.merge({}, patch))
    return config


async def _build_agent(
    user: Any,
    *,
    name: str,
    agent_type: str,
    provider: str | None,
    model: str | None,
    system_prompt: str | None,
    settings: dict | None,
    capabilities: list[str] | None = None,
    shared: bool | None = None,
):
    """Resolve a provider once, then persist the validated agent before publishing it."""
    _settings_allowed(user, settings)
    caller = _caller(user)
    if caller is not None and not caller.has_role("admin"):
        owned = sum(
            1
            for agent in active_agents.values()
            if getattr(agent, "owner_id", None) == caller.user_id
        )
        if owned >= MAX_AGENTS_PER_USER:
            raise HTTPException(413, f"You have {owned} agents; delete one to make another")
    selected_provider = provider
    selected_model = model
    if selected_provider is None or selected_model is None:
        runtime = get_provider_status()
        selected_provider = selected_provider or runtime.get("active")
        if selected_model is None:
            if selected_provider == runtime.get("active") and selected_provider:
                selected_model = runtime.get("default_model") or get_default_model(
                    selected_provider
                )
            else:
                # get_default_model also reads global DEFAULT_MODEL, which
                # belongs to the active provider. An explicitly selected other
                # provider must use its own catalog default or an explicit ID.
                selected_model = next(
                    (
                        item.get("default_model")
                        for item in runtime.get("providers", [])
                        if item.get("name") == selected_provider
                    ),
                    None,
                )
    if not selected_provider or not selected_model or not selected_model.strip():
        raise HTTPException(400, "Select a configured provider and a model")
    config = _new_agent_config(selected_model, system_prompt, settings, capabilities or [])
    config["provider_override"] = {"provider": selected_provider, "model": selected_model}

    # BaseAgent invokes the shared factory, including its owned-only guard.
    # Building privately avoids a second provider initialization or a partial
    # agent becoming visible when that factory rejects the selection.
    try:
        agent = create_agent(agent_type, name=name, config=config, **_agent_services())
    except Exception as exc:
        logger.warning("Agent initialization unavailable (%s)", type(exc).__name__)
        raise HTTPException(400, "Cannot initialize the requested provider") from exc
    if agent.ai_client is None:
        raise HTTPException(400, "Cannot initialize the requested provider")
    config["model"] = agent.ai_model
    config["provider_override"] = {
        "provider": agent.ai_client.provider_name,
        "model": agent.ai_model,
    }
    # Administrators make agents for everyone unless they say otherwise; anyone
    # else's agent is their own.
    admin = caller is None or caller.has_role("admin")
    agent.owner_id = caller.user_id if caller is not None else None
    agent.shared = (True if shared is None else bool(shared)) if admin else False
    agent._created_at = datetime.now(UTC).isoformat()

    await memory.save_agent_profile({**_agent_profile(agent), "role": agent_type})
    _publish_agent(agent)

    if view := _broadcast_view(agent):  # someone's own agent is told to no one else
        await manager.broadcast({"type": "agent_created", "agent": view})

    wali.audit.log("agent_created", {"agent_id": agent.id, "name": agent.name, "type": agent_type})
    await event_bus.emit(
        "agent.created", {"agent_id": agent.id, "name": agent.name, "type": agent_type}
    )
    return agent


@app.get("/api/agents")
async def list_agents(
    user: TokenPayload = Depends(require_auth),
    detail: bool = True,
    limit: int = Query(200, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """The agents you may use (shared ones and your own; administrators see all) with
    their Nafs profile and settings; ``detail=false`` gives each in a few fields, and
    ``limit``/``offset`` page through them."""
    visible = [agent for agent in active_agents.values() if _agent_visible(user, agent)]
    default_id = await _default_agent_id(user.user_id)
    agents_data = []
    for agent in visible[offset : offset + limit]:
        if user.has_role("admin"):
            d = await _agent_view(user, agent, default_id=default_id)
            d["load"] = balancer.load_weights.get(agent.id, 0)
        else:
            private = await chat_agent_for(user, agent)
            d = await _agent_view(user, private, template=agent, default_id=default_id)
        agents_data.append(d if detail else _agent_summary(d))
    return {"agents": agents_data, "total": len(visible), "offset": offset}


@app.post("/api/agents")
async def create_new_agent(req: AgentCreate, user: TokenPayload | None = Depends(get_current_user)):
    """A new agent: an administrator's is shared with everyone unless ``shared`` is
    false; anyone else's is their own, seen and changed by them alone."""
    agent = await _build_agent(
        user,
        name=req.name,
        agent_type=req.type,
        provider=req.provider,
        model=req.model,
        system_prompt=req.system_prompt,
        settings=req.settings.model_dump(exclude_unset=True) if req.settings else None,
        capabilities=req.capabilities,
        shared=req.shared,
    )
    return await _agent_view(user, agent)


class DefaultAgent(BaseModel):
    agent_id: str | None = Field(None, max_length=100)


@app.get("/api/agents/default")
async def get_default_agent(user: TokenPayload = Depends(require_auth)) -> DefaultAgent:
    """Your default agent: it answers your chats that name none, your Telegram, email
    and WhatsApp messages and your watchers' tasks (None: Khalifah)."""
    return DefaultAgent(agent_id=await _default_agent_id(user.user_id))


@app.put("/api/agents/default")
async def set_default_agent(
    req: DefaultAgent, user: TokenPayload = Depends(require_auth)
) -> DefaultAgent:
    """Choose your default agent (one you may use); null goes back to Khalifah."""
    if req.agent_id is not None:
        _visible_agent(user, req.agent_id)
    await memory.set_preference(_default_agent_key(user.user_id), req.agent_id or "")
    return DefaultAgent(agent_id=await _default_agent_id(user.user_id))


class AgentImport(BaseModel):
    format: Literal["mizan-agent/1"]
    agent: AgentExportBody


@app.post("/api/agents/import")
async def import_agent(req: AgentImport, user: TokenPayload = Depends(require_auth)):
    """An agent exported with GET /api/agents/{id}/export, made again as yours. Its
    persona is read by Amanah first: one that tries to override MIZAN's rules, hide
    something from the user or send their data away is refused."""
    from tadbir import amanah

    body = req.agent
    findings = amanah.beyond_instructions(body.system_prompt or "", "agent import")
    if findings:
        raise HTTPException(
            422,
            {
                "message": "This agent's instructions try to override MIZAN's rules, hide "
                "something from you or send your data away, so it was not imported",
                "amanah": amanah.summary(findings),
            },
        )
    provider = body.provider
    if provider is not None and not _provider_startable(provider):
        provider = None  # this server has no key for it: the default provider instead
    agent = await _build_agent(
        user,
        name=body.name,
        agent_type=body.type,
        provider=provider,
        model=body.model if provider else None,
        system_prompt=body.system_prompt,
        settings=body.settings.model_dump(exclude_unset=True) if body.settings else None,
        shared=False,
    )
    return await _agent_view(user, agent)


def _provider_startable(provider: str) -> bool:
    status = get_provider_status()
    return any(
        item.get("name") == provider and item.get("configured") for item in status["providers"]
    )


@app.get("/api/agents/{agent_id}")
async def get_agent(agent_id: str, user: TokenPayload = Depends(require_auth)):
    """One agent you may use, with its settings and the tools its model is offered."""
    template = _visible_agent(user, agent_id)
    agent = await chat_agent_for(user, template)
    return await _agent_view(user, agent, template=template)


@app.post("/api/agents/{agent_id}/clone")
async def clone_agent(agent_id: str, user: TokenPayload = Depends(require_auth)):
    """A copy of an agent you may use, as your own ("<name> (copy)"). The persona is
    copied only when you may see it."""
    from agents import agent_settings

    template = _visible_agent(user, agent_id)
    override = template.config.get("provider_override") or {}
    provider = override.get("provider") or getattr(template.ai_client, "provider_name", None)
    if provider is not None and not _provider_startable(provider):
        provider = None  # its provider cannot start now: the default provider instead
    agent = await _build_agent(
        user,
        name=f"{template.name} (copy)"[:100],
        agent_type=_agent_type(template),
        provider=provider,
        model=(override.get("model") or template.ai_model) if provider else None,
        system_prompt=template.config.get("system_prompt")
        if _agent_editable(user, template)
        else None,
        settings=agent_settings.of(template.config),
        shared=False if not _agent_admin(user) else None,
    )
    return await _agent_view(user, agent)


def _agent_type(agent) -> str:
    """The AgentCreate type that builds this agent again."""
    role = str(getattr(agent, "role", "") or "general")
    return role if role in _AGENT_TYPES else "general"


_AGENT_TYPES = frozenset(
    {"super", "khalifah", "general", "browser", "research", "code", "communication", "wakil",
     "mubashir", "mundhir", "katib", "rasul"}
)  # fmt: skip


@app.get("/api/agents/{agent_id}/export")
async def export_agent(agent_id: str, user: TokenPayload = Depends(require_auth)):
    """The agent as ``mizan-agent/1`` JSON, for POST /api/agents/import here or on
    another server (no keys, no memory, no record). The persona is included only when
    you may see it."""
    from agents import agent_settings

    agent = _visible_agent(user, agent_id)
    override = agent.config.get("provider_override") or {}
    return {
        "format": AGENT_EXPORT_FORMAT,
        "agent": {
            "name": agent.name,
            "type": _agent_type(agent),
            "provider": override.get("provider") or getattr(agent.ai_client, "provider_name", None),
            "model": override.get("model") or agent.ai_model,
            "system_prompt": (agent.config.get("system_prompt") or "")
            if _agent_editable(user, agent)
            else "",
            "settings": agent_settings.of(agent.config),
        },
    }


@app.delete("/api/agents/{agent_id}")
async def delete_agent(agent_id: str, user: TokenPayload | None = Depends(get_current_user)):
    """Delete an agent you own (administrators: any); its saved profile goes too."""
    _editable_agent(user, agent_id)
    del active_agents[agent_id]
    balancer.agents.pop(agent_id, None)
    shura.members.pop(agent_id, None)
    # Its profile goes too, so it does not come back at the next start.
    await memory.delete_agent_profile(agent_id)
    for key in [key for key in _user_agents if key[1] == agent_id]:
        copy = _user_agents.pop(key)
        _user_teams.get(key[0], {}).pop(copy.id, None)
    wali.audit.log("agent_deleted", {"agent_id": agent_id})
    await event_bus.emit("agent.deleted", {"agent_id": agent_id})
    return {"deleted": agent_id}


@app.put("/api/agents/{agent_id}")
async def update_agent(
    agent_id: str,
    req: AgentUpdate,
    user: TokenPayload | None = Depends(get_current_user),
):
    """Change an agent's name, model, persona or settings (each setting merged on its
    own; null resets it). Its record (tasks, success, Nafs) is kept."""
    from agents import agent_settings

    agent = active_agents.get(agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")
    _editable_agent(user, agent_id)

    provider_obj = None
    if req.model is not None:
        provider_obj = create_provider(model=req.model)
        if provider_obj is None:
            raise HTTPException(400, "Requested model provider is unavailable")
    async with agent_settings_lock(agent):
        if req.name is not None:
            agent.name = req.name
        if req.system_prompt is not None:
            agent.config["system_prompt"] = req.system_prompt
        if req.settings is not None:
            _settings_allowed(user, req.settings.model_dump(exclude_unset=True))
            current = agent_settings.of(agent.config)
            agent_settings.apply(
                agent.config,
                agent_settings.merge(current, req.settings.model_dump(exclude_unset=True)),
            )
        if provider_obj is not None and req.model is not None:
            agent.ai_client = provider_obj
            agent.ai_model = normalize_model_for_provider(req.model, provider_obj.provider_name)
            agent.config["model"] = agent.ai_model
            agent.config["provider_override"] = {
                "provider": provider_obj.provider_name,
                "model": agent.ai_model,
            }
            agent.provider_warning = None
        agent._config_revision = getattr(agent, "_config_revision", 0) + 1

    await memory.save_agent_profile(_agent_profile(agent))

    if view := _broadcast_view(agent):  # someone's own agent is told to no one else
        await manager.broadcast({"type": "agent_updated", "agent": view})
    return await _agent_view(user, agent)


class AgentModelRequest(BaseModel):
    provider: str = Field(
        ...,
        pattern=AGENT_PROVIDER_PATTERN,
    )
    model: str = Field(..., min_length=1, max_length=200)


@app.post("/api/agents/{agent_id}/model")
async def set_agent_model(
    agent_id: str,
    req: AgentModelRequest,
    user: TokenPayload | None = Depends(get_current_user),
):
    """Set the model of an agent you own (administrators: any); others keep theirs."""
    agent = active_agents.get(agent_id)
    if not agent:
        raise HTTPException(404, f"Agent '{agent_id}' not found")
    _editable_agent(user, agent_id)

    provider = create_provider(provider=req.provider, model=req.model)
    if not provider:
        raise HTTPException(400, f"Cannot initialize provider '{req.provider}'. Check API key.")

    req.provider = getattr(provider, "provider_name", req.provider)
    req.model = normalize_model_for_provider(req.model, req.provider)
    async with agent_settings_lock(agent):
        agent.ai_client = provider
        agent.ai_model = req.model
        agent.config["model"] = req.model
        agent.config["provider_override"] = {"provider": req.provider, "model": req.model}
        agent.provider_warning = None
        agent._config_revision = getattr(agent, "_config_revision", 0) + 1
    await memory.save_agent_profile(_agent_profile(agent))

    await manager.broadcast(
        {
            "type": "agent_model_changed",
            "agent_id": agent_id,
            "provider": req.provider,
            "model": req.model,
        }
    )

    wali.audit.log("agent_model_changed", {"agent_id": agent_id, "model": req.model})
    return {"agent_id": agent_id, "provider": req.provider, "model": req.model}


# === TASKS ===


@app.post("/api/tasks")
async def run_task(
    req: TaskRequest,
    background_tasks: BackgroundTasks,
    user: TokenPayload | None = Depends(get_current_user),
):
    """Execute a task - single or parallel"""

    if req.parallel and not req.agent_id:
        task_id = str(uuid.uuid4())
        agent_ids = list(active_agents.keys())[:3]

        async def run_parallel():
            tasks = []
            for aid in agent_ids:
                agent = active_agents[aid]
                tasks.append(agent.execute(req.task, req.context))

            with await owner_consent(user.user_id if user else None):
                results = await asyncio.gather(*tasks, return_exceptions=True)

            await manager.broadcast(
                {
                    "type": "task_complete",
                    "task_id": task_id,
                    "parallel": True,
                    "results": [r if isinstance(r, dict) else {"error": str(r)} for r in results],
                }
            )

        background_tasks.add_task(run_parallel)
        return {"task_id": task_id, "mode": "parallel", "agents": agent_ids}

    agent_id = req.agent_id or balancer.select_agent()
    if not agent_id or agent_id not in active_agents:
        if not active_agents:
            raise HTTPException(503, "No agents available")
        agent_id = list(active_agents.keys())[0]

    agent = active_agents[agent_id]
    balancer.assign(agent_id)

    task_id = str(uuid.uuid4())

    async def run_single():
        try:

            async def stream_cb(chunk: str):
                await manager.broadcast(
                    {
                        "type": "task_stream",
                        "task_id": task_id,
                        "agent_id": agent_id,
                        "chunk": chunk,
                    }
                )

            with await owner_consent(user.user_id if user else None):
                result = await agent.execute(req.task, req.context, stream_callback=stream_cb)
            balancer.release(agent_id)

            await manager.broadcast(
                {
                    "type": "task_complete",
                    "task_id": task_id,
                    "agent_id": agent_id,
                    "result": result,
                }
            )
        except Exception as e:
            balancer.release(agent_id)
            await manager.broadcast(
                {
                    "type": "task_error",
                    "task_id": task_id,
                    "error": str(e),
                }
            )

    background_tasks.add_task(run_single)
    return {"task_id": task_id, "agent_id": agent_id, "status": "running"}


@app.get("/api/tasks/history")
async def get_task_history(agent_id: str | None = None, limit: int = 50):
    limit = min(limit, 200)
    history = await memory.get_task_history(agent_id, limit)
    return {"history": history}


_user_agents: dict[tuple[str, str], Any] = {}
_user_teams: dict[str, dict[str, Any]] = {}


def agent_settings_lock(agent):
    """Serialize settings with execution, so a running request retains its config."""
    if not hasattr(agent, "_execution_lock"):
        agent._execution_lock = asyncio.Lock()
    return agent._execution_lock


_private_memories: dict[str, DhikrMemorySystem] = {}


def _private_dir(user_id: str) -> Path:
    """Where this user's own memory and learning live."""
    import hashlib

    return (
        Path(os.getenv("MIZAN_DATA_DIR", "/data/mizan"))
        / "private"
        / hashlib.sha256(user_id.encode()).hexdigest()
    )


def _private_memory(user: TokenPayload) -> DhikrMemorySystem:
    """This user's own memory database, shared by all their agents."""
    directory = _private_dir(user.user_id)
    key = str(directory)
    if key not in _private_memories:
        directory.mkdir(parents=True, exist_ok=True)
        _private_memories[key] = DhikrMemorySystem(db_path=str(directory / "memory.db"))
    return _private_memories[key]


def _from_template(instance, template) -> None:
    """What a user's copy takes from its agent: who owns it, whether it is shared, its
    provider warning and its Nafs level (the record is the agent's own)."""
    instance.owner_id = getattr(template, "owner_id", None)
    instance.shared = bool(getattr(template, "shared", True))
    instance.provider_warning = getattr(template, "provider_warning", None)
    instance.nafs_level = max(instance.nafs_level, getattr(template, "nafs_level", 1) or 1)


def _private_agent(user: TokenPayload, template):
    """This user's own instance of an agent, with private memory and learning."""
    key = (user.user_id, template.id)
    if key not in _user_agents:
        private_memory = _private_memory(user)
        instance = create_agent(
            template.role,
            name=template.name,
            config=deepcopy(template.config),
            **_agent_services(
                memory=private_memory,
                knowledge_graph=private_memory.knowledge_graph,
                plugin_manager=None,  # plugins are the server's, not a user's team's
            ),
        )
        instance.ai_model, instance.ai_client = template.ai_model, template.ai_client
        instance._template_revision = getattr(template, "_config_revision", 0)
        instance._template_id = template.id
        _from_template(instance, template)
        _user_agents[key] = instance
    instance = _user_agents[key]
    # The user's agents form their own Majlis: each knows the others, so
    # MIZAN can give each part of a request to the agent that fits it.
    team = _user_teams.setdefault(user.user_id, {})
    team[instance.id] = instance
    _wire_agent(instance, team)
    return instance


async def chat_agent_for(user: TokenPayload, template):
    if not _agent_visible(user, template):
        # Someone else's own agent: this person is answered by the shared one.
        template = _tadbir_coordinator() or template
    if user.has_role("admin"):
        return template
    for other in active_agents.values():
        if _agent_visible(user, other):
            _private_agent(user, other)
    team = _user_teams.get(user.user_id, {})
    for member_id, member in list(team.items()):
        found = active_agents.get(getattr(member, "_template_id", None) or "")
        if found is None or not _agent_visible(user, found):
            team.pop(member_id, None)  # its agent was removed or is no longer theirs
    instance = _private_agent(user, template)
    if instance._template_revision != getattr(template, "_config_revision", 0):
        async with agent_settings_lock(instance):
            instance.name = template.name
            instance.config = deepcopy(template.config)
            instance.ai_model, instance.ai_client = template.ai_model, template.ai_client
            instance._template_revision = getattr(template, "_config_revision", 0)
            _from_template(instance, template)
    return instance


async def authorize_session(session_id: str, user: TokenPayload, *, create: bool = False):
    if not session_id or len(session_id) > 100:
        raise HTTPException(400, "Invalid session id")
    if not await memory.authorize_session(
        session_id, user.user_id, create=create, adopt_legacy=user.has_role("admin")
    ):
        raise HTTPException(404, "Session not found")


# === CHAT ===


def choose_agent_for_task(task: str) -> str:
    """Thompson-sample an agent by its learned success in this task's category.

    Each agent's Shukr record is a Beta posterior; sampling balances using
    proven agents with occasionally trying less-tested ones.
    """
    agents = list(active_agents.values())
    first = agents[0]
    try:
        category = first._classify_task(task)
        samples = {agent.id: agent.shukr.posterior(agent.id, category).sample() for agent in agents}
        return str(max(samples, key=lambda agent_id: samples[agent_id]))
    except Exception:
        return cast(str, first.id)


async def chat_history(session_id: str, session: dict, agent, task: str) -> list[dict]:
    """Model-sized history: running summary of old turns + recent turns that fit."""
    from providers import effective_limits
    from reasoning.context_engine import ContextEngine, agent_summarizer

    try:
        window, _ = effective_limits(
            getattr(agent, "ai_client", None), getattr(agent, "ai_model", "") or ""
        )
        reserve = agent._history_reserve(window) if hasattr(agent, "_history_reserve") else 0
        history: list[dict] = await ContextEngine(memory).history_for(
            session_id, window, agent_summarizer(agent), current=task, reserved_tokens=reserve
        )
        return history
    except Exception as exc:  # noqa: BLE001 - history assembly must never stop a chat
        logger.warning("Context engine unavailable; using recent turns: %s", exc)
        return list(session["history"][:-1][-50:])


# The learning and training choices (docs/consent.md).
CONSENT_KEYS = CONSENT_PREFERENCES


def consent_bindings(preferences: list[dict]) -> contextlib.ExitStack:
    """The user's own choices for this run (docs/consent.md): MIZAN learns from
    their work for them unless ``learning: off``; their words become training
    candidates only with ``training: on``."""
    from memory import stateless

    chosen = {str(item["key"]): str(item["value"]).strip().lower() for item in preferences}
    stack = contextlib.ExitStack()
    if chosen.get("learning") == "off":
        stack.enter_context(stateless.no_learning("learning: off"))
    if chosen.get("training") == "on":
        stack.enter_context(stateless.allow_training("training: on"))
    return stack


async def owner_consent(owner_id: str | None) -> contextlib.ExitStack:
    """:func:`consent_bindings` for a run done for ``owner_id`` (a watcher, a
    queued or scheduled task, the WebSocket chat). If their choices cannot be
    read, nothing is learned or captured: the safe reading of a choice unknown."""
    if not owner_id:
        return contextlib.ExitStack()
    try:
        return consent_bindings(await memory.get_chat_preferences(owner_id))
    except Exception:  # noqa: BLE001 - never fail a run over a preference read
        logger.warning("Preferences unavailable; this run learns and keeps nothing")
        return consent_bindings([{"key": "learning", "value": "off"}])


async def chat_context(
    user: TokenPayload,
    session_id: str,
    session: dict,
    agent,
    task: str,
    workspace_id: str | None = None,
):
    # Chat routes have already appended the current input for persistence.
    # Pass prior turns once; BaseAgent appends the current task itself.
    preferences = await memory.get_chat_preferences(user.user_id)
    from memory import stateless

    recall_off = stateless.active() or any(
        item["key"] == "cross_chat_recall" and str(item["value"]).strip().lower() == "off"
        for item in preferences
    )
    history = await chat_history(session_id, session, agent, task)
    # 'Azm: a new chat on a project (or with an agent) starts where the last one left
    # it; carried across chats like recall, so off with it (docs/azm.md).
    handoff = None
    from memory import azm

    # learning: off keeps nothing for the person, and so starts them from nothing kept.
    learning_off = not stateless.learns() or any(
        item["key"] == "learning" and str(item["value"]).strip().lower() == "off"
        for item in preferences
    )
    if not history and not recall_off and not learning_off and azm.kept_for(user.user_id):
        try:
            handoff = await asyncio.to_thread(
                azm.opening,
                user.user_id,
                chat_id=session_id,
                workspace_id=workspace_id
                or await memory.session_workspace(user.user_id, session_id),
                agent_id=str(
                    getattr(agent, "_template_id", None) or getattr(agent, "id", "") or ""
                ),
                task=task,
            )
        except Exception:  # noqa: BLE001 - a hand-off never stops a chat
            logger.warning("Hand-off unavailable for a new chat", exc_info=True)
    return {
        "session_id": session_id,
        **({"workspace_id": workspace_id} if workspace_id else {}),
        "history": history,
        # Your own words from other chats; shown under the answer when used,
        # and off when you set the preference cross_chat_recall: off.
        "conversation_memory": []
        if recall_off
        else await memory.recall_conversations(user.user_id, task, exclude_session=session_id),
        "user_preferences": preferences,
        **({"handoff": handoff} if handoff else {}),
    }


_stream_sessions: set[tuple[str, str]] = set()
_stream_runs: dict[tuple[str, str], ChatRunLease] = {}


@app.get("/api/chat/{session_id}/run-state")
async def chat_run_state(
    session_id: str,
    request_id: uuid.UUID | None = None,
    user: TokenPayload = Depends(require_auth),
):
    if not session_id or len(session_id) > 100:
        raise HTTPException(400, "Invalid session id")
    owner = await memory.session_owner(session_id)
    if owner is None:
        # A browser can save its UUID before the first POST reaches us. This
        # read must neither create nor adopt a session simply to recover it.
        return {"state": "idle", "request": None, "history_saved": None}
    await authorize_session(session_id, user)
    lease = _stream_runs.get((user.user_id, session_id))
    if lease is not None and not lease.finished:
        # This is session availability: live work takes precedence over a
        # requested older/missing receipt. Return its explicit server identity.
        return {"state": "active", "request": lease.public(), "history_saved": lease.history_saved}
    ledger = ChatStreamLedger(memory._get_conn, memory._release_conn)
    return ledger.run_state(user.user_id, session_id, str(request_id) if request_id else None)


class StopChatRequest(BaseModel):
    request_id: uuid.UUID | None = None


@app.post("/api/chat/{session_id}/stop")
async def stop_chat(
    session_id: str, req: StopChatRequest | None = None, user: TokenPayload = Depends(require_auth)
):
    """Stop the user's active run in this chat (the Stop button). A dropped
    connection never does this: the run goes on and saves its answer."""
    if not session_id or len(session_id) > 100:
        raise HTTPException(400, "Invalid session id")
    if await memory.session_owner(session_id) is None:
        return {"stopped": False}
    await authorize_session(session_id, user)
    lease = _stream_runs.get((user.user_id, session_id))
    if (
        lease is None
        or lease.producer is None
        or lease.producer.done()
        or (
            req is not None
            and req.request_id is not None
            and str(req.request_id) != lease.request_id
        )
    ):
        return {"stopped": False}
    lease.stop_requested = True
    lease.producer.cancel()
    return {"stopped": True, "request_id": lease.request_id}


@app.delete("/api/chat/{session_id}")
async def delete_chat(session_id: str, user: TokenPayload = Depends(require_auth)):
    """Delete a chat and everything MIZAN derived from it (Mahw). The answer is
    a receipt: what was removed from each store, how many checks ran over what
    is left, and how many traces were found (none, when it worked)."""
    from api import artifacts as artifact_store
    from memory import mahw
    from security.approvals import held_store

    await authorize_session(session_id, user)
    key = (user.user_id, session_id)
    lease = _stream_runs.get(key)
    if key in _stream_sessions or (
        lease is not None and lease.producer is not None and not lease.producer.done()
    ):
        raise HTTPException(409, "This chat is still answering; stop it first")
    receipt = await mahw.erase_chat(
        chat_db=memory.db_path,
        artifacts_db=artifact_store._db_path(),
        private=await _own_memory(user),
        owner=user.user_id,
        session_id=session_id,
        held_db=held_store().path,
    )
    active_sessions.pop(session_id, None)
    _stream_runs.pop(key, None)
    from security import sakk

    sakk.record(
        user.user_id,
        "erase",
        {
            "chat": sakk.store().mac(user.user_id, session_id),
            "removed": sum(int(v) for v in (receipt.get("removed") or {}).values()),
            "traces": int(receipt.get("traces") or 0),
        },
        "chat erased (Mahw)",
    )
    return receipt


class ChatUpdate(BaseModel):
    """Name a chat (``title``), bind it to one of the user's projects (``workspace_id``)
    or unbind it (``workspace_id: null``): at least one of the two."""

    title: str | None = Field(
        None, description="The chat's name: 1-120 characters after trimming, one line."
    )
    workspace_id: str | None = Field(
        None,
        min_length=1,
        max_length=100,
        description="The project this chat works on; null unbinds it.",
    )

    @field_validator("title")
    @classmethod
    def _one_line_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        title = value.strip()
        if not title:
            raise ValueError("A chat title cannot be empty")
        if len(title) > 120:
            raise ValueError("A chat title has at most 120 characters")
        # Control characters (newlines, tabs, NUL, DEL, C1) and lone surrogates.
        if any(unicodedata.category(char) in ("Cc", "Cs") for char in title):
            raise ValueError("A chat title cannot contain control characters")
        return title

    @model_validator(mode="after")
    def _something_to_change(self) -> "ChatUpdate":
        sent = self.model_fields_set & {"title", "workspace_id"}
        if not sent:
            raise ValueError("Send a title, a workspace_id, or both")
        if "title" in sent and self.title is None:
            raise ValueError("A chat title cannot be empty")
        return self


@app.patch("/api/chat/{session_id}")
async def update_chat(session_id: str, req: ChatUpdate, user: TokenPayload = Depends(require_auth)):
    """Name one of the user's chats (the chat list shows the title and searches it),
    or bind it to one of their projects so its messages work on that project."""
    await authorize_session(session_id, user)
    answer: dict[str, Any] = {"session_id": session_id}
    if "workspace_id" in req.model_fields_set:
        if req.workspace_id:
            from workspace.context import authorize_owned_workspace

            authorize_owned_workspace(req.workspace_id, user.user_id)
        if not await memory.bind_session_workspace(user.user_id, session_id, req.workspace_id):
            raise HTTPException(404, "Session not found")  # erased meanwhile
        answer["workspace_id"] = req.workspace_id
    if "title" in req.model_fields_set:
        if not await memory.rename_session(user.user_id, session_id, req.title):
            raise HTTPException(404, "Session not found")
        answer["title"] = req.title
    return answer


def chat_completion_receipt(result: dict) -> dict:
    """Carry observed completion state through storage and all chat transports."""
    return {
        key: result[key]
        for key in ("completion_status", "answer_delivered", "task_verified", "learning_capture")
        if key in result
    }


def chat_failure_payload(result: dict) -> dict:
    """Expose only fixed public errors, retaining the execution's final receipt."""
    public_errors = {
        "output_budget_exhausted": "The model reached its output limit before producing an answer. Try a smaller request or another model.",
        "provider_timeout": "The response model exceeded its wait limit. No automatic retry was made; upstream completion is unconfirmed.",
        "chat_run_timeout": "This chat reached its run time limit. No automatic retry was made; check saved history before sending more work.",
        "model_refused": "The model declined this request. Rephrase it or choose another model.",
        "provider_unavailable": "The model provider returned an error and stayed unavailable after automatic retries and fallback models. Try again in a moment or choose another model.",
        "provider_rate_limited": "The selected model is rate-limited by its provider right now (free models are often busy). Try again in a minute, or choose another model.",
        "provider_credit": "The model provider's account has run out of credit (HTTP 402), so it refused the request before answering. An administrator needs to add credit at the provider; until then only short answers may get through.",
        "own_model_not_ready": "MIZAN's own model (Ruh) is selected as the language model, but it cannot answer in words yet: it returned no text. An administrator can choose a hosted model again in Settings → Providers. MIZAN's own recipes (Quran, hadith, calculations, code, and answers it learned) still work.",
        "empty_answer": "The model finished without writing an answer. Try again, or choose another model.",
    }
    code = result.get("error_code")
    if code == "provider_unavailable" and result.get("provider_status") == 429:
        code = "provider_rate_limited"
    budget = result.get("budget") if code == "budget_exhausted" else None
    if isinstance(budget, dict):
        public_errors["budget_exhausted"] = _budget_message(budget)
    if not isinstance(code, str) or code not in public_errors:
        code = "agent_failed"
    message = public_errors.get(
        code, "The agent could not complete this request. Any partial output was saved."
    )
    status = result.get("completion_status")
    receipt = {
        "completion_status": "incomplete"
        if code in public_errors or status == "incomplete"
        else "failed",
        "answer_delivered": False,
        "task_verified": False,
    }
    usage = result.get("usage")
    return {
        "code": code,
        "message": message,
        "usage": {**(usage if isinstance(usage, dict) else {}), **receipt},
        **({"budget": budget} if isinstance(budget, dict) else {}),
        **receipt,
    }


def _budget_message(budget: dict) -> str:
    """The spending-limit message, built only from numbers and fixed words."""
    if budget.get("reason") == "unpriced":
        return (
            "This model has no known price, so MIZAN cannot keep it inside your spending "
            "limit. Choose a priced model, or ask an administrator to add its price."
        )
    if budget.get("reason") == "unavailable":
        return "MIZAN cannot read its spending ledger right now, so no paid model call may run."
    word = "daily" if budget.get("period") == "day" else "monthly"
    limit = budget.get("limit_usd")
    amount = f" of ${float(limit):.2f}" if isinstance(limit, (int, float)) else ""
    renews = str(budget.get("resets_at") or "")[:25]
    return (
        f"Your {word} model budget{amount} is used up, so MIZAN did not send this to the "
        f"model. It renews at {renews}. MIZAN's own tools (Quran, hadith, calculations, "
        "dates) still work without the model."
    )


def chat_provider_attempts(agent) -> dict:
    """Copy only measured attempt timings, never exception text or guessed usage."""
    timings = getattr(agent, "_execution_timings", None)
    raw = timings.get("provider_attempts") if isinstance(timings, dict) else None
    if not isinstance(raw, list):
        return {}
    attempts = []
    provider_ms = 0.0
    for attempt in raw[:64]:
        if not isinstance(attempt, dict):
            continue
        mode, outcome, elapsed = (
            attempt.get("mode"),
            attempt.get("outcome"),
            attempt.get("latency_ms"),
        )
        if (
            not isinstance(mode, str)
            or mode not in {"stream", "create"}
            or not isinstance(outcome, str)
            or outcome not in {"completed", "failed", "cancelled", "timed_out"}
            or not isinstance(elapsed, (int, float))
            or isinstance(elapsed, bool)
            or not 0 <= elapsed <= 86_400_000
        ):
            continue
        attempts.append({"mode": mode, "outcome": outcome, "latency_ms": elapsed})
        provider_ms += elapsed
    if not attempts:
        return {}
    return {
        "provider_attempts": attempts,
        "provider_attempt_count": len(attempts),
        "provider_ms": round(provider_ms, 1),
    }


def _prepare_images(owner: str, images: list[ImageIn]) -> list[Any]:
    """Each attached image checked, re-encoded without its metadata, and kept
    for its owner (Basar); a file that is not a readable image is refused."""
    prepared = []
    for item in images:
        try:
            image = basar.prepare(basar.decode(item.data))
        except basar.ImageError as exc:
            raise HTTPException(400, str(exc)) from exc
        basar.store(owner, image)
        prepared.append(image)
    return prepared


async def _earlier_images(owner: str, session_id: str) -> list[Any]:
    """The images of the user's previous message in this chat, if it had any."""
    try:
        recent = await memory.get_messages(session_id, limit=6)
    except Exception:  # noqa: BLE001 - no history: nothing to show
        return []
    for message in reversed(recent):
        if message.get("role") != "user":
            continue
        metadata = message.get("metadata") or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except ValueError:
                metadata = {}
        shas = [str(item.get("sha", "")) for item in metadata.get("images") or []]
        return [image for sha in shas if (image := basar.load(owner, sha)) is not None]
    return []


@app.get("/api/media/{sha}")
async def get_media(sha: str, user: TokenPayload = Depends(require_auth)):
    """One of your own images from a chat (Basar); never another user's."""
    image = basar.load(user.user_id, sha)
    if image is None:
        raise HTTPException(404, "Image not found")
    return Response(
        content=image.data,
        media_type=image.media_type,
        headers={"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"},
    )


async def _turn_checkpoint(
    channel: Any, owner_id: str, workspace_id: str, session_id: str, request_id: str
) -> dict | None:
    """Save the project as it is before this message (one read of the project; nothing
    is written when it is unchanged since the last checkpoint) and announce it. A failure
    is reported and the turn goes on. The checkpoint names its chat and request, never
    the message's words, so erasing the chat (Mahw) leaves none of them behind."""
    from workspace.store import WorkspaceStore

    try:
        saved = await asyncio.to_thread(
            WorkspaceStore(owner_id).checkpoint,
            workspace_id,
            "Before a chat message",
            kind="turn",
            origin={"session_id": session_id, "request_id": request_id},
        )
    except HTTPException as exc:
        await channel.emit("checkpoint", workspace_id=workspace_id, error=str(exc.detail)[:300])
        return None
    except Exception:
        logger.exception("Turn checkpoint failed for project %s", workspace_id)
        await channel.emit(
            "checkpoint", workspace_id=workspace_id, error="The project could not be saved"
        )
        return None
    await channel.emit(
        "checkpoint",
        workspace_id=workspace_id,
        checkpoint_id=saved["id"],
        checkpoint_kind="turn",
        reused=saved["reused"],
        created_at=saved["created_at"],
    )
    return {"workspace_id": workspace_id, "id": saved["id"]}


@app.post("/api/chat/stream", response_class=StreamingResponse)
async def stream_chat(
    req: StreamChatMessage,
    user: TokenPayload = Depends(require_auth),
):
    """One authenticated POST produces one SSE stream; it is never replayed.

    The run belongs to the server, not to the connection: if the reader
    disconnects or stalls, the run still finishes and saves its answer, and
    ``/api/chat/{session_id}/run-state`` reports it active until then. Only
    ``POST /api/chat/{session_id}/stop`` cancels it. Clients must not
    automatically retry with a fresh request UUID after an uncertain network
    outcome; read owned chat history instead.
    """
    request_started = asyncio.get_running_loop().time()
    if not _chat_messages.check(f"user:{user.user_id}"):
        raise HTTPException(
            429,
            "Too many messages; wait a moment",
            headers=_rate_headers(_chat_messages, f"user:{user.user_id}"),
        )
    await authorize_session(req.session_id, user, create=True)
    # The project this message works on: the one sent, else the one the chat is bound to.
    stored_workspace = await memory.session_workspace(user.user_id, req.session_id)
    workspace_id = req.workspace_id or stored_workspace
    workspace_context: Any = None
    if workspace_id:
        try:
            from workspace import context as selected_workspace_context
        except ImportError as exc:
            raise HTTPException(503, "Coding workspaces are not available") from exc
        workspace_context = selected_workspace_context
        try:
            workspace_context.authorize_owned_workspace(workspace_id, user.user_id)
        except HTTPException:
            if req.workspace_id:
                raise
            # The chat's project was deleted: the chat goes on without one.
            await memory.bind_session_workspace(user.user_id, req.session_id, None)
            workspace_id, workspace_context = None, None
    agent_id = (
        req.agent_id or await _default_agent_id(user.user_id) or next(iter(active_agents), None)
    )
    if agent_id not in active_agents and not req.content.startswith("/"):
        raise HTTPException(503, "No agents available")
    agent = (
        await chat_agent_for(user, active_agents[agent_id]) if agent_id in active_agents else None
    )
    # Decoding and re-encoding is CPU work; keep it off the event loop.
    attached = await asyncio.to_thread(_prepare_images, user.user_id, req.images)
    request_id, message_id = str(req.request_id), str(uuid.uuid4())
    ledger = ChatStreamLedger(memory._get_conn, memory._release_conn)
    previous = ledger.claim(
        user.user_id,
        request_id,
        req.session_id,
        message_id,
        # The receipt keeps which images were sent, never the images themselves.
        {
            **req.model_dump(mode="json", exclude={"images"}),
            "images": [image.sha for image in attached],
        },
    )
    if previous:
        raise HTTPException(
            409,
            {
                "code": "request_already_submitted",
                "message": "Read session history; this request will not run again",
                **previous,
            },
        )
    stream_key = (user.user_id, req.session_id)
    previous_lease = _stream_runs.get(stream_key)
    if previous_lease is not None and previous_lease.finished:
        _stream_runs.pop(stream_key, None)
        _stream_sessions.discard(stream_key)
    if stream_key in _stream_sessions:
        ledger.update(user.user_id, request_id, "rejected")
        raise HTTPException(
            409,
            {
                "code": "chat_stream_active",
                "message": "A chat stream is still active for this session.",
                "request_id": request_id,
                "session_id": req.session_id,
                "active_request": previous_lease.public() if previous_lease else None,
            },
        )
    if len(_stream_sessions) >= security_config.ws_max_connections:
        ledger.update(user.user_id, request_id, "rejected")
        raise HTTPException(
            429,
            {
                "code": "chat_capacity_reached",
                "message": "Chat capacity is currently full.",
                "request_id": request_id,
            },
        )
    _stream_sessions.add(stream_key)
    lease = ChatRunLease(req.session_id, request_id, message_id)
    _stream_runs[stream_key] = lease

    def release_finished_run(_task=None):
        # A closed socket does not prove producer cancellation finished, and a
        # completed producer does not prove all terminal frames were delivered.
        if lease.finished and _stream_runs.get(stream_key) is lease:
            _stream_runs.pop(stream_key, None)
            _stream_sessions.discard(stream_key)

    def transport_finished():
        lease.transport_finished = True
        if lease.producer is None:
            # No body iteration means no provider or tool invocation started.
            try:
                ledger.update(user.user_id, request_id, "rejected")
            except Exception:
                logger.warning("Unstarted chat receipt update unavailable")
        release_finished_run()

    if req.fix and not workspace_id:
        raise HTTPException(422, "Fix with MIZAN needs the chat's project")
    if req.workspace_id and req.workspace_id != stored_workspace:
        # Sending with a project binds the chat to it, so later messages keep it.
        await memory.bind_session_workspace(user.user_id, req.session_id, req.workspace_id)
    channel = ChatEventChannel(
        session_id=req.session_id, message_id=message_id, request_id=request_id
    )
    cancellation_reason = "task_cancelled"

    async def process_stream():
        nonlocal cancellation_reason
        from api.usage import build_usage_summary

        binding = bind_principal(user)
        workspace_binding = (
            workspace_context.bind_workspace(workspace_id) if workspace_context else None
        )
        # Delete and restore wait while this run works in the project.
        busy = contextlib.ExitStack()
        from api import iqtisad

        # Every paid call of this run is recorded under its request.
        busy.enter_context(iqtisad.bind_request(request_id))
        # The user's learning and training choices (docs/consent.md).
        busy.enter_context(await owner_consent(user.user_id))
        if workspace_context:
            busy.enter_context(workspace_context.running_in(user.user_id, workspace_id))
        turn_checkpoint: dict | None = None
        session: dict | None = None
        response_parts: list[str] = []
        response_characters = 0
        execution_started = False
        persisted = False
        persistence_failed = False
        result: dict | None = None
        execution_stage = "context_preparation"
        lease.update(phase=execution_stage)
        terminal_status = "error"
        trace = thinking_stream.create_trace(message_id)
        artifact_ids: list[str] = []  # delivered, in order; kept on the message

        async def deliver(kind: str, **data):
            nonlocal cancellation_reason, execution_stage
            previous_stage = execution_stage
            execution_stage = "delivery"
            try:
                await channel.emit(kind, **data)
            except StreamDeliveryError as exc:
                # Delivery failures must stop the execution rather than trigger
                # an agent recovery call or subsequent tools.
                cancellation_reason = "delivery_failed"
                raise asyncio.CancelledError("Chat delivery stopped") from exc
            else:
                execution_stage = previous_stage

        async def saved_artifact(reference: Any):
            # Agent/tool output is not an authorization source. Resolve only
            # artifacts actually stored for this principal and this session.
            from api.artifacts import get_artifact

            artifact_id = reference.get("id") if isinstance(reference, dict) else None
            if not isinstance(artifact_id, str) or artifact_id in artifact_ids:
                return
            artifact = get_artifact(user_id=user.user_id, artifact_id=artifact_id)
            if not artifact or artifact["session_id"] != req.session_id:
                return
            artifact_ids.append(artifact_id)
            # Large content is read from the owner-protected artifact endpoint.
            await deliver(
                "artifact", artifact={k: v for k, v in artifact.items() if k != "content"}
            )

        def published_artifacts():
            # This request's own run of the agent: the base agent may still hold
            # another run's tool results.
            from agents.base import run_of

            for receipt in getattr(run_of(agent), "_last_tool_results", []) or []:
                tool_result = receipt.get("result")
                if receipt.get("name") == "workspace_artifact" and isinstance(tool_result, dict):
                    yield tool_result.get("artifact", tool_result)

        async def stream_cb(chunk: str, **kwargs):
            nonlocal response_characters, execution_started, cancellation_reason, execution_stage
            execution_started = True
            execution_stage = "agent_execution"
            lease.provider_attempt_count = None
            lease.update(phase="agent_execution")
            kind = kwargs.get("chunk_type", "text")
            if kind == "tool_use":
                await deliver("tool_use", tool_name=kwargs.get("tool_name", "unknown"))
                # A successfully saved artifact survives a later model failure.
                for reference in published_artifacts():
                    await saved_artifact(reference)
                return
            if kind == "artifact":
                await saved_artifact(kwargs.get("artifact"))
                return
            response_characters += len(chunk)
            if response_characters > MAX_RESPONSE_CHARACTERS:
                cancellation_reason = "response_limit_exceeded"
                execution_stage = "delivery"
                raise asyncio.CancelledError("Chat response exceeds the output limit")
            response_parts.append(chunk)
            for start in range(0, len(chunk), TEXT_CHUNK_CHARACTERS):
                await deliver("chat_stream", chunk=chunk[start : start + TEXT_CHUNK_CHARACTERS])

        async def thinking_cb(phase: str, content: str, confidence: float, metadata: dict):
            nonlocal execution_started, execution_stage
            execution_started = True
            execution_stage = "agent_execution"
            lease.provider_attempt_count = None
            lease.update(phase="agent_execution")
            thinking_stream.add_step(
                trace.request_id, ThinkingPhase(phase), content, confidence, metadata
            )
            if req.thinking:
                await deliver(
                    "thinking",
                    phase=phase,
                    content=content,
                    confidence=confidence,
                    metadata=metadata,
                )

        async def save_assistant(content: str, metadata: dict):
            nonlocal persistence_failed
            try:
                await memory.save_message(
                    req.session_id, "assistant", content, agent_id, metadata=metadata
                )
                lease.history_saved = True
            except Exception:
                lease.history_saved = False
                persistence_failed = True
                raise

        def interruption_receipt() -> dict:
            return {
                "cancellation_reason": cancellation_reason,
                "execution_stage": execution_stage,
                "request_elapsed_ms": round(
                    (asyncio.get_running_loop().time() - request_started) * 1000, 1
                ),
            }

        async def persist_partial(status: str, final_result: dict | None = None):
            nonlocal persisted
            if persisted or session is None:
                return
            from agents.base import run_of

            ran = run_of(agent)  # this request's own run of the agent
            usage = (
                build_usage_summary(getattr(ran, "_llm_calls", []) or [])
                if agent and execution_started
                else {}
            )
            if execution_started and (attempts := chat_provider_attempts(ran)):
                usage["timings"] = attempts
                lease.provider_attempt_count = attempts["provider_attempt_count"]
            receipt = (
                chat_failure_payload({"usage": usage, **final_result})
                if final_result is not None
                else {
                    "completion_status": "incomplete",
                    "answer_delivered": False,
                    "task_verified": False,
                }
            )
            partial = "".join(response_parts)
            await save_assistant(
                partial,
                {
                    "message_id": message_id,
                    "request_id": request_id,
                    "status": status,
                    "partial": True,
                    "usage": usage,
                    "usage_incomplete": final_result is None,
                    **receipt,
                    **(interruption_receipt() if status == "cancelled" else {}),
                },
            )
            if partial.strip():
                # An empty reply is stored with its receipt but never replayed as a turn.
                session["history"].append({"role": "assistant", "content": partial})
            persisted = True

        try:
            selected_model = req.model_override or (agent.ai_model if agent else None)
            await channel.emit(
                "status",
                status="accepted",
                phase="context_preparation",
                elapsed_ms=lease.public()["elapsed_ms"],
                streaming_mode="buffered" if str(selected_model).startswith("ruh") else "provider",
                input_modalities=["text"],
            )
            session = active_sessions.get(req.session_id)
            if session is None:
                stored = await memory.get_messages(req.session_id, limit=50)
                session = {
                    "history": [{"role": m["role"], "content": m["content"]} for m in stored]
                }
                active_sessions[req.session_id] = session
            # Images shown with this turn: the ones attached now, or with no new
            # ones, those of the message just before it ("is image ka HTML banao").
            seen = attached or await _earlier_images(user.user_id, req.session_id)
            if workspace_id:
                turn_checkpoint = await _turn_checkpoint(
                    channel, user.user_id, workspace_id, req.session_id, request_id
                )
            user_message_id = await memory.save_message(
                req.session_id,
                "user",
                req.content,
                agent_id,
                metadata={
                    "request_id": request_id,
                    # "Rewind code to before this message" restores this checkpoint.
                    **({"checkpoint": turn_checkpoint} if turn_checkpoint else {}),
                    **({"images": [image.meta() for image in attached]} if attached else {}),
                    # Never recalled in the user's other chats (Dhikr.recall_conversations).
                    **({"stateless": True} if req.stateless else {}),
                },
            )
            session["history"].append({"role": "user", "content": req.content})
            ledger.update(user.user_id, request_id, "running")
            lease.update(status="running", phase="context_preparation")
            await channel.emit(
                "status",
                status="running",
                phase="context_preparation",
                elapsed_ms=lease.public()["elapsed_ms"],
            )
            # "/skill-name request" activates one of the user's Agent Skills
            # for this chat instead of being treated as a built-in command.
            task_content = req.content
            skill_command = None
            if agent is not None and req.content.startswith("/"):
                from agent_skills.tools import resolve_slash_skill

                skill_command = resolve_slash_skill(req.content, user.user_id, workspace_id)
            if skill_command:
                from agent_skills.tools import activate
                from workspace.context import bind_chat_session, reset_chat_session

                skill_name, rest = skill_command
                session_token = bind_chat_session(req.session_id)
                try:
                    activate(skill_name)
                finally:
                    reset_chat_session(session_token)
                task_content = rest or f"Use the {skill_name} skill for this chat."
                cmd_result = {"is_command": False}
            else:
                cmd_result = await handle_command(
                    req.content,
                    agent=agent,
                    session_id=req.session_id,
                    sessions=active_sessions,
                    memory=memory,
                    active_agents=_visible_agents(user),
                )
            if cmd_result.get("is_command"):
                result = {"success": True, "result": cmd_result["response"], "usage": {}}
            else:
                await channel.emit("typing", agent=agent.name)
                from agents.provider_limits import chat_run_seconds

                async def phase_cb(phase: str):
                    nonlocal execution_stage, execution_started
                    execution_stage = phase
                    if phase == "agent_execution":
                        execution_started = True
                        lease.provider_attempt_count = None
                    lease.update(phase=phase)
                    await channel.emit(
                        "status",
                        status="running",
                        phase=phase,
                        elapsed_ms=lease.public()["elapsed_ms"],
                    )

                from agents.events import bind_event_sink
                from security.approvals import bind_approvals
                from security.approvals import chat_context as approvals_for_chat
                from tadbir.waqt import bind_timezone

                async def activity_sink(kind: str, payload: dict):
                    # Structured tool/todo/approval frames for this run only.
                    await deliver(kind, **payload)

                # A person reads this chat: they are asked, and what they allowed
                # "always" in it earlier still holds.
                # A chat that sends no mode gets its agent's own, else the server's
                # default (MIZAN_DEFAULT_PERMISSION_MODE, auto).
                approval_context = approvals_for_chat(
                    user.user_id, req.session_id, req.permission_mode or _permission_mode(agent)
                )
                if approval_context is not None and (req.plan_approved or req.fix):
                    # What the person pressed, for Tadbir to act on (never their words).
                    approval_context.button = (
                        {"plan_approved": True}
                        if req.plan_approved
                        else {"fix": req.fix.model_dump() if req.fix else {}}
                    )
                run_deadline = asyncio.timeout(chat_run_seconds())
                try:
                    async with run_deadline:
                        from memory import stateless

                        with stateless.bind(req.stateless):
                            context = await chat_context(
                                user, req.session_id, session, agent, req.content, workspace_id
                            )
                        # The person's message this run answers ('Azm's decisions name it).
                        context["message_id"] = user_message_id
                        await phase_cb("queued")
                        with (
                            stateless.bind(req.stateless),
                            bind_event_sink(activity_sink),
                            bind_approvals(approval_context),
                            bind_timezone(req.timezone),
                            basar.bind(seen),
                        ):
                            result = await agent.execute(
                                task_content,
                                context,
                                stream_callback=stream_cb,
                                thinking_callback=thinking_cb,
                                model_override=req.model_override,
                                phase_callback=phase_cb,
                            )
                except TimeoutError:
                    if not run_deadline.expired():
                        raise
                    from agents.base import run_of

                    ran = run_of(agent)  # this request's own run of the agent
                    usage = (
                        build_usage_summary(getattr(ran, "_llm_calls", []) or [])
                        if execution_started
                        else {}
                    )
                    if execution_started and (attempts := chat_provider_attempts(ran)):
                        usage["timings"] = attempts
                    result = {"success": False, "error_code": "chat_run_timeout", "usage": usage}
            observed_count = (
                result.get("usage", {}).get("timings", {}).get("provider_attempt_count")
            )
            if isinstance(observed_count, int) and observed_count >= 0:
                lease.provider_attempt_count = observed_count
            execution_stage = "delivery"
            lease.update(phase="delivery")
            final = result.get("result", "".join(response_parts))
            if isinstance(final, dict):
                final = final.get("response", str(final))
            final = str(final)
            if len(final) > MAX_RESPONSE_CHARACTERS:
                raise StreamDeliveryError("Chat response exceeds the output limit")
            if not result.get("success", True):
                await persist_partial("error", result)
                await channel.emit("error", **chat_failure_payload(result))
                return
            # Artifacts first, so the saved message keeps their ids for a reload.
            for reference in result.get("artifacts", []) or []:
                await saved_artifact(reference)
            if execution_started:
                for reference in published_artifacts():
                    await saved_artifact(reference)
            # Save before the terminal event: a disconnected browser can read
            # the final response and exact observed usage without resubmitting.
            # Pictures MIZAN made for the answer (a browser screenshot), by kept id.
            made = [
                {"sha": str(item["sha"]), "media_type": str(item.get("media_type", "image/png"))}
                for item in result.get("images") or []
                if isinstance(item, dict) and item.get("sha")
            ][:4]
            await save_assistant(
                final,
                {
                    "message_id": message_id,
                    "request_id": request_id,
                    "status": "complete",
                    "usage": result.get("usage", {}),
                    **chat_completion_receipt(result),
                    **({"images": made} if made else {}),
                    **({"artifacts": artifact_ids} if artifact_ids else {}),
                },
            )
            session["history"].append({"role": "assistant", "content": final})
            persisted, terminal_status = True, "complete"
            # A project MIZAN made in a chat without one becomes the chat's project, so
            # the next message ("add dark mode") works on it.
            chat_workspace = workspace_id
            made_workspace = result.get("workspace_id")
            if not workspace_id and isinstance(made_workspace, str) and made_workspace:
                await memory.bind_session_workspace(user.user_id, req.session_id, made_workspace)
                chat_workspace = made_workspace
            thinking_stream.complete(message_id)
            completed_trace = thinking_stream.get_trace(message_id)
            # Qwen3 = generation → attach the QG understanding layer
            # (root/pattern/role) to every response. Best-effort: a failure
            # here must never break the chat stream.
            understanding_kw: dict = {}
            if getattr(getattr(agent, "ai_client", None), "provider_name", "") == "qwen3":
                try:
                    from api.qwen3_understanding import analyze_understanding

                    understanding_kw = {"understanding": analyze_understanding(final)}
                except Exception as exc:  # noqa: BLE001
                    logger.warning("qwen3 understanding layer failed: %s", exc)
            await channel.emit(
                "chat_complete",
                **understanding_kw,
                response=final,
                images=made,
                artifacts=artifact_ids,
                usage=result.get("usage", {}),
                **chat_completion_receipt(result),
                agent=agent.name if agent else None,
                success=True,
                workspace_id=chat_workspace,
                checkpoint=turn_checkpoint,
                **(
                    {
                        "cognitive": {
                            k: result[k]
                            for k in (
                                "nafs_level",
                                "nafs_name",
                                "ruh_energy",
                                "qalb",
                                "yaqin",
                                "mizan_label",
                                "cognitive_method",
                                "lubb",
                                "lawwama",
                                "metrics_kind",
                                "metric_provenance",
                            )
                            if result.get(k) is not None
                        },
                        "thinking_trace": completed_trace.to_dict() if completed_trace else None,
                    }
                    if req.thinking
                    else {}
                ),
            )
        except asyncio.CancelledError:
            if lease.stop_requested:
                cancellation_reason = "user_stopped"
            if terminal_status != "complete":
                terminal_status = "cancelled"
                try:
                    await persist_partial("cancelled")
                except Exception:
                    logger.warning("Cancelled chat persistence unavailable for %s", message_id)
                logger.info(
                    "Chat interrupted message=%s diagnostics=%s", message_id, interruption_receipt()
                )
            if not channel.closed:
                try:
                    await channel.emit(
                        "error",
                        code="delivery_stopped",
                        message="Chat delivery was interrupted",
                        **interruption_receipt(),
                        completion_status="incomplete",
                        answer_delivered=False,
                        task_verified=False,
                    )
                except StreamDeliveryError:
                    logger.warning("Cancelled chat reader unavailable for message %s", message_id)
            raise
        except Exception:
            logger.exception("Chat stream failed for message %s", message_id)
            if terminal_status != "complete" and not persistence_failed:
                try:
                    await persist_partial("error")
                except Exception:
                    logger.warning("Chat persistence unavailable for %s", message_id)
            if not channel.closed:
                try:
                    if persistence_failed:
                        await channel.emit(
                            "error",
                            **{
                                **chat_failure_payload(result or {}),
                                "code": "history_save_failed",
                                "message": "Chat delivery failed and the reply could not be saved.",
                                "history_saved": False,
                            },
                        )
                    else:
                        await channel.emit(
                            "error",
                            code="stream_failed",
                            message="The chat stream could not complete",
                        )
                except StreamDeliveryError:
                    logger.warning("Chat reader unavailable for message %s", message_id)
        finally:
            lease.update(status=terminal_status)
            try:
                ledger.update(user.user_id, request_id, terminal_status)
                thinking_stream.complete(message_id)
            finally:
                busy.close()
                if workspace_context and workspace_binding is not None:
                    workspace_context.reset_workspace(workspace_binding)
                reset_principal(binding)

    async def event_frames():
        producer = asyncio.create_task(process_stream(), name=f"chat-stream-{message_id}")
        lease.producer = producer
        producer.add_done_callback(release_finished_run)
        try:
            # A reader that fell behind gets no more deltas, but the stream stays
            # open (with heartbeats) for the final event (ChatEventChannel).
            while not producer.done() or not channel.queue.empty():
                try:
                    frame = await asyncio.wait_for(channel.queue.get(), timeout=HEARTBEAT_SECONDS)
                except TimeoutError:
                    if not producer.done():
                        yield ": heartbeat\n\n"
                    continue
                yield frame
        finally:
            # The run is not tied to this connection. A phone switching
            # networks, a locked screen or a restarting proxy ends the stream,
            # not the work: the run finishes and saves its answer, and the app
            # reads it from history (run-state shows it active until then).
            # Only POST /api/chat/{session_id}/stop cancels a run.
            channel.detach()

    return ChatStreamingResponse(
        event_frames(),
        release_stream=transport_finished,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store",
            "X-Accel-Buffering": "no",
            "X-Chat-Request-ID": request_id,
            "X-Chat-Message-ID": message_id,
        },
    )


@app.post("/api/chat")
async def chat(
    req: ChatMessage,
    background_tasks: BackgroundTasks,
    user: TokenPayload | None = Depends(get_current_user),
):
    """Chat with an agent"""
    await authorize_session(req.session_id, user, create=True)
    session = active_sessions.get(req.session_id)

    # Auto-restore session from DB if not in memory (fixes cross-restart amnesia)
    if session is None:
        db_messages = await memory.get_messages(req.session_id, limit=50)
        restored_history = [{"role": msg["role"], "content": msg["content"]} for msg in db_messages]
        session = {"history": restored_history}
        if restored_history:
            logger.info(
                "[SESSION] Restored %d messages for session %s from DB",
                len(restored_history),
                req.session_id[:12],
            )

    active_sessions[req.session_id] = session

    await memory.save_message(req.session_id, "user", req.content)
    session["history"].append({"role": "user", "content": req.content})

    agent_id = req.agent_id or (list(active_agents.keys())[0] if active_agents else None)
    agent = active_agents.get(agent_id) if agent_id else None

    if agent:
        agent = await chat_agent_for(user, agent)

    # Check for in-chat commands
    cmd_result = await handle_command(
        req.content,
        agent=agent,
        session_id=req.session_id,
        sessions=active_sessions,
        memory=memory,
        active_agents=_visible_agents(user),
    )
    if cmd_result.get("is_command"):
        await manager.broadcast(
            {
                "type": "command_result",
                "session_id": req.session_id,
                "content": cmd_result["response"],
            }
        )
        return {
            "message_id": str(uuid.uuid4()),
            "session_id": req.session_id,
            "status": "command",
            "response": cmd_result["response"],
        }

    if not agent_id or agent_id not in active_agents:
        raise HTTPException(503, "No agents available")

    agent = await chat_agent_for(user, active_agents[agent_id])
    message_id = str(uuid.uuid4())
    run_key = (user.user_id if user else "", req.session_id)
    running = _stream_runs.get(run_key)
    if running is not None and not running.finished:
        raise HTTPException(
            409,
            {
                "code": "chat_stream_active",
                "message": "A chat run is still active for this session.",
                "session_id": req.session_id,
                "active_request": running.public(),
            },
        )
    lease = ChatRunLease(req.session_id, str(uuid.uuid4()), message_id)
    lease.transport_finished = True  # no stream: the run alone decides when it ends
    lease.update(status="running", phase="model")

    async def process_chat():
        # Send typing indicator before starting agent execution
        await manager.broadcast(
            {
                "type": "typing",
                "session_id": req.session_id,
                "message_id": message_id,
                "agent": agent.name,
            }
        )

        response = ""
        rest_trace = thinking_stream.create_trace(message_id)

        async def stream_cb(chunk: str, **kwargs):
            nonlocal response
            chunk_type = kwargs.get("chunk_type", "text")
            if chunk_type == "tool_use":
                await manager.broadcast(
                    {
                        "type": "tool_use",
                        "tool_name": kwargs.get("tool_name", "unknown"),
                        "session_id": req.session_id,
                        "message_id": message_id,
                    }
                )
                return
            response += chunk
            await manager.broadcast(
                {
                    "type": "chat_stream",
                    "session_id": req.session_id,
                    "message_id": message_id,
                    "chunk": chunk,
                }
            )

        async def thinking_cb(phase: str, content: str, confidence: float, metadata: dict):
            thinking_stream.add_step(
                rest_trace.request_id,
                ThinkingPhase(phase),
                content,
                confidence,
                metadata,
            )
            await manager.broadcast(
                {
                    "type": "thinking",
                    "phase": phase,
                    "content": content,
                    "confidence": confidence,
                    "message_id": message_id,
                    "session_id": req.session_id,
                    "metadata": metadata,
                }
            )

        from tadbir.waqt import bind_timezone

        try:
            with bind_timezone(req.timezone), await owner_consent(user.user_id):
                result = await agent.execute(
                    req.content,
                    await chat_context(user, req.session_id, session, agent, req.content),
                    stream_callback=stream_cb,
                    thinking_callback=thinking_cb,
                    model_override=req.model_override,
                )
        except asyncio.CancelledError:
            # Stopped (POST /api/chat/{id}/stop): what was written so far is kept.
            thinking_stream.complete(message_id)
            await memory.save_message(
                req.session_id,
                "assistant",
                response,
                agent_id,
                metadata={"status": "stopped", "completion_status": "stopped", "partial": True},
            )
            await manager.broadcast(
                {"type": "chat_stopped", "session_id": req.session_id, "message_id": message_id}
            )
            lease.update(status="cancelled", phase="delivery")
            return
        except Exception:
            logger.exception("Legacy chat execution failed for message %s", message_id)
            thinking_stream.complete(message_id)
            result = {"success": False, "completion_status": "failed", "task_verified": False}

        final_response = result.get("result", response) if result.get("success") else response
        if isinstance(final_response, dict):
            final_response = final_response.get("response", str(final_response))

        failure = chat_failure_payload(result) if not result.get("success") else {}
        await memory.save_message(
            req.session_id,
            "assistant",
            str(final_response),
            agent_id,
            metadata={
                "usage": result.get("usage", {}),
                **chat_completion_receipt(result),
                "status": "complete" if result.get("success") else "error",
                **({"partial": True, **failure} if failure else {}),
            },
        )
        session["history"].append({"role": "assistant", "content": str(final_response)})
        if not result.get("success"):
            thinking_stream.complete(message_id)
            await manager.broadcast(
                {
                    "type": "error",
                    "session_id": req.session_id,
                    "message_id": message_id,
                    **failure,
                }
            )
            return

        # Extract cognitive metadata from QALB-7 pipeline
        cognitive = {
            k: result.get(k)
            for k in (
                "nafs_level",
                "nafs_name",
                "ruh_energy",
                "qalb",
                "yaqin",
                "mizan_label",
                "cognitive_method",
                "lubb",
                "lawwama",
                "metrics_kind",
                "metric_provenance",
            )
            if result.get(k) is not None
        }

        thinking_stream.complete(message_id)
        completed_trace = thinking_stream.get_trace(message_id)
        trace_dict = None
        if completed_trace:
            trace_dict = {
                "request_id": completed_trace.request_id,
                "steps": [
                    {
                        "id": s.id,
                        "phase": s.phase.value,
                        "content": s.content,
                        "confidence": s.confidence,
                        "timestamp": s.timestamp,
                        "metadata": s.metadata,
                    }
                    for s in completed_trace.steps
                ],
                "duration_ms": completed_trace.duration_ms,
                "avg_confidence": completed_trace.avg_confidence,
            }

        await manager.broadcast(
            {
                "type": "chat_complete",
                "session_id": req.session_id,
                "message_id": message_id,
                "response": str(final_response),
                "usage": result.get("usage", {}),
                **chat_completion_receipt(result),
                "agent": agent.name,
                "cognitive": cognitive,
                "thinking_trace": trace_dict,
            }
        )

    async def run_chat() -> None:
        try:
            await process_chat()
        finally:
            if lease.status == "running":
                lease.update(status="complete", phase="delivery")
            if _stream_runs.get(run_key) is lease:
                _stream_runs.pop(run_key, None)

    lease.producer = asyncio.create_task(run_chat())
    _stream_runs[run_key] = lease
    return {
        "message_id": message_id,
        "session_id": req.session_id,
        "request_id": lease.request_id,
        "status": "processing",
    }


@app.get("/api/chat/sessions/list")
async def list_sessions(
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    q: str | None = Query(
        None,
        max_length=200,
        description="Only chats whose title or first message contains this, in any case.",
    ),
    workspace_id: str | None = Query(
        None, min_length=1, max_length=100, description="Only the chats bound to this project."
    ),
    user: TokenPayload = Depends(require_auth),
):
    """The user's chats, newest first; ``limit``/``offset`` page through them
    and ``next_offset`` is where the next page starts (null at the end).
    ``q`` keeps the chats whose title or first message holds it (any case;
    ``%`` and ``_`` are plain characters); a blank ``q`` lists every chat."""
    search = (q or "").strip() or None
    db_sessions = await memory.list_sessions(
        limit=limit + 1, owner_id=user.user_id, offset=offset, q=search, workspace_id=workspace_id
    )
    more = len(db_sessions) > limit
    return {
        "sessions": db_sessions[:limit],
        "limit": limit,
        "offset": offset,
        "next_offset": offset + limit if more else None,
        "q": search,
    }


class ChatPreferenceValue(BaseModel):
    value: str = Field(min_length=1, max_length=2000)


@app.get("/api/chat/preferences")
async def get_chat_preferences(user: TokenPayload = Depends(require_auth)):
    return {"preferences": await memory.get_chat_preferences(user.user_id)}


def _consent_receipt(owner: str, key: str, value: str) -> None:
    """A change to what MIZAN may learn or keep is a Sakk receipt (docs/consent.md)."""
    if key not in CONSENT_KEYS:
        return
    from security import sakk

    sakk.record(owner, "consent", {"purpose": key, "value": value}, f"consent · {key} {value}")


@app.put("/api/chat/preferences/{key}")
async def set_chat_preference(
    key: str, req: ChatPreferenceValue, user: TokenPayload = Depends(require_auth)
):
    try:
        saved = await memory.set_chat_preference(user.user_id, key, req.value)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    _consent_receipt(user.user_id, key, saved["value"])
    return saved


@app.delete("/api/chat/preferences/{key}")
async def delete_chat_preference(key: str, user: TokenPayload = Depends(require_auth)):
    try:
        deleted = await memory.delete_chat_preference(user.user_id, key)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if deleted:
        # Back to the default: learning on, training off.
        _consent_receipt(user.user_id, key, "default")
    return {"deleted": deleted}


class ApprovalDecision(BaseModel):
    decision: str = Field(..., pattern=r"^(allow|deny|always)$")


@app.post("/api/chat/approvals/{approval_id}")
async def resolve_chat_approval(
    approval_id: str,
    body: ApprovalDecision,
    user: TokenPayload = Depends(require_auth),
):
    """Answer a pending tool approval of one of the caller's own live chats."""
    import re

    from security.approvals import broker

    if not re.fullmatch(r"[0-9a-f]{32}", approval_id) or not broker.resolve(
        user.user_id, approval_id, body.decision
    ):
        raise HTTPException(404, "No pending approval with that id")
    from security import sakk

    sakk.record(
        user.user_id,
        "approval",
        {"approval": approval_id, "decision": body.decision},
        f"approval · {body.decision}",
    )
    return {"approval_id": approval_id, "decision": body.decision}


@app.get("/api/chat/approvals")
async def list_chat_approvals(user: TokenPayload = Depends(require_auth)):
    from security.approvals import broker

    return {"pending": broker.pending_for(user.user_id)}


class ElicitationAnswer(BaseModel):
    """A person's answer to a question a connected server asked during a tool call."""

    action: str = Field(..., pattern=r"^(accept|decline|cancel)$")
    content: dict[str, Any] | None = Field(default=None, max_length=100)
    # The chat the answer is given in: given, it must be the chat that asked.
    session_id: str | None = Field(default=None, min_length=1, max_length=100)


@app.post("/api/chat/elicitations/{elicitation_id}")
async def answer_chat_elicitation(
    elicitation_id: str,
    body: ElicitationAnswer,
    user: TokenPayload = Depends(require_auth),
):
    """Answer a connector's pending question in one of the caller's own live chats."""
    import re

    from connectors.elicitation import broker as elicitations

    if not re.fullmatch(r"[0-9a-f]{32}", elicitation_id) or not elicitations.resolve(
        user.user_id,
        elicitation_id,
        body.action,
        body.content if body.action == "accept" else None,
        session_id=body.session_id,
    ):
        raise HTTPException(404, "No pending question with that id")
    from security import sakk

    sakk.record(
        user.user_id,
        "elicitation",
        {"elicitation": elicitation_id, "action": body.action},
        f"elicitation · {body.action}",
    )
    return {"id": elicitation_id, "action": body.action}


class HeldDecision(BaseModel):
    decision: str = Field(..., pattern=r"^(allow|deny)$")
    # The SHA-256 (or its first 12+ characters) of the parameters you were
    # shown; given, the decision applies only to exactly those parameters.
    params_sha256: str | None = Field(None, pattern=r"^[0-9a-f]{12,64}$")


@app.get("/api/chat/held")
async def list_held_actions(user: TokenPayload = Depends(require_auth)):
    """Actions your watchers and other unattended runs held for your approval."""
    from security.approvals import held_store

    return {"held": held_store().pending(user.user_id)}


@app.post("/api/chat/held/{held_id}")
async def decide_held_action(
    held_id: str, body: HeldDecision, user: TokenPayload = Depends(require_auth)
):
    """Allow or deny one held action. Allowed, it runs exactly once, as it was
    held, through your own agent and its gates; the result is posted to the chat."""
    outcome = await _decide_held(user, held_id, body.decision, seen=body.params_sha256)
    if outcome is None:
        raise HTTPException(404, "No action is waiting for you with that id and those parameters")
    return outcome


async def _decide_held(
    user: TokenPayload,
    held_id: str,
    decision: str,
    *,
    seen: str | None = None,
    via: str = "web",
) -> dict | None:
    """Claim one held action for its owner and, if allowed, run it once.
    None when nothing is waiting for this owner under that id (or, with
    ``seen``, not with the parameters the owner was shown)."""
    import re

    from security.approvals import ApprovalContext, bind_approvals, held_store, params_digest

    store = held_store()
    item = (
        store.claim(user.user_id, held_id, decision, via=via, seen=seen)
        if re.fullmatch(r"[0-9a-f]{32}", held_id)
        else None
    )
    if item is None:
        return None
    from security import sakk

    sakk.record(
        user.user_id,
        "held_decision",
        {
            "held": held_id,
            "tool": item["tool"],
            "decision": decision,
            # The receipt names exactly what was decided on.
            "params_sha256": item["params_sha256"],
            "via": via,
        },
        f"{item['tool']} · {'allowed' if decision == 'allow' else 'denied'} by you",
    )
    session = item["session_id"]
    if session.startswith("unattended:"):
        session = muraqabah_session(user.user_id)
    if decision == "deny":
        store.finish(held_id, {"declined": True})
        # Islah: the person refused what the answer of that chat needed.
        from tadbir import khatimah

        khatimah.signal(user.user_id, "denied", chat=session)
        return {"held_id": held_id, "status": "denied"}
    template = _tadbir_coordinator()
    if template is None:
        store.finish(held_id, {"error": "No agent available"})
        raise HTTPException(503, "No agent available")
    agent = await chat_agent_for(user, template)
    binding = bind_principal(user)
    try:
        # The owner's decision approves this one exact call; nothing else.
        context = ApprovalContext(
            user.user_id,
            session,
            "ask",
            granted=(item["tool"], params_digest(item["params"])),
        )
        with bind_approvals(context):
            result = await agent._execute_tool_safe(item["tool"], item["params"])
    except Exception as exc:  # noqa: BLE001 - reported to the owner, never re-run
        result = {"error": f"{type(exc).__name__}: {exc}"[:500]}
    finally:
        reset_principal(binding)
    outcome = result if isinstance(result, dict) else {"result": str(result)[:20000]}
    store.finish(held_id, outcome)
    shown = json.dumps(outcome, ensure_ascii=False, default=str)[:3000]
    await memory.authorize_session(session, user.user_id, create=True)
    await memory.save_message(
        session,
        "assistant",
        f"**You allowed: {item['tool']}**\n\n```json\n{shown}\n```",
        metadata={"held_result": held_id, "status": "complete"},
    )
    return {"held_id": held_id, "status": "done", "tool": item["tool"], "result": outcome}


@app.get("/api/chat/{session_id}/always")
async def list_chat_always(session_id: str, user: TokenPayload = Depends(require_auth)):
    """What the user allowed "always" in this chat; each can be revoked."""
    from security.approvals import chat_always_store

    await authorize_session(session_id, user)
    return {
        "session_id": session_id,
        "always": chat_always_store().list(user.user_id, session_id),
    }


@app.delete("/api/chat/{session_id}/always/{key}")
async def revoke_chat_always(session_id: str, key: str, user: TokenPayload = Depends(require_auth)):
    """Ask again before this tool (or tool action) in this chat, from now on."""
    from security.approvals import chat_always_store

    await authorize_session(session_id, user)
    if not chat_always_store().remove(user.user_id, session_id, key):
        raise HTTPException(404, "Nothing was allowed always under that name in this chat")
    return {"session_id": session_id, "revoked": key}


@app.get("/api/chat/{session_id}")
async def get_chat_history(
    session_id: str,
    limit: int = 50,
    before: str | None = None,
    user: TokenPayload = Depends(require_auth),
):
    """Newest ``limit`` messages; pass ``before=<message id>`` to page further back.
    ``workspace_id`` is the project the chat is bound to (null when none)."""
    await authorize_session(session_id, user)
    limit = max(1, min(limit, 500))
    page = await memory.get_messages(session_id, limit=limit + 1, before_id=before)
    has_more = len(page) > limit
    messages = page[1:] if has_more else page
    return {
        "session_id": session_id,
        "messages": messages,
        "has_more": has_more,
        "workspace_id": await memory.session_workspace(user.user_id, session_id),
    }


@app.get("/api/chat/memory/summary")
async def get_conversation_memory_summary(user: TokenPayload = Depends(require_auth)):
    return {
        **await memory.conversation_counts(user.user_id),
        "recall_enabled": True,
        "recall_limit": 5,
        "automatic_weight_training": False,
        "preferences": await memory.get_chat_preferences(user.user_id),
    }


# === PLANNER (Tafakkur — تفكر) ===


class PlanRequest(BaseModel):
    goal: str = Field(..., description="The complex goal to decompose")
    agent_id: str | None = None


@app.post("/api/plan")
async def create_plan(
    req: PlanRequest,
    background_tasks: BackgroundTasks,
    user: TokenPayload | None = Depends(get_current_user),
):
    """Decompose a complex goal into sub-tasks using TafakkurPlanner"""
    agent_id = req.agent_id or (list(active_agents.keys())[0] if active_agents else None)
    if not agent_id or agent_id not in active_agents:
        raise HTTPException(503, "No agents available")

    agent = active_agents[agent_id]
    plan = await planner.decompose(req.goal, agent)

    return {"plan": plan.to_dict()}


@app.post("/api/plan/{plan_id}/execute")
async def execute_plan(
    plan_id: str,
    background_tasks: BackgroundTasks,
    user: TokenPayload | None = Depends(get_current_user),
):
    """Execute a previously created plan"""
    plan = planner.get_plan(plan_id)
    if not plan:
        raise HTTPException(404, f"Plan {plan_id} not found")

    async def run_plan():
        result = await planner.execute_plan(plan, active_agents)
        await manager.broadcast(
            {
                "type": "plan_complete",
                "plan_id": plan_id,
                "result": result,
            }
        )

    background_tasks.add_task(run_plan)
    return {"status": "executing", "plan_id": plan_id}


@app.get("/api/plan/{plan_id}")
async def get_plan(plan_id: str):
    """Get status of a plan"""
    plan = planner.get_plan(plan_id)
    if not plan:
        raise HTTPException(404, f"Plan {plan_id} not found")
    return {"plan": plan.to_dict()}


# === MEMORY ===


async def _own_agent(user: TokenPayload):
    """The agent whose memory and learning belong to this user, if agents are running."""
    template = _tadbir_coordinator()
    return None if template is None else await chat_agent_for(user, template)


async def _own_memory(user: TokenPayload) -> DhikrMemorySystem:
    """This user's notes: admins share the main store, everyone else has their own."""
    agent = await _own_agent(user)
    if agent is not None:
        return cast(DhikrMemorySystem, agent.memory)
    return memory if user.has_role("admin") else _private_memory(user)


def _expiry(value: str) -> str:
    if not value:
        return ""
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(422, "expires must be an ISO date or time") from None
    return (moment if moment.tzinfo else moment.replace(tzinfo=UTC)).isoformat()


@app.post("/api/memory/query")
async def query_memory(req: MemoryQuery, user: TokenPayload = Depends(require_auth)):
    own = await _own_memory(user)
    memories = await own.recall(req.query, req.memory_type, req.agent_id, req.limit)
    return {
        "query": req.query,
        "results": [
            {
                "id": m.id,
                "content": str(m.content)[:500],
                "type": m.memory_type,
                "importance": m.importance,
                "agent_id": m.agent_id,
                "tags": m.tags,
                "recency": m.recency.isoformat(),
                "access_count": m.access_count,
            }
            for m in memories
        ],
    }


@app.post("/api/memory/store")
async def store_memory(req: MemoryStore, user: TokenPayload = Depends(require_auth)):
    """Save a note to this user's own memory, which their agents recall."""
    own = await _own_memory(user)
    mem_id = await own.remember(
        req.content,
        req.memory_type,
        req.importance,
        tags=req.tags,
        source="manual",
        expires=_expiry(req.expires),
    )
    return {"id": mem_id, "stored": True}


@app.post("/api/memory/consolidate")
async def consolidate_memory(user: TokenPayload = Depends(require_auth)):
    result = await (await _own_memory(user)).consolidate()
    return result


@app.get("/api/memory/list")
async def list_memories(
    memory_type: str | None = None, limit: int = 30, user: TokenPayload = Depends(require_auth)
):
    """List this user's recent memories without search filtering."""
    memory = await _own_memory(user)
    conn = memory._get_conn()
    c = conn.cursor()
    sql = "SELECT * FROM memories WHERE 1=1"
    params: list = []
    if memory_type:
        sql += " AND memory_type = ?"
        params.append(memory_type)
    sql += " ORDER BY recency DESC LIMIT ?"
    params.append(limit)
    c.execute(sql, params)
    rows = c.fetchall()
    memory._release_conn(conn)

    results = []
    for row in rows:
        try:
            content = json.loads(row[1]) if row[1] else None
        except Exception:
            content = row[1]
        results.append(
            {
                "id": row[0],
                "content": str(content)[:500] if content else "",
                "type": row[2],
                "importance": row[3] or 0,
                "recency": row[4] or "",
                "access_count": row[5] or 0,
                "agent_id": row[6],
                "tags": json.loads(row[7]) if row[7] else [],
            }
        )
    return {"results": results, "total": len(results)}


@app.get("/api/memory/tadhkir")
async def memory_tadhkir(user: TokenPayload = Depends(require_auth)):
    """The FSRS parameters memory strength is computed with (Tadhkir): FSRS's
    defaults, or parameters fitted on this memory's own review log while MIZAN
    rests, with the held-out test that earned them and the latest night's test
    (``mode``: ``shadow`` reports a passing fit without using it). ``episodes``
    pools every person's episodes (no words): whether their strength says which
    episode is needed (docs/episodic-memory.md, "Before recall")."""
    from memory import episodic, tadhkir

    own = await _own_memory(user)
    conn = own._get_conn()
    try:
        found = tadhkir.report(conn)
    finally:
        own._release_conn(conn)
    try:
        found["episodes"] = await asyncio.to_thread(episodic.strength_report)
    except Exception as exc:  # noqa: BLE001 - the report never hides Tadhkir's
        found["episodes"] = {"status": f"failed: {type(exc).__name__}"}
    return found


# === IQTISAD (اقتصاد): hard spending limits on model calls ===


class SpendingLimits(BaseModel):
    """USD limits; null removes that limit (the server or admin limit applies)."""

    daily_usd: float | None = Field(None, ge=0, le=100_000)
    monthly_usd: float | None = Field(None, ge=0, le=1_000_000)


def _iqtisad_ledger():
    from api import iqtisad

    store = iqtisad.ledger()
    if store is None:
        raise HTTPException(503, "The spending ledger is unavailable")
    return iqtisad, store


@app.get("/api/iqtisad")
async def spending_summary(user: TokenPayload = Depends(require_auth)):
    """What your model calls cost today and this month, against your limits."""
    iqtisad, _ = _iqtisad_ledger()
    return await asyncio.to_thread(iqtisad.summary, user.user_id, admin=user.has_role("admin"))


@app.put("/api/iqtisad/limits")
async def set_own_spending_limits(body: SpendingLimits, user: TokenPayload = Depends(require_auth)):
    """Set your own limits. They can only make your budget smaller: the server's
    or an administrator's limit still applies when it is lower."""
    iqtisad, store = _iqtisad_ledger()
    await asyncio.to_thread(
        store.set_limits, user.user_id, "self", body.daily_usd, body.monthly_usd
    )
    return await asyncio.to_thread(iqtisad.summary, user.user_id, admin=user.has_role("admin"))


@app.get("/api/iqtisad/all")
async def spending_by_user(user: TokenPayload = Depends(require_auth)):
    """This month's model spend for every user (administrators)."""
    _require_admin(user)
    iqtisad, store = _iqtisad_ledger()
    _, month, _ = iqtisad.periods(user.user_id)
    people = {record["id"]: record for record in auth.list_users()}
    rows = await asyncio.to_thread(store.owners, month)
    for row in rows:
        person = people.get(row["owner_id"])
        row["username"] = person["username"] if person else "system"
        row["limits_usd"] = (
            iqtisad.effective_limits(row["owner_id"], admin="admin" in person["roles"])
            if person
            else {"day": None, "month": None}
        )
    return {"month": month, "users": rows}


@app.put("/api/iqtisad/limits/{owner_id}")
async def set_user_spending_limits(
    owner_id: str, body: SpendingLimits, user: TokenPayload = Depends(require_auth)
):
    """Set one user's limits (administrators). Null for both returns that user
    to the server's default limits."""
    _require_admin(user)
    if owner_id not in {record["id"] for record in auth.list_users()}:
        raise HTTPException(404, "No such user")
    _, store = _iqtisad_ledger()
    await asyncio.to_thread(store.set_limits, owner_id, "admin", body.daily_usd, body.monthly_usd)
    return {"owner_id": owner_id, "daily_usd": body.daily_usd, "monthly_usd": body.monthly_usd}


# === DAFTAR (دفتر): everything MIZAN keeps about you, with provenance ===


@app.get("/api/daftar")
async def daftar_ledger(
    query: str = Query("", max_length=200),
    kind: str = Query("", pattern=r"^(|note|preference|summary|learned|decision|handoff)$"),
    user: TokenPayload = Depends(require_auth),
):
    from memory import daftar

    agent = await _own_agent(user)
    return await daftar.ledger(
        notes_store=await _own_memory(user),
        memory=memory,
        adaptive=getattr(agent, "adaptive", None),
        owner_id=user.user_id,
        query=query,
        kind=kind,
    )


@app.post("/api/daftar")
async def daftar_add(req: MemoryStore, user: TokenPayload = Depends(require_auth)):
    """Save a note to remember; it goes to this user's own memory, which their agents recall."""
    own = await _own_memory(user)
    note = await own.remember(
        req.content,
        req.memory_type,
        req.importance,
        tags=req.tags,
        source="manual",
        expires=_expiry(req.expires),
    )
    return {"id": f"note:{note}"}


@app.patch("/api/daftar/{entry_id}")
async def daftar_edit(entry_id: str, req: DaftarEdit, user: TokenPayload = Depends(require_auth)):
    from memory import daftar

    kind, _, key = entry_id.partition(":")
    if kind == "preference":
        if req.content is None:
            raise HTTPException(422, "A preference needs its new value")
        try:
            saved = await memory.set_chat_preference(user.user_id, key, req.content)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        _consent_receipt(user.user_id, key, saved["value"])
        return saved
    if kind != "note":
        raise HTTPException(422, "Only notes and preferences can be edited")
    expires = None if req.expires is None else _expiry(req.expires)
    notes_store = await _own_memory(user)
    if not daftar.edit_note(notes_store, key, content=req.content, tags=req.tags, expires=expires):
        raise HTTPException(404, "No such note")
    return {"edited": entry_id}


@app.post("/api/daftar/forget")
async def daftar_forget(req: DaftarForget, user: TokenPayload = Depends(require_auth)):
    """Forget chosen entries, or everything about a topic (first a preview, then confirm)."""
    from memory import daftar

    notes_store = await _own_memory(user)
    ids = list(req.ids)
    if req.topic.strip():
        found = await daftar.ledger(
            notes_store=notes_store,
            memory=memory,
            adaptive=None,
            owner_id=user.user_id,
            query=req.topic,
        )
        matches = [e for e in found["entries"] if e["kind"] in ("note", "preference")]
        if not req.confirm:
            return {"preview": matches}
        ids += [entry["id"] for entry in matches]
    if not ids:
        return {"forgotten": {"note": 0, "preference": 0}}
    from memory import azm, mahw

    planning = [entry for entry in ids if entry.startswith(("decision:", "handoff:"))]
    ids = [entry for entry in ids if entry not in planning]
    notes = [entry.partition(":")[2] for entry in ids if entry.startswith("note:")]
    others = [entry for entry in ids if not entry.startswith("note:")]
    chosen = {item["key"] for item in await memory.get_chat_preferences(user.user_id)}
    forgotten = await daftar.forget(
        notes_store=notes_store, memory=memory, owner_id=user.user_id, ids=others
    )
    if planning:
        forgotten.update(await asyncio.to_thread(azm.forget_entries, user.user_id, planning))
    for key in CONSENT_KEYS:
        if key in chosen and f"preference:{key}" in others:
            _consent_receipt(user.user_id, key, "default")
    receipt = None
    if notes:
        # Notes live on in vectors and pathways too: Mahw removes them there.
        receipt = await mahw.erase_notes(
            private=notes_store, owner=user.user_id, note_ids=notes, chat_db=memory.db_path
        )
        forgotten["note"] = receipt["removed"].get("notes", 0)
    return {"forgotten": forgotten, **({"receipt": receipt} if receipt else {})}


@app.get("/api/daftar/receipts")
async def daftar_receipts(user: TokenPayload = Depends(require_auth)):
    """Receipts of what you asked MIZAN to forget, newest first."""
    from memory import mahw

    return {"receipts": await asyncio.to_thread(mahw.receipts, user.user_id)}


@app.get("/api/daftar/export")
async def daftar_export(
    format: str = Query("json", pattern=r"^(json|md)$"),
    user: TokenPayload = Depends(require_auth),
):
    from memory import daftar

    agent = await _own_agent(user)
    found = await daftar.ledger(
        notes_store=await _own_memory(user),
        memory=memory,
        adaptive=getattr(agent, "adaptive", None),
        owner_id=user.user_id,
    )
    if format == "md":
        return PlainTextResponse(
            daftar.to_markdown(found["entries"], user.username),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="mizan-daftar.md"'},
        )
    return JSONResponse(
        daftar.to_json(found["entries"]),
        headers={"Content-Disposition": 'attachment; filename="mizan-daftar.json"'},
    )


@app.post("/api/daftar/import")
async def daftar_import(data: dict, user: TokenPayload = Depends(require_auth)):
    from memory import daftar

    try:
        return {
            "imported": await daftar.import_entries(
                notes_store=await _own_memory(user), memory=memory, owner_id=user.user_id, data=data
            )
        }
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


# === 'AZM (عزم): the person's decisions and where the work stands ===


class DecisionCreate(BaseModel):
    """A decision, in the person's own words; scoped to a chat, a project or an agent."""

    decision: str = Field(..., min_length=1, max_length=500)
    why: str = Field("", max_length=500)
    session_id: str | None = Field(None, min_length=1, max_length=100)
    workspace_id: str | None = Field(None, min_length=1, max_length=100)
    agent_id: str | None = Field(None, min_length=1, max_length=100)
    # The message of the chat it was decided in.
    message_id: str | None = Field(None, min_length=1, max_length=100)


async def _azm_scope(
    user: TokenPayload,
    session_id: str | None,
    workspace_id: str | None,
    agent_id: str | None,
) -> None:
    """Every id a caller names must be theirs (404 otherwise, never a hint)."""
    if session_id:
        await authorize_session(session_id, user)
    if workspace_id:
        from workspace.store import WorkspaceStore

        await asyncio.to_thread(WorkspaceStore(user.user_id).project, workspace_id)
    if agent_id:
        _visible_agent(user, agent_id)


@app.get("/api/azm/decisions")
async def list_decisions(
    session_id: str | None = Query(None, max_length=100),
    workspace_id: str | None = Query(None, max_length=100),
    agent_id: str | None = Query(None, max_length=100),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user: TokenPayload = Depends(require_auth),
):
    """Your decisions, oldest first, narrowed to one of your chats, projects or agents."""
    from memory import azm

    if session_id:
        await authorize_session(session_id, user)
    found = await asyncio.to_thread(
        azm.decisions,
        user.user_id,
        chat_id=session_id,
        workspace_id=workspace_id,
        agent_id=agent_id,
        limit=limit,
        offset=offset,
    )
    return {"decisions": found, "limit": limit, "offset": offset}


@app.post("/api/azm/decisions")
async def add_decision(req: DecisionCreate, user: TokenPayload = Depends(require_auth)):
    """Record a decision of yours. It is never edited: a changed decision is a new one."""
    from memory import azm

    await _azm_scope(user, req.session_id, req.workspace_id, req.agent_id)
    if req.message_id:
        if not req.session_id:
            raise HTTPException(422, "A message is named together with its chat")
        messages = await memory.get_messages(req.session_id, limit=1000)
        if not any(str(item.get("id")) == req.message_id for item in messages):
            raise HTTPException(404, "No such message in that chat")
    try:
        decision = await asyncio.to_thread(
            azm.record,
            user.user_id,
            req.decision,
            req.why,
            chat_id=req.session_id or "",
            workspace_id=req.workspace_id or "",
            agent_id=req.agent_id or "",
            message_id=req.message_id or "",
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except azm.Unavailable as exc:
        raise HTTPException(503, "Decisions cannot be kept right now") from exc
    return {"decision": decision}


@app.delete("/api/azm/decisions/{decision_id}")
async def delete_decision(decision_id: int, user: TokenPayload = Depends(require_auth)):
    """Forget one of your decisions."""
    from memory import azm

    if not await asyncio.to_thread(azm.forget_decision, user.user_id, decision_id):
        raise HTTPException(404, "No such decision")
    return {"deleted": decision_id}


@app.get("/api/azm/handoff")
async def read_handoff(
    session_id: str | None = Query(None, max_length=100),
    workspace_id: str | None = Query(None, max_length=100),
    agent_id: str | None = Query(None, max_length=100),
    user: TokenPayload = Depends(require_auth),
):
    """The hand-off snapshot of one of your chats, projects or agents."""
    from memory import azm

    named = [
        (kind, value)
        for kind, value in (("chat", session_id), ("project", workspace_id), ("agent", agent_id))
        if value
    ]
    if len(named) != 1:
        raise HTTPException(422, "Name one chat, project or agent")
    await _azm_scope(user, session_id, workspace_id, agent_id)
    kind, value = named[0]
    found = await asyncio.to_thread(azm.handoff, user.user_id, f"{kind}:{value}")
    if found is None:
        raise HTTPException(404, "No hand-off yet")
    return {"handoff": found}


# === MURAQABAH (مراقبة): watchers that judge when to interrupt ===


def _muraqabah_store():
    from automation import muraqabah

    return muraqabah.default_store()


def _owner_token(owner_id: str) -> TokenPayload | None:
    record = auth.get_user(owner_id)
    if record is None:
        return None
    return TokenPayload(
        user_id=record.id,
        username=record.username,
        roles=list(record.roles),
        exp=time.time() + 600,
        iat=time.time(),
        jti="muraqabah",
    )


def _unattended_principal(owner_id: str | None) -> TokenPayload | None:
    """Who an unattended run acts for: its creator, else the first administrator."""
    if owner_id:
        token = _owner_token(owner_id)
        if token is not None:
            return token
    for record in auth.list_users():
        if "admin" in record["roles"] and record["enabled"]:
            return _owner_token(record["id"])
    return None


async def _run_unattended(agent, task: str, owner_id: str | None, origin: str) -> dict:
    """A run no one is watching (a schedule, a trigger, the queue): it acts as its
    owner, through that owner's gates, and every action that needs a person is
    held for them instead of run."""
    from security import approvals

    user = _unattended_principal(owner_id)
    if user is None:
        return {"error": "No owner to act for"}
    binding = bind_principal(user)
    try:
        with (
            approvals.unattended(user.user_id, f"unattended:{origin}", origin),
            await owner_consent(user.user_id),
        ):
            return cast(dict, await agent.execute(task))
    finally:
        reset_principal(binding)


async def _watcher_task(owner_id: str, task: str) -> str:
    """Run a watcher's task as its owner, through their own agent and its gates;
    actions that need a person are held for the owner (no one is watching)."""
    from automation import muraqabah
    from security import approvals

    user = _owner_token(owner_id)
    # The watcher's own agent when it names one the owner may use, else their default.
    chosen = active_agents.get(muraqabah.current_watcher_agent() or "")
    template = (
        chosen
        if chosen is not None and user is not None and _agent_visible(user, chosen)
        else await _default_agent_for(owner_id)
    )
    if user is None or template is None:
        return ""

    agent = await chat_agent_for(user, template)
    binding = bind_principal(user)
    session = muraqabah_session(owner_id)
    try:
        with (
            muraqabah.running_watcher(),
            approvals.unattended(owner_id, session, "watcher"),
            await owner_consent(owner_id),
        ):
            result = await agent.execute(task, {"session_id": session})
    finally:
        reset_principal(binding)
    from tadbir import niyyah

    # Niyyah: a watcher whose runs drift from its goal says so in its notice.
    drifted = niyyah.summary_line((result.get("usage") or {}).get("niyyah"))
    text = str(result.get("result") or "")
    return f"{text}\n\n{drifted}" if text and drifted else text


async def _watcher_page(owner_id: str, url: str) -> str | None:
    """A watched page's text, read through the web tool and Amanah, as the owner."""
    user = _owner_token(owner_id)
    template = _tadbir_coordinator()
    if user is None or template is None:
        return None
    agent = await chat_agent_for(user, template)
    binding = bind_principal(user)
    try:
        from tadbir import amanah

        page = await agent._execute_tool_safe("web_browse", {"url": url})
    finally:
        reset_principal(binding)
    if not isinstance(page, dict) or page.get("error"):
        return None
    cleaned, _found = amanah.guard_value(page, "web_browse")
    return str(cleaned.get("content") or "")[:20000]


def muraqabah_session(owner_id: str) -> str:
    from automation import muraqabah

    return str(muraqabah.session_id(owner_id))


async def _watcher_deliver(owner_id: str, text: str, metadata: dict) -> None:
    session = muraqabah_session(owner_id)
    await memory.authorize_session(session, owner_id, create=True)
    await memory.save_message(
        session,
        "assistant",
        text,
        metadata={"muraqabah": True, "status": "complete", **metadata},
    )
    await _bab_notify(owner_id, text, metadata)


# === BAB (باب): the user's own MIZAN from outside apps (Telegram) ===

_telegram_bot = None  # gateway.telegram.TelegramBot while the poller runs
_mail_bot = None  # gateway.mail.MailBot while MIZAN's mailbox is read
_whatsapp_bot = None  # gateway.whatsapp.WhatsAppBot when Meta's credentials are set


async def _bab_turn(
    owner_id: str, session_id: str, text: str, channel: str = "telegram"
) -> tuple[str, list[dict]]:
    """One message from a linked outside account: the same turn as the web
    chat, as its owner, saved to their chat. Actions that need a person are
    held and come back as buttons (Telegram) or a pointer to MIZAN (email)."""
    from memory import stateless
    from security import approvals
    from security.approvals import collecting_held
    from tadbir import waqt

    user = _owner_token(owner_id)
    # The person's default agent answers their channels (Khalifah when they chose none).
    template = await _default_agent_for(owner_id)
    if user is None or template is None:
        return "MIZAN cannot answer right now: no agent is running.", []
    await memory.authorize_session(session_id, owner_id, create=True)
    await memory.save_message(session_id, "user", text, metadata={"channel": channel})
    agent = await chat_agent_for(user, template)
    session = active_sessions.setdefault(session_id, {"history": []})
    binding = bind_principal(user)
    held: list[dict] = []
    try:
        context = await chat_context(user, session_id, session, agent, text)
        zone = _remembered_zone(owner_id)
        with (
            waqt.bind_timezone(zone),
            approvals.unattended(owner_id, session_id, channel),
            collecting_held() as found,
            # Meta's terms s.4.7: WhatsApp data never trains or improves a model.
            stateless.no_training(channel) if channel == "whatsapp" else nullcontext(),
            consent_bindings(context.get("user_preferences") or []),
        ):
            result = await agent.execute(text, context)
            held = list(found)
    finally:
        reset_principal(binding)
    if result.get("success", True):
        reply = str(result.get("result") or "").strip() or "—"
        # A channel shows no notes under the answer: a ruling question's
        # referral to a scholar goes in the message itself, on its own line.
        usage = result.get("usage") or {}
        for note in (
            (usage.get("sidq") or {}).get("note"),
            (usage.get("ahl") or {}).get("referral"),
        ):
            if note:
                reply = f"{reply}\n\n_{note}_"
        metadata: dict = {
            "status": "complete",
            "channel": channel,
            "usage": result.get("usage", {}),
        }
    else:
        failure = chat_failure_payload(result)
        reply, metadata = failure["message"], {"status": "error", "channel": channel, **failure}
    if held:
        metadata["held"] = held
    await memory.save_message(session_id, "assistant", reply, metadata=metadata)
    return reply, held


def _remembered_zone(owner_id: str) -> str | None:
    """The user's timezone as MIZAN last saw it (chat or prayer place)."""
    try:
        from api import iqtisad

        store = iqtisad.ledger()
        remembered = store.zone(owner_id) if store is not None else None
        if remembered:
            return str(remembered)
        place = _muraqabah_store().place(owner_id)
        zone = getattr(place, "tz", None)
        return str(zone) if zone else None
    except Exception:  # noqa: BLE001
        return None


async def _bab_decide(owner_id: str, held_id: str, decision: str, seen: str | None) -> str:
    user = _owner_token(owner_id)
    if user is None:
        return "Your MIZAN account is not available."
    try:
        outcome = await _decide_held(user, held_id, decision, seen=seen, via="telegram")
    except HTTPException as exc:
        return str(exc.detail)
    if outcome is None:
        return "Already decided, expired, or changed since you were shown it."
    if outcome["status"] == "denied":
        return "Denied: it will not run."
    result = outcome.get("result") or {}
    if isinstance(result, dict) and result.get("error"):
        return f"Allowed, but {outcome['tool']} failed: {str(result['error'])[:300]}"
    return f"Allowed: {outcome['tool']} ran once. The result is in your MIZAN chat."


async def _bab_notify(owner_id: str, text: str, metadata: dict) -> None:
    """Send a notice to the owner's devices (Web Push), linked Telegram (with
    buttons for held actions there) and linked WhatsApp."""
    from gateway import push
    from gateway import store as bab_store

    try:
        preferences = await memory.get_chat_preferences(owner_id)
        preview = any(
            item["key"] == "push_preview" and str(item["value"]).lower() == "on"
            for item in preferences
        )
        await push.notify(
            bab_store.store(),
            owner_id,
            "MIZAN",
            text,
            f"/?session={muraqabah_session(owner_id)}",
            preview=preview,
            tag="muraqabah",
        )
    except Exception as exc:  # noqa: BLE001 - the notice is still in the MIZAN chat
        logger.warning("Push notice not sent: %s", exc)
    if _whatsapp_bot is not None:
        try:
            await _whatsapp_bot.notify(owner_id, text)
        except Exception as exc:  # noqa: BLE001 - the notice is still in the MIZAN chat
            logger.warning("WhatsApp notice not sent: %s", exc)
    bot = _telegram_bot
    if bot is None or not bot.running:
        return
    link = bab_store.store().link_for_owner("telegram", owner_id)
    if link is None:
        return
    try:
        await bot.send(link["chat_id"], text)
        await bot.send_held(link["chat_id"], metadata.get("held") or [])
    except Exception as exc:  # noqa: BLE001 - the notice is still in the MIZAN chat
        logger.warning("Telegram notice not sent: %s", exc)


class PushSubscription(BaseModel):
    endpoint: str = Field(..., min_length=10, max_length=2000)
    keys: dict[str, str] = Field(default_factory=dict)


@app.get("/api/bab/push/key")
async def push_key(user: TokenPayload = Depends(require_auth)):
    """MIZAN's public key for this browser to subscribe with, and its devices."""
    from gateway import push
    from gateway import store as bab_store

    store = bab_store.store()
    return {
        "public_key": await asyncio.to_thread(push.public_key, store),
        "devices": len(push.subscriptions(store, user.user_id)),
    }


@app.post("/api/bab/push/subscription")
async def push_subscribe(body: PushSubscription, user: TokenPayload = Depends(require_auth)):
    """Turn notifications on for this browser (a known push service only)."""
    from gateway import push
    from gateway import store as bab_store

    try:
        push.subscribe(
            bab_store.store(),
            user.user_id,
            body.endpoint,
            body.keys.get("p256dh", ""),
            body.keys.get("auth", ""),
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, f"Subscription refused: {exc}") from None
    return {"subscribed": True}


@app.delete("/api/bab/push/subscription")
async def push_unsubscribe(
    endpoint: str = Query(..., min_length=10, max_length=2000),
    user: TokenPayload = Depends(require_auth),
):
    from gateway import push
    from gateway import store as bab_store

    return {"removed": push.unsubscribe(bab_store.store(), user.user_id, endpoint)}


@app.post("/api/bab/push/test")
async def push_test(user: TokenPayload = Depends(require_auth)):
    """Send yourself a test notice on every device you turned notifications on for."""
    from gateway import push
    from gateway import store as bab_store

    return await push.notify(
        bab_store.store(),
        user.user_id,
        "MIZAN",
        "Notifications work. Assalamu alaikum!",
        "/",
        preview=True,
        tag="test",
    )


# === VOICE INPUT (Sama' - سمع) ===


async def _earlier_words(session_id: str, user: TokenPayload) -> list[str]:
    """The user's own recent messages in this chat, for the hearing prior."""
    if not session_id or await memory.session_owner(session_id) is None:
        return []
    await authorize_session(session_id, user)
    messages = await memory.get_messages(session_id, limit=24)
    return [str(m["content"]) for m in messages if m.get("role") == "user"][-12:]


def _voice_left(user: TokenPayload) -> float | None:
    from gateway import store as bab_store
    from perception import sama

    return None if user.has_role("admin") else sama.left_today(bab_store.store(), user.user_id)


@app.get("/api/voice")
async def transcribe_status(user: TokenPayload = Depends(require_auth)):
    """Whether this server can turn speech into text, and today's allowance left."""
    from perception import sama

    left = _voice_left(user)
    return {
        "available": sama.available(),
        "seconds_left": None if left is None else round(left),
        "max_seconds": sama.MAX_SECONDS,
        "max_bytes": sama.MAX_BYTES,
    }


@app.post("/api/voice/transcribe")
async def transcribe(request: Request, user: TokenPayload = Depends(require_auth)):
    """A short voice recording as text for the composer (Sama'). The audio is
    heard on this server and kept nowhere; the person reads the words and sends them."""
    from gateway import store as bab_store
    from perception import sama

    if not sama.available():
        raise HTTPException(503, "Voice input is not installed on this server")
    if int(request.headers.get("content-length") or 0) > sama.MAX_BYTES + 65_536:
        raise HTTPException(413, "The recording is over 2 MB; send a shorter one")
    if not wali.check_rate_limit(f"stt:{user.user_id}")["allowed"]:
        raise HTTPException(429, "Too many recordings at once; wait a moment")
    left = _voice_left(user)
    if left is not None and left <= 0:
        raise HTTPException(
            429, "Today's voice allowance is used up; type instead, or try tomorrow"
        )
    form = await request.form()
    file = form.get("file")
    if not isinstance(file, StarletteUploadFile):
        raise HTTPException(400, "Send the recording as the 'file' field")
    audio = await file.read(sama.MAX_BYTES + 1)
    earlier = await _earlier_words(str(form.get("session_id") or "")[:100], user)
    try:
        heard = await sama.hear(
            audio,
            file.content_type or "",
            owner=user.user_id,
            store=bab_store.store(),
            earlier=earlier,
            limited=left is not None,
        )
    except sama.HearingError as exc:
        raise HTTPException(400, str(exc)) from exc
    left = _voice_left(user)
    return {
        "text": heard.text,
        "language": heard.language,
        "seconds": round(heard.seconds, 1),
        "seconds_left": None if left is None else round(left),
    }


async def _bab_hear(owner_id: str, session_id: str, audio: bytes, mime: str) -> str:
    """A Telegram voice note, heard like a recording from the web composer."""
    from gateway import store as bab_store
    from perception import sama

    user = _owner_token(owner_id)
    if user is None:
        raise ValueError("MIZAN cannot hear right now.")
    if not sama.available():
        raise ValueError("This MIZAN reads text messages only; voice input is not installed.")
    try:
        earlier = await _earlier_words(session_id, user)
        heard = await sama.hear(
            audio,
            mime,
            owner=owner_id,
            store=bab_store.store(),
            earlier=earlier,
            limited=not user.has_role("admin"),
        )
    except sama.HearingError as exc:
        raise ValueError(str(exc)) from exc
    return str(heard.text)


@app.get("/api/bab/telegram")
async def telegram_status(user: TokenPayload = Depends(require_auth)):
    """Whether MIZAN runs a Telegram bot, and whether your account is linked."""
    from gateway import store as bab_store

    bot = _telegram_bot
    link = bab_store.store().link_for_owner("telegram", user.user_id)
    username = ""
    if bot is not None and bot.running:
        try:
            username = str((await bot.me()).get("username", ""))
        except Exception:  # noqa: BLE001
            username = ""
    return {
        "available": bool(bot is not None and bot.running),
        "bot": username,
        "linked": link is not None,
        "linked_at": link["linked"] if link else None,
        "error": getattr(bot, "error", "") if bot is not None else "",
    }


@app.post("/api/bab/telegram/link")
async def telegram_link(user: TokenPayload = Depends(require_auth)):
    """A one-time link (10 minutes) that ties a Telegram account to you."""
    from gateway import store as bab_store
    from gateway.store import CODE_TTL

    bot = _telegram_bot
    if bot is None or not bot.running:
        raise HTTPException(503, "MIZAN is not running a Telegram bot")
    code = bab_store.store().new_code(user.user_id, "telegram")
    return {"url": await bot.link_url(code), "expires_in": int(CODE_TTL.total_seconds())}


@app.delete("/api/bab/telegram/link")
async def telegram_unlink(user: TokenPayload = Depends(require_auth)):
    from gateway import store as bab_store

    return {"unlinked": bab_store.store().unlink("telegram", user.user_id)}


@app.get("/api/bab/email")
async def email_status(user: TokenPayload = Depends(require_auth)):
    """Whether MIZAN reads its own mailbox, its address, and whether your address is linked."""
    from gateway import store as bab_store

    bot = _mail_bot
    link = bab_store.store().link_for_owner("email", user.user_id)
    return {
        "available": bool(bot is not None and bot.running),
        "address": bot.config.address if bot is not None else "",
        "linked": link is not None,
        "linked_address": link["external_id"] if link else None,
        "linked_at": link["linked"] if link else None,
        "error": getattr(bot, "error", "") if bot is not None else "",
    }


@app.post("/api/bab/email/link")
async def email_link(user: TokenPayload = Depends(require_auth)):
    """A one-time code (10 minutes): mail "link <code>" to MIZAN from your own address."""
    from gateway import store as bab_store
    from gateway.store import CODE_TTL

    bot = _mail_bot
    if bot is None or not bot.running:
        raise HTTPException(503, "MIZAN is not reading a mailbox")
    code = bab_store.store().new_code(user.user_id, "email")
    return {
        "code": code,
        "address": bot.config.address,
        "subject": f"link {code}",
        "expires_in": int(CODE_TTL.total_seconds()),
    }


@app.delete("/api/bab/email/link")
async def email_unlink(user: TokenPayload = Depends(require_auth)):
    from gateway import store as bab_store

    return {"unlinked": bab_store.store().unlink("email", user.user_id)}


@app.get("/api/bab/whatsapp")
async def whatsapp_status(user: TokenPayload = Depends(require_auth)):
    """Whether MIZAN is on WhatsApp, your linked number, and what Meta's terms
    allow for it: assistant (compelled markets) or ancillary (notices only)."""
    from gateway import store as bab_store
    from gateway import whatsapp

    bot = _whatsapp_bot
    link = bab_store.store().link_for_owner("whatsapp", user.user_id)
    number = str(link["external_id"]) if link else ""
    return {
        "available": bot is not None,
        "number": os.getenv("MIZAN_WHATSAPP_NUMBER", ""),
        "linked": link is not None,
        "linked_number": number or None,
        "region": whatsapp.region(number) if number else None,
        "mode": whatsapp.mode(number) if number else None,
        "error": getattr(bot, "error", "") if bot is not None else "",
    }


@app.post("/api/bab/whatsapp/link")
async def whatsapp_link(user: TokenPayload = Depends(require_auth)):
    """A one-time code (10 minutes): send "link <code>" to MIZAN's WhatsApp number."""
    import urllib.parse

    from gateway import store as bab_store
    from gateway.store import CODE_TTL

    if _whatsapp_bot is None:
        raise HTTPException(503, "MIZAN is not on WhatsApp")
    code = bab_store.store().new_code(user.user_id, "whatsapp")
    number = "".join(ch for ch in os.getenv("MIZAN_WHATSAPP_NUMBER", "") if ch.isdigit())
    text = f"link {code}"
    return {
        "code": code,
        "text": text,
        "url": f"https://wa.me/{number}?text={urllib.parse.quote(text)}" if number else None,
        "expires_in": int(CODE_TTL.total_seconds()),
    }


@app.delete("/api/bab/whatsapp/link")
async def whatsapp_unlink(user: TokenPayload = Depends(require_auth)):
    from gateway import store as bab_store

    return {"unlinked": bab_store.store().unlink("whatsapp", user.user_id)}


class PlaceRequest(BaseModel):
    city: str = Field(default="", max_length=120)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    tz: str = Field(default="", max_length=64)
    method: str = Field(default="", max_length=40)
    hanafi: bool | None = None
    budget: int | None = Field(default=None, ge=0, le=50)
    digest: str = Field(default="", pattern=r"^(|[0-2]?\d:[0-5]\d)$")
    quiet: bool | None = None


class WatcherRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    trigger: dict
    task: str = Field(..., min_length=1, max_length=1000)
    priority: str = Field(default="judge", pattern=r"^(judge|always)$")
    # The agent that runs the task (one you may use); none: your default agent.
    agent_id: str | None = Field(None, max_length=100)
    # Niyyah: what its work is for; none: its task is its goal.
    goal: str | None = Field(None, max_length=1000)


class WatcherUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=120)
    trigger: dict | None = None
    task: str | None = Field(None, min_length=1, max_length=1000)
    priority: str | None = Field(None, pattern=r"^(judge|always)$")
    enabled: bool | None = None
    # "" clears it (the default agent runs the task).
    agent_id: str | None = Field(None, max_length=100)
    # Niyyah: "" clears it (the task is the goal again).
    goal: str | None = Field(None, max_length=1000)


class NoticeFeedback(BaseModel):
    useful: bool


@app.get("/api/muraqabah")
async def muraqabah_overview(user: TokenPayload = Depends(require_auth)):
    """Your watchers, your place, today's prayer times and quiet windows, and attention used."""
    from automation import muraqabah

    store = _muraqabah_store()
    place = store.place(user.user_id)
    now = datetime.now(UTC)
    today = None
    if place is not None:
        day = now.astimezone(place.zone).date()
        times = muraqabah.prayer_times(place, day)
        today = {
            "date": day.isoformat(),
            "times": {name: moment.strftime("%H:%M") for name, moment in times.items()},
            "quiet": [
                {"prayer": name, "from": start.strftime("%H:%M"), "to": end.strftime("%H:%M")}
                for name, start, end in muraqabah.quiet_windows(place, day)
            ],
            "quiet_now": muraqabah.quiet_until(place, now) is not None,
        }
    return {
        "place": place.to_dict() if place else None,
        "today": today,
        "watchers": store.watchers(user.user_id),
        "delivered_today": store.delivered_today(user.user_id, place, now),
        "budget": place.budget if place else muraqabah.DEFAULT_BUDGET,
        "attention": {
            kind: dict(zip(("useful", "not_now"), store.posterior(user.user_id, kind), strict=True))
            for kind in muraqabah.TRIGGERS
        },
        "session_id": muraqabah_session(user.user_id),
        "methods": muraqabah.METHODS,
    }


@app.put("/api/muraqabah/place")
async def muraqabah_place(req: PlaceRequest, user: TokenPayload = Depends(require_auth)):
    """Your place (for prayer times), calculation method, Asr school and attention settings."""
    from automation import muraqabah

    store = _muraqabah_store()
    current = store.place(user.user_id)
    if req.city.strip():
        place = await muraqabah.find_place(req.city)
        if place is None:
            raise HTTPException(404, "MIZAN could not find that city; enter its coordinates")
    elif req.lat is not None and req.lon is not None:
        place = muraqabah.Place("Custom place", req.lat, req.lon, req.tz or "UTC")
    elif current is not None:
        place = current
    else:
        raise HTTPException(422, "Give a city, or coordinates and a time zone")
    if current is not None and place is not current:
        # A new place keeps the user's own settings.
        place.budget, place.digest, place.quiet = current.budget, current.digest, current.quiet
    if req.method:
        if req.method not in muraqabah.METHODS:
            raise HTTPException(422, "Unknown calculation method")
        place.method = req.method
    for name in ("hanafi", "budget", "quiet"):
        if getattr(req, name) is not None:
            setattr(place, name, getattr(req, name))
    if req.digest:
        place.digest = req.digest
    store.set_place(user.user_id, place)
    for watcher in store.watchers(user.user_id):
        store.update(user.user_id, watcher["id"], enabled=watcher["enabled"])  # re-time them
    return place.to_dict()


@app.post("/api/muraqabah/watchers")
async def add_watcher(req: WatcherRequest, user: TokenPayload = Depends(require_auth)):
    if req.agent_id:
        _visible_agent(user, req.agent_id)
    try:
        store = _muraqabah_store()
        made = store.add(
            user.user_id, req.title, req.trigger, req.task, req.priority, agent_id=req.agent_id
        )
        if req.goal and made:
            made = store.update(user.user_id, made["id"], goal=req.goal) or made
        return made
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.patch("/api/muraqabah/watchers/{watcher_id}")
async def update_watcher(
    watcher_id: str, req: WatcherUpdate, user: TokenPayload = Depends(require_auth)
):
    if req.agent_id:
        _visible_agent(user, req.agent_id)
    try:
        updated = _muraqabah_store().update(
            user.user_id, watcher_id, **req.model_dump(exclude_none=True)
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if updated is None:
        raise HTTPException(404, "No such watcher")
    return updated


@app.delete("/api/muraqabah/watchers/{watcher_id}")
async def delete_watcher(watcher_id: str, user: TokenPayload = Depends(require_auth)):
    if not _muraqabah_store().remove(user.user_id, watcher_id):
        raise HTTPException(404, "No such watcher")
    return {"deleted": watcher_id}


@app.post("/api/muraqabah/watchers/{watcher_id}/run")
async def run_watcher(watcher_id: str, user: TokenPayload = Depends(require_auth)):
    """Run a watcher now; its notice is judged like any other (salah, attention)."""
    from automation import muraqabah

    store = _muraqabah_store()
    watcher = store.watcher(user.user_id, watcher_id)
    if watcher is None:
        raise HTTPException(404, "No such watcher")
    now = datetime.now(UTC)
    await muraqabah.fire(store, watcher, now, _watcher_task, _watcher_page)
    counts = await muraqabah.deliver_waiting(store, now, _watcher_deliver)
    return {"ran": watcher_id, **counts}


@app.get("/api/muraqabah/notices")
async def watcher_notices(
    status: str = Query("", pattern=r"^(|pending|held|digest|delivered|opened|dismissed)$"),
    user: TokenPayload = Depends(require_auth),
):
    return {"notices": _muraqabah_store().notices(user.user_id, status or None)}


@app.post("/api/muraqabah/notices/{notice_id}/feedback")
async def watcher_feedback(
    notice_id: str, req: NoticeFeedback, user: TokenPayload = Depends(require_auth)
):
    """Useful or not now: this teaches MIZAN when to interrupt you."""
    if not _muraqabah_store().feedback(user.user_id, notice_id, req.useful):
        raise HTTPException(404, "No such notice")
    return {"recorded": notice_id}


# === PERCEPTION (Sam' + Basar - سَمْع + بَصَر) ===


@app.post("/api/perception/analyze")
async def analyze_multimodal(
    req: MultimodalInput,
    user: TokenPayload | None = Depends(get_current_user),
):
    """Analyze multimodal input through the QCA perception pipeline.

    Accepts text, base64-encoded images, and base64-encoded audio.
    Follows Quranic ordering: Sam' (hearing) before Basar (sight).
    """
    import base64 as b64

    agent = None
    if req.agent_id and req.agent_id in active_agents:
        agent = active_agents[req.agent_id]
    elif active_agents:
        agent = next(iter(active_agents.values()))

    if not agent:
        raise HTTPException(503, "No agents available for perception analysis")

    image_bytes = b64.b64decode(req.image_base64) if req.image_base64 else None
    audio_bytes = b64.b64decode(req.audio_base64) if req.audio_base64 else None

    if not req.text and not image_bytes and not audio_bytes:
        raise HTTPException(400, "At least one of text, image_base64, or audio_base64 is required")

    result = await agent.qca.process_input_multimodal(
        text=req.text,
        image_bytes=image_bytes,
        audio_bytes=audio_bytes,
        media_type=req.media_type,
        qalb_state=req.qalb_state,
    )
    return {"result": result}


# === KNOWLEDGE INGESTION (Ilm - عِلْم) ===


class KnowledgeIngest(BaseModel):
    source: str = Field(..., min_length=1, max_length=5000)
    source_type: str = Field(default="auto", pattern=r"^(auto|url|pdf|youtube)$")


@app.post("/api/knowledge/ingest")
async def ingest_knowledge(req: KnowledgeIngest):
    """Ingest knowledge from a URL or YouTube video into memory."""
    from knowledge.ingest import (
        chunk_content,
        detect_source_type,
        extract_url,
        extract_youtube,
    )

    source_type = req.source_type
    if source_type == "auto":
        source_type = detect_source_type(req.source)

    if source_type == "youtube":
        result = await extract_youtube(req.source)
    elif source_type == "url":
        try:
            result = await extract_url(req.source)
        except (ValueError, OSError) as exc:
            raise HTTPException(422, str(exc)) from exc
    else:
        raise HTTPException(
            400, f"Use /api/knowledge/upload for file uploads. Got source_type: {source_type}"
        )

    if "error" in result:
        raise HTTPException(422, result["error"])

    content = result.get("content", "")
    if not content:
        raise HTTPException(422, "No content extracted from source")

    from tadbir import amanah

    chunks = chunk_content(content)
    stored_ids = []
    for chunk in chunks:
        # Stored text is read back into prompts later: an instruction hidden in
        # the source is neutralized now, and the note says where it came from.
        clean, _found = amanah.neutralize(chunk)
        mem_id = await memory.remember(
            content=clean,
            memory_type="semantic",
            importance=0.8,
            tags=["knowledge", source_type, result.get("title", "")[:50]],
            source=f"knowledge:{req.source[:300]}",
        )
        stored_ids.append(mem_id)

    # Encode full content into Masalik pathways
    if hasattr(memory, "masalik"):
        memory.masalik.encode(content[:5000], importance=0.8)

    return {
        "success": True,
        "title": result.get("title", ""),
        "source": req.source,
        "source_type": source_type,
        "chunks_stored": len(stored_ids),
        "char_count": result.get("char_count", len(content)),
    }


@app.post("/api/knowledge/upload")
async def upload_knowledge(request: Request):
    """Upload a PDF file and ingest its content into memory."""
    from knowledge.ingest import chunk_content, extract_pdf

    form = await request.form()
    file = form.get("file")
    if not isinstance(file, StarletteUploadFile):
        raise HTTPException(400, "No file provided. Send a multipart form with 'file' field.")

    filename = getattr(file, "filename", "upload.pdf")
    file_bytes = await file.read()

    if not filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are supported for upload")

    if len(file_bytes) > 20 * 1024 * 1024:
        raise HTTPException(400, "File too large. Maximum 20MB.")

    result = extract_pdf(file_bytes, filename)
    if "error" in result:
        raise HTTPException(422, result["error"])

    content = result.get("content", "")
    if not content:
        raise HTTPException(422, "No text content extracted from PDF")

    from tadbir import amanah

    chunks = chunk_content(content)
    stored_ids = []
    for chunk in chunks:
        clean, _found = amanah.neutralize(chunk)
        mem_id = await memory.remember(
            content=clean,
            memory_type="semantic",
            importance=0.8,
            tags=["knowledge", "pdf", filename[:50]],
            source=f"knowledge:{filename[:300]}",
        )
        stored_ids.append(mem_id)

    if hasattr(memory, "masalik"):
        memory.masalik.encode(content[:5000], importance=0.8)

    return {
        "success": True,
        "title": result.get("title", ""),
        "source": filename,
        "source_type": "pdf",
        "page_count": result.get("page_count", 0),
        "chunks_stored": len(stored_ids),
        "char_count": result.get("char_count", len(content)),
    }


@app.get("/api/knowledge/sources")
async def list_knowledge_sources():
    """List ingested knowledge sources."""
    conn = memory._get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT DISTINCT json_extract(tags, '$[2]') as source_title, "
        "json_extract(tags, '$[1]') as source_type, "
        "COUNT(*) as chunk_count, "
        "MAX(recency) as last_updated "
        "FROM memories WHERE json_extract(tags, '$[0]') = 'knowledge' "
        "GROUP BY source_title ORDER BY last_updated DESC LIMIT 50"
    )
    rows = cursor.fetchall()
    memory._release_conn(conn)

    sources = [
        {
            "title": row[0] or "Unknown",
            "type": row[1] or "unknown",
            "chunks": row[2],
            "last_updated": row[3] or "",
        }
        for row in rows
    ]
    return {"sources": sources, "total": len(sources)}


# === FILE UPLOAD (Rafi' - رافع) ===

_ALLOWED_UPLOAD_SUFFIXES = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".txt",
    ".md",
    ".docx",
}
_MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB


@app.post("/api/upload")
async def upload_file(
    file: UploadFile,
    user: TokenPayload | None = Depends(get_current_user),
) -> dict:
    """Accept file uploads (PDF, images, docs) for processing."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _ALLOWED_UPLOAD_SUFFIXES:
        raise HTTPException(
            400, f"Unsupported file type '{suffix}'. Allowed: {sorted(_ALLOWED_UPLOAD_SUFFIXES)}"
        )

    content = await file.read()
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(400, "File too large. Maximum 20 MB.")

    upload_dir = Path(os.getenv("UPLOAD_DIR", "/data/uploads"))
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_id = str(uuid.uuid4())
    dest = upload_dir / f"{file_id}{suffix}"
    dest.write_bytes(content)

    wali.audit.log(
        "file_uploaded", {"file_id": file_id, "filename": file.filename, "size": len(content)}
    )
    return {"file_id": file_id, "filename": file.filename, "size": len(content), "path": str(dest)}


# === PROVIDERS (Ruh al-Ilm - روح العلم) ===


@app.get("/api/providers")
async def list_providers():
    """
    List all LLM providers with their status, models, and configuration.
    Inspired by OpenClaw's multi-provider architecture.
    """
    return get_provider_status()


@app.get("/api/providers/{provider_name}/models")
async def list_provider_models(
    provider_name: str,
    limit: int = 50,
    offset: int = 0,
    search: str = "",
    free_only: bool = False,
):
    """
    List available models for a specific provider.
    For OpenRouter: fetches the live catalog with search/filter/pagination.
    For Ollama: fetches locally installed models.
    """
    if provider_name == "openrouter":
        result = await fetch_openrouter_models(
            limit=limit,
            offset=offset,
            search=search,
            free_only=free_only,
        )
        return {"provider": "openrouter", **result}
    elif provider_name == "ollama":
        models = await fetch_ollama_models()
        return {"provider": "ollama", "models": models}
    elif provider_name in COMPATIBLE_ENDPOINTS:
        # xAI (Grok) and Meta (Muse Spark): the provider's own live list.
        models = await fetch_compatible_models(provider_name)
        if search:
            needle = search.lower()
            models = [m for m in models if needle in f"{m['id']} {m['name']}".lower()]
        return {
            "provider": provider_name,
            "models": models[offset : offset + limit],
            "total": len(models),
        }
    else:
        from providers import PROVIDER_MODELS

        return {
            "provider": provider_name,
            "models": next(
                (
                    p["models"]
                    for p in get_provider_status()["providers"]
                    if p["name"] == provider_name
                ),
                PROVIDER_MODELS.get(provider_name, []),
            ),
        }


@app.get("/api/providers/{provider_name}/health")
async def provider_health(provider_name: str):
    """
    Health check for a specific provider.
    Verifies API keys are valid and the provider is reachable.
    """
    result = await check_provider_health(provider_name)
    return result


class ProviderSwitchRequest(BaseModel):
    provider: str = Field(..., pattern=AGENT_PROVIDER_PATTERN)
    model: str = Field(..., min_length=1, max_length=200)


@app.post("/api/providers/switch")
async def switch_provider(
    req: ProviderSwitchRequest, user: TokenPayload | None = Depends(get_current_user)
):
    """
    Switch the default LLM provider and model: every agent that follows the default
    moves; an agent given its own provider and model keeps them.
    Persists choice to database so it survives restarts.
    """
    provider = create_provider(provider=req.provider, model=req.model)
    if not provider:
        raise HTTPException(400, f"Cannot initialize provider '{req.provider}'. Check API key.")
    return await _switch_all_agents(provider, req.model, req.provider)


async def _switch_all_agents(provider: Any, model: str, requested: str = "") -> dict:
    """Give every agent this provider/model and remember it across restarts."""
    provider_name = str(getattr(provider, "provider_name", requested) or requested)
    model = normalize_model_for_provider(model, provider_name)

    # Move every agent that follows the default; an agent given its own provider and
    # model (provider_override) keeps them.
    switched = 0
    for agent in active_agents.values():
        if isinstance(getattr(agent, "config", {}).get("provider_override"), dict):
            continue
        async with agent_settings_lock(agent):
            agent.ai_client = provider
            agent.ai_model = model
            agent._config_revision = getattr(agent, "_config_revision", 0) + 1
            if hasattr(agent, "config"):
                agent.config["model"] = model
        switched += 1

    set_active_state(provider_name, model)

    # Persist to DB so choice survives restart
    await memory.set_preference("active_provider", provider_name)
    await memory.set_preference("active_model", model)

    await manager.broadcast(
        {
            "type": "provider_switched",
            "provider": provider_name,
            "model": model,
            "agents_updated": switched,
        }
    )

    wali.audit.log("provider_switched", {"provider": provider_name, "model": model})
    await event_bus.emit("provider.switched", {"provider": provider_name, "model": model})
    return {
        "provider": provider_name,
        "model": model,
        "agents_updated": switched,
    }


# === ADMIN RUNTIME SETTINGS ===


class RuntimeSettingsUpdate(BaseModel):
    # A value of null resets that setting to the server's own environment value.
    values: dict[str, Any] = Field(default_factory=dict, max_length=80)


async def _apply_provider_settings(model_changed: bool) -> str:
    """Rebuild the active model after a provider, model or API key change."""
    if model_changed:
        name = os.getenv("LLM_PROVIDER", "auto").strip().lower()
        model = os.getenv("DEFAULT_MODEL", "").strip()
    else:
        status = get_provider_status()
        name, model = str(status.get("active") or ""), str(status.get("default_model") or "")
    provider = create_provider(provider=None if name in {"", "auto"} else name, model=model or None)
    if provider is None:
        raise HTTPException(
            400, "No model provider can start with these settings; check the API key"
        )
    model = model or get_default_model(provider.provider_name)
    result = await _switch_all_agents(provider, model)
    return f"Agents now use {result['provider']} / {result['model']}."


@app.get("/api/settings/runtime")
async def runtime_settings_view(user: TokenPayload = Depends(require_auth)):
    """Every operator setting with its current value (secrets are never returned)."""
    if not user.has_role("admin"):
        raise HTTPException(403, "Administrator role required")
    return runtime_settings.public_view()


@app.put("/api/settings/runtime")
async def runtime_settings_update(
    req: RuntimeSettingsUpdate, user: TokenPayload = Depends(require_auth)
):
    if not user.has_role("admin"):
        raise HTTPException(403, "Administrator role required")
    try:
        change = runtime_settings.update(req.values, user.username or user.user_id)
    except KeyError as exc:
        raise HTTPException(422, f"Unknown setting: {exc.args[0]}") from None
    except ValueError as exc:
        try:
            errors = json.loads(str(exc))
        except ValueError:
            errors = {"_": str(exc)}
        raise HTTPException(422, {"message": "Some values are invalid", "errors": errors}) from None
    notes: list[str] = []
    if change.provider_changed:
        try:
            notes.append(await _apply_provider_settings(change.model_changed))
        except HTTPException as exc:
            notes.append(f"Saved, but the model could not start yet: {exc.detail}")
    if change.restart_required:
        notes.append("Restart the backend to apply: " + ", ".join(change.restart_required))
    wali.audit.log("runtime_settings_updated", {"keys": change.applied, "by": user.user_id})
    view = runtime_settings.public_view()
    return {**view, "applied": change.applied, "notes": notes}


# === OWN ARCHITECTURE AND EXPLICIT TEACHER SUPPORT ===


@app.get("/api/owned/learning")
async def owned_learning_status():
    from mizan_owned.learning_service import learning_service

    return await learning_service.snapshot()


@app.post("/api/owned/learning/run", status_code=202)
async def owned_learning_run(req: LearningRunRequest, user: TokenPayload = Depends(require_auth)):
    from mizan_owned.learning_cycle import LearningBusy
    from mizan_owned.learning_service import learning_service

    try:
        job = await learning_service.start_cycle(req.bundle_id, requested_by=user.user_id)
    except LearningBusy as exc:
        raise HTTPException(409, "A learning cycle is already running") from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(
            422, "An approved, unprocessed local learning bundle is required"
        ) from exc
    wali.audit.log(
        "owned_learning_requested", {"user_id": user.user_id, "bundle_id": req.bundle_id}
    )
    return {"job": job, "accepted": True, "training_complete": False}


@app.post("/api/owned/learning/rollback")
async def owned_learning_rollback(
    req: LearningRollbackRequest, user: TokenPayload = Depends(require_auth)
):
    from mizan_owned.learning_cycle import LearningBusy, rollback
    from mizan_owned.learning_service import configured_root

    root = configured_root()
    if root is None:
        raise HTTPException(409, "Owned learning is not configured")
    try:
        result = await asyncio.to_thread(rollback, root, req.expected_generation)
    except LearningBusy as exc:
        raise HTTPException(409, "A learning cycle is running; rollback was not applied") from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(
            409, "Learning state changed or could not be verified; refresh first"
        ) from exc
    wali.audit.log(
        "owned_learning_rollback", {"user_id": user.user_id, "generation": req.expected_generation}
    )
    return result


@app.get("/api/owned/research/search")
async def owned_research_search(q: str = Query(min_length=1, max_length=300)):
    from mizan_owned.research import search

    try:
        return {"results": await asyncio.to_thread(search, q), "training_gold": False}
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/owned/chat")
async def owned_chat(req: OwnedRequest):
    from mizan_owned.provider import OwnedProvider

    def run():
        return OwnedProvider().create(
            "mizan-owned", 512, req.system, [m.model_dump() for m in req.messages]
        )

    response = await asyncio.to_thread(run)
    return {"text": response.content[0].text, "model": response.model, **response.usage}


@app.post("/api/owned/context/resolve")
async def owned_context(req: ContextRequest):
    try:
        return await asyncio.to_thread(resolve_context, req)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/owned/support")
async def owned_support(req: OwnedRequest, user: TokenPayload = Depends(require_auth)):
    from mizan_owned.provider import store_from_env
    from mizan_owned.support import draft_support

    try:
        return await asyncio.to_thread(
            lambda: draft_support(user.user_id, req.model_dump(), store_from_env())
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/owned/reviews")
async def owned_reviews(user: TokenPayload = Depends(require_auth)):
    from mizan_owned.provider import store_from_env

    return await asyncio.to_thread(lambda: store_from_env().list_proposals(user.user_id))


@app.post("/api/owned/reviews/{proposal_id}")
async def owned_review(
    proposal_id: str, req: ReviewRequest, user: TokenPayload = Depends(require_auth)
):
    from mizan_owned.provider import store_from_env

    try:
        return await asyncio.to_thread(
            lambda: store_from_env().review(
                user.user_id, proposal_id, reviewer=user.user_id, **req.model_dump()
            )
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/owned/retract")
async def owned_retract(req: RetractionRequest, user: TokenPayload = Depends(require_auth)):
    from mizan_owned.provider import store_from_env

    count = await asyncio.to_thread(
        lambda: store_from_env().retract(user.user_id, req.evidence, user.user_id)
    )
    return {"retracted": count}


@app.get("/api/owned/export")
async def owned_export(user: TokenPayload = Depends(require_auth)):
    from mizan_owned.provider import store_from_env

    rows = await asyncio.to_thread(lambda: store_from_env().export_reviews(user.user_id))
    return {"format": "reviewed-memory-v1", "original_training_gold": False, "records": rows}


# === PREFERENCES (persisted across restarts) ===


@app.get("/api/preferences")
async def get_preferences():
    """Return all persisted user preferences."""
    prefs = await memory.get_all_preferences()
    return {"preferences": prefs}


@app.post("/api/preferences")
async def save_preferences(req: dict):
    """Save one or more preferences. Body: {"key": "value", ...}"""
    saved = []
    for key, value in req.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        await memory.set_preference(key, value)
        saved.append(key)
    return {"saved": saved}


# === INTEGRATIONS ===


@app.get("/api/integrations")
async def list_integrations():
    integrations = await memory.get_integrations()
    return {"integrations": integrations}


@app.post("/api/integrations")
async def add_integration(
    req: IntegrationCreate, user: TokenPayload | None = Depends(get_current_user)
):
    int_id = await memory.save_integration(
        {
            "name": req.name,
            "type": req.type,
            "config": req.config,
            "enabled": req.enabled,
        }
    )
    return {"id": int_id, "name": req.name, "type": req.type}


@app.delete("/api/integrations/{int_id}")
async def delete_integration(int_id: str, user: TokenPayload | None = Depends(get_current_user)):
    import sqlite3

    conn = sqlite3.connect(memory.db_path)
    conn.execute("DELETE FROM integrations WHERE id = ?", (int_id,))
    conn.commit()
    conn.close()
    return {"deleted": int_id}


# === SECURITY STATUS ===


@app.get("/api/security/audit")
async def security_audit(user: TokenPayload = Depends(require_auth)):
    """View security audit log (admin only)"""
    if not user.has_role("admin"):
        raise HTTPException(403, "Admin access required")
    return wali.get_audit_summary()


@app.get("/api/security/permissions")
async def list_permissions(user: TokenPayload = Depends(require_auth)):
    """View agent permissions"""
    if not user.has_role("admin"):
        raise HTTPException(403, "Admin access required")
    return {"pending_approvals": izn.get_pending_approvals()}


# === SYSTEM STATUS ===


@app.get("/api/status")
async def system_status(detail: bool = True):
    """Full system status - Mizan dashboard; ``detail=false`` lists each agent
    in a few fields."""
    agent_stats = []
    for agent in active_agents.values():
        found = {**agent.to_dict(), "load": balancer.load_weights.get(agent.id, 0)}
        agent_stats.append(found if detail else _agent_summary(found))

    task_history = await memory.get_task_history(limit=10)

    return {
        "system": "MIZAN",
        "version": __version__,
        "status": "active",
        "timestamp": datetime.now(UTC).isoformat(),
        "agents": {
            "total": len(active_agents),
            "active": sum(1 for a in active_agents.values() if a.state == "acting"),
            "details": agent_stats,
        },
        "balancer": {
            "loads": balancer.load_weights,
        },
        "recent_tasks": task_history[:5],
        "connections": len(manager.connections),
        "sessions": len(active_sessions),
        "provider": get_provider_status(),
        "security": {
            "auth_enabled": True,
            "rate_limiting": True,
            "wali_active": True,
            "izn_active": True,
        },
    }


@app.get("/api/version")
async def version_info():
    """Version info and update check"""
    import subprocess

    result = {
        "version": __version__,
        "system": "MIZAN",
        "updates_available": 0,
        "latest_commit": None,
        "can_check": False,
    }

    try:
        # Check if we're in a git repo
        subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True,
            check=True,
            cwd=str(Path(__file__).resolve().parent.parent.parent),
        )
        result["can_check"] = True

        # Fetch latest (quick, non-blocking)
        subprocess.run(
            ["git", "fetch", "origin", "--quiet"],
            capture_output=True,
            timeout=10,
            cwd=str(Path(__file__).resolve().parent.parent.parent),
        )

        # Get current branch
        branch_result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parent.parent.parent),
        )
        branch = branch_result.stdout.strip() or "main"

        # Count commits behind
        behind_result = subprocess.run(
            ["git", "rev-list", "--count", f"HEAD..origin/{branch}"],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parent.parent.parent),
        )
        behind = int(behind_result.stdout.strip() or "0")
        result["updates_available"] = behind

        # Get latest remote commit message
        if behind > 0:
            log_result = subprocess.run(
                ["git", "log", "--oneline", f"origin/{branch}", "-1"],
                capture_output=True,
                text=True,
                cwd=str(Path(__file__).resolve().parent.parent.parent),
            )
            result["latest_commit"] = log_result.stdout.strip()[:80]

    except Exception:
        pass

    return result


# === HEALTH CHECK ===


@app.get("/api/health")
async def health_check(
    authorization: str | None = Header(None),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
):
    """Health for monitoring and Docker: ``status`` for everyone; the version,
    uptime and each check only for a signed-in administrator."""
    import time

    checks = {
        "database": False,
        "memory": False,
        "provider": False,
    }
    try:
        # Check database
        await memory.get_all_agents()
        checks["database"] = True
        checks["memory"] = True
    except Exception:
        pass
    try:
        provider_info = get_provider_status()
        checks["provider"] = provider_info.get("active") is not None
    except Exception:
        pass

    all_healthy = all(checks.values())
    status_code = 200 if all_healthy else 503
    user = auth.extract_token(authorization, x_api_key)  # optional: health is public
    if user is None or "admin" not in user.roles:
        return JSONResponse(
            status_code=status_code, content={"status": "ok" if all_healthy else "degraded"}
        )
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ok" if all_healthy else "degraded",
            "version": __version__,
            "uptime": int(time.time() - app.state.start_time)
            if hasattr(app.state, "start_time")
            else 0,
            "checks": checks,
        },
    )


# === PUBLIC API v1 (Revenue Tier) ===


@app.post("/api/v1/root-analyze")
async def api_v1_root_analyze(request: dict) -> dict:
    """Root, pattern (wazn), part of speech and meaning of each Arabic word,
    from the Quranic Arabic Corpus (the analyzer the chat uses too)."""
    text = request.get("text", "")
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(status_code=400, detail="text field required")
    if len(text) > 2000:
        raise HTTPException(status_code=413, detail="text is limited to 2000 characters")
    from tadbir import sarf

    try:
        corpus = await sarf.corpus()
    except sarf.Unavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    analysis = sarf.analyze(corpus, text)[:200]
    return {
        "text": text,
        "analysis": analysis,
        "word_count": len(analysis),
        "token_count": len(analysis),  # kept for older clients: one entry per word
        "source": sarf.ATTRIBUTION,
    }


@app.post("/api/v1/tokenize")
async def api_v1_tokenize(request: dict) -> dict:
    """Tokenize text into (root_id, pattern_id) tuples.

    Public API endpoint for Q28-aware tokenization.
    """
    text = request.get("text", "")
    if not text:
        raise HTTPException(status_code=400, detail="text field required")

    try:
        from ruh_model.tokenizer.bayan import BOS_ID, EOS_ID, BayanTokenizer

        tokenizer = BayanTokenizer()
        tokens = tokenizer.encode(text)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    # The begin and end markers are units of the model's input, not of the text:
    # "count" is the text's own units, so "كتب" counts 1, not 3.
    kinds = {BOS_ID: "begin", EOS_ID: "end"}
    listed = [{"root_id": r, "pattern_id": p, "kind": kinds.get(r, "unit")} for r, p in tokens]
    return {
        "text": text,
        "tokens": listed,
        "count": sum(1 for item in listed if item["kind"] == "unit"),
        "count_with_markers": len(listed),
        "unit": "word" if tokenizer.version == 1 else "byte",
    }


@app.post("/api/v1/q28-features")
async def api_v1_q28_features(request: dict) -> dict:
    """Extract Q28 articulatory features for any text.

    Maps input through IPA to Q28 articulatory coordinates.
    """
    text = request.get("text", "")
    lang = request.get("lang", "en")
    if not text:
        raise HTTPException(status_code=400, detail="text field required")

    try:
        from ruh_model.tokenizer.q28_articulatory import Q28ArticulatoryBasis

        q28 = Q28ArticulatoryBasis()
        coords = q28.text_to_q28(text, lang=lang)
        root_hint = q28.q28_to_root_hint(coords) if coords else ""
        return {
            "text": text,
            "lang": lang,
            "features": [c.tolist() for c in coords],
            "root_hint": root_hint,
            "phoneme_count": len(coords),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# === DOCTOR (SELF-HEALING DIAGNOSTIC) ===


@app.get("/api/doctor")
async def doctor_check():
    """
    Self-healing diagnostic — check system health and auto-fix issues.
    "And We send down of the Quran that which is a healing (shifa)" — 17:82
    """
    try:
        from doctor import report_to_dict, run_doctor

        report = run_doctor(auto_fix=False, check_only=True)
        return report_to_dict(report)
    except Exception as e:
        return {"healthy": False, "error": str(e)}


@app.post("/api/doctor/fix")
async def doctor_fix():
    """Run doctor with auto-fix enabled."""
    try:
        from doctor import report_to_dict, run_doctor

        report = run_doctor(auto_fix=True)
        return report_to_dict(report)
    except Exception as e:
        return {"healthy": False, "error": str(e)}


# === SETTINGS API ===


class SettingsUpdate(BaseModel):
    section: str
    provider: str | None = None
    api_key: str | None = None
    key: str | None = None
    value: Any = None


@app.get("/api/settings")
async def get_settings(user: TokenPayload | None = Depends(get_current_user)):
    """Get all settings (secrets masked)"""
    get_provider_status()

    # Build providers list
    providers = []
    from providers import COMPATIBLE_ENDPOINTS, compatible_key

    for name in ["anthropic", "openrouter", "openai", *COMPATIBLE_ENDPOINTS, "ollama"]:
        if name in COMPATIBLE_ENDPOINTS:
            key_set = bool(compatible_key(name))
        else:
            key_set = bool(os.getenv(f"{name.upper()}_API_KEY"))
        healthy = False
        try:
            health = await check_provider_health(name)
            healthy = health.get("healthy", False) if isinstance(health, dict) else False
        except Exception:
            pass
        providers.append({"name": name, "key_set": key_set, "healthy": healthy})

    # Build channels list
    channel_tokens = {
        "telegram": "TELEGRAM_BOT_TOKEN",
        "discord": "DISCORD_BOT_TOKEN",
        "whatsapp": "WHATSAPP_TOKEN",
        "slack": "SLACK_APP_TOKEN",
    }
    channels = []
    for ch_name, env_var in channel_tokens.items():
        has_token = bool(os.getenv(env_var))
        channels.append(
            {
                "name": ch_name,
                "enabled": has_token,
                "connected": False,
                "has_token": has_token,
            }
        )

    # Vault status
    vault_status = {"encrypted": False, "secrets_count": 0, "secret_names": []}
    try:
        from security.vault import SecretVault

        vault = SecretVault()
        vault_status = vault.get_status()
    except Exception:
        pass

    return {
        "providers": providers,
        "channels": channels,
        "security": {
            "rate_limit_per_minute": wali.config.rate_limit_per_minute,
            "jwt_expiry_hours": 24,
            "audit_enabled": True,
        },
        "memory": {
            "db_path": os.getenv("MIZAN_DB_PATH", "mizan_memory.db"),
            "consolidation_enabled": True,
        },
        "vault": vault_status,
        "version": __version__,
    }


@app.post("/api/settings")
async def update_settings(
    req: SettingsUpdate, user: TokenPayload | None = Depends(get_current_user)
):
    """Update a setting (API key, config value, etc.)"""
    actor = user.user_id if user else "admin"
    token_map = {
        "telegram": "TELEGRAM_BOT_TOKEN",
        "discord": "DISCORD_BOT_TOKEN",
        "whatsapp": "WHATSAPP_TOKEN",
        "slack": "SLACK_APP_TOKEN",
    }
    if req.section == "provider" and req.provider and req.api_key:
        env_key = f"{req.provider.upper()}_API_KEY"
        if env_key not in runtime_settings.BY_KEY:
            raise HTTPException(400, f"Unknown provider: {req.provider}")
        # Saved encrypted in the data volume, so it survives redeploys.
        try:
            change = runtime_settings.update({env_key: req.api_key}, actor)
        except ValueError:
            raise HTTPException(422, "Invalid API key value") from None
        if change.provider_changed:
            try:
                await _apply_provider_settings(False)
            except HTTPException:
                pass
        wali.audit.log(
            "settings_updated",
            {"section": "provider", "provider": req.provider, "field": "api_key"},
        )
        return {"status": "saved", "message": f"API key for {req.provider} saved"}

    elif req.section == "channel" and req.provider and req.api_key:
        env_key = token_map.get(req.provider, "")
        if not env_key:
            raise HTTPException(400, f"Unknown channel: {req.provider}")
        try:
            runtime_settings.update({env_key: req.api_key}, actor)
        except ValueError:
            raise HTTPException(422, "Invalid token value") from None
        return {"status": "saved", "message": f"Token for {req.provider} saved"}

    raise HTTPException(400, "Invalid settings update request")


# === CHANNEL MANAGEMENT ===

_CHANNEL_TOKENS = {
    "telegram": "TELEGRAM_BOT_TOKEN",
    "email": "MIZAN_EMAIL_PASSWORD",
    "discord": "DISCORD_BOT_TOKEN",
    "whatsapp": "WHATSAPP_TOKEN",
    "slack": "SLACK_APP_TOKEN",
}
_CHANNEL_NAMES = {
    "telegram": "Telegram",
    "email": "Email",
    "discord": "Discord",
    "whatsapp": "WhatsApp",
    "slack": "Slack",
}


def _channel_state(name: str) -> dict:
    """What a channel really is: MIZAN reports only what it runs.

    Web chat is always on. Telegram and email are connected only while their
    poller runs; the others are never reported as connected, whatever token
    is saved."""
    if name == "webchat":
        return {
            "id": "webchat",
            "type": "webchat",
            "name": "WebChat",
            "status": "connected",
            "running": True,
            "startable": False,
            "detail": "Built in.",
            "connected_users": len(manager.connections),
            "messages_processed": 0,
        }
    has_token = bool(os.getenv(_CHANNEL_TOKENS[name]))
    if name == "telegram" and _telegram_bot is not None and _telegram_bot.running:
        return {
            "id": name,
            "type": name,
            "name": _CHANNEL_NAMES[name],
            "status": "connected",
            "running": True,
            "startable": False,
            "has_token": True,
            "detail": "Running. Each user links their own Telegram account under Link Telegram.",
        }
    if name == "whatsapp" and _whatsapp_bot is not None:
        return {
            "id": name,
            "type": name,
            "name": _CHANNEL_NAMES[name],
            "status": "connected",
            "running": True,
            "startable": False,
            "has_token": True,
            "detail": (
                "Official Cloud API. Each user links their number under Link WhatsApp; "
                "it chats only where Meta's terms allow (EEA, Brazil, Türkiye) and sends "
                "notices elsewhere."
            ),
        }
    if name == "email" and _mail_bot is not None and _mail_bot.running:
        return {
            "id": name,
            "type": name,
            "name": _CHANNEL_NAMES[name],
            "status": "connected",
            "running": True,
            "startable": False,
            "has_token": True,
            "detail": "Reading MIZAN's mailbox. Each user links their own address under Link email.",
        }
    return {
        "id": name,
        "type": name,
        "name": _CHANNEL_NAMES[name],
        "status": "configured" if has_token else "unavailable",
        "running": False,
        "startable": False,
        "has_token": has_token,
        "detail": (
            "Token saved, but MIZAN does not run this channel yet."
            if has_token
            else "Not available yet: MIZAN does not run this channel."
        ),
        "connected_users": 0,
        "messages_processed": 0,
    }


def _known_channel(name: str) -> None:
    if name not in _CHANNEL_TOKENS:
        raise HTTPException(404, f"Unknown channel: {name}")


@app.post("/api/channels/{name}/start")
async def start_channel(name: str, user: TokenPayload | None = Depends(get_current_user)):
    """Starting an external channel is not available: none runs yet."""
    _known_channel(name)
    raise HTTPException(501, _channel_state(name)["detail"])


@app.post("/api/channels/{name}/stop")
async def stop_channel(name: str, user: TokenPayload | None = Depends(get_current_user)):
    _known_channel(name)
    raise HTTPException(501, _channel_state(name)["detail"])


@app.get("/api/channels/{name}/status")
async def channel_status(name: str):
    """The channel's real state (never 'connected' unless MIZAN runs it)."""
    _known_channel(name)
    state = _channel_state(name)
    return {
        "channel": name,
        "has_token": state["has_token"],
        "connected": state["running"],
        "status": state["status"],
        "detail": state["detail"],
    }


@app.post("/api/channels/{name}/test")
async def test_channel(name: str, user: TokenPayload | None = Depends(get_current_user)):
    _known_channel(name)
    raise HTTPException(501, _channel_state(name)["detail"])


@app.post("/api/shura")
async def shura_consult(req: ShuraRequest, user: TokenPayload | None = Depends(get_current_user)):
    """Multi-agent Shura consultation"""
    result = await shura.consult(req.question, req.context, list(active_agents.keys()))
    return result


# === TADBIR LEARNING (Majlis routing, Ta'allum wording) ===


def _no_run_active() -> bool:
    """No request is running on any agent, shared or private."""
    agents = [*active_agents.values(), *_user_agents.values()]
    return not any(getattr(agent, "_active_runs", 0) for agent in agents)


async def nawm_night() -> dict:
    """One night of Nawm (docs/automatic-learning.md): each person whose
    agents this process holds, each administrator (whose learning lives with
    the shared agents), and each other enabled person whose learning is on
    disk (no agent of theirs has run since the server started), has their
    lapsed lessons replayed under their own choices, while no request runs and
    within the night's budget."""
    from core.adaptive import AdaptiveStateStore
    from tadbir import nawm

    deadline = time.monotonic() + nawm.SECONDS
    people: list[tuple[str, Any]] = [
        (user_id, instance.adaptive) for (user_id, _), instance in list(_user_agents.items())
    ]
    accounts = [account for account in auth.list_users() if account.get("enabled", True)]
    template = _tadbir_coordinator()
    if template is not None:
        people += [
            (account["id"], template.adaptive)
            for account in accounts
            if "admin" in (account.get("roles") or [])
        ]
    for account in accounts:
        if "admin" in (account.get("roles") or []):
            continue
        # The same file a private agent's learning opens (``_private_memory``),
        # read without building the agents; ``seen`` skips it when one is held.
        kept = _private_dir(account["id"]) / "memory.db"
        if kept.is_file():
            people.append((account["id"], AdaptiveStateStore(str(kept))))
    counted = (
        "replayed", "confirmed", "dropped", "unsettled", "sought", "corroborated", "fitted",
        "shadow", "reader_learned",
    )  # fmt: skip
    totals = {"people": 0, **dict.fromkeys(counted, 0)}
    seen: set[tuple[str, str]] = set()
    for user_id, store in people:
        place = (user_id, str(getattr(store, "db_path", id(store))))
        if store is None or place in seen:
            continue
        seen.add(place)
        if time.monotonic() > deadline or not _no_run_active():
            break
        with await owner_consent(user_id):
            report = await nawm.night(store, user_id, deadline=deadline, idle=_no_run_active)
        totals["people"] += 1
        for key in counted:
            totals[key] += report[key]
    if totals["replayed"] or totals["sought"]:
        logger.info("Nawm: %s", totals)
    return totals


def _tadbir_coordinator():
    for agent in active_agents.values():
        if getattr(agent, "role", "") == "khalifah":
            return agent
    return next(iter(active_agents.values()), None)


@app.get("/api/tadbir/learning")
async def tadbir_learning(user: TokenPayload = Depends(require_auth)):
    """What MIZAN learned from its own verified work: who does which work, and your wording."""
    from tadbir import khatimah, majlis, sullam, taallum, talaqqi

    template = _tadbir_coordinator()
    if template is None:
        raise HTTPException(503, "No agents are running")
    # A user's learning lives with that user's own agents.
    coordinator = await chat_agent_for(user, template)
    return {
        "routing": majlis.report(coordinator),
        "wording": taallum.summary(coordinator.adaptive, user.user_id),
        "answers": talaqqi.summary(coordinator.adaptive, user.user_id),
        # Report only: Majlis stays the default until a vote beats it at equal budget.
        "ladder": await asyncio.to_thread(sullam.report, sorted(majlis.ROLE_FOR)),
        **await asyncio.to_thread(khatimah.summary, user.user_id),
    }


@app.get("/api/tadbir/teacher-calls")
async def tadbir_teacher_calls(
    days: int = Query(30, ge=1, le=365),
    scope: Literal["me", "all"] = Query(
        "me", description="Your own answers, or (administrators) every user's."
    ),
    user: TokenPayload = Depends(require_auth),
):
    """How often MIZAN answered with no hosted-model call, the goal's measure: the
    share overall, per day and per (family, language), each with a Wilson 95 %
    interval, and which Lisan tasks still called the model (docs/teacher-calls.md).
    Counts and shares only; no message content."""
    from api.usage import teacher_share

    if scope == "all" and not user.has_role("admin"):
        raise HTTPException(403, "Only administrators can see every user's answers")
    since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    rows = await memory.answer_usage(None if scope == "all" else user.user_id, since)
    return {"days": days, "scope": scope, **teacher_share(rows)}


@app.get("/api/tadbir/audit")
async def tadbir_audit(
    days: int = Query(90, ge=1, le=3650), user: TokenPayload = Depends(require_auth)
):
    """Tadqiq (admin): the blinded audit of answers MIZAN gave with no model call. Per
    family: audits, agreements and disagreements with the teacher, the disagreement
    rate with a Wilson 95 % interval, spend, and the disagreement monitor (its e-value,
    threshold and alarm). Counts only; no content (docs/tadqiq.md)."""
    from tadbir import tadqiq

    _require_admin(user)
    return await asyncio.to_thread(tadqiq.report, days)


@app.get("/api/tadrib")
async def tadrib_status(user: TokenPayload = Depends(require_auth)):
    """Tadrib (admin): MIZAN's own reader learning each consented message while it
    works: lessons learned, held out and turned down, the prequential log-loss of
    the fast and the slow copy, the safety check, seconds per lesson. Counts only;
    no words (docs/tadrib.md)."""
    from tadbir import tadrib

    _require_admin(user)
    return await asyncio.to_thread(tadrib.status)


@app.get("/api/tadrib/lessons")
async def tadrib_lessons(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: TokenPayload = Depends(require_auth),
):
    """Your lessons: the words of yours MIZAN's own reader learned or holds out as
    test, newest first (docs/tadrib.md)."""
    from tadbir.tadrib import store

    found, total = await asyncio.to_thread(store.listing, user.user_id, limit, offset)
    return {
        "lessons": [lesson.view() for lesson in found],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@app.delete("/api/tadrib/lessons/{digest}")
async def tadrib_reject(digest: str, user: TokenPayload = Depends(require_auth)):
    """Take one of your lessons back: it is deleted, and every version of the
    reader that learned it is dropped (the fast copy is rebuilt without it)."""
    import re

    from tadbir import tadrib

    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise HTTPException(422, "A lesson is named by its SHA-256 (64 hex digits)")
    if not await asyncio.to_thread(tadrib.reject, user.user_id, digest):
        raise HTTPException(404, "No such lesson")
    return {"rejected": digest}


class ReaderInstall(BaseModel):
    """A version of MIZAN's own reader trained and gated elsewhere, read from a
    Hugging Face model repository at a pinned commit."""

    repo: str = Field(..., min_length=3, max_length=120)
    revision: str = Field(..., pattern=r"^[0-9a-f]{40}$")
    weights: str = Field("reader-seed0.pt", min_length=1, max_length=200)
    report: str = Field("seed0.json", min_length=1, max_length=200)
    sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")


@app.post("/api/tadrib/reader")
async def tadrib_reader_install(req: ReaderInstall, user: TokenPayload = Depends(require_auth)):
    """Install (admin) a reader version trained and gated elsewhere as the base and
    current version: its weights and report are read from Hugging Face on the server
    (the owner's token), the weights must have the SHA-256 given and have been trained
    on this server's seeds, and the gate's fit is kept. ``MIZAN_RUH_READER`` is not
    changed: in ``shadow`` the reader is read and logged and never decides
    (docs/ruh-reader.md, "Installing a version on a server")."""
    import hashlib

    from knowledge import hf_hub
    from tadbir import ruh_reader

    _require_admin(user)
    if not ruh_reader.has_torch():
        raise HTTPException(503, "This server has no torch, so it cannot read with a reader")
    try:
        weights = await hf_hub.fetch(
            req.repo, req.weights, kind="models", revision=req.revision, max_bytes=64 << 20
        )
        report = await hf_hub.fetch(
            req.repo, req.report, kind="models", revision=req.revision, max_bytes=8 << 20
        )
    except hf_hub.HubError as exc:
        raise HTTPException(502, str(exc)) from None
    if hashlib.sha256(weights["bytes"]).hexdigest() != req.sha256:
        raise HTTPException(422, "The weights' SHA-256 is not the one given")
    if report.get("sampled"):
        raise HTTPException(422, "The report is larger than 8 MB")
    try:
        parsed = json.loads(report["bytes"])
    except ValueError:
        raise HTTPException(422, "The report is not JSON") from None
    folder = ruh_reader.home()
    folder.mkdir(parents=True, exist_ok=True)
    incoming = folder / f"incoming-{req.sha256[:16]}.pt"
    incoming.write_bytes(weights["bytes"])
    source = {
        "repo": req.repo,
        "revision": req.revision,
        "weights": req.weights,
        "report": req.report,
        "by": user.username or user.user_id,
    }
    try:
        installed = await asyncio.to_thread(ruh_reader.install_trained, incoming, parsed, source)
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(422, f"Not installed: {exc}") from None
    finally:
        incoming.unlink(missing_ok=True)
    return {**installed, "mode": ruh_reader.mode()}


@app.get("/api/tadbir/learning/live")
async def tadbir_learning_live(
    after: int = Query(0, ge=0), user: TokenPayload = Depends(require_auth)
):
    """What MIZAN learned from your work since ``after``, as it happens (Sijill).
    Administrators also see the notes meant for every administrator (an audit
    alarm, docs/tadqiq.md)."""
    from tadbir import sijill

    notes = sijill.since(user.user_id, after)
    if user.has_role("admin"):
        notes = sorted(notes + sijill.since(sijill.ADMINS, after), key=lambda note: note["seq"])
        notes = notes[-100:]
    return {"notes": notes, "last": notes[-1]["seq"] if notes else after}


@app.delete("/api/tadbir/learning/wording")
async def forget_tadbir_wording(user: TokenPayload = Depends(require_auth)):
    """Forget the wording MIZAN learned from this user's requests."""
    from tadbir import taallum

    template = _tadbir_coordinator()
    if template is None:
        raise HTTPException(503, "No agents are running")
    coordinator = await chat_agent_for(user, template)
    taallum.forget(coordinator.adaptive, user.user_id)
    return {"forgotten": True}


def _require_admin(user: TokenPayload) -> None:
    if not user.has_role("admin"):
        raise HTTPException(403, "Administrator role required")


class TalimExample(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)
    label: str = Field(..., min_length=1, max_length=40)


class TalimBatch(BaseModel):
    model: str = Field(..., max_length=60)
    examples: list[TalimExample] = Field(..., min_length=1, max_length=5000)
    source: str = Field("typed by an administrator", max_length=300)
    licence: str = Field("", max_length=120)
    language_name: str = Field("", max_length=60)


class TalimImport(BaseModel):
    model: str = Field(..., max_length=60)
    dataset: str = Field(..., max_length=200)
    config: str = Field("default", max_length=80)
    split: str = Field("train", max_length=40)
    revision: str = Field("", max_length=80)
    text_column: str = Field("text", max_length=80)
    label_column: str = Field("label", max_length=80)
    # Dataset label -> MIZAN label; rows whose label is not in the map are left out.
    label_map: dict[str, str] | None = None
    limit: int = Field(1000, ge=1, le=5000)
    licence: str = Field("", max_length=120)
    language_name: str = Field("", max_length=60)


@app.get("/api/tadbir/talim")
async def talim_view(user: TokenPayload = Depends(require_auth)):
    """Ta'lim (admin): what MIZAN can be taught, and every batch so far."""
    from tadbir import talim

    _require_admin(user)
    return await asyncio.to_thread(
        lambda: {
            "enabled": talim.enabled(),
            "models": talim.models(),
            "languages": talim.languages(),
            "batches": talim.batches(),
        }
    )


@app.post("/api/tadbir/talim")
async def talim_teach(req: TalimBatch, user: TokenPayload = Depends(require_auth)):
    """Teach a batch of examples; kept only if it does not make MIZAN worse at
    what it already knew (leave-one-out before and after, paired bootstrap)."""
    from tadbir import talim

    _require_admin(user)
    try:
        return await asyncio.to_thread(
            talim.teach,
            req.model,
            [(item.text, item.label) for item in req.examples],
            source=req.source,
            licence=req.licence,
            by=user.username or user.user_id,
            language_name=req.language_name,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@app.post("/api/tadbir/talim/import")
async def talim_import(req: TalimImport, user: TokenPayload = Depends(require_auth)):
    """Teach from a Hugging Face dataset split (read through the dataset viewer)."""
    from knowledge import hf_hub
    from tadbir import talim

    _require_admin(user)
    try:
        records = await hf_hub.rows(
            req.dataset, req.config, req.split, limit=req.limit, revision=req.revision
        )
    except hf_hub.HubError as exc:
        raise HTTPException(502, str(exc)) from None
    examples = talim.from_rows(records, req.text_column, req.label_column, req.label_map)
    if not examples:
        raise HTTPException(422, "No rows with those columns and labels")
    source = f"https://huggingface.co/datasets/{req.dataset} ({req.config}/{req.split}"
    source += f"@{req.revision})" if req.revision else ")"
    try:
        return await asyncio.to_thread(
            talim.teach,
            req.model,
            examples,
            source=source,
            licence=req.licence,
            by=user.username or user.user_id,
            language_name=req.language_name,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@app.delete("/api/tadbir/talim/{batch}")
async def talim_undo(batch: str, user: TokenPayload = Depends(require_auth)):
    from tadbir import talim

    _require_admin(user)
    if not await asyncio.to_thread(talim.undo, batch, user.username or user.user_id):
        raise HTTPException(404, "No kept batch with that id")
    return {"undone": batch}


@app.post("/api/tadbir/muhasaba")
async def run_muhasaba(hours: float = 24, user: TokenPayload = Depends(require_auth)):
    """Run MIZAN's self-review now (admin): re-check recent unverified answers."""
    from tadbir import muhasaba

    _require_admin(user)
    return await muhasaba.run(memory, hours=max(0.1, min(hours, 24 * 30)))


@app.get("/api/tadbir/programs")
async def kept_programs(user: TokenPayload = Depends(require_auth)):
    """The programs MIZAN verified for you and re-runs instead of asking the model (Hifz)."""
    from tadbir import hifz

    template = _tadbir_coordinator()
    if template is None:
        raise HTTPException(503, "No agents are running")
    coordinator = await chat_agent_for(user, template)
    return hifz.summary(coordinator.adaptive, user.user_id)


@app.delete("/api/tadbir/programs")
async def forget_programs(user: TokenPayload = Depends(require_auth)):
    from tadbir import hifz

    template = _tadbir_coordinator()
    if template is None:
        raise HTTPException(503, "No agents are running")
    coordinator = await chat_agent_for(user, template)
    hifz.forget(coordinator.adaptive, user.user_id)
    return {"forgotten": True}


@app.delete("/api/tadbir/answers")
async def forget_answers(user: TokenPayload = Depends(require_auth)):
    """Forget every answer MIZAN kept to give you again without the model (Talaqqi)."""
    from tadbir import talaqqi

    template = _tadbir_coordinator()
    if template is None:
        raise HTTPException(503, "No agents are running")
    coordinator = await chat_agent_for(user, template)
    talaqqi.forget(coordinator.adaptive, user.user_id)
    return {"forgotten": True}


@app.get("/api/tadbir/lessons")
async def repair_lessons(user: TokenPayload = Depends(require_auth)):
    """Lessons MIZAN kept from its own verified repairs of your code (Tajriba)."""
    from tadbir import tajriba

    template = _tadbir_coordinator()
    if template is None:
        raise HTTPException(503, "No agents are running")
    coordinator = await chat_agent_for(user, template)
    return tajriba.summary(coordinator.adaptive, user.user_id)


@app.delete("/api/tadbir/lessons")
async def forget_repair_lessons(user: TokenPayload = Depends(require_auth)):
    from tadbir import tajriba

    template = _tadbir_coordinator()
    if template is None:
        raise HTTPException(503, "No agents are running")
    coordinator = await chat_agent_for(user, template)
    tajriba.forget(coordinator.adaptive, user.user_id)
    return {"forgotten": True}


@app.get("/api/tadbir/harness")
async def harness_report(user: TokenPayload = Depends(require_auth)):
    """Lisan's instruction versions (Tajdid) and the models chosen for code work (Wazn), admin."""
    from tadbir import tajdid, wazn

    _require_admin(user)
    return {
        "evolution": tajdid.enabled(),
        "instructions": tajdid.report(),
        "models": wazn.models(),
        "readiness": wazn.readiness(),
        "routing": wazn.report(),
    }


@app.delete("/api/tadbir/harness/{task}")
async def reset_harness(task: str, user: TokenPayload = Depends(require_auth)):
    """Return one kind of work to MIZAN's built-in instruction (admin)."""
    from tadbir import tajdid

    _require_admin(user)
    if task not in tajdid.CONTRACTS:
        raise HTTPException(404, "Unknown kind of work")
    tajdid.reset(task)
    return {"reset": task}


# === DEBUG MODE (Muqabala: the base model alone vs MIZAN) ===


class DebugCompareRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=20000)
    agent_id: str | None = Field(None, max_length=100)
    # An existing chat whose earlier turns both arms receive; nothing is saved to it.
    session_id: str | None = Field(None, min_length=1, max_length=100)
    workspace_id: str | None = Field(None, min_length=1, max_length=100)
    timezone: str | None = Field(None, max_length=64, pattern=r"^[A-Za-z0-9_+\-/]+$")
    # auto: MIZAN runs the tools it chooses (sandboxed code, project edits); plan: read-only.
    permission_mode: str = Field("auto", pattern=r"^(auto|plan)$")


def _debug_access(user: TokenPayload) -> None:
    from tadbir import muqabala

    if not muqabala.allowed(user.has_role("admin")):
        raise HTTPException(403, "Debug mode is not enabled for this account")


@app.get("/api/debug/status")
async def debug_status(user: TokenPayload = Depends(require_auth)):
    from tadbir import muqabala

    return {"enabled": muqabala.allowed(user.has_role("admin")), "access": muqabala.access()}


@app.post("/api/debug/compare")
async def debug_compare(req: DebugCompareRequest, user: TokenPayload = Depends(require_auth)):
    """One message to the base model alone and to MIZAN, with MIZAN's full trace and checks."""
    from security.approvals import ApprovalContext, bind_approvals
    from tadbir import muqabala
    from tadbir.waqt import bind_timezone

    _debug_access(user)
    workspace_context: Any = None
    if req.workspace_id:
        try:
            from workspace import context as selected_workspace_context
        except ImportError as exc:
            raise HTTPException(503, "Coding workspaces are not available") from exc
        workspace_context = selected_workspace_context
        workspace_context.authorize_owned_workspace(req.workspace_id, user.user_id)
    agent_id = req.agent_id or next(iter(active_agents), None)
    if agent_id not in active_agents:
        raise HTTPException(503, "No agents available")
    agent = await chat_agent_for(user, active_agents[agent_id])
    history: list[dict] = []
    if req.session_id:
        # A new id starts an empty conversation of the caller's, as for a chat.
        await authorize_session(req.session_id, user, create=True)
        stored = await memory.get_messages(req.session_id, limit=50)
        history = [
            {"role": m["role"], "content": m["content"]}
            for m in stored
            if m["role"] in {"user", "assistant"} and str(m["content"]).strip()
        ]
    context = {
        "history": history,
        "user_preferences": await memory.get_chat_preferences(user.user_id),
        **({"workspace_id": req.workspace_id} if req.workspace_id else {}),
    }
    approvals = ApprovalContext(user.user_id, f"debug-{uuid.uuid4().hex}", req.permission_mode)
    workspace_binding = (
        workspace_context.bind_workspace(req.workspace_id) if workspace_context else None
    )
    try:
        with bind_approvals(approvals), bind_timezone(req.timezone):
            run = await muqabala.compare(agent, req.prompt, context, history)
    finally:
        if workspace_context and workspace_binding is not None:
            workspace_context.reset_workspace(workspace_binding)
    run["permission_mode"] = req.permission_mode
    try:
        await muqabala.save(user.user_id, run)
    except Exception:  # noqa: BLE001 - the comparison is still returned
        logger.warning("Debug comparison could not be saved")
    return run


@app.get("/api/debug/runs")
async def debug_runs(user: TokenPayload = Depends(require_auth)):
    from tadbir import muqabala

    _debug_access(user)
    return {"runs": await muqabala.runs(user.user_id)}


@app.get("/api/debug/runs/{run_id}")
async def debug_run(run_id: str, user: TokenPayload = Depends(require_auth)):
    from tadbir import muqabala

    _debug_access(user)
    if len(run_id) != 32 or not all(char in "0123456789abcdef" for char in run_id):
        raise HTTPException(400, "Invalid run id")
    run = await muqabala.get(user.user_id, run_id)
    if run is None:
        raise HTTPException(404, "Comparison not found")
    return run


@app.delete("/api/debug/runs")
async def clear_debug_runs(user: TokenPayload = Depends(require_auth)):
    from tadbir import muqabala

    _debug_access(user)
    await muqabala.clear(user.user_id)
    return {"cleared": True}


# === IMTIHAN (AGI test: the base model alone vs MIZAN, scored by rule) ===


class ImtihanRunRequest(BaseModel):
    blocks: list[str] | None = Field(None, max_length=20)
    repeats: int = Field(1, ge=1, le=3)
    agent_id: str | None = Field(None, max_length=100)


@app.get("/api/imtihan/tasks")
async def imtihan_tasks(user: TokenPayload = Depends(require_auth)):
    from imtihan import runner

    _require_admin(user)
    return {
        "blocks": runner.catalog(),
        "tasks": [
            {
                "id": task["id"],
                "block": task["block"],
                "prompt": str(task.get("prompt") or task.get("instructions") or "")[:400],
                "agentic": "instructions" in task,
                "source": task.get("source"),
            }
            for task in runner.load_tasks()
        ],
    }


@app.post("/api/imtihan/run")
async def imtihan_run(req: ImtihanRunRequest, user: TokenPayload = Depends(require_auth)):
    """Start the AGI test in the background: every task to the base model and to MIZAN."""
    from imtihan import runner

    _require_admin(user)
    known = {entry["block"] for entry in runner.catalog()}
    if req.blocks and not set(req.blocks) <= known:
        raise HTTPException(400, f"Unknown blocks: {sorted(set(req.blocks) - known)}")
    agent = active_agents.get(req.agent_id) if req.agent_id else _tadbir_coordinator()
    if agent is None:
        raise HTTPException(503, "No agents available")
    try:
        return runner.start(agent, owner=user.user_id, blocks=req.blocks, repeats=req.repeats)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.get("/api/imtihan/runs")
async def imtihan_runs(user: TokenPayload = Depends(require_auth)):
    from imtihan import runner, scorecard

    _require_admin(user)
    found = await runner.runs()
    published = await asyncio.to_thread(scorecard.published_ids)
    return {"runs": [{**run, "published": run["id"] in published} for run in found]}


@app.get("/api/imtihan/runs/{run_id}")
async def imtihan_run_detail(run_id: str, user: TokenPayload = Depends(require_auth)):
    from imtihan import runner

    _require_admin(user)
    run = await runner.get(run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    if run.get("status") != "complete":
        return run
    from imtihan import quwa

    # The faculty profile is read against the human panel as it is now.
    return await asyncio.to_thread(quwa.with_panel, run)


@app.post("/api/imtihan/runs/{run_id}/cancel")
async def imtihan_cancel(run_id: str, user: TokenPayload = Depends(require_auth)):
    from imtihan import runner

    _require_admin(user)
    if not runner.cancel(run_id):
        raise HTTPException(404, "No running test with that id")
    return {"cancelled": True}


@app.post("/api/imtihan/runs/{run_id}/publish")
async def imtihan_publish(run_id: str, user: TokenPayload = Depends(require_auth)):
    """Publish a finished run's aggregate report on the public reliability page."""
    from imtihan import runner, scorecard

    _require_admin(user)
    run = await runner.get(run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    from imtihan import quwa

    try:
        entry = await asyncio.to_thread(lambda: scorecard.publish(quwa.with_panel(run)))
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    wali.audit.log("scorecard_published", {"run": run_id, "by": user.user_id})
    return entry


@app.delete("/api/imtihan/runs/{run_id}/publish")
async def imtihan_unpublish(run_id: str, user: TokenPayload = Depends(require_auth)):
    from imtihan import scorecard

    _require_admin(user)
    return {"removed": await asyncio.to_thread(scorecard.unpublish, run_id)}


class ImtihanPanelAnswers(BaseModel):
    person: str = Field(..., min_length=1, max_length=40, pattern=r"^[A-Za-z0-9_.-]+$")
    answers: dict[str, str] = Field(..., min_length=1, max_length=300)


@app.get("/api/imtihan/panel")
async def imtihan_panel(user: TokenPayload = Depends(require_auth)):
    """The human panel (imtihan/quwa.py): the text items people can answer, and who has."""
    from imtihan import quwa

    _require_admin(user)
    return {
        "faculties": quwa.faculties(),
        "tasks": await asyncio.to_thread(quwa.panel_tasks),
        "people": await asyncio.to_thread(quwa.people),
    }


@app.post("/api/imtihan/panel")
async def imtihan_panel_answer(
    req: ImtihanPanelAnswers, user: TokenPayload = Depends(require_auth)
):
    """A panel member's answers (under a pseudonym), scored by the items' own rules."""
    from imtihan import quwa

    _require_admin(user)
    if any(len(answer) > 4000 for answer in req.answers.values()):
        raise HTTPException(422, "An answer is longer than 4000 characters")
    scored = await quwa.record(req.person, req.answers, by=user.user_id)
    return {"person": req.person, "scored": scored}


@app.delete("/api/imtihan/panel/{person}")
async def imtihan_panel_forget(person: str, user: TokenPayload = Depends(require_auth)):
    """Erase every answer a panel member gave."""
    from imtihan import quwa

    _require_admin(user)
    return {"removed": await asyncio.to_thread(quwa.forget, person)}


class ImtihanPanelInvite(BaseModel):
    person: str | None = Field(None, min_length=1, max_length=40, pattern=r"^[A-Za-z0-9_.-]+$")
    days: float = Field(14, gt=0, le=60)


@app.post("/api/imtihan/panel/invites")
async def imtihan_panel_invite(req: ImtihanPanelInvite, user: TokenPayload = Depends(require_auth)):
    """A link one person opens to answer the panel's items with no account. The
    code is shown once: only its SHA-256 is kept."""
    from imtihan import quwa

    _require_admin(user)
    made = await asyncio.to_thread(quwa.invite, req.person, user.user_id, req.days)
    return {**made, "path": f"/panel/{made['code']}"}


@app.get("/api/imtihan/panel/invites")
async def imtihan_panel_invites(user: TokenPayload = Depends(require_auth)):
    """Every invite link (never its code), whether it is active and how much was answered."""
    from imtihan import quwa

    _require_admin(user)
    return {"invites": await asyncio.to_thread(quwa.invites)}


@app.delete("/api/imtihan/panel/invites/{invite_id}")
async def imtihan_panel_revoke(invite_id: str, user: TokenPayload = Depends(require_auth)):
    """Close an invite link; the answers given through it are kept."""
    from imtihan import quwa

    _require_admin(user)
    if not await asyncio.to_thread(quwa.revoke, invite_id[:32]):
        raise HTTPException(404, "No invite with that id")
    return {"revoked": invite_id}


class PanelSelfAnswers(BaseModel):
    answers: dict[str, str] = Field(..., min_length=1, max_length=300)


async def _invited(code: str, request: Request) -> dict:
    from imtihan import quwa

    _open_rate_limit(request)
    found: dict | None = await asyncio.to_thread(quwa.invited, code)
    if found is None:
        raise HTTPException(404, "This link is not valid or has expired")
    return found


@app.get("/api/public/panel/{code}")
async def public_panel(code: str, request: Request):
    """The items an invited person answers, and which they already have (no verdicts)."""
    from imtihan import quwa

    found = await _invited(code, request)
    return {
        "person": found["person"],
        "expires": found["expires"],
        "faculties": quwa.faculties(),
        "tasks": await asyncio.to_thread(quwa.panel_tasks),
        "answered": await asyncio.to_thread(quwa.answered_by, found["person"]),
    }


@app.post("/api/public/panel/{code}")
async def public_panel_answer(code: str, req: PanelSelfAnswers, request: Request):
    """An invited person's answers: scored by the items' own rules and kept. The
    first answer to an item is final and no verdict is returned."""
    from imtihan import quwa

    found = await _invited(code, request)
    if any(len(answer) > 4000 for answer in req.answers.values()):
        raise HTTPException(422, "An answer is longer than 4000 characters")
    saved = await quwa.record(found["person"], req.answers, by=f"invite:{found['id']}", final=True)
    return {
        "saved": len(saved),
        "answered": await asyncio.to_thread(quwa.answered_by, found["person"]),
    }


def _open_rate_limit(request: Request) -> None:
    client = request.client.host if request.client else "unknown"
    found = wali.check_rate_limit(f"public:{client}")
    if not found["allowed"]:
        raise HTTPException(
            429,
            "Too many requests; try again in a minute",
            headers={
                "Retry-After": str(found["retry_after"]),
                "RateLimit-Limit": str(found["limit"]),
                "RateLimit-Remaining": "0",
            },
        )


@app.get("/api/public/whatsapp")
async def whatsapp_verify(request: Request):
    """Meta's webhook subscription check (hub.mode, hub.verify_token, hub.challenge)."""
    from gateway import whatsapp

    _open_rate_limit(request)
    bot = _whatsapp_bot
    answer = (
        whatsapp.challenge(dict(request.query_params), bot.config.verify_token) if bot else None
    )
    if answer is None:
        raise HTTPException(403, "Verification failed")
    return Response(content=answer, media_type="text/plain")


@app.post("/api/public/whatsapp")
async def whatsapp_webhook(request: Request):
    """Meta's webhook: accepted only when signed with the app secret."""
    from gateway import whatsapp

    bot = _whatsapp_bot
    if bot is None:
        raise HTTPException(404, "MIZAN is not on WhatsApp")
    if int(request.headers.get("content-length") or 0) > 1_000_000:
        raise HTTPException(413, "Too large")
    body = await request.body()
    if len(body) > 1_000_000 or not whatsapp.signed(
        body, request.headers.get("x-hub-signature-256", ""), bot.config.app_secret
    ):
        _open_rate_limit(request)  # unsigned callers are limited; Meta is not
        raise HTTPException(401, "Not signed by Meta")
    try:
        payload = json.loads(body)
    except ValueError:
        raise HTTPException(400, "Not JSON") from None
    return {"accepted": bot.accept(payload) if isinstance(payload, dict) else 0}


@app.get("/api/public/reliability")
async def public_reliability(request: Request):
    """MIZAN's published AGI-test results (aggregates only) and its signed Sakk roots."""
    from imtihan import scorecard

    _open_rate_limit(request)
    return await asyncio.to_thread(scorecard.view)


@app.get("/api/public/reliability/{run_id}")
async def public_reliability_run(run_id: str, request: Request):
    from imtihan import scorecard

    _open_rate_limit(request)
    entry = await asyncio.to_thread(scorecard.get, run_id[:64])
    if entry is None:
        raise HTTPException(404, "No published result with that id")
    return entry


@app.get("/api/public/sakk")
async def public_sakk(request: Request):
    """MIZAN's receipt-signing public key and its recent signed daily roots."""
    from security import sakk

    _open_rate_limit(request)
    store = sakk.store()
    return {"public_key": store.public_key(), "roots": store.roots(30)}


# === SAKK (صك) — tamper-evident action receipts ===


async def _sakk_daily() -> None:
    """Sign a checkpoint of every chain's head: each day, and within ten
    minutes of any chain moving (nothing is signed when nothing changed)."""
    from security import sakk

    while True:
        try:
            await asyncio.to_thread(sakk.store().sign_day)
        except Exception:  # noqa: BLE001 - signing is retried at the next check
            logger.warning("[SAKK] checkpoint not signed", exc_info=True)
        await asyncio.sleep(600)


@app.get("/api/sakk")
async def sakk_receipts(
    limit: int = 50, before: int | None = None, user: TokenPayload = Depends(require_auth)
):
    """Your action receipts, newest first: tool, outcome, time and chain hash."""
    from security import sakk

    store = sakk.store()
    return {
        "receipts": await asyncio.to_thread(store.receipts, user.user_id, limit, before),
        "public_key": await asyncio.to_thread(store.public_key),
    }


@app.get("/api/sakk/verify")
async def sakk_verify(user: TokenPayload = Depends(require_auth)):
    """Recompute your whole chain and say whether every receipt still holds."""
    from security import sakk

    return await asyncio.to_thread(sakk.store().verify, user.user_id)


@app.get("/api/sakk/verify/all")
async def sakk_verify_all(user: TokenPayload = Depends(require_auth)):
    from security import sakk

    _require_admin(user)
    store = sakk.store()

    def check() -> dict:
        results = {owner: store.verify(owner) for owner in store.owners()}
        return {
            "chains": len(results),
            "ok": all(item["ok"] for item in results.values()),
            "broken": {owner: item for owner, item in results.items() if not item["ok"]},
        }

    return await asyncio.to_thread(check)


@app.get("/api/sakk/export")
async def sakk_export(user: TokenPayload = Depends(require_auth)):
    """Your chain, your digest key and MIZAN's signed proof, to check anywhere
    with scripts/verify_sakk.py."""
    from security import sakk

    data = await asyncio.to_thread(sakk.store().export, user.user_id)
    return JSONResponse(
        data, headers={"Content-Disposition": 'attachment; filename="mizan-sakk.json"'}
    )


class Arc3PlayRequest(BaseModel):
    game_id: str | None = Field(None, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    max_actions: int = Field(400, ge=10, le=2000)


@app.get("/api/imtihan/arc3")
async def imtihan_arc3_status(user: TokenPayload = Depends(require_auth)):
    from imtihan.games import arc3

    _require_admin(user)
    return {"configured": arc3.configured(), "api": arc3.BASE_URL}


@app.post("/api/imtihan/arc3")
async def imtihan_arc3_play(req: Arc3PlayRequest, user: TokenPayload = Depends(require_auth)):
    """MIZAN's explorer plays one official ARC-AGI-3 game (needs ARC_API_KEY)."""
    import httpx

    from imtihan.games import arc3

    _require_admin(user)
    if not arc3.configured():
        raise HTTPException(409, "Set ARC_API_KEY to play ARC-AGI-3 games")
    try:
        return await arc3.play(req.game_id, req.max_actions)
    except (arc3.Arc3Error, httpx.HTTPError) as exc:
        raise HTTPException(502, str(exc)[:300]) from exc


# === AUTOMATION (Qadr) ===


@app.get("/api/automation/jobs")
async def list_jobs(user: TokenPayload | None = Depends(get_current_user)):
    """List all scheduled jobs"""
    return {"jobs": scheduler.list_jobs()}


@app.post("/api/automation/jobs")
async def create_job(
    req: ScheduleJobRequest, user: TokenPayload | None = Depends(get_current_user)
):
    """Create a new scheduled job"""
    job = await scheduler.add_job(req.name, req.cron, req.task, req.agent_id)
    wali.audit.log("job_created", {"name": req.name, "cron": req.cron})
    return job.to_dict()


@app.delete("/api/automation/jobs/{job_id}")
async def delete_job(job_id: str, user: TokenPayload | None = Depends(get_current_user)):
    """Remove a scheduled job"""
    removed = await scheduler.remove_job(job_id)
    if not removed:
        raise HTTPException(404, "Job not found")
    return {"deleted": job_id}


@app.get("/api/automation/webhooks")
async def list_webhooks(user: TokenPayload | None = Depends(get_current_user)):
    """List all webhook triggers"""
    return {"webhooks": trigger_manager.list_webhooks()}


@app.post("/api/automation/webhooks")
async def create_webhook(
    req: WebhookCreateRequest, user: TokenPayload | None = Depends(get_current_user)
):
    """Create a new webhook trigger"""
    webhook = await trigger_manager.register_webhook(
        req.name, req.task_template, req.agent_id, req.secret
    )
    wali.audit.log("webhook_created", {"name": req.name})
    return webhook.to_dict()


@app.post("/api/automation/webhooks/{webhook_id}/trigger")
async def trigger_webhook(webhook_id: str, request: Request):
    """Handle an incoming webhook trigger"""
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    result = await trigger_manager.handle_webhook(webhook_id, payload)
    return result


# === SKILLS (Hikmah) ===


@app.get("/api/skills")
async def list_skills(user: TokenPayload | None = Depends(get_current_user)):
    """List all available skills"""
    return {"skills": skill_registry.list_skills()}


@app.post("/api/skills/install")
async def install_skill(
    req: SkillInstallRequest, user: TokenPayload | None = Depends(get_current_user)
):
    """Install a skill"""
    result = skill_registry.install_skill(req.name)
    if result:
        wali.audit.log("skill_installed", {"name": req.name})
        return {"installed": True, "name": req.name}
    raise HTTPException(404, "Skill not found")


@app.post("/api/skills/uninstall")
async def uninstall_skill(
    req: SkillInstallRequest, user: TokenPayload | None = Depends(get_current_user)
):
    """Uninstall a skill"""
    result = skill_registry.uninstall_skill(req.name)
    if result:
        wali.audit.log("skill_uninstalled", {"name": req.name})
        return {"uninstalled": True, "name": req.name}
    raise HTTPException(404, "Skill not found")


class SkillExecuteRequest(BaseModel):
    model_config = {"extra": "allow"}

    skill: str = Field(..., min_length=1, max_length=200)
    action: str | None = None


@app.post("/api/skills/execute")
async def execute_skill(
    req: SkillExecuteRequest, user: TokenPayload | None = Depends(get_current_user)
):
    """Execute a skill action — routes to the appropriate built-in skill"""
    skill = skill_registry.get_skill(req.skill)
    if not skill:
        raise HTTPException(404, f"Skill '{req.skill}' not found")

    # Build params from request (exclude 'skill' key)
    params = req.model_dump(exclude={"skill"})
    try:
        result = await skill.execute(params)
        return result
    except Exception as e:
        raise HTTPException(500, f"Skill execution error: {str(e)}") from e


# === GATEWAY (Bab) ===


@app.get("/api/gateway/status")
async def gateway_status(user: TokenPayload | None = Depends(get_current_user)):
    """Get gateway status"""
    return {
        "status": "online",
        "channels": 1,  # WebChat always active
        "sessions": len(active_sessions),
        "connections": len(manager.connections),
    }


@app.get("/api/gateway/channels")
async def list_channels(user: TokenPayload | None = Depends(get_current_user)):
    """Every channel with its real state."""
    return {"channels": [_channel_state(name) for name in ("webchat", *_CHANNEL_TOKENS)]}


# ===== NAFS 7-LEVEL ENDPOINTS =====


@app.get("/api/nafs/tiers")
async def get_nafs_tiers():
    """Get all 7 Nafs tiers and their permission mappings."""
    tiers = []
    for level in range(1, 8):
        tiers.append(izn.get_nafs_tier_info(level))
    return {"tiers": tiers}


@app.get("/api/nafs/{agent_id}")
async def get_nafs_status(agent_id: str):
    """Get 7-level Nafs status for an agent."""
    if agent_id not in active_agents:
        raise HTTPException(404, "Agent not found")
    agent = active_agents[agent_id]
    names = {
        1: "Ammara",
        2: "Lawwama",
        3: "Mulhama",
        4: "Mutmainna",
        5: "Radiya",
        6: "Mardiyya",
        7: "Kamila",
    }
    return {
        "agent_id": agent_id,
        "nafs_level": agent.nafs_level,
        "nafs_name": names.get(agent.nafs_level, "Ammara"),
        "success_rate": round(agent.success_rate, 3),
        "total_tasks": agent.total_tasks,
        "ruh_energy": agent.ruh.get_state(agent_id).energy,
        "ihsan_eligible": agent.ihsan.is_eligible(agent.nafs_level),
        "permissions": izn.check_nafs_permission(agent.nafs_level, "bash"),
    }


@app.get("/api/nafs/{agent_id}/faculties")
async def get_agent_faculties(agent_id: str):
    """Get al-Insan faculty state for an agent: Hikmah wisdom and principles.

    Basira (insight) and Hawa (restraint) are per-task signals returned in the
    /api/chat and task results; this endpoint surfaces the persistent faculties.
    """
    if agent_id not in active_agents:
        raise HTTPException(404, "Agent not found")
    agent = active_agents[agent_id]
    hikmah_stats = {}
    principles = []
    try:
        hikmah_stats = agent.hikmah_engine.stats()
        principles = [p.to_dict() for p in agent.hikmah_engine.distill()[:10]]
    except Exception:
        pass
    return {
        "agent_id": agent_id,
        "hikmah": hikmah_stats,
        "applicable_principles": principles,
    }


# ===== YAQIN CERTAINTY ENDPOINTS =====


class YaqinTagRequest(BaseModel):
    content: str
    source: str = "inference"  # inference | observation | proven
    confidence: float = 0.5
    pattern_id: str = ""


@app.post("/api/yaqin/tag")
async def tag_with_yaqin(req: YaqinTagRequest):
    """Tag a piece of knowledge with its Yaqin certainty level."""
    if req.source == "proven":
        tag = yaqin_engine.tag_proven(
            req.content, req.pattern_id or "api", confidence=req.confidence
        )
    elif req.source == "observation":
        tag = yaqin_engine.tag_observation(req.content, confidence=req.confidence)
    else:
        tag = yaqin_engine.tag_inference(req.content, confidence=req.confidence)
    return {"tag": tag.to_dict()}


@app.get("/api/yaqin/stats")
async def yaqin_stats():
    """Get Yaqin engine statistics."""
    return {"stats": yaqin_engine.stats()}


# ===== COGNITIVE METHOD ENDPOINTS =====


class CognitiveRouteRequest(BaseModel):
    query: str
    context: str = ""


@app.post("/api/cognitive/route")
async def route_cognitive_method(req: CognitiveRouteRequest):
    """Route a query to the best Quranic cognitive method."""
    method = select_method(req.query)
    return {
        "method": method.value,
        "description": {
            "tafakkur": "Deep analytical thinking",
            "tadabbur": "Contextual contemplation",
            "istidlal": "Logical deduction",
            "qiyas": "Analogical reasoning",
            "ijma": "Consensus building",
        }.get(method.value, "Unknown"),
    }


# ===== QALB EMOTIONAL INTELLIGENCE ENDPOINTS =====


class QalbAnalyzeRequest(BaseModel):
    message: str
    user_id: str = ""


@app.post("/api/qalb/analyze")
async def analyze_emotion(req: QalbAnalyzeRequest, user: TokenPayload = Depends(require_auth)):
    """Analyze emotional state from a message."""
    reading = qalb_engine.analyze(req.message)
    if req.user_id and req.user_id != user.user_id and not user.has_role("admin"):
        raise HTTPException(403, "Cannot modify another user's emotional history")
    qalb_engine.record(req.user_id or user.user_id, reading)
    return {"reading": reading.to_dict()}


@app.get("/api/qalb/trend/{user_id}")
async def emotional_trend(user_id: str, user: TokenPayload = Depends(require_auth)):
    """Get emotional trend for a user."""
    if user_id != user.user_id and not user.has_role("admin"):
        raise HTTPException(403, "Cannot read another user's emotional history")
    trend = qalb_engine.get_trend(user_id)
    return {"trend": trend}


# ===== FEDERATION ENDPOINTS =====


@app.get("/api/federation/status")
async def federation_status():
    """Get federation network status."""
    # Register active agents with federation
    for aid, agent in active_agents.items():
        federation.register_agent(
            aid,
            agent.name,
            agent.role,
            list(agent.tools.keys()),
            agent.nafs_level,
            agent.success_rate,
        )
    return federation.get_status()


class DiscoverRequest(BaseModel):
    capabilities: list[str] = []


@app.post("/api/federation/discover")
async def discover_agents(req: DiscoverRequest):
    """Discover agents by capability."""
    matches = federation.discover(req.capabilities)
    return {"agents": [m.to_dict() for m in matches]}


class FederationTaskRequest(BaseModel):
    task: str = Field(..., description="Task to route to best agent")
    session_id: str = ""


@app.post("/api/federation/route")
async def federation_route_task(
    req: FederationTaskRequest,
    background_tasks: BackgroundTasks,
    user: TokenPayload | None = Depends(get_current_user),
):
    """Route a task to the best agent via Federation intelligence.

    Uses agent capabilities, success rates, and energy levels to select
    the optimal agent, then executes the task.
    """
    # Register all agents with federation first
    for aid, agent in active_agents.items():
        federation.register_agent(
            aid,
            agent.name,
            agent.role,
            list(agent.tools.keys()),
            agent.nafs_level,
            agent.success_rate,
        )

    # Discover best agent for this task
    task_lower = req.task.lower()
    capabilities = []
    if any(w in task_lower for w in ["code", "script", "python"]):
        capabilities = ["python_exec", "write_file", "bash"]
    elif any(w in task_lower for w in ["search", "browse", "web"]):
        capabilities = ["web_search", "web_browse", "http_get"]
    elif any(w in task_lower for w in ["analyze", "research"]):
        capabilities = ["web_search", "read_file", "python_exec"]
    else:
        capabilities = ["bash", "http_get"]

    matches = federation.discover(capabilities)
    if not matches:
        # Fallback to first available agent
        agent_id = list(active_agents.keys())[0] if active_agents else None
    else:
        agent_id = matches[0].agent_id

    if not agent_id or agent_id not in active_agents:
        raise HTTPException(503, "No suitable agent found")

    agent = active_agents[agent_id]
    session_id = req.session_id or str(uuid.uuid4())
    await authorize_session(session_id, user, create=True)

    with await owner_consent(user.user_id if user else None):
        result = await agent.execute(req.task, {"history": []})
    if result.get("success"):
        await memory.save_message(session_id, "user", req.task)
        await memory.save_message(
            session_id, "assistant", str(result.get("result", ""))[:5000], agent_id
        )

    return {
        "routed_to": agent.name,
        "agent_id": agent_id,
        "session_id": session_id,
        "result": result,
    }


# ===== RUH ENERGY ENDPOINTS =====


# ===== RŪḤ MODEL ENDPOINTS =====


class RuhGenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=10000)
    max_tokens: int = Field(default=256, ge=1, le=2048)
    temperature: float = Field(default=1.0, ge=0.0, le=2.0)


class RuhTokenizeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=10000)
    detailed: bool = Field(default=False)


@app.get("/api/ruh/status")
async def get_ruh_model_status():
    """Get Rūḥ Model availability and configuration."""
    ruh_enabled = os.getenv("RUH_ENABLED", "").lower() in ("true", "1", "yes")
    ruh_path = os.getenv("RUH_MODEL_PATH", "")
    agents = [*active_agents.values(), *_user_agents.values()]
    local_providers = [
        a.ai_client for a in agents if getattr(a.ai_client, "provider_name", "") == "ruh"
    ]
    return {
        "enabled": ruh_enabled,
        "model_path": ruh_path,
        "device": os.getenv("RUH_DEVICE", "cpu"),
        "loaded": any(getattr(p, "_loaded", False) for p in local_providers),
        "checkpoint_exists": bool(ruh_path and Path(ruh_path).exists()),
        "remote_configured": bool(
            os.getenv("RUNPOD_ENDPOINT_ID")
            and (os.getenv("RUNPOD_API_KEY") or os.getenv("RUNPOD_API_TOKEN"))
        ),
        "active_chat_models": sorted(
            {
                f"{getattr(a.ai_client, 'provider_name', 'unavailable')}: {a.ai_model}"
                for a in active_agents.values()
            }
        ),
        "automatic_weight_training": False,
        "training_running": training_manager.get_status()["running"],
    }


@app.post("/api/ruh/generate")
async def ruh_generate(
    req: RuhGenerateRequest,
    user: TokenPayload | None = Depends(get_current_user),
):
    """Generate text using the local Rūḥ Model."""
    ruh_enabled = os.getenv("RUH_ENABLED", "").lower() in ("true", "1", "yes")
    if not ruh_enabled:
        raise HTTPException(503, "Rūḥ Model is not enabled")

    try:
        # Prefer RunPod remote when configured (avoids CPU freeze on VPS)
        remote = bool(
            os.getenv("RUNPOD_ENDPOINT_ID")
            and (os.getenv("RUNPOD_API_KEY") or os.getenv("RUNPOD_API_TOKEN"))
        )
        if remote:
            provider = create_provider(provider="ruh", model="ruh-remote")
        else:
            provider = create_provider(provider="ruh")
        if not provider:
            raise HTTPException(503, "Rūḥ Model provider not available")

        response = await asyncio.to_thread(
            provider.create,
            model="ruh-remote" if remote else "ruh-local",
            max_tokens=req.max_tokens,
            system="",
            messages=[{"role": "user", "content": req.prompt}],
            temperature=req.temperature,
        )
        return {
            "text": response.content[0].text if response.content else "",
            "usage": response.usage,
            "model": response.model,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Rūḥ generation failed: %s", exc)
        raise HTTPException(500, f"Generation failed: {exc}") from exc


@app.post("/api/ruh/tokenize")
async def ruh_tokenize(req: RuhTokenizeRequest):
    """Tokenize text using the Bayān tokenizer and return analysis."""
    try:
        from ruh_model.tokenizer.bayan import BayanTokenizer

        tokenizer = BayanTokenizer()
        tokens = tokenizer.encode(req.text)
        analysis = tokenizer.analyze(req.text)

        result: dict[str, Any] = {
            "tokens": tokens,
            "token_count": len(tokens),
            "analysis": analysis,
        }

        # Detailed pipeline trace
        if req.detailed:
            result["pipeline"] = _build_tokenizer_pipeline_trace(req.text, tokenizer)

        return result
    except ImportError as exc:
        raise HTTPException(503, "Rūḥ Model package not installed") from exc
    except Exception as exc:
        logger.error("Tokenization failed: %s", exc)
        raise HTTPException(500, f"Tokenization failed: {exc}") from exc


def _build_tokenizer_pipeline_trace(text: str, tokenizer: Any) -> list[dict[str, Any]]:
    """Build a step-by-step pipeline trace for detailed tokenization."""
    steps: list[dict[str, Any]] = []

    # Step 1: Language detection per word
    from ruh_model.tokenizer.bayan import (
        _contains_arabic,
        _is_stopword,
        _tokenize_text,
    )

    words = _tokenize_text(text)
    lang_detections = []
    for word in words:
        is_ar = _contains_arabic(word)
        lang_detections.append(
            {
                "word": word,
                "language": "arabic" if is_ar else "english",
                "is_stopword": _is_stopword(word),
            }
        )
    steps.append(
        {
            "phase": "language_detection",
            "description": "Detect language per word (Arabic vs English)",
            "output": lang_detections,
        }
    )

    # Step 2: Morphological analysis
    morph_results = []
    for info in lang_detections:
        word = str(info["word"])
        if info["is_stopword"]:
            morph_results.append(
                {"word": word, "type": "stopword", "root": "", "pattern": "STOPWORD"}
            )
            continue
        if info["language"] == "arabic":
            root_str, pattern_name = tokenizer._arabic_analyzer.analyze(word)
            morph_results.append(
                {
                    "word": word,
                    "type": "arabic_morphology",
                    "root": root_str,
                    "pattern": pattern_name,
                }
            )
        else:
            root_str, pattern_name = tokenizer._english_bridge.to_root(word)
            morph_results.append(
                {
                    "word": word,
                    "type": "english_bridge",
                    "root": root_str,
                    "pattern": pattern_name,
                }
            )
    steps.append(
        {
            "phase": "morphology",
            "description": "Extract roots and patterns via morphological analysis",
            "output": morph_results,
        }
    )

    # Step 3: Root/pattern ID mapping
    id_results = []
    for morph in morph_results:
        root_id = tokenizer._vocab.get_root_id(morph["root"]) if morph["root"] else 0
        pattern_id = tokenizer._vocab.get_pattern_id(morph["pattern"])
        id_results.append(
            {
                "word": morph["word"],
                "root": morph["root"],
                "pattern": morph["pattern"],
                "root_id": root_id,
                "pattern_id": pattern_id,
            }
        )
    steps.append(
        {
            "phase": "id_mapping",
            "description": "Map roots and patterns to integer IDs",
            "output": id_results,
        }
    )

    # Step 4: Q28 articulatory features (sample for first few words)
    q28_results = []
    for info in lang_detections[:5]:  # Limit to first 5 words
        word = str(info["word"])
        if info["is_stopword"]:
            continue
        try:
            coords = tokenizer._q28.text_to_q28(
                word, lang="ar" if info["language"] == "arabic" else "en"
            )
            q28_results.append(
                {
                    "word": word,
                    "features": [c.tolist() if hasattr(c, "tolist") else list(c) for c in coords]
                    if coords
                    else [],
                    "dimensions": ["place", "manner", "voicing", "nasality", "emphasis", "length"],
                }
            )
        except Exception:
            q28_results.append({"word": word, "features": [], "error": "Q28 analysis unavailable"})
    steps.append(
        {
            "phase": "articulatory_features",
            "description": "Q28 articulatory basis: 6D feature vectors per phoneme",
            "output": q28_results,
        }
    )

    # Step 5: Final token pairs
    tokens = tokenizer.encode(text)
    steps.append(
        {
            "phase": "final_tokens",
            "description": "Final (root_id, pattern_id) pairs with BOS/EOS",
            "output": [{"root_id": r, "pattern_id": p} for r, p in tokens],
        }
    )

    return steps


class TasrifDemoRequest(BaseModel):
    features: list[float] = Field(..., min_length=6, max_length=6)
    operators: list[str] = Field(..., min_length=1)


@app.post("/api/ruh/tasrif-demo")
async def tasrif_demo(req: TasrifDemoRequest):
    """Apply tasrif morphophonemic operators to articulatory feature vectors."""
    try:
        import numpy as np
        from ruh_model.tokenizer.tasrif_ops import TasrifEngine

        engine = TasrifEngine()
        available_ops = engine.get_operator_names()

        invalid = [op for op in req.operators if op not in available_ops]
        if invalid:
            raise HTTPException(
                400,
                f"Unknown operators: {invalid}. Valid: {available_ops}",
            )

        features = np.array(req.features, dtype=np.float64)
        results = []
        current = features.copy()

        for op_name in req.operators:
            prev = current.copy()
            current = engine.apply(op_name, current)
            results.append(
                {
                    "operator": op_name,
                    "input": prev.tolist(),
                    "output": current.tolist(),
                    "changed_dims": [i for i in range(6) if abs(prev[i] - current[i]) > 0.001],
                }
            )

        return {
            "original": features.tolist(),
            "final": current.tolist(),
            "steps": results,
            "dimensions": ["place", "manner", "voicing", "nasality", "emphasis", "length"],
            "available_operators": available_ops,
        }
    except HTTPException:
        raise
    except ImportError as exc:
        raise HTTPException(503, "Rūḥ Model package not installed") from exc
    except Exception as exc:
        logger.error("Tasrif demo failed: %s", exc)
        raise HTTPException(500, f"Tasrif demo failed: {exc}") from exc


# ===== TASK QUEUE ENDPOINTS =====

PRIORITY_MAP = {
    "dharurah": TaskPriority.DHARURAH,
    "hajah": TaskPriority.HAJAH,
    "tahsiniyyah": TaskPriority.TAHSINIYYAH,
    "takmiliyyah": TaskPriority.TAKMILIYYAH,
}

PRIORITY_NAMES = {v: k for k, v in PRIORITY_MAP.items()}


def _task_to_dict(task: QueuedTask) -> dict:
    """Serialize a QueuedTask to a JSON-safe dict."""
    return {
        "task_id": task.task_id,
        "status": task.status,
        "priority": PRIORITY_NAMES.get(task.priority, str(task.priority)),
        "payload": task.payload,
        "agent_id": task.agent_id,
        "created_at": task.created_at,
        "result": task.result,
        "error": task.error,
    }


class QueueTaskRequest(BaseModel):
    task: str = Field(..., min_length=1)
    priority: str = Field(default="tahsiniyyah")
    agent_id: str | None = Field(default=None)
    metadata: dict = Field(default_factory=dict)


@app.post("/api/queue/tasks")
async def enqueue_task(
    req: QueueTaskRequest,
    user: TokenPayload | None = Depends(get_current_user),
):
    """Add a task to the priority queue."""
    priority = PRIORITY_MAP.get(req.priority.lower(), TaskPriority.TAHSINIYYAH)
    payload = {
        "task": req.task,
        "agent_id": req.agent_id,
        **req.metadata,
        "owner_id": user.user_id if user else None,
    }
    task_id = await task_queue.enqueue(payload, priority, req.agent_id)
    await manager.broadcast(
        {
            "type": "queue_update",
            "action": "enqueued",
            "task_id": task_id,
            "pending": task_queue.pending_count,
        }
    )
    return {"task_id": task_id, "priority": req.priority, "status": "queued"}


@app.get("/api/queue/tasks")
async def list_queued_tasks(status: str | None = None, limit: int = 50):
    """List tasks in the queue, optionally filtered by status."""
    tasks = await task_queue.list_tasks(status=status)
    tasks = tasks[: min(limit, 200)]
    return {"tasks": [_task_to_dict(t) for t in tasks], "count": len(tasks)}


@app.get("/api/queue/status")
async def get_queue_status():
    """Get overall queue status with counts and worker state."""
    all_tasks = await task_queue.list_tasks()
    counts: dict[str, int] = {}
    for t in all_tasks:
        counts[t.status] = counts.get(t.status, 0) + 1
    return {
        "pending": counts.get("pending", 0),
        "running": counts.get("running", 0),
        "complete": counts.get("complete", 0),
        "failed": counts.get("failed", 0),
        "cancelled": counts.get("cancelled", 0),
        "total": len(all_tasks),
        "worker": {
            "running": task_worker.is_running if task_worker else False,
            "active_tasks": task_worker.active_count if task_worker else 0,
        },
        "tasks": [_task_to_dict(t) for t in all_tasks[:20]],
    }


@app.get("/api/queue/tasks/{task_id}")
async def get_queued_task(task_id: str) -> dict:
    """Get status and details of a specific queued task."""
    task = await task_queue.get_task(task_id)
    if not task:
        raise HTTPException(404, f"Task '{task_id}' not found")
    return _task_to_dict(task)


@app.delete("/api/queue/tasks/{task_id}")
async def cancel_queued_task(
    task_id: str,
    user: TokenPayload | None = Depends(get_current_user),
) -> dict:
    """Cancel a pending queued task."""
    cancelled = await task_queue.cancel(task_id)
    if not cancelled:
        raise HTTPException(404, f"Task '{task_id}' not found or not cancellable")
    wali.audit.log("task_cancelled", {"task_id": task_id})
    await manager.broadcast(
        {
            "type": "queue_update",
            "action": "cancelled",
            "task_id": task_id,
            "pending": task_queue.pending_count,
        }
    )
    return {"task_id": task_id, "status": "cancelled"}


# ===== LEARNER ENDPOINTS =====


@app.get("/api/learner/stats")
async def get_learner_stats(user: TokenPayload = Depends(require_auth)):
    """Get learning data capture statistics."""
    try:
        from learner.ruh_learner import RuhLearner

        learner = RuhLearner.for_owner(user.user_id)
        await learner.initialize()
        stats = await learner.get_stats()
        return stats
    except ImportError as exc:
        raise HTTPException(503, "Learner module not available") from exc
    except Exception as exc:
        logger.error("Learner stats failed: %s", exc)
        raise HTTPException(500, "Learner statistics are unavailable") from exc


@app.post("/api/learner/export")
async def export_learner_data(
    user: TokenPayload = Depends(require_auth),
):
    """Download the caller's reviewed candidates with model authorship intact."""
    try:
        from learner.data_export import DataExporter
        from learner.ruh_learner import RuhLearner

        learner = RuhLearner.for_owner(user.user_id)
        await learner.initialize()
        exporter = DataExporter(learner.db_path)

        async def records():
            async for record in exporter.records():
                yield json.dumps(record, ensure_ascii=False) + "\n"

        return StreamingResponse(
            records(),
            media_type="application/x-ndjson",
            headers={
                "Content-Disposition": 'attachment; filename="mizan-reviewed-candidates.jsonl"'
            },
        )
    except ImportError as exc:
        raise HTTPException(503, "Learner module not available") from exc
    except Exception as exc:
        logger.error("Export failed: %s", exc)
        raise HTTPException(500, "Reviewed candidates export is unavailable") from exc


@app.get("/api/learner/recent")
async def get_recent_learning_candidates(
    limit: int = Query(default=20, ge=1, le=50), user: TokenPayload = Depends(require_auth)
):
    from learner.ruh_learner import RuhLearner

    learner = RuhLearner.for_owner(user.user_id)
    await learner.initialize()
    return {"interactions": await learner.get_recent(limit)}


class LearningCandidateReview(BaseModel):
    expected_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    accepted: bool = Field(strict=True)
    evidence: str = Field(min_length=1, max_length=4000)
    quality_score: float = Field(ge=0, le=1)


@app.post("/api/learner/review/{interaction_id}")
async def review_learning_candidate(
    interaction_id: int,
    req: LearningCandidateReview,
    user: TokenPayload = Depends(require_auth),
):
    from learner.ruh_learner import RuhLearner

    learner = RuhLearner.for_owner(user.user_id)
    await learner.initialize()
    try:
        return await learner.review_interaction(
            interaction_id,
            reviewer_id=user.user_id,
            expected_hash=req.expected_hash,
            accepted=req.accepted,
            evidence=req.evidence,
            quality_score=req.quality_score,
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


# ===== TRAINING ENDPOINTS =====


@app.get("/api/training/status")
async def get_training_status():
    """Get current Rūḥ Model training status."""
    return training_manager.get_status()


@app.get("/api/training/history")
async def get_training_history():
    """Get history of past training runs."""
    return {"runs": training_manager.get_history()}


class TrainingStartRequest(BaseModel):
    stage: str = Field(default="nutfah", pattern="^(nutfah|alaqah|mudghah|khalq_akhar)$")
    config_path: str | None = None
    data_dir: str = Field(default="ruh_model/data/training")
    checkpoint_dir: str = Field(default="ruh_model/checkpoints")
    log_every: int = Field(default=10, ge=1, le=1000)
    generate_seed_data: bool = False


@app.post("/api/training/start")
async def start_training(
    req: TrainingStartRequest,
    user: TokenPayload | None = Depends(get_current_user),
):
    """Start a Rūḥ Model training run."""
    ruh_enabled = os.getenv("RUH_ENABLED", "").lower() in ("true", "1", "yes")
    if not ruh_enabled:
        raise HTTPException(503, "Rūḥ Model is not enabled. Set RUH_ENABLED=true in .env")

    try:
        result = await training_manager.start_training(
            stage=req.stage,
            config_path=req.config_path,
            data_dir=req.data_dir,
            checkpoint_dir=req.checkpoint_dir,
            log_every=req.log_every,
            generate_seed_data=req.generate_seed_data,
        )
        return result
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        logger.error("Failed to start training: %s", exc)
        raise HTTPException(500, f"Failed to start training: {exc}") from exc


@app.post("/api/training/stop")
async def stop_training(
    user: TokenPayload | None = Depends(get_current_user),
):
    """Stop the currently running training."""
    try:
        result = await training_manager.stop_training()
        return result
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        logger.error("Failed to stop training: %s", exc)
        raise HTTPException(500, f"Failed to stop training: {exc}") from exc


@app.get("/api/ruh/checkpoints")
async def list_checkpoints():
    """List available model checkpoints with metadata."""
    checkpoint_dir = Path("ruh_model/checkpoints")
    if not checkpoint_dir.exists():
        return {"checkpoints": []}

    checkpoints = []
    for entry in sorted(checkpoint_dir.iterdir()):
        if not entry.is_dir():
            continue
        # Compute size
        total_size = sum(f.stat().st_size for f in entry.rglob("*") if f.is_file())
        # Look for config to determine stage
        config_file = entry / "config.json"
        config_data = {}
        if config_file.exists():
            try:
                with open(config_file, encoding="utf-8") as fh:
                    config_data = json.load(fh)
            except (json.JSONDecodeError, OSError):
                pass

        checkpoints.append(
            {
                "name": entry.name,
                "created_at": entry.stat().st_mtime,
                "size_mb": round(total_size / (1024 * 1024), 2),
                "max_seq_len": config_data.get("max_seq_len"),
                "config": config_data,
            }
        )

    return {"checkpoints": checkpoints}


@app.get("/api/ruh/data-stats")
async def get_data_stats():
    """Get training data composition and statistics."""
    data_dir = Path("ruh_model/data/training")
    sources = []

    # Check on-disk seed data
    if data_dir.exists():
        for fpath in data_dir.glob("*.jsonl"):
            line_count = sum(1 for _ in open(fpath, encoding="utf-8"))
            sources.append(
                {
                    "name": fpath.stem,
                    "type": "seed",
                    "samples": line_count,
                    "size_mb": round(fpath.stat().st_size / (1024 * 1024), 2),
                    "available": True,
                }
            )

    # The pipeline's own default sources (ruh_model/data/pipeline.py), equally
    # weighted as the pipeline weighs them. The Quran and hadith are never a
    # training target, so they are never listed as training data here.
    try:
        from ruh_model.data.pipeline import DEFAULT_SOURCES
    except Exception:  # noqa: BLE001 - the Ruh package is optional at runtime
        DEFAULT_SOURCES = {}
    hf_datasets = [
        {
            "name": name,
            "weight": round(1 / len(DEFAULT_SOURCES), 4),
            "hf_id": "/".join(str(part) for part in (spec.get("path"), spec.get("name")) if part),
        }
        for name, spec in DEFAULT_SOURCES.items()
    ]
    for ds in hf_datasets:
        sources.append(
            {
                "name": ds["name"],
                "type": "huggingface",
                "weight": ds["weight"],
                "hf_id": ds["hf_id"],
                "samples": 0,
                "size_mb": 0,
                "available": False,  # Would check actual availability
            }
        )

    total_samples = sum(s["samples"] for s in sources)
    total_size = sum(s["size_mb"] for s in sources)

    return {
        "sources": sources,
        "total_samples": total_samples,
        "total_size_mb": round(total_size, 2),
        "scripture_policy": (
            "The Quran and hadith text are never a training target of Ruh; they are "
            "inputs, retrieval sources or an evaluation set (docs/quranic_training_paths.md)."
        ),
    }


@app.get("/api/ruh/architecture")
async def get_model_architecture():
    """Get model architecture info and parameter counts."""
    try:
        # Default config values (from RuhConfig) - used if import fails
        config_values = {
            "n_layers": 12,
            "d_model": 768,
            "d_root": 256,
            "d_pattern": 256,
            "n_heads": 12,
            "n_roots": 5000,
            "n_patterns": 500,
            "max_seq_len": 512,
        }
        try:
            from ruh_model.config import RuhConfig

            config = RuhConfig()
            config_values = {
                "n_layers": config.n_layers,
                "d_model": config.d_model,
                "d_root": config.d_root,
                "d_pattern": config.d_pattern,
                "n_heads": config.n_heads,
                "n_roots": config.n_roots,
                "n_patterns": config.n_patterns,
                "max_seq_len": config.max_seq_len,
            }
        except ImportError:
            # Use defaults if ruh_model not available
            pass

        # Try to count actual parameters
        total_params = 0
        components = []
        try:
            from ruh_model.config import RuhConfig as RC
            from ruh_model.model import RuhModel

            model = RuhModel(RC())
            total_params = model.count_parameters()

            # Per-module parameter counts
            for name, module in model.named_children():
                param_count = sum(p.numel() for p in module.parameters())
                components.append(
                    {
                        "name": name,
                        "type": type(module).__name__,
                        "params": param_count,
                    }
                )
        except Exception:
            total_params = 0

        return {
            "total_params": total_params,
            "n_layers": config_values["n_layers"],
            "d_model": config_values["d_model"],
            "d_root": config_values["d_root"],
            "d_pattern": config_values["d_pattern"],
            "n_heads": config_values["n_heads"],
            "n_roots": config_values["n_roots"],
            "n_patterns": config_values["n_patterns"],
            "max_seq_len": config_values["max_seq_len"],
            "components": components,
            "architecture_layers": [
                {"name": "ISMEmbedding", "desc": "Factored (root, pattern) → d_model embedding"},
                {
                    "name": "SamBasarDual",
                    "desc": "Dual attention: causal (Sam') + bidirectional (Basar)",
                },
                {"name": "QalbAttention ×7", "desc": "Cardiac-oscillation modulated attention"},
                {
                    "name": "ISMFFN / ShuraMoE",
                    "desc": "SwiGLU FFN or Mixture-of-Experts (every 2 blocks)",
                },
                {"name": "LubbMetacognition", "desc": "Confidence estimation layer"},
                {"name": "AdaptiveDepth", "desc": "Early exit based on confidence threshold"},
                {
                    "name": "MizanLoss",
                    "desc": "5-component loss: CE + Calibration + Consistency + Fitrah + Hisbah",
                },
            ],
        }
    except Exception as exc:
        logger.error("Architecture query failed: %s", exc)
        raise HTTPException(500, f"Failed to get architecture: {exc}") from exc


# Declared after every fixed /api/ruh/... route: a path parameter here would
# otherwise answer /api/ruh/checkpoints and /api/ruh/architecture as an agent id.
@app.get("/api/ruh/{agent_id}")
async def get_ruh_energy(agent_id: str):
    """Get Ruh energy state for an agent."""
    if agent_id not in active_agents:
        raise HTTPException(404, "Agent not found")
    agent = active_agents[agent_id]
    state = agent.ruh.get_state(agent_id)
    return {
        "agent_id": agent_id,
        "energy": state.energy,
        "max_energy": state.max_energy,
        "label": agent.ruh.get_fatigue_label(agent_id),
    }


# === PLUGINS (Wasilah - وسيلة) ===


@app.get("/api/plugins")
async def list_plugins(user: TokenPayload | None = Depends(get_current_user)):
    """List all discovered plugins with their status."""
    return {"plugins": plugin_manager.list_plugins()}


@app.post("/api/plugins/{name}/load")
async def load_plugin(name: str, user: TokenPayload | None = Depends(get_current_user)):
    """Load (activate) a plugin."""
    result = await plugin_manager.load(name)
    if result:
        return {"loaded": True, "name": name}
    raise HTTPException(404, f"Plugin '{name}' not found or failed to load")


@app.post("/api/plugins/{name}/unload")
async def unload_plugin(name: str, user: TokenPayload | None = Depends(get_current_user)):
    """Unload (deactivate) a plugin."""
    result = await plugin_manager.unload(name)
    if result:
        return {"unloaded": True, "name": name}
    raise HTTPException(404, f"Plugin '{name}' not found or not loaded")


@app.post("/api/plugins/{name}/reload")
async def reload_plugin(name: str, user: TokenPayload | None = Depends(get_current_user)):
    """Reload a plugin (unload + load)."""
    result = await plugin_manager.reload(name)
    if result:
        return {"reloaded": True, "name": name}
    raise HTTPException(500, f"Failed to reload plugin '{name}'")


@app.get("/api/plugins/tools")
async def list_plugin_tools():
    """List all tools provided by loaded plugins."""
    tools = []
    for plugin in plugin_manager._loaded.values():
        for name, info in plugin.get_tools().items():
            tools.append(
                {
                    "name": name,
                    "plugin": plugin.manifest.name,
                    "schema": info["schema"],
                }
            )
    return {"tools": tools}


# === EVENTS (Nida' - نداء) ===


@app.get("/api/events")
async def list_events():
    """List all standard events and registered handlers."""
    return {
        "standard_events": EVENTS,
        "handlers": event_bus.list_handlers(),
        "history": event_bus.get_history(limit=50),
    }


@app.get("/api/events/history")
async def event_history(event_name: str | None = None, limit: int = 50):
    """Get recent event history."""
    limit = min(limit, 200)
    return {"history": event_bus.get_history(event_name, limit)}


# === HOOKS (Ta'liq - تعليق) ===


@app.get("/api/hooks")
async def list_hooks():
    """List all standard hooks and registered handlers."""
    return {
        "standard_hooks": HOOKS,
        "registered": hook_registry.list_hooks(),
    }


# === MIDDLEWARE (Silsilah - سلسلة) ===


@app.get("/api/middleware")
async def list_middleware():
    """List all registered middleware pipelines."""
    return {"pipelines": middleware_pipeline.list_middleware()}


# === EXTENSIBILITY STATUS ===


@app.get("/api/extensibility")
async def extensibility_status():
    """
    Overview of all extensibility points in MIZAN.
    Useful for developers who want to build plugins.
    """
    return {
        "plugins": {
            "loaded": len(plugin_manager._loaded),
            "available": len(plugin_manager._manifests),
            "directory": plugin_manager.plugins_dir,
            "list": plugin_manager.list_plugins(),
        },
        "events": {
            "standard": list(EVENTS.keys()),
            "handlers_count": len(event_bus.list_handlers()),
        },
        "hooks": {
            "standard": list(HOOKS.keys()),
            "registered_count": len(hook_registry.list_hooks()),
        },
        "skills": {
            "count": len(skill_registry.list_skills()),
        },
        "middleware": middleware_pipeline.list_middleware(),
    }


# === WEBSOCKET ===


@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str, token: str | None = None):
    user = auth.verify_token(token) if token else None
    if not user:
        await websocket.close(code=4401, reason="Authentication required")
        return
    principal_binding = bind_principal(user)
    # The path label is only a client hint; never use it as a routing key.
    client_id = str(uuid.uuid4())
    if not await manager.connect(client_id, websocket):
        reset_principal(principal_binding)
        return
    manager.owners[client_id] = user.user_id

    wali.audit.log(
        "ws_connected",
        {
            "client_id": client_id,
            "authenticated": user is not None,
            "user_id": user.user_id if user else None,
        },
    )

    provider_info = get_provider_status()
    await manager.send(
        client_id,
        {
            "type": "connected",
            "message": "بسم الله - Connected to MIZAN",
            "agents": len(active_agents),
            "authenticated": user is not None,
            "provider": provider_info["active"],
            "model": provider_info["default_model"],
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )

    try:
        while True:
            data = await websocket.receive_json()

            # Rate limit WebSocket messages
            rl = wali.check_rate_limit(f"ws:{client_id}")
            if not rl["allowed"]:
                await manager.send_required(
                    client_id,
                    {
                        "type": "error",
                        "message": f"Rate limit exceeded. Retry in {rl['retry_after']}s",
                    },
                )
                continue

            msg_type = data.get("type", "chat")
            if msg_type in {"task", "multimodal"} and not user.has_role("admin"):
                await manager.send_required(
                    client_id, {"type": "error", "message": "Administrator role required"}
                )
                continue

            if msg_type == "ping":
                await manager.send_required(client_id, {"type": "pong"})

            elif msg_type == "chat":
                session_id = data.get("session_id", client_id)
                try:
                    await authorize_session(session_id, user, create=True)
                except HTTPException:
                    await manager.send_required(
                        client_id, {"type": "error", "message": "Session not found"}
                    )
                    continue
                content = data.get("content", "")
                agent_id = data.get("agent_id")

                # Validate input
                if not content or len(content) > 50000:
                    await manager.send_required(
                        client_id,
                        {
                            "type": "error",
                            "message": "Invalid message content",
                        },
                    )
                    continue

                # Check for in-chat commands
                agent_for_cmd = None
                if agent_id and agent_id in active_agents:
                    agent_for_cmd = active_agents[agent_id]
                elif active_agents:
                    agent_for_cmd = list(active_agents.values())[0]

                if agent_for_cmd:
                    agent_for_cmd = await chat_agent_for(user, agent_for_cmd)
                cmd_result = await handle_command(
                    content,
                    agent=agent_for_cmd,
                    session_id=session_id,
                    sessions=active_sessions,
                    memory=memory,
                    active_agents=_visible_agents(user),
                )
                if cmd_result.get("is_command"):
                    await manager.send_required(
                        client_id,
                        {
                            "type": "command_result",
                            "session_id": session_id,
                            "content": cmd_result["response"],
                        },
                    )
                    continue

                agent = None
                if agent_id and agent_id in active_agents:
                    agent = active_agents[agent_id]
                elif active_agents:
                    agent = await _default_agent_for(user.user_id)

                if agent:
                    agent = await chat_agent_for(user, agent)
                    session = active_sessions.get(session_id)
                    if session is None:
                        stored = await memory.get_messages(session_id, limit=50)
                        session = {
                            "history": [
                                {"role": m["role"], "content": m["content"]} for m in stored
                            ]
                        }
                    active_sessions[session_id] = session

                    await memory.save_message(session_id, "user", content, agent.id)
                    session["history"].append({"role": "user", "content": content})

                    message_id = str(uuid.uuid4())

                    # Send typing indicator before starting
                    await manager.send_required(
                        client_id,
                        {
                            "type": "typing",
                            "agent": agent.name,
                            "session_id": session_id,
                            "message_id": message_id,
                        },
                    )

                    # Create thinking trace for this message
                    trace = thinking_stream.create_trace(message_id)

                    response_text = ""

                    async def ws_stream(chunk, _sid=session_id, _mid=message_id, **kwargs):
                        nonlocal response_text
                        chunk_type = kwargs.get("chunk_type", "text")
                        if chunk_type == "tool_use":
                            await manager.send_required(
                                client_id,
                                {
                                    "type": "tool_use",
                                    "tool_name": kwargs.get("tool_name", "unknown"),
                                    "session_id": _sid,
                                    "message_id": _mid,
                                },
                            )
                            return
                        response_text += chunk
                        await manager.send_required(
                            client_id,
                            {
                                "type": "chat_stream",
                                "chunk": chunk,
                                "session_id": _sid,
                                "message_id": _mid,
                            },
                        )

                    async def ws_thinking(
                        phase: str,
                        content: str,
                        confidence: float,
                        metadata: dict,
                        _trace=trace,
                        _mid=message_id,
                        _sid=session_id,
                    ):
                        thinking_stream.add_step(
                            _trace.request_id,
                            ThinkingPhase(phase),
                            content,
                            confidence,
                            metadata,
                        )
                        await manager.send_required(
                            client_id,
                            {
                                "type": "thinking",
                                "phase": phase,
                                "content": content,
                                "confidence": confidence,
                                "message_id": _mid,
                                "session_id": _sid,
                                "metadata": metadata,
                            },
                        )

                    from agents.events import bind_event_sink
                    from security.approvals import MODES as PERMISSION_MODES
                    from security.approvals import bind_approvals
                    from security.approvals import chat_context as approvals_for_chat
                    from tadbir.waqt import bind_timezone

                    async def ws_activity(
                        kind: str, payload: dict, _sid=session_id, _mid=message_id
                    ):
                        # Tool, plan and approval frames; an approval is answered with
                        # POST /api/chat/approvals/{approval_id}, as in the web chat.
                        await manager.send_required(
                            client_id,
                            {"type": kind, **payload, "session_id": _sid, "message_id": _mid},
                        )

                    asked = data.get("permission_mode")
                    zone = data.get("timezone")
                    try:
                        # Inside the try: a failure here is this message's error frame, not
                        # a socket that goes quiet.
                        ws_approvals = approvals_for_chat(
                            user.user_id,
                            session_id,
                            asked if asked in PERMISSION_MODES else _permission_mode(agent),
                        )
                        with (
                            bind_timezone(
                                zone if isinstance(zone, str) and len(zone) <= 64 else None
                            ),
                            bind_event_sink(ws_activity),
                            bind_approvals(ws_approvals),
                            await owner_consent(user.user_id),
                        ):
                            result = await agent.execute(
                                content,
                                await chat_context(user, session_id, session, agent, content),
                                stream_callback=ws_stream,
                                thinking_callback=ws_thinking,
                            )
                    except asyncio.CancelledError:
                        await memory.save_message(
                            session_id,
                            "assistant",
                            response_text,
                            agent.id,
                            metadata={
                                "status": "cancelled",
                                "completion_status": "incomplete",
                                "task_verified": False,
                            },
                        )
                        thinking_stream.complete(message_id)
                        raise
                    except Exception:
                        logger.exception(
                            "WebSocket chat execution failed for message %s", message_id
                        )
                        thinking_stream.complete(message_id)
                        result = {
                            "success": False,
                            "completion_status": "failed",
                            "task_verified": False,
                        }

                    final = (
                        result.get("result", response_text)
                        if result.get("success")
                        else response_text
                    )
                    if isinstance(final, dict):
                        final = final.get("response", str(final))

                    failure = chat_failure_payload(result) if not result.get("success") else {}
                    await memory.save_message(
                        session_id,
                        "assistant",
                        str(final),
                        agent.id,
                        metadata={
                            "usage": result.get("usage", {}),
                            **chat_completion_receipt(result),
                            "status": "complete" if result.get("success") else "error",
                            **({"partial": True, **failure} if failure else {}),
                        },
                    )
                    session["history"].append({"role": "assistant", "content": str(final)})
                    if not result.get("success"):
                        thinking_stream.complete(message_id)
                        await manager.send_required(
                            client_id,
                            {
                                "type": "error",
                                "session_id": session_id,
                                "message_id": message_id,
                                **failure,
                            },
                        )
                        continue

                    # Extract cognitive metadata from QALB-7 pipeline
                    cognitive = {
                        k: result.get(k)
                        for k in (
                            "nafs_level",
                            "nafs_name",
                            "ruh_energy",
                            "qalb",
                            "yaqin",
                            "mizan_label",
                            "cognitive_method",
                            "lubb",
                            "lawwama",
                            "metrics_kind",
                            "metric_provenance",
                        )
                        if result.get(k) is not None
                    }

                    # Complete thinking trace and include in response
                    thinking_stream.complete(message_id)
                    completed_trace = thinking_stream.get_trace(message_id)
                    trace_dict = None
                    if completed_trace:
                        trace_dict = {
                            "request_id": completed_trace.request_id,
                            "steps": [
                                {
                                    "id": s.id,
                                    "phase": s.phase.value,
                                    "content": s.content,
                                    "confidence": s.confidence,
                                    "timestamp": s.timestamp,
                                    "metadata": s.metadata,
                                }
                                for s in completed_trace.steps
                            ],
                            "duration_ms": completed_trace.duration_ms,
                            "avg_confidence": completed_trace.avg_confidence,
                        }

                    await manager.send_required(
                        client_id,
                        {
                            "type": "chat_complete",
                            "response": str(final),
                            "usage": result.get("usage", {}),
                            **chat_completion_receipt(result),
                            "content": str(final),
                            "agent": agent.name,
                            "session_id": session_id,
                            "message_id": message_id,
                            "success": result.get("success", True),
                            "cognitive": cognitive,
                            "thinking_trace": trace_dict,
                        },
                    )

            elif msg_type == "task":
                task = data.get("task", "")
                agent_id = data.get("agent_id")

                if not task or len(task) > 50000:
                    await manager.send_required(
                        client_id,
                        {
                            "type": "error",
                            "message": "Invalid task",
                        },
                    )
                    continue

                agent_id = agent_id or balancer.select_agent()
                if agent_id and agent_id in active_agents:
                    agent = active_agents[agent_id]

                    await manager.send_required(
                        client_id,
                        {
                            "type": "task_started",
                            "task": task,
                            "agent": agent.name,
                        },
                    )

                    async def task_stream(chunk):
                        await manager.send_required(
                            client_id, {"type": "task_stream", "chunk": chunk}
                        )

                    with await owner_consent(user.user_id):
                        result = await agent.execute(task, stream_callback=task_stream)

                    await manager.send_required(
                        client_id,
                        {
                            "type": "task_done",
                            "result": result,
                        },
                    )

            elif msg_type == "multimodal":
                import base64 as b64

                session_id = data.get("session_id", client_id)
                try:
                    await authorize_session(session_id, user, create=True)
                except HTTPException:
                    await manager.send_required(
                        client_id, {"type": "error", "message": "Session not found"}
                    )
                    continue
                text = data.get("content", "")
                image_b64 = data.get("image_base64")
                audio_b64 = data.get("audio_base64")
                media_type = data.get("media_type", "image/png")
                qalb_state = data.get("qalb_state", "")

                image_bytes = b64.b64decode(image_b64) if image_b64 else None
                audio_bytes = b64.b64decode(audio_b64) if audio_b64 else None

                agent = next(iter(active_agents.values()), None) if active_agents else None
                if agent:
                    try:
                        result = await agent.qca.process_input_multimodal(
                            text=text,
                            image_bytes=image_bytes,
                            audio_bytes=audio_bytes,
                            media_type=media_type,
                            qalb_state=qalb_state,
                        )
                        await manager.send_required(
                            client_id,
                            {
                                "type": "perception_result",
                                "session_id": session_id,
                                "result": result,
                            },
                        )
                    except Exception as e:
                        await manager.send_required(
                            client_id,
                            {
                                "type": "error",
                                "message": f"Multimodal processing failed: {e}",
                            },
                        )
                else:
                    await manager.send_required(
                        client_id,
                        {"type": "error", "message": "No agents available"},
                    )

            elif msg_type == "command":
                cmd = data.get("command", "").strip()
                if cmd == "/status" or cmd == "status":
                    provider_info = get_provider_status()
                    await manager.send_required(
                        client_id,
                        {
                            "type": "command_result",
                            "command": cmd,
                            "result": f"Agents: {len(active_agents)} | Provider: {provider_info['active']} | Model: {provider_info['default_model']}",
                        },
                    )
                elif cmd == "/new" or cmd == "new":
                    session_id = data.get("session_id", client_id)
                    try:
                        await authorize_session(session_id, user, create=True)
                    except HTTPException:
                        await manager.send_required(
                            client_id, {"type": "error", "message": "Session not found"}
                        )
                        continue
                    active_sessions[session_id] = {"history": []}
                    await manager.send_required(
                        client_id,
                        {
                            "type": "command_result",
                            "command": cmd,
                            "result": "New session started",
                        },
                    )
                elif cmd == "/help" or cmd == "help":
                    await manager.send_required(
                        client_id,
                        {
                            "type": "command_result",
                            "command": cmd,
                            "result": "Commands: /status, /new, /help",
                        },
                    )
                else:
                    await manager.send_required(
                        client_id,
                        {
                            "type": "command_result",
                            "command": cmd,
                            "result": f"Unknown command: {cmd}. Try /help",
                        },
                    )

    except WebSocketDisconnect:
        manager.disconnect(client_id)
        wali.audit.log("ws_disconnected", {"client_id": client_id})
    except RuntimeError:
        # Client disconnected before receive_json could read
        manager.disconnect(client_id)
    except Exception as e:
        logger.error(f"WebSocket error for {client_id}: {e}")
        manager.disconnect(client_id)
        # Close it so the client learns the socket is gone instead of waiting for a frame.
        with contextlib.suppress(Exception):
            await websocket.close(code=1011)
    finally:
        manager.disconnect(client_id)
        reset_principal(principal_binding)


# Imported after shared dependencies to keep deferred auth imports cycle safe.
from api import (  # noqa: E402
    agent_skills,
    artifacts,
    coding_workspace,
    connectors,
    modes,
    qwen3,
    ruh_dialect,
    ruh_disambiguate,
    ruh_embeddings,
    ruh_morphology,
    ruh_reader,
    ruh_screening,
    ruh_tajwid,
    sandbox,
    workspace_sessions,
)

# Session routes first: the public preview path must win over /{workspace_id}/...
for feature in (
    artifacts,
    modes,
    sandbox,
    workspace_sessions,
    coding_workspace,
    agent_skills,
    connectors,
):
    app.include_router(feature.router)
app.include_router(workspace_sessions.ws_router)

for feature in (
    ruh_reader,
    ruh_dialect,
    ruh_embeddings,
    ruh_disambiguate,
    ruh_morphology,
    ruh_screening,
    ruh_tajwid,
    qwen3,
):
    # Production forwards /api/ to the backend; expose versioned features
    # there while retaining direct-app clients' existing /v1/ paths.
    app.include_router(feature.router, prefix="/api")
    app.include_router(feature.router, include_in_schema=False)

# Added last so this pure ASGI layer surrounds the security HTTP middleware.
# The response wrapper inside that middleware cannot bypass transport deadlines.
app.add_middleware(ChatTransportGuard)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
