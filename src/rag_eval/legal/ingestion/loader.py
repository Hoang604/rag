"""High-throughput PostgreSQL bulk persistence loader for the Ultra-Lean 3-Table schema.

Persists documents, chunks, and graph edges with foreign key integrity and batch executemany.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable
from typing import Any, cast

import asyncpg

from rag_eval.legal.schemas import (
    CanonicalFullyQualifiedChunk,
    DocumentRecord,
    GraphEdgeRecord,
)

logger = logging.getLogger(__name__)


def compute_chunk_embeddings(
    texts: list[str],
    model_name: str = "intfloat/multilingual-e5-small",
    batch_size: int = 64,
    is_query: bool = False,
) -> list[list[float] | None]:
    """Generates dense vector embeddings for texts using PyTorch/Transformers if available."""
    if not texts:
        return []
    try:
        import torch
        import torch.nn.functional as F
        from transformers import AutoModel, AutoTokenizer

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        raw_tok = AutoTokenizer.from_pretrained(model_name)
        if not callable(raw_tok):
            return [None] * len(texts)
        tokenizer = cast(Callable[..., Any], raw_tok)

        raw_model = AutoModel.from_pretrained(model_name)
        model = cast(Any, raw_model).to(device)
        model.eval()

        prefix = "query: " if is_query else "passage: "
        formatted = [
            f"{prefix}{t}" if not t.startswith(("query: ", "passage: ")) else t
            for t in texts
        ]

        results: list[list[float] | None] = []
        for i in range(0, len(formatted), batch_size):
            batch = formatted[i : i + batch_size]
            encoded = tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            )
            encoded_tensors = {k: v.to(device) for k, v in encoded.items()}
            with torch.no_grad():
                out = model(**encoded_tensors)
                mask = encoded_tensors["attention_mask"].unsqueeze(-1).expand(out[0].size()).float()
                sum_emb = torch.sum(out[0] * mask, dim=1)
                sum_mask = torch.clamp(mask.sum(dim=1), min=1e-9)
                pooled = sum_emb / sum_mask
                normalized = F.normalize(pooled, p=2.0, dim=1)
                results.extend(normalized.cpu().tolist())
        return results
    except (ImportError, RuntimeError, OSError, ValueError) as exc:
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
            $1, $2, $3, $4, $5, $6::jsonb
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
                json.dumps(doc.metadata),
            )
            return uuid.UUID(str(doc_id))

    async def load_chunks(
        self, chunks: list[CanonicalFullyQualifiedChunk]
    ) -> list[uuid.UUID]:
        """Upserts chunks into the 'chunks' table using batch executemany."""
        if not chunks:
            return []

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
            $6::vector, $7::jsonb, $8, $9
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
            emb_str = f"[{','.join(str(x) for x in emb)}]" if emb is not None else None
            records.append(
                (
                    chunk.id,
                    chunk.document_id,
                    chunk.path,
                    chunk.verbatim_text,
                    chunk.contextualized_text,
                    emb_str,
                    json.dumps(chunk.metadata),
                    chunk.effective_date,
                    chunk.expiration_date,
                )
            )

        async with self.pool.acquire() as conn, conn.transaction():
            await conn.executemany(query, records)

        return [c.id for c in chunks]

    async def load_graph_edges(self, edges: list[GraphEdgeRecord]) -> int:
        """Upserts graph edges into the 'graph_edges' table."""
        if not edges:
            return 0

        query = """
        INSERT INTO graph_edges (
            id, source_chunk_id, target_chunk_id, target_external_ref,
            relation_type, citation_text, metadata
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7::jsonb
        )
        ON CONFLICT (source_chunk_id, target_chunk_id, relation_type) DO UPDATE SET
            target_external_ref = EXCLUDED.target_external_ref,
            citation_text = EXCLUDED.citation_text,
            metadata = EXCLUDED.metadata;
        """

        records = [
            (
                e.id,
                e.source_chunk_id,
                e.target_chunk_id,
                e.target_external_ref,
                e.relation_type,
                e.citation_text,
                json.dumps(e.metadata),
            )
            for e in edges
        ]

        async with self.pool.acquire() as conn, conn.transaction():
            await conn.executemany(query, records)

        return len(records)
