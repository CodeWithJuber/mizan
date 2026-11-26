# Production deployments

When production misbehaves or a deployment fails, follow the [runbook](runbook.md). This page explains how deployment works.

Production is one host running the Docker Compose project (`mizan-nginx`, `mizan-backend`, `mizan-frontend`) and, optionally, the managed workspace runner ([runner-setup.md](runner-setup.md)). Deploy Production (`.github/workflows/deploy.yml`) updates it over SSH from a GitHub-hosted runner ([ci-artifacts.md](ci-artifacts.md)). The paths below are the defaults the scripts use: deployment state in `/var/lib/mizan-deploy` (`MIZAN_DEPLOY_STATE_DIR` moves it for `deploy_production.sh`), and the Compose project in `/opt/mizan` for the runner installer.

## When it runs

After a push to `main`, CI runs every check and builds the images as a check ([ci-artifacts.md](ci-artifacts.md#what-a-run-checks)). Deploy Production starts when that run passes, or by hand on `main` (**Actions → Deploy Production → Run workflow**). It never runs for a pull request. Its job uses the `production` environment, so it waits until a required reviewer approves it, and only then gets the environment's secrets.

It skips a commit that is no longer the head of `main` (the newer commit's run deploys that one), then:

1. builds the commit's backend and frontend images on the runner and checks the backend's runtime dependencies (CPU-only torch, pinned pip and setuptools, the owned learning cycle);
2. writes the SSH key and the pinned host key to the job's private temporary directory, and connects with `StrictHostKeyChecking=yes` and `BatchMode=yes`;
3. uploads `deploy_production.sh` and `setup_workspace_runner.py` into a fresh root-only `/var/lib/mizan-deploy/release.XXXXXXXX` directory (removed afterwards);
4. sends the two images straight into the server's Docker (`docker save | gzip | ssh … docker load`);
5. asks the server which workspace images its managed runner needs (`setup_workspace_runner.py --needed-images`), builds only those and sends them as archives into the release directory;
6. runs `deploy_production.sh`, which updates the existing Compose project's backend and frontend.

**No registry.** The images are named `ghcr.io/<owner>/<repo>/<image>:<sha>`, the names the server's deploy state and runner installer record, but they are never pushed to or pulled from ghcr.io. Building on the deploy's runner and streaming the images keeps the rollback exactly as it was: the server still holds the images it ran before, and `rollback.yml` names them. Pushing to GHCR and pulling by digest would also work for a public repository, but it would change the server's deploy script and the runner installer, and add a package whose visibility must be managed.

## On the server

`deploy_production.sh` keeps the running reverse proxy, database volume, host configuration and `.env`. Nginx reloads to resolve the new container addresses as soon as they start (and again after the checks), so the restart window is the old backend's drain plus the new one's start-up, about 15 seconds. During that window the web app shows "MIZAN is restarting", reads wait for the health check and are sent again, and a chat message sent meanwhile says to check the chat before sending it again (`frontend/src/utils/restarting.ts`). The checks then verify health and anonymous-authentication denial inside the containers and through the public URL (`MIZAN_PUBLIC_URL`, which the workflow passes from the `DEPLOY_PUBLIC_URL` secret; the script refuses to start without it). A failed check restores the previous images. Deployment state is stored in `/var/lib/mizan-deploy`.

On a host with the managed workspace runner, the same run then moves the runner and its sandbox runtime to the deployed commit's images, still under the deploy lock, and proves a real sandbox session (files, npm and PyPI through the egress proxy, confinement) before keeping them; a failure restores and verifies the previous runner ([runner-setup.md](runner-setup.md#upgrades-during-deployment)). The new site stays live either way: the run records the release and then fails its last step, "Workspace runner", so a runner that was not upgraded is visible. The job allows 90 minutes: building and sending the images, the lock wait, the site deploy and the runner's 15-minute upgrade with its 10-minute restore.

Each deployed commit gets a 30-day receipt under `/var/lib/mizan-deploy/receipts/<repository-id>/<run-id>-<attempt>.json`. Auto Release (off unless the repository variable `ENABLE_AUTO_RELEASE` is `true`) reads the matching receipt over the same pinned SSH connection, verifies its digest and compares the recorded commit with the branch tip before it tags a release.

## What the repository owner sets up

In **Settings → Environments**, an environment named `production` with a required reviewer, deployment branches limited to `main` (add an `ops/*` branch only while its operation runs), and these environment secrets:

| Secret | Value |
| --- | --- |
| `DEPLOY_HOST` | The server's host name or address |
| `DEPLOY_USER` | The SSH user that runs the deploy (root, or a user allowed to run Docker and write `/var/lib/mizan-deploy`) |
| `DEPLOY_SSH_KEY` | A private key made for this purpose only (`ssh-keygen -t ed25519 -N ''`), whose public half is in that user's `authorized_keys` on the server |
| `DEPLOY_KNOWN_HOSTS` | The server's host key line, checked out of band (for example `ssh-keyscan -t ed25519 <host>` compared with `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` on the server) |
| `DEPLOY_PUBLIC_URL` | The site's `https://` origin, such as `https://mizan.example.com` |

Keep them in the environment, not as repository secrets, so only the approved production jobs see them. Do not put a password or API key in workflow inputs, source files, issues, or job logs: the logs of a public repository are public. Password login for the deploy user is no longer used; the server can turn it off for that user once the key works.

The server's existing `.env` keeps its own settings, such as `RUNPOD_API_KEY` (or `RUNPOD_API_TOKEN`) and `RUNPOD_ENDPOINT_ID` for the Ruh provider; the deploy carries the running values over. The provider choice persists in the existing database. Notebook execution requires an isolated executor and fails closed when unavailable; exposing the host Docker socket to the backend is not part of this deployment. Ruh's serverless image is built and deployed from a separate repository (available on request) with a digest-pinned checkpoint and manifest verification.

## Releases

`release.yml` runs on a `v*` tag: it tests, builds the Docker images as a check, and creates the GitHub release with the wheel and the source archive. PyPI publication runs only when the repository variable `ENABLE_PYPI_PUBLISH` is `true`, with PyPI's trusted publishing: on PyPI, add a trusted publisher for this repository, the workflow `release.yml` and the environment `pypi`. No PyPI token is stored. Docs are validated on their relevant changes and read in the repository; nothing is deployed to GitHub Pages.
