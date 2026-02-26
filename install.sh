#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# MIZAN (ميزان) — One-Line Installer
# "And the heaven He raised and imposed the balance" — 55:7
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/CodeWithJuber/mizan/main/install.sh | bash
#
# Install methods:
#   curl -fsSL https://mizan.dev/install.sh | bash                              # auto (pip)
#   curl -fsSL https://mizan.dev/install.sh | bash -s -- --install-method git   # hackable git
#   curl -fsSL https://mizan.dev/install.sh | bash -s -- --install-method docker
#
# Environment options:
#   MIZAN_DIR=<path>              Install directory for git method (default: ~/mizan)
#   MIZAN_SKIP_FRONTEND=1         Skip frontend setup
#   MIZAN_BRANCH=main             Git branch (default: main)
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

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

# ───── Config ─────
MIZAN_METHOD="${MIZAN_METHOD:-auto}"
MIZAN_DIR="${MIZAN_DIR:-$HOME/mizan}"
MIZAN_BRANCH="${MIZAN_BRANCH:-main}"
MIZAN_REPO="https://github.com/CodeWithJuber/mizan.git"
MIZAN_MIN_PYTHON="3.11"
MIZAN_MIN_NODE="18"

# ───── Parse CLI Arguments ─────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --install-method)
            MIZAN_METHOD="$2"
            shift 2
            ;;
        --dir)
            MIZAN_DIR="$2"
            shift 2
            ;;
        --branch)
            MIZAN_BRANCH="$2"
            shift 2
            ;;
        --skip-frontend)
            MIZAN_SKIP_FRONTEND=1
            shift
            ;;
        --help|-h)
            cat <<'HELP'
MIZAN Installer — Agentic Personal AI

Usage:
  curl -fsSL https://raw.githubusercontent.com/CodeWithJuber/mizan/main/install.sh | bash
  curl -fsSL ... | bash -s -- [OPTIONS]

Options:
  --install-method <method>   pip (default), git, or docker
  --dir <path>                Install directory (default: ~/mizan)
  --branch <branch>           Git branch (default: main)
  --skip-frontend             Skip frontend (Node.js) setup
  --help                      Show this help

Examples:
  # Quick install (pip)
  curl -fsSL https://raw.githubusercontent.com/CodeWithJuber/mizan/main/install.sh | bash

  # Hackable install (full source)
  curl -fsSL https://raw.githubusercontent.com/CodeWithJuber/mizan/main/install.sh | bash -s -- --install-method git

  # Docker install
  curl -fsSL https://raw.githubusercontent.com/CodeWithJuber/mizan/main/install.sh | bash -s -- --install-method docker
HELP
            exit 0
            ;;
        *)
            echo "Unknown option: $1 (use --help for usage)"
            exit 1
            ;;
    esac
done

# ───── Helpers ─────

banner() {
    echo ""
    echo -e "${GOLD}    ╔═══════════════════════════════════════════════╗${NC}"
    echo -e "${GOLD}    ║                                               ║${NC}"
    echo -e "${GOLD}    ║         ${BOLD}ميزان${NC}${GOLD}  ·  MIZAN INSTALLER            ║${NC}"
    echo -e "${GOLD}    ║         Agentic Personal AI System            ║${NC}"
    echo -e "${GOLD}    ║                                               ║${NC}"
    echo -e "${GOLD}    ╚═══════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "    ${DIM}\"And He imposed the balance (Mizan)\" — Quran 55:7${NC}"
    echo ""
}

info()    { echo -e "  ${BLUE}➜${NC} $1"; }
success() { echo -e "  ${GREEN}✓${NC} $1"; }
warn()    { echo -e "  ${GOLD}⚠${NC} $1"; }
error()   { echo -e "  ${RED}✗${NC} $1"; }
step()    { echo -e "\n  ${GOLD}━━━${NC} ${BOLD}$1${NC}"; }

command_exists() { command -v "$1" &>/dev/null; }

# ───── OS Detection ─────

detect_os() {
    OS="unknown"
    ARCH="$(uname -m)"

    case "$(uname -s)" in
        Linux*)   OS="linux" ;;
        Darwin*)  OS="macos" ;;
        MINGW*|MSYS*|CYGWIN*) OS="windows" ;;
    esac

    # Detect package manager
    PKG_MANAGER=""
    if command_exists apt-get; then
        PKG_MANAGER="apt"
    elif command_exists dnf; then
        PKG_MANAGER="dnf"
    elif command_exists yum; then
        PKG_MANAGER="yum"
    elif command_exists pacman; then
        PKG_MANAGER="pacman"
    elif command_exists brew; then
        PKG_MANAGER="brew"
    elif command_exists apk; then
        PKG_MANAGER="apk"
    elif command_exists zypper; then
        PKG_MANAGER="zypper"
    fi

    info "Detected: ${BOLD}$OS${NC} ($ARCH) — package manager: ${PKG_MANAGER:-none}"
}

