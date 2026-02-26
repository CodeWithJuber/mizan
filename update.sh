#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# MIZAN (ميزان) — Self-Updater
#
# Usage:
#   ./update.sh              # Update to latest version
#   ./update.sh --check      # Check for updates without installing
#   ./update.sh --version    # Show current version
#
# Or via other entry points:
#   make update
#   ./start.sh update
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ───── Colors ─────
if [ -t 1 ]; then
    GOLD='\033[0;33m'
    GREEN='\033[0;32m'
    BLUE='\033[0;34m'
    RED='\033[0;31m'
    DIM='\033[2m'
    BOLD='\033[1m'
    NC='\033[0m'
else
    GOLD='' GREEN='' BLUE='' RED='' DIM='' BOLD='' NC=''
fi

info()    { echo -e "  ${BLUE}➜${NC} $1"; }
success() { echo -e "  ${GREEN}✓${NC} $1"; }
warn()    { echo -e "  ${GOLD}⚠${NC} $1"; }
fail()    { echo -e "  ${RED}✗${NC} $1"; }
step()    { echo -e "\n  ${GOLD}━━━${NC} ${BOLD}$1${NC}"; }

# ───── Version ─────

current_version() {
    if [ -f VERSION ]; then
        cat VERSION
    else
        echo "unknown"
    fi
}

# ───── Check for Updates ─────

check_updates() {
    step "Checking for updates"

    local current
    current="$(current_version)"
    info "Current version: ${BOLD}${current}${NC}"

    # Fetch latest from remote without merging
    if ! git fetch origin 2>/dev/null; then
        fail "Could not reach remote repository"
        echo -e "    ${DIM}Check your internet connection${NC}"
        return 1
    fi

    local branch
    branch="$(git branch --show-current 2>/dev/null || echo "main")"

    # Check if there are new commits
    local behind
    behind="$(git rev-list --count HEAD..origin/${branch} 2>/dev/null || echo "0")"

    if [ "$behind" = "0" ]; then
        success "Already up to date (v${current})"
        return 1
    else
        local latest_msg
        latest_msg="$(git log --oneline origin/${branch} -1 2>/dev/null | cut -c1-60)"
        info "${BOLD}${behind} update(s) available${NC}"
        info "Latest: ${DIM}${latest_msg}${NC}"
        return 0
    fi
}

# ───── Stop Running Services ─────

stop_services() {
    step "Stopping running services"

    local stopped=0

    # Stop via PID files
    if [ -f /tmp/mizan-backend.pid ]; then
        kill "$(cat /tmp/mizan-backend.pid)" 2>/dev/null && stopped=1 || true
        rm -f /tmp/mizan-backend.pid
    fi
    if [ -f /tmp/mizan-frontend.pid ]; then
        kill "$(cat /tmp/mizan-frontend.pid)" 2>/dev/null && stopped=1 || true
        rm -f /tmp/mizan-frontend.pid
    fi

    # Stop any stray processes
    pkill -f "uvicorn.*api.main" 2>/dev/null && stopped=1 || true
    pkill -f "vite.*mizan" 2>/dev/null && stopped=1 || true

    if [ "$stopped" = "1" ]; then
        success "Services stopped"
    else
        info "No running services found"
    fi
}

# ───── Pull Latest Code ─────

pull_code() {
    step "Pulling latest code"

    local branch
    branch="$(git branch --show-current 2>/dev/null || echo "main")"

    # Stash any local changes
    local stashed=0
    if ! git diff --quiet 2>/dev/null; then
        info "Stashing local changes..."
        git stash push -m "mizan-update-$(date +%s)" 2>/dev/null && stashed=1 || true
    fi

    # Pull
    if git pull origin "$branch" 2>/dev/null; then
        success "Code updated from ${branch}"
    else
        fail "Git pull failed"
        if [ "$stashed" = "1" ]; then
            info "Restoring local changes..."
            git stash pop 2>/dev/null || true
        fi
        return 1
    fi

    # Restore stashed changes if any
    if [ "$stashed" = "1" ]; then
        info "Restoring local changes..."
        git stash pop 2>/dev/null || warn "Could not auto-restore changes (saved in git stash)"
    fi
}

# ───── Update Backend ─────

update_backend() {
    step "Updating backend"

    if [ -f "venv/bin/activate" ]; then
        # shellcheck disable=SC1091
        source venv/bin/activate
        pip install -e "." --quiet 2>/dev/null
        success "Backend dependencies updated"
    elif [ -f "backend/venv/bin/activate" ]; then
        # shellcheck disable=SC1091
        source backend/venv/bin/activate
        pip install -r backend/requirements.txt --quiet 2>/dev/null
        success "Backend dependencies updated"
    else
        info "No virtual environment found — run: make setup"
    fi
}

