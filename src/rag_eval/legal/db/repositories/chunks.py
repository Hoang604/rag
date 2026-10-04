from __future__ import annotations

import datetime
import json
import uuid

import asyncpg

from rag_eval.legal.db.repositories.base import BaseRepository
from rag_eval.legal.ingestion.embedder import compute_chunk_embeddings
from rag_eval.legal.schemas import (
    E_INVALID_DOCUMENT_HIERARCHY,
    ChunkEntity,
    FinalizationState,
    HierarchicalDirection,
    HierarchyNodeDTO,
    LegalDomainError,
    SearchHitDTO,
    validate_ltree_path,
)


class ChunkRepository(BaseRepository):
    """Repository managing domain persistence, indexing, and search for the 'chunks' table."""

    async def upsert_batch(
        self,
        chunks: list[ChunkEntity],
        compute_embeddings: bool = True,
        conn: asyncpg.Connection | None = None,
    ) -> dict[str, uuid.UUID]:
        """Batch upserts chunks with differential vector embedding caching, returning path->UUID map."""
        if not chunks:
            return {}

        doc_id = chunks[0].document_id

        try:
            async with self._connection_scope(conn) as c:
                # 1. Differential vector caching: fetch existing embeddings for doc_id
                existing_rows = await c.fetch(
                    "SELECT path::text, contextualized_text, embedding FROM chunks WHERE document_id = $1;",
                    doc_id,
                )
                existing_map: dict[str, tuple[str, list[float] | None]] = {
                    r["path"]: (
                        r["contextualized_text"],
                        json.loads(r["embedding"])
                        if isinstance(r["embedding"], str)
                        else (list(r["embedding"]) if r["embedding"] is not None else None),
                    )
                    for r in existing_rows
                }

                # 2. Determine which chunks need embedding computation
                embeddings_to_assign: dict[str, list[float] | None] = {}
                texts_to_embed: list[str] = []
                paths_to_embed: list[str] = []

                for chunk in chunks:
                    if chunk.embedding is not None:
                        embeddings_to_assign[chunk.path] = chunk.embedding
                    elif chunk.path in existing_map and existing_map[chunk.path][1] is not None:
                        old_text, old_emb = existing_map[chunk.path]
                        if old_text == chunk.contextualized_text:
                            embeddings_to_assign[chunk.path] = old_emb
                        elif compute_embeddings:
                            texts_to_embed.append(chunk.contextualized_text)
                            paths_to_embed.append(chunk.path)
                        else:
                            embeddings_to_assign[chunk.path] = None
                    elif compute_embeddings:
                        texts_to_embed.append(chunk.contextualized_text)
                        paths_to_embed.append(chunk.path)
                    else:
                        embeddings_to_assign[chunk.path] = None

                if texts_to_embed and compute_embeddings:
                    computed = compute_chunk_embeddings(texts_to_embed)
                    for p, emb in zip(paths_to_embed, computed, strict=False):
                        embeddings_to_assign[p] = emb

                # 3. Prepare records for insertion with Zero DB Defaults
                records: list[tuple[object, ...]] = []
                for chunk in chunks:
                    emb = embeddings_to_assign.get(chunk.path, chunk.embedding)
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
                            chunk.finalization_state.value
                            if hasattr(chunk.finalization_state, "value")
                            else str(chunk.finalization_state),
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
                            $11::date[], $12::text[], $13::timestamptz[], $14::timestamptz[]
                        ) AS t(
                            id, document_id, path, verbatim_text, contextualized_text,
                            start_line, end_line, embedding, metadata, effective_date,
                            expiration_date, finalization_state, created_at, updated_at
                        )
                    )
                    INSERT INTO chunks (
                        id, document_id, path, verbatim_text, contextualized_text,
                        start_line, end_line, embedding, metadata, effective_date,
                        expiration_date, finalization_state, created_at, updated_at
                    )
                    SELECT
                        b.id, b.document_id, b.path::ltree, b.verbatim_text, b.contextualized_text,
                        b.start_line, b.end_line, b.embedding::vector, b.metadata, b.effective_date,
                        b.expiration_date, b.finalization_state, b.created_at, b.updated_at
                    FROM batch_data b
                    ON CONFLICT (path) DO UPDATE SET
                        document_id = EXCLUDED.document_id,
                        verbatim_text = EXCLUDED.verbatim_text,
                        contextualized_text = EXCLUDED.contextualized_text,
                        start_line = EXCLUDED.start_line,
                        end_line = EXCLUDED.end_line,
                        embedding = COALESCE(EXCLUDED.embedding, chunks.embedding),
                        metadata = EXCLUDED.metadata,
                        effective_date = EXCLUDED.effective_date,
                        expiration_date = EXCLUDED.expiration_date,
                        finalization_state = EXCLUDED.finalization_state,
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
                    [r[13] for r in records],
                )
                return {r["path"]: uuid.UUID(str(r["id"])) for r in inserted_rows}
        except Exception as exc:
            raise self._translate_error("upsert_chunks_batch", exc) from exc

    async def resolve_paths_batch(
        self, paths: list[str], conn: asyncpg.Connection | None = None
    ) -> dict[str, uuid.UUID]:
        """Resolves multiple ltree paths to chunk UUIDs in a single query."""
        if not paths:
            return {}
        query = "SELECT path::text, id FROM chunks WHERE path = ANY($1::ltree[]);"
        try:
            async with self._connection_scope(conn) as c:
                rows = await c.fetch(query, paths)
                return {r["path"]: uuid.UUID(str(r["id"])) for r in rows}
        except Exception as exc:
            raise self._translate_error("resolve_paths_batch", exc) from exc

    async def resolve_ids_batch(
        self, chunk_ids: list[uuid.UUID], conn: asyncpg.Connection | None = None
    ) -> dict[uuid.UUID, str]:
        """Resolves multiple chunk UUIDs to their ltree paths in a single query."""
        if not chunk_ids:
            return {}
        query = "SELECT id, path::text FROM chunks WHERE id = ANY($1::uuid[]);"
        try:
            async with self._connection_scope(conn) as c:
                rows = await c.fetch(query, chunk_ids)
                return {uuid.UUID(str(r["id"])): r["path"] for r in rows}
        except Exception as exc:
            raise self._translate_error("resolve_ids_batch", exc) from exc

    async def get_by_id(
        self, chunk_id: uuid.UUID, conn: asyncpg.Connection | None = None
    ) -> ChunkEntity | None:
        """Retrieves a chunk by its primary key UUID."""
        query = """
        SELECT id, document_id, path::text, verbatim_text, contextualized_text,
               start_line, end_line, embedding, metadata, effective_date,
               expiration_date, finalization_state, created_at, updated_at
        FROM chunks WHERE id = $1;
        """
        try:
            async with self._connection_scope(conn) as c:
                row = await c.fetchrow(query, chunk_id)
                if not row:
                    return None
                emb = row["embedding"]
                emb_list = list(emb) if emb is not None else None
                return ChunkEntity(
                    id=uuid.UUID(str(row["id"])),
                    document_id=uuid.UUID(str(row["document_id"])),
                    path=row["path"],
                    verbatim_text=row["verbatim_text"],
                    contextualized_text=row["contextualized_text"],
                    start_line=row["start_line"],
                    end_line=row["end_line"],
                    embedding=emb_list,
                    tsv_content=None,
                    metadata=self._parse_metadata(row["metadata"]),
                    effective_date=row["effective_date"],
                    expiration_date=row["expiration_date"],
                    finalization_state=FinalizationState(row["finalization_state"]),
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
        except Exception as exc:
            raise self._translate_error(f"get_chunk_by_id({chunk_id})", exc) from exc

    async def get_by_path(
        self, path: str, conn: asyncpg.Connection | None = None
    ) -> ChunkEntity | None:
        """Retrieves a chunk by its unique ltree path."""
        query = """
        SELECT id, document_id, path::text, verbatim_text, contextualized_text,
               start_line, end_line, embedding, metadata, effective_date,
               expiration_date, finalization_state, created_at, updated_at
        FROM chunks WHERE path = $1::ltree;
        """
        try:
            async with self._connection_scope(conn) as c:
                row = await c.fetchrow(query, path)
                if not row:
                    return None
                emb = row["embedding"]
                emb_list = list(emb) if emb is not None else None
                return ChunkEntity(
                    id=uuid.UUID(str(row["id"])),
                    document_id=uuid.UUID(str(row["document_id"])),
                    path=row["path"],
                    verbatim_text=row["verbatim_text"],
                    contextualized_text=row["contextualized_text"],
                    start_line=row["start_line"],
                    end_line=row["end_line"],
                    embedding=emb_list,
                    tsv_content=None,
                    metadata=self._parse_metadata(row["metadata"]),
                    effective_date=row["effective_date"],
                    expiration_date=row["expiration_date"],
                    finalization_state=FinalizationState(row["finalization_state"]),
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
        except Exception as exc:
            raise self._translate_error(f"get_chunk_by_path({path})", exc) from exc

    async def list_by_document(
        self, document_id: uuid.UUID, conn: asyncpg.Connection | None = None
    ) -> list[ChunkEntity]:
        """Lists all chunks belonging to a document ordered hierarchically by path."""
        query = """
        SELECT id, document_id, path::text, verbatim_text, contextualized_text,
               start_line, end_line, embedding, metadata, effective_date,
               expiration_date, finalization_state, created_at, updated_at
        FROM chunks WHERE document_id = $1
        ORDER BY path ASC;
        """
        try:
            async with self._connection_scope(conn) as c:
                rows = await c.fetch(query, document_id)
                return [
                    ChunkEntity(
                        id=uuid.UUID(str(r["id"])),
                        document_id=uuid.UUID(str(r["document_id"])),
                        path=r["path"],
                        verbatim_text=r["verbatim_text"],
                        contextualized_text=r["contextualized_text"],
                        start_line=r["start_line"],
                        end_line=r["end_line"],
                        embedding=list(r["embedding"]) if r["embedding"] is not None else None,
                        tsv_content=None,
                        metadata=self._parse_metadata(r["metadata"]),
                        effective_date=r["effective_date"],
                        expiration_date=r["expiration_date"],
                        finalization_state=FinalizationState(r["finalization_state"]),
                        created_at=r["created_at"],
                        updated_at=r["updated_at"],
                    )
                    for r in rows
                ]
        except Exception as exc:
            raise self._translate_error(f"list_chunks_by_document({document_id})", exc) from exc

    async def delete_stale_by_paths(
        self,
        document_id: uuid.UUID,
        stale_paths: list[str],
        conn: asyncpg.Connection | None = None,
    ) -> int:
        """Deletes chunks matching stale paths for a document."""
        if not stale_paths:
            return 0
        query = "DELETE FROM chunks WHERE document_id = $1 AND path = ANY($2::ltree[]);"
        try:
            async with self._connection_scope(conn) as c:
                res = await c.execute(query, document_id, stale_paths)
                return int(res.split()[-1])
        except Exception as exc:
            raise self._translate_error("delete_stale_chunks", exc) from exc

    async def hybrid_search(
        self,
        query_text: str,
        query_vector: list[float] | None,
        t_violation: datetime.date,
        match_limit: int,
        rrf_k: int,
        doc_codes: list[str] | None,
        path_prefix: str | None,
        only_resolved: bool,
        ts_config: str,
        conn: asyncpg.Connection | None = None,
    ) -> list[SearchHitDTO]:
        """Executes generalized dense+sparse hybrid search via hybrid_search v2 stored proc."""
        query = """
        SELECT chunk_id, doc_code, doc_title, path, start_line, end_line,
               verbatim_text, contextualized_text, metadata, effective_date,
               expiration_date, finalization_state, rrf_score, dense_rank,
               sparse_rank, dense_similarity
        FROM hybrid_search(
            $1::text, $2::vector, $3::date, $4::int, $5::int,
            $6::text[], $7::ltree, $8::boolean, $9::text
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
                    only_resolved,
                    ts_config,
                )
                hits: list[SearchHitDTO] = []
                for r in rows:
                    meta = self._parse_metadata(r["metadata"])
                    hits.append(
                        SearchHitDTO(
                            chunk_id=uuid.UUID(str(r["chunk_id"])),
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
                            finalization_state=FinalizationState(r["finalization_state"]),
                            score=float(r["rrf_score"]),
                            dense_rank=int(r["dense_rank"]) if r["dense_rank"] is not None else None,
                            sparse_rank=int(r["sparse_rank"]) if r["sparse_rank"] is not None else None,
                            dense_similarity=float(r["dense_similarity"]) if r["dense_similarity"] is not None else 0.0,
                            keyword_matched=r["sparse_rank"] is not None and r["sparse_rank"] < 900,
                            is_table=bool(meta.get("is_table", False)),
                            table_summary=str(meta.get("table_summary")) if meta.get("table_summary") else None,
                        )
                    )
                return hits
        except Exception as exc:
            raise self._translate_error("hybrid_search", exc) from exc

    async def verbatim_grep(
        self,
        query_pattern: str,
        target_documents: list[str] | None,
        path_prefix: str | None,
        only_resolved: bool,
        is_regex: bool,
        case_sensitive: bool,
        t_violation: datetime.date,
        match_limit: int,
        conn: asyncpg.Connection | None = None,
    ) -> tuple[list[SearchHitDTO], int]:
        """Executes exact / trigram grep search via verbatim_grep v2 stored proc returning hits and total count."""
        query = """
        SELECT chunk_id, doc_code, doc_title, path, start_line, end_line,
               verbatim_text, contextualized_text, metadata, effective_date,
               expiration_date, finalization_state, similarity_score, full_count
        FROM verbatim_grep(
            $1::text, $2::text[], $3::ltree, $4::boolean, $5::boolean,
            $6::boolean, $7::date, $8::int
        );
        """
        try:
            async with self._connection_scope(conn) as c:
                rows = await c.fetch(
                    query,
                    query_pattern,
                    target_documents,
                    path_prefix,
                    only_resolved,
                    is_regex,
                    case_sensitive,
                    t_violation,
                    match_limit,
                )
                if not rows:
                    return [], 0
                full_count = int(rows[0]["full_count"])
                hits: list[SearchHitDTO] = []
                for r in rows:
                    meta = self._parse_metadata(r["metadata"])
                    hits.append(
                        SearchHitDTO(
                            chunk_id=uuid.UUID(str(r["chunk_id"])),
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
                            finalization_state=FinalizationState(r["finalization_state"]),
                            score=float(r["similarity_score"]),
                            dense_similarity=0.0,
                            keyword_matched=True,
                            is_table=bool(meta.get("is_table", False)),
                            table_summary=str(meta.get("table_summary")) if meta.get("table_summary") else None,
                        )
                    )
                return hits, full_count
        except Exception as exc:
            raise self._translate_error("verbatim_grep", exc) from exc

    async def verbatim_grep_count(
        self,
        query_pattern: str,
        target_documents: list[str] | None,
        path_prefix: str | None,
        only_resolved: bool,
        is_regex: bool,
        case_sensitive: bool,
        t_violation: datetime.date,
        conn: asyncpg.Connection | None = None,
    ) -> int:
        """Executes count for verbatim grep search."""
        query = """
        SELECT verbatim_grep_count(
            $1::text, $2::text[], $3::ltree, $4::boolean, $5::boolean,
            $6::boolean, $7::date
        );
        """
        try:
            async with self._connection_scope(conn) as c:
                val = await c.fetchval(
                    query,
                    query_pattern,
                    target_documents,
                    path_prefix,
                    only_resolved,
                    is_regex,
                    case_sensitive,
                    t_violation,
                )
                return int(val) if val is not None else 0
        except Exception as exc:
            raise self._translate_error("verbatim_grep_count", exc) from exc

    async def navigate_hierarchy(
        self,
        anchor_path: str,
        direction: HierarchicalDirection,
        conn: asyncpg.Connection | None = None,
    ) -> list[HierarchyNodeDTO]:
        """Navigates hierarchy tree relative to an anchor path using ltree operations (no doc_id required)."""
        valid_path = validate_ltree_path(anchor_path)
        dir_val = direction.value if hasattr(direction, "value") else str(direction)

        try:
            async with self._connection_scope(conn) as c:
                # Find document_id and doc_code from anchor path
                row = await c.fetchrow(
                    """
                    SELECT c.id, c.path, c.document_id, d.doc_code
                    FROM chunks c
                    JOIN documents d ON c.document_id = d.id
                    WHERE c.path = $1::ltree;
                    """,
                    valid_path,
                )
                if not row:
                    raise LegalDomainError(
                        error_code=E_INVALID_DOCUMENT_HIERARCHY,
                        message=f"Không tìm thấy đoạn quy phạm tương ứng với đường dẫn '{valid_path}' trong cơ sở dữ liệu.",
                        data={"path": valid_path},
                    )

                doc_id: uuid.UUID = uuid.UUID(str(row["document_id"]))
                doc_code: str = str(row["doc_code"])
                anchor_level = len(valid_path.split("."))

                if dir_val == "FULL_ARTICLE":
                    segments = valid_path.split(".")
                    article_subpath = None
                    for seg in segments:
                        if seg.startswith("a_"):
                            idx = segments.index(seg)
                            article_subpath = ".".join(segments[: idx + 1])
                            break
                    if not article_subpath:
                        raise LegalDomainError(
                            error_code=E_INVALID_DOCUMENT_HIERARCHY,
                            message=(
                                f"Nút '{valid_path}' không nằm trong Điều luật nào (không tìm thấy nhãn 'a_*'). "
                                "Hướng duyệt 'FULL_ARTICLE' chỉ áp dụng cho Điều, Khoản hoặc Điểm. "
                                "Để xem các phân vị con của Chương/Mục/Phụ lục, vui lòng dùng direction='CHILDREN'."
                            ),
                            data={"path": valid_path, "direction": dir_val},
                        )
                    query = """
                        SELECT c.id, c.path, c.start_line, c.end_line, c.verbatim_text, c.contextualized_text, c.metadata
                        FROM chunks c
                        WHERE c.document_id = $1 AND c.path <@ $2::ltree
                        ORDER BY c.path ASC;
                    """
                    params = [doc_id, article_subpath]
                elif dir_val == "CHILDREN":
                    query = """
                        SELECT c.id, c.path, c.start_line, c.end_line, c.verbatim_text, c.contextualized_text, c.metadata
                        FROM chunks c
                        WHERE c.document_id = $1 
                          AND c.path <@ $2::ltree 
                          AND c.path != $2::ltree
                          AND nlevel(c.path) = nlevel($2::ltree) + 1
                        ORDER BY c.path ASC;
                    """
                    params = [doc_id, valid_path]
                elif dir_val == "PARENT_CHAIN":
                    query = """
                        SELECT c.id, c.path, c.start_line, c.end_line, c.verbatim_text, c.contextualized_text, c.metadata
                        FROM chunks c
                        WHERE c.document_id = $1 
                          AND c.path @> $2::ltree 
                          AND c.path != $2::ltree
                        ORDER BY nlevel(c.path) ASC;
                    """
                    params = [doc_id, valid_path]
                elif dir_val == "SIBLINGS":
                    query = """
                        SELECT c.id, c.path, c.start_line, c.end_line, c.verbatim_text, c.contextualized_text, c.metadata
                        FROM chunks c
                        WHERE c.document_id = $1 
                          AND subpath(c.path, 0, nlevel(c.path) - 1) = subpath($2::ltree, 0, nlevel($2::ltree) - 1)
                          AND nlevel(c.path) = nlevel($2::ltree)
                          AND c.path != $2::ltree
                        ORDER BY c.path ASC;
                    """
                    params = [doc_id, valid_path]
                else:
                    raise LegalDomainError(
                        error_code=E_INVALID_DOCUMENT_HIERARCHY,
                        message=f"Hướng điều hướng không hợp lệ: '{dir_val}'",
                        data={"direction": dir_val},
                    )

                result_rows = await c.fetch(query, *params)
                return [
                    HierarchyNodeDTO(
                        chunk_id=uuid.UUID(str(r["id"])),
                        path=str(r["path"]),
                        doc_code=doc_code,
                        start_line=int(r["start_line"]),
                        end_line=int(r["end_line"]),
                        verbatim_text=str(r["verbatim_text"]),
                        contextualized_text=str(r["contextualized_text"]),
                        metadata=self._parse_metadata(r["metadata"]),
                        relative_depth=len(str(r["path"]).split(".")) - anchor_level,
                    )
                    for r in result_rows
                ]
        except LegalDomainError:
            raise
        except Exception as exc:
            raise self._translate_error(f"navigate_hierarchy({anchor_path})", exc) from exc

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
    ) -> int:
        """Purges chunks and outgoing/incoming edges for a document that are not in active_paths."""
        query_edges = """
        DELETE FROM graph_edges e
        USING chunks c, documents d
        WHERE (e.target_chunk_id = c.id OR e.source_chunk_id = c.id)
          AND c.document_id = d.id
          AND d.doc_code = $1
          AND c.path::text <> ALL($2::text[]);
        """
        query_refs = """
        DELETE FROM chunk_context_refs r
        USING chunks c, documents d
        WHERE r.chunk_id = c.id
          AND c.document_id = d.id
          AND d.doc_code = $1
          AND c.path::text <> ALL($2::text[]);
        """
        query_chunks = """
        DELETE FROM chunks c
        USING documents d
        WHERE c.document_id = d.id
          AND d.doc_code = $1
          AND c.path::text <> ALL($2::text[]);
        """
        try:
            async with self._connection_scope(conn) as c:
                await c.execute(query_edges, doc_code, active_paths)
                await c.execute(query_refs, doc_code, active_paths)
                status = await c.execute(query_chunks, doc_code, active_paths)
                return int(status.rsplit(" ", 1)[-1] or 0)
        except Exception as exc:
            raise self._translate_error(f"purge_stale_chunks({doc_code})", exc) from exc

