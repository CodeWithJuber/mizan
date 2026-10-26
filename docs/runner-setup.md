# Dedicated workspace runner setup

`scripts/setup_workspace_runner.py` is a host-specific provisioning script for the
existing `mizan` Compose project in `/opt/mizan`. Its workflow is restricted to a
reviewed push to `ops/enable-workspace-runner-20261026` in `CodeWithJuber/mizan`.
It is not a pull-request workflow, general server installer, or Docker upgrade.

The verified production baseline is commit `0176a873e266d942918de47f8888071568eeeeb2`.
Before enabling the operations branch, retarget `EXPECTED_BACKEND_SHA` to the
final application's deployed, CI-tested commit. Both workspace images must have
been published for that exact commit. The workflow checks main still has that SHA; the
host checks that its backend image ID equals the locally installed image for that
SHA. A newer main/backend requires a reviewed retarget, not bypassing the check.
The baseline runtime includes the pinned plotting dependencies. A different
runtime still requires its corresponding tested image. Production activation and
live Python, PNG and interactive HTML verification are recorded in
[the production validation report](production-validation-2026-10-25.md).

## Changes and boundaries

- Installs only missing `uidmap` and `slirp4netns` prerequisites, allowing their
  new `libsubid4`/`libslirp0` dependencies. The simulated package plan must not
  upgrade or remove packages. It does not replace Docker, restart the production
  daemon, disable AppArmor, change sysctls, or enable privileged Docker-in-Docker.
- Creates locked, non-login `mizan-workspace`, home `/var/lib/mizan-workspace`, and
  a real rootless Docker **user** service with lingering. An unmanaged existing
  account, home, runner service, or override blocks setup. A root-only ownership
  marker permits a safe retry of this script's own incomplete work.
- Delegates `cpu cpuset io memory pids` only to that UID's systemd user service.
  Its user slice has a combined 2 GiB RAM / zero swap / two CPU / 1024-task budget.
  Per-job limits remain 384 MiB, one CPU and 64 processes. The private control
  service separately has 192 MiB, half a CPU and 128 processes.
- Uses a distinct rootless daemon/socket for jobs. Only the private runner
  container receives that socket. Neither backend nor jobs receive a Docker
  socket for the production daemon. Runner has no host ports, a read-only root,
  no capabilities, and no-new-privileges. Jobs additionally have no network,
  persistent mounts, production secrets, or access to the application database.
- Uses the existing private `mizan_mizan-net`, Compose project and volume mounts.
  Only `workspace-runner` and `backend` can be recreated. Nginx configuration is
  tested and reloaded to refresh the backend address; other services are preserved.

Rootless containers still share the host kernel. They are not VM isolation, and
the runner API can submit resource-consuming jobs. The bearer token, network
access controls, host updates, resource limits and runtime checks all matter.
The 2 GiB cgroup limit is not a disk quota. Images and container layers consume
the dedicated user's data directory; monitor free disk rather than pruning host
Docker state. Setup requires at least 3 GiB available RAM and 4 GiB free disk.

## Credentials and configuration

The existing pinned `deploy/known_hosts` and deployment SSH settings are reused.
The short-lived GitHub registry token arrives on stdin, is never a command-line
argument or log entry, and is used only in a temporary root-private Docker client
configuration. That directory is removed after pulling both full-commit tags.
Registry tags can be reassigned, so the installer records their content IDs and
repository digests and uses the pulled content IDs in the runner configuration.
A retry will not silently accept a different image for an already recorded tag.
No credential is copied into the service account or job images.

The installer generates a 48-byte random runner token on the host. Its token file,
Compose override and rollback snapshots are root-readable only. Backend and the
private runner receive this token through their container environments; Docker
administrators can therefore inspect it. Jobs do not receive it. Do not publish
`docker inspect`, full `docker compose config`, snapshots, or token-file contents.

The permanent override is
`/opt/mizan/docker-compose.workspace-runtime.yml`. It must remain in the backend's
Compose `config_files` label. Normal releases strip overrides inside
`/var/lib/mizan-deploy`, so the permanent runner file deliberately lives outside
that directory. The original file list, including its current image override,
is preserved during setup. An additional root-private, one-time override under
`/var/lib/mizan-deploy/workspace-runner/attempt-*/current-backend.yml` preserves
the exact running backend image and environment during recreation. Normal future
deployments discard that temporary image/environment override and retain the
permanent runner connection configuration.

The operations workflow also explicitly passes
`--research-dir /data/mizan/research`. This optional argument accepts only that
reviewed path and adds `MIZAN_RESEARCH_DIR` to the same permanent backend override,
using the already planned backend recreation. Before applying it, a read-only
probe runs as the existing backend user and requires UID 999, an existing
non-symlink `/data/mizan` parent, and write/traverse permission. Both the literal
and resolved research paths must remain on the existing writable persistent
`/data` mount; nested mounts and tmpfs shadows block setup. A later managed import
may use a release-directory symlink that stays within `/data/mizan`.

