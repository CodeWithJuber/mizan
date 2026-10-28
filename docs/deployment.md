# Production deployments

Mizan production image publishing and deployment support both private and
public repositories. Keep the repository's intended visibility; it does not
need to be public to deploy. These workflows use standard `ubuntu-24.04`
GitHub-hosted runners. Private-repository usage follows the account's Actions
allowance and billing settings; no larger or GPU GitHub runners are used.
The existing VPS and RunPod services retain their separate costs.

CI publishes commit-tagged images to GHCR with its repository-scoped
`GITHUB_TOKEN` and `packages: write`. Deployment uses `packages: read` and
passes its short-lived token over the existing verified SSH connection for
the server's registry login. No anonymous registry access or public repository
is required. Existing package access must permit this repository's Actions
token; package visibility is configured separately from repository visibility.
See [GitHub's Container registry documentation](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry).

The separate Auto Release workflow retains its public-repository restriction;
it is not required to publish production images or deploy the application.

After a main/master merge, CI validates the source and publishes production
backend/frontend images tagged with the exact commit, together with the
`workspace-runtime`, `workspace-runner` and `workspace-browser` (Shahid)
images. Deployment changes only backend/frontend; the workspace images are
installed by the reviewed runner setup ([runner-setup.md](runner-setup.md)).
`Deploy Production`
runs only after that CI succeeds, skips an obsolete commit, checks the pinned
SSH host key, and updates the existing Compose project's backend/frontend.
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

Docs are validated on their relevant changes. Set `ENABLE_GITHUB_PAGES=true`
only after enabling the repository's Pages site with GitHub Actions as its
source. PyPI publication similarly requires explicit
`ENABLE_PYPI_PUBLISH=true` and a configured trusted publisher. Both are
repository variables, and the Pages deployment and the PyPI publish job also
run only for a public repository.
