#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# MIZAN Release Script
#
# Creates a full release: bump version, update changelog, commit, tag, push.
# GitHub Actions then auto-publishes to PyPI + GHCR.
#
# Usage:
#   ./scripts/release.sh patch          # 3.0.0 → 3.0.1
#   ./scripts/release.sh minor          # 3.0.0 → 3.1.0
#   ./scripts/release.sh major          # 3.0.0 → 4.0.0
#   ./scripts/release.sh 3.2.0          # exact version
#   ./scripts/release.sh patch --dry-run
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# ───── Colors ─────
GOLD='\033[0;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
DIM='\033[2m'
BOLD='\033[1m'
NC='\033[0m'

info()    { echo -e "  ${BLUE}➜${NC} $1"; }
success() { echo -e "  ${GREEN}✓${NC} $1"; }
warn()    { echo -e "  ${GOLD}⚠${NC} $1"; }
error()   { echo -e "  ${RED}✗${NC} $1"; exit 1; }
step()    { echo -e "\n  ${GOLD}━━━${NC} ${BOLD}$1${NC}"; }

DRY_RUN=false
BUMP_TYPE=""

# Parse args
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        patch|minor|major|beta|rc) BUMP_TYPE="$arg" ;;
        *)
            if [[ "$arg" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
                BUMP_TYPE="$arg"
            else
                echo "Usage: $0 <patch|minor|major|X.Y.Z> [--dry-run]"
                exit 1
            fi
            ;;
    esac
done

if [ -z "$BUMP_TYPE" ]; then
    echo "Usage: $0 <patch|minor|major|X.Y.Z> [--dry-run]"
    exit 1
fi

cd "$ROOT_DIR"

# ───── Pre-flight checks ─────

step "Pre-flight checks"

# Must be on main branch
BRANCH=$(git branch --show-current)
if [ "$BRANCH" != "main" ] && [ "$BRANCH" != "master" ]; then
    warn "Not on main/master branch (currently on: $BRANCH)"
    read -rp "  Continue anyway? [y/N] " confirm
    if [ "${confirm:-n}" != "y" ]; then
        error "Aborted. Switch to main branch first."
    fi
fi
success "Branch: $BRANCH"

# No uncommitted changes
if ! git diff --quiet HEAD 2>/dev/null; then
    error "Uncommitted changes detected. Commit or stash first."
fi
success "Working tree clean"

# Up to date with remote
git fetch origin "$BRANCH" 2>/dev/null || true
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse "origin/$BRANCH" 2>/dev/null || echo "$LOCAL")
if [ "$LOCAL" != "$REMOTE" ]; then
    warn "Local branch is not up to date with origin/$BRANCH"
    info "Run: git pull origin $BRANCH"
fi
success "Checked remote sync"

# ───── Bump version ─────

step "Bumping version"

CURRENT=$(cat VERSION | tr -d '[:space:]')
"$SCRIPT_DIR/bump-version.sh" "$BUMP_TYPE"
NEW_VERSION=$(cat VERSION | tr -d '[:space:]')

if [ "$DRY_RUN" = true ]; then
    echo -e "\n  ${GOLD}[DRY RUN]${NC} Would release ${GREEN}v$NEW_VERSION${NC}"
    echo "  Reverting changes..."
    git checkout -- .
    exit 0
fi

# ───── Update CHANGELOG ─────

step "Updating CHANGELOG"

CHANGELOG="$ROOT_DIR/CHANGELOG.md"
DATE=$(date +%Y-%m-%d)

# Collect commits since last tag
LAST_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "")
if [ -n "$LAST_TAG" ]; then
    COMMITS=$(git log "$LAST_TAG..HEAD" --pretty=format:"- %s" --no-merges 2>/dev/null || echo "- Initial release")
else
    COMMITS=$(git log --pretty=format:"- %s" --no-merges -20 2>/dev/null || echo "- Initial release")
fi

# Categorize commits
FEATURES=$(echo "$COMMITS" | grep -iE "^- (feat|add|new)" || true)
FIXES=$(echo "$COMMITS" | grep -iE "^- (fix|bug|patch|hotfix)" || true)
CHANGES=$(echo "$COMMITS" | grep -iE "^- (refactor|update|improve|enhance|chore|docs|style|perf)" || true)
OTHER=$(echo "$COMMITS" | grep -viE "^- (feat|add|new|fix|bug|patch|hotfix|refactor|update|improve|enhance|chore|docs|style|perf)" || true)

# Build changelog entry
ENTRY="## [v$NEW_VERSION] — $DATE"
ENTRY+="\n"

if [ -n "$FEATURES" ]; then
    ENTRY+="\n### Added\n$FEATURES\n"
fi
if [ -n "$FIXES" ]; then
    ENTRY+="\n### Fixed\n$FIXES\n"
fi
if [ -n "$CHANGES" ]; then
    ENTRY+="\n### Changed\n$CHANGES\n"
fi
if [ -n "$OTHER" ]; then
    ENTRY+="\n### Other\n$OTHER\n"
fi

# Prepend to CHANGELOG (after header)
if [ -f "$CHANGELOG" ]; then
    # Insert after the header line
    HEADER=$(head -3 "$CHANGELOG")
    BODY=$(tail -n +4 "$CHANGELOG")
    printf "%s\n\n%b\n%s" "$HEADER" "$ENTRY" "$BODY" > "$CHANGELOG"
else
    printf "# MIZAN Changelog\n\nAll notable changes to this project will be documented in this file.\n\n%b\n" "$ENTRY" > "$CHANGELOG"
fi

success "CHANGELOG.md updated"

# ───── Commit ─────

step "Committing release"

git add VERSION backend/_version.py pyproject.toml frontend/package.json \
       backend/cli.py backend/api/main.py CHANGELOG.md

git commit -m "chore: release v$NEW_VERSION

Bump version $CURRENT → $NEW_VERSION and update CHANGELOG."

success "Committed: chore: release v$NEW_VERSION"

# ───── Tag ─────

step "Creating git tag"

git tag -a "v$NEW_VERSION" -m "Release v$NEW_VERSION"
success "Tagged: v$NEW_VERSION"

# ───── Push ─────

step "Pushing to origin"

git push origin "$BRANCH"
git push origin "v$NEW_VERSION"
success "Pushed branch and tag"

# ───── Done ─────

echo ""
echo -e "  ${GOLD}═══════════════════════════════════════════════════${NC}"
echo -e "  ${GREEN}${BOLD}  Released MIZAN v$NEW_VERSION${NC}"
echo -e "  ${GOLD}═══════════════════════════════════════════════════${NC}"
echo ""
echo -e "  ${BOLD}What happens next:${NC}"
echo -e "    ${GOLD}1.${NC} GitHub Actions builds and tests the release"
echo -e "    ${GOLD}2.${NC} PyPI package published automatically"
echo -e "    ${GOLD}3.${NC} Docker images pushed to ghcr.io"
echo -e "    ${GOLD}4.${NC} GitHub Release created with changelog"
echo ""
echo -e "  ${BOLD}Verify:${NC}"
echo -e "    ${BLUE}https://github.com/CodeWithJuber/mizan/releases/tag/v$NEW_VERSION${NC}"
echo -e "    ${BLUE}https://pypi.org/project/mizan/$NEW_VERSION/${NC}"
echo ""
