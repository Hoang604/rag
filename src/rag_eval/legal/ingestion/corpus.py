"""The corpus on disk: one folder per document under data/sources, its canonical text under data/raw.

A source folder holds the document's original files and a hand-written `meta.json`; the
canonical text is generated from them by `convert` and never edited by hand.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from rag_eval.legal.ingestion.converter import canonical_text
from rag_eval.legal.ingestion.extract import extract

SOURCES_DIR = Path("data/sources")
TEXT_DIR = Path("data/raw")

_METADATA_KEYS: tuple[str, ...] = ("amends",)


@dataclass(frozen=True)
class SourceDocument:
    """One corpus entry: the cleaned text and the metadata its `.meta.json` records."""

    doc_code: str
    title: str
    raw_text: str
    effective_date: datetime.date
    expiration_date: datetime.date | None  # None: the document has no announced end of validity
    metadata: dict[str, object]


class CorpusEntryError(ValueError):
    """A corpus entry that cannot be loaded (missing text, bad dates)."""


class CorpusMeta(BaseModel):
    """A source folder's `meta.json`: what the document is and which of its files make up its text, in order."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    doc_code: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    effective_date: datetime.date
    expiration_date: datetime.date | None = None  # None: no announced end; else the first day it no longer applies
    amends: str | None = None  # None: the document amends nothing
    consolidates: list[str] = Field(default_factory=list)
    in_force: bool
    superseded_by: str | None = None  # None: nothing supersedes the document
    source_urls: list[str] = Field(default_factory=list)
    parts: list[str] = Field(..., min_length=1)

    @model_validator(mode="after")
    def _repealed_document_has_end_date(self) -> CorpusMeta:
        """A document declared not in force must say from which day it stops applying."""
        if not self.in_force and self.expiration_date is None:
            raise ValueError("in_force is false but expiration_date is missing: give the first day it no longer applies")
        return self


def read_meta(source_dir: Path) -> CorpusMeta:
    return CorpusMeta.model_validate_json((source_dir / "meta.json").read_text(encoding="utf-8"))


def _is_document_page(url: str) -> bool:
    return urlsplit(url).path.strip("/") != ""


def document_links(sources_dir: Path = SOURCES_DIR) -> dict[str, str]:
    links: dict[str, str] = {}
    if not sources_dir.is_dir():
        return links
    for source_dir in sorted(p for p in sources_dir.iterdir() if (p / "meta.json").is_file()):
        try:
            meta = read_meta(source_dir)
        except (ValidationError, OSError):
            continue
        page = next((url for url in meta.source_urls if _is_document_page(url)), None)
        if page is not None:
            links[meta.doc_code] = page
    return links


def convert(source_dir: Path) -> str:
    """The canonical text of one source folder: its parts extracted in order, then cleaned."""
    meta = read_meta(source_dir)
    return canonical_text([block for part in meta.parts for block in extract(source_dir / part)])


def load_corpus(sources_dir: Path = SOURCES_DIR, text_dir: Path = TEXT_DIR) -> list[SourceDocument | tuple[str, CorpusEntryError]]:
    """Reads every source folder's meta.json with its canonical text, in folder-name order.

    A broken entry is returned as (label, error), its label being the doc_code when the
    meta file names one and the folder name otherwise.
    """
    entries: list[SourceDocument | tuple[str, CorpusEntryError]] = []
    for source_dir in sorted(d for d in sources_dir.iterdir() if (d / "meta.json").exists()):
        try:
            meta = read_meta(source_dir)
        except ValidationError as exc:
            entries.append((source_dir.name, CorpusEntryError(f"invalid meta.json: {exc.error_count()} error(s), {exc.errors()[0]['msg']}")))
            continue
        text_path = text_dir / f"{source_dir.name}.txt"
        if not text_path.exists():
            entries.append((meta.doc_code, CorpusEntryError(f"missing canonical text {text_path}; run legal-convert")))
            continue
        entries.append(
            SourceDocument(
                doc_code=meta.doc_code,
                title=meta.title,
                raw_text=text_path.read_text(encoding="utf-8"),
                effective_date=meta.effective_date,
                expiration_date=meta.expiration_date,
                metadata={
                    key: value
                    for key, value in meta.model_dump(mode="json", include=set(_METADATA_KEYS)).items()
                    if value is not None
                },
            )
        )
    return entries
