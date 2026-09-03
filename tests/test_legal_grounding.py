"""Tests for ingestion-time grounding verification.

These cover the failure class no retrieval metric can detect: a chunk that is
retrieved correctly but whose statutory figures were corrupted during parsing.
"""

from __future__ import annotations

import pytest

from rag_eval.legal.ingestion.grounding import (
    ChunkGroundingError,
    enforce_chunk_grounding,
    verify_chunk_grounding,
)

SOURCE = """Điều 6. Xử phạt người điều khiển xe ô tô
1. Phạt tiền từ 18.000.000 đồng đến 20.000.000 đồng đối với hành vi vi phạm sau đây:
a) Điều khiển xe chạy quá tốc độ quy định từ 05 km/h đến dưới 10 km/h;
b) Không tuân thủ hiệu lệnh của đèn tín hiệu giao thông.
"""


def test_fully_grounded_chunks_produce_no_violations() -> None:
    """Chunks copied verbatim from the source pass both checks."""
    chunks = {
        "d6.k1": "1. Phạt tiền từ 18.000.000 đồng đến 20.000.000 đồng đối với hành vi vi phạm sau đây:",
        "d6.k1.a": "a) Điều khiển xe chạy quá tốc độ quy định từ 05 km/h đến dưới 10 km/h;",
    }
    assert verify_chunk_grounding(chunks, SOURCE) == []


def test_dropped_digit_in_fine_is_fatal() -> None:
    """A corrupted fine amount is caught: 18.000.000 silently became 8.000.000."""
    chunks = {"d6.k1": "1. Phạt tiền từ 8.000.000 đồng đến 20.000.000 đồng"}
    violations = verify_chunk_grounding(chunks, SOURCE)

    numeric = [v for v in violations if v.check == "numeric"]
    assert len(numeric) == 1
    assert numeric[0].severity == "fatal"
    # Reported in normalised form: separators are collapsed before comparison.
    assert "8000000" in numeric[0].detail
    assert numeric[0].chunk_path == "d6.k1"


def test_fabricated_speed_limit_is_fatal() -> None:
    """A speed threshold absent from the source is caught."""
    chunks = {"d6.k1.a": "a) Điều khiển xe chạy quá tốc độ quy định từ 25 km/h"}
    numeric = [v for v in verify_chunk_grounding(chunks, SOURCE) if v.check == "numeric"]
    assert len(numeric) == 1
    assert "25" in numeric[0].detail


def test_digit_separator_style_does_not_false_positive() -> None:
    """18 000 000 matches 18.000.000: separators are ignored, digits are not."""
    chunks = {"d6.k1": "Phạt tiền từ 18 000 000 đồng đến 20 000 000 đồng"}
    numeric = [v for v in verify_chunk_grounding(chunks, SOURCE) if v.check == "numeric"]
    assert numeric == []


def test_reflowed_whitespace_is_warning_not_fatal() -> None:
    """Legitimate parser reflow breaks contiguity but must not abort ingestion."""
    chunks = {
        "d6": "Điều 6. Xử phạt người điều khiển xe ô tô 1. Phạt tiền từ 18.000.000 đồng"
    }
    violations = verify_chunk_grounding(chunks, SOURCE)
    assert all(v.severity == "warning" for v in violations)
    assert enforce_chunk_grounding(chunks, SOURCE, strict=True) is not None


def test_enforce_raises_on_fatal_when_strict() -> None:
    """Strict mode aborts before corrupted figures can be persisted."""
    chunks = {"d6.k1": "Phạt tiền từ 8.000.000 đồng"}
    with pytest.raises(ChunkGroundingError) as exc_info:
        enforce_chunk_grounding(chunks, SOURCE, strict=True)
    assert "8000000" in str(exc_info.value)


def test_enforce_reports_without_raising_when_not_strict() -> None:
    """Non-strict mode surfaces violations for triage on a messy corpus."""
    chunks = {"d6.k1": "Phạt tiền từ 8.000.000 đồng"}
    violations = enforce_chunk_grounding(chunks, SOURCE, strict=False)
    assert any(v.severity == "fatal" for v in violations)


def test_text_without_digits_is_trivially_grounded() -> None:
    """Clauses carrying no figures pass the numeric check."""
    chunks = {"d6.k1.b": "b) Không tuân thủ hiệu lệnh của đèn tín hiệu giao thông."}
    assert [v for v in verify_chunk_grounding(chunks, SOURCE) if v.check == "numeric"] == []
