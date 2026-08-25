"""Dataset loaders and parsers."""

from rag_eval.datasets.base import BenchmarkDataset
from rag_eval.datasets.beir_fiqa import download_beir_fiqa, parse_beir_fiqa_from_disk
from rag_eval.datasets.cuad import download_cuad, parse_cuad_from_disk
from rag_eval.datasets.qasper import download_qasper, parse_qasper_from_disk
from rag_eval.datasets.scifact import download_scifact, parse_scifact_from_disk

__all__ = [
    "BenchmarkDataset",
    "download_beir_fiqa",
    "download_cuad",
    "download_qasper",
    "download_scifact",
    "parse_beir_fiqa_from_disk",
    "parse_cuad_from_disk",
    "parse_qasper_from_disk",
    "parse_scifact_from_disk",
]
