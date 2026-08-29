"""BEIR/FiQA financial domain IR dataset parser and normalizer."""

from collections.abc import Callable
from pathlib import Path
from typing import cast

import datasets

from rag_eval.datasets.base import BenchmarkDataset, get_split_rows, row_to_dict
from rag_eval.schemas import Document, GroundTruth, MetadataValue, Query

_load_dataset = cast(Callable[..., object], datasets.load_dataset)


def download_beir_fiqa(output_dir: Path) -> BenchmarkDataset:
    """Download FiQA financial dataset from Hugging Face and normalize into BenchmarkDataset."""
    try:
        corpus_obj = _load_dataset("mteb/fiqa", "corpus")
        queries_obj = _load_dataset("mteb/fiqa", "queries")
        qrels_obj = _load_dataset("mteb/fiqa", "default")
    except (RuntimeError, ValueError, OSError, FileNotFoundError):
        corpus_obj = _load_dataset("BeIR/fiqa", "corpus")
        queries_obj = _load_dataset("BeIR/fiqa", "queries")
        qrels_obj = _load_dataset("BeIR/fiqa-qrels")

    corpus_rows = get_split_rows(corpus_obj, "corpus")
    queries_rows = get_split_rows(queries_obj, "queries")
    qrels_rows = get_split_rows(qrels_obj, "test")

    documents: list[Document] = []
    for raw_row in corpus_rows:
        row = row_to_dict(raw_row)
        if not row:
            continue
        doc_id = str(row.get("_id", "")).strip()
        title = str(row.get("title", "")).strip()
        text = str(row.get("text", "")).strip()
        if doc_id and text:
            metadata: dict[str, MetadataValue] = {
                "title": title,
                "category": "financial_qa",
            }
            documents.append(
                Document(
                    id=doc_id,
                    text=text,
                    title=title if title else None,
                    metadata=metadata,
                )
            )

    qrels_map: dict[str, list[str]] = {}
    for raw_row in qrels_rows:
        row = row_to_dict(raw_row)
        if not row:
            continue
        raw_q_id = row.get("query-id") if "query-id" in row else row.get("query_id")
        raw_c_id = row.get("corpus-id") if "corpus-id" in row else row.get("corpus_id")
        q_id = str(raw_q_id if raw_q_id is not None else "").strip()
        c_id = str(raw_c_id if raw_c_id is not None else "").strip()
        score_val = row.get("score", 1)
        score = int(cast(int | str, score_val)) if score_val is not None else 1
        if score > 0 and q_id and c_id:
            if q_id not in qrels_map:
                qrels_map[q_id] = []
            if c_id not in qrels_map[q_id]:
                qrels_map[q_id].append(c_id)

    queries: list[Query] = []
    ground_truths: list[GroundTruth] = []
    for raw_row in queries_rows:
        row = row_to_dict(raw_row)
        if not row:
            continue
        q_id = str(row.get("_id", "")).strip()
        q_text = str(row.get("text", "")).strip()
        # Retain only active benchmark test queries present in qrels
        if q_id in qrels_map and q_text:
            rel_docs = qrels_map[q_id]
            queries.append(
                Query(id=q_id, text=q_text, metadata={"category": "financial_query"})
            )
            ground_truths.append(
                GroundTruth(
                    query_id=q_id,
                    relevant_doc_ids=rel_docs,
                    answers=[],
                    spans=[],
                )
            )

    benchmark = BenchmarkDataset(
        name="beir_fiqa",
        description="BEIR / FiQA financial question answering and retrieval dataset",
        documents=documents,
        queries=queries,
        ground_truths=ground_truths,
    )

    _ = benchmark.partition_and_export(output_dir)
    return benchmark


def parse_beir_fiqa_from_disk(data_dir: Path, split: str = "dev") -> BenchmarkDataset:
    """Parse local FiQA dataset from open dev JSONL or sealed holdout binary vault."""
    if split.lower() in ("test", "holdout"):
        vault_file = data_dir / ".holdout_vault" / "beir_fiqa.vault"
        if vault_file.is_file():
            return BenchmarkDataset.load_sealed_holdout(vault_file)
    dev_dir = (
        data_dir / "dev" / "beir_fiqa"
        if (data_dir / "dev" / "beir_fiqa").is_dir()
        else data_dir / "beir_fiqa"
    )
    return BenchmarkDataset.load_from_jsonl(
        dataset_dir=dev_dir,
        name="beir_fiqa",
        description="BEIR / FiQA financial question answering and retrieval dataset",
    )
