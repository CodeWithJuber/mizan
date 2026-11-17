#!/usr/bin/env bash
# Runs on the pinned SSH compute host. The caller supplies metadata, then opaque archive bytes.
set -euo pipefail
umask 077
mode=$1 run=$2 id=$3 digest=$4 bytes=$5
[[ "$run" =~ ^[1-9][0-9]*$ && "$id" =~ ^[1-9][0-9]*$ && "$digest" =~ ^[0-9a-f]{64}$ && "$bytes" =~ ^[0-9]+$ ]]
root=/srv/github-actions-archive/CodeWithJuber/mizan
family=$6
[[ "$family" == dist || "$family" == playwright-report ]]
root="$root/ci/$family"
dest="$root/$run/$id"
verify() {
  [[ -s "$dest/metadata.json" && "$(stat -c %s "$dest/artifact.zip")" == "$bytes" ]]
  printf '%s  %s\n' "$digest" "$dest/artifact.zip" | sha256sum -c --status
}
if [[ "$mode" == verify || "$mode" == probe ]]; then
  if [[ "$mode" == probe && ! -e "$dest" ]]; then exit 3; fi
  verify
  exit
fi
[[ "$mode" == store ]]
mkdir -p "$root/$run"
exec 9>"$root/.archive.lock"
flock -w 300 9
if [[ -d "$dest" ]]; then
  # Drain stdin to avoid a broken pipe in a retried transfer.
  cat >/dev/null
  verify
  exit
fi
free=$(df --output=avail -B1 "$root" | tail -1)
(( free - bytes >= 15 * 1024 * 1024 * 1024 )) || { echo 'Archive disk reserve reached' >&2; exit 1; }
stage=$(mktemp -d "$root/$run/.upload.XXXXXXXX")
trap 'rm -rf -- "$stage"' EXIT
IFS= read -r metadata
printf '%s\n' "$metadata" > "$stage/metadata.json"
cat > "$stage/artifact.zip"
[[ "$(stat -c %s "$stage/artifact.zip")" == "$bytes" ]]
printf '%s  %s\n' "$digest" "$stage/artifact.zip" | sha256sum -c --status
sync -f "$stage/artifact.zip"
mv -T "$stage" "$dest"
sync -f "$root/$run"
verify
