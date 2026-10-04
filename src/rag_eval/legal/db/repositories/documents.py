from __future__ import annotations

import json
import uuid

import asyncpg

from rag_eval.legal.db.repositories.base import BaseRepository
from rag_eval.legal.schemas import DocumentEntity, DocumentStatsDTO, get_vietnam_now


class DocumentRepository(BaseRepository):
    """Repository managing domain persistence for the 'documents' table."""

    async def upsert(
        self, doc: DocumentEntity, conn: asyncpg.Connection | None = None
    ) -> uuid.UUID:
        """Upserts a document record without relying on database defaults."""
        meta_json = json.dumps(doc.metadata)
        query = """
        INSERT INTO documents (
            id, doc_code, title, effective_date, expiration_date, metadata, raw_text, created_at, updated_at
        ) VALUES (
            $1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9
        )
        ON CONFLICT (doc_code) DO UPDATE SET
            title = EXCLUDED.title,
            effective_date = EXCLUDED.effective_date,
            expiration_date = EXCLUDED.expiration_date,
            metadata = EXCLUDED.metadata,
            raw_text = COALESCE(EXCLUDED.raw_text, documents.raw_text),
            updated_at = EXCLUDED.updated_at
        RETURNING id;
        """
        try:
            async with self._connection_scope(conn) as c:
                row = await c.fetchrow(
                    query,
                    doc.id,
                    doc.doc_code,
                    doc.title,
                    doc.effective_date,
                    doc.expiration_date,
                    meta_json,
                    doc.raw_text,
                    doc.created_at,
                    doc.updated_at,
                )
                if row is None:
                    msg = f"Failed to upsert document '{doc.doc_code}'"
                    raise RuntimeError(msg)
                return uuid.UUID(str(row["id"]))
        except Exception as exc:
            raise self._translate_error(f"upsert_document({doc.doc_code})", exc) from exc

    async def get_by_code(
        self, doc_code: str, conn: asyncpg.Connection | None = None
    ) -> DocumentEntity | None:
        """Retrieves a document entity by its unique statutory code."""
        query = """
        SELECT id, doc_code, title, effective_date, expiration_date, metadata, raw_text, created_at, updated_at
        FROM documents
        WHERE doc_code = $1;
        """
        try:
            async with self._connection_scope(conn) as c:
                row = await c.fetchrow(query, doc_code)
                if not row:
                    return None
                return DocumentEntity(
                    id=uuid.UUID(str(row["id"])),
                    doc_code=str(row["doc_code"]),
                    title=str(row["title"]),
                    effective_date=row["effective_date"],
                    expiration_date=row["expiration_date"],
                    metadata=self._parse_metadata(row["metadata"]),
                    raw_text=row["raw_text"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
        except Exception as exc:
            raise self._translate_error(f"get_document_by_code({doc_code})", exc) from exc

    async def get_by_id(
        self, doc_id: uuid.UUID, conn: asyncpg.Connection | None = None
    ) -> DocumentEntity | None:
        """Retrieves a document entity by its UUID."""
        query = """
        SELECT id, doc_code, title, effective_date, expiration_date, metadata, raw_text, created_at, updated_at
        FROM documents
        WHERE id = $1;
        """
        try:
            async with self._connection_scope(conn) as c:
                row = await c.fetchrow(query, doc_id)
                if not row:
                    return None
                return DocumentEntity(
                    id=uuid.UUID(str(row["id"])),
                    doc_code=str(row["doc_code"]),
                    title=str(row["title"]),
                    effective_date=row["effective_date"],
                    expiration_date=row["expiration_date"],
                    metadata=self._parse_metadata(row["metadata"]),
                    raw_text=row["raw_text"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
        except Exception as exc:
            raise self._translate_error(f"get_document_by_id({doc_id})", exc) from exc

    async def list_active(
        self, conn: asyncpg.Connection | None = None
    ) -> list[DocumentEntity]:
        """Lists all active documents ordered by effective date."""
        query = """
        SELECT id, doc_code, title, effective_date, expiration_date, metadata, raw_text, created_at, updated_at
        FROM documents
        ORDER BY effective_date DESC, doc_code ASC;
        """
        try:
            async with self._connection_scope(conn) as c:
                rows = await c.fetch(query)
                return [
                    DocumentEntity(
                        id=uuid.UUID(str(r["id"])),
                        doc_code=str(r["doc_code"]),
                        title=str(r["title"]),
                        effective_date=r["effective_date"],
                        expiration_date=r["expiration_date"],
                        metadata=self._parse_metadata(r["metadata"]),
                        raw_text=r["raw_text"],
                        created_at=r["created_at"],
                        updated_at=r["updated_at"],
                    )
                    for r in rows
                ]
        except Exception as exc:
            raise self._translate_error("list_active_documents", exc) from exc

    async def list_with_stats(
        self, conn: asyncpg.Connection | None = None
    ) -> list[DocumentStatsDTO]:
        """Lists all documents along with their chunk counts and in_force status using DocumentStatsDTO."""
        query = """
        SELECT d.doc_code, d.title, d.effective_date, d.expiration_date, d.metadata,
               count(c.id) AS chunk_count
        FROM documents d
        LEFT JOIN chunks c ON c.document_id = d.id
        GROUP BY d.id, d.doc_code, d.title, d.effective_date, d.expiration_date, d.metadata
        ORDER BY d.doc_code ASC;
        """
        today = get_vietnam_now().date()
        try:
            async with self._connection_scope(conn) as c:
                rows = await c.fetch(query)
                return [
                    DocumentStatsDTO(
                        doc_code=str(r["doc_code"]),
                        title=str(r["title"]),
                        effective_date=r["effective_date"],
                        expiration_date=r["expiration_date"],
                        metadata=self._parse_metadata(r["metadata"]),
                        chunk_count=int(r["chunk_count"]),
                        in_force=(
                            r["effective_date"] <= today
                            and (r["expiration_date"] is None or r["expiration_date"] > today)
                        ),
                    )
                    for r in rows
                ]
        except Exception as exc:
            raise self._translate_error("list_with_stats", exc) from exc