# ───── Version Checking ─────

version_ge() {
    # Returns 0 if $1 >= $2 (semantic version comparison)
    printf '%s\n%s' "$2" "$1" | sort -V -C
}

check_python() {
    step "Checking Python"

    local python_cmd=""

    for cmd in python3 python; do
        if command_exists "$cmd"; then
            local ver
            ver="$($cmd --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)"
            if version_ge "$ver" "$MIZAN_MIN_PYTHON"; then
                python_cmd="$cmd"
                success "Python $ver found ($cmd)"
                PYTHON_CMD="$python_cmd"
                return 0
            fi
        fi
    done

    warn "Python $MIZAN_MIN_PYTHON+ not found"
    install_python
}

install_python() {
    info "Installing Python..."
    case "$PKG_MANAGER" in
        apt)
            sudo apt-get update -qq
            sudo apt-get install -y -qq python3 python3-pip python3-venv
            ;;
        dnf|yum)
            sudo "$PKG_MANAGER" install -y python3 python3-pip
            ;;
        pacman)
            sudo pacman -S --noconfirm python python-pip
            ;;
        brew)
            brew install python@3.12
            ;;
        apk)
            sudo apk add python3 py3-pip
            ;;
        zypper)
            sudo zypper install -y python3 python3-pip
            ;;
        *)
            error "Cannot auto-install Python. Please install Python $MIZAN_MIN_PYTHON+ manually."
            error "Visit: https://www.python.org/downloads/"
            exit 1
            ;;
    esac

    PYTHON_CMD="python3"
    success "Python installed"
}

check_node() {
    step "Checking Node.js"

    if command_exists node; then
        local ver
        ver="$(node --version | grep -oE '[0-9]+' | head -1)"
        if [ "$ver" -ge "$MIZAN_MIN_NODE" ] 2>/dev/null; then
            success "Node.js v$(node --version | tr -d 'v') found"
            return 0
        fi
    fi

    warn "Node.js $MIZAN_MIN_NODE+ not found"
    install_node
}

install_node() {
    info "Installing Node.js..."
    case "$PKG_MANAGER" in
        apt)
            curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
            sudo apt-get install -y -qq nodejs
            ;;
        dnf|yum)
            curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo bash -
            sudo "$PKG_MANAGER" install -y nodejs
            ;;
        pacman)
            sudo pacman -S --noconfirm nodejs npm
            ;;
        brew)
            brew install node@20
            ;;
        apk)
            sudo apk add nodejs npm
            ;;
        zypper)
            sudo zypper install -y nodejs20 npm20
            ;;
        *)
            error "Cannot auto-install Node.js. Please install Node.js $MIZAN_MIN_NODE+ manually."
            error "Visit: https://nodejs.org/"
            exit 1
            ;;
    esac

    success "Node.js installed"
}

check_git() {
    if ! command_exists git; then
        warn "Git not found, installing..."
        case "$PKG_MANAGER" in
            apt)    sudo apt-get install -y -qq git ;;
            dnf|yum) sudo "$PKG_MANAGER" install -y git ;;
            pacman) sudo pacman -S --noconfirm git ;;
            brew)   brew install git ;;
            apk)    sudo apk add git ;;
            zypper) sudo zypper install -y git ;;
            *)
                error "Please install git manually"
                exit 1
                ;;
        esac
        success "Git installed"
    fi
}

check_docker() {
    if ! command_exists docker; then
        warn "Docker not found"
        install_docker
    fi

    if ! docker info &>/dev/null 2>&1; then
        warn "Docker daemon not running"
        if [ "$OS" = "linux" ]; then
            info "Starting Docker..."
            sudo systemctl start docker 2>/dev/null || sudo service docker start 2>/dev/null || true
        fi
    fi
}

install_docker() {
    info "Installing Docker..."
    case "$OS" in
        linux)
            if command_exists curl; then
                curl -fsSL https://get.docker.com | sudo sh
                sudo usermod -aG docker "$USER" 2>/dev/null || true
                success "Docker installed (you may need to log out and back in for group changes)"
            else
                error "Cannot auto-install Docker. Visit: https://docs.docker.com/get-docker/"
                exit 1
            fi
            ;;
        macos)
            if command_exists brew; then
                brew install --cask docker
                info "Docker Desktop installed — please open it from Applications to start the daemon"
            else
                error "Cannot auto-install Docker. Visit: https://docs.docker.com/get-docker/"
                exit 1
            fi
            ;;
        *)
            error "Cannot auto-install Docker on this platform."
            error "Visit: https://docs.docker.com/get-docker/"
            exit 1
            ;;
    esac

    success "Docker installed"
}

