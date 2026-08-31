#!/usr/bin/env bash
set -euo pipefail

echo "==> Running Ruff linter & auto-fix..."
uv run ruff check --fix

echo "==> Running static type checking (ty)..."
uv run ty check

echo "==> Running test suite with integrated AST integrity check (pytest)..."
uv run pytest -v