# ───── Update Frontend ─────

update_frontend() {
    step "Updating frontend"

    if [ ! -d "frontend" ]; then
        warn "No frontend directory found"
        return
    fi

    cd "$SCRIPT_DIR/frontend"

    if command -v node &>/dev/null; then
        npm install --silent 2>/dev/null
        success "Frontend dependencies installed"

        info "Building frontend..."
        if npm run build 2>/dev/null; then
            success "Frontend built successfully"
        else
            fail "Frontend build failed — check for errors"
        fi
    else
        warn "Node.js not found — skipping frontend build"
    fi

    cd "$SCRIPT_DIR"
}

# ───── Restart Services ─────

restart_services() {
    step "Restarting MIZAN"

    if [ -f "start.sh" ]; then
        # Use start.sh which handles everything
        bash start.sh start &
        local pid=$!

        # Wait a moment for startup
        sleep 3

        if kill -0 "$pid" 2>/dev/null; then
            success "MIZAN is running!"
            echo ""
            echo -e "  ${BLUE}Frontend:${NC}  http://localhost:3000"
            echo -e "  ${BLUE}Backend:${NC}   http://localhost:8000"
            echo -e "  ${BLUE}API Docs:${NC}  http://localhost:8000/docs"
        else
            warn "Start may still be in progress — check: ./start.sh status"
        fi
    else
        info "Start manually with: make dev"
    fi
}

# ───── Docker Update ─────

update_docker() {
    step "Updating Docker deployment"

    local compose_file="docker-compose.yml"
    if [ -f "docker-compose.prod.yml" ]; then
        compose_file="docker-compose.prod.yml"
    fi

    info "Rebuilding containers..."
    docker compose -f "$compose_file" build --quiet 2>/dev/null || \
        docker-compose -f "$compose_file" build --quiet 2>/dev/null

    info "Restarting services..."
    docker compose -f "$compose_file" up -d 2>/dev/null || \
        docker-compose -f "$compose_file" up -d 2>/dev/null

    success "Docker services updated and restarted"
}

# ───── Detect Install Method ─────

detect_method() {
    if docker compose ps 2>/dev/null | grep -q "mizan" || \
       docker-compose ps 2>/dev/null | grep -q "mizan"; then
        echo "docker"
    else
        echo "local"
    fi
}

# ───── Full Update ─────

full_update() {
    echo ""
    echo -e "${GOLD}    ╔═══════════════════════════════════════════════╗${NC}"
    echo -e "${GOLD}    ║       ${BOLD}ميزان${NC}${GOLD}  ·  MIZAN UPDATER                ║${NC}"
    echo -e "${GOLD}    ╚═══════════════════════════════════════════════╝${NC}"
    echo ""

    local old_version
    old_version="$(current_version)"
    local method
    method="$(detect_method)"

    # 1. Check for updates
    if ! check_updates; then
        return 0
    fi

    # 2. Stop services
    if [ "$method" != "docker" ]; then
        stop_services
    fi

    # 3. Pull code
    pull_code || return 1

    # 4. Update deps + rebuild
    if [ "$method" = "docker" ]; then
        update_docker
    else
        update_backend
        update_frontend
        restart_services
    fi

    # 5. Done
    local new_version
    new_version="$(current_version)"

    echo ""
    echo -e "  ${GOLD}═══════════════════════════════════════════════════${NC}"
    echo -e "  ${GREEN}${BOLD}  Update complete!${NC}"
    if [ "$old_version" != "$new_version" ]; then
        echo -e "  ${DIM}  ${old_version} → ${new_version}${NC}"
    fi
    echo -e "  ${GOLD}═══════════════════════════════════════════════════${NC}"
    echo ""
}

# ───── Main ─────

case "${1:-}" in
    --check|-c)
        check_updates
        ;;
    --version|-v)
        echo "MIZAN v$(current_version)"
        ;;
    --help|-h|help)
        echo "Usage: ./update.sh [OPTIONS]"
        echo ""
        echo "Options:"
        echo "  (no args)    Update to latest version"
        echo "  --check      Check for updates without installing"
        echo "  --version    Show current version"
        echo "  --help       Show this help"
        ;;
    "")
        full_update
        ;;
    *)
        echo "Unknown option: $1 (use --help)"
        exit 1
        ;;
esac
