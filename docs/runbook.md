# Operating MIZAN: runbook

Use this page when production misbehaves: the app is down, a deployment failed, chats hang, or code stops running. It assumes the production layout that [deployment.md](deployment.md) describes, which is Docker Compose on one host:

| Container | Runs |
| --- | --- |
| `mizan-nginx` | The reverse proxy |
| `mizan-backend` | One uvicorn worker |
| `mizan-frontend` | The web app |

Code runs through the private `workspace-runner` service on the same host, which starts sandbox containers on its own rootless Docker daemon ([runner-setup.md](runner-setup.md)).

## Access you need

- **GitHub:** maintainer access to `CodeWithJuber/mizan`, to read Actions logs and run **Deploy Production** by hand.
- **Shell on the production host.** Its credentials live only in the repository's Actions secrets; never paste them into issues, logs or chat.
- **A MIZAN administrator account** for the admin routes below. Send its token as `Authorization: Bearer …`.

## First check: is it up?

```bash
URL=https://your-mizan-host
curl -fsS "$URL/api/health"                                       # 200: the backend answers
curl -s -o /dev/null -w '%{http_code}\n' "$URL/api/status"         # 401: auth is enforced
```

These are the same two checks the deploy script runs after every deployment (`scripts/deploy_production.sh`). If both pass and users still see errors, read the backend log:

```bash
docker logs --since 30m mizan-backend 2>&1 | tail -200    # never copy secrets out of it
```

An administrator can also call `GET /api/doctor` for environment diagnostics. On a source checkout the same diagnostics run as `mizan doctor --check`.

## A deployment failed

**Symptom.** The **Deploy Production** run is red.

**What already happened.** The script restores the previous images itself when a health check or the anonymous-401 check fails. Production is therefore on the last good release.

1. Read the failed job's log. "Deployment did not pass health/auth checks; restoring previous images" means the new images started but were unhealthy.
2. Fix the cause on a branch and merge it. CI runs, and Deploy Production follows on its own.
3. To redeploy the current `main` without a code change, for example after a transient registry or SSH failure, start **Actions → Deploy Production → Run workflow** on `main`. It deploys only the commit that is still the head of the branch.

## Workspace runner not upgraded by a deploy

**Symptom.** Deploy Production is red only at its last step, **Workspace runner**, with "Workspace runner not upgraded" (`runner=kept`, exit 75) or "Workspace runner needs attention" (`runner=unverified`, exit 76).

**What already happened.** The new site is live and recorded in `deployed-sha`. On 75 the previous runner was restored (or never replaced) and verified: one-shot code runs, but anything the new runner adds (for example sandbox sessions) is still missing. The log names the failed stage, and for egress failures the hosts the proxy refused (`egress denied <host>`) or could not reach (`egress unreachable <host>`).