This option does not create a research directory, import an archive, change
ownership, or migrate any existing files. The separate verified importer needs
the target to remain absent. Other environment values and mounts are preserved.
Rollback restores the exact original research environment, including an absent
variable, and retains all research data. Explicit `--rollback` reads the option
from protected setup state; a setup retry must use the same option as its saved
checkpoint. Omitting the option on a new installation leaves research
configuration unchanged.

The current installer intentionally refuses to repurpose an existing setup for
another SHA. A later runtime upgrade must review the new tested runner/runtime
pair and modify the managed override with equivalent rollback and smoke checks.
Do not erase `state.json` to bypass the ownership or version guard.

## Execution and verification

Review the script, workflow and focused tests, then push the reviewed workflow
branch. The workflow shares the `mizan-production` concurrency group and the
server's `/var/lib/mizan-deploy/deploy.lock` with normal deployments. It waits for
the lock and rechecks the deployed image before touching application services.
The lock wait is bounded to ten minutes, setup to thirty minutes after acquiring
it, and rollback has a separate ten-minute budget. The workflow allows sixty
minutes including SSH/package setup. Termination signals enter the same guarded
rollback path when an application switch has begun; an abrupt host crash instead
leaves an `applying` checkpoint to recover on the next attempt.
It creates a private temporary SSH upload directory and removes that script after
execution. The installer performs these checks before recording `ready`:

1. Actual worker daemon reports `rootless`, a distinct daemon ID, cgroup v2 and
   systemd; the user slice and delegated controllers have the intended limits.
2. Control-container inspection verifies its exact image, dedicated socket,
   non-root UID, private network, capabilities, filesystem and memory/CPU limits.
3. Private `/health` rejects anonymous callers and accepts the shared token.
4. Real Python, JavaScript and shell commands execute through `/run`; a generated
   file returns with its expected contents. Code cannot find credential variables,
   Docker sockets or known production paths, and an external TCP connection fails.
5. A long-running command times out with bounded output; a symlink cannot export
   a host file. Live job-container inspection confirms no network/host mounts and
   the configured process, memory and CPU limits. No jobs remain after the probes.
6. The same authenticated checks succeed from the recreated backend. Its data
   mounts and frontend container ID are unchanged. Backend/public health succeed,
   and anonymous application status still returns HTTP 401.

Only fixed stage names and a sanitized receipt reach GitHub logs. A failure returns
nonzero. Do not infer functional readiness from a running container or `/health`
alone. Local unit tests validate guard/rollback logic with fakes; actual rootless
Docker, systemd, registry pulls and HTTP execution require this host-side run.

## Failure, retry and rollback

Before the backend switch, provisioning failures leave its service unchanged.
The owned account, prerequisites and rootless daemon may remain for inspection.
During a failed application switch, the script restores the saved backend image,
environment and original Compose file list, checks backend and public health,
and refreshes nginx before cleaning up its own control service. Cleanup selects
the verified container identity and does not parse a failed Compose override.
It keeps every volume, worker image,
user directory and protected snapshot. This is a configuration/image rollback,
not a database restore.

The protected checkpoint records the original backend container identity and
whether the switch started. A failure before that switch preserves the same
healthy backend without recreation; unknown/legacy state restores conservatively.
Both Compose PID-limit fields are set to 128 for the control service, the rendered
configuration is validated before activation, and the live PID limit is checked.
The recovery workflow budgets 25 minutes for its ten-minute lock wait,
ten-minute recovery budget and SSH/setup overhead.

An interrupted `applying` checkpoint is rolled back before a retry starts.
A successful same-SHA retry rechecks the existing installation and does not
replace its services. Modified managed files, a newer backend or changed original
Compose files stop automatic rollback for manual review. If the rollback itself
cannot be verified, the script clearly reports that result instead of readiness.

For an explicit rollback, copy the same reviewed script through the pinned SSH
connection and run it as the existing deployment user (root). No registry token
is required:

```bash
python3 /path/to/reviewed/setup_workspace_runner.py \
  --sha THE_FULL_SHA_RECORDED_FOR_THIS_SETUP \
  --repository codewithjuber/mizan --rollback
```

Keep the setup's protected state and original Compose files available. If normal
deployment has changed those files or images, inspect the protected snapshot and
prepare a new scoped rollback; do not force this historical command over newer
production state. Stopping/removing the rootless account, its data, package
dependencies or systemd configuration is a separate maintenance action. Neither
automatic nor explicit rollback deletes them, removes volumes, or runs Docker
prune/down.

References: [Docker rootless installation](https://docs.docker.com/engine/security/rootless/),
[user-service operation and cgroup limits](https://docs.docker.com/engine/security/rootless/tips/).
