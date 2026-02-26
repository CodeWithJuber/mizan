.PHONY: help install install-dev install-all setup serve dev test lint format clean docker build

# Default target
help: ## Show this help message
	@echo "ميزان · MIZAN — Agentic Personal AI"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ─── Installation ─────────────────────────────────────────────

install: ## Install core dependencies
	pip install -e .

install-dev: ## Install with development tools (testing, linting)
	pip install -e ".[dev]"
	pre-commit install

install-all: ## Install everything (channels, vector, voice, dev)
	pip install -e ".[all,dev]"
	pre-commit install

setup: ## Full setup: install deps, setup frontend, create .env
	@echo "Setting up MIZAN..."
	pip install -e ".[dev]"
	pre-commit install
	@if [ ! -f .env ]; then cp .env.example .env; echo "Created .env — edit with your API keys"; fi
	cd frontend && npm install
	@echo ""
	@echo "✓ MIZAN setup complete. Edit .env with your API keys, then run: make dev"

# ─── Running ──────────────────────────────────────────────────

serve: ## Start the backend API server
	uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 --reload

dev: ## Start backend + frontend for development
	./start.sh start

cli: ## Start interactive CLI chat
	mizan chat

# ─── Code Quality ─────────────────────────────────────────────

test: ## Run all tests
	pytest tests/ -v --tb=short

test-cov: ## Run tests with coverage report
	pytest tests/ -v --cov=backend --cov-report=term-missing --cov-report=html

lint: ## Lint code with ruff
	ruff check backend/ tests/

format: ## Format code with ruff
	ruff format backend/ tests/
	ruff check --fix backend/ tests/

typecheck: ## Run type checking with mypy
	mypy backend/ --ignore-missing-imports

check: lint typecheck test ## Run all checks (lint + typecheck + test)

# ─── Docker ───────────────────────────────────────────────────

docker: ## Start with Docker Compose
	docker compose up -d --build

docker-full: ## Start with all optional services (Ollama, ChromaDB)
	docker compose --profile ollama --profile vector up -d --build

docker-down: ## Stop Docker Compose
	docker compose down

# ─── Build & Release ──────────────────────────────────────────

build: ## Build Python package
	python -m build

clean: ## Clean build artifacts
	rm -rf dist/ build/ *.egg-info .pytest_cache .mypy_cache .ruff_cache htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

version: ## Show current version
	@cat VERSION

bump-patch: ## Bump patch version (3.0.0 → 3.0.1)
	./scripts/bump-version.sh patch

bump-minor: ## Bump minor version (3.0.0 → 3.1.0)
	./scripts/bump-version.sh minor

bump-major: ## Bump major version (3.0.0 → 4.0.0)
	./scripts/bump-version.sh major

release-patch: ## Full release: bump patch, changelog, tag, push
	./scripts/release.sh patch

release-minor: ## Full release: bump minor, changelog, tag, push
	./scripts/release.sh minor

release-major: ## Full release: bump major, changelog, tag, push
	./scripts/release.sh major

release-dry: ## Dry run of a patch release (no changes)
	./scripts/release.sh patch --dry-run
