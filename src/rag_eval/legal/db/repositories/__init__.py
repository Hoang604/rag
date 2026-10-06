from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg

from rag_eval.legal.db.repositories.base import BaseRepository
from rag_eval.legal.db.repositories.chunks import ChunkRepository
from rag_eval.legal.db.repositories.context_refs import ChunkContextRefRepository
from rag_eval.legal.db.repositories.documents import DocumentRepository
from rag_eval.legal.db.repositories.graph import GraphRepository


class LegalRepository:
    """Unified aggregate root for all statutory legal repositories."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self.documents = DocumentRepository(pool)
        self.chunks = ChunkRepository(pool)
        self.graph = GraphRepository(pool)
        self.context_refs = ChunkContextRefRepository(pool)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[asyncpg.Connection]:
        """Provides an atomic transaction scope on a pooled connection."""
        async with self.pool.acquire() as conn, conn.transaction():
            yield conn


__all__ = [
    "BaseRepository",
    "ChunkContextRefRepository",
    "ChunkRepository",
    "DocumentRepository",
    "GraphRepository",
    "LegalRepository",
]
