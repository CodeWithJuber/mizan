<div align="center">

# MIZAN

### Your Personal AI That Grows With You

**An open-source, plugin-powered AI assistant that anyone can extend**

[![CI](https://github.com/CodeWithJuber/mizan/actions/workflows/ci.yml/badge.svg)](https://github.com/CodeWithJuber/mizan/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-Apache%202.0-green.svg)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/mizan.svg)](https://pypi.org/project/mizan/)

[Install in 1 Minute](#install-in-1-minute) · [What Can It Do?](#what-can-it-do) · [Build a Plugin](#build-a-plugin-in-5-minutes) · [Docs](docs/) · [Contributing](CONTRIBUTING.md)

</div>

---

## What is MIZAN?

MIZAN is a **personal AI assistant** you can run on your own computer. Unlike ChatGPT or other cloud services:

- **You own your data** — everything runs locally or on your server
- **It can DO things** — browse the web, run code, manage files, send messages
- **It learns from you** — remembers your preferences and past conversations
- **Anyone can extend it** — add new abilities with simple plugins
- **Works with any AI** — Anthropic Claude, OpenAI, OpenRouter (300+ models), or local Ollama

> Think of it as your personal AI employee that can use tools, remember things, and get better over time — powered by a 7-layer Quranic Cognitive Architecture (QALB-7).

---

## Install in 1 Minute

### Mac / Linux (recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/CodeWithJuber/mizan/main/install.sh | bash
```

### Windows (PowerShell)

```powershell
irm https://raw.githubusercontent.com/CodeWithJuber/mizan/main/install.ps1 | iex
```

### Using pip

```bash
pip install mizan
mizan setup      # First-time config (adds your API key)
mizan chat       # Start chatting
mizan serve      # Start the web UI
```

### Using Docker

```bash
git clone https://github.com/CodeWithJuber/mizan.git && cd mizan
cp .env.example .env      # Edit .env with your API key
docker compose up -d       # Start everything
# Open http://localhost:3000
```

**Common Docker Commands:**

| What you want to do | Command |
|---------------------|---------|
| Start MIZAN | `docker compose up -d` |
| Stop MIZAN | `docker compose down` |
| Restart MIZAN | `docker compose restart` |
| View logs | `docker compose logs -f` |
| Update & rebuild | `git pull && docker compose up -d --build` |
| Rebuild from scratch | `docker compose down && docker compose up -d --build` |
| Start with Ollama (free local AI) | `docker compose --profile ollama up -d --build` |
| Start everything (all services) | `docker compose --profile ollama --profile vector up -d --build` |

### From Source (for developers)

```bash
git clone https://github.com/CodeWithJuber/mizan.git && cd mizan
make setup                 # Install dependencies
# Edit .env with your API key
make dev                   # Start backend + frontend
# Frontend: http://localhost:3000 — API: http://localhost:8000/docs
```

### Requirements

- **Python 3.11+** (auto-installed by the one-liner)
- **At least one AI API key**: [Anthropic](https://console.anthropic.com/) (best), [OpenRouter](https://openrouter.ai/) (300+ models), [OpenAI](https://platform.openai.com/), or [Ollama](https://ollama.ai/) (free, local)
- Node.js 20+ (only for frontend development, auto-installed)

---

## What Can It Do?

### For Everyone

| Feature | What It Means |
|---------|---------------|
| **Chat** | Talk to your AI in the browser or terminal |
| **Browse the web** | AI can search Google, read websites, extract information |
| **Run code** | AI writes and executes Python, bash scripts |
| **Manage files** | Read, write, organize files on your computer |
| **Remember things** | Remembers your conversations and preferences |
| **Multiple AI models** | Switch between Claude, GPT-4, Gemini, Llama, and 300+ others |
| **Scheduled tasks** | Set up automated tasks that run on a schedule |
| **Multiple channels** | Connect via Web, Telegram, Discord, Slack, WhatsApp |

### For Developers

| Feature | What It Means |
|---------|---------------|
| **QALB-7 Cognitive Pipeline** | 7-layer architecture: ethics → deliberation → emotion → conviction → metacognition |
| **Developmental Stages** | Agents grow from Nutfah (5 tools, 5 turns) to Khalq Akhar (all tools, 25 turns) |
| **5-Layer Memory Pyramid** | Unified query across episodic, semantic, neural pathways, vectors, and knowledge graph |
| **Causal Reasoning** | Pearl's 3-rung causal ladder: observation, intervention, counterfactual |
| **Plugin system** | Add new abilities with a simple Python file |
| **Event bus + Hooks** | Decoupled communication — modify data at any point in the pipeline |
| **REST + WebSocket API** | Full API with cognitive metadata streamed in real-time |
| **Multi-agent Shura** | Agents consult via Shura Council for complex decisions |
| **Self-healing (Lawwama)** | Immune memory, adaptive checkpoints, auto-package-install |
| **Security (Wali)** | JWT auth, rate limiting, sandboxing, SSRF block, audit logs |

---

## Build a Plugin in 5 Minutes

MIZAN is **fully decoupled** — you can add any new feature without touching core code. Here's how:

### Step 1: Create a folder

```
plugins/
└── my_plugin/
    ├── plugin.json    ← Describes your plugin
    └── main.py        ← Your plugin code
```

### Step 2: Describe your plugin

**plugins/my_plugin/plugin.json**
```json
{
    "name": "my_plugin",
    "version": "1.0.0",
    "description": "What your plugin does",
    "author": "Your Name",
    "permissions": [],
    "tags": ["example"],
    "enabled": true
}
```

### Step 3: Write your code

**plugins/my_plugin/main.py**
```python
from core.plugins import PluginBase

class Plugin(PluginBase):
    async def on_load(self):
        # Give agents a new tool
        self.add_tool("weather", self.get_weather, {
            "name": "weather",
            "description": "Get weather for a city",
            "input_schema": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"]
            }
        })

        # React to events
        self.on_event("task.completed", self.on_task_done)

    async def on_unload(self):
        pass  # Cleanup is automatic

    async def get_weather(self, city: str):
        return {"city": city, "temp": 22, "condition": "sunny"}

    async def on_task_done(self, data):
        print(f"Task completed: {data}")
```

### Step 4: Restart MIZAN

Your plugin loads automatically. The agent can now use the "weather" tool!

### What Your Plugin Can Do

| Capability | How | Example |
|-----------|-----|---------|
| **Add tools** | `self.add_tool(name, handler, schema)` | Give agents new abilities |
| **Listen to events** | `self.on_event(name, handler)` | React when things happen |
| **Modify data** | `self.add_hook(name, handler)` | Change prompts, responses, etc. |
| **Emit events** | `await self.emit(name, data)` | Tell other parts something happened |

See the [Plugin Development Guide](docs/) for the full reference.

---

## Architecture

MIZAN implements a **7-layer Quranic Cognitive Architecture (QALB-7)** — a bio-inspired AI system where each cognitive module maps to a concept from Islamic psychology.

### System Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                        MIZAN Architecture                         │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  YOU (Browser / Terminal / Telegram / Discord / Slack / WhatsApp) │
│   │                                                               │
│   ▼                                                               │
│  ┌───────────────────────────────────────────────────────────┐    │
│  │            Gateway (REST API + WebSocket)                  │    │
│  │   Auth · Rate Limiting · Input Validation · CORS           │    │
│  └──────────────────────┬────────────────────────────────────┘    │
│                         │                                         │
│  ┌──────────────────────▼────────────────────────────────────┐    │
│  │               Plugin System (Decoupled)                    │    │
│  │  Events (Nida') · Hooks (Ta'liq) · Middleware (Silsilah)   │    │
│  └──────────────────────┬────────────────────────────────────┘    │
│                         │                                         │
│  ┌──────────────────────▼────────────────────────────────────┐    │
│  │             QALB-7 Cognitive Pipeline                      │    │
│  │                                                            │    │
│  │  Fitrah ──► Nafs Triad ──► Qalb Processor ──► Fu'ad ──►   │    │
│  │  (Ethics)  (Deliberate)   (Modulate LLM)   (Convict)      │    │
│  │                                                            │    │
│  │  ──► Lubb ──► Developmental Gate ──► Causal Engine         │    │
│  │    (Meta)    (Capability Gate)      (Why/What-if)          │    │
│  └──────────────────────┬────────────────────────────────────┘    │
│                         │                                         │
│  ┌──────────────────────▼────────────────────────────────────┐    │
│  │          Agent System (Multi-Agent + Shura Council)        │    │
│  │  ┌────────┐ ┌──────────┐ ┌─────────┐ ┌────────────────┐   │    │
│  │  │ Hafiz  │ │ Mubashir │ │ Mundhir │ │ Khalifah       │   │    │
│  │  │General │ │ Browser  │ │Research │ │ SuperAgent     │   │    │
│  │  └───┬────┘ └────┬─────┘ └────┬────┘ └───┬────────────┘   │    │
│  │      └───────┬────┘───────────┘───────────┘                │    │
│  │              ▼                                              │    │
│  │  ┌──────────────────────────────────────────────────┐      │    │
│  │  │  Agentic Loop (Think → Tool → Lawwama → Repeat)  │      │    │
│  │  │  5–25 turns (gated by Developmental Stage)       │      │    │
│  │  └──────────────────────────────────────────────────┘      │    │
│  └────────────────────────────────────────────────────────────┘    │
│                         │                                         │
│  ┌──────────┬───────────▼────────────┬────────────────────────┐   │
│  │ Memory   │  LLM Providers         │  Skills & Tools        │   │
│  │ Pyramid  │  Claude / GPT / Gemini │  Web, Code, File,     │   │
│  │ (5-layer)│  Llama / 300+ models   │  SSH, HTTP + Custom   │   │
│  └──────────┴────────────────────────┴────────────────────────┘   │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │             Security Layer (Wali Guardian)                  │   │
│  │  JWT Auth · Rate Limit · Sandbox · SSRF Block · Audit Log  │   │
│  └────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

### QALB-7 Cognitive Modules

Each agent processes every task through these cognitive layers:

| # | Module | Arabic | Purpose | File |
|---|--------|--------|---------|------|
| 1 | **Fitrah** | فطرة | Innate ethical guardrails (NO_HARM, TRUTH, JUSTICE) | `core/fitrah.py` |
| 2 | **Nafs Triad** | نفس | Three competing inner voices (Ammara/Lawwama/Mutmainna) deliberate on approach | `core/nafs_triad.py` |
| 3 | **Qalb Processor** | قلب | Cardiac oscillation — alternates between focused (Qabd) and creative (Bast) states, modulating LLM temperature and token limits | `core/qalb_processor.py` |
| 4 | **Fu'ad** | فؤاد | Bayesian conviction engine — evidence accumulation from impression to conviction | `core/fuad.py` |
| 5 | **Lubb** | لبّ | Metacognition — compresses reasoning traces, checks coherence, detects cognitive bias | `core/lubb.py` |
| 6 | **Developmental Gate** | أطوار | Progressive capability gating (7 stages from Nutfah to Khalq Akhar) — controls tools, turn limits, autonomy | `core/developmental_stages.py` |
| 7 | **Causal Engine** | سببية | Pearl's causal ladder — observation, intervention ("what if I do X?"), counterfactual reasoning | `reasoning/causal_engine.py` |

### Extension Modules

| Module | Arabic | Purpose | File |
|--------|--------|---------|------|
| **Lawwama Self-Healing** | لوّامة | Immune memory, health metrics, adaptive checkpoint intervals | `core/self_healing.py` |
| **Parallel Agents** | — | Concurrent task scheduling + skill transfer between agents | `core/parallel_agents.py` |
| **Imagination** | تصوير | Predictive coding — simulate outcomes before acting | `core/imagination.py` |
| **Creativity** | إبداع | 5 creative modes + fitness landscape mathematics | `core/creativity.py` |
| **Dream Engine** | منام | Offline memory consolidation (NREM replay + REM recombination) | `core/dream_engine.py` |
| **Shura Council** | شورى | Multi-agent consultation for complex decisions | `agents/shura_council.py` |
| **Perpetual Rotation** | دورة | Agent rotation and load balancing | `agents/perpetual_rotation.py` |

### Memory Architecture (5-Layer Pyramid)

All memory layers are queried through a unified `MemoryPyramid`:

| Layer | Module | Purpose |
|-------|--------|---------|
| **Dhikr** | `memory/dhikr.py` | Three-tier persistent memory (episodic, semantic, procedural) |
| **Masalik** | `memory/masalik.py` | Neural pathway network with spreading activation |
| **Lawh al-Mahfuz** | `memory/lawh_mahfuz.py` | Immutable core memory with triple-checksum integrity |
| **VectorStore** | `memory/vector_store.py` | Semantic embedding search (ChromaDB) |
| **KnowledgeGraph** | `memory/knowledge_graph.py` | Entity-relationship graph (SQLite) |

Unified query: `memory/memory_pyramid.py` merges, deduplicates, and ranks results by relevance x certainty x recency.

### Developmental Stages (Nafs Levels 1–7)

Agents grow through seven stages, each unlocking new capabilities:

| Level | Stage | Max Turns | Key Unlocks |
|-------|-------|-----------|-------------|
| 1 | **Nutfah** (نطفة) | 5 | Basic tools: bash, read_file, recall_memory |
| 2 | **Alaqah** (علقة) | 8 | + write_file, http_get |
| 3 | **Mudghah** (مضغة) | 10 | + python_exec, http_post, delegation |
| 4 | **Izham** (عظام) | 12 | + create_agent, causal reasoning (rung 2) |
| 5 | **Lahm** (لحم) | 15 | All tools, causal rung 3, Lubb metacognition |
| 6 | **Nafkh** (نفخ) | 20 | Full metacognition |
| 7 | **Khalq Akhar** (خلق آخر) | 25 | Full autonomy |

### Cognitive Metadata in the UI

Every assistant response includes a **CognitiveBar** showing:
- **Qalb** state (Qabd/Bast/Khushu) with confidence
- **Yaqin** certainty level (ʿIlm al-Yaqin / ʿAyn al-Yaqin / Ḥaqq al-Yaqin)
- **Lubb** quality assessment (confident / hedged / uncertain)
- **Ruh** energy percentage
- **Nafs** level and name badge
- **Lawwama** repair indicator (when self-healing is active)

Expandable for detailed signals, bias flags, and evidence lists.

### Decoupled Communication

```
Plugin A ──────►  Event Bus  ◄────── Plugin B
                    │
                    │ (events flow freely)
                    │
Agent ────────►  Hook Chain  ◄────── Plugin C
                    │
                    │ (data gets modified)
                    │
API Request ──►  Middleware  ──────► Handler
```

**Modules don't import each other.** They communicate through:
- **Events** — "Something happened" (fire and forget)
- **Hooks** — "Modify this data" (transformation chain)
- **Middleware** — "Process this request" (pipeline)

---

## Self-Healing Doctor (Shifa)

MIZAN includes a built-in diagnostic and self-healing system:

```bash
mizan doctor          # Full diagnostic + auto-fix
mizan doctor --check  # Diagnose only (no fixes)
```

Or via the API:

```bash
curl http://localhost:8000/api/doctor       # Diagnose
curl -X POST http://localhost:8000/api/doctor/fix  # Auto-fix
```

The doctor checks:
- Python version and virtual environment
- `.env` file and API key configuration
- All dependencies and core module imports
- Database connectivity and schema
- Neural pathway memory (Masalik) initialization
- Port availability (8000, 3000)
- Provider connectivity (Anthropic, OpenRouter, etc.)

Auto-fixes include creating `.env` from template, generating a secure `SECRET_KEY`, creating the data directory, and running database migrations.

---

## Extensibility Points

MIZAN has **5 ways** to extend it, from easiest to most powerful:

### 1. Plugins (Easiest)

Create a folder in `plugins/` with `plugin.json` + `main.py`. Plugins can:
- Add new tools for agents
- Listen to events
- Modify data with hooks
- Hot-reload without restart

### 2. Skills

Skills are built-in capabilities that agents can use. See `backend/skills/builtin/` for examples.

### 3. Channel Adapters

Connect MIZAN to new platforms (Telegram, Discord, etc.). See `backend/gateway/channels/base.py`.

### 4. LLM Providers

Add new AI model providers. See `backend/providers.py` for the unified interface.

### 5. Custom Agents

Create specialized agents with unique capabilities. See `backend/agents/specialized.py`.

---

## API Reference

### Authentication
```
POST /api/auth/login       Authenticate and get JWT token
POST /api/auth/register    Register a new user
POST /api/auth/api-key     Create an API key (requires auth)
```

### Agents
```
GET  /api/agents              List all agents
POST /api/agents              Create a new agent
GET  /api/agents/{id}         Get agent details
DEL  /api/agents/{id}         Delete an agent
```

### Chat & Tasks
```
POST /api/chat                Send a chat message
GET  /api/chat/{session}      Get chat history
GET  /api/chat/sessions/list  List active sessions
POST /api/tasks               Execute a task (single or parallel)
GET  /api/tasks/history       Get task history
```

### Memory
```
POST /api/memory/query        Search memories
POST /api/memory/store        Store a memory
POST /api/memory/consolidate  Prune old memories
```

### Plugins & Extensibility
```
GET  /api/plugins             List all plugins
POST /api/plugins/{n}/load    Load a plugin
POST /api/plugins/{n}/unload  Unload a plugin
POST /api/plugins/{n}/reload  Reload a plugin
GET  /api/plugins/tools       List tools from plugins
GET  /api/events              List events + handlers
GET  /api/events/history      Recent event history
GET  /api/hooks               List hooks + handlers
GET  /api/middleware           List middleware pipelines
GET  /api/extensibility       Full extensibility overview
```

### Providers
```
GET  /api/providers           List all LLM providers
GET  /api/providers/{n}/models  List models for a provider
GET  /api/providers/{n}/health  Health check
POST /api/providers/switch    Switch active provider
```

### Skills & Automation
```
GET  /api/skills              List available skills
POST /api/skills/install      Install a skill
POST /api/skills/execute      Execute a skill action
POST /api/automation/jobs     Create cron job
GET  /api/automation/jobs     List scheduled jobs
DEL  /api/automation/jobs/{id}  Delete a job
POST /api/automation/webhooks Create webhook trigger
GET  /api/automation/webhooks List webhooks
```

### System & Diagnostics
```
GET  /api/status              System dashboard
GET  /api/health              Health check (for monitoring/Docker)
GET  /api/version             Version info and update check
GET  /api/doctor              Run diagnostic checks
POST /api/doctor/fix          Run diagnostics with auto-fix
GET  /api/settings            Get system settings
POST /api/settings            Update settings
POST /api/shura               Multi-agent consultation
WS   /ws/{client_id}          WebSocket connection
```

### Channels
```
POST /api/channels/{name}/start   Start a channel adapter
POST /api/channels/{name}/stop    Stop a channel adapter
GET  /api/channels/{name}/status  Get channel status
POST /api/channels/{name}/test    Send a test message
```

Full interactive docs at `http://localhost:8000/docs` (Swagger UI).

---

## CLI Usage

```bash
mizan                  # Show help
mizan setup            # First-time setup wizard
mizan chat             # Interactive terminal chat
mizan chat --model claude-opus-4-6  # Use specific model
mizan serve            # Start API server
mizan serve --reload   # Start with auto-reload
mizan status           # Show system status
mizan doctor           # Self-healing diagnostics
mizan version          # Show version
```

---

## LLM Providers

MIZAN works with any major AI provider:

| Provider | Models | Setup |
|----------|--------|-------|
| **Anthropic** | Claude Opus, Sonnet, Haiku | `ANTHROPIC_API_KEY=sk-ant-...` |
| **OpenRouter** | 300+ models (Gemini, Llama, Mistral...) | `OPENROUTER_API_KEY=sk-or-...` |
| **OpenAI** | GPT-4o, o3 | `OPENAI_API_KEY=sk-...` |
| **Ollama** | Any local model | Install [Ollama](https://ollama.ai/) and run it |

Switch providers anytime from the UI or API — no restart needed.

---

## Updating MIZAN

### Quick Reference

| Your setup | Update command |
|-----------|----------------|
| **Docker** | `git pull && docker compose up -d --build` |
| **pip install** | `pip install --upgrade mizan` |
| **From source** | `./update.sh` or `make update` |
| **Production server** | `./deploy.sh --update` |

### Docker Update

```bash
cd mizan                              # Go to your mizan folder
git pull                              # Get latest code
docker compose up -d --build          # Rebuild and restart
```

To update only the frontend:
```bash
docker compose build frontend && docker compose up -d frontend
```

To update only the backend:
```bash
docker compose build backend && docker compose up -d backend
```

### Source Install Update

```bash
./update.sh                # Update everything automatically
```

Or use any of these equivalent commands:

```bash
make update                # Via Makefile
./start.sh update          # Via start script
```

### What the Updater Does

1. Checks if new updates are available
2. Stops running services gracefully
3. Stashes your local changes (and restores them after)
4. Pulls the latest code
5. Rebuilds backend dependencies + frontend
6. Restarts services
7. Shows you the version change (e.g., `3.0.0 → 3.1.0`)

### Other Update Commands

```bash
./update.sh --check        # Check for updates without installing
./update.sh --version      # Show current version
```

### Production Deployments

```bash
./deploy.sh --update       # Update existing production deployment
./deploy.sh --status       # Check service status
./deploy.sh --logs         # View production logs
```

### Auto-Update Notifications

When you start MIZAN with `./start.sh start` or `make dev`, it automatically checks for updates and shows a notification if a new version is available. No action is taken unless you run the update command.

---

## Common Tasks

### Check if MIZAN is running

```bash
docker compose ps                              # Docker users
curl http://localhost:8000/api/health          # Any setup
```

### View logs

```bash
docker compose logs -f                  # All services
docker compose logs -f backend          # Backend only
docker compose logs -f frontend         # Frontend only
```

### Reset everything (start fresh)

```bash
docker compose down -v         # Stop and remove all data
docker compose up -d --build   # Rebuild from scratch
```

### Fix common issues

```bash
mizan doctor                                           # Source install
curl -X POST http://localhost:8000/api/doctor/fix      # Docker / any setup
```

---

## Development

```bash
make setup        # Install everything
make dev          # Start backend + frontend
make update       # Update to latest version
make test         # Run tests
make test-cov     # Run tests with coverage
make lint         # Lint code
make format       # Format code
make typecheck    # Type checking
make check        # Run all checks (lint + typecheck + test)
make clean        # Clean build artifacts
```

### Docker via Makefile

```bash
make docker          # Start with Docker (builds + starts)
make docker-full     # Start with Ollama + ChromaDB
make docker-down     # Stop all Docker services
```

---

## Project Structure

```
mizan/
├── backend/
│   ├── api/main.py                  # FastAPI server + WebSocket + all routes
│   ├── agents/
│   │   ├── base.py                  # Base agent with QALB-7 agentic loop
│   │   ├── specialized.py           # Browser, Research, Code, SuperAgent (Khalifah)
│   │   ├── federation.py            # Agent-to-agent communication
│   │   ├── shura_council.py         # Multi-agent consultation
│   │   └── perpetual_rotation.py    # Agent rotation & load balancing
│   ├── core/
│   │   ├── fitrah.py                # Innate ethical guardrails
│   │   ├── nafs_triad.py            # 3-voice deliberation (Ammara/Lawwama/Mutmainna)
│   │   ├── qalb_processor.py        # Cardiac oscillation → LLM param modulation
│   │   ├── fuad.py                  # Bayesian conviction formation
│   │   ├── lubb.py                  # Metacognition: compress, cohere, debias
│   │   ├── developmental_stages.py  # 7-stage capability gating (Nutfah→Khalq Akhar)
│   │   ├── self_healing.py          # Lawwama immune system + health metrics
│   │   ├── parallel_agents.py       # Concurrent task scheduling + skill transfer
│   │   ├── imagination.py           # Predictive coding engine
│   │   ├── creativity.py            # 5 creative modes + landscape math
│   │   ├── dream_engine.py          # Offline memory consolidation (NREM+REM)
│   │   ├── qalb.py                  # Emotional intelligence (sentiment)
│   │   ├── ruh_engine.py            # Energy/vitality management
│   │   ├── tawbah.py                # Error recovery protocol
│   │   ├── ihsan.py                 # Proactive excellence suggestions
│   │   ├── sabr.py                  # Patience engine for long tasks
│   │   ├── shukr.py                 # Strength reinforcement
│   │   ├── events.py                # Event bus — decoupled communication
│   │   ├── hooks.py                 # Hook system — data transformation
│   │   ├── plugins.py               # Plugin manager
│   │   └── middleware.py            # Middleware pipeline
│   ├── qca/
│   │   ├── engine.py                # 7-layer QCA integration
│   │   ├── yaqin_engine.py          # Certainty/confidence tracking
│   │   ├── cognitive_methods.py     # Reasoning method selection
│   │   └── roots.py                 # Semantic root analysis (ISM layer)
│   ├── providers.py                 # Unified LLM provider (Claude/GPT/Ollama/300+)
│   ├── memory/
│   │   ├── dhikr.py                 # Three-tier persistent memory
│   │   ├── masalik.py               # Neural pathway network (spreading activation)
│   │   ├── lawh_mahfuz.py           # Immutable memory (triple-checksum)
│   │   ├── memory_pyramid.py        # Unified 5-layer query engine
│   │   ├── vector_store.py          # Semantic embeddings (ChromaDB)
│   │   ├── knowledge_graph.py       # Entity-relationship graph
│   │   └── living_memory.py         # Adaptive memory lifecycle
│   ├── reasoning/
│   │   ├── aql_engine.py            # Arabic Query Language reasoning
│   │   ├── causal_engine.py         # Pearl's 3-rung causal ladder
│   │   ├── planner.py               # Task planning
│   │   └── context_manager.py       # Context window management
│   ├── security/                    # Auth, permissions, sandboxing
│   ├── skills/                      # Extensible skill registry
│   │   ├── builtin/                 # Built-in skills (web, code, SSH, cloud)
│   │   ├── base.py                  # Skill base class
│   │   └── registry.py              # Skill discovery & loading
│   ├── knowledge/                   # Knowledge base management
│   ├── gateway/channels/            # Telegram, Discord, Slack, WhatsApp adapters
│   ├── automation/                  # Cron scheduler + webhook triggers
│   ├── doctor.py                    # Self-healing diagnostic system
│   ├── settings.py                  # Configuration (env vars, pydantic-settings)
│   └── cli.py                       # Terminal interface
├── frontend/src/
│   ├── App.tsx                      # Main UI + WebSocket handler
│   ├── components/
│   │   ├── ChatMessage.tsx          # Chat bubbles + CognitiveBar pills
│   │   ├── AgentCard.tsx            # Agent card with Nafs + Ruh bars
│   │   ├── Sidebar.tsx              # Navigation sidebar
│   │   └── ...                      # Toast, Markdown, Icons, etc.
│   ├── pages/                       # Feature pages (Plugins, Providers, Settings, etc.)
│   ├── hooks/                       # API & WebSocket hooks
│   └── types.ts                     # TypeScript types (CognitiveMetadata, etc.)
├── plugins/                         # Your custom plugins go here!
├── docs/                            # Documentation
├── tests/                           # Test suite
├── docker/                          # Docker configs
├── pyproject.toml                   # Python package config
├── Makefile                         # Development commands
└── docker-compose.yml               # Full-stack deployment
```

---

## Events Reference

Your plugins can listen to these events:

| Event | When It Fires |
|-------|--------------|
| `system.startup` | MIZAN starts up |
| `system.shutdown` | MIZAN shuts down |
| `agent.created` | New agent created |
| `agent.deleted` | Agent deleted |
| `task.started` | Agent begins a task |
| `task.completed` | Task finished successfully |
| `task.failed` | Task failed |
| `task.tool.called` | Agent calls a tool |
| `chat.message.received` | User sends message |
| `chat.message.sent` | System sends response |
| `provider.switched` | LLM provider changed |
| `plugin.loaded` | Plugin loaded |
| `plugin.unloaded` | Plugin unloaded |
| `memory.stored` | Memory saved |
| `channel.connected` | Channel connects |
| `webhook.triggered` | Webhook fires |

---

## Hooks Reference

Your plugins can modify data at these points:

| Hook | What You Can Modify |
|------|-------------------|
| `agent.system_prompt` | The system prompt before LLM call |
| `agent.messages` | Message history before LLM call |
| `agent.response` | Agent response before returning |
| `agent.tool.before` | Tool parameters before execution |
| `agent.tool.after` | Tool results after execution |
| `chat.input` | User input before processing |
| `chat.output` | Output before sending to user |
| `provider.before_call` | LLM parameters before API call |
| `provider.after_call` | LLM response after API call |
| `memory.before_store` | Memory before saving |
| `memory.after_query` | Query results before returning |

---

## FAQ

**Q: Do I need to pay for an API key?**
A: You need at least one AI provider. Ollama is completely free and runs locally. Anthropic, OpenAI, and OpenRouter are paid but offer free tiers.

**Q: Can I run MIZAN completely offline?**
A: Yes! Install Ollama and use local models like Llama 3.2. No internet needed.

**Q: How do I add a new AI provider?**
A: Add your provider to `backend/providers.py` following the `BaseLLMProvider` interface. Or use OpenRouter which already supports 300+ models.

**Q: Can I use this in production?**
A: Yes. MIZAN has JWT auth, rate limiting, input validation, command sandboxing, and SSRF prevention built in.

**Q: How do I update MIZAN?**
A: Run `./update.sh` — it handles everything automatically (pulls code, rebuilds, restarts). You can also use `make update` or `./start.sh update`.

**Q: How do I connect Telegram/Discord/Slack?**
A: Set the bot token in your `.env` file (e.g., `TELEGRAM_BOT_TOKEN=your-token`). See the Channels page in the UI.

**Q: Something is broken. How do I fix it?**
A: Run `mizan doctor` — it automatically diagnoses and fixes common issues.

---

## License

[Apache License 2.0](LICENSE) — Free for personal and commercial use.

---

<div align="center">

**[Star this repo](https://github.com/CodeWithJuber/mizan)** if MIZAN helps you build something amazing.

Built with care by the MIZAN community.

</div>
