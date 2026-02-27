#!/bin/bash
# ============================================================
# MIZAN (ميزان) - Startup Script
# "And the heaven He raised and imposed the balance" - 55:7
# ============================================================

set -e

MIZAN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$MIZAN_DIR/backend"
FRONTEND_DIR="$MIZAN_DIR/frontend"

GREEN='\033[0;32m'
GOLD='\033[0;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

print_header() {
    echo ""
    echo -e "${GOLD}╔══════════════════════════════════════════════════════╗${NC}"
    echo -e "${GOLD}║              ميزان  ·  MIZAN AGI SYSTEM              ║${NC}"
    echo -e "${GOLD}║   'And He imposed the balance (Mizan)' - 55:7        ║${NC}"
    echo -e "${GOLD}╚══════════════════════════════════════════════════════╝${NC}"
    echo ""
}

install_backend() {
    echo -e "${BLUE}Installing backend dependencies...${NC}"
    cd "$BACKEND_DIR"
    
    if [ ! -d "venv" ]; then
        python3 -m venv venv
    fi
    
    source venv/bin/activate
    pip install -r requirements.txt --quiet
    echo -e "${GREEN}✓ Backend dependencies installed${NC}"
}

install_frontend() {
    if [ ! -d "$FRONTEND_DIR" ]; then
        echo -e "${GOLD}⚠ Frontend directory not found at $FRONTEND_DIR${NC}"
        echo -e "${GOLD}  Backend-only mode. Use 'mizan serve' for API access.${NC}"
        return 0
    fi
    echo -e "${BLUE}Installing frontend dependencies...${NC}"
    cd "$FRONTEND_DIR"
    npm install --silent
    echo -e "${GREEN}✓ Frontend dependencies installed${NC}"
}

