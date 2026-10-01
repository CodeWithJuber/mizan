# Production deployments

Both repositories are public. These workflows use standard `ubuntu-24.04`
GitHub-hosted runners; public-repository Actions compute is free. Deployment
jobs refuse private repositories. No larger or GPU GitHub runners are used.
The existing VPS and RunPod services retain their separate costs.

After a main/master merge, CI validates the source and publishes production
backend/frontend images tagged with the exact commit. `Deploy Production`
runs only after that CI succeeds, skips an obsolete commit, checks the pinned
SSH host key, and updates the existing Compose project's backend/frontend.
The running reverse proxy, database volume, host configuration and `.env`
are preserved. A failed health or anonymous-auth denial check restores the
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
secrets. The endpoint defaults to `6o38qhvti4knkk`, or set repository variable
`RUNPOD_ENDPOINT_ID`. The image is tagged by commit, and deployment changes
the endpoint's template to that image, preserving resource limits and keeping
minimum workers at zero. A failed smoke check restores the previous template.

Docs are validated on their relevant changes. Set `ENABLE_GITHUB_PAGES=true`
only after enabling the repository's Pages site with GitHub Actions as its
source. PyPI publication similarly requires explicit
`ENABLE_PYPI_PUBLISH=true` and a configured trusted publisher.
