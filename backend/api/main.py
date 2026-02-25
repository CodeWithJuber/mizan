"""
MIZAN API Gateway (باب - Bab)
==============================

"And Allah is the Guardian (Wali) over His servants" - Quran 42:6

RESTful + WebSocket API for the MIZAN AGI System
All routes organized by Quranic principles
"""

import asyncio
import json
import os
import sys
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from memory.dhikr import DhikrMemorySystem
from agents.specialized import create_agent, BrowserAgent, ResearchAgent, CodeAgent
from core.architecture import MizanBalancer, ShuraCouncil

# ===== APP INITIALIZATION =====

app = FastAPI(
    title="MIZAN (ميزان) - Quranic AGI System",
    description="Seven-layer AGI architecture derived from Quranic principles",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== GLOBAL STATE =====
memory = DhikrMemorySystem(db_path="/tmp/mizan_memory.db")
balancer = MizanBalancer()
shura = ShuraCouncil()
active_agents: Dict[str, Any] = {}
websocket_connections: Dict[str, WebSocket] = {}
active_sessions: Dict[str, Dict] = {}

# ===== PYDANTIC MODELS =====

class AgentCreate(BaseModel):
    name: str
    type: str = "general"
    model: str = "claude-opus-4-6"
    anthropic_api_key: Optional[str] = None
    system_prompt: Optional[str] = None
    capabilities: List[str] = []

class TaskRequest(BaseModel):
    task: str
    agent_id: Optional[str] = None
    context: Optional[Dict] = None
    parallel: bool = False

class ChatMessage(BaseModel):
    session_id: str
    content: str
    agent_id: Optional[str] = None

class IntegrationCreate(BaseModel):
    name: str
    type: str  # mcp | openai | anthropic | ollama | webhook | email
    config: Dict = {}
    enabled: bool = True

class MemoryQuery(BaseModel):
    query: str
    memory_type: Optional[str] = None
    agent_id: Optional[str] = None
    limit: int = 10

# ===== STARTUP =====

@app.on_event("startup")
async def startup():
    """Initialize the MIZAN system - Bismillah (بسم الله)"""
    print("🌙 MIZAN (ميزان) Starting...")
    print("   'And the heaven He raised and imposed the balance' - 55:7")
    
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
                config={"model": os.getenv("DEFAULT_MODEL", "claude-opus-4-6")},
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
                "config": {"model": os.getenv("DEFAULT_MODEL", "claude-opus-4-6")},
            })
    else:
        # Restore agents from memory
        for profile in existing:
            agent = create_agent(
                profile.get("role", "general"),
                agent_id=profile["id"],
                name=profile["name"],
                memory=memory,
                config=profile.get("config", {}),
            )
            agent.total_tasks = profile.get("total_tasks", 0)
            agent.learning_iterations = profile.get("learning_iterations", 0)
            active_agents[agent.id] = agent
            balancer.register(agent.id)
            shura.members[agent.id] = agent
    
    print(f"✅ {len(active_agents)} agents initialized")
    print("🌙 MIZAN ready - Bismillah!")

# ===== WEBSOCKET MANAGER =====

class ConnectionManager:
    def __init__(self):
        self.connections: Dict[str, WebSocket] = {}
    
    async def connect(self, ws_id: str, websocket: WebSocket):
        await websocket.accept()
        self.connections[ws_id] = websocket
    
    def disconnect(self, ws_id: str):
        self.connections.pop(ws_id, None)
    
    async def send(self, ws_id: str, data: Dict):
        ws = self.connections.get(ws_id)
        if ws:
            try:
                await ws.send_json(data)
            except:
                self.disconnect(ws_id)
    
    async def broadcast(self, data: Dict):
        disconnected = []
        for ws_id, ws in self.connections.items():
            try:
                await ws.send_json(data)
            except:
                disconnected.append(ws_id)
        for ws_id in disconnected:
            self.disconnect(ws_id)

manager = ConnectionManager()

# ===== ROUTES =====

@app.get("/")
async def root():
    return {
        "system": "MIZAN (ميزان)",
        "verse": "And the heaven He raised and imposed the balance (Mizan) - 55:7",
        "version": "1.0.0",
        "agents": len(active_agents),
        "status": "active",
    }

# === AGENTS ===

