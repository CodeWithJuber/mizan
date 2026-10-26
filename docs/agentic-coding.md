# Agentic coding, approvals and preview

A chat can work on a coding project the way a coding agent does. It reads files,
searches them, edits them in place, keeps a plan, and asks before it changes
anything you did not allow. Everything runs inside the normal ReAct loop
(`BaseAgent._agentic_loop`). Every tool call still passes Fitrah, Izn,
provenance and Yaqin checks.

## Tools

When a chat is bound to a project (`workspace_id`), the agent gets these tools:

| Tool | What it does |
|------|--------------|
| `workspace_read` | Read a file. `offset`/`limit` return numbered lines for large files. |
| `workspace_edit` | Replace an exact snippet. It must match once unless `replace_all` is set. A hash lock refuses an edit if the file changed in between. Returns the diff. |
| `workspace_write` | Create or overwrite a whole file. |
| `workspace_glob` | Find files by pattern (`src/**/*.tsx`). |
| `workspace_grep` | Regex search across the project. Bounded: 300 matches, no nested quantifiers, binary files skipped. |
| `workspace_run` | Run a command in the isolated runner (see `coding-workspaces.md`). |
| `todo_write` | Keep a short plan. It is saved per chat and shown live in the UI. |
| `web_search`, `web_browse` | Search the web and read a page. Fetches resolve DNS and refuse private, loopback and metadata addresses on every redirect. |

The tool window grows to 16 tools / 32 KB while a project is bound. An ordinary
chat still sends only `mizan_discover_tools`.

Project limits can be raised with `MIZAN_WORKSPACE_MAX_FILE_BYTES` (max 8 MiB),
`MIZAN_WORKSPACE_MAX_PROJECT_BYTES` (max 100 MiB) and
`MIZAN_WORKSPACE_MAX_FILES` (max 5000).

## Permission modes (Izn approvals)

The chat request carries `permission_mode`. The UI's **Mode** selector sets it.

| Mode | Behaviour |
|------|-----------|
| `auto_edits` (UI default) | Project edits run. Commands, external writes and unknown tools wait for you. |
| `ask` | Every tool that changes something waits for you. |
| `plan` | Read-only tools only. The agent proposes changes instead of making them. |
| `auto` | Every permitted tool runs without prompts. |

A tool that waits for you emits an `approval_request` event. Answer it with
`POST /api/chat/approvals/{id}` and `{"decision": "allow" | "deny" | "always"}`.
`always` allows that tool for the rest of the chat. No answer within 10 minutes
counts as deny. `GET /api/chat/approvals` lists pending requests. Izn rules that
return `APPROVAL_REQUIRED` now prompt you the same way instead of failing.

Requests without `permission_mode` (REST, scheduler, queue) behave as before.

Pending approvals are held in process memory, so the backend must run a single
worker. The production image already does (`uvicorn --workers 1`).

## Live activity events

The chat stream (SSE and WebSocket) carries these extra events:

| Event | Payload |
|-------|---------|
| `tool_start` | `call_id`, `name`, bounded `input` |
| `tool_result` | `call_id`, `ok`, `summary`, `duration_ms`, `diff` |
| `todo` | the plan items |
| `approval_request` / `approval_resolved` | the approval and its decision |
| `skill` | an activated Agent Skill |

Inputs and outputs are redacted: keys that look like tokens, passwords or
cookies are replaced. Text is trimmed to 32 KB per value. Events go only to
transports that asked for them; REST callers and broadcasts never see them.

The chat shows these as an **Activity** card: steps with diffs, the plan, and
Allow / Always / Deny buttons. The card is kept with the finished message.

## The coding workspace (IDE)

Open **Coding workspace** in the sidebar. It has:

- a file tree with new file, new folder, rename and delete
- editor tabs (CodeMirror 6), with save on Ctrl/Cmd+S
- **Terminal**: run a command in the isolated runner
- **Changes**: checkpoints with coloured diffs
- **Preview**:
  - **Web projects** (an `index.html`, or a React/Vite `package.json`) run in
    Sandpack in the browser.
  - **Python files** run with Pyodide, in a sandboxed frame with its own origin
    and a strict CSP. The frame has no access to your session.

