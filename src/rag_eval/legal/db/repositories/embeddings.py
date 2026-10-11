from __future__ import annotations

import datetime
import hashlib
from collections.abc import Mapping, Sequence

import asyncpg

from rag_eval.legal.db.repositories.base import BaseRepository


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class EmbeddingRepository(BaseRepository):
    """Persistent store of computed embeddings, keyed by (model, dim, sha256 of the embedded text)."""

    async def lookup(
        self, model: str, dim: int, texts: Sequence[str], conn: asyncpg.Connection | None = None
    ) -> dict[str, list[float]]:
        """Returns the cached vector of every text that has one, keyed by the text."""
        by_hash = {text_sha256(t): t for t in texts}
        try:
            async with self._connection_scope(conn) as c:
                rows = await c.fetch(
                    """
                    SELECT text_sha256, embedding FROM embedding_cache
                    WHERE model = $1 AND dim = $2 AND text_sha256 = ANY($3::text[])
                    """,
                    model,
                    dim,
                    list(by_hash),
                )
        except Exception as exc:
            raise self._translate_error("embedding_cache.lookup", exc) from exc
        return {by_hash[str(r["text_sha256"])]: r["embedding"].to_list() for r in rows}

    async def store(
        self,
        model: str,
        dim: int,
        vectors: Mapping[str, list[float]],
        at: datetime.datetime,
        conn: asyncpg.Connection | None = None,
    ) -> None:
        if not vectors:
            return
        try:
            async with self._connection_scope(conn) as c:
                await c.execute(
                    """
                    INSERT INTO embedding_cache (model, dim, text_sha256, embedding, created_at)
                    SELECT $1, $2, h, e::vector, $5 FROM unnest($3::text[], $4::text[]) AS t(h, e)
                    ON CONFLICT DO NOTHING
                    """,
                    model,
                    dim,
                    [text_sha256(t) for t in vectors],
                    ["[" + ",".join(f"{x:.6f}" for x in v) + "]" for v in vectors.values()],
                    at,
                )
        except Exception as exc:
            raise self._translate_error("embedding_cache.store", exc) from exc
