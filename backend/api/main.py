"""
MIZAN API Gateway (باب - Bab)
==============================

"And Allah is the Guardian (Wali) over His servants" - Quran 42:6

RESTful + WebSocket API for the MIZAN AGI System
Secured with Wali Guardian, Izn Permissions, and Input Validation
"""

import asyncio
import logging
import os
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
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
from agents.specialized import create_agent
from automation.qadr import QadrScheduler
from automation.triggers import TriggerManager
from core.architecture import MizanBalancer, ShuraCouncil
from memory.dhikr import DhikrMemorySystem
from security.auth import MizanAuth, TokenPayload
from security.izn import IznPermission, NAFS_PERMISSION_TIERS
from security.validation import InputValidator
from security.wali import SecurityConfig, WaliGuardian
from skills.registry import SkillRegistry

# New Quranic systems
from qca.yaqin_engine import YaqinEngine, YaqinLevel
from qca.cognitive_methods import CognitiveMethod, TafakkurEngine, select_method
from core.qalb import QalbEngine
from core.ruh_engine import RuhEngine
from agents.federation import AgentFederation

logger = logging.getLogger("mizan.api")

# ===== LIFESPAN =====

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown logic."""
    logger.info("MIZAN (ميزان) Starting...")
    logger.info("   'And the heaven He raised and imposed the balance' - 55:7")

    # Create default agents if none exist
    existing = await memory.get_all_agents()
    if not existing:
        default_agents = [
            {"name": "Hafiz", "type": "general", "role": "Preserver"},
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
            )
            active_agents[agent.id] = agent
            balancer.register(agent.id)
            shura.members[agent.id] = agent

            await memory.save_agent_profile({
                "id": agent.id,
                "name": agent.name,
                "role": da["type"],
                "nafs_level": 1,
                "capabilities": list(agent.tools.keys()),
                "config": {"model": os.getenv("DEFAULT_MODEL", "claude-sonnet-4-20250514")},
            })
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
            )
            agent.total_tasks = profile.get("total_tasks", 0)
            agent.learning_iterations = profile.get("learning_iterations", 0)
            active_agents[agent.id] = agent
            balancer.register(agent.id)
            shura.members[agent.id] = agent

    logger.info(f"{len(active_agents)} agents initialized")

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

    logger.info("MIZAN ready - Bismillah!")

    yield  # App is running

    # Shutdown
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
memory = DhikrMemorySystem(db_path=os.getenv("DB_PATH", "/tmp/mizan_memory.db"))
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


# ===== RATE LIMIT MIDDLEWARE =====

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Rate limiting via Wali Guardian"""
    client_ip = request.client.host if request.client else "unknown"
    if not wali.check_rate_limit(client_ip):
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded. Please slow down."},
        )
    response = await call_next(request)
    return response


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
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'"

    # Referrer policy
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    # Permissions policy
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

    return response


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
    type: str = Field(default="general", pattern=r"^(general|browser|research|code|communication|wakil|mubashir|mundhir|katib|rasul)$")
    model: str = Field(default="claude-opus-4-6", max_length=100)
    system_prompt: str | None = Field(None, max_length=10000)
    capabilities: list[str] = []


class TaskRequest(BaseModel):
    task: str = Field(..., min_length=1, max_length=50000)
    agent_id: str | None = None
    context: dict | None = None
    parallel: bool = False


class ChatMessage(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=100)
    content: str = Field(..., min_length=1, max_length=50000)
    agent_id: str | None = None


class IntegrationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    type: str = Field(..., pattern=r"^(mcp|openai|anthropic|ollama|webhook|email)$")
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
async def create_new_agent(req: AgentCreate,
                            user: TokenPayload | None = Depends(get_current_user)):
    """Create a new agent"""
    config = {
        "model": req.model,
        "system_prompt": req.system_prompt,
    }

    agent = create_agent(
        req.type, name=req.name, memory=memory, config=config,
        wali=wali, izn=izn,
    )
    active_agents[agent.id] = agent
    balancer.register(agent.id)
    shura.members[agent.id] = agent

    await memory.save_agent_profile({
        "id": agent.id,
        "name": agent.name,
        "role": req.type,
        "nafs_level": 1,
        "capabilities": list(agent.tools.keys()),
        "config": config,
    })

    await manager.broadcast({
        "type": "agent_created",
        "agent": agent.to_dict(),
    })

    wali.audit.log("agent_created", {"agent_id": agent.id, "name": agent.name, "type": req.type})
    return agent.to_dict()


