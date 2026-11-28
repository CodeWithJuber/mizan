# MIZAN Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- ForgeKit 1.26 for MIZAN's development (`docs/forgekit.md`): Jev memory in all five layers (`forge memory`; on with `FORGE_LLM=1 FORGE_JEV_MEMORY=all` and `TYPESAFE_API_KEY` in the environment, never the repository), `portableMemory` so facts, lessons and decisions carry over to new checkouts as reviewed Markdown in `.forge/` (the raw ledger stays local), the first five verified project facts, Pi's `.pi/mcp.json`, and the agent-config guard now also asks a maintainer to read changes to `.claude/skills/` and `.agents/skills/`.
- Personal agents (`docs/personal-agents.md`): every user may make, change, clone, export and import agents of their own (`POST /api/agents` for everyone; `POST /api/agents/{id}/clone`, `GET /api/agents/{id}/export`, `POST /api/agents/import` in `mizan-agent/1`, its persona read by Amanah first). An agent has an owner and is shared or private (`owner_id`, `shared` on `agent_profiles`; administrators' agents are shared by default); a user sees shared agents and their own and changes only their own. Each agent carries its own `settings` (temperature, Claude effort, steps, output tokens, orchestration, permission mode, tool allow/deny lists, connectors, skills, starter prompts, avatar, `learn_skills`), its `effective_tools` and a `provider_warning`.
- A default agent per person (`GET`/`PUT /api/agents/default`): it answers chats that name no agent, the person's Telegram, email and WhatsApp messages and their watchers' tasks (Khalifah when none is chosen). A watcher may name its own `agent_id`.
- `skill_write`: an agent saves a multi-step task that could recur as a SKILL.md in its user's own skills (32 KB at most, refused when Amanah reads an override, concealment or exfiltration in it), offered while the agent's `learn_skills` is on.
- xAI (Grok) and Meta (Muse Spark) as providers (`xai`, `meta`; `XAI_API_KEY`, `META_API_KEY`, also Meta's `MODEL_API_KEY`), OpenAI-compatible, detected from their keys, their models listed live from each provider's `GET /models` (cached an hour) and priced by OpenRouter's live ids (`x-ai/…`, `meta/…`).
- Settings for what were fixed limits: `MIZAN_DEFAULT_PERMISSION_MODE` (`auto`; also `default_permission_mode` in `GET /api/auth/me`), `MIZAN_ALWAYS_ASK_TOOLS` (empty), `MIZAN_TOOL_CALLS_PER_MINUTE` (120), `MIZAN_CHAT_PER_MINUTE` (60), `MIZAN_TOOL_CATALOG_LIMIT` (16) and `MIZAN_TOOL_CATALOG_BYTES` (32 KB).
- ForgeKit for every coding agent working on MIZAN: shared `AGENTS.md` rules, project hooks for Claude Code, Codex, Gemini CLI, Cursor, Copilot and OpenCode (dep-gate, secret redaction, protected paths, completion gate, session memory), and the `forge-cortex` MCP server. Hooks call only the installed CLI, never a script from the checked-out branch, and CI's `agent-config-guard` fails a pull request that changes agent hook or MCP files unless the owner wrote it or a maintainer labelled it `agent-config-reviewed` (`docs/forgekit.md`).
- Owned inference provider, authenticated review/retraction ledger, and separate OpenRouter support drafts.
- Corrected causal byte reply model and finite/existential context reasoning from the preserved research archive.
- Pinned full research importer, local source search, provenance inventory and research invariant checks (CI's weekly own-research job).
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
- Imtihan AGI test: 186 tasks across the base and MIZAN arms, agentic tasks, ARC-style games, and the Quwa ten-faculty profile with human-panel invite links (#143, #145). Debug mode compares one message across both arms.
- Learning with no weights: Ta'allum, Qasd overlays, Tajriba, Tajdid (paired e-value, #143), Wazn, Tadhkir (FSRS, #143) and Ta'lim teaching (#142).
- The web app, rebuilt:
  - Every page has a URL (`/chat/<id>`, `/code`, `/agents`, `/library/*`, `/automations/*`, `/settings/*`), so Back, reload and links work. Signing out leads to a sign-in page.
  - A six-item sidebar (Chat, Code, Agents, Library, Automations, Settings) holds the chat history, grouped by date, searchable, with rename and delete. Administrator pages are under Settings → Developer.
  - The chat:
    - One "Working…" line holds thinking, tools, the plan and Allow / Always / Deny. It folds into "Worked · N steps" when done.
    - One quiet row under each answer carries the Isnad grades, Truth Gate, sources, recall and usage.
    - Messages have "Ask again", "Edit and send again", Copy and Read aloud.
    - Images can be pasted or dropped into the message box.
    - A slash menu lists commands and skills; a "+" menu holds the other options.
  - Answers stream through streamdown: tables, code highlighted by Shiki, and math. Highlighting and math load only when an answer needs them.
  - A design system: shadcn/ui on Base UI, gold on a neutral base in light and dark, self-hosted fonts, and confirm dialogs and toasts in place of the browser's.
  - `PATCH /api/chat/{id}` renames a chat; `GET /api/chat/sessions/list?q=` searches titles and messages.
- Coding, closer to a coding agent:
  - A chat keeps its project (`chat_sessions.workspace_id`, `PATCH /api/chat/{id}`), and a project MIZAN makes in a chat becomes that chat's project, so the next message works on it. Before each message of a bound chat a checkpoint is saved; the user message records it.
  - Checkpoints store each file once by SHA-256 and can be restored, whole or file by file, with an undo (`POST /api/workspaces/{id}/checkpoints/{cid}/restore`). The 30 newest are kept within 50 MiB; an unchanged project reuses its last one. `.git` is no longer part of the project's files.
  - Projects can be renamed, deleted and exported as a zip. Delete and restore wait while a chat works in the project.
  - Approvals: git and sandbox reads run without a prompt; "Always" lasts the chat and can be taken back (`/api/chat/{id}/always`); the prompt for an edit shows its diff.
  - A request beyond MIZAN's recipes (a React or Next.js app, a server, a project with `package.json`) goes to the model with the project's tools only, in a chat someone is reading. MIZAN makes and binds the project, checks every changed file and that a started dev server still runs, gives one repair turn, and reports what it checked. `plan_approved` and `fix` on the chat request stand for the "Approve plan and run" and "Fix with MIZAN" buttons. `MIZAN_WORKSPACE_AGENT`.
  - The web app works this way:
    - `/code` lists the projects; `/code/<id>` shows a project beside its chat (resizable; a Chat | Project switch on a phone), with Preview, Code, Changes and Terminal.
    - Each chat keeps its own project in the browser, and a new chat starts with none (it was one project for every chat).
    - Changes lists what changed since the checkpoint before your last message. A file or everything can be undone, with Undo. A file can be reviewed hunk by hunk with Accept and Reject (`@codemirror/merge`), then saved.
    - Each of your messages with a checkpoint has "Rewind code to before this message", with Undo.
    - "Always" grants show under the message box and can be taken back.
    - "Approve plan and run" follows a plan-mode answer, and "Fix with MIZAN" sits on preview, Python and terminal errors. A started dev server opens in the preview.
- Frontend checks (CI runs the Vitest specs on every run, and the rest on main, weekly and by hand):
  - oxlint, with a cap on warnings and a ratchet so raw colour classes can only decrease (`npm run lint`);
  - Vitest specs;
  - size budgets (the entry bundle dropped from 371 KB to 178 KB gzip; `npm run size`);
  - Playwright tests on desktop and phone against a mock API (`npm run e2e`).
- Connectors (MCP), ready for production (`docs/connectors.md`):
  - the HTTP+SSE transport beside Streamable HTTP; per-connector `timeouts` (`connect_s`, default 30 s or 90 s for `npx`/`uvx` servers; `call_s`, default 120 s);
  - OAuth with a pre-registered client (`oauth: {client_id, client_secret?, scopes?}`, the secret sealed) for servers without dynamic registration, MIZAN's client metadata document (`/api/connectors/oauth/client-metadata.json`), requested scopes, `auth.expires_at`, and sign-out that revokes the tokens (RFC 7009, `POST /api/connectors/{id}/signout`);
  - curated presets checked against each vendor's documentation (`GET /api/connectors/presets`: GitHub, Notion, Linear, Atlassian, Sentry, Stripe, Hugging Face, Cloudflare docs, Vercel, and sandboxed Files and Fetch);
  - the MCP Registry's `v0.1` API (with `v0` as fallback), only active entries, an `official` mark, and a ready `install` (command, arguments, environment) per package for npm, PyPI and OCI;
  - resources as `mcp__<server>__resources_list`/`__resources_read` tools and on the page (`GET /{id}/resources`), prompts (`GET /{id}/prompts`, `POST /{id}/prompts/get`), the server's instructions on its tools' descriptions, re-listing on `tools/list_changed`, progress as the live event `tool_progress`, the server's log messages in the connector's log, and questions from the server (elicitation) answered in the chat (`POST /api/chat/elicitations/{id}`; declined with no one watching);
  - per-tool policy `allow` · `ask` (a person approves every call, even in auto mode) · `never` (`POST /{id}/tools/policy`), new tools offered at once and marked `new` until seen (`POST /{id}/tools/ack`), `POST /{id}/tools/trust {tool}`, and a changed tool's `previous` description, schema and hints;
  - live status (`connected`, `connecting`, `disconnected`, `error`, `auth_required`, `disabled`), `capabilities.sandbox_stdio`/`runner_available`, `POST /{id}/test` (`{ok, latency_ms, tools}`) and `GET /{id}/logs` (last 200 lines); `PATCH` changes the URL, transport, command, arguments, OAuth client and limits, and merges headers and environment per key;
  - `MIZAN_CONNECTORS_KEY`: the data key from the environment, comma-separated for rotation (the first seals, all open; the key file still opens what it sealed).

### Changed
- `MIZAN_ORCHESTRATION` defaults to `hybrid`: MIZAN's recipes (Quran, hadith, computing, code, projects, dates, search) run as before, and the model-driven loop chains tools for the rest, including requests for a connected tool, requests of several parts with no scripture part, and any request Tadbir failed on. Each agent may choose its own mode.
- Every user gets `bash`, `python_exec`, the file tools and `http_get`/`http_post`. For non-admins commands and files run in their own sandbox project (started when needed; a clear error when the server has no runner) and HTTP goes through `net_guard`; administrators keep host execution.
- The agent's persona reaches Lisan (after its own rules: scripture comes only from MIZAN's sources) and the agent loop's prompt without being marked "subordinate".
- A chat that sends no `permission_mode` gets its agent's own, else `MIZAN_DEFAULT_PERMISSION_MODE`. `shahid_submit` follows the chat's mode unless named in `MIZAN_ALWAYS_ASK_TOOLS`. Amanah asks before a model-chosen change only after it found an instruction in the run, not because outside text or an image was read.
- The Nafs level no longer hides tools or gates delegation; Izn's role defaults deny no tool; the Fitrah check of a tool call is advisory (reported in `result["fitrah"]`).
- A default provider switch moves only the agents that follow the default; an agent given its own provider and model keeps them.
- Relicensed from the Apache License 2.0 to the GNU Affero General Public License v3.0 only (`AGPL-3.0-only`), Copyright (C) 2026 Juber Shaikh (Hostlelo). The Bayan package (`packages/bayan/`, MIT), the shadcn/ui components (MIT), the sense-model artifacts (Apache-2.0), the Amiri font (OFL-1.1) and the licensed datasets keep their licences: `NOTICE` lists them, `REUSE.toml` gives every file's licence and `LICENSES/` holds the texts. Contributors sign a Contributor License Agreement (`CLA.md`, checked by `cla.yml`); `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1), `SECURITY.md` (private vulnerability reporting), `CITATION.cff` and a pull request template are added.
- The candidate sense models' pickles (`nlp/artifacts/candidate_*/model.joblib`) are release assets, downloaded by `scripts/fetch_nlp_candidates.py` and checked against the SHA-256 their manifests pin; the default model still ships.
- The research analyzer downloads the Quranic Arabic Corpus morphology on first use from the copy Sarf pins, instead of reading a committed copy.
- The deploy scripts and the workspace-runner installer read the site's public URL from `MIZAN_PUBLIC_URL` instead of a written-in domain.
- CI checks each change once, on GitHub-hosted runners (`ubuntu-24.04`, free for a public repository). A pull request gets typecheck and the unit tests its change reaches (`scripts/ci/plan.py`: Python tests by import graph, Vitest `--changed`); a push to main gets lint (ruff, oxlint and the colour ratchet), typecheck, every unit test, the provenance preflight, the frontend build with its size budget and the Playwright tests, and the Docker images with the runner's import check and Shahid's browser self-test; the weekly run and a run by hand get all of that on Python 3.11 to 3.14 plus the Ruh model tests, the owned-model research invariants and the learning-cycle tests (CPU torch). Coding-workspace isolation runs on main after a merge that touches it, never on a pull request. Main skips its checks only when a full run passed with the same files (`fkirc/skip-duplicate-actions`, pinned to a commit); a pull request's partial run never counts. `pr-check.yml` and `ruh-training.yml` are folded into `ci.yml`, and a newer push to a pull request cancels its older run (`docs/ci-artifacts.md`, What a run checks).
- The repository is prepared to be public. `scripts/ci/public-repo-guard.sh` (CI's first job, `make check`, pre-commit) fails a self-hosted or larger runner, an action not pinned to a full commit SHA, and a `pull_request_target` workflow that checks out code; every workflow reads by default and keeps no checkout credentials. `security.yml` adds dependency review, gitleaks and `reuse lint`; `scorecard.yml` runs OpenSSF Scorecard; Dependabot proposes updates weekly. Deploy Production builds the commit's images on its runner and streams them to the server (`docker save | ssh docker load`, the same rollback), runs in the `production` environment with a required reviewer, connects with an SSH key and a pinned host key from environment secrets (no password, no `deploy/known_hosts` in the repository), and reads the site's URL from a secret (`MIZAN_PUBLIC_URL` on the server). The dated operations do the same and keep their reports on the server, since job logs are public. Auto Release is off until `ENABLE_AUTO_RELEASE` is set; PyPI publishing uses trusted publishing through `pypa/gh-action-pypi-publish` (`docs/ci-artifacts.md`, `docs/deployment.md`).
- A runner older than the backend now answers the session and browser routes with 503 "The private runner on this server predates sandbox sessions" instead of a bare 404. Deploy Production uploads its scripts to a fresh root-only release directory, allows 90 minutes, and fails its last step when the runner was not upgraded.
- New Compose setups select owned inference; hosted model overrides and mem0 calls are disabled in owned mode.
- Own model drafts are excluded from the legacy training exporter; useful general chat and automatic neural learning remain unverified.
- Documentation brought up to date with the code:
  - README, `docs/architecture.md` and the docs site rewritten;
  - every subsystem document checked against its module;
  - interactive Archify diagrams sourced from the code (`docs/diagrams/*.html`);
  - diagram-design SVGs for the README, in light and dark.

### Fixed
- Agent settings that did not work: a deleted agent came back at the next start (its profile is now removed); saving an agent reset its tasks and success record (the live record is kept); a new agent and each user's own copy lacked the knowledge graph, context manager, planner, plugins and registry (`_wire_agent`), and a user's copy did not carry its agent's Nafs level; an agent whose own provider could not start kept that choice and failed (it now follows the default and says so); the temperature, step, output-token and tool-window keys the loop reads could not be set; `capabilities` on `POST /api/agents` was ignored (it is the agent's tool list now).
- WebSocket chats now bind an interactive approval context and send tool and approval events, so a tool that asks is asked instead of refused.
- A chat no longer fails when the store of what was allowed "always" cannot be opened (`MIZAN_DATA_DIR` not writable): it runs with no remembered grants and asks again. A WebSocket chat whose handler fails now closes the socket (1011) instead of leaving the client waiting for a frame.
- Sandbox sessions now have `curl`, so the agent can check its own dev server. `@swc/core` (Vite's React SWC template) could not load in a session: its native addon unpacks into a cache that sat on the non-executable `/tmp`. Caches and user installs now live on the session volume, never synced, for commands, the terminal and stdio servers alike: `XDG_CACHE_HOME` and npm's cache under `/workspace/.cache`, pip user installs under `/workspace/.cache/python-user` with its `bin` on `PATH`. So `npx <tool>` from the terminal or a stdio connector, pip console scripts and compiled wheels run. A React + SWC + Vite project installs, builds and serves in a session. The image sets no npm allow-scripts list: npm 11 runs unlisted install scripts and only warns, and a global list is passed on to every nested `npm install` (`create-next-app`, `create-vite --immediate`, a `postinstall` that installs a sub-project), which npm then refuses with EALLOWSCRIPTS.
- A message sent while a project's chat was still opening (`/code/<id>`) was lost: the chat looked up afterwards started a new session, which stopped the reply and cleared the thread. The message box now appears once the project's chat is settled ("Opening this project's chat…" until then). The browser tests' mock server answers that lookup slowly, so the race is tested every run.
- Sandbox sessions on production answered 404 and `npm install` could not reach the registry, so React and Vite projects could not install, run a dev server or preview. The private runner was still the first install's, which predates sessions and their egress proxy, and deploys never updated it. Now each deploy also moves the managed runner and runtime to the deployed commit's images (when what they are built from changed), proves a real session there (files, npm and PyPI through the egress proxy, confinement) and keeps them only then; otherwise it restores and verifies the previous runner. The site deploy stands either way and the run's last step reports a runner that was not upgraded.
- Plan mode on a chat's project answered from memory ("I can't open files here"). MIZAN's own edit recipe needs a tool that writes, which plan mode does not offer, so the request fell back to words. Now a plan for the chat's project, of any size, is the model's, with the project's reads.
- Editing a project no longer loses code. Files were cut to 12,000 characters (8,000 for repairs) before the model saw them, and its "complete" reply was saved, so the end of a longer file was deleted. Now a long file changes only by SEARCH/REPLACE blocks that match it exactly once, a whole-file reply for it is dropped, and a reply cut at the output limit saves nothing. TypeScript and JSX files are parsed by esbuild, added to the sandbox image.
- "Build me a todo app in React", "Next.js mein blog banao" and "Make me an Express API" were read as conversation: 17 `build_project` and 6 `edit_project` seeds, balanced by 8 conversation seeds of questions about building ("How do I build a React app?").
- Opening a finished chat from history no longer shows "the previous local run has ended".
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

- Connectors:
  - an OAuth connector asked for a new browser authorization after every reconnect: tokens were kept without their expiry, so a new connection sent a stale token and never refreshed. The absolute expiry and the authorization server's metadata are kept now: a later connection refreshes first, and a 401 is answered by a refresh before a new authorization;
  - a server that restarted or a local process that exited left a dead session in use; MIZAN now notices it, reconnects, sends a call that cannot have run once more, and pings idle connections;
  - a slow connect raised out of the tool call; timeouts are a receipt now (`code: connector_timeout`), as are the other failures (`connector_disconnected`, `auth_required`, `secrets_unreadable`, `connector_not_allowed`);
  - the HTTP client of every connection was left open; registry entries offered SSE servers MIZAN could not connect to; "Add local" from the registry dropped package and runtime arguments; the status shown was the stored one (a closed connection still read "connected"), `sandbox_stdio` was always false, and a local server could be added where no runner exists;
  - tools of a connector waiting for sign-in, or that just failed, were still offered to the model; structured results had no size limit, and a resource link in a result could not be read;
  - the connector file was read again for every tool the model was offered (now cached by modification time); OAuth states and per-connection locks were never pruned; the connection limit could close one with a call running; disabling a sandboxed server left its container running.
- Lisan maps a request to a connected tool knowing the user's tool names, and fills its arguments with the chat's last three messages; MIZAN's tool choice folds plurals and -ing/-ed and counts a tool's own name, so "list my issues" finds `list_issues`.

### Security
- Connectors: a tool's behaviour hints (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`) are part of its pin, so a read-only tool that stops saying so is held (pins made before are accepted once and upgraded); connections go only to an address checked a moment before (a pinned transport, no DNS rebinding); OAuth endpoints must use https (`MIZAN_DEV` allows loopback http for development); the OAuth callback is completed only by the user who started the sign-in, and shows "Connected" only after the token exchange; host stdio servers are re-checked against `MIZAN_MCP_HOST_STDIO` and the owner's role at every launch, start with a minimal environment and their own home directory, and their stderr goes to the connector's log; a sealed secret the key no longer opens is an error, never read as "no secret".

### Removed
- Data that may not be redistributed: the Quranic Arabic Corpus morphology (its GPL notice stripped) and the word table and root summary built from it with Quran.com's word-by-word glosses, a Quran.com tafsir excerpt and API responses, a hadith token pool whose upstream gives no terms for its texts, and poetry and Tabari samples with no recorded source (`backend/research/datasets/LICENSES.md`).
- Private material: the owner's research reports, session log and timeline, handoff note, Track-2 report, production validation record, a proposed AgentOps pilot, personal agent settings (`.claude` identity and instincts, `.codex`), and the Ibrah tasks taken from the owner's chats (five synthetic examples ship instead; a deployment's own `ibrah.jsonl` is gitignored). Links to private models, notebooks and endpoints say "available on request".
- The self-hosted runner's billing guard (`scripts/ci/no-github-billing.sh`) and results keeper (`scripts/ci/keep-results.sh`).
- GitHub-billed CI features: the GitHub Pages docs deploy (`docs.yml` only validates; `ENABLE_GITHUB_PAGES` is no longer read), image pushes to ghcr.io (commit images from CI, version and `latest` images from a release), and the compute-server upload of CI output (`scripts/upload_ci_artifact.py`), replaced by `$CI_RESULTS_DIR`.
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