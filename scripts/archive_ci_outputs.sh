#!/usr/bin/env bash
# Executed from the trusted default branch after CI completes, including failed PR runs.
set -euo pipefail
umask 077
[[ "$GITHUB_REPOSITORY" == CodeWithJuber/mizan && "$CI_RUN_ID" =~ ^[1-9][0-9]*$ ]]
api="repos/$GITHUB_REPOSITORY/actions"
work=$(mktemp -d)
host="$SSH_USER@$SSH_HOST"
ssh_options=(-S "$work/control" -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$PWD/deploy/known_hosts" -o ConnectTimeout=15 -o ServerAliveInterval=30 -o ServerAliveCountMax=5)
remote=''
on_host() { ssh "${ssh_options[@]}" "$host" "$@"; }
cleanup() {
  if [[ "$remote" =~ ^/var/lib/mizan-deploy/archive-ci\.[a-zA-Z0-9]{8}$ ]]; then on_host "rm -f '$remote'" || true; fi
  if [[ -S "$work/control" ]]; then ssh -S "$work/control" -O exit "$host" || true; fi
  rm -rf "$work"
}
trap cleanup EXIT
# Check the source repository and workflow even when the event was a PR from a fork.
gh api "$api/runs/$CI_RUN_ID" | jq -e --arg repo "$GITHUB_REPOSITORY" --argjson id "$CI_RUN_ID" \
  '.id == $id and .repository.full_name == $repo and .status == "completed" and .path == ".github/workflows/ci.yml"' >/dev/null
# Fetch only this run. All filenames and remote paths come from the fixed allowlist.
gh api --paginate "$api/runs/$CI_RUN_ID/artifacts?per_page=100" |
  jq -c --argjson id "$CI_RUN_ID" '.artifacts[] | select(.workflow_run.id == $id and (.expired | not) and (.name == "dist" or .name == "playwright-report"))' > "$work/artifacts"
if [[ ! -s "$work/artifacts" ]]; then echo "No matching CI artifacts."; exit 0; fi
sshpass -e ssh "${ssh_options[@]}" -MNf -o ControlMaster=yes "$host"
remote=$(on_host 'umask 077; mkdir -p /var/lib/mizan-deploy && mktemp /var/lib/mizan-deploy/archive-ci.XXXXXXXX')
[[ "$remote" =~ ^/var/lib/mizan-deploy/archive-ci\.[a-zA-Z0-9]{8}$ ]]
on_host "cat > '$remote'" < scripts/store_actions_archive.sh
while IFS= read -r info; do
  id=$(jq -er .id <<< "$info")
  name=$(jq -er .name <<< "$info")
  bytes=$(jq -er .size_in_bytes <<< "$info")
  digest=$(jq -er .digest <<< "$info")
  [[ "$id" =~ ^[1-9][0-9]*$ && "$bytes" =~ ^[0-9]+$ && "$digest" =~ ^sha256:[a-f0-9]{64}$ ]]
  [[ "$name" == dist || "$name" == playwright-report ]]
  sha=${digest#sha256:}
  args="$CI_RUN_ID $id $sha $bytes $name"
  status=0
  on_host "bash '$remote' probe $args" </dev/null || status=$?
  case "$status" in
    0) ;;
    3)
      gh api "$api/artifacts/$id/zip" > "$work/artifact.zip"
      [[ "$(stat -c %s "$work/artifact.zip")" == "$bytes" ]]
      printf '%s  %s\n' "$sha" "$work/artifact.zip" | sha256sum -c --status
      { printf '%s\n' "$info"; cat "$work/artifact.zip"; } | on_host "bash '$remote' store $args"
      ;;
    *) exit "$status" ;;
  esac
  on_host "bash '$remote' verify $args" </dev/null
  gh api -X DELETE "$api/artifacts/$id"
  echo "Verified $name ($bytes bytes, SHA-256 $sha) at /srv/github-actions-archive/CodeWithJuber/mizan/ci/$name/$CI_RUN_ID/$id/artifact.zip" | tee -a "$GITHUB_STEP_SUMMARY"
done < "$work/artifacts"
