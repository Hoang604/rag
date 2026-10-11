"""The whole database in one file: export it here, import it anywhere, no embedding run needed.

The file is gzip-compressed JSON lines. The first line is a header (format, applied migrations, the
embedding model and dimension, row counts); every other line is one row of one table, in load order:
documents, chunks, graph_edges, graph_edge_log. A chunk carries its vector as the base64 of its
float32 bytes, which round-trips exactly, and every jsonb value as the JSON text stored in the
database. `embedding_cache` is not stored: import rebuilds it from the chunks, one entry per
distinct text, so a later `legal-ingest` reuses every vector. `relation_types` is seeded by the
migrations and is not stored either.
"""

from __future__ import annotations

import base64
import datetime
import gzip
import struct
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, Final, Literal, TextIO

import asyncpg
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from rag_eval.legal.db.migrations import (
    get_migration_sql_files,
    run_migrations,
)
from rag_eval.legal.db.repositories.embeddings import text_sha256
from rag_eval.legal.ingestion.embedder import (
    DEFAULT_EMBEDDING_DIM,
    DEFAULT_EMBEDDING_MODEL,
)
from rag_eval.legal.text import get_vietnam_now

SNAPSHOT_FORMAT: Final = 1
DEFAULT_SNAPSHOT_PATH: Final = Path("data/snapshot/rag_legal.jsonl.gz")
_BATCH: Final = 500
_TABLES: Final = ("documents", "chunks", "graph_edges", "graph_edge_log")


class SnapshotError(RuntimeError):
    """The snapshot cannot be written, or cannot be loaded into this database."""


