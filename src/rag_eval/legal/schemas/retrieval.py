from __future__ import annotations

import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field

from rag_eval.legal.schemas.domain import StatutoryRelationType
from rag_eval.legal.text import format_path_address

_LOW_SIMILARITY: float = 0.86
_LOW_RERANK: float = -1.0
RERANK_POOL: int = 10


class AmendmentNote(BaseModel):
    model_config = ConfigDict(extra="ignore")

    doc_code: str
    label: str
    title: str
    effective_date: datetime.date
    path: str


class SearchHit(BaseModel):
    """Authoritative canonical model for search, grep, and traversal hits."""

    model_config = ConfigDict(extra="ignore")

    doc_code: str
    doc_title: str
    path: str
    start_line: int
    end_line: int
    verbatim_text: str
    contextualized_text: str
    metadata: dict[str, object] = Field(default_factory=dict)
    effective_date: datetime.date
    expiration_date: datetime.date | None = None
    score: float = Field(default=0.0, exclude=True)
    dense_rank: int | None = Field(default=None, exclude=True)
    sparse_rank: int | None = Field(default=None, exclude=True)
    dense_similarity: float = Field(default=0.0, exclude=True)
    keyword_matched: bool = Field(default=True, exclude=True)
    rerank_score: float | None = Field(default=None, exclude=True)
    rank: int = 1
    amended_by: list[AmendmentNote] = Field(default_factory=list)

    @computed_field
    @property
    def address(self) -> str:
        return format_path_address(self.path)


class SearchResult(BaseModel):
    """Unified canonical search response."""

    model_config = ConfigDict(extra="ignore")

    query: str = ""
    hits: list[SearchHit]
    violation_date: str = ""
    dense_is_informative: bool = Field(default=True, exclude=True)
    elapsed_ms: float = 0.0

    @computed_field
    @property
    def confidence(self) -> str:
        if not self.hits:
            return "none"
        if not any(hit.keyword_matched for hit in self.hits):
            return "none"
        scores = [h.rerank_score for h in self.hits if h.rerank_score is not None]
        if scores and max(scores) < _LOW_RERANK:
            return "low"
        if not self.dense_is_informative:
            return "high"
        if max(hit.dense_similarity for hit in self.hits) < _LOW_SIMILARITY:
            return "low"
        return "high"



class SearchDocument(BaseModel):
    """A document that at least one search match belongs to."""

    title: str
    effective_date: datetime.date
    expiration_date: datetime.date | None  # None: the document has no announced end of validity


def _split_context(hit: SearchHit) -> str:
    suffix = "\n" + hit.verbatim_text
    if not hit.contextualized_text.endswith(suffix):
        raise ValueError(f"contextualized_text of {hit.path} does not end with its verbatim_text")
    return hit.contextualized_text.removesuffix(suffix)


class ProvisionText(BaseModel):
    """A provision's own wording, without the parent context it shares with its siblings."""

    path: str
    address: str
    text: str
    start_line: int  # first line of `text` in the document's raw text (readable with get_raw)
    end_line: int
    amended_by: list[AmendmentNote] = Field(default_factory=list, exclude_if=lambda notes: not notes)

    @classmethod
    def from_hit(cls, hit: SearchHit) -> ProvisionText:
        return cls(
            path=hit.path,
            address=hit.address,
            text=hit.verbatim_text,
            start_line=hit.start_line,
            end_line=hit.end_line,
            amended_by=hit.amended_by,
        )


class ProvisionMatch(ProvisionText):
    """A provision standing alone: its wording plus the document and parent context it sits in."""

    doc_code: str
    context: str

    @classmethod
    def from_hit(cls, hit: SearchHit) -> ProvisionMatch:
        return cls(
            path=hit.path,
            address=hit.address,
            text=hit.verbatim_text,
            start_line=hit.start_line,
            end_line=hit.end_line,
            amended_by=hit.amended_by,
            doc_code=hit.doc_code,
            context=_split_context(hit),
        )


def documents_of(hits: list[SearchHit]) -> dict[str, SearchDocument]:
    return {
        hit.doc_code: SearchDocument(
            title=hit.doc_title,
            effective_date=hit.effective_date,
            expiration_date=hit.expiration_date,
        )
        for hit in hits
    }


class LegalSearchResult(BaseModel):
    """Semantic and verbatim matches of one search, each provision listed once."""

    query: str
    pattern: str
    violation_date: datetime.date
    documents: dict[str, SearchDocument]
    both: list[ProvisionMatch]
    semantic_only: list[ProvisionMatch]
    verbatim_only: list[ProvisionMatch]
    verbatim_total: int
    verbatim_truncated: bool


class ProvisionGroup(BaseModel):
    """Consecutive provisions that share one parent context."""

    context: str
    provisions: list[ProvisionText]


class HierarchicalNavigateResult(BaseModel):
    """The provisions under one node of a document, in reading order, grouped by parent context."""

    path: str
    doc_code: str
    document: SearchDocument
    groups: list[ProvisionGroup]
    total: int
    truncated: bool

    @classmethod
    def from_hits(cls, path: str, hits: list[SearchHit], total: int) -> HierarchicalNavigateResult:
        groups: list[ProvisionGroup] = []
        for hit in hits:
            context = _split_context(hit)
            if not groups or groups[-1].context != context:
                groups.append(ProvisionGroup(context=context, provisions=[]))
            groups[-1].provisions.append(ProvisionText.from_hit(hit))
        first = hits[0]
        return cls(
            path=path,
            doc_code=first.doc_code,
            document=documents_of(hits)[first.doc_code],
            groups=groups,
            total=total,
            truncated=total > len(hits),
        )


class GraphStep(BaseModel):
    """One walked edge and the provision it reaches."""

    from_path: str
    relation_type: StatutoryRelationType
    citation_text: str
    depth: int
    to: ProvisionMatch


class GraphTraverseResult(BaseModel):
    """Provisions reached from one provision by following relation edges."""

    source_path: str
    documents: dict[str, SearchDocument]
    steps: list[GraphStep]


RAW_MAX_LINES: int = 100


class RawLine(BaseModel):
    number: int  # 1-based line number in the document's raw text
    text: str


class RawTextResult(BaseModel):
    """Consecutive lines of a document's raw text, the text every chunk was cut from."""

    doc_code: str
    document: SearchDocument
    start_line: int
    end_line: int  # last line returned; below the requested end when the document ends first
    total_lines: int
    lines: list[RawLine]
