#!/usr/bin/env bash
# Fails when a workflow could run this public repository's jobs somewhere unsafe or billed, or
# run a stranger's code with this repository's write token (docs/ci-artifacts.md). A line that
# breaks a rule is printed as FILE:LINE: why.
#
#   bash scripts/ci/public-repo-guard.sh [FILE...]   (default: every YAML file under .github)
#
# The rules:
#   - Every job names one of GitHub's standard hosted runners in runs-on, literally. They are free
#     for a public repository. A self-hosted runner would run any fork's pull request on the
#     machine it lives on, and a larger runner, a runner group or a label list is billed or could
#     pick one; an expression or a variable could too.
#   - A workflow started by pull_request_target runs with this repository's token and secrets, so
#     it never checks out code or names the pull request's head: the pull request's code would run
#     with them.
#   - Every action from another repository is pinned to a full commit SHA: a tag can be moved.
set -euo pipefail

files=()
if (($#)); then
  files=("$@")
else
  cd "$(dirname "${BASH_SOURCE[0]}")/../.."
  while IFS= read -r -d '' file; do files+=("$file"); done \
    < <(git ls-files -z -- '.github/*.yml' '.github/*.yaml')
fi
((${#files[@]})) || exit 0

# POSIX awk, so it runs the same with mawk, gawk and the BSD awk on macOS.
program=$(
  cat <<'AWK'
function report(line, why) { printf "%s:%d: %s\n", file, line, why; failed = 1 }
function value_of(text) {
  sub(/^[^:]*:[ \t]*/, "", text)
  gsub(/^["']|["']$/, "", text)
  return text
}
function finish_file() {
  if (file != "" && target_line && checkout_line)
    report(checkout_line, "A pull_request_target workflow must not check out code: the pull request's code would run with this repository's token and secrets.")
  if (file != "" && target_line && head_line)
    report(head_line, "A pull_request_target workflow must not use the pull request's head: its code would run with this repository's token and secrets.")
}
FNR == 1 { finish_file(); file = FILENAME; target_line = 0; checkout_line = 0; head_line = 0; pending = 0 }
/^[ \t]*#/ { next }
{ line = $0; sub(/[ \t]+#.*$/, "", line) }
pending {
  pending = 0
  if (line ~ /^[ \t]*(-[ \t]|group:|labels:)/)
    report(runs_on_line, "runs-on must name one standard GitHub-hosted runner, such as ubuntu-24.04. A label list or a group picks a self-hosted or a larger runner.")
}
line ~ /^[ \t]*(-[ \t]+)?runs-on:/ {
  runs_on = value_of(line)
  if (runs_on == "") { pending = 1; runs_on_line = FNR }
  else if (runs_on ~ /\$\{\{/)
    report(FNR, "runs-on must name the runner itself. An expression or a variable could pick a self-hosted or a larger runner.")
  else if (runs_on !~ /^(ubuntu-(latest|24\.04|22\.04)(-arm)?|windows-(latest|2025|2022|11-arm)|macos-(latest|26|15|14))$/)
    report(FNR, "runs-on must name one standard GitHub-hosted runner, such as ubuntu-24.04. A self-hosted runner would run forks' code on its machine; a larger runner is billed.")
}
line ~ /(^|[ \t,\[])pull_request_target([ \t]*:|[ \t]*,|[ \t]*\]|[ \t]*$)/ && !target_line { target_line = FNR }
line ~ /uses:[ \t]*["']?actions\/checkout@/ && !checkout_line { checkout_line = FNR }
line ~ /github\.event\.pull_request\.head\./ && !head_line { head_line = FNR }
line ~ /^[ \t]*(-[ \t]+)?uses:/ {
  action = value_of(line)
  if (action !~ /^(\.\/|docker:\/\/)/ && action !~ /@[0-9a-f]{40}$/)
    report(FNR, "Pin an action from another repository to a full commit SHA (with its version in a comment): a tag can be moved.")
}
END { finish_file(); exit failed }
AWK
)

if ! awk "$program" "${files[@]}"; then
  echo 'A workflow above breaks a rule for a public repository (docs/ci-artifacts.md).' >&2
  exit 1
fi
