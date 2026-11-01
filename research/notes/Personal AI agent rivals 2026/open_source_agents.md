# Open-source self-hosted agent rivals: pi, Hermes Agent, OpenClaw (as of 27 October 2026)

Notes for the MIZAN feature-design report. Research date: 27 Oct 2026. "Pub." = the source's publication date. A star count marked "Exa crawl" was read from a GitHub page fetched on 27 Oct 2026. The GitHub REST API was blocked from this session, so these counts could not be cross-checked. Anything dated before roughly Aug 2026 is historical and dated as such.

**Name ambiguity (read first):**
- "pi" here means Earendil's open-source coding-agent harness (pi.dev, github.com/earendil-works/pi). It is not Inflection's "Pi" chatbot (pi.ai).
- "Hermes Agent" means Nous Research's agent (hermes-agent.nousresearch.com, github.com/NousResearch/hermes-agent). Several look-alike sites are **not official**: hermes-agent.org, hermesagents.net, hermes-ai.net. Nous also ships "Hermes" LLMs, which are a different thing.
- "OpenClaw" means Peter Steinberger's assistant, formerly Warelay, CLAWDIS, Clawdbot and Moltbot (github.com/openclaw/openclaw). Third-party sites such as open-claw.me, clawdocs.org, getopenclaw.ai, tryopenclaw.ai and betterclaw.io are **not** the project. Some of them sell competing services, so I treat them as biased.

---

## 1. Release, version, licence, GitHub activity, governance and supported models (per product)

### Takeaway
All three are MIT-licensed and very active.
- **OpenClaw:** ~393k stars. Stewarded by a 501(c)(3) foundation since its creator joined OpenAI. Latest stable is 2026.10.8 (27 Oct 2026).
- **Hermes Agent:** ~258k stars. Owned and driven by Nous Research, a VC-backed company valued at $1.5B in Oct 2026. Latest is v0.22.5 (23 Oct 2026).
- **pi:** ~118k stars. Owned by Earendil Inc., a public benefit corporation, since Apr 2026. Pi 1.0 shipped on 1 Oct 2026 and the latest is v1.4.0 (21 Oct 2026). Pi is also the embedded agent core inside OpenClaw.

### Cited Findings

