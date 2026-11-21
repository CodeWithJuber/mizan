#!/usr/bin/env bash
# Fails when a workflow uses something GitHub bills for (docs/ci-artifacts.md). The checks run on
# the self-hosted runner labelled mizan, and their caches and results stay on its disk. Nothing goes
# to GitHub's storage. A line that breaks a rule is printed as FILE:LINE: why.
#
#   bash scripts/ci/no-github-billing.sh [FILE...]   (default: every YAML file under .github)
#
# The rules:
#   - Every job names `self-hosted` in runs-on, literally. GitHub-hosted runners bill by the minute,
#     and an expression, a variable or a runner group could pick one.
#   - No reusable workflow from another repository, whose jobs choose their own runners.
#   - No artifact upload or download and no Pages artifact: they use GitHub's artifact storage,
#     500 MB on the free plan and shared with GitHub Packages.
#   - No actions/cache, no cache input on a setup action, no package-manager-cache other than
#     false, no Docker build cache of type gha: they use GitHub's cache storage.
#   - No GitHub Packages (*.pkg.github.com, pushing to ghcr.io): billed with artifact storage.
#   - No CodeQL: on a private repository it needs GitHub Code Security, a paid product.
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
function finish_runs_on() {
  if (!pending) return
  pending = 0
  if (labels !~ /self-hosted/)
    report(runs_on_line, "runs-on must list the labels of a self-hosted runner. A runner group or a GitHub-hosted label bills by the minute.")
}
function finish_file() {
  finish_runs_on()
  if (file != "" && setup_node > setup_node_without_cache)
    report(setup_node_line, "actions/setup-node needs package-manager-cache: false, or it may cache in GitHub's storage.")
}
FNR == 1 { finish_file(); file = FILENAME; setup_node = 0; setup_node_without_cache = 0; setup_node_line = 0 }
/^[ \t]*#/ { next }
pending {
  if ($0 ~ /^[ \t]*-[ \t]/) { labels = labels " " $0; next }
  finish_runs_on()
}
{ line = $0; sub(/[ \t]+#.*$/, "", line) }
line ~ /^[ \t]*(-[ \t]+)?runs-on:/ {
  runs_on = value_of(line)
  if (runs_on ~ /\$\{\{/)
    report(FNR, "runs-on must name the self-hosted labels itself. An expression or a variable could pick a GitHub-hosted runner, which bills by the minute.")
  else if (runs_on == "") { pending = 1; runs_on_line = FNR; labels = "" }
  else if (runs_on !~ /self-hosted/)
    report(FNR, "runs-on must include self-hosted. GitHub-hosted runners bill by the minute.")
}
line ~ /^[ \t]*(-[ \t]+)?uses:[ \t]*["']?[^. \t"']/ && line ~ /\.github\/workflows\// {
  report(FNR, "A reusable workflow from another repository chooses its own runners. Copy its steps here instead.")
}
line ~ /uses:[ \t]*["']?actions\/(upload-artifact|download-artifact|upload-pages-artifact|deploy-pages)([\/@"']|$)/ {
  report(FNR, "Artifacts use GitHub's artifact storage (500 MB free, shared with Packages). Keep results on the runner, as scripts/ci/keep-results.sh does.")
}
line ~ /uses:[ \t]*["']?actions\/cache([\/@"']|$)/ {
  report(FNR, "actions/cache uses GitHub's cache storage. Keep caches on the runner's own disk (docs/ci-artifacts.md).")
}
line ~ /uses:[ \t]*["']?github\/codeql-action/ {
  report(FNR, "CodeQL needs GitHub Code Security on a private repository, which is paid.")
}
line ~ /uses:[ \t]*["']?actions\/setup-node@/ { setup_node++; if (!setup_node_line) setup_node_line = FNR }
line ~ /^[ \t]*package-manager-cache:/ {
  if (value_of(line) == "false") setup_node_without_cache++
  else report(FNR, "package-manager-cache must be false. Its cache goes to GitHub's storage.")
}
line ~ /^[ \t]*cache:/ && value_of(line) != "false" {
  report(FNR, "A cache input saves to GitHub's cache storage. Keep caches on the runner's own disk (docs/ci-artifacts.md).")
}
line ~ /type=gha/ {
  report(FNR, "Docker's gha cache backend uses GitHub's cache storage. Use the runner's own Docker build cache.")
}
line ~ /pkg\.github\.com/ || (line ~ /ghcr\.io/ && line ~ /push|registry:|tags:/) {
  report(FNR, "GitHub Packages storage is billed together with artifact storage. Publish somewhere else.")
}
END { finish_file(); exit failed }
AWK
)

if ! awk "$program" "${files[@]}"; then
  echo 'Something above would be billed by GitHub, or could be (docs/ci-artifacts.md).' >&2
  exit 1
fi
