<div align="center">

# ميزان · MIZAN

### Agentic Personal AI

**Production-ready, self-improving AI assistant with Quranic Cognitive Architecture**

[![CI](https://github.com/CodeWithJuber/mizan/actions/workflows/ci.yml/badge.svg)](https://github.com/CodeWithJuber/mizan/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-Apache%202.0-green.svg)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/mizan.svg)](https://pypi.org/project/mizan/)

[Quick Start](#quick-start) · [Features](#features) · [Architecture](#architecture) · [API Docs](#api-reference) · [Contributing](CONTRIBUTING.md)

</div>

---

## What is MIZAN?

MIZAN is an **agentic personal AI** that goes beyond simple chatbots. It features:

- **Multi-turn agentic loop** — agents autonomously plan, use tools, observe results, and iterate up to 15 turns per task
- **Multi-agent orchestration** — specialized agents (Browser, Researcher, Coder, Communicator) collaborate via Shura consensus
- **Persistent memory** — three-tier memory system with importance-based decay and automatic consolidation
- **Self-improvement** — agents learn from every task, evolve performance tiers, and extract reusable patterns
- **Production security** — JWT auth, rate limiting, command sandboxing, SSRF prevention, and audit logging
- **Easy to install** — `pip install mizan` and you're running

> *"And the heaven He raised and imposed the balance (Mizan), that you not transgress within the balance."* — Quran 55:7-8

---

## Quick Start

### One-Liner (macOS / Linux)

```bash
curl -fsSL https://raw.githubusercontent.com/CodeWithJuber/mizan/main/install.sh | bash
```

Works everywhere. Installs Python and everything else for you.
On macOS, first run may need an Administrator for Homebrew.

### One-Liner (Windows PowerShell)

```powershell
irm https://raw.githubusercontent.com/CodeWithJuber/mizan/main/install.ps1 | iex
```

### Hackable Git Install (macOS / Linux)

```bash
curl -fsSL https://raw.githubusercontent.com/CodeWithJuber/mizan/main/install.sh | bash -s -- --install-method git
```

### Docker Install

```bash
curl -fsSL https://raw.githubusercontent.com/CodeWithJuber/mizan/main/install.sh | bash -s -- --install-method docker
```

Or on Windows PowerShell:

```powershell
$env:MIZAN_METHOD="docker"; irm https://raw.githubusercontent.com/CodeWithJuber/mizan/main/install.ps1 | iex
```

### pip Install

```bash
pip install mizan
mizan setup      # First-time config
mizan chat       # Chat in terminal
mizan serve      # Start API server
```

### Manual Git Clone & Build

```bash
git clone https://github.com/CodeWithJuber/mizan.git
cd mizan && make setup
# Edit .env with your ANTHROPIC_API_KEY
make dev
# Frontend: http://localhost:3000 — API: http://localhost:8000/docs
```

### Docker Compose (Manual)

```bash
git clone https://github.com/CodeWithJuber/mizan.git
cd mizan
cp .env.example .env
# Edit .env with your API key

docker compose up -d

# With local Ollama + vector database:
docker compose --profile ollama --profile vector up -d
```

### Requirements

- **Python 3.11+** (auto-installed by the one-liner)
- **At least one API key**: Anthropic (recommended), OpenAI, or local Ollama
- Node.js 20+ (for frontend only, auto-installed by git method)

---

## Features

### Agentic AI Core

| Feature | Description |
|---------|-------------|
| **Multi-turn tool loop** | Agents call tools, observe results, reason, and repeat — up to 15 autonomous iterations per task |
| **7 agent types** | Hafiz (General), Mubashir (Browser), Mundhir (Research), Katib (Code), Rasul (Communication), + custom |
| **Shura consensus** | Multi-agent consultation with confidence-weighted voting for complex decisions |
| **Nafs evolution** | Agents grow: Ammara (raw) → Lawwama (self-correcting) → Mutmainna (perfected) |
| **Hikmah learning** | Pattern extraction after every task, applied to future similar tasks |

### Tools Available to Agents

| Tool | Capability |
|------|-----------|
| `bash` | Shell command execution (sandboxed) |
| `http_get/post` | HTTP requests with SSRF prevention |
| `read_file/write_file` | File operations (sandboxed paths) |
| `python_exec` | Python code execution (subprocess isolated) |
| `list_files` | Directory listing |
| `browse_url` | Web content retrieval |
| `search_web` | DuckDuckGo search |
| `git_operation` | Git commands |

### Memory System (Dhikr)

Three-tier persistent memory inspired by Quranic epistemology:

- **Episodic (Qisas)** — Event memories with temporal context
- **Semantic (Ilm)** — Knowledge facts and relationships
- **Procedural (Sunnah)** — Skills, patterns, and learned behaviors
- **Auto-consolidation** — Low-importance memories decay; frequently accessed ones strengthen
- **Working memory** — 7-item capacity (Miller's Law meets Quranic 7 heavens)

### QCA Cognitive Pipeline

The **Quranic Cognitive Architecture** processes every input through 7 layers:

```
Input → Sam' (Sequential) + Basar (Structural) + Fu'ad (Integration)
     → ISM (Root-Space Semantics)
     → Mizan (Epistemic Weighting — prevents overclaiming)
     → 'Aql (Typed Relationship Binding — 8 relationship types)
     → Lawh (4-Tier Memory — Immutable/Verified/Active/Conjecture)
     → Furqan + Bayan (Discrimination + Articulation)
```

### Security

- **JWT authentication** with API key support
- **Rate limiting** (60 req/min per IP)
- **Command sandboxing** — blocks `rm -rf`, `sudo`, `eval`, etc.
- **Path sandboxing** — agents can only write to allowed directories
- **SSRF prevention** — blocks requests to internal IPs
- **Input validation** — max 50KB, whitelist patterns
- **Audit logging** — every action is logged with severity levels

### Integrations

| Provider | Status |
|----------|--------|
| Anthropic Claude (all models) | Full support |
| OpenAI GPT-4o | Supported |
| Ollama (local models) | Supported |
| Telegram | Channel adapter |
| Discord | Channel adapter |
| Slack | Channel adapter |
| WhatsApp | Channel adapter |
| Email (IMAP/SMTP) | Supported |
| Webhooks | Trigger system |
| MCP Servers | Integration layer |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    MIZAN Architecture                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─── Frontend ────┐  ┌──── CLI ────┐  ┌─── Channels ──┐  │
│  │ React + Tailwind│  │ mizan chat  │  │ Telegram/Slack │  │
│  │ WebSocket       │  │ mizan serve │  │ Discord/WA     │  │
│  └────────┬────────┘  └──────┬──────┘  └───────┬────────┘  │
│           │                  │                  │           │
│  ┌────────▼──────────────────▼──────────────────▼────────┐  │
│  │              FastAPI Gateway (Bab)                     │  │
│  │    REST API + WebSocket + Auth + Rate Limiting         │  │
│  └────────────────────────┬──────────────────────────────┘  │
│                           │                                 │
│  ┌────────────────────────▼──────────────────────────────┐  │
│  │              Agent System                              │  │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐    │  │
│  │  │ Hafiz   │ │Mubashir │ │ Mundhir │ │  Katib  │    │  │
│  │  │ General │ │ Browser │ │Research │ │  Code   │    │  │
│  │  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘    │  │
│  │       └──────┬────┘───────────┘────────────┘         │  │
│  │              │                                        │  │
│  │  ┌───────────▼──────────────────────────────────┐    │  │
│  │  │  Agentic Loop (ReAct)                        │    │  │
│  │  │  Think → Tool Use → Observe → Think → ...    │    │  │
│  │  │  Up to 15 autonomous iterations              │    │  │
│  │  └──────────────────────────────────────────────┘    │  │
│  └───────────────────────────────────────────────────────┘  │
│                           │                                 │
│  ┌────────────────────────▼──────────────────────────────┐  │
│  │              QCA Engine (7-Layer Pipeline)             │  │
│  │  Sam'→Basar→Fu'ad→ISM→Mizan→'Aql→Lawh→Furqan        │  │
│  └───────────────────────────────────────────────────────┘  │
│                           │                                 │
│  ┌──────────┬─────────────▼────────────┬─────────────────┐  │
│  │ Memory   │   Security (Wali)       │ Skills Registry  │  │
│  │ (Dhikr)  │   JWT + Rate Limit      │ Extensible       │  │
│  │ SQLite   │   Sandboxing + Audit    │ Plugin System    │  │
│  └──────────┴──────────────────────────┴─────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### The Seven-Layer Architecture (سبع سماوات)

| # | Arabic | Latin | Quranic Basis | Function |
|---|--------|-------|---------------|----------|
| 1 | سمع | **SAMA'** | "He created hearing" (67:23) | Perception & Input |
| 2 | فكر | **FIKR** | "Do they not think?" (88:17) | Cognitive Processing |
| 3 | ذكر | **DHIKR** | "Quran easy for remembrance" (54:17) | Memory & Storage |
| 4 | عقل | **AQL** | "For people of reason" (3:190) | Logic & Reasoning |
| 5 | حكمة | **HIKMAH** | "He gives wisdom to whom He wills" (2:269) | Wisdom & Meta-learning |
| 6 | عمل | **AMAL** | "And do righteous deeds" (18:30) | Action & Execution |
| 7 | تفكر | **TAFAKKUR** | "Those who reflect on the creation" (3:191) | Self-Improvement |

### Agent Roles

| Role | Arabic | Function |
|------|--------|----------|
| **Wakil** | وكيل | General executor / trustee |
| **Mubashir** | مبشر | Browser & discovery |
| **Mundhir** | منذر | Research & analysis |
| **Katib** | كاتب | Code generation |
| **Rasul** | رسول | Communication |
| **Hafiz** | حافظ | Memory preservation |
| **Shahid** | شاهد | Monitoring & audit |

### Project Structure

```
mizan/
├── backend/
│   ├── api/main.py          # FastAPI server + WebSocket
│   ├── agents/
│   │   ├── base.py          # Base agent with agentic loop
│   │   └── specialized.py   # Browser, Research, Code agents
│   ├── memory/dhikr.py      # Three-tier memory system
│   ├── qca/engine.py        # 7-layer cognitive pipeline
│   ├── security/            # Auth, permissions, validation
│   ├── skills/              # Extensible skill registry
│   ├── automation/          # Cron scheduler + triggers
│   ├── gateway/             # Multi-channel adapters
│   ├── settings.py          # Centralized configuration
│   └── cli.py               # CLI interface
├── frontend/src/            # React + Tailwind UI
├── tests/                   # Comprehensive test suite
├── docker/                  # Docker configurations
├── .github/                 # CI/CD + issue templates
├── pyproject.toml           # Python package config
├── Makefile                 # Development commands
├── docker-compose.yml       # Full-stack deployment
└── CONTRIBUTING.md          # Contributor guide
```

---

## API Reference

### Agents
```
GET  /api/agents           List all agents
POST /api/agents           Create agent
GET  /api/agents/{id}      Get agent details
DEL  /api/agents/{id}      Delete agent
```

### Tasks
```
POST /api/tasks            Execute task (single or parallel)
GET  /api/tasks/history    Get task history
```

### Chat
```
POST /api/chat             Send chat message
GET  /api/chat/{session}   Get chat history
```

### Memory
```
POST /api/memory/query     Search memories
POST /api/memory/store     Store a memory
POST /api/memory/consolidate  Prune old memories
```

### System
```
GET  /api/status           System dashboard
POST /api/shura            Multi-agent consultation
WS   /ws/{client_id}       WebSocket connection
```

### Skills & Automation
```
GET  /api/skills           List available skills
POST /api/skills/install   Install a skill
POST /api/skills/execute   Execute a skill action
POST /api/automation/jobs  Create cron job
POST /api/automation/webhooks  Create webhook trigger
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

## Development

```bash
# Install dev dependencies
make install-dev

# Run tests
make test

# Run tests with coverage
make test-cov

# Lint and format
make lint
make format

# Type checking
make typecheck

# Run all checks
make check
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for full development guide.

---

## Extending MIZAN

### Add a Custom Agent

```python
from agents.base import BaseAgent

class HakimAgent(BaseAgent):
    """Hakim (حكيم) - Wisdom Agent"""

    TOOL_SCHEMAS = [{
        "name": "analyze_topic",
        "description": "Deep analysis of a topic",
        "input_schema": {
            "type": "object",
            "properties": {"topic": {"type": "string"}},
            "required": ["topic"],
        },
    }]

    def __init__(self, **kwargs):
        super().__init__(role="hakim", **kwargs)
        self.tools["analyze_topic"] = self._tool_analyze

    async def _tool_analyze(self, topic: str) -> dict:
        return {"analysis": f"Deep analysis of {topic}..."}
```

### Add a Custom Skill

```python
from skills.base import BaseSkill

class TranslationSkill(BaseSkill):
    name = "translation"
    description = "Translate text between languages"

    async def execute(self, params: dict) -> dict:
        return {"translated": "..."}
```

---

## Unique Features

### Tafakkur Self-Improvement Loop
After every task, each agent enters a reflection cycle — classifying the task, extracting patterns (Hikmah), updating success rate, and triggering Nafs evolution.

### Shura Multi-Agent Consensus
All agents vote on complex decisions, weighted by confidence and Nafs level. Inspired by Quran 42:38.

### Epistemic Calibration (Mizan Layer)
The QCA Mizan layer prevents agents from overclaiming certainty. Claims are weighted by evidence level (Yaqin → Zann → Shakk → Wahm) and flagged if they exceed what evidence supports (Tughyan detection).

### Memory Consolidation (Nisyan Principle)
Low-importance, old, rarely-accessed memories are automatically pruned — mirroring how the human brain forgets unused information.

---

## License

[Apache License 2.0](LICENSE)

---

<div align="center">

*"He gives wisdom (hikmah) to whom He wills, and whoever has been given wisdom has certainly been given much good."* — Quran 2:269

**[Star this repo](https://github.com/CodeWithJuber/mizan)** if MIZAN helps you build something amazing.

</div>