1. Read the stage in the log. "Not enough free disk" or a pull failure changed nothing live; free space or retry. A failed sandbox session check (npm, PyPI, confinement) points at the worker daemon's outbound network or the egress proxy.
2. Fix the cause and run **Deploy Production** again on `main`. The upgrade runs again; an interrupted restore (phase `upgrading` in `/var/lib/mizan-deploy/workspace-runner/state.json`) is finished first.
3. **76 is an escalation.** The runner could not be verified, or its managed files changed outside the installer. Do not edit `state.json`, the override or `override.previous` by hand; read [runner-setup.md](runner-setup.md#upgrades-during-deployment) and escalate.

The chat answers "The private runner on this server predates sandbox sessions" (HTTP 503) while the runner is older than the backend; the next successful upgrade removes it.

## A deployment passed but the release is bad

**Preferred: revert through `main`.** Revert the commit (`git revert <sha>`), open a pull request and merge it. CI publishes the images and Deploy Production ships them, with the usual checks.

**Emergency: restore the previous images on the host.** Each deployment keeps the images it replaced in `/var/lib/mizan-deploy/rollback.yml`. This repeats the script's own `rollback()`:

```bash
state=/var/lib/mizan-deploy
project=$(docker inspect -f '{{ index .Config.Labels "com.docker.compose.project" }}' mizan-backend)
files=$(docker inspect -f '{{ index .Config.Labels "com.docker.compose.project.config_files" }}' mizan-backend)
cd "$(docker inspect -f '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}' mizan-backend)"
args=(-p "$project"); IFS=',' read -ra list <<< "$files"
for f in "${list[@]}"; do [[ $f == "$state"/* ]] || args+=(-f "$f"); done
cp "$state/rollback.yml" "$state/current.yml"
docker compose "${args[@]}" -f "$state/current.yml" up -d --no-deps --no-build backend frontend
docker exec mizan-nginx nginx -t && docker exec mizan-nginx nginx -s reload
```

Then run the first checks again. The next merge to `main` deploys over this, so revert through `main` as well.

## The app says "MIZAN is restarting", or returns 502

During a deployment the backend restarts in about 15 seconds, and the web app waits for it. If the message stays after the backend is healthy, Nginx may still point at the old container addresses. Reload it, as the deploy script does:

```bash
docker exec mizan-nginx nginx -t && docker exec mizan-nginx nginx -s reload
```

## A chat keeps running, or never answers

A run belongs to the server, not to the connection, so a closed tab does not stop it.

```text
GET  /api/chat/{session_id}/run-state     # is a run active?
POST /api/chat/{session_id}/stop          # cancel it
```

A client must not resend the same message with a fresh `request_id` after a dropped connection. It should read the chat's history instead ([api-testing.md](api-testing.md)).

## Actions wait, or are refused

| What you see | Why | What to do |
| --- | --- | --- |
| "Held for the owner's approval" | An unattended run (watcher, schedule, trigger, queue or channel message) wanted to change something | `GET /api/chat/held` lists the actions; decide each once with `POST /api/chat/held/{id}` before it expires (24 h) |
| "Plan mode is read-only" | The chat is in `plan` mode | Switch the chat's permission mode |
| `error_code: budget_exhausted` | Iqtisad's daily or monthly limit is reached | Settings → Spending, or `MIZAN_BUDGET_DAILY_USD` / `MIZAN_BUDGET_MONTHLY_USD` ([iqtisad.md](iqtisad.md)) |

## Code does not run

Code runs only on the runner host; the backend has no local shell fallback.

1. Check that `MIZAN_WORKSPACE_RUNNER_URL` and `MIZAN_WORKSPACE_RUNNER_TOKEN` are set on the backend. Settings → Developer → System settings shows whether a value comes from `.env` or was set there.
2. If sandbox sessions say the runner "predates sandbox sessions", the last deploy did not upgrade the runner: see [Workspace runner not upgraded by a deploy](#workspace-runner-not-upgraded-by-a-deploy).
3. Follow [runner-setup.md](runner-setup.md), which covers execution, verification, failure, retry and rollback for the runner.

## Receipts look wrong

Every tool call, held decision, approval and erase is a Sakk receipt in a hash chain.

```text
GET /api/sakk/verify        # the caller's own chain
GET /api/sakk/verify/all    # every chain (administrator)
GET /api/sakk/export        # then offline: python scripts/verify_sakk.py mizan-sakk.json
```

A break in a chain is evidence of tampering or data loss. Keep the export and the database volume; do not repair the chain by hand ([sakk.md](sakk.md)).

## Data and backups

- Everything lives in the data volume (`$MIZAN_DATA_DIR`, `/data/mizan` in Docker). Back it up whole.
- Keep `connectors.key` with it: without that file, saved connector secrets cannot be decrypted.
- Do not run `docker compose down -v` on production, because it deletes the volume.
- To erase one user's chat everywhere, use Mahw (`DELETE /api/chat/{id}`), never a manual database edit: Mahw also removes what was learned from the chat and writes a receipt ([mahw.md](mahw.md)).

## Escalation

1. **The repository owner** (`CodeWithJuber` on GitHub) decides on reverts, credentials and anything that touches user data.
2. **Bugs:** open an issue in `CodeWithJuber/mizan` with:
   - the time;
   - the `request_id` from the chat stream, if there is one;
   - the failing check or the job URL.

   Never include tokens, passwords, `.env` contents or users' messages.
3. **Credentials that may have leaked:** rotate them first (Actions secrets, provider keys, then administrator passwords, using `POST /api/auth/logout` with `everywhere`), then report.
