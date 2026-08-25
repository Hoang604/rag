"""Unit tests for Pydantic domain schemas with strict typing."""

import pytest
from pydantic import ValidationError

from rag_eval.schemas import (
    Document,
    GroundTruth,
    PredictionResult,
    Query,
    TextSpan,
)


def test_document_schema_validation() -> None:
    """Test valid and invalid document instantiation."""
    doc = Document(
        id="doc_1",
        text="Sample document text.",
        title="Sample Title",
        metadata={"category": "legal", "clause_count": 5},
    )
    assert doc.id == "doc_1"
    assert doc.text == "Sample document text."
    assert doc.title == "Sample Title"
    assert doc.metadata["category"] == "legal"
    assert doc.metadata["clause_count"] == 5

    # Test serialization roundtrip
    json_str = doc.model_dump_json()
    reloaded = Document.model_validate_json(json_str)
    assert reloaded == doc


def test_query_and_ground_truth_schemas() -> None:
    """Test Query and GroundTruth schema validation with spans."""
    span = TextSpan(start_char=10, end_char=35, text="termination clause", section_name="Section 4")
    gt = GroundTruth(
        query_id="q_1",
        relevant_doc_ids=["doc_1", "doc_2"],
        answers=["Termination within 30 days."],
        spans=[span],
    )
    assert gt.query_id == "q_1"
    assert len(gt.relevant_doc_ids) == 2
    assert len(gt.spans) == 1
    assert gt.spans[0].start_char == 10

    q = Query(id="q_1", text="What is the termination period?", metadata={"source": "CUAD"})
    assert q.id == "q_1"


def test_prediction_result_schema() -> None:
    """Test PredictionResult model validation."""
    pred = PredictionResult(
        query_id="q_1",
        retrieved_doc_ids=["doc_1", "doc_3"],
        generated_answer="30 days notice required.",
        latency_ms=124.5,
    )
    assert pred.query_id == "q_1"
    assert pred.latency_ms == 124.5
    assert pred.retrieved_doc_ids == ["doc_1", "doc_3"]


def test_extra_fields_forbidden() -> None:
    """Ensure extra attributes raise validation errors."""
    with pytest.raises(ValidationError):
        _ = Document.model_validate({"id": "d1", "text": "abc", "unexpected_field": "invalid"})
