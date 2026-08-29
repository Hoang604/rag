"""Strictly typed domain models and contracts with zero Any types."""

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

type MetadataScalar = str | int | float | bool
type MetadataValue = MetadataScalar | list[str] | list[int]
type DocumentMetadata = dict[str, MetadataValue]


class TextSpan(BaseModel):
    """Exact character offset or section reference in a document."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    start_char: int
    end_char: int
    text: str
    section_name: str | None = None


class Document(BaseModel):
    """Raw or structured document unit for ingestion."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    id: str
    text: str
    title: str | None = None
    metadata: DocumentMetadata = Field(
        default_factory=lambda: dict[str, MetadataValue]()
    )


class Query(BaseModel):
    """Benchmark evaluation query or question."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    id: str
    text: str
    metadata: DocumentMetadata = Field(
        default_factory=lambda: dict[str, MetadataValue]()
    )


class GroundTruth(BaseModel):
    """Relevance and answer ground truth for a benchmark query."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    query_id: str
    relevant_doc_ids: list[str] = Field(default_factory=lambda: list[str]())
    answers: list[str] = Field(default_factory=lambda: list[str]())
    spans: list[TextSpan] = Field(default_factory=lambda: list[TextSpan]())


class PredictionResult(BaseModel):
    """Standardized prediction output produced by any RAG system."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    query_id: str
    retrieved_doc_ids: list[str] = Field(default_factory=lambda: list[str]())
    generated_answer: str | None = None
    latency_ms: float | None = None
    metadata: DocumentMetadata = Field(
        default_factory=lambda: dict[str, MetadataValue]()
    )


class MetricScore(BaseModel):
    """Individual aggregated metric evaluation score."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    metric_name: str
    score: float
    description: str


class EvaluationReport(BaseModel):
    """Complete evaluation report containing IR and generation scores."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    dataset_name: str
    total_queries: int
    evaluated_queries: int
    retrieval_metrics: dict[str, float]
    generation_metrics: dict[str, float]
    per_query_scores: list[dict[str, str | float]]
