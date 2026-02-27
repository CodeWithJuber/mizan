# MIZAN Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- Replace deprecated `datetime.utcnow()` with `datetime.now(timezone.utc)` across all modules
- Fix Pydantic `class Config` deprecation in `SkillExecuteRequest` (use `model_config` dict)
- Fix `check_provider_health()` called without `await` in settings endpoint
- Fix bare `except` clause in memory persistence (`dhikr.py`)
- Sync `requirements.txt` with `pyproject.toml` (add missing `pydantic-settings`, `openai`, `click`, `rich`, `aiosqlite`)
- Fix `start.sh` to use `python3` instead of `python` for portability
- Fix `start.sh` to use `docker compose` (v2) instead of deprecated `docker-compose`
- Remove deprecated `version` key from `docker-compose.yml` and `docker-compose.prod.yml`

### Changed
- Improve README with Doctor system, QCA architecture, and self-healing documentation
- Improve CONTRIBUTING guide with current architecture and development workflow
- Update documentation site with Doctor, Federation, and QCA sections
- Update CHANGELOG to follow Keep a Changelog standard

## [v3.0.0] — 2025-01-01

### Added

#### Core System
- Agentic loop with ReAct pattern (Think → Tool → Observe → Repeat, up to 15 iterations)
- Multi-agent orchestration with Shura consensus protocol
- Agent Federation for agent-to-agent communication and capability discovery
- Load balancing via MizanBalancer for intelligent agent selection

#### Quranic Cognitive Architecture (QCA)
- 7-layer cognitive pipeline: Sam', Basar, Fu'ad, ISM, Mizan, 'Aql, Lawh, Furqan
- Yaqin certainty engine — 3-tier epistemic tagging (Ilm, Ayn, Haqq)
- Cognitive method routing: Tafakkur, Tadabbur, Istidlal, Qiyas, Ijma
- Qalb emotional intelligence — tone detection and empathetic response adaptation
- Ruh energy management — task complexity gating and fatigue tracking
- Tawbah error recovery protocol — structured acknowledge → analyze → fix → verify cycle
- Ihsan proactive excellence — automatic suggestions for code tests, backups, optimizations
- Sabr patience engine — long-running task management
- Shukr strength reinforcement — success pattern tracking
- Fitrah innate knowledge — pre-wired concepts for bootstrapping

#### Memory
- Masalik neural pathway network — bio-inspired associative memory with spreading activation
- Three-tier persistent memory: episodic, semantic, procedural (SQLite-backed)
- Memory consolidation with Tafakkur (new connections) and Nisyan (decay/pruning)
- QCA Lawh 4-tier hierarchical memory (immutable → verified → active → conjecture)
- Context compaction tool for long conversations

#### Agents
- Four default agents: Hafiz (General), Mubashir (Browser), Mundhir (Research), Katib (Code)
- 7-level Nafs evolution system (Ammara → Kamila) based on performance
- Browser agent with Playwright support and httpx fallback
- Research agent with ArXiv search and multi-source synthesis
- Code agent with git operations and package management
- Communication agent with email and webhook capabilities

#### Security (Wali Guardian)
- JWT authentication with role-based access control (admin, user, agent, viewer)
- API key support for programmatic access
- Token bucket rate limiting per IP
- Command sandboxing with blocklist
- File path sandboxing with allowed/blocked directories
- SSRF prevention for HTTP requests
- Input validation with length limits
- Security headers middleware (XSS, clickjacking, MIME, CSP, HSTS)
- Audit logging with severity levels
- Izn permission system with 7-tier Nafs-based access control

#### API & Gateway
- FastAPI REST API with full Swagger/OpenAPI documentation
- WebSocket support for real-time streaming
- Multi-channel gateway: Telegram, Discord, Slack, WhatsApp adapters
- In-chat commands (/status, /new, /compact, /help)

#### Plugins & Extensibility
- Plugin system with hot-reload (load/unload/reload without restart)
- Event bus (Nida') — decoupled publish-subscribe communication
- Hook system (Ta'liq) — data transformation pipeline
- Middleware pipeline (Silsilah) — request/response processing
- Extensible skill registry with auto-discovery

#### Built-in Skills
- Web browsing and content extraction
- Data analysis and CSV processing
- Notebook/journaling (Kitab)
- Social collaboration (Majlis)
- Security scanning (Raqib)
- Cloud operations (Sahab)
- Plugin marketplace (Suq)

#### Automation (Qadr)
- Cron job scheduler for recurring tasks
- Webhook trigger system for event-driven automation

#### Self-Healing (Shifa Doctor)
- Comprehensive diagnostic system with 14 checks
- Auto-fix for common issues (missing .env, data directory, SECRET_KEY)
- Environment, configuration, dependencies, database, and network checks
- API endpoint (`/api/doctor`) and CLI command (`mizan doctor`)

#### Providers
- Unified LLM provider interface for Anthropic, OpenRouter, OpenAI, Ollama
- Auto-detection of provider from API keys or model name
- Hot-swap provider switching without restart
- OpenRouter support for 300+ models
- Ollama support for local/offline AI

#### Frontend
- React + Vite + Tailwind CSS web interface
- Real-time chat with WebSocket streaming
- Dark/light theme system
- Pages: Chat, Plugins, Providers, Settings, Developer, Channels, Automation, Security, Scanner, Notebook, Majlis
- Version display and update checker

#### DevOps
- Docker Compose for development and production
- Nginx configuration with optional SSL (Let's Encrypt)
- Production deployment script (`deploy.sh`)
- One-line install script for macOS/Linux (`install.sh`) and Windows (`install.ps1`)
- Self-update system (`update.sh`)
- Makefile with all development commands
- GitHub Actions CI/CD (lint, test, build, Docker)
- Pre-commit hooks configuration
- Version management with bump scripts

#### CLI
- `mizan setup` — first-time setup wizard
- `mizan chat` — interactive terminal chat with model selection
- `mizan serve` — start the API server
- `mizan status` — show system status
- `mizan doctor` — run diagnostics
- `mizan version` — show version

#### Testing
- 484 tests covering agents, API, memory, security, QCA, architecture, and end-to-end scenarios
- pytest with asyncio support
- Coverage reporting
