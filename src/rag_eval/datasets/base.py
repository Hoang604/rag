"""Unified benchmark dataset container and parser interface."""

import hashlib
import random
import struct
import zlib
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import ClassVar, cast

from pydantic import BaseModel, ConfigDict

from rag_eval.schemas import Document, GroundTruth, Query

VAULT_MAGIC = b"RAGV"
VAULT_VERSION = 1


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

    def export_sealed_holdout(self, vault_file: Path) -> None:
        """Serialize queries, ground_truths, and document corpus into compressed binary vault.

        Binary Structure:
            [4 bytes Magic: b'RAGV']
            [4 bytes Version: uint32 (1)]
            [4 bytes Compressed Payload Length: uint32]
            [32 bytes SHA256 payload checksum]
            [8 bytes Uncompressed Payload Length: uint64]
            [Variable Zlib-compressed JSON payload]
        """
        vault_file.parent.mkdir(parents=True, exist_ok=True)
        raw_json_str = self.model_dump_json()
        raw_bytes = raw_json_str.encode("utf-8")
        uncompressed_len = len(raw_bytes)
        checksum = hashlib.sha256(raw_bytes).digest()
        compressed_payload = zlib.compress(raw_bytes, level=9)

        header = struct.pack(">4sII32sQ", VAULT_MAGIC, VAULT_VERSION, len(compressed_payload), checksum, uncompressed_len)
        with vault_file.open("wb") as f:
            f.write(header)
            f.write(compressed_payload)

    @classmethod
    def load_sealed_holdout(cls, vault_file: Path) -> "BenchmarkDataset":
        """Deserialize a sealed binary holdout vault into an in-memory BenchmarkDataset.

        Args:
            vault_file: Path to <dataset>.vault binary container.

        Returns:
            Validated BenchmarkDataset instance.

        Raises:
            FileNotFoundError: If vault_file does not exist.
            ValueError: If magic bytes, version, payload size, or SHA256 checksum validation fails.
        """
        if not vault_file.is_file():
            msg = f"Holdout vault file not found: {vault_file}"
            raise FileNotFoundError(msg)

        header_size = struct.calcsize(">4sII32sQ")
        with vault_file.open("rb") as f:
            header_bytes = f.read(header_size)
            if len(header_bytes) < header_size:
                msg = f"Invalid vault header in {vault_file}"
                raise ValueError(msg)

            magic, version, compressed_len, expected_checksum, uncompressed_len = struct.unpack(">4sII32sQ", header_bytes)
            if magic != VAULT_MAGIC:
                msg = f"Invalid vault magic header: expected {VAULT_MAGIC!r}, got {magic!r}"
                raise ValueError(msg)
            if version != VAULT_VERSION:
                msg = f"Unsupported vault version: {version}"
                raise ValueError(msg)

            compressed_payload = f.read(compressed_len)
            if len(compressed_payload) != compressed_len:
                msg = f"Truncated vault payload in {vault_file}"
                raise ValueError(msg)

        try:
            raw_bytes = zlib.decompress(compressed_payload)
        except (zlib.error, ValueError) as err:
            msg = f"Failed to decompress vault payload in {vault_file}: {err}"
            raise ValueError(msg) from err

        if len(raw_bytes) != uncompressed_len:
            msg = f"Decompressed payload size mismatch: expected {uncompressed_len}, got {len(raw_bytes)}"
            raise ValueError(msg)

        actual_checksum = hashlib.sha256(raw_bytes).digest()
        if actual_checksum != expected_checksum:
            msg = f"Holdout vault SHA256 checksum mismatch in {vault_file}"
            raise ValueError(msg)

        raw_json_str = raw_bytes.decode("utf-8")
        return cls.model_validate_json(raw_json_str)

    def partition_and_export(
        self,
        base_output_dir: Path,
        dev_ratio: float = 0.20,
        seed: int = 42,
    ) -> tuple[Path, Path]:
        """Partition queries and ground truths into open dev split and sealed holdout test split.

        Args:
            base_output_dir: Target data root directory (e.g., ./data).
            dev_ratio: Ratio of queries assigned to open development split (default: 0.20).
            seed: Deterministic random seed for stable partitioning.

        Returns:
            Tuple of (dev_directory_path, holdout_vault_file_path).
        """
        if not (0.0 < dev_ratio < 1.0):
            msg = f"dev_ratio must be between 0.0 and 1.0 (exclusive), got {dev_ratio}"
            raise ValueError(msg)

        if not self.queries:
            msg = f"Cannot partition dataset '{self.name}' with empty queries."
            raise ValueError(msg)

        gt_lookup = {gt.query_id: gt for gt in self.ground_truths}

        indexed_queries = list(self.queries)
        rng = random.Random(seed)
        shuffled_indices = list(range(len(indexed_queries)))
        rng.shuffle(shuffled_indices)

        dev_count = max(1, int(len(indexed_queries) * dev_ratio))
        dev_indices = set(shuffled_indices[:dev_count])

        dev_queries: list[Query] = []
        dev_gts: list[GroundTruth] = []
        test_queries: list[Query] = []
        test_gts: list[GroundTruth] = []

        for idx, query in enumerate(indexed_queries):
            gt = gt_lookup.get(query.id)
            if idx in dev_indices:
                dev_queries.append(query)
                if gt is not None:
                    dev_gts.append(gt)
            else:
                test_queries.append(query)
                if gt is not None:
                    test_gts.append(gt)

        dev_dataset = BenchmarkDataset(
            name=self.name,
            description=f"{self.description} (Dev Split)",
            documents=self.documents,
            queries=dev_queries,
            ground_truths=dev_gts,
        )
        dev_dir = base_output_dir / "dev" / self.name
        dev_dataset.export_to_jsonl(dev_dir)

        test_dataset = BenchmarkDataset(
            name=self.name,
            description=f"{self.description} (Sealed Holdout Test Split)",
            documents=self.documents,
            queries=test_queries,
            ground_truths=test_gts,
        )
        vault_file = base_output_dir / ".holdout_vault" / f"{self.name}.vault"
        test_dataset.export_sealed_holdout(vault_file)

        return dev_dir, vault_file

    @classmethod
    def load_from_jsonl(cls, dataset_dir: Path, name: str, description: str) -> "BenchmarkDataset":
        """Load a standardized dataset from a local directory containing JSONL files."""
        docs_file = dataset_dir / "documents.jsonl"
        queries_file = dataset_dir / "queries.jsonl"
        qrels_file = dataset_dir / "qrels.jsonl"

        if not (docs_file.is_file() and queries_file.is_file() and qrels_file.is_file()):
            dev_subdir = dataset_dir / "dev" / name
            if dev_subdir.is_dir():
                docs_file = dev_subdir / "documents.jsonl"
                queries_file = dev_subdir / "queries.jsonl"
                qrels_file = dev_subdir / "qrels.jsonl"
            elif (dataset_dir / name / "documents.jsonl").is_file():
                docs_file = dataset_dir / name / "documents.jsonl"
                queries_file = dataset_dir / name / "queries.jsonl"
                qrels_file = dataset_dir / name / "qrels.jsonl"

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
