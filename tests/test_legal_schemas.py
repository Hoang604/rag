"""Unit tests for Pydantic v2 schemas and domain models of the 3-table architecture."""

from __future__ import annotations

import datetime
import uuid

import pytest

from rag_eval.legal.schemas import (
    CanonicalFullyQualifiedChunk,
    DocumentRecord,
    GraphEdgeRecord,
    LegalDomainError,
    parse_flexible_date,
    sanitize_ltree_label,
    validate_ltree_path,
)


def test_sanitize_ltree_label() -> None:
    """Verifies label sanitization adheres strictly to PostgreSQL ltree requirements with Vietnamese transliteration."""
    assert sanitize_ltree_label("100/2019/NĐ-CP") == "100_2019_nd_cp"
    assert sanitize_ltree_label("Điều 5.1") == "dieu_5_1"
    assert sanitize_ltree_label("") == "root"
    assert sanitize_ltree_label("___") == "node"


def test_validate_ltree_path() -> None:
    """Verifies path validation and normalization with Vietnamese transliteration."""
    assert validate_ltree_path("doc_100.c_1.a_2") == "doc_100.c_1.a_2"
    assert validate_ltree_path("doc-100. điều 5 . điểm a") == "doc_100.dieu_5.diem_a"
    with pytest.raises(ValueError, match="LTREE path cannot be empty"):
        validate_ltree_path("")


def test_parse_flexible_date() -> None:
    """Verifies flexible statutory date parsing across ISO, DD/MM/YYYY, and YYYY/MM/DD."""
    assert parse_flexible_date("2020-01-15") == datetime.date(2020, 1, 15)
    assert parse_flexible_date("15/01/2020") == datetime.date(2020, 1, 15)
    assert parse_flexible_date("15-01-2020") == datetime.date(2020, 1, 15)
    assert parse_flexible_date("2020/01/15") == datetime.date(2020, 1, 15)
    assert parse_flexible_date(datetime.date(2020, 1, 15)) == datetime.date(2020, 1, 15)
    assert parse_flexible_date(None) is None
    assert parse_flexible_date("") is None
    assert parse_flexible_date("   ") is None


def test_parse_vietnamese_statutory_date() -> None:
    """Verifies parsing Vietnamese legal gazette and statutory date strings."""
    assert parse_flexible_date("Hà Nội, ngày 30 tháng 12 năm 2019") == datetime.date(2019, 12, 30)
    assert parse_flexible_date("ngày 15 tháng 01 năm 2020") == datetime.date(2020, 1, 15)
    assert parse_flexible_date("ngày 5 tháng 9 năm 2024") == datetime.date(2024, 9, 5)


def test_parse_flexible_date_invalid_calendar_and_empty() -> None:
    """Verifies invalid calendar dates or unresolvable strings raise ValueError."""
    with pytest.raises(ValueError, match="Unable to parse date string"):
        parse_flexible_date("31/02/2020")
    with pytest.raises(ValueError, match="Unable to parse date string"):
        parse_flexible_date("invalid-date-format")


def test_document_record_creation(sample_document_record: DocumentRecord) -> None:
    """Verifies DocumentRecord creation and validation."""
    assert sample_document_record.doc_code == "100/2019/NĐ-CP"
    assert sample_document_record.effective_date == datetime.date(2020, 1, 15)
    assert sample_document_record.expiration_date is None
    assert isinstance(sample_document_record.id, uuid.UUID)
    assert sample_document_record.metadata["doc_type"] == "NGHI_DINH"


def test_canonical_chunk_creation(
    sample_chunk_record: CanonicalFullyQualifiedChunk,
) -> None:
    """Verifies CanonicalFullyQualifiedChunk creation and metadata flexibility."""
    assert sample_chunk_record.path == "doc_100_2019_nd_cp.c_ii.a_5.c_3.p_a"
    assert "Điểm a)" in sample_chunk_record.verbatim_text
    assert "[Nghị định 100/2019/NĐ-CP]" in sample_chunk_record.contextualized_text
    assert sample_chunk_record.metadata["fines"]["min_vnd"] == 800000
    assert len(sample_chunk_record.embedding or []) == 384


def test_graph_edge_creation(sample_graph_edge: GraphEdgeRecord) -> None:
    """Verifies GraphEdgeRecord creation with external reference handling."""
    assert sample_graph_edge.relation_type == "REFERENCES"
    assert sample_graph_edge.target_chunk_id is None
    assert "Điều 12" in (sample_graph_edge.target_external_ref or "")


def test_legal_domain_error() -> None:
    """Verifies domain error encapsulation."""
    err = LegalDomainError(error_code=-32001, message="AST validation failed", data={"path": "root"})
    assert err.error_code == -32001
    assert err.message == "AST validation failed"
    assert err.data == {"path": "root"}
