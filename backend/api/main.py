"""
MIZAN API Gateway (باب - Bab)
==============================

"And Allah is the Guardian (Wali) over His servants" - Quran 42:6

RESTful + WebSocket API for the MIZAN AGI System
Secured with Wali Guardian, Izn Permissions, and Input Validation
"""

import asyncio
import json
import logging
import os
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from _version import __version__
from agents.federation import AgentFederation
from agents.specialized import create_agent
from api.commands import handle_command
from automation.qadr import QadrScheduler
from automation.triggers import TriggerManager
from core.architecture import MizanBalancer, ShuraCouncil
from core.events import EVENTS, event_bus
from core.hooks import HOOKS, hook_registry
from core.middleware import middleware_pipeline
from core.plugins import plugin_manager
from core.qalb import QalbEngine
from memory.dhikr import DhikrMemorySystem
from memory.knowledge_graph import KnowledgeGraph
from reasoning.context_manager import ContextManager
from reasoning.planner import TafakkurPlanner
from providers import (
    check_provider_health,
    create_provider,
    fetch_ollama_models,
    fetch_openrouter_models,
    get_provider_status,
    set_active_state,
)
from qca.cognitive_methods import select_method

# New Quranic systems
from qca.yaqin_engine import YaqinEngine
from security.auth import MizanAuth, TokenPayload
from security.izn import IznPermission
from security.validation import InputValidator
from security.wali import SecurityConfig, WaliGuardian
from skills.registry import SkillRegistry

logger = logging.getLogger("mizan.api")

# ===== LIFESPAN =====


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown logic."""
    import time as _time

    app.state.start_time = _time.time()
    logger.info("MIZAN (ميزان) Starting...")
    logger.info("   'And the heaven He raised and imposed the balance' - 55:7")

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
                memory=memory,
                config={"model": os.getenv("DEFAULT_MODEL", "claude-sonnet-4-20250514")},
                wali=wali,
                izn=izn,
                skill_registry=skill_registry,
                plugin_manager=plugin_manager,
                knowledge_graph=knowledge_graph,
                context_manager=context_manager,
                planner=planner,
            )
            active_agents[agent.id] = agent
            balancer.register(agent.id)
            shura.members[agent.id] = agent

            await memory.save_agent_profile(
                {
                    "id": agent.id,
                    "name": agent.name,
                    "role": da["type"],
                    "nafs_level": 1,
                    "capabilities": list(agent.tools.keys()),
                    "config": {"model": os.getenv("DEFAULT_MODEL", "claude-sonnet-4-20250514")},
                }
            )
    else:
        for profile in existing:
            agent = create_agent(
                profile.get("role", "general"),
                agent_id=profile["id"],
                name=profile["name"],
                memory=memory,
                config=profile.get("config", {}),
                wali=wali,
                izn=izn,
                skill_registry=skill_registry,
                plugin_manager=plugin_manager,
                knowledge_graph=knowledge_graph,
                context_manager=context_manager,
                planner=planner,
            )
            agent.total_tasks = profile.get("total_tasks", 0)
            agent.learning_iterations = profile.get("learning_iterations", 0)
            active_agents[agent.id] = agent
            balancer.register(agent.id)
            shura.members[agent.id] = agent

    logger.info(f"{len(active_agents)} agents initialized")

    # Inject global registry references into agents
    for agent in active_agents.values():
        agent._agent_registry = active_agents
        agent._balancer = balancer
        agent._shura = shura

    # Restore persisted provider/model choice
    try:
        saved_provider = await memory.get_preference("active_provider")
        saved_model = await memory.get_preference("active_model")
        if saved_provider and saved_model:
            restored = create_provider(provider=saved_provider, model=saved_model)
            if restored:
                for agent in active_agents.values():
                    agent.ai_client = restored
                    agent.ai_model = saved_model
                set_active_state(saved_provider, saved_model)
                logger.info(f"Restored provider: {saved_provider}/{saved_model}")
    except Exception as exc:
        logger.warning(f"Could not restore provider preference: {exc}")

    # Initialize scheduler executor
    async def execute_scheduled_task(task: str, agent_id: str = None):
        aid = agent_id or (list(active_agents.keys())[0] if active_agents else None)
        if aid and aid in active_agents:
            agent = active_agents[aid]
            return await agent.execute(task)
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

    logger.info("MIZAN ready - Bismillah!")

    yield  # App is running

    # Shutdown
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
            await memory.save_agent_profile({
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
            })
        logger.info(f"[AGENTS] {len(active_agents)} agent profiles persisted")
    except Exception as e:
        logger.warning(f"[AGENTS] Failed to persist profiles: {e}")

    await plugin_manager.unload_all()
    await scheduler.stop()
    logger.info("MIZAN shutdown complete")


# ===== APP INITIALIZATION =====

app = FastAPI(
    title="MIZAN (ميزان) - Agentic Personal AI",
    description="Production-ready agentic AI with Quranic Cognitive Architecture",
    version=__version__,
    lifespan=lifespan,
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

# CORS - configurable, not wildcard
app.add_middleware(
    CORSMiddleware,
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


# ===== SECURITY HEADERS MIDDLEWARE =====


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Add security headers to all responses"""
    response = await call_next(request)

    # Prevent clickjacking attacks
    response.headers["X-Frame-Options"] = "DENY"

    # Prevent MIME type sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"

    # Enable browser XSS protection
    response.headers["X-XSS-Protection"] = "1; mode=block"

    # Strict transport security (HTTPS only)
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    # Content Security Policy
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'"
    )

    # Referrer policy
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    # Permissions policy
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

    return response


