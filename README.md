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

> Think of it as your personal AI employee that can use tools, remember things, and get better over time.

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

### From Source (for developers)

```bash
git clone https://github.com/CodeWithJuber/mizan.git && cd mizan
make setup                 # Install dependencies
# Edit .env with your API key
make dev                   # Start backend + frontend
# Frontend: http://localhost:3000 — API: http://localhost:8000/docs
```

### What You Need

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
| **Plugin system** | Add new abilities with a simple Python file |
| **Event bus** | Modules communicate without knowing about each other |
| **Hook system** | Modify any data flowing through the system |
| **Middleware pipeline** | Intercept and process requests/responses |
| **REST + WebSocket API** | Full API for building custom integrations |
| **Multi-agent system** | Multiple AI agents collaborate on complex tasks |
| **Security built-in** | JWT auth, rate limiting, sandboxing, audit logs |

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

```
┌─────────────────────────────────────────────────────────────────┐
│                        MIZAN Architecture                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   YOU (Browser/Terminal/Telegram/Discord/Slack/WhatsApp)          │
│    │                                                             │
│    ▼                                                             │
│   ┌──────────────────────────────────────────────────────────┐   │
│   │             Gateway (REST API + WebSocket)                │   │
│   │    Auth · Rate Limiting · Input Validation · CORS        │   │
│   └────────────────────────┬─────────────────────────────────┘   │
│                            │                                     │
│   ┌────────────────────────▼─────────────────────────────────┐   │
│   │                  Plugin System                            │   │
│   │   Events (Nida') · Hooks (Ta'liq) · Middleware (Silsilah) │   │
│   │   Any plugin can listen, modify, or extend               │   │
│   └────────────────────────┬─────────────────────────────────┘   │
│                            │                                     │
│   ┌────────────────────────▼─────────────────────────────────┐   │
│   │              Agent System (Multi-Agent)                   │   │
│   │  ┌────────┐ ┌──────────┐ ┌─────────┐ ┌────────┐         │   │
│   │  │ Hafiz  │ │ Mubashir │ │ Mundhir │ │ Katib  │  + Any  │   │
│   │  │General │ │ Browser  │ │Research │ │  Code  │  Custom  │   │
│   │  └───┬────┘ └────┬─────┘ └────┬────┘ └───┬────┘         │   │
│   │      └──────┬────┘────────────┘───────────┘              │   │
│   │             ▼                                            │   │
│   │  ┌──────────────────────────────────────────────┐        │   │
│   │  │  Agentic Loop (Think → Use Tools → Repeat)   │        │   │
│   │  │  Up to 15 autonomous iterations per task     │        │   │
│   │  └──────────────────────────────────────────────┘        │   │
│   └──────────────────────────────────────────────────────────┘   │
│                            │                                     │
│   ┌───────────┬────────────▼──────────┬──────────────────────┐   │
│   │  Memory   │  LLM Providers        │  Skills & Tools      │   │
│   │  SQLite   │  Claude/GPT/Gemini/   │  Web Browse, Code,   │   │
│   │  3-tier   │  Llama/300+ models    │  File, HTTP + Custom │   │
│   └───────────┴───────────────────────┴──────────────────────┘   │
│                                                                  │
│   ┌──────────────────────────────────────────────────────────┐   │
│   │              Security Layer (Wali Guardian)               │   │
│   │   JWT Auth · Rate Limit · Sandbox · SSRF Block · Audit   │   │
│   └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### How Everything Connects (No Coupling!)

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
POST /api/automation/webhooks Create webhook trigger
```

### System
```
GET  /api/status              System dashboard
POST /api/shura               Multi-agent consultation
WS   /ws/{client_id}          WebSocket connection
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

## Development

```bash
make setup        # Install everything
make dev          # Start backend + frontend
make test         # Run tests
make lint         # Lint code
make format       # Format code
make typecheck    # Type checking
make check        # Run all checks (lint + typecheck + test)
make docker       # Start with Docker
```

---

## Project Structure

```
mizan/
├── backend/
│   ├── api/main.py              # FastAPI server + WebSocket + all routes
│   ├── agents/
│   │   ├── base.py              # Base agent with agentic loop (Think → Tool → Repeat)
│   │   ├── specialized.py       # Browser, Research, Code agents
│   │   └── federation.py        # Agent-to-agent communication
│   ├── core/
│   │   ├── events.py            # Event bus — decoupled communication
│   │   ├── hooks.py             # Hook system — data transformation
│   │   ├── plugins.py           # Plugin manager — extend without touching core
│   │   ├── middleware.py         # Middleware pipeline
│   │   └── ...                  # Quranic core systems
│   ├── providers.py             # Unified LLM provider (Claude/GPT/Ollama/300+)
│   ├── memory/dhikr.py          # Three-tier persistent memory
│   ├── security/                # Auth, permissions, sandboxing
│   ├── skills/                  # Extensible skill registry
│   │   ├── base.py              # Skill base class
│   │   ├── registry.py          # Skill discovery & loading
│   │   └── builtin/             # Built-in skills
│   ├── gateway/channels/        # Telegram, Discord, Slack, WhatsApp adapters
│   ├── automation/              # Cron scheduler + webhook triggers
│   ├── settings.py              # Configuration (env vars)
│   └── cli.py                   # Terminal interface
├── frontend/src/
│   ├── App.tsx                  # Main UI
│   ├── pages/                   # Feature pages (Plugins, Providers, Developer, etc.)
│   ├── hooks/                   # API & WebSocket hooks
│   └── types.ts                 # TypeScript types
├── plugins/                     # Your custom plugins go here!
│   ├── hello_world/             # Example plugin
│   └── request_logger/          # Example monitoring plugin
├── docs/                        # Documentation site
├── tests/                       # Test suite
├── docker/                      # Docker configs
├── pyproject.toml               # Python package config
├── Makefile                     # Development commands
└── docker-compose.yml           # Full-stack deployment
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

**Q: How do I connect Telegram/Discord/Slack?**
A: Set the bot token in your `.env` file (e.g., `TELEGRAM_BOT_TOKEN=your-token`). See the Channels page in the UI.

---

## License

[Apache License 2.0](LICENSE) — Free for personal and commercial use.

---

<div align="center">

**[Star this repo](https://github.com/CodeWithJuber/mizan)** if MIZAN helps you build something amazing.

Built with care by the MIZAN community.

</div>