@app.get("/api/agents/{agent_id}")
async def get_agent(agent_id: str):
    if agent_id not in active_agents:
        raise HTTPException(404, "Agent not found")
    return active_agents[agent_id].to_dict()


@app.delete("/api/agents/{agent_id}")
async def delete_agent(agent_id: str,
                       user: TokenPayload | None = Depends(get_current_user)):
    if agent_id not in active_agents:
        raise HTTPException(404, "Agent not found")
    del active_agents[agent_id]
    balancer.agents.pop(agent_id, None)
    shura.members.pop(agent_id, None)
    wali.audit.log("agent_deleted", {"agent_id": agent_id})
    return {"deleted": agent_id}


# === TASKS ===

@app.post("/api/tasks")
async def run_task(req: TaskRequest, background_tasks: BackgroundTasks,
                   user: TokenPayload | None = Depends(get_current_user)):
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

            await manager.broadcast({
                "type": "task_complete",
                "task_id": task_id,
                "parallel": True,
                "results": [
                    r if isinstance(r, dict) else {"error": str(r)}
                    for r in results
                ],
            })

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
                await manager.broadcast({
                    "type": "task_stream",
                    "task_id": task_id,
                    "agent_id": agent_id,
                    "chunk": chunk,
                })

            result = await agent.execute(req.task, req.context, stream_callback=stream_cb)
            balancer.release(agent_id)

            await manager.broadcast({
                "type": "task_complete",
                "task_id": task_id,
                "agent_id": agent_id,
                "result": result,
            })
        except Exception as e:
            balancer.release(agent_id)
            await manager.broadcast({
                "type": "task_error",
                "task_id": task_id,
                "error": str(e),
            })

    background_tasks.add_task(run_single)
    return {"task_id": task_id, "agent_id": agent_id, "status": "running"}


@app.get("/api/tasks/history")
async def get_task_history(agent_id: str | None = None, limit: int = 50):
    limit = min(limit, 200)
    history = await memory.get_task_history(agent_id, limit)
    return {"history": history}


# === CHAT ===

@app.post("/api/chat")
async def chat(req: ChatMessage, background_tasks: BackgroundTasks,
               user: TokenPayload | None = Depends(get_current_user)):
    """Chat with an agent"""
    session = active_sessions.get(req.session_id, {"history": []})
    active_sessions[req.session_id] = session

    await memory.save_message(req.session_id, "user", req.content)
    session["history"].append({"role": "user", "content": req.content})

    agent_id = req.agent_id or (list(active_agents.keys())[0] if active_agents else None)
    if not agent_id or agent_id not in active_agents:
        raise HTTPException(503, "No agents available")

    agent = active_agents[agent_id]
    message_id = str(uuid.uuid4())

    async def process_chat():
        response = ""

        async def stream_cb(chunk: str):
            nonlocal response
            response += chunk
            await manager.broadcast({
                "type": "chat_stream",
                "session_id": req.session_id,
                "message_id": message_id,
                "chunk": chunk,
            })

        result = await agent.execute(
            req.content,
            {"history": session["history"][-10:]},
            stream_callback=stream_cb,
        )

        final_response = result.get("result", response) if result.get("success") else response
        if isinstance(final_response, dict):
            final_response = final_response.get("response", str(final_response))

        await memory.save_message(req.session_id, "assistant", str(final_response), agent_id)
        session["history"].append({"role": "assistant", "content": str(final_response)})

        await manager.broadcast({
            "type": "chat_complete",
            "session_id": req.session_id,
            "message_id": message_id,
            "response": str(final_response),
            "agent": agent.name,
        })

    background_tasks.add_task(process_chat)
    return {"message_id": message_id, "session_id": req.session_id, "status": "processing"}


@app.get("/api/chat/{session_id}")
async def get_chat_history(session_id: str):
    messages = await memory.get_messages(session_id)
    return {"session_id": session_id, "messages": messages}


@app.get("/api/chat/sessions/list")
async def list_sessions():
    return {"sessions": list(active_sessions.keys())}


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


# === INTEGRATIONS ===