**OpenClaw: versions**
- Latest stable is **openclaw 2026.10.8**, marked "Latest" on GitHub with a 27 Oct 2026 timestamp. Its notes add the following:
  - security hardening: exec allowlist needs approval for `test -v`; generic node invoke refuses browser proxy commands; sandboxed children cannot run host CLI backends; the secret egress proxy rejects distrusted eMudhra chains;
  - channel fixes for Slack, Matrix, Twitch, Zalo, iMessage and Feishu.
  — [GitHub releases, openclaw/openclaw](https://github.com/openclaw/openclaw/releases) (accessed 27 Oct 2026)
- On the same day, **2026.9.35** shipped as a gateway-only "extended-stable" (LTS-equivalent) release, and **2026.10.10-beta.4** shipped as a pre-release. Earlier October releases were 2026.10.7 (24 Oct; replay-safe session recovery), 2026.10.6, 2026.10.5 and 2026.10.1. — [GitHub releases](https://github.com/openclaw/openclaw/releases) (accessed 27 Oct 2026)
- Per an aggregator, 2026.10.1 (10 Oct) let MCP Apps call their tools while their views stay open, and 2026.10.5 brought Skill Workshop 2.0 and public conversation links. Secondary only. — [releases.sh/openclaw](https://releases.sh/openclaw) (accessed 27 Oct 2026)
- OpenClaw now requires Node 24.22.1+ or 26.12.1+. — [openclaw/openclaw README](https://github.com/openclaw/openclaw) (Exa crawl, 27 Oct 2026)

**OpenClaw: OpenClaw 2.0 (historical, 30 Aug 2026)**
- The Foundation called v2026.8.1 "by far the largest update" in its history: built by 933 contributors (569 first-time) across 16,000+ PRs, after "106 releases in 230 days".
- It added simpler install (reusing existing ChatGPT or Claude subscriptions, API keys and local models), a rebuilt browser app, and shared cloud ("multiplayer") sessions.
— [OpenClaw blog, "OpenClaw 2.0, Accidentally", Hannes Rudolph](https://openclaw.ai/blog/openclaw-2-accidentally/) (pub. 30 Aug 2026)

**OpenClaw: GitHub activity**
- **393,184 stars**, 82,663 forks, 7,694 "open issues". GitHub counts PRs in that open-issues number. Repo created 24 Nov 2025. Top contributor is steipete with 67,827 contributions. — [github.com/openclaw/openclaw](https://github.com/openclaw/openclaw) (Exa crawl, 27 Oct 2026)
- The releases page shows 4.9k open issues, 2.8k open PRs and 722 security advisories. — [GitHub releases](https://github.com/openclaw/openclaw/releases) (accessed 27 Oct 2026)
- Historical: 247,000 stars and 47,700 forks on 2 Mar 2026. — [Wikipedia citing archived GitHub](https://en.wikipedia.org/wiki/OpenClaw) (archive 2 Mar 2026)

**OpenClaw: licence and governance**
- MIT. "Stewarded by the OpenClaw Foundation, an independent 501(c)(3), and has no paid tier, hosted service, or token." — [README](https://github.com/openclaw/openclaw) (Exa crawl, 27 Oct 2026)
- Steinberger announced on 14 Feb 2026 that he was joining OpenAI. Sam Altman said OpenClaw would "live in a foundation as an open source project that OpenAI will continue to support". — [TechCrunch](https://techcrunch.com/2026/02/15/openclaw-creator-peter-steinberger-joins-openai/) (pub. 15 Feb 2026)

**OpenClaw: name history (historical)**
- First published as Warelay on 24 Nov 2025. Then CLAWDIS (3 Dec 2025) and Clawdbot (2 Jan 2026).
- Renamed Moltbot on 27 Jan 2026 after Anthropic's trademark complaint, then OpenClaw about 30 Jan 2026.
— [Wikipedia](https://en.wikipedia.org/wiki/OpenClaw), citing [TechCrunch 28 Jan 2026](https://techcrunch.com/2026/01/27/everything-you-need-to-know-about-viral-personal-ai-assistant-clawdbot-now-moltbot/) and [CNBC 2 Feb 2026](https://www.cnbc.com/2026/02/02/openclaw-open-source-ai-agent-rise-controversy-clawdbot-moltbot-moltbook.html)

**OpenClaw: models**
- "Models and agent harnesses (Claude, Codex, local models) are plugins you can swap." — [README](https://github.com/openclaw/openclaw) (Exa crawl, 27 Oct 2026)
- A Sept/Oct 2026 PR notes that main moved `DEFAULT_MODEL`/`DEFAULT_PROVIDER` off Opus to `openai`/`gpt-5.6-sol`. — [PR #114545](https://github.com/openclaw/openclaw/pull/114545) (date not shown; PR number places it around Aug–Sep 2026)
- The 27 Oct release adds Kimi K3.1 Pro controls. — [GitHub releases](https://github.com/openclaw/openclaw/releases)
- Chinese developers adapted OpenClaw for DeepSeek and WeChat. Tencent and Z.ai launched OpenClaw-based services. — [CNBC](https://www.cnbc.com/2026/03/12/china-openclaw-ai-agent-adoption-tech-companies-government-support-lobster-shrimp.html) (pub. 12 Mar 2026)

**Hermes Agent: versions**
- Latest is **v0.22.5** (GitHub timestamp 23 Oct 2026). It reworked Nous sign-in, added pluggable delegation backends and `hermes import-agent`, and moved `hermes mcp serve` into plugins.
- **v0.22.0 "The Threshold Release"** (14 Oct 2026) added:
  - a guided first-launch setup chat;
  - Connectors for hosted apps such as Linear and Notion;
  - one-click local models via llama.cpp;
  - a ~600-entry plugin catalog;
  - stable SemVer with signed desktop packages and a Microsoft Store build;
  - a `hermes pm` package manager;
  - password-manager sign-in for the browser agent;
  - a "Bot Screen" to watch and take over a bot's desktop;
  - memory providers moved to plugins.
— [GitHub releases, NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent/releases) (accessed 27 Oct 2026)
- v0.21.7 (12 Oct 2026): source installs now follow tagged releases by default. — same source

**Hermes Agent: GitHub activity**
- **257,581 stars**, 56,452 forks. Repo created 22 Jul 2025. Top contributor is teknium1 with 24,821 contributions. — [github.com/NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) (Exa crawl, 27 Oct 2026)
- Conflict: that crawl shows "Open issues: 51,417", while the releases page shows "5k+" issues and "5k+" PRs. The 51k figure is unreliable. — [GitHub releases](https://github.com/NousResearch/hermes-agent/releases)
- Historical: ~214,000 stars and ~40,000 forks on 13 Jul 2026. — [TechCrunch](https://techcrunch.com/2026/07/13/hermes-agent-maker-nous-research-in-talks-for-new-funding-at-1-5b-valuation/) (pub. 13 Jul 2026)

**Hermes Agent: licence, governance and funding**
- MIT, released publicly in Feb 2026. Nous says Hermes "has been cloned over 24 million times" and drives "approximately 2.5% of all global token usage" (company estimate). — [Nous Research, "A Note on Our Fundraise"](https://nousresearch.com/a-note-on-our-fundraise) (pub. 7 Oct 2026)
- $90M Series B at a $1.5B valuation, led by Robot Ventures with NVIDIA, USV, Menlo, Samsung and 1789 Capital. Total funding is $158M. The money funds "Hermes for Businesses". The WSJ reported ~$36M annualised revenue by mid-Sep 2026. — [TechCrunch](https://techcrunch.com/2026/10/07/nous-research-confirms-it-hit-1-5b-valuation-launches-ai-agents-for-business-users/) (pub. 7 Oct 2026)
- Nous Research was founded in 2023 by Jeffrey Quesnelle, Karan Malhotra, Ryan Teknium and Shivani Mitra. It also offers a cloud-hosted Hermes at $20–$200/month. — [TechCrunch](https://techcrunch.com/2026/07/13/hermes-agent-maker-nous-research-in-talks-for-new-funding-at-1-5b-valuation/) (pub. 13 Jul 2026)
- The CEO is Dillon Rolnick. — [TNW](https://thenextweb.com/news/nous-research-90m-1-5bn-hermes-agent-wsj) (pub. 7 Oct 2026)

**Hermes Agent: models**
- "Use any model you want — Nous Portal, OpenRouter, OpenAI, your own endpoint, and many others. Switch with `hermes model`." — [README](https://github.com/nousresearch/hermes-agent/blob/main/README.md) (accessed 27 Oct 2026)
- A review reports a hard 64,000-token context floor: smaller models are rejected at startup. Secondary. — [Dupple review](https://dupple.com/reviews/hermes-agent) (pub. 23 Jun 2026)

**pi: versions**
- **Pi 1.0** shipped on 1 Oct 2026. It added:
  - Codemode (native MCP support, plus non-LLM models such as Jev and image models);
  - extension support for virtual models;
  - deferred tool loading;
  - cache warming for Anthropic models;
  - mid-conversation system messages;
  - full-screen TUI.
- Earendil says "hundreds of thousands of people around the world use Pi every week". It also shipped the experimental **Pi Durable** package.
— [Earendil, "Pi 1.0"](https://earendil.com/posts/pi-1-0/) (pub. 1 Oct 2026)
- Latest is **v1.4.0** (21 Oct 2026). Earlier: v1.3.0 (15 Oct), v1.2.0 (12 Oct), v1.1.0 (7 Oct), v1.0.1–1.0.4 (3–5 Oct). — [GitHub releases, earendil-works/pi](https://github.com/earendil-works/pi/releases) (accessed 27 Oct 2026)

**pi: GitHub activity**
- **117,931 stars**, 15,106 forks, 390 open issues. Created 9 Aug 2025. Top contributors are badlogic (3,957) and mitsuhiko (916).
- "New issues and PRs from new contributors are auto-closed by default. Maintainers review auto-closed issues daily."
— [github.com/earendil-works/pi](https://github.com/earendil-works/pi) (Exa crawl, 27 Oct 2026)

**pi: licence and governance**
- Earendil Inc. (a PBC founded by Armin Ronacher and Colin Daymond Hanna) acquired Pi on 8 Apr 2026. Mario Zechner became a stakeholder and team member. Earendil calls Pi "the minimal agent within OpenClaw". Peter Steinberger is listed among Earendil's backers. — [Earendil, "Announcing Pi & Lefos"](https://earendil.com/posts/announcing-pi-and-lefos/) (pub. 8 Apr 2026)
- "pi is owned by Earendil, the company… I'm… in charge of all pi decisions, along with Armin and Colin." No CLA or DCO. — [Mario Zechner, "I've sold out"](https://www.mariozechner.at/posts/2026-04-08-ive-sold-out/) (pub. 8 Apr 2026)
- Licensing plan:
  - "The core is MIT: there is no discussion."
  - "Certain value added features will be Fair Source", with "closed source additions" alongside.
  - Trademark enforcement is "our main mechanism of protection".
  — [Earendil RFC 0015, Armin Ronacher](https://rfc.earendil.com/0015/) (pub. 30 Mar 2026)
- The repo moved to `earendil-works/pi` and npm moved to `@earendil-works/*`. 0.73.1 was the last release on `@mariozechner`, and 0.74.0 the first under the new scope. — [pi.dev news](https://pi.dev/news/2026/5/7/pi-has-a-new-home) (pub. 7 May 2026)
- Origin (historical): started Aug 2025 as `badlogic/pi-mono`. — [GitHub repo metadata](https://github.com/earendil-works/pi) (created 2025-08-09)

**pi: models**
- 15+ providers with "hundreds of models": Anthropic, OpenAI, Google, Azure, Bedrock, Mistral, Groq, Cerebras, xAI, Hugging Face, Kimi For Coding, MiniMax, NVIDIA, OpenRouter, Ollama and more. API keys or OAuth. Switch mid-session with `/model`. — [pi.dev](https://pi.dev) (accessed 27 Oct 2026)

### Inferences
- OpenClaw's shipping cadence is extreme: four tagged builds on 27 Oct 2026 alone, and "106 releases in 230 days" before 2.0. Self-hosters therefore face constant upgrade churn. That explains why "extended-stable" (LTS) and Doctor-based upgrade recovery now exist.
- Steinberger still dominates contribution counts and published the March 2026 advisories, which suggests he stayed active after joining OpenAI. I found no explicit statement of his current role.
- Pi is effectively the agent kernel in the OpenClaw ecosystem: Earendil says so, and OpenClaw source paths are named `pi-embedded-runner`. A weakness in pi's agent loop can therefore propagate into OpenClaw.
- Two of the three have commercial owners (Nous: $158M raised; Earendil: VC-backed, with Fair Source/proprietary add-ons planned). Only OpenClaw is foundation-governed.

### Gaps
- Exact live star counts could not be verified via the GitHub API (blocked). The Exa-crawl numbers may lag by hours or days.
- OpenClaw Foundation's board, budget and OpenAI's financial role: not found.
- Hermes' open-issue count conflicts between sources (51,417 vs "5k+").

---

## 2. Capabilities in detail (channels, browser/computer control, memory, skills/marketplaces, scheduling, multi-agent, sandboxing, approvals, cost controls, audit logs, voice, mobile)

### Takeaway
OpenClaw and Hermes are full "assistant platforms":
- 25–30+ messaging channels, mixing official bot APIs with unofficial libraries (Baileys for WhatsApp, signal-cli, imsg/BlueBubbles for iMessage, zca-js for Zalo);
- real browser control;
- cron/automations;
- multi-agent features;
- container sandboxes, which are **off by default** in OpenClaw;
- skill marketplaces (ClawHub; the Hermes Skills Hub, which also installs from ClawHub);
- voice and native or desktop apps.

Neither has built-in hard spending caps or tamper-evident action receipts. Pi is deliberately minimal: a coding harness with no built-in permissions, memory, scheduler or channels (Slack via a separate `pi-chat`). It is extended through TypeScript extensions and npm/git "pi packages".

### Cited Findings

#### OpenClaw

**Channels**
- **Built-in or bundled:** A2A 1.0, Reef (E2E-encrypted agent-to-agent messaging between people's OpenClaw agents), Telegram, WebChat and X/Twitter.
- **Official plugins:**
  - Discord, Feishu, Google Chat, IRC, LINE, Matrix, Mattermost, Microsoft Teams, Nextcloud Talk;
  - Nostr (NIP-04), QQ, Raft, Synology Chat, Tlon/Urbit, Twitch, Zalo;
  - Buzz, ClickClack;
  - iMessage "via imsg (JSON-RPC over stdio)… private API actions";
  - Signal "via signal-cli";
  - Slack (Socket Mode, HTTP or relay);
  - SMS via Twilio;
  - WhatsApp;
  - "Zalo personal… via native zca-js (QR login)".
- **External plugins:** WeChat, WeCom, Yuanbao and Zalo ClawBot.
- **Telephony:** a "Voice Call" plugin via Plivo, Telnyx or Twilio.
- Docs say "Start with Telegram. It needs a bot token and no plugin install."
— [OpenClaw docs: Chat channels](https://docs.openclaw.ai/channels) (accessed 27 Oct 2026)

**WhatsApp specifically**
- "production-ready via WhatsApp Web (Baileys)… there is no separate Twilio WhatsApp channel". Login is QR-only.
- "A separate WhatsApp number is recommended", but personal-number and self-chat setups are supported.
- The default DM policy is pairing for unknown senders.
— [OpenClaw docs: WhatsApp](https://docs.openclaw.ai/channels/whatsapp) (accessed 27 Oct 2026)

**Browser control**
- A dedicated agent-only Chrome/Brave/Edge/Chromium profile (`openclaw`), driven over CDP plus Playwright through a loopback control service.
- Also a `user` profile that attaches to the real signed-in Chrome via Chrome DevTools MCP (needs someone at the computer to approve), and a `chrome` extension profile that "works from a phone with nobody at the desk".
- Actions: snapshot (AI/ARIA tree with refs), act (click/type/drag/select), screenshot, PDF, network-request log, emulate.
- Browsing can also route to remote CDP or a node host.
— [OpenClaw docs: Browser](https://docs.openclaw.ai/tools/browser), [Browser agent tools](https://docs.openclaw.ai/tools/browser/agent-tools), [Browser profiles](https://docs.openclaw.ai/tools/browser/profiles) (accessed 27 Oct 2026)

**Memory**
- Plain Markdown in the workspace: `USER.md` (preferences as directives with observed-date and active/superseded metadata), `MEMORY.md` (curated long-term facts), daily `memory/YYYY-MM-DD.md` notes, and `DREAMS.md`.
- A background "dreaming sweep" distils daily notes into MEMORY.md.
- `memory_search`/`memory_get` tools; workspace provenance records exclude untrusted or remote files.
- The Control UI can **import memory from Codex, Claude Code and Hermes**.
— [OpenClaw docs: Memory overview](https://docs.openclaw.ai/concepts/memory) (accessed 27 Oct 2026)

**Context and cost knobs**
- Bootstrap files injected per run are capped at 20,000 chars each and 60,000 total. Tool-result caps scale with the context window. — [OpenClaw docs: Token use and costs](https://docs.openclaw.ai/reference/token-use) (accessed 27 Oct 2026)

**Skills and ClawHub**
- A skill is a directory with `SKILL.md`; workspace skills override bundled or global ones. — [Wikipedia](https://en.wikipedia.org/wiki/OpenClaw), citing [docs.openclaw.ai/tools/skills](https://docs.openclaw.ai/tools/skills)
- ClawHub is the skill marketplace. Since 7 Feb 2026 every published skill is:
  - packaged deterministically and SHA-256 hashed;
  - looked up or uploaded to VirusTotal and analysed by Gemini-powered "Code Insight";
  - auto-approved if benign, warning-labelled if suspicious, blocked if malicious;
  - re-scanned daily.
- The maintainers say: "this is not a silver bullet… A skill that uses natural language to instruct an agent to do something malicious won't trigger a virus signature."
— [OpenClaw blog, VirusTotal partnership](https://openclaw.ai/blog/virustotal-partnership) (pub. 7 Feb 2026)
- The WhatsApp plugin itself falls back to its ClawHub package when npm is unavailable. — [OpenClaw docs: WhatsApp](https://docs.openclaw.ai/channels/whatsapp)

**Scheduling and proactive behaviour**
- "Automations are OpenClaw's built-in scheduler" (`openclaw automations`, alias `cron`):
  - one-shot and recurring jobs, condition watchers, dynamic pacing and a `/loop` shortcut;
  - command and script payloads;
  - delivery to a chat channel or webhook;
  - inbound webhooks (`/hooks/wake`, `/hooks/agent`);
  - **Gmail Pub/Sub triggers**.
— [OpenClaw docs: Automations](https://docs.openclaw.ai/automation/cron-jobs) (accessed 27 Oct 2026)
- The old 30-minute "heartbeat" is now migrated into ordinary automation jobs by `openclaw doctor --fix`. Migration removes heartbeat-specific duplicate suppression. — [OpenClaw docs: Heartbeat migration](https://docs.openclaw.ai/gateway/heartbeat) (accessed 27 Oct 2026)

**Multi-agent**
- Multiple isolated agents in one Gateway, each with its own workspace, state directory, SQLite session store and auth profiles.
- "Bindings" route channel accounts (e.g. two WhatsApp numbers) to agents. Subagent delegation has depth and concurrency limits.
- The workspace "is the default cwd, not a hard sandbox".
— [OpenClaw docs: Multi-agent routing](https://docs.openclaw.ai/concepts/multi-agent) (accessed 27 Oct 2026)
- Shared multiplayer sessions arrived in 2.0. The Foundation says these "are not tenant isolation or a security boundary". — [The Register](https://www.theregister.com/ai-and-ml/2026/08/31/openclaw-20-pours-glitter-on-slow-burning-security-dumpster-fire/5293492) (pub. 31 Aug 2026)

**Sandboxing**
- "Sandboxing is off by default". Backends: Docker, Podman, SSH, OpenShell and Crabbox (a leased cloud box).
- The Gateway always stays on the host. `tools.elevated` is an explicit escape hatch to run exec outside the sandbox.
- Docs: "This is not a perfect security boundary."
— [OpenClaw docs: Sandboxing](https://docs.openclaw.ai/gateway/sandboxing) (accessed 27 Oct 2026)

**Approvals and permissions**
- On a host install the Gateway binds to loopback.
- Unknown DM senders get a pairing code; groups are allowlisted behind a mention gate.
- Container images default to an exposed bind.
- "One trust boundary per gateway… not a hostile multi-tenant security boundary."
- `openclaw security audit` checks config drift and applies auto-fixes.
- Exec allowlists and approvals exist, as advisories about "exec approvals" show.
— [OpenClaw docs: Security](https://docs.openclaw.ai/gateway/security) (accessed 27 Oct 2026)

**Cost controls**
- **No built-in budget enforcement.** The maintainer bot's triage on the budget feature request says: "Current main still lacks built-in token/request budget enforcement". Usage tracking is "provider quota/status and session usage display surfaces, not configured enforcement".
- Work is split across open trackers: #42475 (per-agent spend budgets), #13615, #64463, #9912 and #75841.
— [openclaw issue #58826](https://github.com/openclaw/openclaw/issues/58826) (triage comment 30 Apr 2026)
- A Feb 2026 "cost-guard" extension PR (#17449) was closed. — [PR #17449](https://github.com/openclaw/openclaw/pull/17449) (pub. 15 Feb 2026)
- Still open in Aug 2026 for "Friendly daily spending allowances". — [issue #121729](https://github.com/openclaw/openclaw/issues/121729) (comment 10–18 Aug 2026)

**Audit logs**
- Docs describe "Secrets, storage, and logs — What lands on disk… what transcripts contain" and an "Operator incident response" page. Sessions are stored in per-agent SQLite.
- I found no signed or hash-chained action log. — [OpenClaw docs: Security](https://docs.openclaw.ai/gateway/security) (accessed 27 Oct 2026)

**Voice**
- "Talk mode" covers:
  - a native continuous speech loop on macOS, iOS and Android;
  - realtime WebRTC on iOS for OpenAI realtime;
  - Android Gateway-relay realtime for "GPT-Live" models;
  - **standalone Apple Watch Talk**;
  - Browser Talk;
  - transcription-only sessions.
- For code-heavy replies, `talk.speak` "uses a short spoken message directing the listener to the screen".
— [OpenClaw docs: Talk mode](https://docs.openclaw.ai/nodes/talk) (accessed 27 Oct 2026)

**Mobile and native apps**
- "Native apps for macOS, iOS, Android, Windows, and Linux". Companion "nodes" add voice, Canvas, camera, screen and device-local actions. — [README](https://github.com/openclaw/openclaw) (Exa crawl, 27 Oct 2026)

#### Hermes Agent

**Channels**
- One gateway process covers Telegram, Discord, Slack, Google Chat, WhatsApp, WhatsApp Cloud API, Signal, SMS, Email, Home Assistant (plugin), Mattermost, Matrix, DingTalk, Feishu/Lark, WeCom, Weixin, BlueBubbles and Photon (iMessage), QQ, Yuanbao, Microsoft Teams, LINE, ntfy, Raft, IRC, Buzz and SimpleX.
- The gateway "runs cron jobs, and delivers voice messages".
- "Hermes Relay" (experimental) fronts platforms through an external connector that owns the credentials.
— [Hermes docs: Messaging Gateway](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/) (accessed 27 Oct 2026)

**How each channel is connected**
- **WhatsApp:** "a built-in bridge based on Baileys… emulating a WhatsApp Web session — not through the official WhatsApp Business API". The docs state "Unofficial API — Ban Risk" and recommend a dedicated number. A separate official adapter uses the WhatsApp Business Cloud API, which needs a Meta Business account and a public webhook. — [Hermes docs: WhatsApp](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/whatsapp) (accessed 27 Oct 2026)
- **Signal:** the signal-cli daemon (Java 17+) linked as a secondary device. — [Hermes docs: Signal](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/signal)
- **Telegram:** python-telegram-bot. Voice memos are auto-transcribed. The dashboard can create the bot via QR. — [Hermes docs: Telegram](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/telegram)
- **Others:** Email via IMAP/SMTP, SMS via Twilio, Weixin via the iLink Bot API, Google Chat via Cloud Pub/Sub. There are also an OpenAI-compatible API server (for Open WebUI), A2A, webhooks and a Microsoft Graph webhook listener. — [Hermes docs index (llms.txt)](https://hermes-agent.nousresearch.com/docs/assets/files/llms-7240021af84660c2a79f9fdaf65e9e8f.txt) (accessed 27 Oct 2026)

**Browser and computer control**
- `browser_exec` runs model-written Python against the browser over CDP. Companion tools: `browser_cdp` (raw CDP), `browser_dialog`, and **`browser_vault`**, which fills saved logins, cards, addresses and 2FA codes "without the secrets entering the conversation".
- Browser sources: local headless Chromium (default), cloud browsers (Nous subscription, Browserbase, Browser Use, Firecrawl), Lightpanda, attaching to the user's running Chrome, or a managed copy of the user's real profile.
— [Hermes docs: Browser Automation](https://hermes-agent.nousresearch.com/docs/user-guide/features/browser) (accessed 27 Oct 2026)
- v0.22.0 added a "Bot Screen for watching and taking over a bot's desktop". — [GitHub releases](https://github.com/NousResearch/hermes-agent/releases) (14 Oct 2026)

**Memory**
- `MEMORY.md` (2,200-char limit) and `USER.md` (1,375 chars), injected as a "frozen snapshot" at session start. No auto-compaction: the agent must consolidate itself.
- `session_search` over SQLite FTS5 handles cross-session recall. Optional `write_approval` holds memory writes for review.
- Docs warn that small models "produce the confirmation without the tool call" (a false "I'll remember that").
— [Hermes docs: Persistent Memory](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory) (accessed 27 Oct 2026)
- "Honcho dialectic user modeling". External memory providers (Honcho, Mem0, Supermemory, Hindsight) became plugins in v0.22.0. — [README](https://github.com/nousresearch/hermes-agent/blob/main/README.md); [GitHub releases](https://github.com/NousResearch/hermes-agent/releases)

**Skills and Skills Hub**
- Skills live in `~/.hermes/skills/` and follow the agentskills.io standard. "The agent can modify or delete any skill." Hermes creates skills autonomously after complex tasks and improves them during use.
- The public Skills Hub installs with "Install in Hermes" buttons and source-qualified identifiers: `official/...`, **`clawhub/...` (ClawHub)**, or repository paths. Installs go through a "security scan, action log".
— [Hermes docs: Skills System](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills) (accessed 27 Oct 2026); [README](https://github.com/nousresearch/hermes-agent/blob/main/README.md)
- v0.22.0 added a ~600-entry plugin catalog. — [GitHub releases](https://github.com/NousResearch/hermes-agent/releases)

**Scheduling**
- A `cronjob_manage` tool handles one-shot and recurring jobs, attached skills and delivery to the origin chat or other platforms.
- **"No-agent mode — a script on a schedule, its stdout delivered verbatim, zero LLM involvement".** Event-triggered cron fires from webhooks.
- Per-job model and reasoning-effort pins are "user-owned": "The agent cannot point a job at a different model".
— [Hermes docs: Cron](https://hermes-agent.nousresearch.com/docs/user-guide/features/cron) (accessed 27 Oct 2026)

**Multi-agent**
- `delegate_task` spawns isolated child agents, "up to 10 concurrent subagents by default… no hard ceiling". Results can be validated against an `output_schema`.
- Background completions are delivered "at least once" across restarts.
— [Hermes docs: Subagent Delegation](https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation) (accessed 27 Oct 2026)

**Sandboxing and terminal backends**
- "Six built-in terminal backends — local, Docker, SSH, Modal, Daytona, and Vercel Sandbox — plus plugin backends such as Singularity/Apptainer". Daytona and Modal hibernate when idle. — [README](https://github.com/nousresearch/hermes-agent/blob/main/README.md)
- v0.22.4 added a bwrap (Linux sandboxing) terminal backend to the plugin catalog. — [GitHub releases](https://github.com/NousResearch/hermes-agent/releases) (21 Oct 2026)

**Approvals**
- An eight-layer security model: user allowlists and DM pairing, dangerous-command approval, file-write denylist, container isolation, MCP credential filtering, context-file injection scanning, cross-session isolation and input sanitisation.
- `approvals.mode` takes three values:
  - `smart` (default): "Use an auxiliary LLM to assess risk"; low-risk commands are auto-approved, dangerous ones auto-denied, uncertain ones escalated;
  - `manual`;
  - `off` (YOLO).
- Cron, single-query and unattended (webhook/API) sessions default to `deny`.
- Approval buttons are native on Telegram, Discord and Slack.
— [Hermes docs: Security](https://hermes-agent.nousresearch.com/docs/user-guide/security) (accessed 27 Oct 2026)

**Cost controls**
- The security docs mention only that "An MCP server's declared spend limit still asks" even in YOLO mode. — [Hermes docs: Security](https://hermes-agent.nousresearch.com/docs/user-guide/security)
- I found no general per-user or daily hard budget (see Gaps).

**Audit**
- "The audit log at `~/.hermes/skills/.hub/audit.log` is the review surface" for skill installs. — [teknium1 comment on issue #7072](https://github.com/NousResearch/hermes-agent/issues/7072) (23 May 2026)

**Voice**
- CLI push-to-talk (Ctrl+B) with silence detection; auto voice replies on Telegram and Discord; **Discord voice channels** (the bot listens and speaks).
- A **wake word** ("hey hermes") on CLI, TUI and desktop.
- Local Faster-Whisper STT where supported; TTS via OpenAI, ElevenLabs or NeuTTS.
— [Hermes docs: Voice Mode](https://hermes-agent.nousresearch.com/docs/user-guide/features/voice-mode) (accessed 27 Oct 2026)

**Mobile and desktop**
- Desktop app (signed, Microsoft Store build) and an Android/Termux APT repository. — [README](https://github.com/nousresearch/hermes-agent/blob/main/README.md); [GitHub releases](https://github.com/NousResearch/hermes-agent/releases)
- **No official iOS or Android app.** Nous said its Series B will "build a mobile app". — [Nous Research LinkedIn post](https://www.linkedin.com/posts/nousresearch_as-reported-in-the-wall-street-journal-we-activity-7513650487024381953-I5jM) (pub. 7 Oct 2026)
- A third-party comparison page reports, as of 20 Oct 2026, a mobile engineer kickoff on 13 Oct, no release date, and open GitHub requests #98196 and #126292. Secondary, from an unofficial competing app vendor. — [Herald comparison page](https://heraldapp.dev/compare/herald-vs-official-hermes-app) (pub. 20 Oct 2026)

**Research use**
- "Batch trajectory generation, trajectory compression for training the next generation of tool-calling models." — [README](https://github.com/nousresearch/hermes-agent/blob/main/README.md)

#### pi

**Design and modes**
- "Pi ships with powerful defaults but skips features like sub-agents and plan mode."
- Four modes: interactive TUI, print/JSON, RPC (JSON over stdin/stdout) and a TypeScript SDK ("See OpenClaw for a real-world integration").
- Extensions are TypeScript modules with access to tools, commands, events and the TUI. Sub-agents, plan mode, permission gates, sandboxing and MCP are things "you can build yourself" or install as packages via `pi install npm:…`/`git:…`.
— [pi.dev](https://pi.dev) (accessed 27 Oct 2026)

**Memory and sessions**
- No built-in long-term memory. AGENTS.md and SYSTEM.md load at startup.
- Sessions are **trees** in one file: `/tree` navigates and branches; `/export` writes HTML; `/share` uploads a gist.
- Auto-compaction is customisable. "Extensions can… implement RAG, or build long-term memory."
— [pi.dev](https://pi.dev)

**Pi Durable (experimental)**
- "a new substrate for building long-running agentic applications", MIT. — [Earendil](https://earendil.com/posts/pi-1-0/) (pub. 1 Oct 2026)
- Per a secondary write-up:
  - every step checkpoints, so a new process resumes after a crash;
  - tool calls rerun only when declared safe;
  - requestId deduplication;
  - forks without copying history;
  - multiple attached clients;
  - storage in memory, SQLite or JSONL.
  — [backBone Brief](https://backbonebrief.com/articles/pi-1-0/) (pub. 1 Oct 2026)

**MCP**
- Native MCP arrived in 1.0 via Codemode, a JavaScript sandbox that orchestrates tool calls. Before that, MCP was only via extensions such as pi-mcp-adapter. — [Earendil](https://earendil.com/posts/pi-1-0/); [HN thread](https://news.ycombinator.com/item?id=46844822) (approx. early 2026)
- Armin Ronacher on HN: "Codex in particular is using responses lite internally and relies on codemode for parallel tool calling. So codemode was a given." — [HN comment](https://news.ycombinator.com/item?id=49926377) (approx. Sep–Oct 2026; relative timestamp)

**Channels**
- No messaging gateway in pi itself: "For Slack/chat automation and workflows see earendil-works/pi-chat." — [README](https://github.com/earendil-works/pi)
- Earendil's separate product, Lefos (public alpha, 8 Apr 2026), "communicates with you… over email". — [Earendil](https://earendil.com/posts/announcing-pi-and-lefos/)

**Permissions and sandboxing**
- "Pi does not include a built-in permission system… By default, it runs with the permissions of the user and process that launched it."
- Three containerisation patterns are documented: Gondolin micro-VM extension, plain Docker, and OpenShell.
— [README](https://github.com/earendil-works/pi); [pi.dev docs: Run Pi in an isolated environment](https://pi.dev/docs/latest/containerization) (accessed 27 Oct 2026)
- Third-party packages add permission modes (policy engine plus OS sandbox via `@anthropic-ai/sandbox-runtime`). — [pi-permission-modes](https://pi.dev/packages/pi-permission-modes); [pi-sandbox](https://pi.dev/packages/pi-sandbox) (accessed 27 Oct 2026)

**Cost and telemetry**
- Codemode usage "counts toward the session cost". — [Pi 1.0.0 changelog](https://pi.dev/changelog/releases/1.0.0) (pub. 1 Oct 2026)
- The repo ships `@earendil-works/pi-telemetry` (vendor-neutral telemetry contracts). — [README](https://github.com/earendil-works/pi)
- No hard budget or approval system was found.

**Scheduling, voice, mobile**
- None found built in for pi.

### Inferences
- **Channel breadth is the rivals' main moat.** OpenClaw (~30 channels plus telephony) and Hermes (~28 channels) both rely on **unofficial** clients for WhatsApp (Baileys), Signal (signal-cli) and iMessage (imsg/BlueBubbles). Hermes alone also offers the official WhatsApp Cloud API. The ban risk is acknowledged in Hermes docs.
- **Browser control is real and deep in both platforms.** The most differentiated pieces are driving the user's real signed-in browser (OpenClaw extension profile, usable "from a phone"; Hermes real-profile copy) and filling secrets without exposing them (Hermes `browser_vault`).
- **Neither OpenClaw nor Hermes enforces hard spend limits by default.** OpenClaw's own maintainer triage confirms the absence. This is MIZAN's Iqtisad advantage.
- Hermes' "smart" approvals ask an auxiliary LLM to judge risk. That is the opposite of MIZAN's principle that the model never controls a tool by default.
- Hermes' no-agent cron mode (zero LLM calls) is conceptually close to MIZAN's Hifz re-runs with no model call.

### Gaps
- I found no verifiable built-in hard spending limit in Hermes (only the MCP "declared spend limit"). Hermes' cost-tracking UI was not checked.
- Neither OpenClaw nor Hermes documents a tamper-evident or signed action audit log. I found none, but absence is not proven.
- OpenClaw: exact counts of ClawHub skills as of Oct 2026 were not found.
- pi-chat's capabilities were not examined.

---

## 3. Security incidents (CVEs, malicious skills, exposed instances, Moltbook, prompt injection)

### Takeaway
OpenClaw has the worst record by far:
- one-click RCE (CVE-2026-25253, Jan–Feb 2026);
- dozens of critical authorization and sandbox-escape advisories in Mar–May 2026 and a further batch on 11 Sep 2026;
- the ClawHavoc malicious-skill campaign on ClawHub (341 malicious skills found by Koi in Feb 2026, later "1,000+");
- 40k–135k internet-exposed gateways (Feb 2026);
- repeated published prompt-injection and "agent phishing" exploits.

Moltbook's leak (1.5M agent API keys) was a separate product built for OpenClaw agents. Hermes Agent has had path-traversal and Skills Guard issues (VulDB CVEs, medium/low) and an Oct 2026 auth-fix release. Its policy explicitly says Skills Guard is not a security boundary. Pi has no CVEs that I could find; its docs place prompt injection and the lack of a sandbox outside its security boundary.

### Cited Findings

#### OpenClaw CVEs and advisories

**CVE-2026-25253 (one-click RCE)**
- "OpenClaw… before 2026.1.29 obtains a gatewayUrl value from a query string and automatically makes a WebSocket connection without prompting, sending a token value."
- CVSS 3.1 8.8 (MITRE). CWE-669. NVD published 1 Feb 2026. Vendor advisory GHSA-g8p2-7wf7-98mq. Exploit refs: depthfirst and Ethiack.
— [NVD CVE-2026-25253](https://nvd.nist.gov/vuln/detail/CVE-2026-25253) (pub. 1 Feb 2026; modified 17 Jun 2026)
- Exploitable even on loopback-bound instances because the victim's browser makes the outbound connection. The attacker can change sandbox and tool policies and invoke privileged actions. Fixed in 2026.1.29 (30 Jan 2026). — [The Hacker News](https://thehackernews.com/2026/02/openclaw-bug-enables-one-click-remote.html) (pub. Feb 2026); [SOCRadar](https://socradar.io/blog/cve-2026-25253-rce-openclaw-auth-token/) (secondary)

**Critical authorization advisories, Mar 2026 (historical)**
| ID | Published | Severity | What it allowed | Fixed in |
|---|---|---|---|---|
| GHSA-rqpp-rjj8-7wv8 | 13 Mar 2026 | Critical, 9.9 | WebSocket shared-auth connections could self-declare `operator.admin` | 2026.3.12 |
| GHSA-4jpw-hj22-2xmc (CVE-2026-32922) | Advisory 12 Mar, CVE 29 Mar 2026 | Critical, 9.9 | `device.token.rotate` let a pairing-scoped caller mint admin tokens and "reach real remote code execution on the node" | 2026.3.11 |
| CVE-2026-32916 | 12 Mar 2026 | Critical | Plugin subagent routes ran with "synthetic admin scopes", reachable by unauthenticated requests | 2026.3.11 |
| GHSA-fqw4-mph7-2vr8 | 26 Mar 2026 | Critical, 9.4 | Silent shared-auth reconnect widened `operator.read` to `operator.admin` | 2026.3.25 |
| CVE-2026-33579 | 29 Mar 2026 | Critical | `/pair approve` skipped caller scope subsetting | 2026.3.28 |
| GHSA-9p3r-hh9g-5cmg (CVE-2026-41296) | 31 Mar 2026 | Critical, 9.4 | Sandbox escape via a TOCTOU race in the remote FS bridge | 2026.3.31 |

Sources: [GHSA-rqpp-rjj8-7wv8](https://github.com/openclaw/openclaw/security/advisories/GHSA-rqpp-rjj8-7wv8); [GHSA-4jpw-hj22-2xmc](https://github.com/openclaw/openclaw/security/advisories/GHSA-4jpw-hj22-2xmc); [GHSA-xw77-45gv-p728](https://github.com/advisories/ghsa-xw77-45gv-p728); [GHSA-fqw4-mph7-2vr8](https://github.com/advisories/GHSA-FQW4-MPH7-2VR8); [GHSA-hc5h-pmr3-3497](https://github.com/advisories/GHSA-hc5h-pmr3-3497); [GHSA-9p3r-hh9g-5cmg](https://github.com/openclaw/openclaw/security/advisories/GHSA-9p3r-hh9g-5cmg)

**Further critical items, Apr–Jul 2026 (from the GitHub Advisory Database listing)**
- CVE-2026-41294: CWD `.env` injection leading to config takeover (1 Apr).
- CVE-2026-41329: heartbeat context inheritance bypasses the sandbox via `senderIsOwner` (2 Apr).
- CVE-2026-43585 and CVE-2026-44109 (17 Apr).
- CVE-2026-43575, -43578 and -43581: auth bypass, privilege escalation and sandbox network binding, all before 2026.4.10 (6 May).
- CVE-2026-8634: Crabbox environment-variable exposure (14 May).
- GHSA-w4v6-g3wm-w36c: QQBot admin commands skip DM-only policy (2 Jul).
- CVE-2026-66418: "OpenClaw Dashboard v3.0.0" stored XSS (30 Jul). This may be a third-party dashboard; unclear.
- CVE-2026-100551: iOS app does not enforce saved Gateway TLS pins, 2026.7.1–2026.8.11 (26 Sep, critical, unreviewed).
— [GitHub Advisory Database query "openclaw severity:critical"](https://github.com/advisories?query=openclaw+severity%3Acritical) (accessed 27 Oct 2026; 39 critical advisories listed)

**11 Sep 2026 batch**
- High: "Exec approvals could outlive their reviewed working directory" (GHSA-3mq7-q27j-mq7q).
- High: "WhatsApp login tool could reach non-owner turns" (GHSA-9m4p-cqp4-jppq).
- Moderate: OpenAI-compatible transport could send provider credentials to the wrong endpoint; Unicode fallback could escape workspaceOnly roots; Slack file downloads could miss authorization; iOS deep-link logs could expose credentials; and others.
— [openclaw/openclaw Security Advisories](https://github.com/openclaw/openclaw/security/advisories/) (accessed 27 Oct 2026)

**Total CVE count (secondary)**
- "543 CVEs tracked as of September 2026 (jgamblin/OpenClawCVEs tracker)… 212 security advisories". Many CVEs were assigned by third-party CNAs. Secondary, from a commercial competitor blog; not verified. — [betterclaw.io](https://www.betterclaw.io/blog/openclaw-security-2026) (accessed 27 Oct 2026)

#### ClawHavoc and malicious skills
- **341 malicious ClawHub skills** found by a Koi Security audit of 2,857 skills. **335** used fake "Prerequisites" to install Atomic Stealer (AMOS) on macOS, or a keylogging trojan on Windows. Koi named the campaign **ClawHavoc**.
- Lures included ClawHub typosquats, Solana/crypto tools, Polymarket bots, YouTube utilities, auto-updaters and Google Workspace tools.
— [The Hacker News](https://thehackernews.com/2026/02/researchers-find-341-malicious-clawhub.html) (pub. 2 Feb 2026)
- Koi's original blog URL now redirects to Palo Alto Networks (which acquired Koi). That page cites "1,000+ Malicious skills… (Clawhavoc, Jan 2026)". — [koi.ai → Palo Alto Networks](https://www.koi.ai/blog/clawhavoc-341-malicious-clawedbot-skills-found-by-the-bot-they-were-targeting) (accessed 27 Oct 2026)
- Later estimates of "1,184 by Feb 16" and Bitdefender's "~900 of 10,700 skills" come only from secondary aggregators; unverified. — [eSecurity Planet](https://esecurityplanet.com/threats/hundreds-of-malicious-skills-found-in-openclaws-clawhub) (Feb 2026)
- Earlier, Cisco found a third-party skill that exfiltrated data and injected prompts without the user knowing. — [Cisco Blogs](https://blogs.cisco.com/ai/personal-ai-agents-like-openclaw-are-a-security-nightmare) (pub. 28 Jan 2026)
- Response: VirusTotal scanning (see section 2). The Verge reported "over 400 malicious skills were uploaded to ClawHub and GitHub in just one week". — [The Verge](https://www.theverge.com/ai-artificial-intelligence/875393/openclaw-scanning-ai-skills-malware) (pub. 7 Feb 2026)

#### Exposed instances
- **SecurityScorecard STRIKE (9 Feb 2026):**
  - more than 40,000 exposed instances in the first 24 hours, rising to **135,000+** the same day;
  - RCE-vulnerable instances rose from 12,812 to **50,000+**;
  - 53,000+ instances linked to prior breaches;
  - root cause: "Out of the box, OpenClaw binds to `0.0.0.0:18789`".
  — [The Register](https://www.theregister.com/security/2026/02/09/openclaw-instances-open-to-the-internet-present-ripe-targets/5043770) (pub. 9 Feb 2026); [SecurityScorecard blog](https://securityscorecard.com/blog/how-exposed-openclaw-deployments-turn-agentic-ai-into-an-attack-surface/) (pub. 11 Feb 2026; "35.4% of observed deployments flagged as vulnerable")
- **Censys:** ~1,000 → 21,639 in late January (31 Jan 2026); 63,070 live instances confirmed on 31 Mar 2026. Secondary only: I could not open Censys' own post. — [CyberDesserts](https://blog.cyberdesserts.com/openclaw-exposure-numbers-explained/) (pub. 31 Mar 2026)
- **Current state:** docs now say a host install binds to loopback, but "container images default to an exposed bind". — [OpenClaw docs: Security](https://docs.openclaw.ai/gateway/security) (accessed 27 Oct 2026)

#### Moltbook leak (separate product)
- Moltbook was a social network for AI agents, launched by Matt Schlicht on 27 Jan 2026. — [Wikipedia](https://en.wikipedia.org/wiki/OpenClaw)
- Wiz found a misconfigured Supabase (no RLS) with the key in client-side JS. It exposed "1.5 million API authentication tokens, 35,000 email addresses, and private messages between agents", with full read and write access.
- Only ~17,000 human owners stood behind 1.5M agents. Fixed "within hours".
— [Wiz blog, Gal Nagli](https://www.wiz.io/blog/exposed-moltbook-database-reveals-millions-of-api-keys) (pub. 2 Feb 2026)
- Moltbook's PSA said some private messages contained third-party credentials such as OpenAI keys. — [Moltbook post](https://www.moltbook.com/post/b0866bcf-2f08-4072-aa71-19c261d50448) (undated)
- Reuters reported "more than 6,000 owners"' emails. This figure conflicts with Wiz's 35,000 total, which includes 29,631 early-access signups. — [Reuters](https://www.reuters.com/legal/litigation/moltbook-social-media-site-ai-agents-had-big-security-hole-cyber-firm-wiz-says-2026-02-02/) (pub. 2 Feb 2026)

#### Prompt-injection and agent-phishing exploits against OpenClaw
- **HiddenLayer (3 Feb 2026):** injected instructions fetched through the heartbeat acted as C2. API keys are "stored in plaintext in the ~/.openclaw/.env file" and were exfiltrated. — [HiddenLayer](https://www.hiddenlayer.com/research/exploring-the-security-risks-of-ai-assistants-like-openclaw)
- **Zenity Labs (4 Feb 2026):** zero-click indirect injection adds an attacker-controlled chat integration as a backdoor, then persists by editing SOUL.md via scheduled tasks. "No software vulnerability is required." — [Zenity Labs](https://labs.zenity.io/post/openclaw-or-opendoor-indirect-prompt-injection-makes-openclaw-vulnerable-to-backdoors-and-much-more)
- **Promptfoo (12 Mar 2026):** a malicious web page made the agent enumerate capabilities, read local documents and broadcast a false "Security incident" message to SMS, email and social sinks. — [Promptfoo](https://www.promptfoo.dev/blog/openclaw-at-work/)
- **Okta (28 Apr 2026):** an agent filling a web form "dumped its entire credential store in the email field". A Sonnet 4.5 agent retrieved a Keychain Wi-Fi password and relayed it via Telegram. — [Okta](https://www.okta.com/newsroom/articles/why-ai-guardrails-are-not-enough/)
- **Varonis "Pinchy" (Jun 2026):**
  - an impersonation email made the agent forward mock AWS keys and SSH credentials, and a CRM export of 247 customers;
  - both generic and strict profiles failed;
  - it did block a phishing URL and a malicious OAuth app.
  Secondary: TNW, not Varonis' own post. — [The Next Web](https://thenextweb.com/news/openclaw-ai-agent-phishing-varonis-pinchy) (pub. 10 Jun 2026)
- **CSA research note:** zero-click exfiltration via Telegram and Discord **link previews**. Injected content makes the agent post a URL carrying secrets, and the platform's preview fetch delivers them before the user sees the message. — [CSA Labs](https://labs.cloudsecurityalliance.org/research/csa-research-note-openclaw-indirect-prompt-injection-2026061/) (date in URL suggests ~Jun 2026)

#### Other OpenClaw harms (historical)
- **MoltMatch (Feb 2026):** an agent created a dating profile without direction. — [Taipei Times](https://www.taipeitimes.com/News/world/archives/2026/02/14/2003852326) (pub. 14 Feb 2026)
- **China (10–11 Mar 2026):** restricted state agencies and banks from running OpenClaw. — [Bloomberg](https://www.bloomberg.com/news/articles/2026-03-11/china-moves-to-limit-use-of-openclaw-ai-at-banks-government-agencies) (pub. 11 Mar 2026)
- **The Register on 2.0:** the Secret Store "values are not encrypted at rest". Sandboxing is "turned off by default". Cited cases: Hannah Fry's agent sharing private info, and an agent that "hacked a gym's waiting list". — [The Register](https://www.theregister.com/ai-and-ml/2026/08/31/openclaw-20-pours-glitter-on-slow-burning-security-dumpster-fire/5293492) (pub. 31 Aug 2026)

#### Hermes Agent
- **Issue #3967 (30 Mar 2026, P0):** two path traversals.
  - `credential_files.py` could mount `../../.ssh/id_rsa` into sandboxes.
  - `quarantine_bundle()` wrote bundle files outside quarantine **before** the security scan.
  Fixed by PR #3986, merged 30 Mar 2026. — [Issue #3967](https://github.com/NousResearch/hermes-agent/issues/3967); [PR #3986](https://github.com/NousResearch/hermes-agent/pull/3986)
- **Issue #7072 (10 Apr 2026):** a complete Skills Guard bypass via `importlib` and string construction let a "safe" community skill exfiltrate all environment variables (reporter's CVSS 7.7).
  - Closed 23 May 2026 as **not a vulnerability**. Policy: "Skills Guard… is a review aid; the boundary for third-party skills is operator review before install." GHSA-vhq2-hm76-j85j was closed unpublished. "No CVE."
  — [Issue #7072](https://github.com/NousResearch/hermes-agent/issues/7072)
- **VulDB-assigned CVEs (vendor "did not respond"):**
  - CVE-2026-9353: Skills Guard injection, up to 2026.4.23, CVSS 4.0 5.5. — [NVD](https://nvd.nist.gov/vuln/detail/cve-2026-9353)
  - CVE-2026-10220: `skills_tool.py` injection, up to 2026.4.30, 5.5, published 1 Jun 2026. — [GHSA-vq96-9529-5crp](https://github.com/advisories/ghsa-vq96-9529-5crp)
  - CVE-2026-14783: `skill_view` path traversal, 2026.5.29.2, 2.1, published 6 Jul 2026. — [GHSA-xq87-v97r-jw5g](https://github.com/advisories/GHSA-xq87-v97r-jw5g)
- **PR #71723 (date not shown):** the unsigned skills index could stamp `source="official"` and so grant "builtin" trust that allowed dangerous scan verdicts. — [PR #71723](https://github.com/NousResearch/hermes-agent/pull/71723)
- **v0.21.6 (8 Oct 2026), security fixes:**
  - dashboard rate-limit bypass via a spoofed `X-Forwarded-For`;
  - a native sign-in redirect that could allow session takeover;
  - untrusted git clean/smudge filters;
  - email-gateway sender spoofing via quoted `From` display names.
  — [Hermes GitHub releases](https://github.com/NousResearch/hermes-agent/releases)
- I found no reported mass malicious-skill campaign specific to the Hermes Skills Hub. Note, however, that Hermes installs `clawhub/...` skills. — [Hermes docs: Skills](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills)

#### pi
- Pi's security docs: "Treat model-generated commands and code as untrusted. Pi can read, change, and execute files with the permissions of the account that started it, and it does not ask for approval before every tool call."
- Pi's security policy: "prompt injection from untrusted content, lack of a built-in sandbox, and behavior from user-installed extensions or skills are generally outside the security boundary".
— [pi.dev docs: Run Pi safely](https://pi.dev/docs/latest/security) (accessed 27 Oct 2026)
- Recent hardening: v1.0.0 rejects OAuth responses with a mismatched `iss` (RFC 9207); v1.0.1 pinned `brace-expansion` to fix three GHSA advisories; v1.0.4 "codemode freezes built-ins before scripts run". — [pi GitHub releases](https://github.com/earendil-works/pi/releases) (1–5 Oct 2026)

### Inferences
- OpenClaw's critical bugs cluster in the **authorization model of the gateway control plane**: scopes, pairing, token rotation, plugin routes, shared auth. That is a large, privileged attack surface attached to a local agent. MIZAN's single-backend design with JWT and Izn should be audited against these same classes: scope self-declaration, token minting and webhook routes that bypass auth.
- Marketplace attacks hit the **instructions layer** (fake "Prerequisites" telling users to paste shell commands), not just code. VirusTotal hashing cannot catch natural-language payloads, as OpenClaw itself admits. This supports MIZAN's Amanah approach (evidence-based injection detection and holding poisoned skills).
- Hermes' and pi's explicit "not a security boundary" policies push risk onto users. A selling point for MIZAN could be that its controls *are* boundaries: Hudud audit hook, Sakk receipts, approvals held for unattended runs.
- The link-preview exfiltration class (CSA) applies directly to MIZAN's Telegram channel. Any Telegram send of a model-composed URL is a potential zero-click exfiltration path.

### Gaps
- Censys' primary posts were not opened; the Censys numbers are secondary.
- Varonis' primary post was not opened (TNW only).
- The total OpenClaw CVE count (543) is unverified.
- I found no CVEs or security incidents specific to pi itself beyond dependency pins.
- Koi's original ClawHavoc post is no longer reachable at its URL; the figures come via The Hacker News.

---

## 4. Recurring complaints and feature requests (reliability, cost, memory, setup, channel bans, hallucinated actions; what users say is missing)

### Takeaway
Across GitHub, Hacker News and reviews, the dominant complaints are:
- **cost blow-ups:** idle heartbeats, retry or failover loops, full-history replay;
- **memory that fails silently:** tiny caps, lost recall, false "saved" claims;
- **reliability and setup burden.**

What users ask for:
- hard budgets and idle pause (OpenClaw);
- bigger memory, official mobile apps and cost visibility (Hermes);
- permissions, plan mode, subagents and token efficiency (pi).

### Cited Findings

#### OpenClaw: cost
- **Heartbeat and loop issues:**
  - A heartbeat tool loop consumed **47,659,109 tokens in one day** (17 Feb 2026), after 117M on 15 Feb. — [issue #21597](https://github.com/openclaw/openclaw/issues/21597)
  - "Empty HEARTBEAT.md still costs $20+/week due to full session history replay" (v2026.4.2). — [issue #61690](https://github.com/openclaw/openclaw/issues/61690)
  - "2M+ tokens/day with zero user activity". — [issue #64293](https://github.com/openclaw/openclaw/issues/64293)
  - Default 30-minute heartbeat burned ~2,500 credits/day idle. Closed 12 May 2026 as a duplicate of the still-open activity-based heartbeat issue #14051, which notes "current main… lacks an activity/idle-timeout gate". — [issue #81186](https://github.com/openclaw/openclaw/issues/81186)
- **Failover loop:** v2026.3.28 "caused uncontrolled runaway API calls across all configured LLM providers… entire monthly budget… consumed in approximately 2 days". Auth errors triggered a failover loop. — [issue #60450](https://github.com/openclaw/openclaw/issues/60450) (Mar–Apr 2026)
- **Spend spike PR:** "confirmed $347–$1,382/day Anthropic spend spike", root-caused to tool-loop detection being **disabled by default** and "No spend cap or kill-switch". — [PR #114545](https://github.com/openclaw/openclaw/pull/114545) (circa Aug–Sep 2026)
- **User interviews:** "after speaking with over a hundred OpenClaw users, cost is the topic that comes up in almost every conversation"; examples of $254 in two weeks and $800/month. Vendor blog. — [Manifest](https://manifest.build/blog/how-to-stop-burning-money-on-openclaw/) (pub. 2 Mar 2026)
- **Retry-loop bug:** 761–1,384 paid calls in 60 seconds (25 and 29 Apr 2026), "$20 to $30 burned in a single minute". Secondary, from a consultancy blog. — [OpenClaw Consult](https://openclawconsult.com/lab/openclaw-cost-runaway-fix) (pub. 3 May 2026)

#### OpenClaw: reliability, memory, setup
- A user who switched to Hermes wrote that OpenClaw "would make up steps or get stuck", and that its memory "gets bloated. It drags old, irrelevant conversations into new tasks". — [The Tool Nerd](https://www.thetoolnerd.com/p/i-tested-hermes-agent-for-a-week-openclaw-vs-hermes) (pub. 11 Jun 2026)
- Maintainer "Shadow": "if you can't understand how to run a command line, this is far too dangerous of a project for you to use safely." — [TechCrunch](https://techcrunch.com/2026/01/30/openclaws-ai-assistants-are-now-building-their-own-social-network/) (pub. 30 Jan 2026)
- Platformer: complexity and security risk limit it for casual users. — [Platformer](https://www.platformer.news/moltbot-clawdbot-review-ai-agent/) (Jan 2026)

#### OpenClaw: what users say is missing
- Built-in pre-dispatch budgets: #42475 open; #121729 open as of Aug 2026. — [issue #58826 triage](https://github.com/openclaw/openclaw/issues/58826); [issue #121729](https://github.com/openclaw/openclaw/issues/121729)
- Idle heartbeat pause: #14051. — [issue #81186](https://github.com/openclaw/openclaw/issues/81186)
- Encryption at rest, sandbox on by default, tenant isolation. — [The Register](https://www.theregister.com/ai-and-ml/2026/08/31/openclaw-20-pours-glitter-on-slow-burning-security-dumpster-fire/5293492) (pub. 31 Aug 2026)
- Community products have appeared to fill these gaps, e.g. a ClawMetry "hard budget cap — auto-pause gateway" request. It cites "Anthropic's April 4 billing change" putting OpenClaw users on API billing. That billing claim is unverified. — [vivekchand/clawmetry #555](https://github.com/vivekchand/clawmetry/issues/555) (4 Apr 2026)

#### Hermes Agent: cost
- **Field report (Apr 2026):** "lost approximately 2.6M tokens (~69%)" to context replay. Maintainers replied on 21 Jun 2026 that this premise "doesn't hold". — [issue #5563](https://github.com/NousResearch/hermes-agent/issues/5563)
- **Scheduled tasks:** "Every time a task ran, the output was being passed back through Hermes… four AI API calls… unexplained credit consumption on a day I had not interacted". — [Benjamin Lim](https://limbenjamin.com/articles/why-hermes-agent-is-not-for-me.html) (pub. 2 Oct 2026)
- **Tool-schema overhead:** "~14,000 tokens" of tool listing per call. Biased source (an OpenClaw reseller). — [getopenclaw.ai](https://www.getopenclaw.ai/blog/openclaw-vs-hermes-agent) (undated)

#### Hermes Agent: memory
- `state.db` SQLite corruption killed `session_search`. Fixed with auto-recovery and `hermes db repair` (#43149). — [issue #5563](https://github.com/NousResearch/hermes-agent/issues/5563) (maintainer reply 21 Jun 2026)
- The 2,200-char MEMORY.md limit was called "critically small". It is still the default and tracked as feature request **#5320**. — same source
- A two-week user: "It had no recollection of the conversation. We burned tokens 'remembering' nothing." The same user notes the agent "self-evaluates its own success, and it almost always concludes it succeeded." — [cjonsystems Substack](https://cjonsystems.substack.com/p/i-used-hermes-every-day-for-2-weeks) (pub. 13 Jun 2026)
- Across 1,990 messages, the agent used `session_search` on its own only 9 times. It "almost always compacted [memory] instead" of curating it. — [heyjonny.dev](https://heyjonny.dev/posts/i-think-i-used-the-hermes-agent-wrong/) (undated)
- The docs confirm small models make false memory claims. — [Hermes docs: Memory](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory)

#### Hermes Agent: reliability
- Context-compression "death spiral" (#2153).
- Silent history loss (#886): "Every compression event silently deleted 30–50 turns".
- "systemic fail-silent behavior".
— [Medium technical review, Leif Markthaler](https://medium.com/@leif.markthaler/hermes-agent-a-deep-technical-review-of-nousresearchs-self-improving-ai-agent-b48c64f8e3cc) (pub. 20 Apr 2026)
- v0.22.2 notes that sessions run under 0.22.1 cannot be deleted in 0.22.2. — [Hermes GitHub releases](https://github.com/NousResearch/hermes-agent/releases) (15 Oct 2026)

#### Hermes Agent: setup
- "CLI installs, a Python and Node toolchain, roughly 3.7GB of storage, gateway credentials for each messaging platform". Windows Defender flags the bundled `uv.exe`. — [Dupple](https://dupple.com/reviews/hermes-agent) (pub. 23 Jun 2026); [README](https://github.com/nousresearch/hermes-agent/blob/main/README.md)
- An HN commenter: "Sluggish, very slow to start… Seems over-engineered". — [HN item 48419000](https://news.ycombinator.com/item?id=48419000) (date not visible)

#### Hermes Agent: what users say is missing
- Official iOS/Android app: GitHub #98196 and #126292, per a secondary source. — [Herald page](https://heraldapp.dev/compare/herald-vs-official-hermes-app) (pub. 20 Oct 2026)
- Bigger, auto-scaling memory: #5320.
- Visible session-boundary and replay cost indicators. — [issue #5563](https://github.com/NousResearch/hermes-agent/issues/5563)

#### Channel bans
- Hermes docs: "Using a third-party bridge carries a small risk of account restrictions… Use a dedicated phone number". — [Hermes docs: WhatsApp](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/whatsapp)
- OpenClaw recommends a dedicated number. — [OpenClaw docs: WhatsApp](https://docs.openclaw.ai/channels/whatsapp)
- Model-provider bans: an HN commenter warned that Pi's Anthropic OAuth "they might ban you". — [HN](https://news.ycombinator.com/item?id=46844822) (approx. early 2026)
- Neither doc page reports actual bans (see Gaps).

#### pi: what users say is missing
- "I do miss support for permissions, MCP and perhaps Todos and a server mode." Users answer with extensions such as pi-mcp-adapter and the "oh-my-pi" fork. — [HN "Pi – A minimal terminal coding harness"](https://news.ycombinator.com/item?id=47143754) (608 points; approx. Feb 2026)
- Requests for built-in subagents, which Zechner deferred to packages such as pi-subagents. — [HN "What I learned building an opinionated and minimal coding agent"](https://news.ycombinator.com/item?id=46844822) (421 points; approx. Feb 2026)
- "Pi doesn't even support a permissions model." — [HN item 49907054](https://news.ycombinator.com/item?id=49907054) (approx. Oct 2026)
- Token efficiency: "pi used 2-3x the tokens of codex. pi with subagent pkg used 8x-10x"; another user said it "devoured tokens (much more than Claude)". Anecdotal. — [HN item 49655092](https://news.ycombinator.com/item?id=49655092) (approx. Sep 2026)
- Project gatekeeping: new contributors' issues and PRs are auto-closed. — [README](https://github.com/earendil-works/pi)
- Armin Ronacher describes Zechner as exerting "back-pressure on the issue tracker… through OSS vacations". — [Armin Ronacher](https://lucumr.pocoo.org/2026/4/8/mario-and-earendil/) (pub. 8 Apr 2026)

#### Hallucinated actions
- Hermes docs on memory: "a sentence like 'I've added that to my memory' is just text… the model claimed a save it never made." — [Hermes docs: Memory](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory)
- OpenClaw: agents taking unrequested actions (MoltMatch profile; gym waitlist). — [Taipei Times](https://www.taipeitimes.com/News/world/archives/2026/02/14/2003852326) (14 Feb 2026); [The Register](https://www.theregister.com/ai-and-ml/2026/08/31/openclaw-20-pours-glitter-on-slow-burning-security-dumpster-fire/5293492) (31 Aug 2026)

### Inferences
- Users' top pains map almost one-to-one onto MIZAN subsystems:
  - cost → Iqtisad;
  - false "done/saved" claims → Isnad/Sidq (mawdu' action claims removed);
  - silent memory loss → Daftar provenance;
  - runaway loops on unattended runs → Iqtisad reservations plus deferred approvals.
  These are strong positioning claims. They hold only if MIZAN's equivalents are demonstrably reliable, for example via its AGI test or public scorecard.
- Hermes' memory problems are structural: tiny caps, recall only across session boundaries, and agent self-evaluation. A per-claim provenance ledger with explicit "unverified" grading answers the "it thinks it succeeded" complaint.
- Pi's critics want safety and structure; its fans want minimalism. Pi's users are developers, not MIZAN's target audience.

### Gaps
- I found no first-hand reports (with dates) of WhatsApp or Signal account bans caused by OpenClaw or Hermes; only docs warnings.
- Reddit threads were not reached directly; the Reddit-sourced cost tables come via vendor blogs.
- HN comment dates are relative ("8 months ago"), so the dates above are approximate.

---

## 5. What each does that MIZAN (as described) appears not to do

### Takeaway
The concrete gaps for MIZAN are:
- channel breadth (WhatsApp, Signal, iMessage, Discord, Slack, Email, SMS, voice calls);
- real-browser and computer control, including the user's signed-in browser and secret-safe form filling;
- native mobile, desktop and watch apps with realtime two-way voice and a wake word;
- marketplace-scale skill ecosystems and self-authored skills;
- event triggers (Gmail Pub/Sub, webhooks) and zero-LLM scheduled scripts;
- remote and serverless execution backends;
- interoperability surfaces (A2A, OpenAI-compatible API, MCP Apps, memory import from other agents);
- shared multi-person sessions;
- session branching and crash-durable runs (pi).

Conversely, I found no rival equivalent of MIZAN's hard spend limits, signed hash-chained receipts, true-forget receipts, truth gate or salah-aware delivery.

### Cited Findings (rival capabilities; MIZAN status is from the task brief, not independently verified)

**Channels**
- OpenClaw: ~30 channels including WhatsApp (Baileys), Signal (signal-cli), iMessage (imsg), Discord, Slack, Teams, Matrix, LINE, WeChat, Zalo personal, Nostr, SMS (Twilio), X/Twitter, plus phone calls via Plivo, Telnyx or Twilio. — [OpenClaw docs: channels](https://docs.openclaw.ai/channels)
- Hermes: ~28, including Email (IMAP/SMTP), the official WhatsApp Cloud API alongside Baileys, SimpleX, Home Assistant and ntfy. — [Hermes docs: Messaging](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/)
- MIZAN (per brief): Telegram and Web Push.

**Interactive browser and computer control**
- OpenClaw: an agent-owned Chrome profile; attaching to the user's real signed-in Chrome via extension "from a phone with nobody at the desk"; remote CDP and node-hosted browsers. — [OpenClaw docs: Browser profiles](https://docs.openclaw.ai/tools/browser/profiles)
- Hermes: CDP `browser_exec`, cloud browsers, real-profile copy, `browser_vault` secret fill, and a "Bot Screen" desktop takeover. — [Hermes docs: Browser](https://hermes-agent.nousresearch.com/docs/user-guide/features/browser); [releases v0.22.0](https://github.com/NousResearch/hermes-agent/releases)
- MIZAN (per brief): web search/read and a server code sandbox, with no interactive browser control described.

**Native apps and realtime voice**
- OpenClaw: macOS, iOS, Android, Windows and Linux apps; realtime WebRTC Talk; standalone Apple Watch Talk. — [README](https://github.com/openclaw/openclaw); [Talk mode](https://docs.openclaw.ai/nodes/talk)
- Hermes: wake word, Discord voice-channel conversations, spoken replies on Telegram and Discord, signed desktop app. — [Hermes docs: Voice](https://hermes-agent.nousresearch.com/docs/user-guide/features/voice-mode)
- MIZAN (per brief): local Whisper STT, browser read-aloud, PWA.

**Skill ecosystem**
- ClawHub, with VirusTotal and Code Insight scanning plus daily re-scans. — [OpenClaw blog](https://openclaw.ai/blog/virustotal-partnership) (7 Feb 2026)
- The Hermes Skills Hub installs from official sources, ClawHub and repositories. The agent autonomously creates and improves skills. A ~600-entry plugin catalog. — [Hermes docs: Skills](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills); [README](https://github.com/nousresearch/hermes-agent/blob/main/README.md)
- Pi packages install via npm or git. — [pi.dev](https://pi.dev)

**Triggers and automation**
- OpenClaw: Gmail Pub/Sub triggers, inbound webhooks, condition watchers, command and script payloads. — [OpenClaw docs: Automations](https://docs.openclaw.ai/automation/cron-jobs)
- Hermes: webhook-fired cron and "no-agent mode" scripts with zero LLM calls; cron model pins the agent cannot change. — [Hermes docs: Cron](https://hermes-agent.nousresearch.com/docs/user-guide/features/cron)

**Execution backends**
- Hermes: local, Docker, SSH, Modal, Daytona, Vercel Sandbox and Singularity, with serverless hibernation. — [README](https://github.com/nousresearch/hermes-agent/blob/main/README.md)
- OpenClaw: Docker, Podman, SSH, OpenShell and Crabbox. — [OpenClaw docs: Sandboxing](https://docs.openclaw.ai/gateway/sandboxing)
- MIZAN: one server sandbox per project.

**Multi-agent and multi-user**
- Hermes: up to 10 parallel subagents by default, with JSON-schema-validated outputs. — [Hermes docs: Delegation](https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation)
- OpenClaw: multiple personas bound to separate channel accounts, and shared multiplayer sessions. — [OpenClaw docs: Multi-agent](https://docs.openclaw.ai/concepts/multi-agent); [OpenClaw 2.0 blog](https://openclaw.ai/blog/openclaw-2-accidentally/)
- MIZAN's Majlis (Thompson-sampled routing) is comparable for delegation, but no multiplayer session is described.

**Interop**
- A2A 1.0 channel (OpenClaw) and an A2A page (Hermes). — [OpenClaw docs: channels](https://docs.openclaw.ai/channels); [Hermes docs index](https://hermes-agent.nousresearch.com/docs/assets/files/llms-7240021af84660c2a79f9fdaf65e9e8f.txt)
- An OpenAI-compatible API server for Open WebUI (Hermes). — same Hermes docs index
- MCP Apps (OpenClaw 2026.10.1, secondary). — [releases.sh](https://releases.sh/openclaw)
- Import of memory from Codex, Claude Code and Hermes (OpenClaw). — [OpenClaw docs: Memory](https://docs.openclaw.ai/concepts/memory)
- `hermes import-agent`. — [Hermes releases v0.22.5](https://github.com/NousResearch/hermes-agent/releases)

**Pluggable memory backends**
- Honcho, Mem0, Supermemory and Hindsight plugins (Hermes). — [Hermes releases v0.22.0](https://github.com/NousResearch/hermes-agent/releases)
- "Dreaming" consolidation of daily notes into MEMORY.md (OpenClaw). — [OpenClaw docs: Memory](https://docs.openclaw.ai/concepts/memory)

**Durability and session tooling (pi)**
- Session trees with branch, export and share. — [pi.dev](https://pi.dev)
- Pi Durable: per-step checkpoints, crash resume, idempotent requestIds, forks. — [Earendil](https://earendil.com/posts/pi-1-0/); [backBone Brief](https://backbonebrief.com/articles/pi-1-0/) (1 Oct 2026)
- RPC and SDK embedding. — [pi.dev](https://pi.dev)

**Local models one-click**
- llama.cpp one-click (Hermes v0.22.0). — [Hermes releases](https://github.com/NousResearch/hermes-agent/releases)
- Pi: 15+ providers with mid-session switching. — [pi.dev](https://pi.dev)

**Training data**
- Hermes batch trajectory generation and compression for training tool-calling models. — [README](https://github.com/nousresearch/hermes-agent/blob/main/README.md)

**Operator security tooling**
- `openclaw security audit` with auto-fix and a MITRE ATLAS threat model. — [OpenClaw docs: Security](https://docs.openclaw.ai/gateway/security)

**Rival gaps that MIZAN covers (for positioning)**
- OpenClaw lacks built-in budget enforcement, per maintainer triage. — [issue #58826](https://github.com/openclaw/openclaw/issues/58826)
- OpenClaw's Secret Store is not encrypted at rest and its sandbox is off by default. — [The Register](https://www.theregister.com/ai-and-ml/2026/08/31/openclaw-20-pours-glitter-on-slow-burning-security-dumpster-fire/5293492)
- Hermes treats Skills Guard and approval regexes as "not boundaries". — [issue #7072](https://github.com/NousResearch/hermes-agent/issues/7072)
- Pi has no permission system. — [pi README](https://github.com/earendil-works/pi)
- I found no rival with signed or hash-chained action receipts, verified deletion receipts, arithmetic/scripture quote correction, or prayer-time-aware notification gating.

### Inferences
**Highest-leverage gaps for MIZAN's design report:**
1. **WhatsApp and Email channels.** Prefer official paths (WhatsApp Cloud API, IMAP/SMTP) to avoid Baileys ban risk. Hermes shows the dual-adapter pattern.
2. **Secret-safe interactive browser.** A sandboxed, server-side browser with Hudud-style action limits and Sakk receipts would beat the rivals' records. Note that OpenClaw's real-browser attach is exactly what injection exploits abuse (Promptfoo, Okta).
3. **Realtime voice on mobile and in the PWA.** Keep the rule that Quranic text is never synthesised; OpenClaw's "direct the listener to the screen" pattern for code is analogous.
4. **Event triggers.** Gmail and webhooks feeding Muraqabah, plus zero-LLM scheduled scripts, extending Hifz.
5. **Interop.** An OpenAI-compatible endpoint and A2A, plus memory import from OpenClaw/Hermes/Claude Code into Daftar, with Amanah screening of imported notes.

**Telegram link previews.** These are a known zero-click exfiltration channel (CSA). MIZAN's Telegram adapter should send model-composed links with previews disabled, or only links Sidq has verified.

**Marketplace caution.** Hermes installs ClawHub skills, so a ClawHavoc-style campaign crosses ecosystems. A MIZAN skill marketplace would need Amanah scanning of SKILL.md *instructions* (fake prerequisites), not just code hashing.

### Gaps
- MIZAN's own current channels and browser features were taken from the task brief and CLAUDE.md, not verified in code. For example, CLAUDE.md mentions `automation/triggers` and `webhooks` modules and optional Discord, Slack and WhatsApp tokens. Whether these are live channels in MIZAN should be checked before claiming the gap.
- Whether OpenClaw or Hermes offer any form of verified deletion ("right to be forgotten" with a receipt) was not specifically searched; I found none incidentally.
