"""Unified benchmark dataset container and parser interface."""

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import ClassVar, cast

from pydantic import BaseModel, ConfigDict

from rag_eval.schemas import Document, GroundTruth, Query


def row_to_dict(raw_row: object) -> dict[str, object]:
    """Safely convert a dataset row into a string-keyed dictionary."""
    if isinstance(raw_row, Mapping):
        return {str(k): v for k, v in cast(Mapping[object, object], raw_row).items()}
    return {}


def get_split_rows(data: object, split_name: str) -> list[object]:
    """Extract rows from a dataset split as a concrete list of objects."""
    if isinstance(data, Mapping):
        mapping_data = cast(Mapping[str, object], data)
        target: object = mapping_data.get(split_name)
        if isinstance(target, Iterable):
            return list(target)
        if mapping_data:
            first_val: object = next(iter(mapping_data.values()))
            if isinstance(first_val, Iterable):
                return list(first_val)
    elif isinstance(data, Iterable):
        return list(data)
    return []


class BenchmarkDataset(BaseModel):
    """Standardized in-memory container representing a loaded RAG benchmark."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    name: str
    description: str
    documents: list[Document]
    queries: list[Query]
    ground_truths: list[GroundTruth]

    def get_ground_truth(self, query_id: str) -> GroundTruth | None:
        """Lookup ground truth for a given query identifier."""
        for gt in self.ground_truths:
            if gt.query_id == query_id:
                return gt
        return None

    def export_to_jsonl(self, output_dir: Path) -> None:
        """Export standardized documents.jsonl, queries.jsonl, and qrels.jsonl to disk."""
        output_dir.mkdir(parents=True, exist_ok=True)

        docs_file = output_dir / "documents.jsonl"
        with docs_file.open("w", encoding="utf-8") as f:
            for doc in self.documents:
                _ = f.write(doc.model_dump_json() + "\n")

        queries_file = output_dir / "queries.jsonl"
        with queries_file.open("w", encoding="utf-8") as f:
            for query in self.queries:
                _ = f.write(query.model_dump_json() + "\n")

        qrels_file = output_dir / "qrels.jsonl"
        with qrels_file.open("w", encoding="utf-8") as f:
            for gt in self.ground_truths:
                _ = f.write(gt.model_dump_json() + "\n")

    @classmethod
    def load_from_jsonl(cls, dataset_dir: Path, name: str, description: str) -> "BenchmarkDataset":
        """Load a standardized dataset from a local directory containing JSONL files."""
        docs_file = dataset_dir / "documents.jsonl"
        queries_file = dataset_dir / "queries.jsonl"
        qrels_file = dataset_dir / "qrels.jsonl"

        if not docs_file.is_file() or not queries_file.is_file() or not qrels_file.is_file():
            msg = f"Missing JSONL files in directory: {dataset_dir}"
            raise FileNotFoundError(msg)

        documents: list[Document] = []
        with docs_file.open("r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped:
                    documents.append(Document.model_validate_json(stripped))

        queries: list[Query] = []
        with queries_file.open("r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped:
                    queries.append(Query.model_validate_json(stripped))

        ground_truths: list[GroundTruth] = []
        with qrels_file.open("r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped:
                    ground_truths.append(GroundTruth.model_validate_json(stripped))

        return cls(
            name=name,
            description=description,
            documents=documents,
            queries=queries,
            ground_truths=ground_truths,
        )
