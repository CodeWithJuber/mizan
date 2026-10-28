# MIZAN Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- Owned inference provider, authenticated review/retraction ledger, and separate OpenRouter support drafts.
- Corrected causal byte reply model and finite/existential context reasoning from the preserved research archive.
- Pinned full research importer, local source search, provenance inventory and research invariant CI checks.
- Tadbir: MIZAN's own orchestration. Fahm understands the request, then MIZAN plans, runs every tool through one gate, verifies and expresses the result. The language model (Lisan) is used only for language; in the default `mizan` mode it never controls a tool. Majlis routes work between agents by Thompson sampling.
- Fahm by evidence: language and intent from fitted naive Bayes models (Tamyiz, Lughah, Qasd) replace word lists and cue regexes. The fits include a length exponent and log(1+n) counts (#125, #144).
- Truth and provenance:
  - Isnad grades each claim; Sidq is the truth gate; Ahl al-Dhikr asks sources (#137); Nazm checks the answer's form (#143).
  - Tathabbut cross-checks programs; Hifz reuses checked ones; Muhasaba re-checks answers daily.
  - Hadith-source and Quran-word search (Fihris) and morphology (Sarf).
- Safety and the user's data:
  - per-chat approvals, and held actions for unattended runs;
  - Amanah prompt-injection containment, by evidence;
  - Hudud write limits;
  - Sakk signed receipts and the public reliability scorecard;
  - Iqtisad hard spending limits (#127);
  - Mahw true forget (#128);
  - the Daftar ledger.
- Channels and senses: Bab for Telegram (#130), email and WhatsApp (#141), and Web Push; Sama' voice input (#132); Basar images in chat; Muraqabah watchers held during salah.
- Work: sandboxed coding workspaces and sessions, the Shahid sandboxed browser, MCP connectors, Agent Skills, and Hugging Face read on the server (#123).
- Imtihan AGI test: 194 tasks across the base and MIZAN arms, agentic tasks, ARC-style games, and the Quwa ten-faculty profile with human-panel invite links (#143, #145). Debug mode compares one message across both arms.
- Learning with no weights: Ta'allum, Qasd overlays, Tajriba, Tajdid (paired e-value, #143), Wazn, Tadhkir (FSRS, #143) and Ta'lim teaching (#142).

### Changed
- New Compose setups select owned inference; hosted model overrides and mem0 calls are disabled in owned mode.
- Own model drafts are excluded from the legacy training exporter; useful general chat and automatic neural learning remain unverified.
- Documentation brought up to date with the code:
  - README, `docs/architecture.md` and the docs site rewritten;
  - every subsystem document checked against its module;
  - interactive Archify diagrams sourced from the code (`docs/diagrams/*.html`);
  - diagram-design SVGs for the README, in light and dark.

### Fixed
- Quran requests by topic or wording reach MIZAN's own search again (they had been answered as conversation since the decisive rule of #139):
  - 37 shorter `quran_search` seeds ("<term> kya hai", "ayah about <topic>", bare transliteration), balanced by 19 conversation seeds of everyday dhikr and 3 `build_project` seeds with "about";
  - held-out requests: "Sidratul muntaha kya hai", "Hasbunallahu wa nimal wakeel" and "ayah about patience and prayer" are now decisive;
  - Lisan may map wording to `quran_search` over the user's own words, and a Quran surah Lisan names that the user did not write is refused.

  Ta'lim's gate kept the batch (P(worse) = 0.61). The leave-one-out loss on the seeds both fits share fell from 1.0045 to 0.9907.
- Iqtibas: a message that is the Quran's own words reaches MIZAN's Quran search. The evidence is how much likelier the span is drawn from the Quran than said in ordinary speech, times the share of the message it is, as a Bayes factor on the Quran family. b is fitted by leave-one-out on the seeds and a calibration set of quotes against Quranic formulas said in conversation. "light upon light" is now searched; salam, dhikr and "peace be upon you" stay conversation. `MIZAN_IQTIBAS`.
- Bayan morphology (`ruh_model/tokenizer/morphology.py`, vendored into `packages/bayan`, prepared as 0.2.0):
  - ك, ب, ل, ف or و at the start of a word stays a root letter when only that reading gives a root the lexicon knows (كتاب → كتب, not تاب);
  - a stem after ال, ب or ك is never read as a verb (العلم is `NOUN`, not `VERB_PAST`).

  The root accuracy on the 172-word QAC-derived gold set rose from 79/172 to 81/172 (60/172 in the published 0.1.0). The vendored copy had drifted from upstream; CI now runs `sync_vendor.py --check` and the package tests.

### Removed
- The `DEEP_FACULTY_LOOP` setting ("Active faculty loop") and the `deep_faculty_loop` field of `GET /api/nafs/{agent_id}/faculties`. The setting promised that Basira, Hawa and Hikmah would gate the agent, but no code acted on it. A saved value is ignored. The gates that act are Amanah, approvals, Hudud and Sidq.

## [v3.3.0] — 2026-10-01

### Added
- feat: add bounded private full-size Ruh training run
- feat: add private bounded Kaggle training validation

### Fixed
- fix: prevent learned attention temperature singularities in BF16
- fix: verify pinned training source before allocating GPU
- fix: isolate GPU job dependencies and include setup in deadline
- fix: balance full Ruh training and verify continuation checkpoints
- fix: repair Ruh sentence and dialogue training pipeline

### Changed
- perf: accelerate Ruh continuation with private bounded GPU lifecycle


## [v3.2.1] — 2026-10-01

### Fixed
- fix: expose versioned features through the production API proxy
- fix: use packaged tokenizer imports in public NLP routes


## [v3.2.0] — 2026-10-01

### Added
- Add ruh-remote provider (RunPod GPU) + fix architecture endpoint (#79)
- feat: chat mega-upgrade — session hardening, streaming, transparency, export, artifacts, sandbox, modes, mem0
- feat(bayan): PyPI-ready Bayan tokenizer package (#58)
- feat(tajwid): full tajwid rules engine + API (#60)
- feat(ruh): Ruh use-case study as code — eval, APIs, packaging (#57)
- feat(ruh): sense-disambiguation API track (use-case #1)
- feat(ruh): RootSpace Reader annotator/store/API + dialect->root normalization
- feat(ruh): deterministic root-morphology chat features (sarf)
- Add AYY:vocative sense split — 97→96 senses (#42)
- feat(nlp): Phase-3 Track-2 — candidate data-side artifact (v1.1.0-data)
- feat(nlp): Track-3 candidate_model_v1 — balanced class-weight winner (informational, pending Track-2 merge)
- feat(nlp): lock Phase-3 baseline (post-merge space)

### Fixed
- fix: verify public access and refresh proxy after deployment
- fix: pin the verified production SSH host key
- fix: automate verified production deployments on free Actions runners
- Fix access control, provider contracts, and Ruh training defects
- Fix: poll RunPod /status on IN_PROGRESS (#80)
- fix(ruh): add stream() to RuhModelProvider — chat loop streams via create() single-chunk wrapper; add contract tests
- Fix Ruh router container imports + provider switch allowlist
- fix: container-layout imports — usage.py + commands.py + regression test
- fix: pass RUH_MODEL_PATH through to backend container in prod compose
- fix: chat production-ready — streaming, parallel tools, session restore, memory, copy formats (#74)
- fix: P0-10 webhook delete, P1 tooltips/confirms/pause-resume, P2 drafts/auth label (#73)
- fix: P0 double-/api prefix (Channels/Settings/Automation 404s), RuhModelPage + WelcomePage toast wiring (#72)
- fix: audit batch 3 — WelcomePage deep-link, X2 terminal-in-UI, X3 silent catches, /web_search command (#71)
- Fix: agent no-response after tool call + Ruh 6500% display bug (#70)
- fix: WS multimodal reads text or content key (backend half)
- fix: deep audit batch 1 — functional P0s, responsive P0s, UX systemic (useApi throws on !ok + 401, WS multimodal content, Perception unwrap, Ruh metrics fallback, Channels honest toggle, Majlis/Notebook toasts, tab/page/btn CSS, Toast position, modal height, PasswordInput, Majlis+Scanner nav, delete confirm)
- fix: SettingsPage mobile responsive — tabs stack on small screens (#67)
- fix: WelcomePage login-first flow, no Skip on first visit, honest status (#66)
- fix: SecurityPage login broken — backend returns token, frontend read access_token (#65)
- fix: admin-only registration + wire MIZAN_ADMIN_PASS (#64)
- fix: WS disconnect — absolute wss:// URL + accept-then-close 4401 (#63)
- fix: chat_complete 'Thinking...' freeze — raw YaqinLevel enum in trace metadata
- fix(morphology): handle Quranic alef-wasla U+0671 in analyzer (#61)
- fix: restore PR #59 eval files dropped by stale-tree squash of #60
- Hotfix: live-site stability — auth-aware connection state, map-crash fix, mobile sidebar verify (#56)
- fix(tests): load ArabicMorphAnalyzer by path when torch is absent
- fix(lint): I001 — aliased morphology imports inline in first-party block
- fix(security): require auth on open endpoints + NEUTRAL leak (#53)
- fix(backend): persist users to /data volume (#52)
- fix(frontend): mobile navigation drawer + hamburger menu (#51)
- Fix pymizan setup bugs: wizard key-drop, /data defaults, silent model override (#44)
- fix(nlp): apply 9 Phase-3 sense merges — inventory 115→106 (ontology correction) (#41)
- fix(nlp): eval_phase3 sys.path bootstrap before imports
- fix: ruff I001 in tests after nlp packaging move; gate nlp/ in lint
- fix: ruff I001 in tests after nlp packaging move; gate nlp/ in lint
- fix(nlp): merge-aware Phase-3 eval harness + Amendment A1

### Changed
- docs(eval): honest baseline numbers from eval harness (#59)
- docs: training results + retrain pipeline guide (#54)
- docs(nlp): Track-3 prereg addenda A1 adoption + packaging move


The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [v3.0.0] — 2026-09-29

### Added
- Mizan ECC bundle: docs + skills library covering every command contract (PR #34)
- Bounded AgentOps reference application with finite control evaluation (PR #36)
- Multimodal perception pipeline: Basirah (vision) + Nutq (voice) wired into QCA engine
- Auditory-first processing (Sam' before Basar) per Quran 16:78/17:36
- Perception-Qalb integration: emotional context modulates vision and voice analysis
- `POST /api/perception/analyze` endpoint for multimodal analysis
- WebSocket `multimodal` message type for real-time perception
- DNA-inspired quaternary encoding module (`backend/memory/quaternary.py`)
- Quaternary checksum as 4th integrity layer in Lawh al-Mahfuz
- VectorStore (ChromaDB) integration in Living Memory novelty gate
- Hybrid text + semantic similarity in Living Memory `_find_best_match()`
- `search_entities()` method in KnowledgeGraph (fixes MemoryPyramid layer 4)
- Perception page in frontend UI with image/audio upload
- Image and audio attachment support in chat interface
- `BasirahEngine` and `NutqEngine` exports in perception `__init__.py`
- NutqEngine: language detection (Arabic, Urdu, English) via Unicode analysis
- NutqEngine: 8+ intent types (question, command, greeting, farewell, confirmation, negation, request, statement)

### Fixed
- BasirahEngine: JSON-structured LLM output parsing (was returning empty extracted_text/key_elements)
- BasirahEngine: category detection bug (`"error" in raw_lower and "text"` evaluated boolean inside list)
- NutqEngine: `_adjust_for_tone()` was a no-op, now implements warm/patient/focused text transforms
- KnowledgeGraph: missing `search_entities()` caused MemoryPyramid layer 4 to silently fail
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

## [v3.0.0-beta] — 2025-01-01

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