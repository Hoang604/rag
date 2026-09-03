"""Disk-based Staging Store and Manager for Two-Phase Statutory Ingestion.

Provides isolated staging sessions stored under .cache/stg/<doc_code>.json, allowing
external LLMs to preview, patch candidate chunks, and attach relational graph edges
before committing to the production 3-table database.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import re
import uuid
from collections.abc import Sequence
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from rag_eval.legal.ingestion.cphc import CPHCEngine
from rag_eval.legal.ingestion.parser import LegalASTParser
from rag_eval.legal.schemas import (
    E_AST_GROUNDING_VALIDATION,
    E_CORPUS_INTEGRITY_VIOLATION,
    E_INVALID_DOCUMENT_HIERARCHY,
    LegalDomainError,
    parse_flexible_date,
    sanitize_ltree_label,
    validate_ltree_path,
)

logger = logging.getLogger(__name__)
DEFAULT_STAGING_DIR = Path(".cache/stg")


def deep_merge_dict(base: dict[str, Any], delta: dict[str, Any]) -> dict[str, Any]:
    """Recursively merges delta dictionary into base dictionary without clobbering sibling keys."""
    merged = dict(base)
    for key, value in delta.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = deep_merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


class StagingChunkDelta(BaseModel):
    """Payload representing partial field updates to an existing staged chunk."""

    model_config = ConfigDict(extra="ignore")

    path: str = Field(..., description="Target dot-separated ltree path to patch")
    verbatim_text: str | None = Field(None, description="Optional updated verbatim clause text")
    contextualized_text: str | None = Field(None, description="Optional updated CPHC contextual text")
    lead_sentence: str | None = Field(None, description="Optional updated lead sentence")
    metadata: dict[str, Any] | None = Field(None, description="Optional partial metadata dictionary to deep-merge")
    effective_date: datetime.date | None = Field(None, description="Optional updated effective date")
    expiration_date: datetime.date | None = Field(None, description="Optional updated expiration date")

    @field_validator("effective_date", "expiration_date", mode="before")
    @classmethod
    def parse_dates(cls, v: Any) -> datetime.date | None:
        if v is None:
            return None
        return parse_flexible_date(v)


class StagingDeltaReport(BaseModel):
    """Summary of applied chunk mutations and cascaded hierarchical updates."""

    model_config = ConfigDict(extra="ignore")

    doc_code: str = Field(..., description="Document statutory code")
    updated_count: int = Field(..., description="Count of directly patched chunks")
    cascaded_count: int = Field(..., description="Count of descendant chunks whose breadcrumbs were updated")
    removed_count: int = Field(..., description="Count of removed chunk paths")
    total_chunks: int = Field(..., description="Total chunks remaining in session")
    fields_modified: list[str] = Field(
        default_factory=list, description="Unique field names modified across all deltas"
    )


class ReparentPathMapping(BaseModel):
    """Pairwise mapping from old ltree path to new ltree path."""

    old_path: str = Field(..., description="Original ltree path before migration")
    new_path: str = Field(..., description="Transformed ltree path after migration")


class StgReparentResult(BaseModel):
    """Result returned by subtree re-parenting operation."""

    model_config = ConfigDict(extra="ignore")

    doc_code: str = Field(..., description="Statutory document code")
    status: str = Field("SUCCESS", description="Operation status")
    dry_run: bool = Field(False, description="Whether mutation was simulated")
    affected_chunks_count: int = Field(..., description="Total count of chunks whose path was migrated")
    affected_edges_count: int = Field(..., description="Total count of internal edges migrated")
    old_path_prefix: str = Field(..., description="Old prefix searched")
    new_path_prefix: str = Field(..., description="New target prefix")
    sample_mappings: list[ReparentPathMapping] = Field(
        default_factory=list, description="Sample of path mappings (up to 10)"
    )


class StagingStatus(str, Enum):
    """Lifecycle statuses for statutory staging sessions."""

    DRAFT = "DRAFT"
    AGENT_COMMITTED = "AGENT_COMMITTED"
    APPROVED = "APPROVED"
    PROMOTED = "PROMOTED"


class StagingMutationRecord(BaseModel):
    """Immutable audit trail entry for staging session transformations."""

    model_config = ConfigDict(extra="ignore")

    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Unique mutation record ID")
    timestamp: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC),
        description="UTC timestamp of mutation",
    )
    actor: str = Field(..., description="'SYSTEM' | 'AGENT' | 'HUMAN:<username>'")
    action_type: str = Field(..., description="Action type code")
    description: str = Field(..., description="Human-readable summary of mutation")
    diff_payload: dict[str, Any] | None = Field(default=None, description="Detailed mutation payload")


class StagingSessionSummary(BaseModel):
    """Lightweight summary model for dashboard listing."""

    model_config = ConfigDict(extra="ignore")

    doc_code: str = Field(..., description="Statutory document code")
    title: str = Field(..., description="Document title")
    status: StagingStatus = Field(..., description="Current staging status")
    total_chunks: int = Field(..., description="Total count of staged chunks")
    total_edges: int = Field(..., description="Total count of staged edges")
    effective_date: datetime.date = Field(..., description="Effective date")
    expiration_date: datetime.date | None = Field(None, description="Expiration date")
    created_at: datetime.datetime = Field(..., description="Session creation timestamp")
    updated_at: datetime.datetime = Field(..., description="Session last updated timestamp")
    committed_at: datetime.datetime | None = Field(None, description="Session commit timestamp")
    promoted_at: datetime.datetime | None = Field(None, description="Session promotion timestamp")


class RawTextWindow(BaseModel):
    """Encapsulates a bounded line-window of original statutory source text."""

    model_config = ConfigDict(extra="ignore")

    doc_code: str = Field(..., description="Document statutory code")
    start_line: int = Field(..., ge=1, description="1-indexed starting line number")
    end_line: int = Field(..., ge=1, description="1-indexed ending line number")
    total_lines: int = Field(..., ge=0, description="Total line count of source raw text")
    lines: list[str] = Field(default_factory=list, description="Array of sliced raw lines")
    content: str = Field(..., description="Newline-concatenated text of the window slice")


class StagingGrepHit(BaseModel):
    """Represents a matched chunk hit from in-memory staging session grep."""

    model_config = ConfigDict(extra="ignore")

    path: str = Field(..., description="Hierarchical dot-separated ltree path")
    field_matched: str = Field(..., description="'VERBATIM' | 'CONTEXT' | 'PATH' | 'METADATA'")
    match_snippet: str = Field(..., description="Concise snippet highlighting the matched term")
    verbatim_text: str = Field(..., description="Complete verbatim text of the chunk")
    contextualized_text: str = Field(..., description="Full CPHC synthesized context text")
    char_length: int = Field(..., description="Character count of verbatim text")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Chunk metadata payload")


class StagingChunk(BaseModel):
    """Represents a candidate statutory chunk within a staging session."""

    model_config = ConfigDict(extra="ignore")

    path: str = Field(..., description="Hierarchical dot-separated ltree path")
    verbatim_text: str = Field(..., description="Verbatim clause/point text")
    contextualized_text: str = Field(..., description="Synthesized CPHC context text")
    lead_sentence: str = Field("", description="Inherited lead sentence")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Dynamic metadata payload")
    effective_date: datetime.date = Field(..., description="Effective date")
    expiration_date: datetime.date | None = Field(None, description="Expiration date")
    char_length: int = Field(default=0, description="Total character count of verbatim text")

    @field_validator("effective_date", "expiration_date", mode="before")
    @classmethod
    def parse_dates(cls, v: Any) -> datetime.date | None:
        if v is None:
            return None
        return parse_flexible_date(v)

    @model_validator(mode="after")
    def compute_char_length(self) -> StagingChunk:
        if not self.char_length and self.verbatim_text:
            self.char_length = len(self.verbatim_text)
        return self


class StagingEdge(BaseModel):
    """Represents a candidate directed relation edge within a staging session."""

    model_config = ConfigDict(extra="ignore")

    source_path: str = Field(..., description="Source chunk ltree path")
    target_path: str | None = Field(None, description="Target chunk ltree path")
    target_external_ref: str | None = Field(None, description="External citation text")
    relation_type: str = Field(..., description="Graph relation type enum string")
    citation_text: str | None = Field(None, description="Verbatim statutory citation phrase")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Dynamic edge metadata")


class StagingDocumentSession(BaseModel):
    """Represents a persisted staging document session."""

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
    raw_text: str | None = Field(default=None, description="Raw statutory source text")
    doc_metadata: dict[str, Any] = Field(default_factory=dict, description="Document metadata")
    chunks: list[StagingChunk] = Field(default_factory=list, description="List of staged chunks")
    edges: list[StagingEdge] = Field(default_factory=list, description="List of staged graph edges")
    raw_ast_snapshot: list[dict[str, Any]] | None = Field(
        default=None, description="Initial AST/CPHC baseline snapshot for version diffing"
    )
    mutation_history: list[StagingMutationRecord] = Field(
        default_factory=list, description="Audit trail of mutations"
    )

    @field_validator("effective_date", "expiration_date", mode="before")
    @classmethod
    def parse_dates(cls, v: Any) -> datetime.date | None:
        if v is None:
            return None
        return parse_flexible_date(v)

    def get_chunk(self, path: str) -> StagingChunk | None:
        """Looks up a single staged chunk by dot-separated ltree path.

        Args:
            path: Target ltree path e.g. 'doc_100_2019_nd_cp.a_5.c_3.p_a'.

        Returns:
            Matched StagingChunk if present, None otherwise.
        """
        clean_path = path.strip()
        for chunk in self.chunks:
            if chunk.path == clean_path:
                return chunk
        return None

    def get_raw_window(self, start_line: int = 1, end_line: int = 100) -> RawTextWindow:
        """Extracts a 1-indexed bounded slice of lines from session raw_text.

        Args:
            start_line: 1-indexed start line (inclusive).
            end_line: 1-indexed end line (inclusive).

        Returns:
            Populated RawTextWindow with clamped indices and lines.

        Raises:
            LegalDomainError(E_CORPUS_INTEGRITY_VIOLATION): If raw_text is null or empty.
        """
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
        clamped_end = max(clamped_start, min(end_line, total_lines))

        selected_lines = all_lines[clamped_start - 1 : clamped_end]
        content = "\n".join(selected_lines)

        return RawTextWindow(
            doc_code=self.doc_code,
            start_line=clamped_start,
            end_line=clamped_end,
            total_lines=total_lines,
            lines=selected_lines,
            content=content,
        )

    def grep(
        self,
        pattern: str,
        is_regex: bool = False,
        case_sensitive: bool = False,
        search_in: str = "ALL",
        limit: int = 50,
    ) -> list[StagingGrepHit]:
        """Searches in-memory chunks in the session using substring or regex matching.

        Args:
            pattern: Search string or regular expression.
            is_regex: If True, evaluates pattern as a compiled POSIX/Python regex.
            case_sensitive: If True, respects letter case.
            search_in: Targeted search field ('ALL' | 'VERBATIM' | 'CONTEXT' | 'PATH' | 'METADATA').
            limit: Maximum matches to return.

        Returns:
            List of StagingGrepHit records up to limit.
        """
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

        hits: list[StagingGrepHit] = []

        def _check_match(text: str) -> tuple[bool, str]:
            if not text:
                return False, ""
            if compiled_regex is not None:
                m = compiled_regex.search(text)
                if m:
                    s_start = max(0, m.start() - 30)
                    s_end = min(len(text), m.end() + 30)
                    snippet = text[s_start:s_end].replace("\n", " ").strip()
                    return True, snippet
                return False, ""
            else:
                target_str = text if case_sensitive else text.lower()
                query_str = clean_pattern if case_sensitive else clean_pattern.lower()
                idx = target_str.find(query_str)
                if idx >= 0:
                    s_start = max(0, idx - 30)
                    s_end = min(len(text), idx + len(clean_pattern) + 30)
                    snippet = text[s_start:s_end].replace("\n", " ").strip()
                    return True, snippet
                return False, ""

        for chunk in self.chunks:
            if len(hits) >= limit:
                break

            matched_field: str | None = None
            snippet: str = ""

            # Check PATH
            if search_mode in ("ALL", "PATH"):
                matched, snip = _check_match(chunk.path)
                if matched:
                    matched_field = "PATH"
                    snippet = f"Path: {chunk.path}"

            # Check VERBATIM
            if not matched_field and search_mode in ("ALL", "VERBATIM"):
                matched, snip = _check_match(chunk.verbatim_text)
                if matched:
                    matched_field = "VERBATIM"
                    snippet = snip

            # Check CONTEXT
            if not matched_field and search_mode in ("ALL", "CONTEXT"):
                matched, snip = _check_match(chunk.contextualized_text)
                if matched:
                    matched_field = "CONTEXT"
                    snippet = snip

            # Check METADATA
            if not matched_field and search_mode in ("ALL", "METADATA"):
                meta_str = json.dumps(chunk.metadata, ensure_ascii=False)
                matched, snip = _check_match(meta_str)
                if matched:
                    matched_field = "METADATA"
                    snippet = snip

            if matched_field:
                hits.append(
                    StagingGrepHit(
                        path=chunk.path,
                        field_matched=matched_field,
                        match_snippet=snippet,
                        verbatim_text=chunk.verbatim_text,
                        contextualized_text=chunk.contextualized_text,
                        char_length=chunk.char_length or len(chunk.verbatim_text),
                        metadata=chunk.metadata,
                    )
                )

        return hits

    def apply_chunk_deltas(
        self,
        deltas: Sequence[StagingChunkDelta],
        removed_paths: list[str] | None = None,
        cascade_breadcrumbs: bool = True,
        actor: str = "AGENT",
    ) -> StagingDeltaReport:
        """Applies surgical field-level updates and removals to chunks in the session."""
        if self.status == StagingStatus.PROMOTED:
            raise LegalDomainError(
                error_code=E_CORPUS_INTEGRITY_VIOLATION,
                message=f"Không thể chỉnh sửa phiên staging ở trạng thái '{self.status.value}'.",
                data={"doc_code": self.doc_code, "status": self.status.value},
            )

        chunk_map: dict[str, StagingChunk] = {c.path: c for c in self.chunks}
        removed_count = 0
        if removed_paths:
            for rp in removed_paths:
                clean_rp = validate_ltree_path(rp)
                if clean_rp in chunk_map:
                    del chunk_map[clean_rp]
                    removed_count += 1

        fields_modified_set: set[str] = set()
        cascaded_count = 0

        for delta in deltas:
            clean_p = validate_ltree_path(delta.path)
            chunk = chunk_map.get(clean_p)
            if chunk is None:
                if delta.verbatim_text is not None:
                    # Surgical creation of a new chunk
                    new_chunk = StagingChunk(
                        path=clean_p,
                        verbatim_text=delta.verbatim_text,
                        contextualized_text=delta.contextualized_text or delta.verbatim_text,
                        lead_sentence=delta.lead_sentence or "",
                        metadata=delta.metadata or {},
                        effective_date=delta.effective_date or self.effective_date,
                        expiration_date=delta.expiration_date or self.expiration_date,
                    )
                    chunk_map[clean_p] = new_chunk
                    fields_modified_set.add("created")
                    continue
                raise LegalDomainError(
                    error_code=E_INVALID_DOCUMENT_HIERARCHY,
                    message=f"Đoạn quy phạm '{clean_p}' không tồn tại trong phiên làm việc cho văn bản '{self.doc_code}'.",
                    data={"doc_code": self.doc_code, "path": clean_p},
                )

            if delta.verbatim_text is not None:
                chunk.verbatim_text = delta.verbatim_text
                chunk.char_length = len(delta.verbatim_text)
                fields_modified_set.add("verbatim_text")

            if delta.contextualized_text is not None:
                chunk.contextualized_text = delta.contextualized_text
                fields_modified_set.add("contextualized_text")

            if delta.metadata is not None:
                chunk.metadata = deep_merge_dict(chunk.metadata, delta.metadata)
                fields_modified_set.add("metadata")

            if delta.effective_date is not None:
                chunk.effective_date = delta.effective_date
                fields_modified_set.add("effective_date")

            if delta.expiration_date is not None:
                chunk.expiration_date = delta.expiration_date
                fields_modified_set.add("expiration_date")

            if delta.lead_sentence is not None and delta.lead_sentence != chunk.lead_sentence:
                old_lead = chunk.lead_sentence
                chunk.lead_sentence = delta.lead_sentence
                fields_modified_set.add("lead_sentence")

                # Cascade lead sentence to all descendant child points
                if cascade_breadcrumbs:
                    child_prefix = f"{clean_p}."
                    for other_p, other_c in chunk_map.items():
                        if other_p.startswith(child_prefix):
                            other_c.lead_sentence = delta.lead_sentence
                            if old_lead and old_lead in other_c.contextualized_text:
                                other_c.contextualized_text = other_c.contextualized_text.replace(
                                    old_lead, delta.lead_sentence
                                )
                            elif delta.lead_sentence not in other_c.contextualized_text:
                                other_c.contextualized_text = (
                                    f"{other_c.contextualized_text}\n{delta.lead_sentence}"
                                )
                            cascaded_count += 1

        sorted_chunks = sorted(chunk_map.values(), key=lambda x: x.path)
        self.chunks = sorted_chunks

        now = datetime.datetime.now(datetime.UTC)
        self.updated_at = now
        self.mutation_history.append(
            StagingMutationRecord(
                actor=actor,
                action_type="CHUNK_PATCHED",
                description=f"Patched {len(deltas)} chunks (cascaded {cascaded_count} children) and removed {removed_count} paths.",
                timestamp=now,
                diff_payload={
                    "updated_count": len(deltas),
                    "cascaded_count": cascaded_count,
                    "removed_count": removed_count,
                    "fields_modified": sorted(fields_modified_set),
                    "removed_paths": removed_paths or [],
                },
            )
        )

        return StagingDeltaReport(
            doc_code=self.doc_code,
            updated_count=len(deltas),
            cascaded_count=cascaded_count,
            removed_count=removed_count,
            total_chunks=len(self.chunks),
            fields_modified=sorted(fields_modified_set),
        )

    def validate_and_attach_edges(
        self,
        edges: Sequence[StagingEdge],
        actor: str = "AGENT",
    ) -> tuple[int, list[StagingEdge]]:
        """Pre-commit lints candidate relation edges and attaches valid ones to the session."""
        if self.status == StagingStatus.PROMOTED:
            raise LegalDomainError(
                error_code=E_CORPUS_INTEGRITY_VIOLATION,
                message=f"Không thể chỉnh sửa phiên staging ở trạng thái '{self.status.value}'.",
                data={"doc_code": self.doc_code, "status": self.status.value},
            )

        valid_paths = {c.path for c in self.chunks}
        doc_prefix = sanitize_ltree_label(self.doc_code)

        existing_edges: dict[tuple[str, str | None, str], StagingEdge] = {
            (e.source_path, e.target_path, e.relation_type): e for e in self.edges
        }

        for new_edge in edges:
            clean_src = validate_ltree_path(new_edge.source_path)
            clean_tgt = validate_ltree_path(new_edge.target_path) if new_edge.target_path else None

            # Grounding check 1: source_path must exist
            if clean_src not in valid_paths:
                raise LegalDomainError(
                    error_code=E_AST_GROUNDING_VALIDATION,
                    message=f"Invalid edge source path '{clean_src}': path does not exist in staged document '{self.doc_code}'.",
                    data={"doc_code": self.doc_code, "source_path": clean_src},
                )

            # Self-loop check
            if clean_tgt and clean_src == clean_tgt:
                raise LegalDomainError(
                    error_code=E_AST_GROUNDING_VALIDATION,
                    message=f"Self-referencing edge loop detected on '{clean_src}'.",
                    data={"doc_code": self.doc_code, "path": clean_src},
                )

            # Grounding check 2: intra-document target_path must exist
            if clean_tgt and clean_tgt.startswith(f"{doc_prefix}.") and clean_tgt not in valid_paths:
                raise LegalDomainError(
                    error_code=E_AST_GROUNDING_VALIDATION,
                    message=f"Invalid edge target path '{clean_tgt}': intra-document target does not exist in staged document '{self.doc_code}'.",
                    data={"doc_code": self.doc_code, "target_path": clean_tgt},
                )

            new_edge.source_path = clean_src
            new_edge.target_path = clean_tgt
            key = (clean_src, clean_tgt, new_edge.relation_type)
            existing_edges[key] = new_edge

        self.edges = list(existing_edges.values())

        now = datetime.datetime.now(datetime.UTC)
        self.updated_at = now
        self.mutation_history.append(
            StagingMutationRecord(
                actor=actor,
                action_type="EDGES_ADDED",
                description=f"Added or updated {len(edges)} relation edges.",
                timestamp=now,
                diff_payload={"edges_count": len(edges)},
            )
        )

        return len(self.edges), self.edges

    def reparent_subtree(
        self,
        old_path_prefix: str,
        new_path_prefix: str,
        dry_run: bool = False,
        actor: str = "AGENT",
    ) -> StgReparentResult:
        """Atomically migrates an entire subtree and its graph edges to a new parent prefix."""
        if self.status == StagingStatus.PROMOTED:
            raise LegalDomainError(
                error_code=E_CORPUS_INTEGRITY_VIOLATION,
                message=f"Không thể tái cấu trúc phiên staging ở trạng thái '{self.status.value}'.",
                data={"doc_code": self.doc_code, "status": self.status.value},
            )

        clean_old = validate_ltree_path(old_path_prefix)
        clean_new = validate_ltree_path(new_path_prefix)
        doc_prefix = sanitize_ltree_label(self.doc_code)

        if not (clean_old == doc_prefix or clean_old.startswith(f"{doc_prefix}.")):
            raise LegalDomainError(
                error_code=E_INVALID_DOCUMENT_HIERARCHY,
                message=f"Đường dẫn cũ '{clean_old}' không thuộc văn bản '{self.doc_code}'.",
                data={"doc_code": self.doc_code, "path": clean_old},
            )

        if not (clean_new == doc_prefix or clean_new.startswith(f"{doc_prefix}.")):
            raise LegalDomainError(
                error_code=E_INVALID_DOCUMENT_HIERARCHY,
                message=f"Đường dẫn mới '{clean_new}' không thuộc văn bản '{self.doc_code}'.",
                data={"doc_code": self.doc_code, "path": clean_new},
            )

        if clean_new == clean_old or clean_new.startswith(f"{clean_old}."):
            raise LegalDomainError(
                error_code=E_INVALID_DOCUMENT_HIERARCHY,
                message=f"Không thể di dời nút cha '{clean_old}' vào trong chính nó hoặc con cháu của nó '{clean_new}'.",
                data={"old_path_prefix": clean_old, "new_path_prefix": clean_new},
            )

        old_dot = f"{clean_old}."
        target_chunks: list[StagingChunk] = [
            c for c in self.chunks if c.path == clean_old or c.path.startswith(old_dot)
        ]
        if not target_chunks:
            raise LegalDomainError(
                error_code=E_INVALID_DOCUMENT_HIERARCHY,
                message=f"Không tìm thấy đoạn quy phạm nào khớp với tiền tố '{clean_old}'.",
                data={"doc_code": self.doc_code, "path_prefix": clean_old},
            )

        new_dot = f"{clean_new}."
        collision_chunks = [
            c for c in self.chunks if c.path == clean_new or c.path.startswith(new_dot)
        ]
        if collision_chunks:
            raise LegalDomainError(
                error_code=E_INVALID_DOCUMENT_HIERARCHY,
                message=f"Tiền tố đích '{clean_new}' bị xung đột với {len(collision_chunks)} đoạn quy phạm đã tồn tại.",
                data={"doc_code": self.doc_code, "colliding_path": collision_chunks[0].path},
            )

        sample_mappings: list[ReparentPathMapping] = []
        path_rename_map: dict[str, str] = {}
        for c in target_chunks:
            if c.path == clean_old:
                new_p = clean_new
            else:
                suffix = c.path[len(clean_old) :]
                new_p = f"{clean_new}{suffix}"
            path_rename_map[c.path] = new_p
            if len(sample_mappings) < 10:
                sample_mappings.append(ReparentPathMapping(old_path=c.path, new_path=new_p))

        # Check affected edges
        affected_edges_count = 0
        for e in self.edges:
            is_affected = False
            if e.source_path in path_rename_map or e.source_path.startswith(old_dot) or e.target_path and (e.target_path in path_rename_map or e.target_path.startswith(old_dot)):
                is_affected = True
            if is_affected:
                affected_edges_count += 1

        result = StgReparentResult(
            doc_code=self.doc_code,
            status="SUCCESS",
            dry_run=dry_run,
            affected_chunks_count=len(target_chunks),
            affected_edges_count=affected_edges_count,
            old_path_prefix=clean_old,
            new_path_prefix=clean_new,
            sample_mappings=sample_mappings,
        )

        if dry_run:
            return result

        # Apply mutations
        for c in target_chunks:
            c.path = path_rename_map[c.path]

        # Migrate internal edges
        existing_edges: dict[tuple[str, str | None, str], StagingEdge] = {}
        for e in self.edges:
            new_src = path_rename_map.get(e.source_path)
            if new_src is None and e.source_path.startswith(old_dot):
                new_src = f"{clean_new}{e.source_path[len(clean_old):]}"
            if new_src:
                e.source_path = new_src

            if e.target_path:
                new_tgt = path_rename_map.get(e.target_path)
                if new_tgt is None and e.target_path.startswith(old_dot):
                    new_tgt = f"{clean_new}{e.target_path[len(clean_old):]}"
                if new_tgt:
                    e.target_path = new_tgt

            key = (e.source_path, e.target_path, e.relation_type)
            existing_edges[key] = e

        self.edges = list(existing_edges.values())
        self.chunks.sort(key=lambda x: x.path)

        now = datetime.datetime.now(datetime.UTC)
        self.updated_at = now
        self.mutation_history.append(
            StagingMutationRecord(
                actor=actor,
                action_type="SUBTREE_REPARENTED",
                description=f"Migrated subtree '{clean_old}' to '{clean_new}' ({len(target_chunks)} chunks, {affected_edges_count} edges).",
                timestamp=now,
                diff_payload={
                    "old_path_prefix": clean_old,
                    "new_path_prefix": clean_new,
                    "affected_chunks": len(target_chunks),
                    "affected_edges": affected_edges_count,
                    "sample_mappings": [m.model_dump() for m in sample_mappings],
                },
            )
        )

        return result


class StagingManager:
    """Manages disk-based staging sessions for two-phase statutory ingestion."""

    def __init__(self, staging_dir: Path | str = DEFAULT_STAGING_DIR) -> None:
        self.staging_dir = Path(staging_dir)
        self.staging_dir.mkdir(parents=True, exist_ok=True)

    def reparent_node(
        self,
        doc_code: str,
        old_path_prefix: str,
        new_path_prefix: str,
        dry_run: bool = False,
        actor: str = "AGENT",
    ) -> tuple[StagingDocumentSession, StgReparentResult]:
        """Loads session, applies subtree re-parenting, persists if not dry_run, and returns session + result."""
        session = self.load_session(doc_code)
        result = session.reparent_subtree(
            old_path_prefix=old_path_prefix,
            new_path_prefix=new_path_prefix,
            dry_run=dry_run,
            actor=actor,
        )
        if not dry_run:
            self.save_session(session)
        return session, result

    def _get_session_path(self, doc_code: str) -> Path:
        sanitized = sanitize_ltree_label(doc_code)
        return self.staging_dir / f"{sanitized}.json"

    def create_session_from_raw(
        self,
        doc_code: str,
        title: str,
        raw_text: str,
        effective_date: datetime.date,
        expiration_date: datetime.date | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> StagingDocumentSession:
        """Parses raw text via AST and CPHC into a fresh StagingDocumentSession and persists to disk."""
        parser = LegalASTParser(doc_code=doc_code)
        root = parser.parse(raw_text, doc_title=title)

        temp_doc_id = uuid.uuid4()
        cphc = CPHCEngine(
            document_id=temp_doc_id,
            doc_code=doc_code,
            doc_title=title,
            effective_date=effective_date,
            expiration_date=expiration_date,
        )
        canonical_chunks = cphc.chunk_ast(root)

        stg_chunks = [
            StagingChunk(
                path=c.path,
                verbatim_text=c.verbatim_text,
                contextualized_text=c.contextualized_text,
                lead_sentence="",
                metadata=c.metadata,
                effective_date=c.effective_date,
                expiration_date=c.expiration_date,
            )
            for c in canonical_chunks
        ]

        now = datetime.datetime.now(datetime.UTC)
        initial_mutation = StagingMutationRecord(
            actor="SYSTEM",
            action_type="CREATED",
            description=f"Created initial staging session from raw text ({len(stg_chunks)} chunks).",
            timestamp=now,
            diff_payload={"total_chunks": len(stg_chunks)},
        )

        raw_ast_snapshot = [c.model_dump(mode="json") for c in stg_chunks]

        session = StagingDocumentSession(
            doc_code=doc_code,
            title=title,
            status=StagingStatus.DRAFT,
            effective_date=effective_date,
            expiration_date=expiration_date,
            created_at=now,
            updated_at=now,
            committed_at=None,
            promoted_at=None,
            raw_text=raw_text,
            doc_metadata=metadata or {},
            chunks=stg_chunks,
            edges=[],
            raw_ast_snapshot=raw_ast_snapshot,
            mutation_history=[initial_mutation],
        )
        self.save_session(session)
        return session

    def load_session(self, doc_code: str) -> StagingDocumentSession:
        """Loads an existing staging session from disk."""
        p = self._get_session_path(doc_code)
        if not p.exists():
            raise LegalDomainError(
                error_code=E_CORPUS_INTEGRITY_VIOLATION,
                message=f"Staging session for document '{doc_code}' does not exist at {p}",
                data={"doc_code": doc_code, "staging_path": str(p)},
            )

        try:
            content = p.read_text(encoding="utf-8")
            raw_data = json.loads(content)
            return StagingDocumentSession.model_validate(raw_data)
        except json.JSONDecodeError as exc:
            raise LegalDomainError(
                error_code=E_CORPUS_INTEGRITY_VIOLATION,
                message=f"Staging session for document '{doc_code}' is corrupted: {exc}",
                data={"doc_code": doc_code},
            ) from exc

    def save_session(self, session: StagingDocumentSession) -> Path:
        """Atomically persists a staging session to disk using temp file rename."""
        p = self._get_session_path(session.doc_code)
        p.parent.mkdir(parents=True, exist_ok=True)
        content = session.model_dump_json(indent=2)

        tmp_p = p.parent / f"{p.name}.tmp.{uuid.uuid4()}"
        try:
            with open(tmp_p, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            tmp_p.replace(p)
        except (OSError, RuntimeError):
            if tmp_p.exists():
                tmp_p.unlink(missing_ok=True)
            raise
        return p

    def patch_chunks(
        self,
        doc_code: str,
        updated_chunks: Sequence[StagingChunkDelta | StagingChunk | dict[str, Any]] | None = None,
        removed_paths: list[str] | None = None,
        cascade_breadcrumbs: bool = True,
        actor: str = "AGENT",
    ) -> StagingDocumentSession:
        """Surgically updates or removes chunks within an existing staging session."""
        session = self.load_session(doc_code)
        parsed_deltas: list[StagingChunkDelta] = []
        if updated_chunks:
            for item in updated_chunks:
                if isinstance(item, StagingChunkDelta):
                    parsed_deltas.append(item)
                elif isinstance(item, StagingChunk):
                    parsed_deltas.append(
                        StagingChunkDelta(
                            path=item.path,
                            verbatim_text=item.verbatim_text,
                            contextualized_text=item.contextualized_text,
                            lead_sentence=item.lead_sentence,
                            metadata=item.metadata,
                            effective_date=item.effective_date,
                            expiration_date=item.expiration_date,
                        )
                    )
                elif isinstance(item, dict):
                    parsed_deltas.append(StagingChunkDelta.model_validate(item))

        session.apply_chunk_deltas(
            deltas=parsed_deltas,
            removed_paths=removed_paths,
            cascade_breadcrumbs=cascade_breadcrumbs,
            actor=actor,
        )
        self.save_session(session)
        return session

    def add_edges(
        self,
        doc_code: str,
        edges: Sequence[StagingEdge | dict[str, Any]],
        actor: str = "AGENT",
    ) -> StagingDocumentSession:
        """Appends and deduplicates graph relationship edges in the staging session with pre-commit validation."""
        session = self.load_session(doc_code)
        parsed_edges: list[StagingEdge] = []
        for e in edges:
            if isinstance(e, StagingEdge):
                parsed_edges.append(e)
            elif isinstance(e, dict):
                parsed_edges.append(StagingEdge.model_validate(e))

        session.validate_and_attach_edges(edges=parsed_edges, actor=actor)
        self.save_session(session)
        return session

    def list_sessions(self) -> list[StagingSessionSummary]:
        """Discovers and lists summaries of all staging sessions in the staging directory."""
        summaries: list[StagingSessionSummary] = []
        if not self.staging_dir.exists():
            return summaries
        for file_path in sorted(self.staging_dir.glob("*.json")):
            if file_path.name.startswith("."):
                continue
            try:
                content = file_path.read_text(encoding="utf-8")
                data = json.loads(content)
                session = StagingDocumentSession.model_validate(data)
                summaries.append(
                    StagingSessionSummary(
                        doc_code=session.doc_code,
                        title=session.title,
                        status=session.status,
                        total_chunks=len(session.chunks),
                        total_edges=len(session.edges),
                        effective_date=session.effective_date,
                        expiration_date=session.expiration_date,
                        created_at=session.created_at,
                        updated_at=session.updated_at,
                        committed_at=session.committed_at,
                        promoted_at=session.promoted_at,
                    )
                )
            except (json.JSONDecodeError, ValueError, KeyError, OSError) as exc:
                logger.warning("Skipping unreadable staging session file %s: %s", file_path, exc)
        return summaries

    def update_session_status(
        self,
        doc_code: str,
        status: StagingStatus,
        actor: str,
        description: str,
    ) -> StagingDocumentSession:
        """Updates the status of an existing staging session and records the transition in mutation history."""
        session = self.load_session(doc_code)
        old_status = session.status
        session.status = status
        now = datetime.datetime.now(datetime.UTC)
        session.updated_at = now

        if status == StagingStatus.AGENT_COMMITTED and not session.committed_at:
            session.committed_at = now
        elif status == StagingStatus.PROMOTED and not session.promoted_at:
            session.promoted_at = now

        session.mutation_history.append(
            StagingMutationRecord(
                actor=actor,
                action_type=f"STATUS_TRANSITION_{status.value}",
                description=description or f"Transitioned status from {old_status.value} to {status.value}",
                timestamp=now,
                diff_payload={"old_status": old_status.value, "new_status": status.value},
            )
        )
        self.save_session(session)
        return session

    def delete_session(self, doc_code: str) -> bool:
        """Deletes a staging session file after successful promotion to PostgreSQL."""
        p = self._get_session_path(doc_code)
        if p.exists():
            p.unlink()
            return True
        return False
