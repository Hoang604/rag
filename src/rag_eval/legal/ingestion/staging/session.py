from __future__ import annotations

import datetime
import json
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from rag_eval.legal.errors import (
    E_AST_GROUNDING_VALIDATION,
    E_CORPUS_INTEGRITY_VIOLATION,
    LegalDomainError,
)
from rag_eval.legal.schemas.domain import (
    RelationEdge,
    StagingStatus,
    StatutoryChunk,
)
from rag_eval.legal.schemas.retrieval import (
    RawTextResult,
    SearchHit,
)
from rag_eval.legal.schemas.staging import (
    MutationRecord,
)
from rag_eval.legal.text import (
    parse_flexible_date,
)


class StagingDocumentSession(BaseModel):
    """Represents an in-memory staging statutory document session."""

    model_config = ConfigDict(extra="ignore")

    doc_code: str = Field(..., description="Statutory document code")
    title: str = Field(..., description="Document title")
    status: StagingStatus = Field(default=StagingStatus.DRAFT, description="Current staging status")
    effective_date: datetime.date = Field(..., description="Effective date")
    expiration_date: datetime.date | None = Field(None, description="Expiration date")
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC),
        description="Session creation timestamp",
    )
    updated_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC),
        description="Session last update timestamp",
    )
    committed_at: datetime.datetime | None = Field(None, description="Session commit timestamp")
    promoted_at: datetime.datetime | None = Field(None, description="Session promotion timestamp")
    raw_text: str = Field(..., description="Raw statutory source text")
    doc_metadata: dict[str, object] = Field(default_factory=dict, description="Document metadata")
    chunks: list[StatutoryChunk] = Field(default_factory=list, description="List of staged chunks")
    edges: list[RelationEdge] = Field(default_factory=list, description="List of staged graph edges")
    raw_ast_snapshot: list[dict[str, object]] | None = Field(
        default=None, description="Initial AST/CPHC baseline snapshot for deterministic replay"
    )
    mutation_history: list[MutationRecord] = Field(
        default_factory=list, description="Audit trail of mutations"
    )
    inspected_paths: set[str] = Field(
        default_factory=set, description="Set of chunk paths inspected during this session"
    )

    @field_validator("effective_date", "expiration_date", mode="before")
    @classmethod
    def parse_dates(cls, v: object) -> datetime.date | None:
        if v is None:
            return None
        return parse_flexible_date(v)

    def get_chunk(self, path: str) -> StatutoryChunk | None:
        """Looks up a single staged chunk by dot-separated ltree path."""
        clean_path = path.strip()
        for chunk in self.chunks:
            if chunk.path == clean_path:
                self.inspected_paths.add(clean_path)
                return chunk
        return None

    def get_raw_window(self, start_line: int = 1, end_line: int | None = None) -> RawTextResult:
        """Extracts a 1-indexed bounded slice of lines from session raw_text."""
        if not self.raw_text or not self.raw_text.strip():
            raise LegalDomainError(
                error_code=E_CORPUS_INTEGRITY_VIOLATION,
                message=f"Văn bản gốc (raw_text) cho '{self.doc_code}' chưa được lưu hoặc đang rỗng.",
                data={"doc_code": self.doc_code},
            )

        all_lines = self.raw_text.splitlines()
        total_lines = len(all_lines)
        if total_lines == 0:
            raise LegalDomainError(
                error_code=E_CORPUS_INTEGRITY_VIOLATION,
                message=f"Văn bản gốc (raw_text) cho '{self.doc_code}' không chứa dòng nào.",
                data={"doc_code": self.doc_code},
            )

        clamped_start = max(1, min(start_line, total_lines))
        target_end = total_lines if end_line is None else end_line
        clamped_end = max(clamped_start, min(target_end, total_lines))
        selected_lines = all_lines[clamped_start - 1 : clamped_end]
        content = "\n".join(selected_lines)

        for chunk in self.chunks:
            if not (chunk.end_line < clamped_start or chunk.start_line > clamped_end):
                self.inspected_paths.add(chunk.path)

        return RawTextResult(
            doc_code=self.doc_code,
            title=self.title,
            raw_text=content,
            start_line=clamped_start,
            end_line=clamped_end,
            total_lines=total_lines,
            chunks_count=len(self.chunks),
        )

    def grep(
        self,
        pattern: str,
        is_regex: bool = False,
        case_sensitive: bool = False,
        search_in: str = "ALL",
        limit: int = 50,
    ) -> list[SearchHit]:
        """Searches in-memory chunks in the session using substring or regex matching."""
        if not pattern or not pattern.strip():
            return []

        clean_pattern = pattern.strip()
        search_mode = search_in.upper()
        flags = 0 if case_sensitive else re.IGNORECASE
        compiled_regex: re.Pattern[str] | None = None

        if is_regex:
            try:
                compiled_regex = re.compile(clean_pattern, flags)
            except re.error as exc:
                raise LegalDomainError(
                    error_code=E_AST_GROUNDING_VALIDATION,
                    message=f"Biểu thức chính quy không hợp lệ '{pattern}': {exc}",
                    data={"pattern": pattern, "is_regex": is_regex},
                ) from exc

        hits: list[SearchHit] = []

        def _check_match(text: str) -> bool:
            if not text:
                return False
            if compiled_regex is not None:
                return compiled_regex.search(text) is not None
            else:
                target_str = text if case_sensitive else text.lower()
                query_str = clean_pattern if case_sensitive else clean_pattern.lower()
                return query_str in target_str

        for chunk in self.chunks:
            if len(hits) >= limit:
                break

            matched_field: str | None = None

            if search_mode in ("ALL", "PATH") and _check_match(chunk.path):
                matched_field = "PATH"

            if not matched_field and search_mode in ("ALL", "VERBATIM") and _check_match(chunk.verbatim_text):
                matched_field = "VERBATIM"

            if not matched_field and search_mode in ("ALL", "CONTEXT") and _check_match(chunk.contextualized_text):
                matched_field = "CONTEXT"

            meta_dict: dict[str, object] = (
                chunk.metadata.model_dump()
                if isinstance(chunk.metadata, BaseModel)
                else chunk.metadata
                if isinstance(chunk.metadata, dict)
                else {}
            )

            if not matched_field and search_mode in ("ALL", "METADATA"):
                meta_str = json.dumps(meta_dict, ensure_ascii=False)
                if _check_match(meta_str):
                    matched_field = "METADATA"

            if matched_field:
                hits.append(
                    SearchHit(
                        doc_code=self.doc_code,
                        doc_title=self.title,
                        path=chunk.path,
                        start_line=chunk.start_line,
                        end_line=chunk.end_line,
                        verbatim_text=chunk.verbatim_text,
                        contextualized_text=chunk.contextualized_text,
                        effective_date=chunk.effective_date,
                        expiration_date=chunk.expiration_date,
                        finalization_state=chunk.finalization_state,
                        metadata=meta_dict,
                    )
                )

        return hits


