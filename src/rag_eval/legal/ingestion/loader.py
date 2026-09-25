"""High-throughput PostgreSQL bulk persistence loader for the Ultra-Lean 3-Table schema.

Persists documents, chunks, and graph edges with foreign key integrity, pgvector native codecs,
and GPU-accelerated dense vector embeddings via sentence-transformers.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Final

import asyncpg
from sentence_transformers import SentenceTransformer

from rag_eval.legal.ingestion.facets import classify_context, classify_role
from rag_eval.legal.schemas import (
    CanonicalFullyQualifiedChunk,
    DocumentRecord,
    GraphEdgeRecord,
)

logger = logging.getLogger(__name__)

# Global cache for SentenceTransformer embedding model
_embedding_model_cache: dict[str, SentenceTransformer] = {}

DEFAULT_EMBEDDING_MODEL: Final[str] = "Qwen/Qwen3-Embedding-0.6B"
DEFAULT_EMBEDDING_DIM: Final[int] = 512


def get_embedding_model(
    model_name: str = DEFAULT_EMBEDDING_MODEL,
    truncate_dim: int = DEFAULT_EMBEDDING_DIM,
) -> SentenceTransformer | None:
    """Loads and caches the SentenceTransformer embedding model with GPU acceleration."""
    cache_key = f"{model_name}:{truncate_dim}"
    if cache_key in _embedding_model_cache:
        return _embedding_model_cache[cache_key]

    try:
        import torch
        from sentence_transformers import SentenceTransformer

        device = "cuda" if torch.cuda.is_available() else "cpu"
        model_kwargs = (
            {"torch_dtype": torch.float16}
            if device == "cuda"
            else {"torch_dtype": torch.float32}
        )
        model = SentenceTransformer(
            model_name,
            truncate_dim=truncate_dim,
            model_kwargs=model_kwargs,
            device=device,
        )
        if model.tokenizer is not None:
            model.tokenizer.padding_side = "left"
        model.eval()
        if device == "cuda":
            logger.info(
                "Loaded embedding model %s (dim=%d) on GPU (CUDA FP16).",
                model_name,
                truncate_dim,
            )
        else:
            logger.info(
                "Loaded embedding model %s (dim=%d) on CPU.",
                model_name,
                truncate_dim,
            )

        _embedding_model_cache[cache_key] = model
        return model
    except (ImportError, RuntimeError, OSError, ValueError) as exc:
        logger.debug(
            "Failed to load sentence-transformers model %s: %s", model_name, exc
        )
        return None


def compute_chunk_embeddings(
    texts: list[str],
    model_name: str = DEFAULT_EMBEDDING_MODEL,
    batch_size: int = 128,
    is_query: bool = False,
    truncate_dim: int = DEFAULT_EMBEDDING_DIM,
) -> list[list[float] | None]:
    """Generates dense vector embeddings using sentence-transformers with GPU FP16 and inference_mode support."""
    if not texts:
        return []

    model = get_embedding_model(model_name, truncate_dim=truncate_dim)
    if model is None:
        return [None] * len(texts)

    try:
        if "e5" in model_name.lower():
            prefix = "query: " if is_query else "passage: "
            formatted = [
                f"{prefix}{t}" if not t.startswith(("query: ", "passage: ")) else t
                for t in texts
            ]
        else:
            formatted = texts

        try:
            import torch

            with torch.inference_mode():
                embeddings = model.encode(
                    formatted,
                    batch_size=batch_size,
                    normalize_embeddings=True,
                    show_progress_bar=len(texts) > 100,
                    convert_to_numpy=True,
                )
        except (ImportError, AttributeError):
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


def _with_vehicle_facet(metadata: object, contextualized_text: str | None) -> dict[str, object]:
    """Stamps the retrieval facets a chunk's ancestors imply into its metadata."""
    facets: dict[str, object] = {
        "vehicle_classes": classify_context(contextualized_text) or None,
        "provision_role": classify_role(contextualized_text),
    }
    facets = {key: value for key, value in facets.items() if value is not None}
    if not facets:
        return metadata if isinstance(metadata, dict) else {}
    if isinstance(metadata, dict):
        return {**metadata, **facets}
    # The jsonb codec serialises on the way out, so a str here would be stored
    if isinstance(metadata, str):
        try:
            decoded = json.loads(metadata)
        except json.JSONDecodeError:
            return facets
        if isinstance(decoded, dict):
            return {**decoded, **facets}
        return facets
    return dict(facets)


