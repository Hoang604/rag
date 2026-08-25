#!/usr/bin/env bash
set -euo pipefail

echo "Running unified QA pipeline (ruff --fix, ty, pytest)..."
uv run ruff check --fix && uv run ty check && uv run pytest -v
