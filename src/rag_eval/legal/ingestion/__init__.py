"""Vietnamese Traffic Law Ingestion Subsystem.

Provides Context-Preserving Hierarchical Chunking (CPHC), AST parsing,
deterministic graph cross-reference linkers, and PostgreSQL bulk loading.
"""

from __future__ import annotations

from rag_eval.legal.ingestion.converter import (
    convert_pdf_to_text,
    sanitize_legal_text,
)
from rag_eval.legal.ingestion.cphc import CPHCEngine, synthesize_cphc_prefix
from rag_eval.legal.ingestion.grammar import VietnameseLegalGrammar, parse_vnd_amount
from rag_eval.legal.ingestion.loader import PostgresBulkLoader
from rag_eval.legal.ingestion.parser import (
    ASTNode,
    LegalASTParser,
    sanitize_ltree_label,
)
from rag_eval.legal.ingestion.pipeline import IngestionResult, LegalIngestionPipeline

__all__ = [
    "ASTNode",
    "CPHCEngine",
    "IngestionResult",
    "LegalASTParser",
    "LegalIngestionPipeline",
    "PostgresBulkLoader",
    "VietnameseLegalGrammar",
    "convert_pdf_to_text",
    "parse_vnd_amount",
    "sanitize_legal_text",
    "sanitize_ltree_label",
    "synthesize_cphc_prefix",
]

