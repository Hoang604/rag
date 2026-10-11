from __future__ import annotations

import datetime
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict

from rag_eval.legal.schemas.domain import StatutoryRelationType


class DocumentEntity(BaseModel):
    """Canonical physical entity matching PostgreSQL 'documents' table."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: uuid.UUID
    doc_code: str
    title: str
    effective_date: datetime.date
    expiration_date: datetime.date | None
    metadata: dict[str, object]
    raw_text: str
    created_at: datetime.datetime
    updated_at: datetime.datetime


class ChunkEntity(BaseModel):
    """Canonical physical entity matching PostgreSQL 'chunks' table (CFQC)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: uuid.UUID
    document_id: uuid.UUID
    path: str
    verbatim_text: str
    contextualized_text: str
    start_line: int
    end_line: int
    embedding: list[float] | None
    metadata: dict[str, object]
    effective_date: datetime.date
    expiration_date: datetime.date | None
    created_at: datetime.datetime
    updated_at: datetime.datetime


class GraphEdgeEntity(BaseModel):
    """Canonical physical entity matching PostgreSQL 'graph_edges' table."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: uuid.UUID
    source_chunk_id: uuid.UUID
    target_chunk_id: uuid.UUID
    relation_type: StatutoryRelationType
    citation_text: str
    created_at: datetime.datetime


class EdgeRow(BaseModel):
    """An existing edge addressed by its endpoint paths."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    edge_id: uuid.UUID
    source_path: str
    target_path: str
    relation_type: StatutoryRelationType
    citation_text: str


class EdgeLogEntity(BaseModel):
    """Canonical physical entity matching PostgreSQL 'graph_edge_log' table (append-only)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: uuid.UUID
    action: Literal["ADDED", "REMOVED", "INVALIDATED"]
    source_path: str
    target_path: str
    relation_type: StatutoryRelationType
    citation_text: str
    actor: Literal["INGEST", "AGENT"]
    reason: str
    created_at: datetime.datetime

    @classmethod
    def record(
        cls,
        action: Literal["ADDED", "REMOVED", "INVALIDATED"],
        actor: Literal["INGEST", "AGENT"],
        source_path: str,
        target_path: str,
        relation_type: StatutoryRelationType,
        citation_text: str,
        reason: str,
        at: datetime.datetime,
    ) -> EdgeLogEntity:
        return cls(
            id=uuid.uuid4(),
            action=action,
            source_path=source_path,
            target_path=target_path,
            relation_type=relation_type,
            citation_text=citation_text,
            actor=actor,
            reason=reason,
            created_at=at,
        )