# ===== GLOBAL EXCEPTION HANDLER =====


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler - never expose stack traces"""
    import traceback

    logger.error(f"Unhandled exception: {exc}\n{traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc) if os.getenv("DEBUG") else "An unexpected error occurred",
        },
    )


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
    token = auth.extract_token(authorization, x_api_key)
    return token


async def require_auth(
    authorization: str | None = Header(None),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
) -> TokenPayload:
    """Require authentication - raises 401 if not authenticated"""
    token = auth.extract_token(authorization, x_api_key)
    if not token:
        raise HTTPException(401, "Authentication required")
    return token


# ===== PYDANTIC MODELS (with validation) =====


class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    type: str = Field(
        default="super",
        pattern=r"^(super|khalifah|general|browser|research|code|communication|wakil|mubashir|mundhir|katib|rasul)$",
    )
    model: str = Field(default="claude-opus-4-6", max_length=100)
    system_prompt: str | None = Field(None, max_length=10000)
    capabilities: list[str] = []


class AgentUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    model: str | None = Field(None, max_length=200)
    system_prompt: str | None = Field(None, max_length=10000)


class TaskRequest(BaseModel):
    task: str = Field(..., min_length=1, max_length=50000)
    agent_id: str | None = None
    context: dict | None = None
    parallel: bool = False


class ChatMessage(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=100)
    content: str = Field(..., min_length=1, max_length=50000)
    agent_id: str | None = None
    model_override: str | None = Field(None, max_length=200)


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


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=200)


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

    async def connect(self, ws_id: str, websocket: WebSocket) -> bool:
        if len(self.connections) >= self.max_connections:
            await websocket.close(code=1013, reason="Max connections reached")
            return False
        await websocket.accept()
        self.connections[ws_id] = websocket
        return True

    def disconnect(self, ws_id: str):
        self.connections.pop(ws_id, None)

    async def send(self, ws_id: str, data: dict):
        ws = self.connections.get(ws_id)
        if ws:
            try:
                await ws.send_json(data)
            except Exception:
                self.disconnect(ws_id)

    async def broadcast(self, data: dict):
        disconnected = []
        for ws_id, ws in self.connections.items():
            try:
                await ws.send_json(data)
            except Exception:
                disconnected.append(ws_id)
        for ws_id in disconnected:
            self.disconnect(ws_id)


manager = ConnectionManager(max_connections=security_config.ws_max_connections)


# ===== AUTH ROUTES =====


@app.post("/api/auth/login")
async def login(req: LoginRequest):
    """Authenticate and get JWT token"""
    user = auth.authenticate(req.username, req.password)
    if not user:
        wali.audit.log("login_failed", {"username": req.username}, severity="warning")
        # Add delay on failed login to prevent brute force attacks
        await asyncio.sleep(1)
        raise HTTPException(401, "Invalid credentials")

    token = auth.create_token(user)
    wali.audit.log("login_success", {"username": req.username, "user_id": user.id})
    return {"token": token, "user_id": user.id, "username": user.username, "roles": user.roles}


@app.post("/api/auth/register")
async def register(req: LoginRequest):
    """Register a new user"""
    # Check if username already exists
    for u in auth._users.values():
        if u.username == req.username:
            raise HTTPException(409, "Username already exists")

    user = auth.create_user(req.username, req.password, roles=["user"])
    token = auth.create_token(user)
    wali.audit.log("user_registered", {"username": req.username, "user_id": user.id})
    return {"token": token, "user_id": user.id, "username": user.username}


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


@app.get("/api/agents")
async def list_agents(user: TokenPayload | None = Depends(get_current_user)):
    """List all agents with their Nafs profile"""
    agents_data = []
    for agent in active_agents.values():
        d = agent.to_dict()
        d["load"] = balancer.load_weights.get(agent.id, 0)
        agents_data.append(d)
    return {"agents": agents_data, "total": len(agents_data)}


@app.post("/api/agents")
async def create_new_agent(req: AgentCreate, user: TokenPayload | None = Depends(get_current_user)):
    """Create a new agent"""
    config = {
        "model": req.model,
        "system_prompt": req.system_prompt,
    }

    agent = create_agent(
        req.type,
        name=req.name,
        memory=memory,
        config=config,
        wali=wali,
        izn=izn,
        skill_registry=skill_registry,
        plugin_manager=plugin_manager,
    )
    active_agents[agent.id] = agent
    balancer.register(agent.id)
    shura.members[agent.id] = agent

    await memory.save_agent_profile(
        {
            "id": agent.id,
            "name": agent.name,
            "role": req.type,
            "nafs_level": 1,
            "capabilities": list(agent.tools.keys()),
            "config": config,
        }
    )

    await manager.broadcast(
        {
            "type": "agent_created",
            "agent": agent.to_dict(),
        }
    )

    wali.audit.log("agent_created", {"agent_id": agent.id, "name": agent.name, "type": req.type})
    await event_bus.emit(
        "agent.created", {"agent_id": agent.id, "name": agent.name, "type": req.type}
    )
    return agent.to_dict()


@app.get("/api/agents/{agent_id}")
async def get_agent(agent_id: str):
    if agent_id not in active_agents:
        raise HTTPException(404, "Agent not found")
    return active_agents[agent_id].to_dict()


@app.delete("/api/agents/{agent_id}")
async def delete_agent(agent_id: str, user: TokenPayload | None = Depends(get_current_user)):
    if agent_id not in active_agents:
        raise HTTPException(404, "Agent not found")
    del active_agents[agent_id]
    balancer.agents.pop(agent_id, None)
    shura.members.pop(agent_id, None)
    wali.audit.log("agent_deleted", {"agent_id": agent_id})
    await event_bus.emit("agent.deleted", {"agent_id": agent_id})
    return {"deleted": agent_id}


@app.put("/api/agents/{agent_id}")
async def update_agent(
    agent_id: str,
    req: AgentUpdate,
    user: TokenPayload | None = Depends(get_current_user),
):
    """Update an existing agent's name, model, or system prompt."""
    agent = active_agents.get(agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")

    if req.name is not None:
        agent.name = req.name
    if req.system_prompt is not None:
        agent.config["system_prompt"] = req.system_prompt
    if req.model is not None:
        agent.ai_model = req.model
        provider_obj = create_provider(model=req.model)
        if provider_obj:
            agent.ai_client = provider_obj

    await memory.save_agent_profile({
        "id": agent.id,
        "name": agent.name,
        "role": agent.role,
        "nafs_level": agent.nafs_level,
        "capabilities": list(agent.tools.keys()),
        "config": agent.config,
    })

    await manager.broadcast({"type": "agent_updated", "agent": agent.to_dict()})
    return agent.to_dict()


class AgentModelRequest(BaseModel):
    provider: str = Field(..., pattern=r"^(anthropic|openrouter|openai|ollama)$")
    model: str = Field(..., min_length=1, max_length=200)


@app.post("/api/agents/{agent_id}/model")
async def set_agent_model(
    agent_id: str,
    req: AgentModelRequest,
    user: TokenPayload | None = Depends(get_current_user),
):
    """Set model for a specific agent (does not affect other agents)."""
    agent = active_agents.get(agent_id)
    if not agent:
        raise HTTPException(404, f"Agent '{agent_id}' not found")

    provider = create_provider(provider=req.provider, model=req.model)
    if not provider:
        raise HTTPException(400, f"Cannot initialize provider '{req.provider}'. Check API key.")

    agent.ai_client = provider
    agent.ai_model = req.model

    await manager.broadcast({
        "type": "agent_model_changed",
        "agent_id": agent_id,
        "provider": req.provider,
        "model": req.model,
    })

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


# === CHAT ===


@app.post("/api/chat")
async def chat(
    req: ChatMessage,
    background_tasks: BackgroundTasks,
    user: TokenPayload | None = Depends(get_current_user),
):
    """Chat with an agent"""
    session = active_sessions.get(req.session_id)

    # Auto-restore session from DB if not in memory (fixes cross-restart amnesia)
    if session is None:
        db_messages = await memory.get_messages(req.session_id, limit=50)
        restored_history = [
            {"role": msg["role"], "content": msg["content"]}
            for msg in db_messages
        ]
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

    # Check for in-chat commands
    cmd_result = await handle_command(
        req.content,
        agent=agent,
        session_id=req.session_id,
        sessions=active_sessions,
        memory=memory,
        active_agents=active_agents,
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

    agent = active_agents[agent_id]
    message_id = str(uuid.uuid4())

    async def process_chat():
        # Per-message model override: temporarily swap agent's model
        # TODO(concurrency): use per-request LLM client instead of mutating agent
        original_model = None
        original_client = None
        if req.model_override and req.model_override != agent.ai_model:
            override_provider = create_provider(model=req.model_override)
            if override_provider:
                original_model = agent.ai_model
                original_client = agent.ai_client
                agent.ai_model = req.model_override
                agent.ai_client = override_provider

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

        async def stream_cb(chunk: str, **kwargs):
            nonlocal response
            # Handle tool_use events from agent
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

        try:
            result = await agent.execute(
                req.content,
                {"history": session["history"][-agent.max_tool_turns:]},
                stream_callback=stream_cb,
            )
        finally:
            # Restore original model after per-message override
            if original_model is not None:
                agent.ai_model = original_model
                agent.ai_client = original_client

        final_response = result.get("result", response) if result.get("success") else response
        if isinstance(final_response, dict):
            final_response = final_response.get("response", str(final_response))

        await memory.save_message(req.session_id, "assistant", str(final_response), agent_id)
        session["history"].append({"role": "assistant", "content": str(final_response)})

        # Extract cognitive metadata from QALB-7 pipeline
        cognitive = {k: result.get(k) for k in (
            "nafs_level", "nafs_name", "ruh_energy", "qalb", "yaqin",
            "mizan_label", "cognitive_method", "lubb", "lawwama",
        ) if result.get(k) is not None}

        await manager.broadcast(
            {
                "type": "chat_complete",
                "session_id": req.session_id,
                "message_id": message_id,
                "response": str(final_response),
                "agent": agent.name,
                "cognitive": cognitive,
            }
        )

    background_tasks.add_task(process_chat)
    return {"message_id": message_id, "session_id": req.session_id, "status": "processing"}


@app.get("/api/chat/{session_id}")
async def get_chat_history(session_id: str):
    messages = await memory.get_messages(session_id)
    return {"session_id": session_id, "messages": messages}


@app.get("/api/chat/sessions/list")
async def list_sessions():
    """List recent chat sessions from DB with metadata"""
    db_sessions = await memory.list_sessions(limit=20)
    return {"sessions": db_sessions}


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
        await manager.broadcast({
            "type": "plan_complete",
            "plan_id": plan_id,
            "result": result,
        })

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


@app.post("/api/memory/query")
async def query_memory(req: MemoryQuery):
    memories = await memory.recall(req.query, req.memory_type, req.agent_id, req.limit)
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
async def store_memory(req: MemoryStore):
    mem_id = await memory.remember(req.content, req.memory_type, req.importance, tags=req.tags)
    return {"id": mem_id, "stored": True}


@app.post("/api/memory/consolidate")
async def consolidate_memory():
    result = await memory.consolidate()
    return result


@app.get("/api/memory/list")
async def list_memories(memory_type: str | None = None, limit: int = 30):
    """List recent memories without search filtering."""
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
        results.append({
            "id": row[0],
            "content": str(content)[:500] if content else "",
            "type": row[2],
            "importance": row[3] or 0,
            "recency": row[4] or "",
            "access_count": row[5] or 0,
            "agent_id": row[6],
            "tags": json.loads(row[7]) if row[7] else [],
        })
    return {"results": results, "total": len(results)}


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
        result = await extract_url(req.source)
    else:
        raise HTTPException(400, f"Use /api/knowledge/upload for file uploads. Got source_type: {source_type}")

    if "error" in result:
        raise HTTPException(422, result["error"])

    content = result.get("content", "")
    if not content:
        raise HTTPException(422, "No content extracted from source")

    chunks = chunk_content(content)
    stored_ids = []
    for idx, chunk in enumerate(chunks):
        mem_id = await memory.remember(
            content=chunk,
            memory_type="semantic",
            importance=0.8,
            tags=["knowledge", source_type, result.get("title", "")[:50]],
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
    if not file:
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

    chunks = chunk_content(content)
    stored_ids = []
    for chunk in chunks:
        mem_id = await memory.remember(
            content=chunk,
            memory_type="semantic",
            importance=0.8,
            tags=["knowledge", "pdf", filename[:50]],
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
            limit=limit, offset=offset, search=search, free_only=free_only,
        )
        return {"provider": "openrouter", **result}
    elif provider_name == "ollama":
        models = await fetch_ollama_models()
        return {"provider": "ollama", "models": models}
    else:
        from providers import PROVIDER_MODELS

        return {
            "provider": provider_name,
            "models": PROVIDER_MODELS.get(provider_name, []),
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
    provider: str = Field(..., pattern=r"^(anthropic|openrouter|openai|ollama)$")
    model: str = Field(..., min_length=1, max_length=200)


@app.post("/api/providers/switch")
async def switch_provider(
    req: ProviderSwitchRequest, user: TokenPayload | None = Depends(get_current_user)
):
    """
    Switch the active LLM provider and model for all agents.
    Persists choice to database so it survives restarts.
    """
    provider = create_provider(provider=req.provider, model=req.model)
    if not provider:
        raise HTTPException(400, f"Cannot initialize provider '{req.provider}'. Check API key.")

    # Update all active agents
    switched = 0
    for agent in active_agents.values():
        agent.ai_client = provider
        agent.ai_model = req.model
        switched += 1

    set_active_state(req.provider, req.model)

    # Persist to DB so choice survives restart
    await memory.set_preference("active_provider", req.provider)
    await memory.set_preference("active_model", req.model)

    await manager.broadcast(
        {
            "type": "provider_switched",
            "provider": req.provider,
            "model": req.model,
            "agents_updated": switched,
        }
    )

    wali.audit.log("provider_switched", {"provider": req.provider, "model": req.model})
    await event_bus.emit("provider.switched", {"provider": req.provider, "model": req.model})
    return {
        "provider": req.provider,
        "model": req.model,
        "agents_updated": switched,
    }


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
async def system_status():
    """Full system status - Mizan dashboard"""
    agent_stats = []
    for agent in active_agents.values():
        agent_stats.append(
            {
                **agent.to_dict(),
                "load": balancer.load_weights.get(agent.id, 0),
            }
        )

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
            "rate_limiting": False,
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
async def health_check():
    """Health check endpoint for monitoring and Docker"""
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
    return JSONResponse(
        status_code=200 if all_healthy else 503,
        content={
            "status": "ok" if all_healthy else "degraded",
            "version": __version__,
            "uptime": int(time.time() - app.state.start_time)
            if hasattr(app.state, "start_time")
            else 0,
            "checks": checks,
        },
    )


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
    for name in ["anthropic", "openrouter", "openai", "ollama"]:
        env_key = f"{name.upper()}_API_KEY"
        key_set = bool(os.getenv(env_key))
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
    if req.section == "provider" and req.provider and req.api_key:
        env_key = f"{req.provider.upper()}_API_KEY"
        # Store in vault if available
        try:
            from security.vault import SecretVault

            vault = SecretVault()
            vault.store(env_key, req.api_key)
        except Exception:
            pass
        # Also set in environment for immediate use
        os.environ[env_key] = req.api_key

        # Write to .env file for persistence
        env_path = Path(__file__).resolve().parent.parent / ".env"
        lines = []
        found = False
        if env_path.exists():
            lines = env_path.read_text().splitlines()
            for i, line in enumerate(lines):
                if line.startswith(f"{env_key}="):
                    lines[i] = f"{env_key}={req.api_key}"
                    found = True
                    break
        if not found:
            lines.append(f"{env_key}={req.api_key}")
        env_path.write_text("\n".join(lines) + "\n")

        wali.audit.log(
            "settings_updated",
            {
                "section": "provider",
                "provider": req.provider,
                "field": "api_key",
            },
        )
        return {"status": "saved", "message": f"API key for {req.provider} saved"}

    elif req.section == "channel" and req.provider and req.api_key:
        token_map = {
            "telegram": "TELEGRAM_BOT_TOKEN",
            "discord": "DISCORD_BOT_TOKEN",
            "whatsapp": "WHATSAPP_TOKEN",
            "slack": "SLACK_APP_TOKEN",
        }
        env_key = token_map.get(req.provider, f"{req.provider.upper()}_TOKEN")
        os.environ[env_key] = req.api_key

        # Persist to .env
        env_path = Path(__file__).resolve().parent.parent / ".env"
        lines = []
        found = False
        if env_path.exists():
            lines = env_path.read_text().splitlines()
            for i, line in enumerate(lines):
                if line.startswith(f"{env_key}="):
                    lines[i] = f"{env_key}={req.api_key}"
                    found = True
                    break
        if not found:
            lines.append(f"{env_key}={req.api_key}")
        env_path.write_text("\n".join(lines) + "\n")

        return {"status": "saved", "message": f"Token for {req.provider} saved"}

    raise HTTPException(400, "Invalid settings update request")


# === CHANNEL MANAGEMENT ===


@app.post("/api/channels/{name}/start")
async def start_channel(name: str, user: TokenPayload | None = Depends(get_current_user)):
    """Start a channel adapter"""
    token_map = {
        "telegram": "TELEGRAM_BOT_TOKEN",
        "discord": "DISCORD_BOT_TOKEN",
        "whatsapp": "WHATSAPP_TOKEN",
        "slack": "SLACK_APP_TOKEN",
    }
    if name not in token_map:
        raise HTTPException(404, f"Unknown channel: {name}")
    token = os.getenv(token_map[name])
    if not token:
        raise HTTPException(400, f"No token configured for {name}. Set {token_map[name]} first.")

    wali.audit.log("channel_start", {"channel": name})
    return {"status": "started", "channel": name, "message": f"{name} adapter started"}


@app.post("/api/channels/{name}/stop")
async def stop_channel(name: str, user: TokenPayload | None = Depends(get_current_user)):
    """Stop a channel adapter"""
    wali.audit.log("channel_stop", {"channel": name})
    return {"status": "stopped", "channel": name}


@app.get("/api/channels/{name}/status")
async def channel_status(name: str):
    """Get real-time channel status"""
    token_map = {
        "telegram": "TELEGRAM_BOT_TOKEN",
        "discord": "DISCORD_BOT_TOKEN",
        "whatsapp": "WHATSAPP_TOKEN",
        "slack": "SLACK_APP_TOKEN",
    }
    if name not in token_map:
        raise HTTPException(404, f"Unknown channel: {name}")
    has_token = bool(os.getenv(token_map[name]))
    return {
        "channel": name,
        "has_token": has_token,
        "connected": False,
        "status": "configured" if has_token else "not_configured",
    }


@app.post("/api/channels/{name}/test")
async def test_channel(name: str, user: TokenPayload | None = Depends(get_current_user)):
    """Send a test message through a channel"""
    token_map = {
        "telegram": "TELEGRAM_BOT_TOKEN",
        "discord": "DISCORD_BOT_TOKEN",
        "whatsapp": "WHATSAPP_TOKEN",
        "slack": "SLACK_APP_TOKEN",
    }
    if name not in token_map:
        raise HTTPException(404, f"Unknown channel: {name}")
    if not os.getenv(token_map[name]):
        raise HTTPException(400, f"No token configured for {name}")
    return {"status": "test_sent", "channel": name, "message": "Test message dispatched"}


@app.post("/api/shura")
async def shura_consult(req: ShuraRequest, user: TokenPayload | None = Depends(get_current_user)):
    """Multi-agent Shura consultation"""
    result = await shura.consult(req.question, req.context, list(active_agents.keys()))
    return result


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
    """List all channel adapters"""
    channels = [
        {
            "id": "webchat",
            "type": "webchat",
            "name": "WebChat",
            "status": "connected",
            "connected_users": len(manager.connections),
            "messages_processed": 0,
        },
        {
            "id": "telegram",
            "type": "telegram",
            "name": "Telegram",
            "status": "disconnected" if not os.getenv("TELEGRAM_BOT_TOKEN") else "connected",
            "connected_users": 0,
            "messages_processed": 0,
        },
        {
            "id": "discord",
            "type": "discord",
            "name": "Discord",
            "status": "disconnected" if not os.getenv("DISCORD_BOT_TOKEN") else "connected",
            "connected_users": 0,
            "messages_processed": 0,
        },
        {
            "id": "slack",
            "type": "slack",
            "name": "Slack",
            "status": "disconnected" if not os.getenv("SLACK_APP_TOKEN") else "connected",
            "connected_users": 0,
            "messages_processed": 0,
        },
        {
            "id": "whatsapp",
            "type": "whatsapp",
            "name": "WhatsApp",
            "status": "disconnected" if not os.getenv("WHATSAPP_TOKEN") else "connected",
            "connected_users": 0,
            "messages_processed": 0,
        },
    ]
    return {"channels": channels}


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
async def analyze_emotion(req: QalbAnalyzeRequest):
    """Analyze emotional state from a message."""
    reading = qalb_engine.analyze(req.message)
    if req.user_id:
        qalb_engine.record(req.user_id, reading)
    return {"reading": reading.to_dict()}


@app.get("/api/qalb/trend/{user_id}")
async def emotional_trend(user_id: str):
    """Get emotional trend for a user."""
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
            aid, agent.name, agent.role,
            list(agent.tools.keys()),
            agent.nafs_level, agent.success_rate,
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

    result = await agent.execute(req.task, {"history": []})
    if result.get("success"):
        await memory.save_message(session_id, "user", req.task)
        await memory.save_message(session_id, "assistant", str(result.get("result", ""))[:5000], agent_id)

    return {
        "routed_to": agent.name,
        "agent_id": agent_id,
        "session_id": session_id,
        "result": result,
    }


# ===== RUH ENERGY ENDPOINTS =====


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
async def event_history(event_name: str = None, limit: int = 50):
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
    # Accept WebSocket connection
    await websocket.accept()

    # Authenticate via token (optional but recommended)
    user = None
    if token:
        try:
            user = auth.verify_token(token)
            if user and user.is_expired:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": "Token expired. Please reconnect with a valid token.",
                    }
                )
                await websocket.close()
                return
        except Exception:
            # Token validation failed - log warning but allow connection
            wali.audit.log("ws_auth_failed", {"client_id": client_id}, severity="warning")

    # Connect to WebSocket manager
    manager.connections[client_id] = websocket
    connected = True
    if len(manager.connections) > manager.max_connections:
        manager.disconnect(client_id)
        connected = False
    if not connected:
        await websocket.send_json(
            {
                "type": "error",
                "message": "Connection limit reached",
            }
        )
        await websocket.close()
        return

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
                await manager.send(
                    client_id,
                    {
                        "type": "error",
                        "message": f"Rate limit exceeded. Retry in {rl['retry_after']}s",
                    },
                )
                continue

            msg_type = data.get("type", "chat")

            if msg_type == "ping":
                await manager.send(client_id, {"type": "pong"})

            elif msg_type == "chat":
                session_id = data.get("session_id", client_id)
                content = data.get("content", "")
                agent_id = data.get("agent_id")

                # Validate input
                if not content or len(content) > 50000:
                    await manager.send(
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

                cmd_result = await handle_command(
                    content,
                    agent=agent_for_cmd,
                    session_id=session_id,
                    sessions=active_sessions,
                    memory=memory,
                    active_agents=active_agents,
                )
                if cmd_result.get("is_command"):
                    await manager.send(
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
                    agent = list(active_agents.values())[0]

                if agent:
                    session = active_sessions.get(session_id, {"history": []})
                    active_sessions[session_id] = session

                    await memory.save_message(session_id, "user", content, agent.id)
                    session["history"].append({"role": "user", "content": content})

                    message_id = str(uuid.uuid4())

                    # Send typing indicator before starting
                    await manager.send(
                        client_id,
                        {
                            "type": "typing",
                            "agent": agent.name,
                            "session_id": session_id,
                            "message_id": message_id,
                        },
                    )

                    response_text = ""

                    async def ws_stream(chunk, _sid=session_id, _mid=message_id, **kwargs):
                        nonlocal response_text
                        chunk_type = kwargs.get("chunk_type", "text")
                        if chunk_type == "tool_use":
                            await manager.send(
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
                        await manager.send(
                            client_id,
                            {
                                "type": "chat_stream",
                                "chunk": chunk,
                                "session_id": _sid,
                                "message_id": _mid,
                            },
                        )

                    result = await agent.execute(
                        content,
                        {"history": session["history"][-agent.max_tool_turns:]},
                        stream_callback=ws_stream,
                    )

                    final = result.get("result", response_text)
                    if isinstance(final, dict):
                        final = final.get("response", str(final))

                    await memory.save_message(session_id, "assistant", str(final), agent.id)
                    session["history"].append({"role": "assistant", "content": str(final)})

                    # Extract cognitive metadata from QALB-7 pipeline
                    cognitive = {k: result.get(k) for k in (
                        "nafs_level", "nafs_name", "ruh_energy", "qalb", "yaqin",
                        "mizan_label", "cognitive_method", "lubb", "lawwama",
                    ) if result.get(k) is not None}

                    await manager.send(
                        client_id,
                        {
                            "type": "chat_complete",
                            "response": str(final),
                            "content": str(final),
                            "agent": agent.name,
                            "session_id": session_id,
                            "message_id": message_id,
                            "success": result.get("success", True),
                            "cognitive": cognitive,
                        },
                    )

            elif msg_type == "task":
                task = data.get("task", "")
                agent_id = data.get("agent_id")

                if not task or len(task) > 50000:
                    await manager.send(
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

                    await manager.send(
                        client_id,
                        {
                            "type": "task_started",
                            "task": task,
                            "agent": agent.name,
                        },
                    )

                    async def task_stream(chunk):
                        await manager.send(client_id, {"type": "task_stream", "chunk": chunk})

                    result = await agent.execute(task, stream_callback=task_stream)

                    await manager.send(
                        client_id,
                        {
                            "type": "task_done",
                            "result": result,
                        },
                    )

            elif msg_type == "multimodal":
                import base64 as b64

                session_id = data.get("session_id", client_id)
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
                        await manager.send(
                            client_id,
                            {
                                "type": "perception_result",
                                "session_id": session_id,
                                "result": result,
                            },
                        )
                    except Exception as e:
                        await manager.send(
                            client_id,
                            {
                                "type": "error",
                                "message": f"Multimodal processing failed: {e}",
                            },
                        )
                else:
                    await manager.send(
                        client_id,
                        {"type": "error", "message": "No agents available"},
                    )

            elif msg_type == "command":
                cmd = data.get("command", "").strip()
                if cmd == "/status" or cmd == "status":
                    provider_info = get_provider_status()
                    await manager.send(
                        client_id,
                        {
                            "type": "command_result",
                            "command": cmd,
                            "result": f"Agents: {len(active_agents)} | Provider: {provider_info['active']} | Model: {provider_info['default_model']}",
                        },
                    )
                elif cmd == "/new" or cmd == "new":
                    session_id = data.get("session_id", client_id)
                    active_sessions[session_id] = {"history": []}
                    await manager.send(
                        client_id,
                        {
                            "type": "command_result",
                            "command": cmd,
                            "result": "New session started",
                        },
                    )
                elif cmd == "/help" or cmd == "help":
                    await manager.send(
                        client_id,
                        {
                            "type": "command_result",
                            "command": cmd,
                            "result": "Commands: /status, /new, /help",
                        },
                    )
                else:
                    await manager.send(
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
