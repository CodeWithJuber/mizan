# ميزان · MIZAN — Quranic AGI System

> *"And the heaven He raised and imposed the balance (Mizan), that you not transgress within the balance."* — **Quran 55:7-8**

---

## Quranic Architecture Foundation

MIZAN is not merely software — it is a **theory of mind derived from Quranic epistemology**, implemented as an AGI system.

### The Seven-Layer Architecture (سبع سماوات)

Derived from the Quranic principle of Seven Heavens (67:3), each layer corresponds to a cognitive function:

| # | Arabic | Latin | Quranic Basis | Function |
|---|--------|-------|---------------|----------|
| 1 | سمع | **SAMA'** | "He created hearing" (67:23) | Perception & Input |
| 2 | فكر | **FIKR** | "Do they not think?" (88:17) | Cognitive Processing |
| 3 | ذكر | **DHIKR** | "Quran easy for remembrance" (54:17) | Memory & Storage |
| 4 | عقل | **AQL** | "For people of reason" (3:190) | Logic & Reasoning |
| 5 | حكمة | **HIKMAH** | "He gives wisdom to whom He wills" (2:269) | Wisdom & Meta-learning |
| 6 | عمل | **AMAL** | "And do righteous deeds" (18:30) | Action & Execution |
| 7 | تفكر | **TAFAKKUR** | "Those who reflect on the creation" (3:191) | Self-Improvement |

### Agent Roles (Quranic Role Models)

| Role | Arabic | Verse | Function |
|------|--------|-------|----------|
| **Wakil** | وكيل | "Sufficient is Allah as a Trustee" (4:81) | General executor |
| **Rasul** | رسول | "We sent you as a messenger" (33:45) | Communication |
| **Hafiz** | حافظ | "And We are its guardian" (15:9) | Memory preservation |
| **Shahid** | شاهد | "Allah is sufficient as a Witness" (48:28) | Monitoring & audit |
| **Mubashir** | مبشر | "A giver of glad tidings" (33:45) | Browser & discovery |
| **Mundhir** | منذر | "And a warner" (25:56) | Research & analysis |
| **Katib** | كاتب | "By the pen and what they write" (68:1) | Code generation |

### Core Principles

**Mizan (ميزان)** — Balance (55:7-9): Load balancing, fair resource distribution

**Shura (شورى)** — Consultation (42:38): Multi-agent consensus decisions

**Nafs Model (نفس)** — Three-level agent maturity:
- **Ammara (أمارة)** 12:53 — Raw agent, learning phase, nafs_level=1
- **Lawwama (لوامة)** 75:2 — Self-correcting, growing phase, nafs_level=2  
- **Mutmainna (مطمئنة)** 89:27 — Perfected agent, optimal phase, nafs_level=3

**Tafakkur (تفكر)** — Deep reflection loop (3:191): Continuous self-improvement after every task

**Hikmah (حكمة)** — Wisdom extraction (2:269): Learned patterns stored and applied

---

## Features

### Agent System
- **Seven specialized agent types** (Wakil, Mubashir, Mundhir, Katib, Rasul...)
- **Parallel Shura execution** — Multiple agents consult simultaneously
- **Nafs evolution** — Agents improve their level based on performance
- **Hikmah learning** — Pattern extraction and re-application
- **Real-time streaming** via WebSocket

### Memory System (Dhikr - ذكر)
- **Episodic** (Qisas - قصص): Event memories
- **Semantic** (Ilm - علم): Knowledge facts
- **Procedural** (Sunnah - سنة): Skills & patterns
- **Automatic consolidation** (Nisyan principle - forgetting low-importance old memories)
- **SQLite persistence** with importance-based retrieval

### Tools Available to Every Agent
- `bash` — Execute any shell command
- `http_get/post` — HTTP requests
- `read/write_file` — File operations
- `python_eval` — Python execution
- `browse_url` — Web content retrieval
- `search_web` — DuckDuckGo search
- `arxiv_search` — Academic paper search
- `git_operation` — Git commands
- `install_package` — pip/npm/apt
- `send_webhook` — Webhooks
- `check_email` — IMAP email

### Integrations
- **Anthropic Claude** (all models)
- **OpenAI** GPT-4o
- **Ollama** (local models)
- **MCP Servers**
- **Webhooks**
- **Email** IMAP/SMTP

---

