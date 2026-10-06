from __future__ import annotations

import uuid

import asyncpg

from rag_eval.legal.db.entities import GraphEdgeEntity, RelationTypeEntity
from rag_eval.legal.db.repositories.base import BaseRepository
from rag_eval.legal.errors import (
    E_INVALID_DOCUMENT_HIERARCHY,
    LegalDomainError,
)
from rag_eval.legal.schemas.domain import (
    GraphTraversalStep,
    StatutoryRelationType,
)
from rag_eval.legal.text import (
    validate_ltree_path,
)


class GraphRepository(BaseRepository):
    """Repository managing domain persistence, relation types catalog, and graph traversal."""

    async def get_relation_catalog(
        self, conn: asyncpg.Connection | None = None
    ) -> list[RelationTypeEntity]:
        """Loads all valid relation types from relation_types catalog table."""
        query = "SELECT code, description, is_symmetric FROM relation_types ORDER BY code ASC;"
        try:
            async with self._connection_scope(conn) as c:
                rows = await c.fetch(query)
                return [
                    RelationTypeEntity(
                        code=StatutoryRelationType(r["code"]),
                        description=str(r["description"]),
                        is_symmetric=bool(r["is_symmetric"]),
                    )
                    for r in rows
                ]
        except Exception as exc:
            raise self._translate_error("get_relation_catalog", exc) from exc

    async def get_valid_relation_codes(
        self, conn: asyncpg.Connection | None = None
    ) -> set[StatutoryRelationType]:
        """Returns the set of active relation codes from DB."""
        catalog = await self.get_relation_catalog(conn=conn)
        return {r.code for r in catalog}

    async def upsert_edges(
        self,
        edges: list[GraphEdgeEntity],
        conn: asyncpg.Connection | None = None,
    ) -> dict[tuple[uuid.UUID, uuid.UUID, StatutoryRelationType], uuid.UUID]:
        """Upserts graph edges, returning a mapping of (source, target, relation) to edge UUID."""
        if not edges:
            return {}

        records: list[tuple[object, ...]] = []
        for e in edges:
            records.append(
                (
                    e.id,
                    e.source_chunk_id,
                    e.target_chunk_id,
                    e.relation_type.value if hasattr(e.relation_type, "value") else str(e.relation_type),
                    e.citation_text,
                    e.created_at,
                )
            )

        query = """
        WITH batch_data AS (
            SELECT * FROM unnest(
                $1::uuid[], $2::uuid[], $3::uuid[], $4::varchar(32)[],
                $5::text[], $6::timestamptz[]
            ) AS t(
                id, source_chunk_id, target_chunk_id, relation_type,
                citation_text, created_at
            )
        )
        INSERT INTO graph_edges (
            id, source_chunk_id, target_chunk_id, relation_type,
            citation_text, created_at
        )
        SELECT
            b.id, b.source_chunk_id, b.target_chunk_id, b.relation_type,
            b.citation_text, b.created_at
        FROM batch_data b
        ON CONFLICT (source_chunk_id, target_chunk_id, relation_type) DO UPDATE SET
            citation_text = EXCLUDED.citation_text
        RETURNING source_chunk_id, target_chunk_id, relation_type, id;
        """
        try:
            async with self._connection_scope(conn) as c:
                rows = await c.fetch(
                    query,
                    [r[0] for r in records],
                    [r[1] for r in records],
                    [r[2] for r in records],
                    [r[3] for r in records],
                    [r[4] for r in records],
                    [r[5] for r in records],
                )
                return {
                    (
                        uuid.UUID(str(r["source_chunk_id"])),
                        uuid.UUID(str(r["target_chunk_id"])),
                        StatutoryRelationType(r["relation_type"]),
                    ): uuid.UUID(str(r["id"]))
                    for r in rows
                }
        except Exception as exc:
            raise self._translate_error("upsert_edges", exc) from exc

    async def delete_edges_for_chunks(
        self, chunk_ids: list[uuid.UUID], conn: asyncpg.Connection | None = None
    ) -> int:
        """Deletes all edges where source or target chunk is in the given chunk_ids list."""
        if not chunk_ids:
            return 0
        query = "DELETE FROM graph_edges WHERE source_chunk_id = ANY($1::uuid[]) OR target_chunk_id = ANY($1::uuid[]);"
        try:
            async with self._connection_scope(conn) as c:
                res = await c.execute(query, chunk_ids)
                return int(res.split()[-1])
        except Exception as exc:
            raise self._translate_error("delete_edges_for_chunks", exc) from exc

    async def delete_outgoing_edges_for_chunks(
        self, chunk_ids: list[uuid.UUID], conn: asyncpg.Connection | None = None
    ) -> int:
        """Deletes only outgoing edges originating from the given chunk IDs."""
        if not chunk_ids:
            return 0
        query = "DELETE FROM graph_edges WHERE source_chunk_id = ANY($1::uuid[]);"
        try:
            async with self._connection_scope(conn) as c:
                res = await c.execute(query, chunk_ids)
                return int(res.split()[-1])
        except Exception as exc:
            raise self._translate_error("delete_outgoing_edges_for_chunks", exc) from exc

    async def list_edges_for_chunks(
        self, chunk_ids: list[uuid.UUID], conn: asyncpg.Connection | None = None
    ) -> list[GraphEdgeEntity]:
        """Lists edges originating from any of the provided chunk IDs."""
        if not chunk_ids:
            return []
        query = """
        SELECT id, source_chunk_id, target_chunk_id, relation_type, citation_text, created_at
        FROM graph_edges
        WHERE source_chunk_id = ANY($1::uuid[])
        ORDER BY source_chunk_id, target_chunk_id;
        """
        try:
            async with self._connection_scope(conn) as c:
                rows = await c.fetch(query, chunk_ids)
                return [
                    GraphEdgeEntity(
                        id=uuid.UUID(str(r["id"])),
                        source_chunk_id=uuid.UUID(str(r["source_chunk_id"])),
                        target_chunk_id=uuid.UUID(str(r["target_chunk_id"])),
                        relation_type=StatutoryRelationType(r["relation_type"]),
                        citation_text=r["citation_text"],
                        created_at=r["created_at"],
                    )
                    for r in rows
                ]
        except Exception as exc:
            raise self._translate_error("list_edges_for_chunks", exc) from exc

    async def list_edges_with_paths_for_chunks(
        self, chunk_ids: list[uuid.UUID], conn: asyncpg.Connection | None = None
    ) -> list[dict[str, object]]:
        """Lists edges joined with chunk paths, returning source_path, target_path, relation_type, citation_text."""
        if not chunk_ids:
            return []
        query = """
        SELECT sc.path::text AS source_path, tc.path::text AS target_path,
               ge.relation_type, ge.citation_text
        FROM graph_edges ge
        JOIN chunks sc ON ge.source_chunk_id = sc.id
        JOIN chunks tc ON ge.target_chunk_id = tc.id
        WHERE ge.source_chunk_id = ANY($1::uuid[])
        ORDER BY sc.path, tc.path;
        """
        try:
            async with self._connection_scope(conn) as c:
                rows = await c.fetch(query, chunk_ids)
                return [
                    {
                        "source_path": str(r["source_path"]),
                        "target_path": str(r["target_path"]),
                        "relation_type": str(r["relation_type"]),
                        "citation_text": r["citation_text"],
                    }
                    for r in rows
                ]
        except Exception as exc:
            raise self._translate_error("list_edges_with_paths_for_chunks", exc) from exc

    async def traverse(
        self,
        source: str | uuid.UUID,
        nav_direction: str,
        depth_limit: int,
        filter_relations: list[str] | None = None,
        conn: asyncpg.Connection | None = None,
    ) -> list[GraphTraversalStep]:
        """Traverses knowledge graph with cycle protection via traverse_knowledge_graph v2.
        Accepts LTREE path string or chunk UUID directly.
        """
        try:
            async with self._connection_scope(conn) as c:
                source_uuid: uuid.UUID
                if isinstance(source, str):
                    clean_path = validate_ltree_path(source)
                    row = await c.fetchrow("SELECT id FROM chunks WHERE path = $1::ltree;", clean_path)
                    if not row:
                        raise LegalDomainError(
                            error_code=E_INVALID_DOCUMENT_HIERARCHY,
                            message=f"Source node '{clean_path}' was not found in knowledge graph chunks.",
                            data={"source_path": clean_path},
                        )
                    source_uuid = uuid.UUID(str(row["id"]))
                else:
                    source_uuid = source

                query = """
                SELECT id, source_chunk_id, target_chunk_id, relation_type, citation_text, depth, target_path, target_text
                FROM traverse_knowledge_graph($1::uuid, $2::text, $3::int, $4::varchar(32)[]);
                """
                rows = await c.fetch(query, source_uuid, nav_direction, depth_limit, filter_relations)
                return [
                    GraphTraversalStep(
                        edge_id=uuid.UUID(str(r["id"])),
                        source_chunk_id=uuid.UUID(str(r["source_chunk_id"])),
                        target_chunk_id=uuid.UUID(str(r["target_chunk_id"])),
                        relation_type=StatutoryRelationType(r["relation_type"]),
                        citation_text=r["citation_text"],
                        depth=int(r["depth"]),
                        target_path=str(r["target_path"]),
                        target_text=r["target_text"],
                    )
                    for r in rows
                ]
        except LegalDomainError:
            raise
        except Exception as exc:
            raise self._translate_error(f"traverse_graph({source})", exc) from exc
