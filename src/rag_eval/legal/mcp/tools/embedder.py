"""Embedding protocols and model adapters for legal search queries."""

from __future__ import annotations

import asyncio
from typing import Protocol, final

from rag_eval.legal.ingestion.loader import compute_chunk_embeddings


class QueryEmbedder(Protocol):
    """Encodes a search query into a dense vector for hybrid_search."""

    async def embed_query(self, query: str) -> list[float] | None: ...


@final
class SentenceTransformerQueryEmbedder:
    """Default embedder: same model and asymmetric prefix as ingestion.

    Documents are embedded as "passage: <text>" by the ingestion loader. e5
    models are trained on that asymmetry, so a query embedded without the
    "query: " prefix lands in the wrong region of the space and dense recall
    degrades silently. Reusing compute_chunk_embeddings keeps the two paths from
    drifting apart, including L2 normalisation.
    """

    def __init__(self, model_name: str = "intfloat/multilingual-e5-small") -> None:
        self._model_name = model_name

    async def embed_query(self, query: str) -> list[float] | None:
        vectors = await asyncio.to_thread(
            compute_chunk_embeddings,
            [query],
            model_name=self._model_name,
            is_query=True,
        )
        if not vectors:
            return None
        return vectors[0]
