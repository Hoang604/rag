from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
)


class StatutoryRelationType(str, Enum):
    """Authoritative statutory relation type catalog in Vietnamese jurisprudence."""

    MODIFIES_AND_REPLACES = "MODIFIES_AND_REPLACES"
    SANCTIONS = "SANCTIONS"
    OVERRIDES = "OVERRIDES"
    EXEMPTS = "EXEMPTS"
    GUIDES = "GUIDES"
    DEFINES_TERM = "DEFINES_TERM"
    REFERENCES = "REFERENCES"
    CONFLICTS_WITH = "CONFLICTS_WITH"
    SEE_ALSO = "SEE_ALSO"


GraphDirection = Literal["OUTGOING", "INCOMING", "BOTH"]
CitationDirection = Literal["OUTGOING", "INCOMING"]


class GraphTraversalStep(BaseModel):
    """One edge walked by a graph traversal, from the node already reached to the next."""

    model_config = ConfigDict(extra="ignore")

    from_path: str
    to_path: str
    relation_type: StatutoryRelationType
    citation_text: str
    direction: CitationDirection  # OUTGOING: citation_text is in from_path; INCOMING: it is in to_path
    depth: int
