#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# MIZAN (ميزان) — Server Deployment Script
# "And the heaven He raised and imposed the balance" — 55:7
#
# Usage:
#   ./deploy.sh                    # Deploy without SSL
#   ./deploy.sh --ssl example.com  # Deploy with SSL + Let's Encrypt
#   ./deploy.sh --update           # Update existing deployment
#   ./deploy.sh --stop             # Stop all services
#   ./deploy.sh --status           # Check service status
#   ./deploy.sh --logs             # View logs
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

# ───── Colors ─────
GOLD='\033[0;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
DIM='\033[2m'
BOLD='\033[1m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ───── Helpers ─────
info()    { echo -e "  ${BLUE}➜${NC} $1"; }
success() { echo -e "  ${GREEN}✓${NC} $1"; }
warn()    { echo -e "  ${GOLD}⚠${NC} $1"; }
error()   { echo -e "  ${RED}✗${NC} $1"; exit 1; }
step()    { echo -e "\n  ${GOLD}━━━${NC} ${BOLD}$1${NC}"; }

banner() {
    echo ""
    echo -e "${GOLD}    ╔═══════════════════════════════════════════════╗${NC}"
    echo -e "${GOLD}    ║                                               ║${NC}"
    echo -e "${GOLD}    ║       ${BOLD}ميزان${NC}${GOLD}  ·  MIZAN SERVER DEPLOY           ║${NC}"
    echo -e "${GOLD}    ║       Production Deployment Tool              ║${NC}"
    echo -e "${GOLD}    ║                                               ║${NC}"
    echo -e "${GOLD}    ╚═══════════════════════════════════════════════╝${NC}"
    echo ""
}

# ───── Prerequisite Checks ─────

check_prerequisites() {
    step "Checking prerequisites"

    if ! command -v docker &>/dev/null; then
        error "Docker is not installed. Visit: https://docs.docker.com/get-docker/"
    fi
    success "Docker found: $(docker --version | head -1)"

    if ! docker compose version &>/dev/null && ! command -v docker-compose &>/dev/null; then
        error "Docker Compose is not installed."
    fi
    success "Docker Compose available"

    if ! docker info &>/dev/null 2>&1; then
        error "Docker daemon is not running. Start it with: sudo systemctl start docker"
    fi
    success "Docker daemon running"
}

# ───── Environment Setup ─────

setup_env() {
    step "Setting up environment"

    if [ ! -f .env ]; then
        if [ -f .env.example ]; then
            cp .env.example .env
            warn "Created .env from template"
        else
            error "No .env or .env.example found"
        fi
    fi

    # Check required keys
    source .env 2>/dev/null || true

    if [ -z "${ANTHROPIC_API_KEY:-}" ] || [ "${ANTHROPIC_API_KEY}" = "sk-ant-your-key-here" ]; then
        warn "ANTHROPIC_API_KEY not set in .env"
        echo -e "    ${DIM}Edit .env and add your API key before starting${NC}"
    else
        success "ANTHROPIC_API_KEY configured"
    fi

    if [ -z "${SECRET_KEY:-}" ] || [ "${SECRET_KEY}" = "change-this-to-a-secure-random-string" ]; then
        info "Generating secure SECRET_KEY..."
        NEW_KEY=$(openssl rand -hex 32 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(32))")
        sed -i "s|SECRET_KEY=.*|SECRET_KEY=${NEW_KEY}|" .env
        success "SECRET_KEY generated"
    else
        success "SECRET_KEY configured"
    fi
}

# ───── SSL Setup ─────

setup_ssl() {
    local domain="$1"
    step "Setting up SSL for ${domain}"

    # Use SSL nginx config
    export NGINX_CONF="nginx.conf"
    export DOMAIN="$domain"

    # Substitute domain in nginx config
    sed "s/\${DOMAIN}/${domain}/g" docker/nginx.conf > docker/nginx-generated.conf
    export NGINX_CONF="nginx-generated.conf"

    # Get initial certificate
    info "Obtaining SSL certificate via Let's Encrypt..."

    # Start nginx temporarily with HTTP only for ACME challenge
    docker compose -f docker-compose.prod.yml up -d nginx

    docker compose -f docker-compose.prod.yml run --rm certbot \
        certbot certonly --webroot \
        --webroot-path=/var/www/certbot \
        --email "${SSL_EMAIL:-admin@${domain}}" \
        --agree-tos \
        --no-eff-email \
        -d "$domain"

    success "SSL certificate obtained for ${domain}"

    # Restart nginx with SSL config
    docker compose -f docker-compose.prod.yml restart nginx
    success "Nginx restarted with SSL"
}

# ───── Deploy ─────

