"""Unit tests for BenchmarkDataset JSONL and sealed binary vault serialization."""

from pathlib import Path

import pytest

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


def test_benchmark_dataset_sealed_vault_roundtrip(tmp_path: Path) -> None:
    """Test serializing and deserializing BenchmarkDataset via sealed binary vault."""
    doc = Document(id="d1", text="Sample document text", title="Doc 1")
    query = Query(id="q1", text="Sample query")
    gt = GroundTruth(query_id="q1", relevant_doc_ids=["d1"], answers=["Sample answer"])

    dataset = BenchmarkDataset(
        name="vault_test",
        description="Vault test dataset",
        documents=[doc],
        queries=[query],
        ground_truths=[gt],
    )

    vault_file = tmp_path / "vault_test.vault"
    dataset.export_sealed_holdout(vault_file)

    assert vault_file.is_file()
    # Ensure file is binary and contains magic bytes
    with vault_file.open("rb") as f:
        header = f.read(4)
        assert header == b"RAGV"

    reloaded = BenchmarkDataset.load_sealed_holdout(vault_file)
    assert reloaded.name == dataset.name
    assert len(reloaded.documents) == 1
    assert reloaded.documents[0].id == "d1"
    assert len(reloaded.queries) == 1
    assert reloaded.queries[0].id == "q1"
    assert len(reloaded.ground_truths) == 1
    assert reloaded.ground_truths[0].answers == ["Sample answer"]


def test_tampered_holdout_vault_fails(tmp_path: Path) -> None:
    """Test that tampering with vault payload bytes raises ValueError on load."""
    doc = Document(id="d1", text="Sample document text")
    query = Query(id="q1", text="Sample query")
    gt = GroundTruth(query_id="q1", relevant_doc_ids=["d1"])

    dataset = BenchmarkDataset(
        name="tamper_test",
        description="Tamper test dataset",
        documents=[doc],
        queries=[query],
        ground_truths=[gt],
    )

    vault_file = tmp_path / "tamper_test.vault"
    dataset.export_sealed_holdout(vault_file)

    # Tamper with the binary content
    raw_bytes = bytearray(vault_file.read_bytes())
    raw_bytes[-5] = (raw_bytes[-5] + 1) % 256
    vault_file.write_bytes(bytes(raw_bytes))

    with pytest.raises(ValueError):
        _ = BenchmarkDataset.load_sealed_holdout(vault_file)


def test_partition_and_export_disjointness(tmp_path: Path) -> None:
    """Test that partitioning creates disjoint dev/test queries and shared documents."""
    docs = [Document(id=f"doc_{i}", text=f"Doc text {i}") for i in range(5)]
    queries = [Query(id=f"q_{i}", text=f"Query text {i}") for i in range(10)]
    gts = [GroundTruth(query_id=f"q_{i}", relevant_doc_ids=[f"doc_{i % 5}"]) for i in range(10)]

    dataset = BenchmarkDataset(
        name="partition_test",
        description="Partition test",
        documents=docs,
        queries=queries,
        ground_truths=gts,
    )

    dev_dir, vault_file = dataset.partition_and_export(tmp_path, dev_ratio=0.30, seed=42)

    assert dev_dir.is_dir()
    assert vault_file.is_file()

    dev_ds = BenchmarkDataset.load_from_jsonl(dev_dir, "partition_test", "dev")
    test_ds = BenchmarkDataset.load_sealed_holdout(vault_file)

    assert len(dev_ds.documents) == 5
    assert len(test_ds.documents) == 5

    dev_qids = {q.id for q in dev_ds.queries}
    test_qids = {q.id for q in test_ds.queries}

    assert len(dev_qids) == 3
    assert len(test_qids) == 7
    assert dev_qids.isdisjoint(test_qids)
    assert dev_qids.union(test_qids) == {q.id for q in queries}


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