start_backend() {
    echo -e "${BLUE}Starting MIZAN Backend (AQL Engine)...${NC}"
    cd "$BACKEND_DIR"

    if [ -f "venv/bin/activate" ]; then
        source venv/bin/activate
    fi

    # Load .env if exists (filter comments and blank lines safely)
    if [ -f "$MIZAN_DIR/.env" ]; then
        set -a
        while IFS='=' read -r key value; do
            # Skip comments and blank lines
            [[ "$key" =~ ^[[:space:]]*# ]] && continue
            [[ -z "$key" ]] && continue
            # Only export if key looks like a valid env var name
            if [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
                export "$key=$value"
            fi
        done < "$MIZAN_DIR/.env"
        set +a
    else
        echo -e "${GOLD}⚠ No .env file found. Run: cp .env.example .env && edit .env${NC}"
        echo -e "${GOLD}  Or run: mizan setup${NC}"
    fi

    # Run from project root so 'backend.api.main:app' resolves correctly
    cd "$MIZAN_DIR"
    python -m uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 --reload &
    BACKEND_PID=$!
    echo -e "${GREEN}✓ Backend running on http://localhost:8000 (PID: $BACKEND_PID)${NC}"
    echo $BACKEND_PID > /tmp/mizan-backend.pid
}

start_frontend() {
    if [ ! -d "$FRONTEND_DIR" ]; then
        echo -e "${GOLD}⚠ Frontend not available. Backend-only mode.${NC}"
        return 0
    fi
    echo -e "${BLUE}Starting MIZAN Frontend (Sama' Layer)...${NC}"
    cd "$FRONTEND_DIR"
    npm run dev &
    FRONTEND_PID=$!
    echo -e "${GREEN}✓ Frontend running on http://localhost:3000 (PID: $FRONTEND_PID)${NC}"
    echo $FRONTEND_PID > /tmp/mizan-frontend.pid
}

stop_all() {
    echo -e "${BLUE}Stopping MIZAN...${NC}"
    [ -f /tmp/mizan-backend.pid ] && kill $(cat /tmp/mizan-backend.pid) 2>/dev/null || true
    [ -f /tmp/mizan-frontend.pid ] && kill $(cat /tmp/mizan-frontend.pid) 2>/dev/null || true
    pkill -f "uvicorn backend.api.main" 2>/dev/null || true
    pkill -f "uvicorn api.main" 2>/dev/null || true
    pkill -f "vite" 2>/dev/null || true
    rm -f /tmp/mizan-*.pid
    echo -e "${GREEN}✓ MIZAN stopped${NC}"
}

docker_start() {
    echo -e "${BLUE}Starting with Docker Compose...${NC}"
    cd "$MIZAN_DIR"
    
    if [ ! -f ".env" ]; then
        cp .env.example .env
        echo -e "${GOLD}⚠ Created .env from template. Please edit it with your API keys.${NC}"
    fi
    
    docker-compose up -d --build
    echo -e "${GREEN}✓ MIZAN running via Docker${NC}"
    echo -e "${BLUE}  Frontend: http://localhost:3000${NC}"
    echo -e "${BLUE}  Backend:  http://localhost:8000${NC}"
}

show_status() {
    echo -e "${BLUE}MIZAN Status:${NC}"
    curl -s http://localhost:8000/ | python3 -m json.tool 2>/dev/null || echo "Backend not running"
}

run_doctor() {
    echo -e "${BLUE}Running MIZAN Doctor (شفاء - Shifa)...${NC}"
    cd "$BACKEND_DIR"

    if [ -f "venv/bin/activate" ]; then
        source venv/bin/activate
    fi

    cd "$MIZAN_DIR"
    python -m backend.cli doctor "$@"
}

show_help() {
    echo "Usage: ./start.sh [command]"
    echo ""
    echo "Commands:"
    echo "  start       - Start backend + frontend (dev mode)"
    echo "  stop        - Stop all processes"
    echo "  install     - Install dependencies only"
    echo "  update      - Update MIZAN to the latest version"
    echo "  doctor      - Self-healing diagnostic (auto-fix issues)"
    echo "  docker      - Start with Docker Compose"
    echo "  status      - Show system status"
    echo "  backend     - Start backend only"
    echo "  frontend    - Start frontend only"
    echo "  help        - Show this help"
}

# ───── Auto-update check (non-blocking) ─────
check_for_updates() {
    # Silent background check — only shows a notice if updates exist
    if [ -d "$MIZAN_DIR/.git" ] && command -v git &>/dev/null; then
        git fetch origin --quiet 2>/dev/null || return 0
        local branch
        branch="$(git -C "$MIZAN_DIR" branch --show-current 2>/dev/null || echo "main")"
        local behind
        behind="$(git -C "$MIZAN_DIR" rev-list --count HEAD..origin/${branch} 2>/dev/null || echo "0")"
        if [ "$behind" != "0" ] && [ "$behind" != "" ]; then
            echo ""
            echo -e "${GOLD}  ╭─────────────────────────────────────────────╮${NC}"
            echo -e "${GOLD}  │${NC}  ${BOLD}Update available!${NC} ${behind} new update(s)          ${GOLD}│${NC}"
            echo -e "${GOLD}  │${NC}  Run: ${GREEN}./update.sh${NC} or ${GREEN}make update${NC}            ${GOLD}│${NC}"
            echo -e "${GOLD}  ╰─────────────────────────────────────────────╯${NC}"
            echo ""
        fi
    fi
}

# Main
print_header

case "${1:-start}" in
    start)
        check_for_updates
        install_backend
        install_frontend
        start_backend
        sleep 2
        start_frontend
        echo ""
        echo -e "${GOLD}═══════════════════════════════════════════${NC}"
        echo -e "${GREEN}  MIZAN is running!${NC}"
        echo -e "${BLUE}  Frontend: http://localhost:3000${NC}"
        echo -e "${BLUE}  Backend:  http://localhost:8000${NC}"
        echo -e "${BLUE}  API Docs: http://localhost:8000/docs${NC}"
        echo -e "${GOLD}═══════════════════════════════════════════${NC}"
        echo ""
        echo "Press Ctrl+C to stop..."
        wait
        ;;
    stop)
        stop_all
        ;;
    install)
        install_backend
        install_frontend
        ;;
    docker)
        docker_start
        ;;
    update)
        if [ -f "$MIZAN_DIR/update.sh" ]; then
            bash "$MIZAN_DIR/update.sh"
        else
            echo -e "${RED}update.sh not found. Run: git pull origin main${NC}"
        fi
        ;;
    doctor)
        shift
        run_doctor "$@"
        ;;
    status)
        show_status
        ;;
    backend)
        install_backend
        start_backend
        wait
        ;;
    frontend)
        install_frontend
        start_frontend
        wait
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo "Unknown command: $1"
        show_help
        exit 1
        ;;
esac
