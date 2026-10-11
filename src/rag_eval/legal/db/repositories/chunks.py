from __future__ import annotations

import datetime
import json
import uuid
from collections.abc import Mapping, Sequence
from typing import Final

import asyncpg

from rag_eval.legal.db.entities import ChunkEntity
from rag_eval.legal.db.repositories.base import BaseRepository
from rag_eval.legal.schemas.retrieval import (
    SearchHit,
)

_NO_SPARSE_MATCH_RANK: Final = 999  # the rank hybrid_search gives a chunk its keyword branch did not match


class ChunkRepository(BaseRepository):
    """Repository managing domain persistence, indexing, and search for the 'chunks' table."""

    async def upsert_batch(
        self,
        chunks: Sequence[ChunkEntity],
        vectors: Mapping[str, list[float]],
        conn: asyncpg.Connection | None = None,
    ) -> dict[str, uuid.UUID]:
        """Batch upserts chunks, each with the vector of its contextualized text when `vectors` has one; returns path->UUID."""
        if not chunks:
            return {}

        try:
            async with self._connection_scope(conn) as c:
                # 3. Prepare records for insertion with Zero DB Defaults
                records: list[tuple[object, ...]] = []
                for chunk in chunks:
                    emb = vectors.get(chunk.contextualized_text)
                    emb_str = f"[{','.join(f'{x:.6f}' for x in emb)}]" if emb is not None else None
                    records.append(
                        (
                            chunk.id,
                            chunk.document_id,
                            chunk.path,
                            chunk.verbatim_text,
                            chunk.contextualized_text,
                            chunk.start_line,
                            chunk.end_line,
                            emb_str,
                            json.dumps(chunk.metadata),
                            chunk.effective_date,
                            chunk.expiration_date,
                            chunk.created_at,
                            chunk.updated_at,
                        )
                    )

                inserted_rows = await c.fetch(
                    """
                    WITH batch_data AS (
                        SELECT * FROM unnest(
                            $1::uuid[], $2::uuid[], $3::text[], $4::text[], $5::text[],
                            $6::int[], $7::int[], $8::text[], $9::jsonb[], $10::date[],
                            $11::date[], $12::timestamptz[], $13::timestamptz[]
                        ) AS t(
                            id, document_id, path, verbatim_text, contextualized_text,
                            start_line, end_line, embedding, metadata, effective_date,
                            expiration_date, created_at, updated_at
                        )
                    )
                    INSERT INTO chunks (
                        id, document_id, path, verbatim_text, contextualized_text,
                        start_line, end_line, embedding, metadata, effective_date,
                        expiration_date, created_at, updated_at
                    )
                    SELECT
                        b.id, b.document_id, b.path::ltree, b.verbatim_text, b.contextualized_text,
                        b.start_line, b.end_line, b.embedding::vector, b.metadata, b.effective_date,
                        b.expiration_date, b.created_at, b.updated_at
                    FROM batch_data b
                    ON CONFLICT (path) DO UPDATE SET
                        document_id = EXCLUDED.document_id,
                        verbatim_text = EXCLUDED.verbatim_text,
                        contextualized_text = EXCLUDED.contextualized_text,
                        start_line = EXCLUDED.start_line,
                        end_line = EXCLUDED.end_line,
                        embedding = COALESCE(
                            EXCLUDED.embedding,
                            CASE WHEN chunks.contextualized_text = EXCLUDED.contextualized_text THEN chunks.embedding END
                        ),
                        metadata = EXCLUDED.metadata,
                        effective_date = EXCLUDED.effective_date,
                        expiration_date = EXCLUDED.expiration_date,
                        updated_at = EXCLUDED.updated_at
                    RETURNING path::text, id;
                    """,
                    [r[0] for r in records],
                    [r[1] for r in records],
                    [r[2] for r in records],
                    [r[3] for r in records],
                    [r[4] for r in records],
                    [r[5] for r in records],
                    [r[6] for r in records],
                    [r[7] for r in records],
                    [r[8] for r in records],
                    [r[9] for r in records],
                    [r[10] for r in records],
                    [r[11] for r in records],
                    [r[12] for r in records],
                )
                return {r["path"]: uuid.UUID(str(r["id"])) for r in inserted_rows}
        except Exception as exc:
            raise self._translate_error("upsert_chunks_batch", exc) from exc

    async def get_verbatim_by_paths(
        self, paths: Sequence[str], conn: asyncpg.Connection | None = None
    ) -> dict[str, tuple[uuid.UUID, str]]:
        """Maps each existing chunk path to its id and verbatim text; absent paths are left out."""
        if not paths:
            return {}
        query = "SELECT path::text, id, verbatim_text FROM chunks WHERE path = ANY($1::ltree[]);"
        try:
            async with self._connection_scope(conn) as c:
                rows = await c.fetch(query, list(paths))
                return {r["path"]: (uuid.UUID(str(r["id"])), str(r["verbatim_text"])) for r in rows}
        except Exception as exc:
            raise self._translate_error("get_verbatim_by_paths", exc) from exc

    async def expand_to_leaf_paths(
        self, paths: Sequence[str], conn: asyncpg.Connection | None = None
    ) -> dict[str, list[tuple[str, uuid.UUID]]]:
        """For each path: itself if it is a chunk, else all chunks under it, ordered by path.

        A path with no chunk at or under it maps to an empty list.
        """
        if not paths:
            return {}
        query = """
        SELECT q.path AS query_path, c.path::text AS path, c.id
        FROM unnest($1::text[]) AS q(path)
        JOIN chunks c ON c.path <@ q.path::ltree
        ORDER BY c.path;
        """
        try:
            async with self._connection_scope(conn) as c:
                rows = await c.fetch(query, list(paths))
        except Exception as exc:
            raise self._translate_error("expand_to_leaf_paths", exc) from exc
        under: dict[str, list[tuple[str, uuid.UUID]]] = {p: [] for p in paths}
        for r in rows:
            under[str(r["query_path"])].append((str(r["path"]), uuid.UUID(str(r["id"]))))
        expanded: dict[str, list[tuple[str, uuid.UUID]]] = {}
        for p, leaves in under.items():
            exact = [(path, cid) for path, cid in leaves if path == p]
            expanded[p] = exact or leaves
        return expanded

    async def hybrid_search(
        self,
        query_text: str,
        query_vector: list[float] | None,
        t_violation: datetime.date,
        match_limit: int,
        rrf_k: int,
        doc_codes: list[str] | None,
        path_prefix: str | None,
        conn: asyncpg.Connection | None = None,
    ) -> list[SearchHit]:
        """Executes generalized dense+sparse hybrid search via hybrid_search v2 stored proc."""
        query = """
        SELECT chunk_id, doc_code, doc_title, path, start_line, end_line,
               verbatim_text, contextualized_text, metadata, effective_date,
               expiration_date, sparse_rank, dense_similarity
        FROM hybrid_search(
            $1::text, $2::vector, $3::date, $4::int, $5::int,
            $6::text[], $7::ltree
        );
        """
        try:
            async with self._connection_scope(conn) as c:
                rows = await c.fetch(
                    query,
                    query_text,
                    query_vector,
                    t_violation,
                    match_limit,
                    rrf_k,
                    doc_codes,
                    path_prefix,
                )
                return [
                    self._hit_from_row(r).model_copy(
                        update={
                            "dense_similarity": float(r["dense_similarity"]),
                            "keyword_matched": int(r["sparse_rank"]) != _NO_SPARSE_MATCH_RANK,
                        }
                    )
                    for r in rows
                ]
        except Exception as exc:
            raise self._translate_error("hybrid_search", exc) from exc

    async def verbatim_grep(
        self,
        query_pattern: str,
        target_documents: list[str] | None,
        path_prefix: str | None,
        is_regex: bool,
        t_violation: datetime.date,
        match_limit: int,
        conn: asyncpg.Connection | None = None,
    ) -> tuple[list[SearchHit], int]:
        query = """
        SELECT chunk_id, doc_code, doc_title, path, start_line, end_line,
               verbatim_text, contextualized_text, metadata, effective_date,
               expiration_date, full_count
        FROM verbatim_grep(
            $1::text, $2::text[], $3::ltree, $4::boolean, $5::date, $6::int
        );
        """
        try:
            async with self._connection_scope(conn) as c:
                rows = await c.fetch(
                    query,
                    query_pattern,
                    target_documents,
                    path_prefix,
                    is_regex,
                    t_violation,
                    match_limit,
                )
                if not rows:
                    return [], 0
                full_count = int(rows[0]["full_count"])
                hits = [self._hit_from_row(r) for r in rows]
                return hits, full_count
        except Exception as exc:
            raise self._translate_error("verbatim_grep", exc) from exc

    async def paths_matching_pattern(
        self,
        paths: list[str],
        pattern: str,
        is_regex: bool,
        conn: asyncpg.Connection | None = None,
    ) -> set[str]:
        query = """
        SELECT path::text AS path FROM chunks
        WHERE path = ANY($1::ltree[])
          AND chunk_matches_pattern(contextualized_text, $2::text, $3::boolean)
        """
        try:
            async with self._connection_scope(conn) as c:
                rows = await c.fetch(query, paths, pattern, is_regex)
                return {str(r["path"]) for r in rows}
        except Exception as exc:
            raise self._translate_error("paths_matching_pattern", exc) from exc

    @classmethod
    def _hit_from_row(cls, r: asyncpg.Record) -> SearchHit:
        meta = cls._parse_metadata(r["metadata"])
        return SearchHit(
            doc_code=str(r["doc_code"]),
            doc_title=str(r["doc_title"]),
            path=str(r["path"]),
            start_line=int(r["start_line"]),
            end_line=int(r["end_line"]),
            verbatim_text=str(r["verbatim_text"]),
            contextualized_text=str(r["contextualized_text"]),
            metadata=meta,
            effective_date=r["effective_date"],
            expiration_date=r["expiration_date"],
        )

    _HIT_COLUMNS = """
        c.id AS chunk_id, d.doc_code, d.title AS doc_title, c.path::text AS path,
        c.start_line, c.end_line, c.verbatim_text, c.contextualized_text, c.metadata,
        c.effective_date, c.expiration_date
    """

    async def get_hits_by_paths(
        self, paths: Sequence[str], conn: asyncpg.Connection | None = None
    ) -> list[SearchHit]:
        """Returns the chunks at these paths in the order given; unknown paths are skipped."""
        query = f"""
        SELECT {self._HIT_COLUMNS}
        FROM chunks c JOIN documents d ON d.id = c.document_id
        WHERE c.path = ANY($1::ltree[])
        """
        try:
            async with self._connection_scope(conn) as c:
                rows = await c.fetch(query, list(paths))
        except Exception as exc:
            raise self._translate_error("get_hits_by_paths", exc) from exc
        by_path = {str(r["path"]): self._hit_from_row(r) for r in rows}
        return [by_path[path] for path in dict.fromkeys(paths) if path in by_path]

    async def provisions_under(
        self, path: str, limit: int, conn: asyncpg.Connection | None = None
    ) -> tuple[list[SearchHit], int]:
        """Returns the first `limit` chunks at or under `path` in reading order, and how many there are."""
        query = f"""
        SELECT {self._HIT_COLUMNS}, COUNT(*) OVER()::BIGINT AS full_count
        FROM chunks c JOIN documents d ON d.id = c.document_id
        WHERE c.path <@ $1::ltree
        ORDER BY c.start_line, c.path
        LIMIT $2
        """
        try:
            async with self._connection_scope(conn) as c:
                rows = await c.fetch(query, path, limit)
        except Exception as exc:
            raise self._translate_error("provisions_under", exc) from exc
        if not rows:
            return [], 0
        return [self._hit_from_row(r) for r in rows], int(rows[0]["full_count"])

    async def reindex_and_vacuum(
        self, conn: asyncpg.Connection | None = None
    ) -> None:
        """Executes maintenance reindex and vacuum commands."""
        try:
            async with self._connection_scope(conn) as c:
                await c.execute("REINDEX TABLE chunks;")
                await c.execute("VACUUM ANALYZE chunks;")
        except Exception as exc:
            raise self._translate_error("reindex_and_vacuum", exc) from exc

    async def get_sibling_windows(
        self, parent_paths: list[str], conn: asyncpg.Connection | None = None
    ) -> list[tuple[str, str]]:
        """Retrieves path and verbatim_text for window expansion."""
        if not parent_paths:
            return []
        query = """
        SELECT c.path::text, c.verbatim_text
        FROM chunks c
        WHERE subpath(c.path, 0, nlevel(c.path) - 1) = ANY($1::ltree[])
        ORDER BY c.path ASC;
        """
        try:
            async with self._connection_scope(conn) as c:
                rows = await c.fetch(query, parent_paths)
                return [(str(r["path"]), str(r["verbatim_text"])) for r in rows]
        except Exception as exc:
            raise self._translate_error("get_sibling_windows", exc) from exc

    async def purge_stale_chunks(
        self, doc_code: str, active_paths: list[str], conn: asyncpg.Connection | None = None
    ) -> list[str]:
        """Deletes the document's chunks that are not in active_paths and returns their paths.

        Edges touching them go with them through the ON DELETE CASCADE foreign keys.
        """
        query = """
        DELETE FROM chunks c
        USING documents d
        WHERE c.document_id = d.id
          AND d.doc_code = $1
          AND c.path::text <> ALL($2::text[])
        RETURNING c.path::text;
        """
        try:
            async with self._connection_scope(conn) as c:
                return [str(r["path"]) for r in await c.fetch(query, doc_code, active_paths)]
        except Exception as exc:
            raise self._translate_error(f"purge_stale_chunks({doc_code})", exc) from exc

    async def documents_missing_embedding(self, conn: asyncpg.Connection | None = None) -> list[tuple[str, int]]:
        """(doc_code, number of chunks without an embedding) for every document that has such chunks."""
        query = """
        SELECT d.doc_code, COUNT(*)::INT AS missing
        FROM chunks c JOIN documents d ON d.id = c.document_id
        WHERE c.embedding IS NULL
        GROUP BY d.doc_code
        ORDER BY d.doc_code;
        """
        try:
            async with self._connection_scope(conn) as c:
                return [(str(r["doc_code"]), int(r["missing"])) for r in await c.fetch(query)]
        except Exception as exc:
            raise self._translate_error("documents_missing_embedding", exc) from exc

    async def texts_missing_embedding(self, doc_code: str, conn: asyncpg.Connection | None = None) -> list[str]:
        """The distinct contextualized texts of the document's chunks that have no embedding."""
        query = """
        SELECT DISTINCT c.contextualized_text
        FROM chunks c JOIN documents d ON d.id = c.document_id
        WHERE d.doc_code = $1 AND c.embedding IS NULL;
        """
        try:
            async with self._connection_scope(conn) as c:
                return [str(r["contextualized_text"]) for r in await c.fetch(query, doc_code)]
        except Exception as exc:
            raise self._translate_error(f"texts_missing_embedding({doc_code})", exc) from exc

    async def fill_embeddings(
        self, doc_code: str, vectors: Mapping[str, list[float]], conn: asyncpg.Connection | None = None
    ) -> int:
        """Sets the embedding of the document's chunks that have none, by contextualized text; returns the rows set."""
        if not vectors:
            return 0
        query = """
        UPDATE chunks c
        SET embedding = v.e::vector
        FROM documents d, unnest($2::text[], $3::text[]) AS v(t, e)
        WHERE c.document_id = d.id AND d.doc_code = $1
          AND c.embedding IS NULL AND c.contextualized_text = v.t;
        """
        try:
            async with self._connection_scope(conn) as c:
                status = await c.execute(
                    query,
                    doc_code,
                    list(vectors),
                    ["[" + ",".join(f"{x:.6f}" for x in v) + "]" for v in vectors.values()],
                )
        except Exception as exc:
            raise self._translate_error(f"fill_embeddings({doc_code})", exc) from exc
        return int(status.split()[-1])