@app.get("/api/integrations")
async def list_integrations():
    integrations = await memory.get_integrations()
    return {"integrations": integrations}


@app.post("/api/integrations")
async def add_integration(req: IntegrationCreate,
                           user: TokenPayload | None = Depends(get_current_user)):
    int_id = await memory.save_integration({
        "name": req.name,
        "type": req.type,
        "config": req.config,
        "enabled": req.enabled,
    })
    return {"id": int_id, "name": req.name, "type": req.type}


@app.delete("/api/integrations/{int_id}")
async def delete_integration(int_id: str,
                              user: TokenPayload | None = Depends(get_current_user)):
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
        agent_stats.append({
            **agent.to_dict(),
            "load": balancer.load_weights.get(agent.id, 0),
        })

    task_history = await memory.get_task_history(limit=10)

    return {
        "system": "MIZAN",
        "version": __version__,
        "status": "active",
        "timestamp": datetime.utcnow().isoformat(),
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
        "security": {
            "auth_enabled": True,
            "rate_limiting": True,
            "wali_active": True,
            "izn_active": True,
        },
    }


@app.post("/api/shura")
async def shura_consult(req: ShuraRequest,
                        user: TokenPayload | None = Depends(get_current_user)):
    """Multi-agent Shura consultation"""
    result = await shura.consult(req.question, req.context, list(active_agents.keys()))
    return result


# === AUTOMATION (Qadr) ===

@app.get("/api/automation/jobs")
async def list_jobs(user: TokenPayload | None = Depends(get_current_user)):
    """List all scheduled jobs"""
    return {"jobs": scheduler.list_jobs()}


@app.post("/api/automation/jobs")
async def create_job(req: ScheduleJobRequest,
                     user: TokenPayload | None = Depends(get_current_user)):
    """Create a new scheduled job"""
    job = await scheduler.add_job(req.name, req.cron, req.task, req.agent_id)
    wali.audit.log("job_created", {"name": req.name, "cron": req.cron})
    return job.to_dict()


@app.delete("/api/automation/jobs/{job_id}")
async def delete_job(job_id: str,
                     user: TokenPayload | None = Depends(get_current_user)):
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
async def create_webhook(req: WebhookCreateRequest,
                         user: TokenPayload | None = Depends(get_current_user)):
    """Create a new webhook trigger"""
    webhook = await trigger_manager.register_webhook(
        req.name, req.task_template, req.agent_id, req.secret)
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
async def install_skill(req: SkillInstallRequest,
                        user: TokenPayload | None = Depends(get_current_user)):
    """Install a skill"""
    result = skill_registry.install_skill(req.name)
    if result:
        wali.audit.log("skill_installed", {"name": req.name})
        return {"installed": True, "name": req.name}
    raise HTTPException(404, "Skill not found")


@app.post("/api/skills/uninstall")
async def uninstall_skill(req: SkillInstallRequest,
                          user: TokenPayload | None = Depends(get_current_user)):
    """Uninstall a skill"""
    result = skill_registry.uninstall_skill(req.name)
    if result:
        wali.audit.log("skill_uninstalled", {"name": req.name})
        return {"uninstalled": True, "name": req.name}
    raise HTTPException(404, "Skill not found")


class SkillExecuteRequest(BaseModel):
    skill: str = Field(..., min_length=1, max_length=200)
    action: str | None = None

    class Config:
        extra = "allow"  # Allow dynamic params for skill execution