deploy() {
    local ssl_domain="${1:-}"

    step "Building and deploying MIZAN"

    local compose_cmd="docker compose -f docker-compose.prod.yml"

    if [ -n "$ssl_domain" ]; then
        export DOMAIN="$ssl_domain"
        export NGINX_CONF="nginx.conf"
        export ALLOWED_ORIGINS="https://${ssl_domain}"
        sed "s/\${DOMAIN}/${ssl_domain}/g" docker/nginx.conf > docker/nginx-generated.conf
        export NGINX_CONF="nginx-generated.conf"
    fi

    info "Building Docker images..."
    $compose_cmd build

    info "Starting services..."
    $compose_cmd up -d

    if [ -n "$ssl_domain" ]; then
        setup_ssl "$ssl_domain"
        # Start certbot for auto-renewal
        $compose_cmd --profile ssl up -d certbot
    fi

    # Wait for backend health
    info "Waiting for backend to be healthy..."
    local retries=0
    local max_retries=30
    while [ $retries -lt $max_retries ]; do
        if docker inspect --format='{{.State.Health.Status}}' mizan-backend 2>/dev/null | grep -q "healthy"; then
            break
        fi
        retries=$((retries + 1))
        sleep 2
    done

    if [ $retries -ge $max_retries ]; then
        warn "Backend health check timed out — check logs with: ./deploy.sh --logs"
    else
        success "Backend is healthy"
    fi

    echo ""
    echo -e "  ${GOLD}═══════════════════════════════════════════════════${NC}"
    echo -e "  ${GREEN}${BOLD}  MIZAN deployed successfully!${NC}"
    echo -e "  ${GOLD}═══════════════════════════════════════════════════${NC}"
    echo ""

    if [ -n "$ssl_domain" ]; then
        echo -e "  ${BOLD}Access:${NC}"
        echo -e "    ${BLUE}https://${ssl_domain}${NC}"
        echo -e "    ${BLUE}https://${ssl_domain}/api/docs${NC}  (API docs)"
    else
        echo -e "  ${BOLD}Access:${NC}"
        echo -e "    ${BLUE}http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo 'your-server-ip')${NC}"
        echo -e "    ${BLUE}http://localhost/api/docs${NC}  (API docs)"
    fi

    echo ""
    echo -e "  ${BOLD}Management:${NC}"
    echo -e "    ${GOLD}./deploy.sh --status${NC}   Check service status"
    echo -e "    ${GOLD}./deploy.sh --logs${NC}     View logs"
    echo -e "    ${GOLD}./deploy.sh --update${NC}   Pull & redeploy"
    echo -e "    ${GOLD}./deploy.sh --stop${NC}     Stop all services"
    echo ""
    echo -e "  ${DIM}بسم الله الرحمن الرحيم${NC}"
    echo ""
}

# ───── Update ─────

update() {
    step "Updating MIZAN deployment"

    info "Pulling latest code..."
    git pull origin "$(git branch --show-current)" || warn "Git pull failed — using local code"

    info "Rebuilding images..."
    docker compose -f docker-compose.prod.yml build

    info "Restarting services..."
    docker compose -f docker-compose.prod.yml up -d

    success "MIZAN updated and restarted"
}

# ───── Stop ─────

stop() {
    step "Stopping MIZAN"
    docker compose -f docker-compose.prod.yml down
    success "All services stopped"
}

# ───── Status ─────

status() {
    step "MIZAN Service Status"
    echo ""
    docker compose -f docker-compose.prod.yml ps
    echo ""

    # Health check
    if curl -sf http://localhost/api/ > /dev/null 2>&1; then
        success "API is responding"
        echo -e "    ${DIM}$(curl -sf http://localhost/ 2>/dev/null | head -c 200)${NC}"
    elif curl -sf http://localhost:8000/ > /dev/null 2>&1; then
        success "API is responding (direct)"
    else
        warn "API is not responding"
    fi
}

# ───── Logs ─────

logs() {
    docker compose -f docker-compose.prod.yml logs -f --tail=100
}

# ───── Help ─────

show_help() {
    echo "Usage: ./deploy.sh [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  (no args)             Deploy without SSL (HTTP only)"
    echo "  --ssl <domain>        Deploy with SSL via Let's Encrypt"
    echo "  --update              Update and redeploy"
    echo "  --stop                Stop all services"
    echo "  --status              Show service status"
    echo "  --logs                View service logs"
    echo "  --help                Show this help"
    echo ""
    echo "Examples:"
    echo "  ./deploy.sh                        # Quick deploy (HTTP)"
    echo "  ./deploy.sh --ssl mizan.example.com # Deploy with SSL"
    echo "  SSL_EMAIL=you@email.com ./deploy.sh --ssl mizan.example.com"
    echo ""
    echo "Environment variables (set in .env):"
    echo "  ANTHROPIC_API_KEY    Your Anthropic API key (required)"
    echo "  SECRET_KEY           JWT secret (auto-generated if missing)"
    echo "  DOMAIN               Your domain name (for SSL)"
    echo "  HTTP_PORT            HTTP port (default: 80)"
    echo "  HTTPS_PORT           HTTPS port (default: 443)"
    echo "  LOG_LEVEL            Logging level (default: INFO)"
}

# ───── Main ─────

main() {
    banner

    case "${1:-}" in
        --ssl)
            if [ -z "${2:-}" ]; then
                error "Usage: ./deploy.sh --ssl <domain>"
            fi
            check_prerequisites
            setup_env
            deploy "$2"
            ;;
        --update)
            check_prerequisites
            update
            ;;
        --stop)
            stop
            ;;
        --status)
            status
            ;;
        --logs)
            logs
            ;;
        --help|-h|help)
            show_help
            ;;
        "")
            check_prerequisites
            setup_env
            deploy ""
            ;;
        *)
            error "Unknown option: $1. Use --help for usage."
            ;;
    esac
}

main "$@"