# ───── Installation Methods ─────

install_via_pip() {
    step "Installing MIZAN via pip"

    # Create virtual environment
    if [ ! -d "$HOME/.mizan/venv" ]; then
        info "Creating virtual environment..."
        mkdir -p "$HOME/.mizan"
        $PYTHON_CMD -m venv "$HOME/.mizan/venv"
    fi

    # Activate and install
    # shellcheck disable=SC1091
    source "$HOME/.mizan/venv/bin/activate"
    info "Installing mizan package..."
    pip install --upgrade pip -q
    pip install mizan -q 2>/dev/null || {
        warn "PyPI package not available yet. Falling back to git install..."
        MIZAN_METHOD="git"
        install_via_git
        return
    }

    success "MIZAN installed via pip"

    # Run setup
    step "Running MIZAN setup"
    mizan setup || true

    # Add to PATH
    add_to_path "$HOME/.mizan/venv/bin"
}

install_via_git() {
    step "Installing MIZAN from source"

    check_git

    if [ -d "$MIZAN_DIR" ]; then
        info "Directory $MIZAN_DIR exists, updating..."
        cd "$MIZAN_DIR"
        git pull origin "$MIZAN_BRANCH" 2>/dev/null || true
    else
        info "Cloning MIZAN repository..."
        git clone --branch "$MIZAN_BRANCH" --depth 1 "$MIZAN_REPO" "$MIZAN_DIR"
        cd "$MIZAN_DIR"
    fi

    # Backend setup
    info "Setting up Python environment..."
    $PYTHON_CMD -m venv venv
    # shellcheck disable=SC1091
    source venv/bin/activate
    pip install --upgrade pip -q
    pip install -e "." -q
    success "Backend dependencies installed"

    # Frontend setup
    if [ "${MIZAN_SKIP_FRONTEND:-}" != "1" ]; then
        if command_exists node; then
            info "Setting up frontend..."
            cd "$MIZAN_DIR/frontend"
            npm install --silent 2>/dev/null
            success "Frontend dependencies installed"
            cd "$MIZAN_DIR"
        else
            warn "Node.js not available — skipping frontend setup"
            warn "Install Node.js $MIZAN_MIN_NODE+ and run: cd $MIZAN_DIR/frontend && npm install"
        fi
    fi

    # Create .env if not exists
    if [ ! -f "$MIZAN_DIR/.env" ]; then
        if [ -f "$MIZAN_DIR/.env.example" ]; then
            cp "$MIZAN_DIR/.env.example" "$MIZAN_DIR/.env"
            warn "Created .env from template — edit with your API keys"
        fi
    fi

    # Create data directory
    mkdir -p "$MIZAN_DIR/data"

    success "MIZAN installed from source at $MIZAN_DIR"
}

install_via_docker() {
    step "Installing MIZAN via Docker"

    check_docker
    check_git

    if [ -d "$MIZAN_DIR" ]; then
        cd "$MIZAN_DIR"
        git pull origin "$MIZAN_BRANCH" 2>/dev/null || true
    else
        git clone --branch "$MIZAN_BRANCH" --depth 1 "$MIZAN_REPO" "$MIZAN_DIR"
        cd "$MIZAN_DIR"
    fi

    # Create .env
    if [ ! -f ".env" ]; then
        cp .env.example .env
        warn "Created .env from template — edit with your API keys before starting"
    fi

    info "Building Docker containers..."
    docker compose build --quiet 2>/dev/null || docker-compose build --quiet 2>/dev/null
    success "Docker images built"

    info "Starting MIZAN..."
    docker compose up -d 2>/dev/null || docker-compose up -d 2>/dev/null
    success "MIZAN is running!"
}

# ───── PATH Management ─────

add_to_path() {
    local bin_dir="$1"
    if [[ ":$PATH:" != *":$bin_dir:"* ]]; then
        # Detect shell config file
        local shell_rc=""
        if [ -n "${ZSH_VERSION:-}" ] || [ "$(basename "$SHELL" 2>/dev/null)" = "zsh" ]; then
            shell_rc="$HOME/.zshrc"
        elif [ -n "${BASH_VERSION:-}" ] || [ "$(basename "$SHELL" 2>/dev/null)" = "bash" ]; then
            shell_rc="$HOME/.bashrc"
        fi

        if [ -n "$shell_rc" ] && [ -f "$shell_rc" ]; then
            if ! grep -q "mizan" "$shell_rc" 2>/dev/null; then
                echo "" >> "$shell_rc"
                echo "# MIZAN" >> "$shell_rc"
                echo "export PATH=\"$bin_dir:\$PATH\"" >> "$shell_rc"
                info "Added $bin_dir to PATH in $shell_rc"
            fi
        fi
        export PATH="$bin_dir:$PATH"
    fi
}

