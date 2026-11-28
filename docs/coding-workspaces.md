Mizan coding projects persist under `MIZAN_WORKSPACE_ROOT` (default
`MIZAN_DATA_DIR/workspaces`). Each principal has a separate namespace. The API
supports file trees, optimistic file edits, rename/delete of individual files,
checkpoints you can restore, actual diffs, and saved code/HTML/markdown/image
artifacts. Files survive chat and backend restarts.

**Projects.** `PATCH /api/workspaces/{id}` renames one (`{"name"}`), sets its
goal (`{"goal"}`, see Niyyah below) and its protected paths
(`{"protected_paths": [...]}`, below), `DELETE /api/workspaces/{id}` deletes it
(its server session is stopped first) and `GET /api/workspaces/{id}/export.zip`
downloads its files without `.git`.
Delete and restore answer 409 while a chat is working in the project.

**Protected paths.** A `workspace_write` or `workspace_edit` the agent makes to a
protected path asks you in every permission mode, `auto` included and after an
"Always", shows the diff on the prompt, is held for you when no one is watching the
run (a watcher, a schedule), and is refused when there is no one to ask. Each project
keeps its own list in its record (`protected_paths`, returned by `GET /api/workspaces`
and the PATCH); a project with none uses the defaults `.env`, `.env.*` (but not
`.env.example`, `.env.sample` or `.env.template`, which are meant to be committed),
`*.pem`, `*.key`, `id_rsa*`, `.git/**` and `.github/workflows/**`. A pattern with no `/`
matches a file's name at any depth (`.env` is also `config/.env`); one with `/` matches
from the project's root (`**` spans folders), except `.git/…`, which also matches a
nested repository's own folder (`vendor/lib/.git/config`). A pattern starting with `!`
exempts what it matches (`!certs/public.pem`). Send `[]` to protect nothing; at most 100
relative patterns, no `..`. `.git` at the root stays refused outright (below), never
asked. When the project's list cannot be read, the change asks rather than going ahead.
Your own edits in the project editor are not asked: the list guards what the agent
changes. Only `workspace_write` and `workspace_edit` are guarded: a command a run
executes (`echo x > .env`) or the sandbox `write_file` tool is not, so this is a
check in front of the project tools, not a sandbox boundary. A write that would put a
`[redacted:…]` placeholder where the file holds a secret Satr covered is refused
([Satr](satr.md)).

**Checkpoints.** A checkpoint is a manifest of `{path: sha256}`; each file's
bytes are stored once under `checkpoints/objects/<sha[:2]>/<sha>`, so ten
checkpoints of a project that changed one file cost one copy of the rest. A
checkpoint whose files are the same as the newest one is not saved again
(`reused: true`). The 30 newest are kept (`MIZAN_WORKSPACE_MAX_CHECKPOINTS`, at
most 200) within 50 MiB of stored files; objects no checkpoint uses are
deleted. Kinds: `manual` (you), `agent` (the model or MIZAN), `turn` (before a
chat message) and `restore` (before a restore).
`POST /api/workspaces/{id}/checkpoints/{cid}/restore` puts the project back as
it was (`{"paths": [...]}` restores only those files). It saves a "Before
restore" checkpoint first, so a restore can itself be undone, and brings a
running server session up to date. `GET .../checkpoints/{cid}/file?path=` reads
one file as it was. Checkpoints written by older versions (whole files in
base64) are converted the first time they are read.

**`.git` is not part of the project's files.** Glob, grep, checkpoints, diffs,
restore and export skip it, and the file API refuses writes under it (422).
Programs still see it, so `git` works in a run; the runner's 500-entry and
10 MiB caps still count it. Project files have a 1 MiB
limit and projects a 10 MiB/500-entry limit (see `agentic-coding.md` for raising
them). Each user may keep `MIZAN_WORKSPACE_MAX_PROJECTS` projects (default 10,
at most 200; System settings, applied on the next create). The private Scratch
project that plain-chat code runs in and the AGI test's projects do not count.

The `coding_workspace` built-in skill exposes actual `workspace_*` tools to the
agent registry. Authenticated chat binds its selected `workspace_id`; tools
cannot switch that scope or impersonate another user. Coding quality depends on
a model that actually supports tool calls. The current small Ruh model cannot
be described as a coding or vision model merely because these tools exist.

Execution runs in a separate private service. The public backend never executes
project commands locally and receives no Docker socket. It sends a bounded file
snapshot to the runner, which runs Python 3.13, Node 24, shell and git in a new
container with no network, no host mounts or keys, a read-only root filesystem,
1 CPU, 384 MiB, 64 PIDs and a 120-second wall-clock maximum. Both streams are
drained continuously with bounded retention. Job containers are removed before
the service returns. Generated regular files are exported back to the project;
symlinks, device files and oversized exports are rejected. A concurrent editor
change prevents generated files from overwriting the editor's work.

