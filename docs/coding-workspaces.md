Mizan coding projects persist under `MIZAN_WORKSPACE_ROOT` (default
`MIZAN_DATA_DIR/workspaces`). Each principal has a separate namespace. The API
supports file trees, optimistic file edits, rename/delete of individual files,
five retained checkpoints, actual diffs, and saved code/HTML/markdown/image
artifacts. Files survive chat and backend restarts. Project files have a 1 MiB
limit, projects a 10 MiB/500-entry limit, and each user can create ten projects.

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
12.3.0, with their resolved dependencies pinned in
`docker/workspace-runtime-requirements.txt`. These packages are installed while
building the image; a job has no network and does not install packages. Plotting
uses the noninteractive Agg backend, a writable cache in `/tmp`, and one BLAS
thread so it fits the job's process limit. Save a chart as a small PNG, JPEG or
WebP and publish that saved file with `workspace_artifact`. Image artifacts are
limited to 500000 encoded characters (roughly 375 kB of image bytes), which is
smaller than the project file limit.

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
`ghcr.io/codewithjuber/mizan/workspace-runtime:<sha>` and
`ghcr.io/codewithjuber/mizan/workspace-runner:<sha>`, published by the main CI
pipeline after isolation checks. Set `MIZAN_WORKSPACE_RUNTIME_IMAGE` and
`MIZAN_WORKSPACE_RUNNER_IMAGE` to those tags. The backend and runner share only
the private API token. The runner
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
