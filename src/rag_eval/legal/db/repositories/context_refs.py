from __future__ import annotations

import uuid

import asyncpg

from rag_eval.legal.db.entities import ChunkContextRefEntity
from rag_eval.legal.db.repositories.base import BaseRepository
from rag_eval.legal.schemas.domain import (
    FinalizationState,
    UnresolvedReference,
)


class ChunkContextRefRepository(BaseRepository):
    """Repository managing domain persistence for chunk_context_refs."""

    async def batch_create_refs(
        self,
        refs: list[ChunkContextRefEntity],
        conn: asyncpg.Connection | None = None,
    ) -> int:
        """Batch inserts chunk context references."""
        if not refs:
            return 0

        query = """
        WITH batch_data AS (
            SELECT * FROM unnest(
                $1::uuid[], $2::uuid[], $3::int[], $4::int[], $5::text[],
                $6::uuid[], $7::uuid[], $8::varchar(500)[],
                $9::varchar(32)[], $10::timestamptz[]
            ) AS t(
                id, chunk_id, char_start, char_end, citation_phrase,
                target_chunk_id, edge_id, target_path,
                dependency_type, created_at
            )
        )
        INSERT INTO chunk_context_refs (
            id, chunk_id, char_start, char_end, citation_phrase,
            target_chunk_id, edge_id, target_path,
            dependency_type, created_at
        )
        SELECT
            b.id, b.chunk_id, b.char_start, b.char_end, b.citation_phrase,
            b.target_chunk_id, b.edge_id, b.target_path,
            b.dependency_type, b.created_at
        FROM batch_data b
        ON CONFLICT (id) DO NOTHING;
        """
        try:
            async with self._connection_scope(conn) as c:
                await c.execute(
                    query,
                    [r.id for r in refs],
                    [r.chunk_id for r in refs],
                    [r.char_start for r in refs],
                    [r.char_end for r in refs],
                    [r.citation_phrase for r in refs],
                    [r.target_chunk_id for r in refs],
                    [r.edge_id for r in refs],
                    [r.target_path for r in refs],
                    [r.dependency_type for r in refs],
                    [r.created_at for r in refs],
                )
                return len(refs)
        except Exception as exc:
            raise self._translate_error("batch_create_refs", exc) from exc

    async def delete_refs_for_chunks(
        self,
        chunk_ids: list[uuid.UUID],
        conn: asyncpg.Connection | None = None,
    ) -> int:
        """Deletes all references originating from the specified chunk IDs."""
        if not chunk_ids:
            return 0
        query = "DELETE FROM chunk_context_refs WHERE chunk_id = ANY($1::uuid[]);"
        try:
            async with self._connection_scope(conn) as c:
                res = await c.execute(query, chunk_ids)
                return int(res.split()[-1])
        except Exception as exc:
            raise self._translate_error("delete_refs_for_chunks", exc) from exc

    async def list_by_chunk_ids(
        self,
        chunk_ids: list[uuid.UUID],
        conn: asyncpg.Connection | None = None,
    ) -> list[ChunkContextRefEntity]:
        """Queries all context references belonging to a set of chunk IDs (hydration support)."""
        if not chunk_ids:
            return []
        query = """
        SELECT id, chunk_id, char_start, char_end, citation_phrase, target_chunk_id,
               edge_id, target_path, dependency_type, created_at
        FROM chunk_context_refs
        WHERE chunk_id = ANY($1::uuid[])
        ORDER BY chunk_id, char_start NULLS LAST;
        """
        try:
            async with self._connection_scope(conn) as c:
                rows = await c.fetch(query, chunk_ids)
                return [
                    ChunkContextRefEntity(
                        id=uuid.UUID(str(r["id"])),
                        chunk_id=uuid.UUID(str(r["chunk_id"])),
                        char_start=r["char_start"],
                        char_end=r["char_end"],
                        citation_phrase=r["citation_phrase"],
                        target_chunk_id=uuid.UUID(str(r["target_chunk_id"])) if r["target_chunk_id"] else None,
                        edge_id=uuid.UUID(str(r["edge_id"])) if r["edge_id"] else None,
                        target_path=r["target_path"],
                        dependency_type=r["dependency_type"],
                        created_at=r["created_at"],
                    )
                    for r in rows
                ]
        except Exception as exc:
            raise self._translate_error("list_by_chunk_ids", exc) from exc

    async def get_unresolved_backlog(
        self,
        doc_code: str | None,
        finalization_state: FinalizationState | None,
        limit: int,
        conn: asyncpg.Connection | None = None,
    ) -> list[UnresolvedReference]:
        """Queries chunks with unresolved external dependencies."""
        fin_state_val = (
            finalization_state.value
            if hasattr(finalization_state, "value")
            else (str(finalization_state) if finalization_state else None)
        )
        query = """
        SELECT
            c.id AS chunk_id,
            c.path::text AS source_path,
            d.doc_code,
            d.title AS doc_title,
            r.target_path,
            c.finalization_state,
            c.verbatim_text,
            r.id AS ref_id,
            r.char_start,
            r.char_end,
            r.citation_phrase,
            r.dependency_type,
            c.metadata
        FROM chunk_context_refs r
        JOIN chunks c ON r.chunk_id = c.id
        JOIN documents d ON c.document_id = d.id
        WHERE ($1::varchar IS NULL OR d.doc_code = $1)
          AND ($2::varchar IS NULL OR c.finalization_state = $2)
          AND r.target_chunk_id IS NULL
        ORDER BY d.doc_code, c.path, r.char_start NULLS LAST
        LIMIT $3::int;
        """
        try:
            async with self._connection_scope(conn) as c:
                rows = await c.fetch(query, doc_code, fin_state_val, limit)
                return [
                    UnresolvedReference(
                        source_path=str(r["source_path"]),
                        dependency_text=str(r["citation_phrase"] or ""),
                        dependency_type=str(r["dependency_type"] or "OPEN_ENDED"),
                        char_start=r["char_start"],
                        char_end=r["char_end"],
                        reason="DOC_NOT_IN_CORPUS",
                    )
                    for r in rows
                ]
        except Exception as exc:
            raise self._translate_error("get_unresolved_backlog", exc) from exc

    async def count_unresolved_backlog(
        self,
        doc_code: str | None,
        finalization_state: FinalizationState | None,
        conn: asyncpg.Connection | None = None,
    ) -> int:
        """Counts total chunks with unresolved external dependencies."""
        fin_state_val = (
            finalization_state.value
            if hasattr(finalization_state, "value")
            else (str(finalization_state) if finalization_state else None)
        )
        query = """
        SELECT count(*)
        FROM chunk_context_refs r
        JOIN chunks c ON r.chunk_id = c.id
        JOIN documents d ON c.document_id = d.id
        WHERE ($1::varchar IS NULL OR d.doc_code = $1)
          AND ($2::varchar IS NULL OR c.finalization_state = $2)
          AND r.target_chunk_id IS NULL;
        """
        try:
            async with self._connection_scope(conn) as c:
                val = await c.fetchval(query, doc_code, fin_state_val)
                return int(val) if val is not None else 0
        except Exception as exc:
            raise self._translate_error("count_unresolved_backlog", exc) from exc
