.PHONY: check test lint typecheck benchmark download help

help:
	@echo "Available commands:"
	@echo "  make check      - Run linter auto-fix, static type checks, and tests"
	@echo "  make test       - Run pytest test suite"
	@echo "  make lint       - Run ruff check with auto-fix"
	@echo "  make typecheck  - Run basedpyright type checker"
	@echo "  make download   - Download all 4 benchmark datasets"
	@echo "  make benchmark  - Run baseline retrieval and evaluation on all datasets"

check:
	./scripts/check.sh

test:
	uv run pytest -v

lint:
	uv run ruff check --fix

typecheck:
	uv run basedpyright

download:
	uv run rag-eval download --dataset all --output-dir ./data

benchmark:
	./scripts/benchmark_all.sh
