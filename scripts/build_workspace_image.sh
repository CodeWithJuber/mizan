#!/usr/bin/env bash
# Retry the same digest-pinned build once against the official registry.
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo 'Usage: build_workspace_image.sh workspace-runtime|workspace-runner|workspace-browser TAG --load|--push' >&2
  exit 2
fi
case "$1" in
  workspace-runtime|workspace-runner|workspace-browser) dockerfile="docker/Dockerfile.$1" ;;
  *) echo 'Unsupported workspace image' >&2; exit 2 ;;
esac
image_tag="$2"
if [[ ! "$image_tag" =~ ^[A-Za-z0-9][A-Za-z0-9._:/-]*$ ]]; then
  echo 'Invalid image tag' >&2
  exit 2
fi
case "$3" in
  --load) output=(--load) ;;
  # Keep production provenance when exporting directly to the registry.
  --push) output=(--push --provenance=mode=max) ;;
  *) echo 'Unsupported image output mode' >&2; exit 2 ;;
esac

# The browser image downloads Chromium and its system libraries.
limit=3m
[[ "$1" == workspace-browser ]] && limit=10m
last_status=1
for registry in mirror.gcr.io/library docker.io/library; do
  echo "Building $1 using $registry ($limit attempt limit)"
  # Buildx exports/pushes the final image only after its build succeeds. Do not
  # add a separate unconditional push or change any Dockerfile digest here.
  if timeout --signal=TERM --kill-after=15s "$limit" \
    docker buildx build --progress=plain \
      --build-arg "BASE_REGISTRY=$registry" \
      --file "$dockerfile" --tag "$image_tag" "${output[@]}" .; then
    exit 0
  else
    last_status=$?
    echo "Workspace image attempt failed with exit $last_status" >&2
  fi
done
exit "$last_status"
