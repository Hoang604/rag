"""Unit tests for BenchmarkDataset JSONL serialization and roundtrip loading."""

from pathlib import Path

from rag_eval.datasets.base import BenchmarkDataset
from rag_eval.schemas import Document, GroundTruth, Query, TextSpan


def test_benchmark_dataset_jsonl_roundtrip(tmp_path: Path) -> None:
    """Test exporting and re-loading BenchmarkDataset via JSONL."""
    span = TextSpan(start_char=5, end_char=25, text="indemnification clause", section_name="Section 8")
    doc = Document(
        id="doc_101",
        text="This is a full legal contract agreement text.",
        title="Agreement 101",
        metadata={"category": "contract", "parties": ["Party A", "Party B"]},
    )
    query = Query(id="q_101", text="Find indemnification clause", metadata={"source": "law"})
    gt = GroundTruth(
        query_id="q_101",
        relevant_doc_ids=["doc_101"],
        answers=["Party A indemnifies Party B."],
        spans=[span],
    )

    dataset = BenchmarkDataset(
        name="synthetic_test",
        description="Synthetic test benchmark dataset",
        documents=[doc],
        queries=[query],
        ground_truths=[gt],
    )

    dataset.export_to_jsonl(tmp_path)

    assert (tmp_path / "documents.jsonl").is_file()
    assert (tmp_path / "queries.jsonl").is_file()
    assert (tmp_path / "qrels.jsonl").is_file()

    reloaded = BenchmarkDataset.load_from_jsonl(
        dataset_dir=tmp_path,
        name="synthetic_test",
        description="Synthetic test benchmark dataset",
    )

    assert reloaded.name == dataset.name
    assert len(reloaded.documents) == 1
    assert reloaded.documents[0].id == "doc_101"
    assert reloaded.documents[0].title == "Agreement 101"
    assert reloaded.documents[0].metadata["parties"] == ["Party A", "Party B"]

    assert len(reloaded.queries) == 1
    assert reloaded.queries[0].id == "q_101"

    assert len(reloaded.ground_truths) == 1
    assert reloaded.ground_truths[0].query_id == "q_101"
    assert reloaded.ground_truths[0].relevant_doc_ids == ["doc_101"]
    assert len(reloaded.ground_truths[0].spans) == 1
    assert reloaded.ground_truths[0].spans[0].start_char == 5


def test_get_ground_truth_lookup() -> None:
    """Test get_ground_truth helper method."""
    gt1 = GroundTruth(query_id="q1", relevant_doc_ids=["d1"])
    gt2 = GroundTruth(query_id="q2", relevant_doc_ids=["d2"])

    dataset = BenchmarkDataset(
        name="test",
        description="test",
        documents=[],
        queries=[],
        ground_truths=[gt1, gt2],
    )

    assert dataset.get_ground_truth("q1") == gt1
    assert dataset.get_ground_truth("q2") == gt2
    assert dataset.get_ground_truth("nonexistent") is None