@app.get("/api/agents")
async def list_agents():
    """List all agents with their Nafs profile"""
    agents_data = []
    for agent in active_agents.values():
        d = agent.to_dict()
        d["load"] = balancer.load_weights.get(agent.id, 0)
        agents_data.append(d)
    return {"agents": agents_data, "total": len(agents_data)}

@app.post("/api/agents")
async def create_new_agent(req: AgentCreate):
    """Create a new agent"""
    config = {
        "model": req.model,
        "system_prompt": req.system_prompt,
    }
    if req.anthropic_api_key:
        config["anthropic_api_key"] = req.anthropic_api_key
    
    agent = create_agent(req.type, name=req.name, memory=memory, config=config)
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
    
    return agent.to_dict()

@app.get("/api/agents/{agent_id}")
async def get_agent(agent_id: str):
    if agent_id not in active_agents:
        raise HTTPException(404, "Agent not found")
    return active_agents[agent_id].to_dict()

@app.delete("/api/agents/{agent_id}")
async def delete_agent(agent_id: str):
    if agent_id not in active_agents:
        raise HTTPException(404, "Agent not found")
    del active_agents[agent_id]
    balancer.agents.pop(agent_id, None)
    shura.members.pop(agent_id, None)
    return {"deleted": agent_id}

# === TASKS ===

@app.post("/api/tasks")
async def run_task(req: TaskRequest, background_tasks: BackgroundTasks):
    """Execute a task - single or parallel"""
    
    if req.parallel and not req.agent_id:
        # Shura mode - consult multiple agents
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
    
    # Single agent
    agent_id = req.agent_id or balancer.select_agent()
    if not agent_id or agent_id not in active_agents:
        # Use first available
        if not active_agents:
            raise HTTPException(503, "No agents available")
        agent_id = list(active_agents.keys())[0]
    
    agent = active_agents[agent_id]
    balancer.assign(agent_id)
    
    task_id = str(uuid.uuid4())
    
    async def run_single():
        try:
            chunks = []
            
            async def stream_cb(chunk: str):
                chunks.append(chunk)
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
async def get_task_history(agent_id: Optional[str] = None, limit: int = 50):
    history = await memory.get_task_history(agent_id, limit)
    return {"history": history}

# === CHAT ===

@app.post("/api/chat")
async def chat(req: ChatMessage, background_tasks: BackgroundTasks):
    """Chat with an agent"""
    # Get or create session
    session = active_sessions.get(req.session_id, {"history": []})
    active_sessions[req.session_id] = session
    
    # Save user message
    await memory.save_message(req.session_id, "user", req.content)
    session["history"].append({"role": "user", "content": req.content})
    
    # Select agent
    agent_id = req.agent_id or (list(active_agents.keys())[0] if active_agents else None)
    if not agent_id:
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
        
        # Save assistant message
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
async def store_memory(content: str, memory_type: str = "semantic",
                        importance: float = 0.5, tags: List[str] = []):
    mem_id = await memory.remember(content, memory_type, importance, tags=tags)
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
async def add_integration(req: IntegrationCreate):
    int_id = await memory.save_integration({
        "name": req.name,
        "type": req.type,
        "config": req.config,
        "enabled": req.enabled,
    })
    return {"id": int_id, "name": req.name, "type": req.type}

@app.delete("/api/integrations/{int_id}")
async def delete_integration(int_id: str):
    conn = __import__('sqlite3').connect("/tmp/mizan_memory.db")
    conn.execute("DELETE FROM integrations WHERE id = ?", (int_id,))
    conn.commit()
    conn.close()
    return {"deleted": int_id}

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
    }

@app.post("/api/shura")
async def shura_consult(question: str, context: Dict = {}):
    """Multi-agent Shura consultation"""
    result = await shura.consult(question, context, list(active_agents.keys()))
    return result

# === WEBSOCKET ===

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await manager.connect(client_id, websocket)
    
    # Send welcome
    await manager.send(client_id, {
        "type": "connected",
        "message": "بسم الله - Connected to MIZAN",
        "agents": len(active_agents),
        "timestamp": datetime.utcnow().isoformat(),
    })
    
    try:
        while True:
            data = await websocket.receive_json()
            
            msg_type = data.get("type", "chat")
            
            if msg_type == "ping":
                await manager.send(client_id, {"type": "pong"})
            
            elif msg_type == "chat":
                session_id = data.get("session_id", client_id)
                content = data.get("content", "")
                agent_id = data.get("agent_id")
                
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
