"""Ingestion and text processing modules for the Ultra-Lean 3-Table Legal Architecture."""

from rag_eval.legal.ingestion.converter import (
    clean_legal_text,
    load_legal_document,
    load_pdf_file,
    load_text_file,
)
from rag_eval.legal.ingestion.cphc import CPHCEngine, synthesize_cphc_prefix
from rag_eval.legal.ingestion.layout import LayoutBlock, PDFLayoutExtractor
from rag_eval.legal.ingestion.lexer import LegalLexer, LegalToken
from rag_eval.legal.ingestion.loader import PostgresBulkLoader
from rag_eval.legal.ingestion.parser import ASTNode, LegalASTParser
from rag_eval.legal.ingestion.pipeline import LegalIngestionPipeline
from rag_eval.legal.ingestion.staging import (
    StagingChunk,
    StagingDocumentSession,
    StagingEdge,
    StagingManager,
)

__all__ = [
    "ASTNode",
    "CPHCEngine",
    "LayoutBlock",
    "LegalASTParser",
    "LegalIngestionPipeline",
    "LegalLexer",
    "LegalToken",
    "PDFLayoutExtractor",
    "PostgresBulkLoader",
    "StagingChunk",
    "StagingDocumentSession",
    "StagingEdge",
    "StagingManager",
    "clean_legal_text",
    "load_legal_document",
    "load_pdf_file",
    "load_text_file",
    "synthesize_cphc_prefix",
]