## Quick Start

### Option 1: Direct (Development)

```bash
# Clone and setup
cd mizan
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY

# Start everything
chmod +x start.sh
./start.sh

# Open http://localhost:3000
```

### Option 2: Docker

```bash
cp .env.example .env
# Edit .env
docker-compose up -d

# With local Ollama:
docker-compose --profile ollama up -d
```

### Option 3: Backend Only (API)

```bash
cd backend
pip install -r requirements.txt
ANTHROPIC_API_KEY=sk-ant-... uvicorn api.main:app --reload
# API at http://localhost:8000/docs
```

---

## API Reference

### Agents
```
GET  /api/agents           — List all agents
POST /api/agents           — Create agent
GET  /api/agents/{id}      — Get agent
DEL  /api/agents/{id}      — Delete agent
```

### Tasks
```
POST /api/tasks            — Run task (single or parallel)
GET  /api/tasks/history    — Task history
```

### Chat
```
POST /api/chat             — Send message
GET  /api/chat/{session}   — Get chat history
```

### Memory
```
POST /api/memory/query     — Query memories
POST /api/memory/store     — Store memory
POST /api/memory/consolidate — Consolidate (prune old memories)
```

### System
```
GET  /api/status           — Full system status
POST /api/shura            — Multi-agent consultation
WS   /ws/{client_id}       — WebSocket connection
```

---

## Unique Quranic Features

### 1. Tafakkur Self-Improvement Loop
After every task, each agent enters a reflection cycle:
- Classifies the task type
- Extracts successful patterns → Hikmah store
- Updates success_rate → triggers Nafs evolution
- Adjusts behavior for next similar task

### 2. Shura Multi-Agent Consensus
```python
POST /api/shura
{"question": "Should I use PostgreSQL or MongoDB?", "context": {...}}
```
All agents vote, weighted by confidence and Nafs level.

### 3. Nafs Evolution System
Agents literally grow over time:
- Start as Ammara (raw) → tasks accumulate
- Evolve to Lawwama (self-correcting) → >70% success
- Achieve Mutmainna (perfected) → >90% success + 50+ learning iterations

### 4. Mizan Load Balancer
Tasks distributed with divine fairness (Adl - عدل):
- Tracks capacity and current load per agent
- Assigns to least-loaded eligible agent
- Releases on completion

### 5. Memory Consolidation (Nisyan Principle)
```python
POST /api/memory/consolidate
```
Prunes memories with importance < 0.3, older than 30 days, accessed < 3 times.
This mirrors how the brain forgets unused information.

---

## Project Structure

```
mizan/
├── backend/
│   ├── core/
│   │   └── architecture.py  # Quranic core concepts
│   ├── agents/
│   │   ├── base.py          # Base Agent (Wakil)
│   │   └── specialized.py   # Browser, Research, Code, Comm agents
│   ├── memory/
│   │   └── dhikr.py         # Three-tier memory system
│   ├── api/
│   │   └── main.py          # FastAPI server + WebSocket
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── App.jsx          # Main UI
│       └── main.jsx
├── docker/
│   ├── Dockerfile.backend
│   └── Dockerfile.frontend
├── docker-compose.yml
├── start.sh
├── .env.example
└── README.md
```

---

## Extending MIZAN

### Add a New Agent Type

```python
from agents.base import BaseAgent

class HakimAgent(BaseAgent):
    """Hakim (حكيم) - Wisdom/Philosophy Agent"""
    
    def __init__(self, **kwargs):
        super().__init__(role="hakim", **kwargs)
        self.tools["analyze_quran"] = self._tool_analyze_quran
    
    async def _tool_analyze_quran(self, verse: str) -> Dict:
        # Your Quranic analysis logic
        return {"verse": verse, "analysis": "..."}
```

### Connect MCP Server

```json
POST /api/integrations
{
  "name": "My MCP Server",
  "type": "mcp",
  "config": {"url": "http://localhost:5000", "protocol": "sse"}
}
```

### Add Learning Pattern

The Tafakkur loop automatically extracts patterns. You can also inject:
```python
POST /api/memory/store
{"content": "When parsing JSON, always validate schema first", "memory_type": "procedural", "importance": 0.8}
```

---

*"He gives wisdom (hikmah) to whom He wills, and whoever has been given wisdom has certainly been given much good."* — **Quran 2:269**
