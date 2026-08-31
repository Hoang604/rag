"""Vietnamese Traffic Law Ingestion Subsystem.

Provides Context-Preserving Hierarchical Chunking (CPHC), AST parsing,
PostgreSQL bulk loading, and Two-Phase Staging Area management.
"""

from __future__ import annotations

from rag_eval.legal.ingestion.converter import clean_legal_text, load_text_file
from rag_eval.legal.ingestion.cphc import CPHCEngine, synthesize_cphc_prefix
from rag_eval.legal.ingestion.loader import PostgresBulkLoader
from rag_eval.legal.ingestion.parser import (
    ASTNode,
    LegalASTParser,
)
from rag_eval.legal.ingestion.pipeline import LegalIngestionPipeline
from rag_eval.legal.ingestion.staging import (
    StagingChunk,
    StagingDocumentSession,
    StagingEdge,
    StagingManager,
)
from rag_eval.legal.schemas import sanitize_ltree_label

__all__ = [
    "ASTNode",
    "CPHCEngine",
    "LegalASTParser",
    "LegalIngestionPipeline",
    "PostgresBulkLoader",
    "StagingChunk",
    "StagingDocumentSession",
    "StagingEdge",
    "StagingManager",
    "clean_legal_text",
    "load_text_file",
    "sanitize_ltree_label",
    "synthesize_cphc_prefix",
]
