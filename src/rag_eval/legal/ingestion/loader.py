"""High-throughput PostgreSQL bulk persistence loader for the Ultra-Lean 3-Table schema.

Persists documents, chunks, and graph edges with foreign key integrity, pgvector native codecs,
and GPU-accelerated dense vector embeddings via sentence-transformers.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import asyncpg

from rag_eval.legal.schemas import (
    CanonicalFullyQualifiedChunk,
    DocumentRecord,
    GraphEdgeRecord,
)

logger = logging.getLogger(__name__)

# Global cache for SentenceTransformer embedding model
_embedding_model_cache: dict[str, Any] = {}


def get_embedding_model(model_name: str = "intfloat/multilingual-e5-small") -> Any:
    """Loads and caches the SentenceTransformer embedding model with GPU acceleration."""
    if model_name in _embedding_model_cache:
        return _embedding_model_cache[model_name]

    try:
        import torch
        from sentence_transformers import SentenceTransformer

        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = SentenceTransformer(model_name, device=device)
        if device == "cuda":
            model.half()  # Enable FP16 for maximum GPU inference throughput
            logger.info("Loaded embedding model %s on GPU (CUDA FP16).", model_name)
        else:
            logger.info("Loaded embedding model %s on CPU.", model_name)

        _embedding_model_cache[model_name] = model
        return model
    except (ImportError, RuntimeError, OSError, ValueError) as exc:
        logger.debug("Failed to load sentence-transformers model %s: %s", model_name, exc)
        return None


def compute_chunk_embeddings(
    texts: list[str],
    model_name: str = "intfloat/multilingual-e5-small",
    batch_size: int = 128,
    is_query: bool = False,
) -> list[list[float] | None]:
    """Generates dense vector embeddings using sentence-transformers with GPU FP16 support."""
    if not texts:
        return []

    model = get_embedding_model(model_name)
    if model is None:
        return [None] * len(texts)

    try:
        prefix = "query: " if is_query else "passage: "
        formatted = [
            f"{prefix}{t}" if not t.startswith(("query: ", "passage: ")) else t
            for t in texts
        ]

        embeddings = model.encode(
            formatted,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=len(texts) > 100,
            convert_to_numpy=True,
        )
        return [emb.tolist() for emb in embeddings]
    except (RuntimeError, ValueError, TypeError) as exc:
        logger.debug("Embedding generation fallback to None: %s", exc)
        return [None] * len(texts)


class PostgresBulkLoader:
    """Batch loader for documents, chunks, and graph_edges."""

    def __init__(
        self,
        pool: asyncpg.Pool,
        compute_embeddings: bool = False,
        embedding_model: str = "intfloat/multilingual-e5-small",
    ) -> None:
        self.pool = pool
        self.compute_embeddings = compute_embeddings
        self.embedding_model = embedding_model

    async def load_document(self, doc: DocumentRecord) -> uuid.UUID:
        """Upserts a document record into the 'documents' table."""
        query = """
        INSERT INTO documents (
            id, doc_code, title, effective_date, expiration_date, metadata
        ) VALUES (
            $1, $2, $3, $4, $5, $6
        )
        ON CONFLICT (doc_code) DO UPDATE SET
            title = EXCLUDED.title,
            effective_date = EXCLUDED.effective_date,
            expiration_date = EXCLUDED.expiration_date,
            metadata = EXCLUDED.metadata
        RETURNING id;
        """
        async with self.pool.acquire() as conn:
            doc_id = await conn.fetchval(
                query,
                doc.id,
                doc.doc_code,
                doc.title,
                doc.effective_date,
                doc.expiration_date,
                doc.metadata,
            )
            return uuid.UUID(str(doc_id))

    async def load_chunks(
        self, chunks: list[CanonicalFullyQualifiedChunk]
    ) -> dict[str, uuid.UUID]:
        """Upserts chunks into the 'chunks' table using batch transaction and returns {path: chunk_uuid}."""
        if not chunks:
            return {}

        embeddings: list[list[float] | None] = []
        if self.compute_embeddings:
            texts = [c.contextualized_text for c in chunks]
            embeddings = compute_chunk_embeddings(
                texts, model_name=self.embedding_model
            )
        else:
            embeddings = [c.embedding for c in chunks]

        query = """
        INSERT INTO chunks (
            id, document_id, path, verbatim_text, contextualized_text,
            embedding, metadata, effective_date, expiration_date
        ) VALUES (
            $1, $2, $3::ltree, $4, $5,
            $6, $7, $8, $9
        )
        ON CONFLICT (path) DO UPDATE SET
            verbatim_text = EXCLUDED.verbatim_text,
            contextualized_text = EXCLUDED.contextualized_text,
            embedding = COALESCE(EXCLUDED.embedding, chunks.embedding),
            metadata = EXCLUDED.metadata,
            effective_date = EXCLUDED.effective_date,
            expiration_date = EXCLUDED.expiration_date;
        """

        records: list[tuple[Any, ...]] = []
        for idx, chunk in enumerate(chunks):
            emb = embeddings[idx]
            records.append(
                (
                    chunk.id,
                    chunk.document_id,
                    chunk.path,
                    chunk.verbatim_text,
                    chunk.contextualized_text,
                    emb,
                    chunk.metadata,
                    chunk.effective_date,
                    chunk.expiration_date,
                )
            )

        all_paths = [c.path for c in chunks]
        async with self.pool.acquire() as conn, conn.transaction():
            await conn.executemany(query, records)
            rows = await conn.fetch(
                "SELECT id, path::text FROM chunks WHERE path = ANY($1::ltree[]);",
                all_paths,
            )

        return {str(r["path"]): uuid.UUID(str(r["id"])) for r in rows}

    async def resolve_chunk_paths(
        self, paths: list[str]
    ) -> dict[str, uuid.UUID]:
        """Resolves existing chunk UUIDs in PostgreSQL by ltree paths in a single batch query."""
        if not paths:
            return {}
        query = "SELECT id, path::text FROM chunks WHERE path = ANY($1::ltree[]);"
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, paths)
            return {str(r["path"]): uuid.UUID(str(r["id"])) for r in rows}

    async def load_graph_edges(self, edges: list[GraphEdgeRecord]) -> int:
        """Upserts graph edges into the 'graph_edges' table."""
        if not edges:
            return 0

        query = """
        INSERT INTO graph_edges (
            id, source_chunk_id, target_chunk_id, target_external_ref,
            relation_type, citation_text, metadata
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7
        )
        ON CONFLICT ON CONSTRAINT uq_graph_edges DO UPDATE SET
            target_external_ref = EXCLUDED.target_external_ref,
            citation_text = EXCLUDED.citation_text,
            metadata = EXCLUDED.metadata;
        """

        # uq_graph_edges is NULLS NOT DISTINCT, so two citations differing only
        # in their unresolved text collapse onto one key. Chunk merges make that
        # ordinary rather than exceptional.
        seen: dict[tuple[str, str, str], tuple[Any, ...]] = {}
        for e in edges:
            key = (
                str(e.source_chunk_id),
                str(e.target_chunk_id),
                e.relation_type,
            )
            seen[key] = (
                e.id,
                e.source_chunk_id,
                e.target_chunk_id,
                e.target_external_ref,
                e.relation_type,
                e.citation_text,
                e.metadata,
            )
        records = list(seen.values())

        async with self.pool.acquire() as conn, conn.transaction():
            await conn.executemany(query, records)

        return len(records)
