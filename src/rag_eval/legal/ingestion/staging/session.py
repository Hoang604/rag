from __future__ import annotations

import datetime
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from rag_eval.legal.errors import (
    E_AST_GROUNDING_VALIDATION,
    E_CORPUS_INTEGRITY_VIOLATION,
    LegalDomainError,
)
from rag_eval.legal.schemas.domain import (
    GrepMatchTier,
    NodeType,
    RelationEdge,
    StagingStatus,
    StatutoryChunk,
)
from rag_eval.legal.schemas.retrieval import (
    RawTextResult,
)
from rag_eval.legal.schemas.staging import (
    GrepHit,
    MutationRecord,
)
from rag_eval.legal.text import (
    address_of_path,
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

        if start_line < 1:
            raise LegalDomainError(
                error_code=E_AST_GROUNDING_VALIDATION,
                message=f"Dòng bắt đầu start_line ({start_line}) phải lớn hơn hoặc bằng 1.",
                data={"doc_code": self.doc_code, "start_line": start_line},
            )

        target_end = min(total_lines, start_line + 99) if end_line is None else end_line
        if target_end < start_line:
            raise LegalDomainError(
                error_code=E_AST_GROUNDING_VALIDATION,
                message=f"Dòng kết thúc end_line ({target_end}) không được nhỏ hơn dòng bắt đầu start_line ({start_line}).",
                data={"doc_code": self.doc_code, "start_line": start_line, "end_line": target_end},
            )

        window_size = target_end - start_line + 1
        if window_size > 200:
            raise LegalDomainError(
                error_code=E_AST_GROUNDING_VALIDATION,
                message=(
                    f"Cửa sổ dòng yêu cầu ({window_size} dòng) vượt quá giới hạn tối đa cho phép "
                    f"là 200 dòng (từ dòng {start_line} đến {target_end})."
                ),
                data={
                    "doc_code": self.doc_code,
                    "start_line": start_line,
                    "end_line": target_end,
                    "window_size": window_size,
                    "max_allowed": 200,
                },
            )

        clamped_start = max(1, min(start_line, total_lines))
        clamped_end = max(clamped_start, min(target_end, total_lines))
        selected_lines = all_lines[clamped_start - 1 : clamped_end]
        content = "\n".join(f"{clamped_start + idx}: {line}" for idx, line in enumerate(selected_lines))

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
        heading_hint: str | None = None,
        body_hint: str | None = None,
        is_regex: bool = False,
        case_sensitive: bool = False,
        limit: int | None = None,
    ) -> tuple[list[GrepHit], int]:
        """Searches in-memory chunks in the session using hierarchical relevance scoring."""
        if not pattern or not pattern.strip():
            return [], 0

        clean_pattern = pattern.strip()
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

        def _check_match(text: str | None) -> bool:
            if not text:
                return False
            if compiled_regex is not None:
                return compiled_regex.search(text) is not None
            target_str = text if case_sensitive else text.lower()
            query_str = clean_pattern if case_sensitive else clean_pattern.lower()
            return query_str in target_str

        def _check_hint(hint: str | None, text: str | None) -> bool:
            if not hint or not hint.strip() or not text:
                return False
            clean_hint = hint.strip()
            # Match on word boundary to prevent false positives like 'mô tô' containing 'ô tô'
            escaped_hint = re.escape(clean_hint)
            pattern_hint = rf"(?<!\w){escaped_hint}(?!\w)"
            h_flags = 0 if case_sensitive else re.IGNORECASE
            return re.search(pattern_hint, text, flags=h_flags) is not None

        def _highlight(text: str) -> str:
            if compiled_regex is not None:
                return compiled_regex.sub(lambda m: f"**{m.group(0)}**", text)
            escaped = re.escape(clean_pattern)
            return re.sub(escaped, lambda m: f"**{m.group(0)}**", text, flags=flags)

        def _infer_node_type(chunk: StatutoryChunk) -> NodeType:
            if chunk.metadata.node_type is not None:
                return chunk.metadata.node_type
            p = chunk.path.lower()
            last = p.split(".")[-1]
            if last.startswith("p_"):
                return "POINT"
            if last.startswith("c_") and ".a_" in p:
                return "CLAUSE"
            if last.startswith("a_"):
                return "ARTICLE"
            if last.startswith("s_"):
                return "SECTION"
            if last.startswith("c_"):
                return "CHAPTER"
            if "app" in last:
                return "APPENDIX_ITEM" if "_" in last else "APPENDIX"
            return "ARTICLE"

        candidates: list[GrepHit] = []

        for chunk in self.chunks:
            is_body = _check_match(chunk.verbatim_text)
            is_art = _check_match(chunk.metadata.article_title)
            is_sec = _check_match(chunk.metadata.section_title)
            is_chap = _check_match(chunk.metadata.chapter_title)
            is_path = _check_match(chunk.path)

            if not (is_body or is_art or is_sec or is_chap or is_path):
                continue

            matched_in: list[GrepMatchTier] = []
            if is_body:
                matched_in.append("BODY")
            if is_art:
                matched_in.append("ARTICLE_HEADING")
            if is_sec:
                matched_in.append("SECTION_HEADING")
            if is_chap:
                matched_in.append("CHAPTER_HEADING")
            if is_path:
                matched_in.append("PATH")

            is_head_hint = False
            if heading_hint and (
                _check_hint(heading_hint, chunk.metadata.article_title)
                or _check_hint(heading_hint, chunk.metadata.section_title)
                or _check_hint(heading_hint, chunk.metadata.chapter_title)
            ):
                is_head_hint = True
                matched_in.append("HEADING_HINT")

            is_body_hint = False
            if body_hint and _check_hint(body_hint, chunk.verbatim_text):
                is_body_hint = True
                matched_in.append("BODY_HINT")

            if is_body:
                base_score = 0.80
            elif is_art:
                base_score = 0.40
            elif is_sec:
                base_score = 0.20
            elif is_chap:
                base_score = 0.10
            else:
                base_score = 0.30

            bonus = (
                (0.20 if (is_body and (is_art or is_sec)) else 0.0)
                + (0.20 if is_head_hint else 0.0)
                + (0.20 if is_body_hint else 0.0)
            )
            final_score = min(1.0, round(base_score + bonus, 2))

            addr = address_of_path(chunk.path)
            parts: list[str] = []
            if addr.dieu:
                parts.append(f"Điều {addr.dieu}")
            if addr.khoan:
                parts.append(f"Khoản {addr.khoan}")
            if addr.diem:
                parts.append(f"Điểm {addr.diem}")
            addr_str = ", ".join(parts)
            address = (
                addr_str
                or chunk.metadata.index_label
                or (
                    f"Phụ lục {chunk.path.split('.')[-1].upper()}"
                    if "app" in chunk.path
                    else chunk.path
                )
            )

            snippet: str = ""
            if chunk.verbatim_text:
                full_body = chunk.verbatim_text.strip()
                # Find match index in body to center window
                match_span: tuple[int, int] | None = None
                if compiled_regex is not None:
                    m = compiled_regex.search(full_body)
                    if m:
                        match_span = (m.start(), m.end())
                else:
                    target_body = full_body if case_sensitive else full_body.lower()
                    target_pat = clean_pattern if case_sensitive else clean_pattern.lower()
                    idx = target_body.find(target_pat)
                    if idx != -1:
                        match_span = (idx, idx + len(clean_pattern))

                if match_span is not None:
                    m_start, m_end = match_span
                    # Focused window around match (~50-60 chars for < 6 KB UTF-8 payload)
                    win_start = max(0, m_start - 20)
                    win_end = min(len(full_body), m_end + 30)
                    raw_snippet = full_body[win_start:win_end].strip()
                    if win_start > 0:
                        raw_snippet = f"... {raw_snippet}"
                    if win_end < len(full_body):
                        raw_snippet = f"{raw_snippet} ..."
                    snippet = _highlight(raw_snippet)

            if not snippet:
                if is_art and chunk.metadata.article_title:
                    snippet = f"{_highlight(chunk.metadata.article_title)}: {chunk.verbatim_text[:70].strip()} ..."
                elif is_sec and chunk.metadata.section_title:
                    snippet = f"{_highlight(chunk.metadata.section_title)}: {chunk.verbatim_text[:70].strip()} ..."
                elif is_chap and chunk.metadata.chapter_title:
                    snippet = f"{_highlight(chunk.metadata.chapter_title)}: {chunk.verbatim_text[:70].strip()} ..."
                elif is_path:
                    snippet = f"{_highlight(chunk.path)}: {chunk.verbatim_text[:70].strip()} ..."
                else:
                    snippet = chunk.verbatim_text[:70].strip() or chunk.path

            if not snippet.strip():
                snippet = chunk.path

            candidates.append(
                GrepHit(
                    rank=1,
                    score=final_score,
                    path=chunk.path,
                    doc_code=self.doc_code,
                    address=address,
                    node_type=_infer_node_type(chunk),
                    matched_in=matched_in,
                    snippet=snippet,
                    start_line=chunk.start_line,
                    end_line=chunk.end_line,
                )
            )

        candidates.sort(key=lambda h: (-h.score, h.path))
        total_matches = len(candidates)
        if limit is not None:
            candidates = candidates[:limit]

        for i, hit in enumerate(candidates, start=1):
            hit.rank = i

        return candidates, total_matches


