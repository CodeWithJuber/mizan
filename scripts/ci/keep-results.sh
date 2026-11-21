#!/usr/bin/env bash
# Keeps a job's output on the self-hosted runner's disk, never as a GitHub artifact
# (docs/ci-artifacts.md). The files land in $CI_RESULTS_DIR/<run id>-<attempt>/NAME/, a directory
# private to this repository that the runner prunes after 14 days. The job summary names that
# directory and each file's SHA-256; the path is the same on the server, so scp can copy it as is.
#
#   bash scripts/ci/keep-results.sh NAME [--optional] [--base DIR] PATH...
#
# PATHs are files or directories relative to DIR (default: the current directory). Only regular,
# visible files are kept: no symlinks, nothing whose name or directory starts with a dot. Without
# --optional, a run that produced none of them fails.
set -euo pipefail

: "${CI_RESULTS_DIR:?runs on the self-hosted runner only}"
: "${GITHUB_RUN_ID:?} ${GITHUB_RUN_ATTEMPT:?}"

usage() {
  echo 'Usage: keep-results.sh NAME [--optional] [--base DIR] PATH...' >&2
  exit 2
}

(($# >= 2)) || usage
name=$1
shift
optional=false
base=.
paths=()
while (($#)); do
  case $1 in
    --optional) optional=true ;;
    --base)
      (($# >= 2)) || usage
      base=$2
      shift
      ;;
    *) paths+=("$1") ;;
  esac
  shift
done
((${#paths[@]})) || usage
[[ $name =~ ^[a-z0-9][a-z0-9-]*$ ]] || { echo "Invalid results name: $name" >&2; exit 2; }
[[ $GITHUB_RUN_ID =~ ^[0-9]+$ && $GITHUB_RUN_ATTEMPT =~ ^[0-9]+$ ]] || exit 2
present=()
for path in "${paths[@]}"; do
  if [[ $path == /* || /$path/ == */../* ]]; then
    echo "A results path must stay inside its base directory: $path" >&2
    exit 2
  fi
  if [[ -e $base/$path && ! -L $base/$path ]]; then present+=("$path"); fi
done

files=()
if ((${#present[@]})); then
  while IFS= read -r -d '' file; do files+=("${file#./}"); done < <(
    cd "$base" && find "${present[@]}" -name '.*' ! -name . -prune -o -type f -print0 | sort -z
  )
fi
if ! ((${#files[@]})); then
  if [[ $optional == true ]]; then
    echo "::notice::No files were produced for $name."
    exit 0
  fi
  echo "::error::No files were produced for $name."
  exit 1
fi

destination="$CI_RESULTS_DIR/$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT/$name"
mkdir -p -- "$destination"
printf '%s\0' "${files[@]}" | tar --directory="$base" --null --files-from=- --create --file=- |
  tar --directory="$destination" --extract --file=-

bytes=$(find "$destination" -type f -printf '%s\n' | awk '{ total += $1 } END { print total + 0 }')
{
  # shellcheck disable=SC2016 # The backticks are Markdown for the summary, not a command.
  printf '**%s** kept on the runner: `%s` (%d files, %d bytes; kept 14 days).\n' \
    "$name" "$destination" "${#files[@]}" "$bytes"
  if ((${#files[@]} <= 10)); then
    printf '\n```\n'
    (cd "$destination" && sha256sum -- "${files[@]}")
    printf '```\n'
  fi
} | tee -a "${GITHUB_STEP_SUMMARY:-/dev/null}"
