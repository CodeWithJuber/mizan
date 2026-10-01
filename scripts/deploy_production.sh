#!/usr/bin/env bash
# Run over an authenticated SSH connection. Registry token arrives on stdin.
# Preserve the existing Compose project, .env, volumes and reverse proxy.
set -euo pipefail
umask 077
sha=${1:?Commit SHA is required}
repository=${2:?Lowercase GitHub repository is required}
[[ "$sha" =~ ^[a-f0-9]{40}$ ]] || { echo 'Invalid commit SHA' >&2; exit 1; }
[[ "$repository" =~ ^[a-z0-9_-]+/[a-z0-9_.-]+$ ]] || exit 1
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
printf '%s' "$registry_token" | docker login ghcr.io -u "${repository%%/*}" --password-stdin
unset registry_token
python3 - "$tmp_dir" "$sha" "$repository" "$backend_before" "$frontend_before" <<'PY'
import json, subprocess, sys
from pathlib import Path
directory, sha, repository, old_backend, old_frontend = sys.argv[1:]
# Preserve the running provider configuration, including installations where
# the endpoint ID was set directly in Compose rather than in .env. Values stay
# on the server in files protected by umask 077; none are printed or sent back.
raw = subprocess.check_output(["docker", "inspect", "-f", "{{json .Config.Env}}", "mizan-backend"])
runtime = dict(item.split("=", 1) for item in json.loads(raw) if "=" in item)
keys = ("RUNPOD_API_KEY", "RUNPOD_API_TOKEN", "RUNPOD_ENDPOINT_ID")
environment = {key: runtime[key] for key in keys if key in runtime}
environment["MIZAN_DATA_DIR"] = runtime.get("MIZAN_DATA_DIR") or "/data/mizan"
for filename, backend, frontend in [
    ("new.yml", f"ghcr.io/{repository}/backend:{sha}", f"ghcr.io/{repository}/frontend:{sha}"),
    ("rollback.yml", old_backend, old_frontend),
]:
    config = {"services": {"backend": {"image": backend, "environment": environment},
                           "frontend": {"image": frontend}}}
    (Path(directory) / filename).write_text(json.dumps(config))
PY

"${compose[@]}" -f "$tmp_dir/new.yml" config --quiet
"${compose[@]}" -f "$tmp_dir/new.yml" pull backend frontend
cp "$tmp_dir/rollback.yml" "$state_dir/rollback.yml"
cp "$tmp_dir/new.yml" "$state_dir/current.yml"
rollback() {
  echo 'Deployment did not pass health/auth checks; restoring previous images.' >&2
  cp "$state_dir/rollback.yml" "$state_dir/current.yml"
  "${compose[@]}" -f "$state_dir/current.yml" up -d --no-deps --no-build backend frontend
}
if ! "${compose[@]}" -f "$state_dir/current.yml" up -d --no-deps --no-build backend frontend; then
  rollback
  exit 1
fi
healthy=false
for attempt in $(seq 1 "${MIZAN_DEPLOY_HEALTH_ATTEMPTS:-45}"); do
  if docker exec mizan-backend curl --fail --silent http://127.0.0.1:8000/api/health >/dev/null &&
     [[ $(docker exec mizan-backend curl --silent --output /dev/null --write-out '%{http_code}' http://127.0.0.1:8000/api/status) == 401 ]] &&
     docker exec mizan-frontend wget -qO- http://127.0.0.1:3000/ >/dev/null; then
    healthy=true
    break
  fi
  sleep 2
done
if [[ "$healthy" != true ]]; then rollback; exit 1; fi
printf '%s\n' "$sha" > "$state_dir/deployed-sha"
echo "Mizan deployed: $sha; health and anonymous-auth denial passed."
