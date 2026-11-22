#!/usr/bin/env bash
# Remembers, on the runner's own disk, that this exact code passed its checks, so the same code is
# not checked twice. The usual case: a pull request passes, it is merged, and the push to main
# holds the same files. GitHub tests a pull request as the merge would leave it, so when main has
# not moved in between, both runs see one tree and the second can go straight to the deploy.
# Copy this file unchanged into each repository (scripts/ci/ci-verified.sh).
#
#   bash scripts/ci/ci-verified.sh check  [NAME]   Has this code passed NAME? Writes verified=true
#                                                  or verified=false to $GITHUB_OUTPUT. Exits 0.
#   bash scripts/ci/ci-verified.sh record [NAME]   This code has passed NAME. Run it last, in a step
#                                                  or job that runs only when every check passed.
#
# NAME (default: checks) says what passed, for a repository whose runs differ: `full` for the whole
# suite and `smoke` for a part of it, so that a smoke pass never stands in for a full one.
#
# "The same code" is the Git tree of the checked-out commit: every tracked file, the workflows and
# this script among them. A commit message, an author or a merge commit does not change it.
#
# `check` answers verified=false, so everything runs, when:
#   - the run was started by hand (Run workflow) or by a schedule, or is a re-run: someone asked
#     for the checks themselves. That is also how to check a tree again;
#   - the record is older than CI_VERIFIED_DAYS days (default 14);
#   - there is no $CI_RESULTS_DIR, which means this is not the self-hosted runner.
#
# The records are small files in $CI_RESULTS_DIR/verified on the runner's server. They are trusted
# as far as the runner's caches are: whatever can run a job there can write one. The kit is for
# private repositories whose only pushers are the owner and the agents they run.
set -euo pipefail

fail() {
  echo "ci-verified.sh: $1" >&2
  exit 2
}

(($# == 1 || $# == 2)) || fail 'usage: ci-verified.sh check|record [NAME]'
action="$1"
name="${2:-checks}"
[[ "$action" == check || "$action" == record ]] || fail "the first argument is check or record, not '$action'."
[[ "$name" =~ ^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$ ]] ||
  fail "NAME is up to 40 letters, digits, dashes or underscores, not '$name'."
days="${CI_VERIFIED_DAYS:-14}"
[[ "$days" =~ ^[1-9][0-9]{0,3}$ ]] || fail "CI_VERIFIED_DAYS must be a whole number of days, not '$days'."
tree="$(git rev-parse --verify --quiet 'HEAD^{tree}')" || fail 'run it inside the checkout.'

dir="${CI_RESULTS_DIR:+$CI_RESULTS_DIR/verified}"
file="$dir/$name.$tree"

# answer true|false SENTENCE: the result of `check`. A skip is also explained in the run's summary.
answer() {
  [[ -z "${GITHUB_OUTPUT:-}" ]] || printf 'verified=%s\n' "$1" >>"$GITHUB_OUTPUT"
  printf '%s\n' "$2"
  if [[ "$1" == true && -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
    printf '%s\n' "$2" >>"$GITHUB_STEP_SUMMARY"
  fi
  exit 0
}

if [[ "$action" == check ]]; then
  [[ -n "$dir" ]] || answer false 'CI_RESULTS_DIR is not set, so nothing is remembered here: every check runs.'
  case "${GITHUB_EVENT_NAME:-}" in
    workflow_dispatch | schedule) answer false "A $GITHUB_EVENT_NAME run always checks in full." ;;
  esac
  [[ "${GITHUB_RUN_ATTEMPT:-1}" == 1 ]] || answer false 'A re-run always checks in full.'
  [[ -f "$file" ]] || answer false "Tree ${tree:0:12} has not passed '$name' on this runner yet."
  [[ -z "$(find "$file" -mtime "+$days")" ]] ||
    answer false "Tree ${tree:0:12} passed '$name' more than $days days ago: checking again."
  # The record is read as text, never run, and a line is used only in the shape this script writes.
  run="$(sed -n 's/^run=//p' "$file" | head -n 1)"
  [[ "$run" =~ ^https://[A-Za-z0-9._/-]+/actions/runs/[0-9]+$ ]] || run='an earlier run'
  answer true "This code (tree ${tree:0:12}) already passed '$name' in $run. It is not checked again."
fi

if [[ -z "$dir" ]]; then
  echo 'CI_RESULTS_DIR is not set, so this pass is not remembered.'
  exit 0
fi
mkdir -p "$dir"
new="$(mktemp "$dir/.new.XXXXXX")"
{
  printf 'tree=%s\nname=%s\n' "$tree" "$name"
  printf 'commit=%s\n' "${GITHUB_SHA:-$(git rev-parse HEAD)}"
  if [[ -n "${GITHUB_SERVER_URL:-}" && -n "${GITHUB_REPOSITORY:-}" && -n "${GITHUB_RUN_ID:-}" ]]; then
    printf 'run=%s/%s/actions/runs/%s\n' "$GITHUB_SERVER_URL" "$GITHUB_REPOSITORY" "$GITHUB_RUN_ID"
  fi
  printf 'event=%s\nref=%s\n' "${GITHUB_EVENT_NAME:-}" "${GITHUB_REF:-}"
  printf 'recorded=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} >"$new"
mv -f "$new" "$file"
# Records nobody would accept any more, and what an interrupted run left behind.
find "$dir" -maxdepth 1 -type f -mtime "+$days" -exec rm -f -- {} +
echo "Remembered: tree ${tree:0:12} passed '$name'."
