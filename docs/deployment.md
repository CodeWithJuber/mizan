# Production deployments

When production misbehaves or a deployment fails, follow the [runbook](runbook.md). This page explains how deployment works.

Mizan production image builds and deployment support both private and
public repositories. Keep the repository's intended visibility; it does not
need to be public to deploy. Every workflow runs on the owner's self-hosted
runner labelled `mizan` and uses nothing GitHub bills for
([ci-artifacts.md](ci-artifacts.md)). The existing VPS and RunPod services
retain their separate costs.

No registry is involved. CI's `production-images` job builds the commit's
backend, frontend, `workspace-runtime`, `workspace-runner` and
`workspace-browser` images into the runner's own Docker. Deploy Production,
on the same runner, sends them to the server over its verified SSH connection
(`docker save | gzip | ssh … docker load`). The images keep the names the
server's deploy state and runner installer already record
(`ghcr.io/codewithjuber/mizan/<image>:<sha>`), but they are never pushed to or
pulled from ghcr.io: GitHub Packages is billed for a private repository. The
runner keeps only the newest commit's images; the server keeps the images it
runs and the ones a rollback needs. If the runner no longer has a commit's
images (its Docker was reset), re-run that commit's CI before deploying it.

Each deployed commit gets a 30-day receipt under `/var/lib/mizan-deploy/receipts/<repository-id>/<run-id>-<attempt>.json`. After a successful deployment, Auto Release reads the matching receipt over pinned SSH, verifies its digest and compares the recorded commit with the branch tip. Earlier deployment runs read their archived receipt from the same compute host, verifying GitHub's original digest and the triggering attempt's start time.

The separate Auto Release workflow retains its public-repository restriction;
it is not required to publish production images or deploy the application.

After a main/master merge, CI validates the source and builds the production
backend/frontend images tagged with the exact commit, together with the
`workspace-runtime`, `workspace-runner` and `workspace-browser` (Shahid)
images, on the runner. `Deploy Production`
runs only after that CI succeeds, skips an obsolete commit, checks the pinned
SSH host key, uploads `deploy_production.sh` and `setup_workspace_runner.py`
into a fresh root-only `/var/lib/mizan-deploy/release.XXXXXXXX` directory
(removed afterwards), loads the backend and frontend images into the server's
Docker, sends the workspace images there as archives only when the managed
runner will move to them (`setup_workspace_runner.py --needed-images`), and
updates the existing Compose project's backend/frontend.
The running reverse proxy, database volume, host configuration and `.env`
are preserved. Nginx reloads to resolve the new container addresses as soon
as they start (and again after the checks), so the restart window is the old
backend's drain plus the new one's start-up, about 15 seconds; checks
then verify health and authentication through the public HTTPS URL.
During that window the web app shows "MIZAN is restarting", reads wait for
the health check and are sent again, and a chat message sent meanwhile says
to check the chat before sending it again (`frontend/src/utils/restarting.ts`).
A failed health or anonymous-auth denial check restores the
previous images. Deployment state is stored in `/var/lib/mizan-deploy`.

On a host with the managed workspace runner, the same run then moves the runner
and its sandbox runtime to the deployed commit's images, still under the deploy
lock, and proves a real sandbox session (files, npm and PyPI through the egress
proxy, confinement) before keeping them; a failure restores and verifies the
previous runner ([runner-setup.md](runner-setup.md#upgrades-during-deployment)).
The new site stays live either way: the run records the release and then fails
its last step, "Workspace runner", so a runner that was not upgraded is visible.
The job allows 45 minutes: sending the images, the lock wait, the site deploy
and the runner's 15-minute upgrade with its 10-minute restore. The runner needs
outbound SSH to the server for this, as it does for the operations workflows.

Required Mizan Actions secrets:

- `SSH_COMPUTING_HOST`
- `SSH_COMPUTING_HOST_USER`
- `SSH_COMPUTING_HOST_PASSWORD`

The first two can instead be repository variables. Store values through GitHub
Settings → Secrets and variables → Actions. Codex environment variables are
separate; they are not automatically available to Actions. Do not put a
password or API key in workflow inputs, source files, issues, or job logs.

`deploy/known_hosts` pins the VPS's public SSH key. The PR connection-check job
can obtain the key without credentials; verify the initial target/identity
before committing it. Later deployments use strict key checking.

The server's existing `.env` must retain `RUNPOD_API_KEY` (or
`RUNPOD_API_TOKEN`) and `RUNPOD_ENDPOINT_ID`. The provider choice persists in
the existing database. Notebook execution requires an isolated executor and
fails closed when unavailable; exposing the host Docker socket to the backend
is not part of this deployment.

Ruh builds use a digest-pinned checkpoint artifact with manifest verification.
Set `RUNPOD_API_KEY` (or `RUNPOD_API_TOKEN`) in that repository's Actions
secrets. The endpoint defaults to `your-endpoint-id`, or set repository variable
`RUNPOD_ENDPOINT_ID`. The image is tagged by commit, and deployment changes
the endpoint's template to that image, preserving resource limits and keeping
minimum workers at zero. A failed smoke check restores the previous template.

Docs are validated on their relevant changes, on the runner. They are no longer
deployed to GitHub Pages, which needs a paid plan for a private repository;
`ENABLE_GITHUB_PAGES` is no longer read. PyPI publication requires explicit
`ENABLE_PYPI_PUBLISH=true` (a repository variable) and a configured trusted
publisher, and runs only for a public repository. The release workflow mints
the short-lived PyPI token from GitHub's OIDC token itself and uploads with
`twine`, because `pypa/gh-action-pypi-publish` runs in a Docker container
action the self-hosted runner cannot mount its workspace into. A release builds
its Docker images as a check but no longer publishes them to ghcr.io.
