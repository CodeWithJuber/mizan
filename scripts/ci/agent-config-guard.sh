#!/usr/bin/env bash
# Fails a pull request that changes what coding agents run or load, unless the repository's
# owner wrote it or a maintainer labelled it after reading it (docs/forgekit.md).
#
#   bash scripts/ci/agent-config-guard.sh [BASE [HEAD]]   (default: HEAD^1 and HEAD, which is
#                                                          the pull request's merge commit)
#
# Hook and MCP files are executed by the agent the moment someone opens a checkout of the branch
# (a SessionStart hook runs before any approval prompt), so a change to them deserves a reading
# by eye even when every test passes. The workflow passes these in the environment, never inline:
#   PR_AUTHOR   the pull request author's login          (empty outside a pull request)
#   REPO_OWNER  the repository owner's login
#   PR_LABELS   the pull request's labels, comma-separated
# Outside a pull request (a push, the weekly run) the guard only lists what it would watch.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."

LABEL="agent-config-reviewed"
base="${1:-HEAD^1}"
head="${2:-HEAD}"

# What an agent executes or loads from the repository as configuration.
watched() {
  case "$1" in
    .claude/settings.json | .claude/settings.local.json | .mcp.json | opencode.json | AGENTS.md) return 0 ;;
    .claude/hooks/* | .claude/agents/* | .claude/commands/*) return 0 ;;
    # Skills are instructions every agent loads; ForgeKit's Jev now writes learned ones itself.
    .claude/skills/* | .agents/skills/*) return 0 ;;
    .codex/* | .gemini/* | .cursor/* | .github/hooks/* | .opencode/* | .forge/*) return 0 ;;
    .vscode/mcp.json | .roo/* | .zed/* | .continue/* | .kimi-code/* | .openclaw/* | .pi/* | .hermes/*) return 0 ;;
    .aider.conf.yml | scripts/ci/agent-config-guard.sh) return 0 ;;
    *) return 1 ;;
  esac
}

if ! git rev-parse --verify --quiet "$base" >/dev/null; then
  echo "agent-config-guard: no base commit ($base) to compare with; nothing to check."
  exit 0
fi

changed=()
while IFS= read -r -d '' path; do
  if watched "$path"; then changed+=("$path"); fi
done < <(git diff -z --name-only "$base" "$head" --)

if ((${#changed[@]} == 0)); then
  echo "agent-config-guard: no agent hook or MCP configuration changed."
  exit 0
fi

echo "agent-config-guard: this change touches what coding agents run or load:"
printf '  %s\n' "${changed[@]}"

author="${PR_AUTHOR:-}"
owner="${REPO_OWNER:-}"
labels=",${PR_LABELS:-},"

if [[ -z "$author" ]]; then
  echo "agent-config-guard: not a pull request; listed only."
  exit 0
fi
if [[ -n "$owner" && "$author" == "$owner" ]]; then
  echo "agent-config-guard: written by the repository owner ($owner); allowed."
  exit 0
fi
if [[ "$labels" == *",$LABEL,"* ]]; then
  echo "agent-config-guard: labelled $LABEL by a maintainer; allowed."
  exit 0
fi

echo "agent-config-guard: a maintainer must read these files and add the label '$LABEL'." >&2
echo "  They run in an agent session as soon as someone checks out this branch." >&2
exit 1