@app.post("/api/skills/execute")
async def execute_skill(req: SkillExecuteRequest,
                        user: TokenPayload | None = Depends(get_current_user)):
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
        raise HTTPException(500, f"Skill execution error: {str(e)}")


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
        {"id": "webchat", "type": "webchat", "name": "WebChat",
         "status": "connected", "connected_users": len(manager.connections),
         "messages_processed": 0},
        {"id": "telegram", "type": "telegram", "name": "Telegram",
         "status": "disconnected" if not os.getenv("TELEGRAM_BOT_TOKEN") else "connected",
         "connected_users": 0, "messages_processed": 0},
        {"id": "discord", "type": "discord", "name": "Discord",
         "status": "disconnected" if not os.getenv("DISCORD_BOT_TOKEN") else "connected",
         "connected_users": 0, "messages_processed": 0},
        {"id": "slack", "type": "slack", "name": "Slack",
         "status": "disconnected" if not os.getenv("SLACK_APP_TOKEN") else "connected",
         "connected_users": 0, "messages_processed": 0},
        {"id": "whatsapp", "type": "whatsapp", "name": "WhatsApp",
         "status": "disconnected" if not os.getenv("WHATSAPP_TOKEN") else "connected",
         "connected_users": 0, "messages_processed": 0},
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
    names = {1: "Ammara", 2: "Lawwama", 3: "Mulhama", 4: "Mutmainna",
             5: "Radiya", 6: "Mardiyya", 7: "Kamila"}
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
        tag = yaqin_engine.tag_proven(req.content, req.pattern_id or "api", confidence=req.confidence)
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
        federation.register_agent(aid, agent.name, agent.role,
                                  list(agent.tools.keys()),
                                  agent.nafs_level, agent.success_rate)
    return federation.get_status()


class DiscoverRequest(BaseModel):
    capabilities: List[str] = []

@app.post("/api/federation/discover")
async def discover_agents(req: DiscoverRequest):
    """Discover agents by capability."""
    matches = federation.discover(req.capabilities)
    return {"agents": [m.to_dict() for m in matches]}


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
                await websocket.send_json({
                    "type": "error",
                    "message": "Token expired. Please reconnect with a valid token.",
                })
                await websocket.close()
                return
        except Exception:
            # Token validation failed - log warning but allow connection
            wali.audit.log("ws_auth_failed", {"client_id": client_id}, severity="warning")

    # Connect to WebSocket manager
    connected = manager.connect(client_id, websocket)
    if not connected:
        await websocket.send_json({
            "type": "error",
            "message": "Connection limit reached",
        })
        await websocket.close()
        return

    wali.audit.log("ws_connected", {
        "client_id": client_id,
        "authenticated": user is not None,
        "user_id": user.user_id if user else None
    })

    await manager.send(client_id, {
        "type": "connected",
        "message": "بسم الله - Connected to MIZAN",
        "agents": len(active_agents),
        "authenticated": user is not None,
        "timestamp": datetime.utcnow().isoformat(),
    })

    try:
        while True:
            data = await websocket.receive_json()

            # Rate limit WebSocket messages
            if not wali.check_rate_limit(f"ws:{client_id}"):
                await manager.send(client_id, {
                    "type": "error",
                    "message": "Rate limit exceeded",
                })
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
                    await manager.send(client_id, {
                        "type": "error",
                        "message": "Invalid message content",
                    })
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

                    response_text = ""

                    async def ws_stream(chunk):
                        nonlocal response_text
                        response_text += chunk
                        await manager.send(client_id, {
                            "type": "stream",
                            "chunk": chunk,
                            "session_id": session_id,
                        })

                    result = await agent.execute(
                        content,
                        {"history": session["history"][-10:]},
                        stream_callback=ws_stream,
                    )

                    final = result.get("result", response_text)
                    if isinstance(final, dict):
                        final = final.get("response", str(final))

                    await memory.save_message(session_id, "assistant", str(final), agent.id)
                    session["history"].append({"role": "assistant", "content": str(final)})

                    await manager.send(client_id, {
                        "type": "response",
                        "content": str(final),
                        "agent": agent.name,
                        "session_id": session_id,
                        "success": result.get("success", True),
                    })

            elif msg_type == "task":
                task = data.get("task", "")
                agent_id = data.get("agent_id")

                if not task or len(task) > 50000:
                    await manager.send(client_id, {
                        "type": "error",
                        "message": "Invalid task",
                    })
                    continue

                agent_id = agent_id or balancer.select_agent()
                if agent_id and agent_id in active_agents:
                    agent = active_agents[agent_id]

                    await manager.send(client_id, {
                        "type": "task_started",
                        "task": task,
                        "agent": agent.name,
                    })

                    async def task_stream(chunk):
                        await manager.send(client_id, {"type": "task_stream", "chunk": chunk})

                    result = await agent.execute(task, stream_callback=task_stream)

                    await manager.send(client_id, {
                        "type": "task_done",
                        "result": result,
                    })

    except WebSocketDisconnect:
        manager.disconnect(client_id)
        wali.audit.log("ws_disconnected", {"client_id": client_id})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