class PostgresBulkLoader:
    """Batch loader for documents, chunks, and graph_edges."""

    def __init__(
        self,
        pool: asyncpg.Pool,
        compute_embeddings: bool = False,
        embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    ) -> None:
        self.pool = pool
        self.compute_embeddings = compute_embeddings
        self.embedding_model = embedding_model

    async def load_document(
        self, doc: DocumentRecord, conn: asyncpg.Connection | None = None
    ) -> uuid.UUID:
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
        if conn is not None:
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

        async with self.pool.acquire() as c:
            doc_id = await c.fetchval(
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
        self,
        chunks: list[CanonicalFullyQualifiedChunk],
        conn: asyncpg.Connection | None = None,
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
            start_line, end_line,
            embedding, metadata, effective_date, expiration_date, finalization_state
        ) VALUES (
            $1, $2, $3::ltree, $4, $5,
            $6, $7,
            $8, $9, $10, $11, $12
        )
        ON CONFLICT (path) DO UPDATE SET
            verbatim_text = EXCLUDED.verbatim_text,
            contextualized_text = EXCLUDED.contextualized_text,
            start_line = EXCLUDED.start_line,
            end_line = EXCLUDED.end_line,
            embedding = COALESCE(EXCLUDED.embedding, chunks.embedding),
            metadata = EXCLUDED.metadata,
            effective_date = EXCLUDED.effective_date,
            expiration_date = EXCLUDED.expiration_date,
            finalization_state = EXCLUDED.finalization_state;
        """

        records: list[tuple[object, ...]] = []
        for idx, chunk in enumerate(chunks):
            emb = embeddings[idx]
            records.append(
                (
                    chunk.id,
                    chunk.document_id,
                    chunk.path,
                    chunk.verbatim_text,
                    chunk.contextualized_text,
                    chunk.start_line,
                    chunk.end_line,
                    emb,
                    _with_vehicle_facet(chunk.metadata, chunk.contextualized_text),
                    chunk.effective_date,
                    chunk.expiration_date,
                    chunk.finalization_state.value,
                )
            )

        all_paths = [c.path for c in chunks]
        dep_query = """
        INSERT INTO chunk_dangling_dependencies (
            chunk_id, dependency_text, dependency_type, suggested_target_doc
        ) VALUES ($1, $2, $3, $4);
        """

        if conn is not None:
            await conn.executemany(query, records)
            rows = await conn.fetch(
                "SELECT id, path::text FROM chunks WHERE path = ANY($1::ltree[]);",
                all_paths,
            )
            path_to_uuid = {str(r["path"]): uuid.UUID(str(r["id"])) for r in rows}
            if path_to_uuid:
                await conn.execute(
                    "DELETE FROM chunk_dangling_dependencies WHERE chunk_id = ANY($1::uuid[]);",
                    list(path_to_uuid.values()),
                )
            dep_records = [
                (
                    path_to_uuid[chunk.path],
                    dep.dependency_text,
                    dep.dependency_type,
                    dep.suggested_target_doc,
                )
                for chunk in chunks
                if chunk.path in path_to_uuid
                for dep in chunk.dangling_dependencies
            ]
            if dep_records:
                await conn.executemany(dep_query, dep_records)
            return path_to_uuid

        async with self.pool.acquire() as c, c.transaction():
            await c.executemany(query, records)
            rows = await c.fetch(
                "SELECT id, path::text FROM chunks WHERE path = ANY($1::ltree[]);",
                all_paths,
            )
            path_to_uuid = {str(r["path"]): uuid.UUID(str(r["id"])) for r in rows}
            if path_to_uuid:
                await c.execute(
                    "DELETE FROM chunk_dangling_dependencies WHERE chunk_id = ANY($1::uuid[]);",
                    list(path_to_uuid.values()),
                )
            dep_records = [
                (
                    path_to_uuid[chunk.path],
                    dep.dependency_text,
                    dep.dependency_type,
                    dep.suggested_target_doc,
                )
                for chunk in chunks
                if chunk.path in path_to_uuid
                for dep in chunk.dangling_dependencies
            ]
            if dep_records:
                await c.executemany(dep_query, dep_records)
            return path_to_uuid

    async def resolve_chunk_paths(self, paths: list[str]) -> dict[str, uuid.UUID]:
        """Resolves existing chunk UUIDs in PostgreSQL by ltree paths in a single batch query."""
        if not paths:
            return {}
        query = "SELECT id, path::text FROM chunks WHERE path = ANY($1::ltree[]);"
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, paths)
            return {str(r["path"]): uuid.UUID(str(r["id"])) for r in rows}

    async def load_graph_edges(
        self, edges: list[GraphEdgeRecord], conn: asyncpg.Connection | None = None
    ) -> int:
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
        seen: dict[tuple[str, str, str], tuple[object, ...]] = {}
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

        if conn is not None:
            await conn.executemany(query, records)
            return len(records)

        async with self.pool.acquire() as c, c.transaction():
            await c.executemany(query, records)
            return len(records)

