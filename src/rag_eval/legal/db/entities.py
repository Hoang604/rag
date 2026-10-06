from __future__ import annotations

import datetime
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict

from rag_eval.legal.schemas.domain import FinalizationState, StatutoryRelationType


class DocumentEntity(BaseModel):
    """Canonical physical entity matching PostgreSQL 'documents' table."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: uuid.UUID
    doc_code: str
    title: str
    effective_date: datetime.date
    expiration_date: datetime.date | None
    metadata: dict[str, object]
    raw_text: str | None
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
    tsv_content: str | None
    metadata: dict[str, object]
    effective_date: datetime.date
    expiration_date: datetime.date | None
    finalization_state: FinalizationState
    created_at: datetime.datetime
    updated_at: datetime.datetime


class RelationTypeEntity(BaseModel):
    """Catalog physical entity matching PostgreSQL 'relation_types' table."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: StatutoryRelationType
    description: str
    is_symmetric: bool


class GraphEdgeEntity(BaseModel):
    """Canonical physical entity matching PostgreSQL 'graph_edges' table."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: uuid.UUID
    source_chunk_id: uuid.UUID
    target_chunk_id: uuid.UUID
    relation_type: StatutoryRelationType
    citation_text: str | None
    created_at: datetime.datetime


class ChunkContextRefEntity(BaseModel):
    """Canonical physical entity matching PostgreSQL 'chunk_context_refs' table."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: uuid.UUID
    chunk_id: uuid.UUID
    char_start: int | None
    char_end: int | None
    citation_phrase: str | None
    target_chunk_id: uuid.UUID | None
    edge_id: uuid.UUID | None
    target_path: str | None
    dependency_type: Literal["OPEN_ENDED", "EXTERNAL_CITATION", "INTERNAL_REFERENCE"]
    created_at: datetime.datetime