The isolated runtime image includes Matplotlib 3.11.2, NumPy 2.5.4 and Pillow
13.0.0, with their resolved dependencies pinned in
`docker/workspace-runtime-requirements.txt`. These packages are installed while
building the image; a job has no network and does not install packages. Plotting
uses the noninteractive Agg backend, a writable cache in `/tmp`, and one BLAS
thread so it fits the job's process limit. Save a chart as a small PNG, JPEG or
WebP and publish that saved file with `workspace_artifact`. Image artifacts are
limited to 500000 encoded characters (roughly 375 kB of image bytes), which is
smaller than the project file limit.

**ForgeKit in the sandbox.** The runtime image also carries ForgeKit
(`@codewithjuber/forgekit`, the exact version pinned in the Dockerfile and in
`backend/workspace/forgekit.py`, checked by `tests/test_workspace_forgekit.py`).
Three tools run it on the project, in its live session when one runs (installed
packages are there), otherwise in a one-shot job that copies nothing back:

| Tool | Runs | Returns |
|---|---|---|
| `workspace_verify` | `forge verify --json`: the project's own test commands (`npm test`, `pytest -q`, …) | `verdict` (`PASS`, `FAIL`, `INCOMPLETE`, `NOT_CONFIGURED` when ForgeKit finds no test command, `SUSPECT` when a change weakened the tests), `commands` (each with `status`, `exit_code`, `duration_ms`, `counts`), `counts` (total/pass/fail/skipped, when the runner reports them), `detail` (the failing output), `tree` (the files tested), `tree_after`, `bound`, `forge` (version, git `head`, ForgeKit's `dirty_hash`) |
| `workspace_impact` | `forge impact <symbol\|path> --json`: ForgeKit's code graph | `found`, `defined_in`, `direct` (files that use it), `files` (every predicted file), `hops` |
| `workspace_docs_check` | `forge docs sync --base HEAD --json` | `stale` (each doc with the lines that mention a changed name), `changed_files`, `updated` |

