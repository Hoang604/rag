from __future__ import annotations

import uuid
from collections.abc import Sequence

import asyncpg

from rag_eval.legal.db.entities import (
    EdgeLogEntity,
    EdgeRow,
    GraphEdgeEntity,
)
from rag_eval.legal.db.repositories.base import BaseRepository
from rag_eval.legal.errors import (
    E_CORPUS_INTEGRITY_VIOLATION,
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

_EDGE_ROW_SELECT = """
        SELECT e.id, s.path::text AS source_path, t.path::text AS target_path, e.relation_type, e.citation_text
        FROM graph_edges e
        JOIN chunks s ON s.id = e.source_chunk_id
        JOIN chunks t ON t.id = e.target_chunk_id"""


def _edge_row(r: asyncpg.Record) -> EdgeRow:
    return EdgeRow(
        edge_id=uuid.UUID(str(r["id"])),
        source_path=str(r["source_path"]),
        target_path=str(r["target_path"]),
        relation_type=StatutoryRelationType(r["relation_type"]),
        citation_text=str(r["citation_text"]),
    )


class GraphRepository(BaseRepository):
    """Repository managing domain persistence, relation types catalog, and graph traversal."""

    async def insert_edges(
        self,
        edges: Sequence[GraphEdgeEntity],
        conn: asyncpg.Connection | None = None,
    ) -> list[GraphEdgeEntity]:
        """Inserts edges whose (source, target, relation) triple is new; returns the ones actually inserted.

        An existing triple is left untouched, so nobody's edge is overwritten.
        """
        if not edges:
            return []
        query = """
        INSERT INTO graph_edges (id, source_chunk_id, target_chunk_id, relation_type, citation_text, created_at)
        SELECT * FROM unnest($1::uuid[], $2::uuid[], $3::uuid[], $4::varchar(32)[], $5::text[], $6::timestamptz[])
        ON CONFLICT (source_chunk_id, target_chunk_id, relation_type) DO NOTHING
        RETURNING id;
        """
        try:
            async with self._connection_scope(conn) as c:
                rows = await c.fetch(
                    query,
                    [e.id for e in edges],
                    [e.source_chunk_id for e in edges],
                    [e.target_chunk_id for e in edges],
                    [e.relation_type.value for e in edges],
                    [e.citation_text for e in edges],
                    [e.created_at for e in edges],
                )
                inserted = {uuid.UUID(str(r["id"])) for r in rows}
                return [e for e in edges if e.id in inserted]
        except Exception as exc:
            raise self._translate_error("insert_edges", exc) from exc

    async def list_edges_touching(
        self, document_id: uuid.UUID, conn: asyncpg.Connection | None = None
    ) -> list[EdgeRow]:
        """Lists every edge whose source or target chunk belongs to the document."""
        query = f"""
        {_EDGE_ROW_SELECT}
        WHERE s.document_id = $1 OR t.document_id = $1;
        """
        try:
            async with self._connection_scope(conn) as c:
                return [_edge_row(r) for r in await c.fetch(query, document_id)]
        except Exception as exc:
            raise self._translate_error("list_edges_touching", exc) from exc

    async def find_edges(
        self, keys: Sequence[tuple[str, str, StatutoryRelationType]], conn: asyncpg.Connection | None = None
    ) -> list[EdgeRow]:
        """Returns the existing edges among the given (source path, target path, relation) triples."""
        if not keys:
            return []
        query = f"""
        {_EDGE_ROW_SELECT}
        JOIN unnest($1::text[], $2::text[], $3::varchar(32)[]) AS k(source_path, target_path, relation_type)
          ON s.path = k.source_path::ltree AND t.path = k.target_path::ltree AND e.relation_type = k.relation_type;
        """
        try:
            async with self._connection_scope(conn) as c:
                rows = await c.fetch(
                    query, [k[0] for k in keys], [k[1] for k in keys], [k[2].value for k in keys]
                )
                return [_edge_row(r) for r in rows]
        except Exception as exc:
            raise self._translate_error("find_edges", exc) from exc

    async def delete_edge(self, edge_id: uuid.UUID, conn: asyncpg.Connection | None = None) -> None:
        """Deletes one edge by id."""
        try:
            async with self._connection_scope(conn) as c:
                await c.execute("DELETE FROM graph_edges WHERE id = $1;", edge_id)
        except Exception as exc:
            raise self._translate_error("delete_edge", exc) from exc

    async def log_edge_events(self, events: Sequence[EdgeLogEntity], conn: asyncpg.Connection | None = None) -> None:
        """Appends rows to the edge audit log."""
        if not events:
            return
        query = """
        INSERT INTO graph_edge_log (
            id, action, source_path, target_path, relation_type, citation_text, actor, reason, created_at
        )
        SELECT id, action, source_path::ltree, target_path::ltree, relation_type, citation_text, actor, reason, created_at
        FROM unnest(
            $1::uuid[], $2::varchar(16)[], $3::text[], $4::text[], $5::varchar(32)[],
            $6::text[], $7::text[], $8::text[], $9::timestamptz[]
        ) AS t(id, action, source_path, target_path, relation_type, citation_text, actor, reason, created_at);
        """
        try:
            async with self._connection_scope(conn) as c:
                await c.execute(
                    query,
                    [e.id for e in events],
                    [e.action for e in events],
                    [e.source_path for e in events],
                    [e.target_path for e in events],
                    [e.relation_type.value for e in events],
                    [e.citation_text for e in events],
                    [e.actor for e in events],
                    [e.reason for e in events],
                    [e.created_at for e in events],
                )
        except Exception as exc:
            raise self._translate_error("log_edge_events", exc) from exc

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
                SELECT id, source_chunk_id, target_chunk_id, relation_type, citation_text, depth, target_path
                FROM traverse_knowledge_graph($1::uuid, $2::text, $3::int, $4::varchar(32)[]);
                """
                rows = await c.fetch(query, source_uuid, nav_direction, depth_limit, filter_relations)
                if not rows:
                    return []

                all_src_ids = {uuid.UUID(str(r["source_chunk_id"])) for r in rows}
                id_to_path: dict[uuid.UUID, str] = {}
                if isinstance(source, str):
                    id_to_path[source_uuid] = clean_path

                missing_ids = [uid for uid in all_src_ids if uid not in id_to_path]
                if missing_ids:
                    id_rows = await c.fetch(
                        "SELECT id, path::text FROM chunks WHERE id = ANY($1::uuid[]);",
                        missing_ids,
                    )
                    for ir in id_rows:
                        id_to_path[uuid.UUID(str(ir["id"]))] = str(ir["path"])

                steps: list[GraphTraversalStep] = []
                for r in rows:
                    src_uid = uuid.UUID(str(r["source_chunk_id"]))
                    if src_uid not in id_to_path:
                        raise LegalDomainError(
                            error_code=E_CORPUS_INTEGRITY_VIOLATION,
                            message=f"Tọa độ của chunk nguồn '{src_uid}' không tồn tại trong cơ sở dữ liệu.",
                            data={"source_chunk_id": str(src_uid)},
                        )
                    steps.append(
                        GraphTraversalStep(
                            from_path=id_to_path[src_uid],
                            to_path=str(r["target_path"]),
                            relation_type=StatutoryRelationType(r["relation_type"]),
                            citation_text=str(r["citation_text"]),
                            depth=int(r["depth"]),
                        )
                    )
                return steps
        except LegalDomainError:
            raise
        except Exception as exc:
            raise self._translate_error(f"traverse_graph({source})", exc) from exc