class _Line(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SnapshotHeader(_Line):
    table: Literal["header"] = "header"
    format: int
    migrations: list[str]
    embedding_model: str
    embedding_dim: int
    counts: dict[str, int]


class DocumentRow(_Line):
    table: Literal["documents"] = "documents"
    id: uuid.UUID
    doc_code: str
    title: str
    effective_date: datetime.date
    expiration_date: datetime.date | None  # None: the document has no announced end of validity
    metadata: str  # the jsonb value as JSON text, exactly as stored
    raw_text: str
    created_at: datetime.datetime
    updated_at: datetime.datetime


class ChunkRow(_Line):
    table: Literal["chunks"] = "chunks"
    id: uuid.UUID
    document_id: uuid.UUID
    path: str
    verbatim_text: str
    contextualized_text: str
    embedding: str  # base64 of the float32 vector; a snapshot without vectors would defeat its purpose
    metadata: str
    effective_date: datetime.date
    expiration_date: datetime.date | None  # None: the chunk has no announced end of validity
    created_at: datetime.datetime
    start_line: int
    end_line: int
    updated_at: datetime.datetime


class EdgeRow(_Line):
    table: Literal["graph_edges"] = "graph_edges"
    id: uuid.UUID
    source_chunk_id: uuid.UUID
    target_chunk_id: uuid.UUID
    relation_type: str
    citation_text: str
    created_at: datetime.datetime


class EdgeLogRow(_Line):
    table: Literal["graph_edge_log"] = "graph_edge_log"
    id: uuid.UUID
    action: str
    source_path: str
    target_path: str
    relation_type: str
    citation_text: str
    actor: str
    reason: str
    created_at: datetime.datetime


Row = DocumentRow | ChunkRow | EdgeRow | EdgeLogRow
_ROW: Final = TypeAdapter(Annotated[Row, Field(discriminator="table")])

_SELECT: Final = {
    "documents": """
        SELECT id, doc_code, title, effective_date, expiration_date, metadata::text AS metadata,
               raw_text, created_at, updated_at
        FROM documents ORDER BY doc_code
    """,
    "chunks": """
        SELECT id, document_id, path::text AS path, verbatim_text, contextualized_text, embedding,
               metadata::text AS metadata, effective_date, expiration_date, created_at,
               start_line, end_line, updated_at
        FROM chunks ORDER BY path
    """,
    "graph_edges": """
        SELECT id, source_chunk_id, target_chunk_id, relation_type, citation_text, created_at
        FROM graph_edges ORDER BY id
    """,
    "graph_edge_log": """
        SELECT id, action, source_path::text AS source_path, target_path::text AS target_path,
               relation_type, citation_text, actor, reason, created_at
        FROM graph_edge_log ORDER BY created_at, id
    """,
}


def _encode_vector(values: Sequence[float]) -> str:
    return base64.b64encode(struct.pack(f"<{len(values)}f", *values)).decode("ascii")


def _vector_text(encoded: str, dim: int) -> str:
    raw = base64.b64decode(encoded)
    if len(raw) != 4 * dim:
        raise SnapshotError(f"A chunk vector has {len(raw) // 4} values, the snapshot declares {dim}.")
    return "[" + ",".join(f"{x:.9g}" for x in struct.unpack(f"<{dim}f", raw)) + "]"


async def export_snapshot(pool: asyncpg.Pool, path: Path) -> SnapshotHeader:
    """Writes every row of the database to `path`, read in one consistent transaction."""
    async with pool.acquire() as conn, conn.transaction(isolation="repeatable_read", readonly=True):
        unembedded = int(await conn.fetchval("SELECT count(*) FROM chunks WHERE embedding IS NULL"))
        if unembedded:
            raise SnapshotError(f"{unembedded} chunks have no embedding; run `legal-embed` first.")
        counts = {table: int(await conn.fetchval(f"SELECT count(*) FROM {table}")) for table in _TABLES}
        header = SnapshotHeader(
            format=SNAPSHOT_FORMAT,
            migrations=sorted(str(r["version"]) for r in await conn.fetch("SELECT version FROM schema_migrations")),
            embedding_model=DEFAULT_EMBEDDING_MODEL,
            embedding_dim=DEFAULT_EMBEDDING_DIM,
            counts=counts,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_name(path.name + ".tmp")
        with gzip.open(partial, "wt", encoding="utf-8", compresslevel=9) as out:
            out.write(header.model_dump_json() + "\n")
            async for record in conn.cursor(_SELECT["documents"]):
                out.write(DocumentRow.model_validate(dict(record)).model_dump_json() + "\n")
            async for record in conn.cursor(_SELECT["chunks"]):
                fields = dict(record)
                fields["embedding"] = _encode_vector(record["embedding"].to_list())
                out.write(ChunkRow.model_validate(fields).model_dump_json() + "\n")
            async for record in conn.cursor(_SELECT["graph_edges"]):
                out.write(EdgeRow.model_validate(dict(record)).model_dump_json() + "\n")
            async for record in conn.cursor(_SELECT["graph_edge_log"]):
                out.write(EdgeLogRow.model_validate(dict(record)).model_dump_json() + "\n")
        partial.replace(path)
    return header


def _check_header(header: SnapshotHeader) -> None:
    if header.format != SNAPSHOT_FORMAT:
        raise SnapshotError(f"Snapshot format {header.format} is not the format {SNAPSHOT_FORMAT} this code reads.")
    if (header.embedding_model, header.embedding_dim) != (DEFAULT_EMBEDDING_MODEL, DEFAULT_EMBEDDING_DIM):
        raise SnapshotError(
            f"The snapshot holds {header.embedding_model} vectors of {header.embedding_dim} values; "
            f"this code embeds with {DEFAULT_EMBEDDING_MODEL} at {DEFAULT_EMBEDDING_DIM}."
        )
    current = sorted(p.name for p in get_migration_sql_files())
    if header.migrations != current:
        raise SnapshotError(
            "The snapshot was taken on a different schema than this checkout's migrations "
            f"(snapshot only: {sorted(set(header.migrations) - set(current))}, "
            f"checkout only: {sorted(set(current) - set(header.migrations))}). "
            "Check out the commit the snapshot was made at, or export it again."
        )


async def _insert(conn: asyncpg.Connection, rows: Sequence[Row], dim: int) -> None:
    first = rows[0]
    if isinstance(first, DocumentRow):
        documents = [r for r in rows if isinstance(r, DocumentRow)]
        await conn.execute(
            """
            INSERT INTO documents (id, doc_code, title, effective_date, expiration_date, metadata, raw_text,
                                   created_at, updated_at)
            SELECT id, doc_code, title, effective_date, expiration_date, metadata::jsonb, raw_text,
                   created_at, updated_at
            FROM unnest($1::uuid[], $2::text[], $3::text[], $4::date[], $5::date[], $6::text[], $7::text[],
                        $8::timestamptz[], $9::timestamptz[])
                 AS t(id, doc_code, title, effective_date, expiration_date, metadata, raw_text,
                      created_at, updated_at)
            """,
            [r.id for r in documents],
            [r.doc_code for r in documents],
            [r.title for r in documents],
            [r.effective_date for r in documents],
            [r.expiration_date for r in documents],
            [r.metadata for r in documents],
            [r.raw_text for r in documents],
            [r.created_at for r in documents],
            [r.updated_at for r in documents],
        )
    elif isinstance(first, ChunkRow):
        chunks = [r for r in rows if isinstance(r, ChunkRow)]
        vectors = [_vector_text(r.embedding, dim) for r in chunks]
        await conn.execute(
            """
            INSERT INTO chunks (id, document_id, path, verbatim_text, contextualized_text, embedding, metadata,
                                effective_date, expiration_date, created_at, start_line, end_line, updated_at)
            SELECT id, document_id, path::ltree, verbatim_text, contextualized_text, embedding::vector,
                   metadata::jsonb, effective_date, expiration_date, created_at, start_line, end_line, updated_at
            FROM unnest($1::uuid[], $2::uuid[], $3::text[], $4::text[], $5::text[], $6::text[], $7::text[],
                        $8::date[], $9::date[], $10::timestamptz[], $11::int[], $12::int[], $13::timestamptz[])
                 AS t(id, document_id, path, verbatim_text, contextualized_text, embedding, metadata,
                      effective_date, expiration_date, created_at, start_line, end_line, updated_at)
            """,
            [r.id for r in chunks],
            [r.document_id for r in chunks],
            [r.path for r in chunks],
            [r.verbatim_text for r in chunks],
            [r.contextualized_text for r in chunks],
            vectors,
            [r.metadata for r in chunks],
            [r.effective_date for r in chunks],
            [r.expiration_date for r in chunks],
            [r.created_at for r in chunks],
            [r.start_line for r in chunks],
            [r.end_line for r in chunks],
            [r.updated_at for r in chunks],
        )
        by_text = {r.contextualized_text: vector for r, vector in zip(chunks, vectors, strict=True)}
        await conn.execute(
            """
            INSERT INTO embedding_cache (model, dim, text_sha256, embedding, created_at)
            SELECT $1, $2, h, e::vector, $5 FROM unnest($3::text[], $4::text[]) AS t(h, e)
            ON CONFLICT DO NOTHING
            """,
            DEFAULT_EMBEDDING_MODEL,
            dim,
            [text_sha256(text) for text in by_text],
            list(by_text.values()),
            get_vietnam_now(),
        )
    elif isinstance(first, EdgeRow):
        edges = [r for r in rows if isinstance(r, EdgeRow)]
        await conn.execute(
            """
            INSERT INTO graph_edges (id, source_chunk_id, target_chunk_id, relation_type, citation_text, created_at)
            SELECT * FROM unnest($1::uuid[], $2::uuid[], $3::uuid[], $4::text[], $5::text[], $6::timestamptz[])
            """,
            [r.id for r in edges],
            [r.source_chunk_id for r in edges],
            [r.target_chunk_id for r in edges],
            [r.relation_type for r in edges],
            [r.citation_text for r in edges],
            [r.created_at for r in edges],
        )
    else:
        log = [r for r in rows if isinstance(r, EdgeLogRow)]
        await conn.execute(
            """
            INSERT INTO graph_edge_log (id, action, source_path, target_path, relation_type, citation_text,
                                        actor, reason, created_at)
            SELECT id, action, source_path::ltree, target_path::ltree, relation_type, citation_text,
                   actor, reason, created_at
            FROM unnest($1::uuid[], $2::text[], $3::text[], $4::text[], $5::text[], $6::text[], $7::text[],
                        $8::text[], $9::timestamptz[])
                 AS t(id, action, source_path, target_path, relation_type, citation_text, actor, reason, created_at)
            """,
            [r.id for r in log],
            [r.action for r in log],
            [r.source_path for r in log],
            [r.target_path for r in log],
            [r.relation_type for r in log],
            [r.citation_text for r in log],
            [r.actor for r in log],
            [r.reason for r in log],
            [r.created_at for r in log],
        )


async def _load_rows(conn: asyncpg.Connection, lines: TextIO, dim: int) -> None:
    batch: list[Row] = []
    for line in lines:
        row = _ROW.validate_json(line)
        if batch and (type(batch[0]) is not type(row) or len(batch) >= _BATCH):
            await _insert(conn, batch, dim)
            batch = []
        batch.append(row)
    if batch:
        await _insert(conn, batch, dim)


async def import_snapshot(pool: asyncpg.Pool, path: Path, replace: bool) -> SnapshotHeader:
    """Loads the snapshot in one transaction, so a failure leaves the database as it was.

    The database is migrated first. It must hold no documents unless `replace` is set, which empties
    documents, chunks, graph_edges, graph_edge_log and embedding_cache before the load.
    """
    with gzip.open(path, "rt", encoding="utf-8") as lines:
        header = SnapshotHeader.model_validate_json(lines.readline())
        _check_header(header)
        await run_migrations(pool)
        async with pool.acquire() as conn, conn.transaction():
            if int(await conn.fetchval("SELECT count(*) FROM documents")):
                if not replace:
                    raise SnapshotError("The database already holds documents; pass --replace to replace everything.")
                await conn.execute("TRUNCATE documents, graph_edge_log, embedding_cache CASCADE")
            await _load_rows(conn, lines, header.embedding_dim)
            loaded = {table: int(await conn.fetchval(f"SELECT count(*) FROM {table}")) for table in _TABLES}
            unembedded = int(await conn.fetchval("SELECT count(*) FROM chunks WHERE embedding IS NULL"))
            if loaded != header.counts or unembedded:
                raise SnapshotError(
                    f"The load does not match the snapshot header: loaded {loaded}, header {header.counts}, "
                    f"{unembedded} chunks without a vector."
                )
    return header