The command MIZAN sends calls ForgeKit, node, python, git and `timeout` by their
paths in the image (never a project's own `node_modules/.bin`), puts ForgeKit's
state (`.forge/`: atlas cache, provenance, verifier events) back exactly as it
was so a check changes no project file, stops ForgeKit 20 s before the run's own limit so that cleanup
always runs, and reads the answer after a marker with a fresh random mark.

Git never reads the project's own git configuration. ForgeKit works through a
git directory MIZAN makes under `.cache/` for each run: it borrows the
project's objects (an alternate, read only), its HEAD, index, shallow list and
ignore patterns, and nothing that names a program: not `.git/config`
(`core.fsmonitor`, `diff.external`, filter and textconv drivers), not its hooks,
not `.git/info/attributes`. The project's `.gitattributes` then name drivers
that are defined nowhere, so they run nothing. No system or global git
configuration is read (`GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL=/dev/null`),
and `core.fsmonitor=false`, `core.hooksPath=/dev/null`, `core.pager=cat` and no
attributes or excludes file are set over any file. `diff.external` cannot be
switched off by setting it empty (git then fails to run `""`), which is why the
project's config is never read at all. A test in `tests/test_workspace_forgekit.py`
builds a repository whose config, attributes and `~/.gitconfig` name programs
and checks that none runs. Apart from git, `forge impact` and `forge docs sync`
start nothing (ForgeKit's model adjudication is off: `FORGE_LLM=0`), so they run
none of the project's code and are reads in approval terms. `forge verify` runs
the project's test commands (and `jscpd` from the image's PATH when the
project's `.forge` config asks for its duplicate check), so `workspace_verify`
asks like `workspace_run` and, like it, may run unattended in the sandbox.
MIZAN's own state under `.cache/` is ignored there, so ForgeKit never counts it
as a change.

A project without git history is verified against a throwaway snapshot commit
in that directory: its tests run and the verdict is bound, though ForgeKit's
test-integrity check then has nothing earlier to compare with.
`workspace_docs_check` compares with the project's own git `HEAD` and answers
`code: no_git` without one. An image older than this change answers
`code: forgekit_missing` ("ForgeKit is not installed in this sandbox image; the
runner needs upgrading"); the next deploy's runner upgrade brings it.
A verdict is what the project's own tests report in its sandbox: evidence, not
a proof against a test suite written to lie, since tests are the project's code.

**Verifications are bound to the files they tested.** `workspace_verify` keeps
its verdict in `verifications.json` beside the project's files, keyed by the
digest of the files as they were when the tests started (`tree`, the same
digest a checkpoint of them records), with the digest after the run beside it
(`tree_after`). A verification is current only while the project's files are
the tested ones: any later edit, and any file the run itself wrote (a test
report, a snapshot), makes a new digest, so it reads `stale: true`; restoring
the tested checkpoint brings it back. A verdict is kept only when ForgeKit saw
no change to the code while the tests ran and every file that changed in the
project is one the run wrote; otherwise the answer says `bound: false` and
nothing is kept.
`GET /api/workspaces/{id}/checkpoints` returns `verification` (the record for the
current files, else the newest, with `stale`, `current_tree` and the
`checkpoint_id` holding the tested files) and each checkpoint whose files were
verified carries `verification: {verdict, passed, checked_at}`. Records follow
the checkpoint limit (the newest 30 trees). A verification is bound to the
project's files, not to its installed dependencies.

After rebuilding the runtime image, verify a real chart run and artifact export:

```sh
docker build -f docker/Dockerfile.workspace-runtime -t mizan-workspace-runtime:v1 .
PYTHONPATH=backend:. pytest tests/test_coding_workspace.py::TestRealRuntime -q
```

The chart check runs under the same network, memory, process and user restrictions
as other jobs, persists its generated file, publishes it through the artifact
API, and decodes the returned image. A missing Docker runtime skips these checks;
the CI image-build job must run them before publishing the new runtime tag.

For deployment, provide a dedicated Docker daemon (preferably rootless on an
isolated worker) that has no production containers, credentials or host mounts.
Do not use the production Docker socket. Build the two digest-pinned Dockerfiles,
load the runtime into that daemon, and set a random runner token
of at least 32 characters. The optional `docker-compose.workspace.yml` override
requires `MIZAN_WORKSPACE_DOCKER_SOCKET` to identify that dedicated daemon and
`MIZAN_WORKSPACE_RUNNER_TOKEN` to authenticate the private service. It exposes no
host port. Set `MIZAN_WORKSPACE_RUNNER_UID` and `MIZAN_WORKSPACE_RUNNER_GID` to
the dedicated daemon socket owner's numeric UID/GID; the runner drops all Linux
capabilities and cannot bypass socket permissions. The image supports an
unprivileged runner user. Production images use immutable commit tags
`ghcr.io/<owner>/<repo>/workspace-runtime:<sha>` and
`ghcr.io/<owner>/<repo>/workspace-runner:<sha>`, built by Deploy Production after
CI's isolation checks and sent to the server (local names: nothing is pushed to
or pulled from ghcr.io, see `deployment.md`). Set `MIZAN_WORKSPACE_RUNTIME_IMAGE`
and `MIZAN_WORKSPACE_RUNNER_IMAGE` to those images. The deploy also builds
`ghcr.io/<owner>/<repo>/workspace-browser:<sha>`; Shahid's browser jobs run
only when the runner has `MIZAN_WORKSPACE_BROWSER_IMAGE` set to it (see
`shahid.md`). The backend and runner share only the private API token. The runner
receives no Mizan database or project volume. A remotely hosted runner can
instead use `MIZAN_WORKSPACE_RUNNER_URL` and the same token through a private or
TLS-protected connection. Missing or unhealthy isolation returns HTTP 503 and
the frontend reports execution unavailable; there is no host-shell fallback.

`GET /api/workspaces/hardware` requires the administrator role and reports CPU,
memory and disk information visible to the backend container. This scope is
explicit. It does not grant unrestricted access to server files, hardware
devices, Docker administration or production secrets. Owner project file
management and isolated code execution are the concrete authorized operations.

Image artifacts accept decoder-verified PNG, JPEG and WebP data only; SVG and
external image URLs are rejected. HTML previews must use a sandboxed iframe with
no same-origin privilege. Saved images do not imply that the active language
model understands image attachments or can generate images.

See also `agentic-coding.md` for the agent coding tools, approvals and the in-browser preview.

## Niyyah: the project's goal

"Actions are judged by intentions" (Bukhari 1). A project keeps its goal: the
one you set (`PATCH /api/workspaces/{id}` with `{"goal": "..."}`, up to 1000
characters, or **Rename or set goal** on `/code`; `""` clears it), else the
first request of the project's chat. Each answer's work is read against it
(`backend/tadbir/niyyah.py`, ForgeKit's `anchor.js`):

- the goal's concepts are its distinctive words (more information than its
  average word), with a light suffix fold;
- each action of the run that changed something (a write, an edit, a run; not
  a read) is one item; its concepts are the request's words, the tool's name,
  its short arguments (a path, an id) and the names a program it wrote
  defines, split at camelCase and symbols;
- an item is on the goal with a noisy-OR of its hits, 1 − (1 − 0.6)^k for k
  distinct goal concepts it shows (a prefix of four letters or more meets a
  variant, `valid` → `validation`; a bare substring does not, `port` is not
  `report`);
- the run's drift is the off-goal share of its items (no change: 0), and a
  one-sided CUSUM C = max(0, C + drift − 0.35) alarms at C > 1.0, so one
  exploratory step drains back while sustained work elsewhere is noted.

The alarm is only a note under the answer: **Off the project's goal?** in the
answer's sources row, which opens to the goal and the off-goal actions
(`usage.niyyah`: `scope`, `goal`, `goal_source` stated or first_request,
`work`, `drift`, `cusum`, `alarm`, `off_goal`). Nothing is ever stopped. The
chart is kept per project with no words, in the person's `azm.sqlite3`; with
no store it starts from zero for that run. The goal also heads the project's
hand-off ([azm.md](azm.md)), which a new chat on the project starts from.
