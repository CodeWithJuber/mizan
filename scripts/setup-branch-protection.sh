#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# MIZAN Branch Protection Setup
#
# Sets up GitHub branch protection rules for main branch.
# Requires: gh CLI authenticated with repo admin access.
#
# Usage:
#   ./scripts/setup-branch-protection.sh
#   ./scripts/setup-branch-protection.sh --branch master
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

GOLD='\033[0;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

info()    { echo -e "  ${BLUE}➜${NC} $1"; }
success() { echo -e "  ${GREEN}✓${NC} $1"; }
error()   { echo -e "  ${RED}✗${NC} $1"; exit 1; }
step()    { echo -e "\n  ${GOLD}━━━${NC} ${BOLD}$1${NC}"; }

BRANCH="${1:---branch}"
if [ "$BRANCH" = "--branch" ]; then
    BRANCH="${2:-main}"
fi

# Detect repo from git remote
REPO=$(gh repo view --json nameWithOwner -q '.nameWithOwner' 2>/dev/null) || true
if [ -z "$REPO" ]; then
    REPO=$(git remote get-url origin | sed -E 's|.*github\.com[:/](.+)(\.git)?$|\1|' | sed 's/\.git$//')
fi

if [ -z "$REPO" ]; then
    error "Could not detect repository. Run from within a git repo with a GitHub remote."
fi

echo ""
echo -e "  ${GOLD}═══════════════════════════════════════════════════${NC}"
echo -e "  ${BOLD}  MIZAN Branch Protection Setup${NC}"
echo -e "  ${GOLD}═══════════════════════════════════════════════════${NC}"
echo ""
info "Repository: $REPO"
info "Branch: $BRANCH"

# ───── Check prerequisites ─────

step "Checking prerequisites"

if ! command -v gh &>/dev/null; then
    error "GitHub CLI (gh) not installed. Install: https://cli.github.com"
fi
success "gh CLI found"

if ! gh auth status &>/dev/null; then
    error "Not authenticated. Run: gh auth login"
fi
success "Authenticated with GitHub"

# ───── Apply branch protection rules ─────

step "Applying branch protection rules"

gh api \
  --method PUT \
  -H "Accept: application/vnd.github+json" \
  "/repos/$REPO/branches/$BRANCH/protection" \
  -f "required_status_checks[strict]=true" \
  -f "required_status_checks[contexts][]=Lint" \
  -f "required_status_checks[contexts][]=Test" \
  -f "required_status_checks[contexts][]=Frontend Build" \
  -f "enforce_admins=true" \
  -f "required_pull_request_reviews[dismiss_stale_reviews]=true" \
  -f "required_pull_request_reviews[require_code_owner_reviews]=false" \
  -f "required_pull_request_reviews[required_approving_review_count]=1" \
  -F "restrictions=null" \
  -F "allow_force_pushes=false" \
  -F "allow_deletions=false" \
  -F "block_creations=false" \
  -F "required_linear_history=false" \
  -F "required_conversation_resolution=true" \
  > /dev/null 2>&1

success "Branch protection rules applied"

# ───── Summary ─────

echo ""
echo -e "  ${GOLD}═══════════════════════════════════════════════════${NC}"
echo -e "  ${GREEN}${BOLD}  Branch protection enabled for $BRANCH${NC}"
echo -e "  ${GOLD}═══════════════════════════════════════════════════${NC}"
echo ""
echo -e "  ${BOLD}Rules applied:${NC}"
echo -e "    ${GREEN}✓${NC} Require PR before merging (1 approval)"
echo -e "    ${GREEN}✓${NC} Dismiss stale reviews on new pushes"
echo -e "    ${GREEN}✓${NC} Require status checks to pass:"
echo -e "      • Lint (ruff check + format)"
echo -e "      • Test (pytest)"
echo -e "      • Frontend Build (tsc + vite)"
echo -e "    ${GREEN}✓${NC} Require branches to be up to date"
echo -e "    ${GREEN}✓${NC} Require conversations resolved"
echo -e "    ${GREEN}✓${NC} Enforce for admins too"
echo -e "    ${GREEN}✓${NC} Block force pushes"
echo -e "    ${GREEN}✓${NC} Block branch deletion"
echo ""
echo -e "  ${BOLD}To verify:${NC}"
echo -e "    ${BLUE}https://github.com/$REPO/settings/branches${NC}"
echo ""
