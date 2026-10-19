.PHONY: check lint typecheck api ui server migrate thesis thesis-clean help

help:
	@echo "Available commands:"
	@echo "  make check        - Run QA verification pipeline (ruff, ty)"
	@echo "  make lint         - Run ruff check with auto-fix"
	@echo "  make typecheck    - Run ty type checker"
	@echo "  make api          - Launch the legal lookup and answer FastAPI backend"
	@echo "  make ui           - Launch the legal lookup and answer web application"
	@echo "  make server       - Launch Vietnamese Traffic Law MCP server over stdio"
	@echo "  make migrate      - Run PostgreSQL database migrations"
	@echo "  make thesis       - Build thesis LaTeX report into thesis/latex/main.pdf"
	@echo "  make thesis-clean - Remove LaTeX auxiliary build files"

check:
	uv run python scripts/check.py

lint:
	uv run ruff check --fix

typecheck:
	uv run ty check

api:
	uv run rag-eval api

ui:
	uv run rag-eval ui

server:
	uv run rag-eval legal-server

migrate:
	uv run rag-eval legal-migrate

thesis:
	latexmk -xelatex -interaction=nonstopmode -halt-on-error -cd thesis/latex/main.tex

thesis-clean:
	latexmk -C -cd thesis/latex/main.tex
	rm -f thesis/latex/chapters/*.aux
