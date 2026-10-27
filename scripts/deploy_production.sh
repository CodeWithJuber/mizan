#!/usr/bin/env bash
# Run over an authenticated SSH connection. Registry token arrives on stdin.
# Preserve the existing Compose project, .env, volumes and reverse proxy.
set -euo pipefail
umask 077
sha=${1:?Commit SHA is required}
repository=${2:?Lowercase GitHub repository is required}
[[ "$sha" =~ ^[a-f0-9]{40}$ ]] || { echo 'Invalid commit SHA' >&2; exit 1; }
[[ "$repository" =~ ^[a-z0-9_-]+/[a-z0-9_.-]+$ ]] || exit 1
health_attempts=${MIZAN_DEPLOY_HEALTH_ATTEMPTS:-45}
[[ "$health_attempts" =~ ^[1-9][0-9]?$ ]] && (( health_attempts <= 45 )) || {
  echo 'Health attempts must be decimal integers from 1 to 45.' >&2; exit 1;
}
command -v timeout >/dev/null || { echo 'Bounded health checks require timeout.' >&2; exit 1; }
read -r registry_token
test -n "$registry_token"

state_dir=${MIZAN_DEPLOY_STATE_DIR:-/var/lib/mizan-deploy}
mkdir -p "$state_dir"
exec 9>"$state_dir/deploy.lock"
flock -w 600 9
root=$(docker inspect -f '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}' mizan-backend)
project=$(docker inspect -f '{{ index .Config.Labels "com.docker.compose.project" }}' mizan-backend)
files=$(docker inspect -f '{{ index .Config.Labels "com.docker.compose.project.config_files" }}' mizan-backend)
test -d "$root" && test -n "$project" && test -n "$files"
cd "$root"
tmp_dir=$(mktemp -d "$state_dir/pending.XXXXXXXX")
export DOCKER_CONFIG="$tmp_dir/docker"
mkdir -p "$DOCKER_CONFIG"
trap 'rm -rf "$tmp_dir"' EXIT

compose=(docker compose -p "$project")
IFS=',' read -ra compose_files <<< "$files"
for file in "${compose_files[@]}"; do
  # Previous successful deployments may have added an image override.
  if [[ "$file" != "$state_dir/"* ]]; then compose+=(-f "$file"); fi
