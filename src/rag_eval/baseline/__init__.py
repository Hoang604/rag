"""Baseline RAG retrieval and indexing components."""

from rag_eval.baseline.bm25 import BM25Index, tokenize
from rag_eval.baseline.chunking import DocumentChunk, chunk_documents, chunk_text
from rag_eval.baseline.dense import DenseCandidateScorer
from rag_eval.baseline.pipeline import (
    compute_rrf_ranks,
    export_predictions,
    run_baseline_retrieval,
    select_query_subset,
)

__all__ = [
    "BM25Index",
    "DenseCandidateScorer",
    "DocumentChunk",
    "chunk_documents",
    "chunk_text",
    "compute_rrf_ranks",
    "export_predictions",
    "run_baseline_retrieval",
    "select_query_subset",
    "tokenize",
]
