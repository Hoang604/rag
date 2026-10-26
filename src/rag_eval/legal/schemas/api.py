from __future__ import annotations

import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from rag_eval.legal.schemas.retrieval import SearchHit


class HealthResponse(BaseModel):
    """System health probe response."""

    model_config = ConfigDict(extra="ignore")

    status: str = Field("OK", description="Service health status")
    database: str = Field("CONNECTED", description="PostgreSQL connection health")
    timestamp: str = Field(..., description="ISO 8601 timestamp")


class DocumentStatsDTO(BaseModel):
    """Document catalog listing statistics."""

    model_config = ConfigDict(extra="ignore")

    doc_code: str
    title: str
    effective_date: datetime.date
    expiration_date: datetime.date | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    chunk_count: int
    in_force: bool


class SearchRequest(BaseModel):
    """Retrieval query issued from the UI."""

    model_config = ConfigDict(extra="ignore")

    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=5, ge=1, le=20)
    violation_date: str | None = None
    rerank: bool | None = None
    doc_codes: list[str] = Field(default_factory=list, max_length=32)
    deep: bool = False


class AnswerRequest(BaseModel):
    """A question to answer from retrieved provisions."""

    model_config = ConfigDict(extra="ignore")

    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=5, ge=1, le=10)
    violation_date: str | None = None
    rerank: bool | None = None
    doc_codes: list[str] = Field(default_factory=list, max_length=32)
    provider: str = Field(default="claude", max_length=32)
    mode: Literal["agent", "retrieve"] = "retrieve"  # agent: claude searches with the MCP tools itself


class ProviderResponse(BaseModel):
    """Agent CLI provider status."""

    model_config = ConfigDict(extra="ignore")

    name: str
    label: str
    installed: bool
    agent: bool  # can answer in agent mode


class GroundingResponse(BaseModel):
    """Answer grounding evaluation report."""

    model_config = ConfigDict(extra="ignore")

    ok: bool
    unsupported_articles: list[str] = Field(default_factory=list)
    unsupported_amounts: list[str] = Field(default_factory=list)


class AnswerResponse(BaseModel):
    """Composed answer with grounded retrieval context."""

    model_config = ConfigDict(extra="ignore")

    query: str
    provider: str
    answer: str
    abstained: bool
    grounding: GroundingResponse
    confidence: str
    retrieval_ms: float
    answer_ms: float
    hits: list[SearchHit]
    search_query: str | None = None