done
test ${#compose[@]} -gt 4
backend_before=$(docker inspect -f '{{.Image}}' mizan-backend)
frontend_before=$(docker inspect -f '{{.Image}}' mizan-frontend)
python3 - "$tmp_dir" "$sha" "$repository" "$backend_before" "$frontend_before" <<'PY'
import json, os, re, subprocess, sys
from pathlib import Path
directory, sha, repository, old_backend, old_frontend = sys.argv[1:]
# Preserve the running provider configuration, including installations where
# the endpoint ID was set directly in Compose rather than in .env. Values stay
# on the server in files protected by umask 077; none are printed or sent back.
raw = subprocess.check_output(["docker", "inspect", "-f", "{{json .Config.Env}}", "mizan-backend"])
runtime = dict(item.split("=", 1) for item in json.loads(raw) if "=" in item)
keys = (
    "RUNPOD_API_KEY", "RUNPOD_API_TOKEN", "RUNPOD_ENDPOINT_ID",
    "MIZAN_LLM_FIRST_PROGRESS_SECONDS", "MIZAN_LLM_PROGRESS_SECONDS",
    "MIZAN_LLM_MAX_CALL_SECONDS", "MIZAN_CHAT_RUN_SECONDS",
    "MIZAN_CHAT_TOOL_SCHEMA_LIMIT", "MIZAN_CHAT_TOOL_SCHEMA_BYTES", "MIZAN_CHAT_TEMPERATURE",
)
environment = {key: runtime[key] for key in keys if key in runtime}
environment["MIZAN_DATA_DIR"] = runtime.get("MIZAN_DATA_DIR") or "/data/mizan"

def graceful_seconds(value):
    # Do not echo invalid values: a mistaken environment value could be a secret.
    if not re.fullmatch(r"[1-9][0-9]{1,2}", value) or not 10 <= int(value) <= 180:
        raise SystemExit("Invalid graceful shutdown configuration; use decimal seconds from 10 to 180.")
    return int(value)

# For an old image without either setting, 90s is a Docker drain allowance;
# an environment change cannot retrofit a deadline into its running Uvicorn.
old_grace = graceful_seconds(runtime.get("MIZAN_GRACEFUL_SHUTDOWN_SECONDS",
                                       runtime.get("UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN", "90")))
new_grace = graceful_seconds(os.environ.get("MIZAN_GRACEFUL_SHUTDOWN_SECONDS", str(old_grace)))
# Compose's explicit timeout applies to the already-running container too.
# Use both deadlines: reducing the new setting must not cut short the old
# process, and rollback must allow the newly-started process to drain.
stop_timeout = max(old_grace, new_grace) + 15
(Path(directory) / "stop-timeout").write_text(str(stop_timeout))
for filename, backend, frontend, grace in [
    ("new.yml", f"ghcr.io/{repository}/backend:{sha}", f"ghcr.io/{repository}/frontend:{sha}", new_grace),
    ("rollback.yml", old_backend, old_frontend, old_grace),
]:
    selected_environment = environment | {
        "MIZAN_GRACEFUL_SHUTDOWN_SECONDS": str(grace),
        "UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN": str(grace),
    }
    # Compose interpolates dollar signs even in JSON-formatted overrides.
    # Preserve literal running credentials/configuration, never expand them.
    selected_environment = {key: value.replace("$", "$$") for key, value in selected_environment.items()}
    config = {"services": {"backend": {"image": backend, "environment": selected_environment,
                                       "stop_grace_period": f"{grace + 15}s"},
                           "frontend": {"image": frontend}}}
    (Path(directory) / filename).write_text(json.dumps(config))
PY
stop_timeout=$(<"$tmp_dir/stop-timeout")

"${compose[@]}" -f "$tmp_dir/new.yml" config --quiet
printf '%s' "$registry_token" | docker login ghcr.io -u "${repository%%/*}" --password-stdin
unset registry_token
"${compose[@]}" -f "$tmp_dir/new.yml" pull backend frontend
cp "$tmp_dir/rollback.yml" "$state_dir/rollback.yml"
cp "$tmp_dir/new.yml" "$state_dir/current.yml"
refresh_proxy() {
  if [[ $(docker inspect -f '{{.State.Running}}' mizan-nginx 2>/dev/null || true) == true ]]; then
    docker exec mizan-nginx nginx -t && docker exec mizan-nginx nginx -s reload
  fi
}
rollback() {
  echo 'Deployment did not pass health/auth checks; restoring previous images.' >&2
  cp "$state_dir/rollback.yml" "$state_dir/current.yml"
  "${compose[@]}" -f "$state_dir/current.yml" up -d --timeout "$stop_timeout" --no-deps --no-build backend frontend
  refresh_proxy
}
if ! "${compose[@]}" -f "$state_dir/current.yml" up -d --timeout "$stop_timeout" --no-deps --no-build backend frontend; then
  rollback
  exit 1
fi
# Nginx resolves its upstream names only when it loads, so until a reload it
# keeps sending to the old containers' addresses (502). Reload now, while the
# health checks run, so the restart window ends when the new containers start.
refresh_proxy || true
healthy=false
health_deadline=$((SECONDS + 90))
health_probe() {
  local remaining=$((health_deadline - SECONDS))
  (( remaining > 0 )) || return 1
  local probe_seconds=8
  if (( remaining < probe_seconds )); then probe_seconds=$remaining; fi
  # The inner clients bound container-side work; the outer limit also bounds a
  # stuck Docker exec client. The one-second kill margin may extend the phase.
  timeout --signal=TERM --kill-after=1s "${probe_seconds}s" "$@"
}
for ((attempt = 1; attempt <= health_attempts; attempt++)); do
  if health_probe docker exec mizan-backend curl --fail --silent --connect-timeout 2 --max-time 5 http://127.0.0.1:8000/api/health >/dev/null &&
     anonymous_status=$(health_probe docker exec mizan-backend curl --silent --connect-timeout 2 --max-time 5 --output /dev/null --write-out '%{http_code}' http://127.0.0.1:8000/api/status) &&
     [[ "$anonymous_status" == 401 ]] &&
     health_probe docker exec mizan-frontend wget -T 5 -qO- http://127.0.0.1:3000/ >/dev/null; then
    healthy=true
    break
  fi
  pause=$((health_deadline - SECONDS))
  (( pause > 0 && attempt < health_attempts )) || break
  if (( pause > 2 )); then pause=2; fi
  sleep "$pause"
done
if [[ "$healthy" != true ]]; then rollback; exit 1; fi
if ! refresh_proxy; then rollback; exit 1; fi
public_url=${MIZAN_PUBLIC_URL:-https://mizan.example.com}
if ! curl --fail --silent --connect-timeout 15 --max-time 30 --retry 3 --retry-delay 2 "$public_url/api/health" >/dev/null ||
   [[ $(curl --silent --connect-timeout 15 --max-time 30 --output /dev/null --write-out '%{http_code}' "$public_url/api/status") != 401 ]]; then
  rollback
  exit 1
fi
printf '%s\n' "$sha" > "$state_dir/deployed-sha"
echo "Mizan deployed: $sha; health and anonymous-auth denial passed."
