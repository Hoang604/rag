#!/usr/bin/env bash
set -euo pipefail

echo "Running unified QA pipeline (ruff --fix, basedpyright, pytest)..."
uv run ruff check --fix && uv run basedpyright && uv run pytest -v