The preview loads the whole project in one request:
`GET /api/workspaces/{id}/files`. It returns text files only, up to 3 MB, and
skips `node_modules`, build output and binaries.

## Server sandbox sessions

A session is a private Linux container for one project. It runs on the existing
workspace runner, on the runner's own rootless Docker daemon, never on the
backend host. It has:

- the project files on a disk volume at `/workspace`
- Python 3.13, Node 24, npm, git and bash
- an unprivileged user, no capabilities, a read-only root filesystem and
  resource limits
- **no route to the internet except the egress proxy**, which allows HTTPS only
  to package and code hosts:
  - npm, PyPI, GitHub, `esm.sh`, jsDelivr and unpkg
  - it refuses every non-public address

Start one from the **Sandbox** tab of the Coding workspace, or let the agent call
`workspace_sandbox action=start`. Then:

- **Command** tab and `workspace_run`: commands run in the session. Installed
  packages persist, and the timeout goes up to 900 s.
- **Open shell**: an interactive terminal (xterm.js) over
  `/ws/workspaces/{id}/terminal`. The browser sends its token as a WebSocket
  subprotocol, so it never appears in URLs or logs.
- **Dev server**: starts a long-running process on a port. Two modes:
  - **base**: the server is told its public path, `$MIZAN_PREVIEW_PREFIX/$PORT/`
    (Vite: `--base`). Use it for frameworks that support a base path.
  - **root**: MIZAN strips that prefix. Use it for simple servers such as
    `python3 -m http.server $PORT --bind 127.0.0.1`.
- **Preview → Server** shows the running server in the side panel.

**Preview URLs.** The address is
`/api/workspaces/preview/<capability>/<port>/`. The capability binds the session
and its start nonce with an HMAC derived from the runner token, so the URL works
without a login and stops working when the session stops. Every preview
response is served with `Content-Security-Policy: sandbox …` and no
`allow-same-origin`. The previewed page therefore always has an opaque origin,
even when opened in its own tab. It cannot read MIZAN's storage or cookies.
Cookies and `Clear-Site-Data` from the dev server are dropped. Hot reload
WebSockets are not proxied: use the reload button.

**File sync.** Sync is a three-way merge against the last synced state:

- Editor saves go to the session.
- Files created in the session (by commands, the shell or `npm run build`)
  come back to the project.
- When both sides changed a file, the editor's version wins.

Dependency and build folders are never synced:

- `node_modules`, `.venv` and `__pycache__`
- `dist`, `build` and `.cache`
- similar framework folders

Commands sync automatically. After using the shell, press **Sync**.

**Lifetime.** A session stops after 30 idle minutes, which removes its volume
and installed packages. Project files are already saved in the project.

Runner settings (environment of the `workspace-runner` service):

| Variable | Default | Meaning |
|----------|---------|---------|
| `MIZAN_SESSION_MAX` | 2 | concurrent project sessions |
| `MIZAN_SESSION_MEMORY` / `_CPUS` / `_PIDS` | 768m / 1 / 256 | per-session limits |
| `MIZAN_SESSION_IDLE_SECONDS` | 1800 | idle stop |
| `MIZAN_SANDBOX_EGRESS` | `allowlist` | `off` keeps sessions fully offline |
| `MIZAN_SANDBOX_EGRESS_ALLOW` | built-in list | comma list; `.example.com` allows subdomains |
| `MIZAN_MCP_SESSION_MAX` / `_MEMORY` | 4 / 384m | containers for users' stdio MCP servers |

**Rollout.** Enabling sessions in production needs the runtime and runner
images published for the deployed commit, then the reviewed runner setup run
again (`docs/runner-setup.md`). The runner container now gets 384 MiB and 512
processes. The worker slice's 2 GiB budget is shared by jobs and sessions. Raise
it before raising `MIZAN_SESSION_MAX`.
