# Test runner for Beckn AI Agent Marketplace
# Usage:
#   make test          — run all unit + integration tests (no Docker needed)
#   make test-bap      — run only BAP tests
#   make test-bpp      — run only BPP tests
#   make test-bpp-serg — run only BPP-Serg tests
#   make test-e2e      — run E2E tests (requires docker compose up)
#   make test-cov      — run with coverage report
#   make install-test  — install test dependencies for all services

.PHONY: test test-bap test-bpp test-bpp-serg test-planner test-e2e test-cov install-test

test: test-bap test-bpp test-bpp-serg test-planner

test-bap:
	@echo "\n=== BAP Tests ===\n"
	cd services/bap && python -m pytest tests/ -v --tb=short

test-bpp:
	@echo "\n=== BPP Tests ===\n"
	cd services/bpp && python -m pytest tests/ -v --tb=short

test-bpp-serg:
	@echo "\n=== BPP-Serg Tests ===\n"
	cd services/bpp-serg && python -m pytest tests/ -v --tb=short

test-planner:
	@echo "\n=== Planner Tests ===\n"
	cd services/planner && python -m pytest tests/ -v --tb=short

test-e2e:
	@echo "\n=== E2E Tests (requires Docker) ===\n"
	python -m pytest tests/e2e/ -v --tb=short -m e2e

test-cov:
	@echo "\n=== BAP Coverage ===\n"
	cd services/bap && python -m pytest tests/ --cov=app --cov-report=term-missing --tb=short
	@echo "\n=== BPP Coverage ===\n"
	cd services/bpp && python -m pytest tests/ --cov=app --cov-report=term-missing --tb=short
	@echo "\n=== BPP-Serg Coverage ===\n"
	cd services/bpp-serg && python -m pytest tests/ --cov=app --cov-report=term-missing --tb=short

install-test:
	cd services/bap && pip install -r requirements-test.txt
	cd services/bpp && pip install -r requirements-test.txt
	cd services/bpp-serg && pip install -r requirements-test.txt
	cd services/planner && pip install -r requirements-test.txt
