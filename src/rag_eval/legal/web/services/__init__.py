"""Web service package re-exporting validation, tree, diff, and promotion services."""

from rag_eval.legal.web.services.diff import DiffCalculator
from rag_eval.legal.web.services.promotion import HumanPromotionEngine
from rag_eval.legal.web.services.tree import (
    TreeHierarchyBuilder,
    natural_legal_path_key,
    roman_to_int,
)
from rag_eval.legal.web.services.validation import PreFlightValidator

__all__ = [
    "DiffCalculator",
    "HumanPromotionEngine",
    "PreFlightValidator",
    "TreeHierarchyBuilder",
    "natural_legal_path_key",
    "roman_to_int",
]
