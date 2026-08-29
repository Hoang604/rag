"""Vietnamese Traffic Law Ingestion Subsystem.

Provides Context-Preserving Hierarchical Chunking (CPHC), AST parsing,
deterministic graph cross-reference linkers, and PostgreSQL bulk loading.
"""

from __future__ import annotations

from rag_eval.legal.ingestion.benchmark_gen import SyntheticBenchmarkGenerator
from rag_eval.legal.ingestion.cphc import CPHCEngine, synthesize_cphc_prefix
from rag_eval.legal.ingestion.grammar import VietnameseLegalGrammar, parse_vnd_amount
from rag_eval.legal.ingestion.graph_linker import DeterministicGraphLinker
from rag_eval.legal.ingestion.loader import PostgresBulkLoader
from rag_eval.legal.ingestion.parser import (
    ASTNode,
    LegalASTParser,
    sanitize_ltree_label,
)
from rag_eval.legal.ingestion.pipeline import IngestionResult, LegalIngestionPipeline
from rag_eval.legal.schemas import SyntheticQAPair

__all__ = [
    "ASTNode",
    "CPHCEngine",
    "DeterministicGraphLinker",
    "IngestionResult",
    "LegalASTParser",
    "LegalIngestionPipeline",
    "PostgresBulkLoader",
    "SyntheticBenchmarkGenerator",
    "SyntheticQAPair",
    "VietnameseLegalGrammar",
    "parse_vnd_amount",
    "sanitize_ltree_label",
    "synthesize_cphc_prefix",
]

