.PHONY: install install-backend install-frontend dev dev-backend dev-frontend test test-backend test-frontend clean help

# Default target
help:
	@echo "Commander Demo - Available Commands"
	@echo ""
	@echo "  make install          Install all dependencies"
	@echo "  make dev              Run backend and frontend in development mode"
	@echo "  make dev-backend      Run backend only"
	@echo "  make dev-frontend     Run frontend only"
	@echo "  make test             Run all tests"
	@echo "  make test-backend     Run backend tests"
	@echo "  make test-frontend    Run frontend tests"
	@echo "  make clean            Clean build artifacts"
	@echo ""

# Installation
install: install-backend install-frontend

install-backend:
	cd backend && python -m venv .venv && \
		. .venv/bin/activate && \
		pip install -e ".[dev]"

install-frontend:
	cd frontend && pnpm install

# Development
dev:
	@echo "Starting backend and frontend..."
	@make -j2 dev-backend dev-frontend

dev-backend:
	cd backend && . .venv/bin/activate && python -m commander.main

dev-frontend:
	cd frontend && pnpm dev

# Testing
test: test-backend test-frontend

test-backend:
	cd backend && . .venv/bin/activate && pytest

test-frontend:
	cd frontend && pnpm test

# Cleanup
clean:
	rm -rf backend/.venv
	rm -rf backend/__pycache__
	rm -rf backend/src/*.egg-info
	rm -rf backend/.pytest_cache
	rm -rf frontend/node_modules
	rm -rf frontend/dist
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
