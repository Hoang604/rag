"""End-to-end statutory document ingestion pipeline for the Ultra-Lean 3-Table schema."""

from __future__ import annotations

import datetime
import logging
import uuid
from typing import Any

import asyncpg

from rag_eval.legal.ingestion.converter import clean_legal_text
from rag_eval.legal.ingestion.cphc import CPHCEngine
from rag_eval.legal.ingestion.loader import PostgresBulkLoader
from rag_eval.legal.ingestion.parser import LegalASTParser
from rag_eval.legal.schemas import CanonicalFullyQualifiedChunk, DocumentRecord

logger = logging.getLogger(__name__)


class LegalIngestionPipeline:
    """Orchestrates parsing, CPHC chunking, and batch persistence for legal documents."""

    def __init__(
        self,
        pool: asyncpg.Pool,
        compute_embeddings: bool = False,
        embedding_model: str = "intfloat/multilingual-e5-small",
    ) -> None:
        self.pool = pool
        self.loader = PostgresBulkLoader(
            pool=pool,
            compute_embeddings=compute_embeddings,
            embedding_model=embedding_model,
        )

    async def ingest_document(
        self,
        doc_code: str,
        title: str,
        raw_text: str,
        effective_date: datetime.date,
        expiration_date: datetime.date | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[uuid.UUID, list[CanonicalFullyQualifiedChunk]]:
        """Parses raw text, performs CPHC chunking, and persists into 'documents' and 'chunks'."""
        clean_text = clean_legal_text(raw_text)

        # 1. Persist Document
        doc_record = DocumentRecord(
            doc_code=doc_code,
            title=title,
            effective_date=effective_date,
            expiration_date=expiration_date,
            metadata=metadata or {},
        )
        doc_id = await self.loader.load_document(doc_record)

        # 2. Parse AST Hierarchy
        parser = LegalASTParser(doc_code=doc_code)
        ast_root = parser.parse(clean_text, doc_title=title)

        # 3. Context-Preserving Hierarchical Chunking
        cphc = CPHCEngine(
            document_id=doc_id,
            doc_code=doc_code,
            doc_title=title,
            effective_date=effective_date,
            expiration_date=expiration_date,
        )
        chunks = cphc.chunk_ast(ast_root)

        # 4. Bulk Persist Chunks
        await self.loader.load_chunks(chunks)
        logger.info(
            "Successfully ingested document %s (%s) with %d atomic chunks.",
            doc_code,
            doc_id,
            len(chunks),
        )
        return doc_id, chunks
