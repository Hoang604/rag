"""Web and API module for Human-in-the-Loop Legal Staging Reviewer."""

from __future__ import annotations

from rag_eval.legal.web.app import create_app
from rag_eval.legal.web.service import (
    DiffCalculator,
    HumanPromotionEngine,
    PreFlightValidator,
    TreeHierarchyBuilder,
)

__all__ = [
    "DiffCalculator",
    "HumanPromotionEngine",
    "PreFlightValidator",
    "TreeHierarchyBuilder",
    "create_app",
]
