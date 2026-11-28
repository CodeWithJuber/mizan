# Agentic coding, approvals and preview

A chat can work on a coding project the way a coding agent does. It reads files,
searches them, edits them in place, keeps a plan, and asks before it changes
anything you did not allow. Every tool call passes Fitrah, Izn, Amanah and
approvals, and leaves a Sakk receipt.

Who does the work depends on the request ([Tadbir](tadbir.md)). MIZAN's own
recipes build and edit small projects themselves (`build_project`,
`edit_project`). A request beyond them is given to the model with the
project's tools only (see [Coding beyond MIZAN's recipes](#coding-beyond-mizans-recipes)).
In `hybrid` and `llm` modes the model-driven ReAct loop
(`BaseAgent._agentic_loop`) also takes what Tadbir does not recognise.

## Tools

When a chat is bound to a project (`workspace_id`), the agent gets these tools:

| Tool | What it does |
|------|--------------|
| `workspace_read` | Read a file. `offset`/`limit` return numbered lines for large files. |
| `workspace_edit` | Replace an exact snippet. It must match once unless `replace_all` is set. A hash lock refuses an edit if the file changed in between. Returns the diff. |
| `workspace_write` | Create or overwrite a whole file. |
| `workspace_glob` | Find files by pattern (`src/**/*.tsx`). |
| `workspace_grep` | Regex search across the project. Bounded: 300 matches, no nested quantifiers, binary files skipped. |
| `workspace_run` | Run a command in the isolated runner (see `coding-workspaces.md`). Without a selected project it runs in the user's private Scratch project. |
| `workspace_sandbox` | Start, stop or inspect the project's server sandbox session; run a dev server and get its preview URL (see below). |
| `workspace_checkpoint`, `workspace_diff` | Keep a checkpoint (the 30 latest are kept; see `coding-workspaces.md`) and review changes against one. |
| `workspace_git` | `status`, `diff`, `log`, `init` or a local `commit`; no remote operations. The three reads lock nothing and write nothing back. |
| `workspace_artifact` | Publish a project file (code, HTML, Markdown or a raster image) as a saved artifact in the chat. |
| `workspace_list`, `workspace_tree`, `workspace_create` | List projects, show a project's files, create one. `workspace_hardware` (administrators) reports the backend's CPU, memory and disk. |
| `todo_write` | Keep a short plan. It is saved per chat and shown live in the UI. |
| `web_search`, `web_browse` | Search the web and read a page. Fetches resolve DNS and refuse private, loopback and metadata addresses on every redirect. |

The tool window grows to 16 tools / 32 KB while a project is bound. An ordinary
chat still sends only `mizan_discover_tools`.

Project limits can be raised with `MIZAN_WORKSPACE_MAX_FILE_BYTES` (max 8 MiB),
`MIZAN_WORKSPACE_MAX_PROJECT_BYTES` (max 100 MiB) and
`MIZAN_WORKSPACE_MAX_FILES` (max 5000).

## Permission modes (Izn approvals)

The chat request carries `permission_mode`. The UI's **Mode** selector sets it. A chat
that sends none (an older client, the WebSocket chat) gets its agent's own
`settings.permission_mode`, else the server's default, `MIZAN_DEFAULT_PERMISSION_MODE`
(`auto` unless an administrator changes it; `GET /api/auth/me` returns it as
`default_permission_mode`, so the UI starts there). Every web and WebSocket chat now
binds an interactive approval context, so a tool that asks is asked, not refused.

| Mode | Behaviour |
|------|-----------|
| `auto` (default) | Every permitted tool runs without prompts. |
| `auto_edits` | Project edits run. Commands, external writes and unknown tools wait for you. |
| `ask` | Every tool that changes something waits for you. |
| `plan` | Read-only tools only. The agent proposes changes instead of making them. |

These actions ask in every mode, `auto` included, even after an `always`, and
are held for the owner when no one is watching the run:

- a tool an administrator named in `MIZAN_ALWAYS_ASK_TOOLS` (empty by default;
  `shahid_submit`, which sends something to a site on your behalf, is the
  usual one to name: [Shahid](shahid.md));
- a change the model chooses after Amanah **found** instructions aimed at the AI in
  outside content the run read (a page, a file, a tool result, pasted text):
  [Amanah](amanah.md). Reading outside content, or attaching an image, with no
  finding asks nothing extra;
- an install of a package Wara' doubts: new, with few versions, its name one slip
  from a popular package ([Wara'](wara.md)). A package no registry has, or one OSV
  lists as malicious, is refused outright; a registry that cannot be reached never
  blocks;
- a `workspace_write` or `workspace_edit` to one of the project's protected paths
  (`.env`, `.env.*`, `*.pem`, `*.key`, `id_rsa*`, `.github/workflows/**` by default;
  each project keeps its own list: [coding-workspaces.md](coding-workspaces.md)).

With no approval context (an internal caller that binds none), each is refused
instead of asked. The prompt's `reason` says which of them asked.

Two more guards act on every tool call, whatever the mode:

- **Satr** covers secrets in a tool's output (keys, tokens, passwords, private keys)
  as `[redacted:<kind>]` before the model, the history, the live events or the
  receipt see it ([Satr](satr.md)). A write that would put such a placeholder back
  into a project file is refused, so a covered secret is never overwritten.
- **Tawbah** counts failed tool calls by signature within one run (the tool, the
  error's class, the message with numbers, paths and ids taken out). The third
  identical failure closes that path: the model is told it failed three times the
  same way and must change approach, the diagnosis is kept (`result.tawbah_loops`),
  and where `MIZAN_LISAN_MODELS` lists the run's model, the rest of the run uses the
  next stronger one (Wazn).

### Host tools for everyone, in their own sandbox

`bash`, `python_exec`, `read_file`, `write_file`, `list_files`, `http_get` and
`http_post` are offered to every signed-in user, not only administrators. For an
administrator they act on the backend host as before. For everyone else they never
touch the host:

- `bash` and `python_exec` run in the user's own sandbox session
  (`workspace.session_client`): the chat's project, or their private Scratch project
  when the chat has none, started when it is not running. A runner without
  sessions runs them as one-shot isolated jobs. With no runner the tool says
  "Sandbox runner is not available on this server; ask the admin to set it up
  (docs/runner-setup.md)".
- `read_file`, `write_file` and `list_files` work on that project's files (synced with
  a running session before and after).
- `http_get` and `http_post` go through the connectors' `net_guard`: public
  addresses only, every redirect checked again, so no one reaches this server's own
  network (other containers, metadata services, `connectors.key`).

A tool that waits for you emits an `approval_request` event. Answer it with
`POST /api/chat/approvals/{id}` and `{"decision": "allow" | "deny" | "always"}`.
No answer within 10 minutes counts as deny. `GET /api/chat/approvals` lists
pending requests. Izn rules that return `APPROVAL_REQUIRED` now prompt you the
same way instead of failing.

- **Reads never ask.** `workspace_git` `status`/`diff`/`log` and
  `workspace_sandbox` `status`/`logs` only observe, so they run without a
  prompt, in plan mode too. The other actions of those tools still ask.
- **"Always" lasts the chat.** It is kept for the chat's later messages
  (`chat_always` in `held_actions.db`) and allows one action of an action tool
  (`workspace_git:commit`), not the whole tool. `GET /api/chat/{id}/always`
  lists what you allowed; `DELETE /api/chat/{id}/always/{key}` takes it back,
  also for a run going on now. Erasing the chat erases them. When the store
  cannot be opened (`MIZAN_DATA_DIR` not writable), the chat still runs with no
  remembered grants, so you are asked again; it is never refused for this.
- **The prompt shows the change.** For `workspace_edit` and `workspace_write`
  the request carries `preview {path, diff, truncated, new_file}`, the diff the
  change would make, worked out without writing anything.

Requests without `permission_mode` from an interactive caller get the default mode
described above.

### Runs no one is watching

Watchers, schedules, triggers, queued tasks and messages from the outside
channels (Telegram, email, WhatsApp: [Bab](bab.md)) run while no one can
answer a prompt in the middle of the run. They act as their owner (the
watcher's owner, the queued task's sender, the linked account's user, or for
schedules and triggers the first administrator) through that owner's own
gates. Every action that needs a person is **held** instead of run:

- What goes ahead: reading, private project edits, and programs in MIZAN's
  isolated sandbox (`workspace_run`).
- What is held: host commands, outside writes, connector actions, anything
  Izn asks about, and anything Amanah marked tainted.
- Each held action is stored with its exact parameters and their SHA-256
  (`$MIZAN_DATA_DIR/held_actions.db`) and expires after 24 hours.
- A watcher's notice says what waits and shows **Allow once / Deny** under the
  message, with **what it will do**: the exact parameters and the first 12
  characters of their SHA-256 (the fingerprint). Allow is offered only once
  every parameter can be read there. `GET /api/chat/held` lists your held
  actions with their parameters.
- `POST /api/chat/held/{id}` with `{"decision": "allow" | "deny"}` decides one.
  Add `"params_sha256"` (the fingerprint or the full digest) and the decision
  holds only for exactly the parameters you were shown; the web app and
  Telegram always send it. The Sakk receipt of the decision names the digest.
  It is accepted once, only from the owner, only before it expires, and only
  if the stored parameters still match their digest. An allowed action runs
  exactly as it was held, through your own agent, and its result is posted
  to the chat. Your decision approves that one call (tool plus parameter
  digest) and nothing else, so Izn does not ask again for it.

Pending approvals are held in process memory, so the backend must run a single
worker. The production image already does (`uvicorn --workers 1`).

## Live activity events

The chat stream (SSE and WebSocket) carries these extra events:

| Event | Payload |
|-------|---------|
| `tool_start` | `call_id`, `name`, bounded `input` |
| `tool_result` | `call_id`, `ok`, `summary`, `duration_ms`, `diff` |
| `todo` | the plan items |
| `approval_request` / `approval_resolved` | the approval and its decision (with `preview` for edits) |
| `skill` | an activated Agent Skill |
| `workspace` | `workspace_id`, `name`, `created`: MIZAN made a project and the chat is bound to it |
| `checkpoint` | `workspace_id`, `checkpoint_id`, `checkpoint_kind`, `reused`, `created_at` (or `error`): the project as it was before this message |
| `preview` | `workspace_id`, `port`, `preview_url`: a dev server started in the project's sandbox |

Inputs and outputs are redacted: keys that look like tokens, passwords or
cookies are replaced. Text is trimmed to 32 KB per value. Events go only to
transports that asked for them; REST callers and broadcasts never see them.

The chat shows these as an **Activity** card: steps with diffs, the plan, and
Allow / Always / Deny buttons. The card is kept with the finished message.

## A chat and its project

A chat is bound to at most one project (`chat_sessions.workspace_id`).

- Sending a message with `workspace_id` binds the chat; later messages need no
  id. `PATCH /api/chat/{id}` with `{"workspace_id": "<id>" | null}` binds or
  unbinds (with `title` too, if sent). `GET /api/chat/{id}` and
  `GET /api/chat/sessions/list` return it; `?workspace_id=` lists a project's
  chats.
- A project MIZAN makes in a chat that had none becomes the chat's project, so
  "add dark mode" in the next message works on it. `chat_complete` carries
  `workspace_id`.
- Before each message of a bound chat MIZAN saves a `turn` checkpoint
  ("Before a chat message", never the chat's words). Its id is kept in the user
  message's metadata as `checkpoint {workspace_id, id}` and sent in
  `chat_complete`, so the code can be put back to before that message. When
  nothing changed since the last one, the same checkpoint is reused.
- While a message runs the project is busy: deleting or restoring it answers 409.
  A deleted project unbinds the chat on its next message; naming a deleted
  project is a 404.

## Edits never lose code

MIZAN's own edit recipe shows Lisan each file whole up to 12,000 characters and
up to 48,000 characters for a long one. A long file may change only by
`SEARCH`/`REPLACE` blocks, each applied when its search text matches the file
exactly once; a whole-file reply for a long file is dropped, and edits that do
not apply are listed in the answer. A reply the model cut at its output limit
saves nothing. Changed TypeScript, TSX and JSX files are parsed by esbuild in
the sandbox (the project's own copy, else the one in the runtime image); where
there is none the check says "not run".

## Coding beyond MIZAN's recipes

A React or Next.js app, a server, or a change to a project that installs and
builds (`package.json`, `pyproject.toml`, `requirements.txt`), or one with more
than eight text files or 60 KB, is more than MIZAN's own recipes can see and
check. In the default `mizan` mode such a request is given to the model, with
the project's tools only (Tadbir `_workspace_agent`):

1. **Only when someone answers.** The chat must be read by a person who answers
   approval prompts (the web chat with a `permission_mode`), and
   `MIZAN_WORKSPACE_AGENT` must be `on` (System settings). AGI tests,
   comparisons, watchers, schedules and channels never hand off; there the
   request is answered in words.
2. **Understood by evidence.** Fahm reads the request as one to make
   something, but no blueprint fits; Lisan reads the wording (a question about
   how to build is conversation) and MIZAN checks the mapping
   (`kind: "stack"`).
3. **MIZAN makes the project** when the chat has none and binds the chat to it
   (`workspace` event).
4. **The model works with the project's tools only**: tree, read, glob, grep,
   edit, write, run, sandbox, git, diff, checkpoint and `todo_write`. They are
   sent directly (no `mizan_discover_tools`); any other tool, or another
   project, is refused. What the tools read from the project reaches the model
   fenced as data, and an instruction found in it makes later changes ask. Each
   change goes through the chat's permission mode as usual.
5. **MIZAN checks what changed.** It compares the project's files before and
   after, checks each changed file (references, CSS, JSON, `node --check`,
   `py_compile`, esbuild, unit tests), and checks that a dev server the model
   started still runs. When a check fails, the model gets one turn to repair
   it, with the failure fenced as data.
6. **The answer says what was checked.** The model's words, then MIZAN's check
   section: the files changed or removed and each check. It is verified only
   when checks ran and all passed; the model's words still go through Sidq. A
   checkpoint is saved when files changed.

In plan mode the model reads the project and writes a plan; nothing changes
and nothing is checked. This holds for any request to make or change the
chat's project, small or large: plan mode offers no tool that writes, so
MIZAN's own edit recipe cannot run there. A plan for a project that does not
exist yet is answered in words.

Two fields stand for buttons, never words (Fahm reads "go ahead" as
conversation). They need a `permission_mode` other than `plan`:

- `plan_approved: true` ("Approve plan and run") carries out the plan of the
  previous answer.
- `fix: {"source": "preview" | "server" | "terminal", "error": "..."}` ("Fix
  with MIZAN") asks for an error the project showed to be fixed; it needs the
  chat's project. The error reaches the model fenced as data.

## The coding workspace (IDE)

**Code** in the sidebar (`/code`) lists your projects: create one, open it,
rename it, export it as a zip, or delete it (a project a chat is working in
answers "busy"). Opening a project (`/code/<id>`) shows it beside its chat:

- **The chat** on the left is the project's chat: `?chat=<id>` when given, else
  its newest chat, else a new chat bound to it. The browser remembers each
  chat's project (`mizan_chat_workspaces`, at most 200 chats); the server's
  binding wins whenever a chat loads or a reply names its project. A new chat
  starts with no project.
- **The project** on the right has four tabs:
  - **Preview**: web projects (an `index.html`, or a React/Vite
    `package.json`) run in Sandpack in the browser, and Python files run with
    Pyodide in a sandboxed frame with its own origin and a strict CSP. When a
    reply starts a dev server (the `preview` event), the preview switches to
    that server.
  - **Code**: a file tree (new file, new folder, rename, delete) and editor
    tabs (CodeMirror 6, Ctrl/Cmd+S saves). Files a reply changed reload when it
    finishes, unless they have unsaved edits; leaving with unsaved edits asks
    first.
  - **Changes**: what changed since a checkpoint, by default the one saved
    before your last message. Each file can be undone, and all of them at once;
    each undo saves the current files first and offers **Undo** in its notice.
    Opening a file shows its changes hunk by hunk (CodeMirror's merge view,
    loaded only here) with **Accept** and **Reject** on each; **Save** writes
    what is kept, and a file changed meanwhile is reloaded instead of
    overwritten. Binary files are listed but not merged.
  - **Terminal**: run a command in the isolated runner, or in the project's
    server sandbox when it runs.
- On a phone a **Chat | Project** switch shows one side at a time; on a wider
  screen the divider can be dragged, and its position is remembered.

The chat has the coding controls:

- **Rewind code to before this message**, on each of your messages that has a
  checkpoint: it lists the files that go back, restores them, and offers
  **Undo**. The chat itself is unchanged.
- An edit prompt shows its diff, marked **New file** for a file that does not
  exist yet and with a note when the diff is shortened.
- What you allowed with **Always in this chat** is listed under the message box
  (`Always: Edit files`, `Always: Git commit`); the ✕ takes it back, so MIZAN
  asks again.
- After a plan-mode answer about the chat's project, **Approve plan and run**
  sends `plan_approved` and leaves plan mode (edits allowed, everything else
  still asks).
- **Fix with MIZAN** appears on a preview error, a failed Python run and a
  failed terminal command; it sends the error as `fix` (leaving plan mode for
  that message).
- **Open project** in the chat's header opens the chat's project beside it; a
  dot shows that its server is running.

The preview loads the whole project in one request:
`GET /api/workspaces/{id}/files`. It returns text files only, up to 3 MB, and
skips `node_modules`, build output and binaries.

## Server sandbox sessions

A session is a private Linux container for one project. It runs on the existing
workspace runner, on the runner's own rootless Docker daemon, never on the
backend host. It has:

- the project files on a disk volume at `/workspace`
- Python 3.13, Node 24, npm, git, curl and bash
- npm 11 runs a dependency's install script (esbuild, `@swc/core`, sharp…) and
  only warns when `allowScripts` in `package.json` does not list it; the image
  sets no global allow list, because npm passes one on to every nested
  `npm install` (scaffolders such as `create-next-app`) and refuses it there
- caches and user installs live on the session volume and are never synced:
  `XDG_CACHE_HOME` and npm's cache under `/workspace/.cache`, pip user installs
  under `/workspace/.cache/python-user` (its `bin` is on `PATH`). `/tmp` is not
  executable, so nothing that must run (npx binaries, native addons, console
  scripts) is placed there, in commands, the terminal and stdio servers alike
- an unprivileged user, no capabilities, a read-only root filesystem and
  resource limits
- **no route to the internet except the egress proxy**, which allows HTTPS only
  to package and code hosts:
  - npm (and the Yarn registry), PyPI, GitHub, nodejs.org, `esm.sh`, jsDelivr
    and unpkg
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
| `MIZAN_MCP_SESSION_MAX` / `_MEMORY` / `_CPUS` / `_PIDS` | 4 / 384m / 0.5 / 128 | containers for users' stdio MCP servers |

**Rollout.** Deploys move the managed runner and runtime to the deployed
commit's images and prove a real session (npm and PyPI through the egress proxy,
confinement) before keeping them; a failed check restores the previous runner
([runner-setup.md](runner-setup.md#upgrades-during-deployment)). The runner
container gets 384 MiB and 512 processes. Until a runner serves sessions, the
session routes answer 503 "predates sandbox sessions" instead of 404. The worker
slice's 2 GiB budget is shared by jobs and sessions. Raise it before raising
`MIZAN_SESSION_MAX`.
