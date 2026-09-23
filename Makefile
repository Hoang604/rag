.PHONY: check lint typecheck ui server migrate help

help:
	@echo "Available commands:"
	@echo "  make check      - Run QA verification pipeline (ruff, ty)"
	@echo "  make lint       - Run ruff check with auto-fix"
	@echo "  make typecheck  - Run ty type checker"
	@echo "  make ui         - Launch Legal Reviewer Studio web application"
	@echo "  make server     - Launch Vietnamese Traffic Law MCP server over stdio"
	@echo "  make migrate    - Run PostgreSQL database migrations"

check:
	./scripts/check.sh

lint:
	uv run ruff check --fix

typecheck:
	uv run ty check

ui:
	uv run rag-eval ui

server:
	uv run rag-eval legal-server

migrate:
	uv run rag-eval legal-migrate
