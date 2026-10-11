from __future__ import annotations

import datetime
from collections.abc import Sequence
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from rag_eval.legal.schemas.domain import CitationDirection, StatutoryRelationType
from rag_eval.legal.text import format_path_address

_LOW_SIMILARITY: float = 0.86
_LOW_RERANK: float = -1.0
RERANK_POOL: int = 10

SearchFoundIn = Literal["both", "semantic_only", "verbatim_only"]
FOUND_IN_ORDER: Final[tuple[SearchFoundIn, ...]] = ("both", "semantic_only", "verbatim_only")


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


def _context_of(hit: SearchHit) -> str:
    """The parent context a provision sits under, without its own text and without the document
    title (`documents` states the title once). Empty when the provision sits directly under the
    document."""
    suffix = "\n" + hit.verbatim_text
    if not hit.contextualized_text.endswith(suffix):
        raise ValueError(f"contextualized_text of {hit.path} does not end with its verbatim_text")
    head = hit.contextualized_text.removesuffix(suffix)
    title = f"[{hit.doc_title}]"
    if not head.startswith(title):
        raise ValueError(f"contextualized_text of {hit.path} does not start with its document title")
    rest = head.removeprefix(title)
    if rest.startswith(" > "):
        return rest.removeprefix(" > ")
    if rest.startswith("\n"):
        return rest.removeprefix("\n")
    if rest:
        raise ValueError(f"contextualized_text of {hit.path} has text right after its document title")
    return ""


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


class SearchProvision(ProvisionText):
    """A provision a search returned, with how it matched and where it ranks."""

    found_in: SearchFoundIn
    rank: int  # 1-based over the whole result: every `both`, then `semantic_only`, then `verbatim_only`

    @classmethod
    def of(cls, hit: SearchHit, found_in: SearchFoundIn, rank: int) -> SearchProvision:
        return cls.model_validate(
            {**ProvisionText.from_hit(hit).model_dump(), "found_in": found_in, "rank": rank}
        )


class ProvisionGroup[P: ProvisionText](BaseModel):
    """Provisions of one document that share a parent context, which is stated once."""

    doc_code: str
    context: str  # "": the provisions sit directly under the document
    provisions: list[P]


def documents_of(hits: Sequence[SearchHit]) -> dict[str, SearchDocument]:
    return {
        hit.doc_code: SearchDocument(
            title=hit.doc_title,
            effective_date=hit.effective_date,
            expiration_date=hit.expiration_date,
        )
        for hit in hits
    }


def group_in_reading_order(hits: Sequence[SearchHit]) -> list[ProvisionGroup[ProvisionText]]:
    """Groups consecutive hits that share a document and context. Only consecutive ones: a clause's
    own text and its tail share a context with the points between them, so merging by context would
    move the tail ahead of the points."""
    groups: list[ProvisionGroup[ProvisionText]] = []
    for hit in hits:
        context = _context_of(hit)
        if not groups or (groups[-1].doc_code, groups[-1].context) != (hit.doc_code, context):
            groups.append(ProvisionGroup[ProvisionText](doc_code=hit.doc_code, context=context, provisions=[]))
        groups[-1].provisions.append(ProvisionText.from_hit(hit))
    return groups


def group_ranked(matches: Sequence[tuple[SearchFoundIn, SearchHit]]) -> list[ProvisionGroup[SearchProvision]]:
    """Groups search matches, given best first, by document and context. Groups come in the order
    of their best-ranked provision; provisions inside a group come in reading order."""
    groups: dict[tuple[str, str], ProvisionGroup[SearchProvision]] = {}
    for rank, (found_in, hit) in enumerate(matches, start=1):
        context = _context_of(hit)
        group = groups.setdefault(
            (hit.doc_code, context),
            ProvisionGroup[SearchProvision](doc_code=hit.doc_code, context=context, provisions=[]),
        )
        group.provisions.append(SearchProvision.of(hit, found_in, rank))
    for group in groups.values():
        group.provisions.sort(key=lambda p: (p.start_line, p.path))
    return list(groups.values())


class LegalSearchResult(BaseModel):
    """Semantic and verbatim matches of one search, each provision listed once."""

    query: str
    pattern: str
    violation_date: datetime.date
    documents: dict[str, SearchDocument]
    groups: list[ProvisionGroup[SearchProvision]]
    verbatim_total: int
    verbatim_truncated: bool


class HierarchicalNavigateResult(BaseModel):
    """The provisions under one node of a document, in reading order, grouped by parent context."""

    path: str
    documents: dict[str, SearchDocument]
    groups: list[ProvisionGroup[ProvisionText]]
    total: int
    truncated: bool

    @classmethod
    def from_hits(cls, path: str, hits: Sequence[SearchHit], total: int) -> HierarchicalNavigateResult:
        return cls(
            path=path,
            documents=documents_of(hits),
            groups=group_in_reading_order(hits),
            total=total,
            truncated=total > len(hits),
        )


class GraphLink(BaseModel):
    """One citation walked by a graph traversal and the provisions it leads to."""

    from_path: str  # the provision the walk stood on
    direction: CitationDirection  # OUTGOING: `citation_text` is in from_path; INCOMING: it is in each reached provision
    relation_type: StatutoryRelationType
    citation_text: str
    depth: int
    total: int  # provisions this citation leads to; a citation to a container leads to every provision under it
    truncated: bool  # True: `groups` holds only the first provisions in reading order, fewer than `total`
    groups: list[ProvisionGroup[ProvisionText]]


class GraphTraverseResult(BaseModel):
    """Provisions reached from one provision by following relation edges."""

    source_path: str
    documents: dict[str, SearchDocument]
    links: list[GraphLink]


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