# ───── Post-Install ─────

print_success() {
    echo ""
    echo -e "  ${GOLD}═══════════════════════════════════════════════════${NC}"
    echo -e "  ${GREEN}${BOLD}  MIZAN installed successfully!${NC}"
    echo -e "  ${GOLD}═══════════════════════════════════════════════════${NC}"
    echo ""

    case "$MIZAN_METHOD" in
        pip)
            echo -e "  ${BOLD}Quick Start:${NC}"
            echo -e "    ${GOLD}mizan chat${NC}              # Chat in terminal"
            echo -e "    ${GOLD}mizan serve${NC}             # Start API server"
            echo ""
            ;;
        git)
            echo -e "  ${BOLD}Quick Start:${NC}"
            echo -e "    ${GOLD}cd $MIZAN_DIR${NC}"
            echo -e "    ${GOLD}source venv/bin/activate${NC}"
            echo -e "    ${GOLD}mizan chat${NC}              # Chat in terminal"
            echo -e "    ${GOLD}make dev${NC}                # Start full stack"
            echo ""
            echo -e "  ${BOLD}Or run directly:${NC}"
            echo -e "    ${GOLD}./start.sh start${NC}        # Backend + Frontend"
            echo ""
            echo -e "  ${BOLD}Update later:${NC}"
            echo -e "    ${GOLD}./update.sh${NC}             # One-command update"
            echo -e "    ${GOLD}make update${NC}             # Or via make"
            echo ""
            ;;
        docker)
            echo -e "  ${BOLD}Quick Start:${NC}"
            echo -e "    ${GOLD}cd $MIZAN_DIR${NC}"
            echo -e "    ${GOLD}# Edit .env with your ANTHROPIC_API_KEY${NC}"
            echo -e "    ${GOLD}docker compose up -d${NC}    # Start all services"
            echo ""
            echo -e "  ${BOLD}Update later:${NC}"
            echo -e "    ${GOLD}./update.sh${NC}             # One-command update"
            echo ""
            ;;
    esac

    echo -e "  ${BOLD}Important:${NC}"
    echo -e "    Set your API key in ${GOLD}.env${NC} or environment:"
    echo -e "    ${DIM}export ANTHROPIC_API_KEY=sk-ant-...${NC}"
    echo ""
    echo -e "  ${BOLD}Access:${NC}"
    echo -e "    Frontend:  ${BLUE}http://localhost:3000${NC}"
    echo -e "    Backend:   ${BLUE}http://localhost:8000${NC}"
    echo -e "    API Docs:  ${BLUE}http://localhost:8000/docs${NC}"
    echo ""
    echo -e "  ${BOLD}Documentation:${NC}"
    echo -e "    ${BLUE}https://github.com/CodeWithJuber/mizan${NC}"
    echo ""
    echo -e "  ${DIM}بسم الله الرحمن الرحيم${NC}"
    echo ""
}

# ───── Interactive Mode ─────

interactive_setup() {
    echo -e "  ${BOLD}Choose installation method:${NC}"
    echo ""
    echo -e "    ${GOLD}1)${NC} pip install ${DIM}(recommended — quick setup)${NC}"
    echo -e "    ${GOLD}2)${NC} git clone   ${DIM}(development — full source)${NC}"
    echo -e "    ${GOLD}3)${NC} docker      ${DIM}(containerized — production)${NC}"
    echo ""

    read -rp "  Select [1/2/3] (default: 1): " choice
    case "${choice:-1}" in
        1) MIZAN_METHOD="pip" ;;
        2) MIZAN_METHOD="git" ;;
        3) MIZAN_METHOD="docker" ;;
        *)
            error "Invalid choice"
            exit 1
            ;;
    esac
}

# ───── Main ─────

main() {
    banner
    detect_os

    # Resolve "auto" method
    if [ "$MIZAN_METHOD" = "auto" ]; then
        if [ -t 0 ]; then
            # Interactive terminal — let user choose
            interactive_setup
        else
            # Piped from curl — default to pip
            MIZAN_METHOD="pip"
        fi
    fi

    # Prerequisites
    if [ "$MIZAN_METHOD" != "docker" ]; then
        check_python
        if [ "$MIZAN_METHOD" = "git" ] && [ "${MIZAN_SKIP_FRONTEND:-}" != "1" ]; then
            check_node
        fi
    fi

    # Install
    case "$MIZAN_METHOD" in
        pip)    install_via_pip ;;
        git)    install_via_git ;;
        docker) install_via_docker ;;
        *)
            error "Unknown method: $MIZAN_METHOD"
            error "Use: pip, git, or docker"
            exit 1
            ;;
    esac

    print_success
}

main
