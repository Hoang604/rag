"""End-to-end baseline RAG pipeline with stage-by-stage timing instrumentation."""

import json
import random
import time
from pathlib import Path
from typing import Literal

from rich.console import Console
from tqdm import tqdm

from rag_eval.baseline.bm25 import BM25Index
from rag_eval.baseline.chunking import DocumentChunk, chunk_documents
from rag_eval.baseline.dense import CandidateScorer, DenseCandidateScorer
from rag_eval.schemas import Document, PredictionResult, Query

console = Console()


def select_query_subset(
    queries: list[Query],
    max_queries: int | None = None,
    seed: int | None = None,
) -> list[Query]:
    """Select a head slice or seeded pseudo-random sample of queries."""
    if max_queries is None or max_queries >= len(queries):
        return queries
    if max_queries <= 0:
        msg = f"max_queries must be positive, got {max_queries}"
        raise ValueError(msg)
    if seed is not None:
        rng = random.Random(seed)
        return rng.sample(queries, max_queries)
    return queries[:max_queries]


def compute_rrf_ranks(scores: list[float]) -> dict[int, int]:
    """Compute 1-indexed ranks from raw scores (highest score -> rank 1)."""
    scored_indices = [(idx, score) for idx, score in enumerate(scores) if score > 0.0]
    scored_indices.sort(key=lambda item: item[1], reverse=True)
    return {idx: rank + 1 for rank, (idx, _) in enumerate(scored_indices)}


def run_baseline_retrieval(
    documents: list[Document],
    queries: list[Query],
    top_k: int = 10,
    chunk_size: int = 512,
    chunk_overlap: int = 64,
    max_queries: int | None = None,
    seed: int | None = None,
    mode: Literal["bm25", "dense", "hybrid"] = "hybrid",
    dense_model_name: str = "BAAI/bge-small-en-v1.5",
    candidate_pool_size: int = 150,
    show_progress: bool = True,
    rrf_k: int = 20,
    dense_weight: float = 2.0,
    bm25_weight: float = 1.0,
    dense_scorer: CandidateScorer | None = None,
) -> list[PredictionResult]:
    """Execute high-speed two-stage retrieval with detailed stage latency logging."""
    if not documents:
        msg = "Cannot run baseline retrieval with empty document corpus."
        raise ValueError(msg)

    target_queries = select_query_subset(queries=queries, max_queries=max_queries, seed=seed)

    # Stage 1: Text Chunking
    t_chunk_start = time.perf_counter()
    chunks: list[DocumentChunk] = chunk_documents(
        documents=documents,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    chunk_ms = (time.perf_counter() - t_chunk_start) * 1000.0
    console.print(f"[cyan][Stage 1: Chunking][/cyan] Split {len(documents)} documents into {len(chunks)} chunks in [bold]{chunk_ms:.2f}ms[/bold]")

    chunk_texts = [c.text for c in chunks]

    # Stage 2: Sparse Inverted Index
    t_bm25_start = time.perf_counter()
    bm25_index = BM25Index(corpus=chunk_texts)
    bm25_idx_ms = (time.perf_counter() - t_bm25_start) * 1000.0
    console.print(f"[cyan][Stage 2: BM25 Indexing][/cyan] Built sparse postings for {len(chunks)} chunks in [bold]{bm25_idx_ms:.2f}ms[/bold]")

    # Stage 3: Dense Model Instantiation
    active_dense_scorer: CandidateScorer | None = dense_scorer
    if mode in ("dense", "hybrid") and active_dense_scorer is None:
        t_dense_init = time.perf_counter()
        active_dense_scorer = DenseCandidateScorer(model_name=dense_model_name)
        dense_init_ms = (time.perf_counter() - t_dense_init) * 1000.0
        console.print(f"[cyan][Stage 3: Dense Init][/cyan] Initialized {dense_model_name} in [bold]{dense_init_ms:.2f}ms[/bold]")

    results: list[PredictionResult] = []

    iterator = target_queries
    if show_progress:
        iterator = tqdm(
            target_queries,
            desc=f"Retrieving {len(target_queries)} queries ({mode.upper()})",
            unit="query",
        )

    for q_idx, q in enumerate(iterator):
        q_start = time.perf_counter()
        doc_scores: dict[str, float] = {}

        # Query Step A: BM25 candidate lookup
        t_bm25_q = time.perf_counter()
        bm25_scores = bm25_index.get_scores(q.text)
        bm25_q_ms = (time.perf_counter() - t_bm25_q) * 1000.0

        if mode == "bm25":
            for chunk_idx, score in enumerate(bm25_scores):
                if score <= 0.0:
                    continue
                parent_id = chunks[chunk_idx].doc_id
                if parent_id not in doc_scores or score > doc_scores[parent_id]:
                    doc_scores[parent_id] = score

        elif mode in ("dense", "hybrid"):
            assert active_dense_scorer is not None
            # Query Step B: Candidate Filtering
            t_cand = time.perf_counter()
            scored_candidates = [
                (idx, score) for idx, score in enumerate(bm25_scores) if score > 0.0
            ]
            scored_candidates.sort(key=lambda item: item[1], reverse=True)
            top_candidates = scored_candidates[:candidate_pool_size]

            if not top_candidates:
                top_candidates = [(i, 0.0) for i in range(min(candidate_pool_size, len(chunks)))]

            cand_indices = [idx for idx, _ in top_candidates]
            cand_texts = [chunk_texts[idx] for idx in cand_indices]
            cand_filter_ms = (time.perf_counter() - t_cand) * 1000.0

            # Query Step C: Dense Transformer Embedding on Candidate Slice
            dense_cand_scores, dense_emb_ms = active_dense_scorer.score_candidates(
                q.text, cand_texts, log_timings=(len(target_queries) <= 3)
            )

            # Query Step D: Fusion & Parent Doc Pooling
            t_fuse = time.perf_counter()
            if mode == "dense":
                for local_pos, chunk_idx in enumerate(cand_indices):
                    score = dense_cand_scores[local_pos]
                    if score <= 0.0:
                        continue
                    parent_id = chunks[chunk_idx].doc_id
                    if parent_id not in doc_scores or score > doc_scores[parent_id]:
                        doc_scores[parent_id] = score

            elif mode == "hybrid":
                bm25_cand_scores = [score for _, score in top_candidates]
                bm25_ranks = compute_rrf_ranks(bm25_cand_scores)
                dense_ranks = compute_rrf_ranks(dense_cand_scores)

                for local_pos, chunk_idx in enumerate(cand_indices):
                    rrf_score = 0.0
                    if local_pos in bm25_ranks:
                        rrf_score += bm25_weight / float(rrf_k + bm25_ranks[local_pos])
                    if local_pos in dense_ranks:
                        rrf_score += dense_weight / float(rrf_k + dense_ranks[local_pos])

                    parent_id = chunks[chunk_idx].doc_id
                    if parent_id not in doc_scores or rrf_score > doc_scores[parent_id]:
                        doc_scores[parent_id] = rrf_score

            fuse_ms = (time.perf_counter() - t_fuse) * 1000.0

            if len(target_queries) <= 3:
                num_cands = len(cand_indices)
                console.print(
                    f"[dim]  [Query {q_idx+1}/{len(target_queries)}] BM25 Search: {bm25_q_ms:.2f}ms | Candidate Filter ({num_cands}): {cand_filter_ms:.2f}ms | Dense Embedding: {dense_emb_ms:.2f}ms | RRF Fusion: {fuse_ms:.2f}ms[/dim]"
                )

        # Sort documents by descending aggregated score
        sorted_docs = sorted(doc_scores.items(), key=lambda item: item[1], reverse=True)
        retrieved_ids = [doc_id for doc_id, _ in sorted_docs[:top_k]]

        total_q_ms = (time.perf_counter() - q_start) * 1000.0

        results.append(
            PredictionResult(
                query_id=q.id,
                retrieved_doc_ids=retrieved_ids,
                generated_answer=None,
                latency_ms=round(total_q_ms, 3),
                metadata={"retriever": f"{mode}_baseline", "top_k": str(top_k)},
            )
        )

    return results


def export_predictions(
    predictions: list[PredictionResult],
    output_path: Path,
) -> None:
    """Save predictions to JSON or JSONL file on disk."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.suffix.lower() == ".jsonl":
        with output_path.open("w", encoding="utf-8") as f:
            for pred in predictions:
                _ = f.write(pred.model_dump_json() + "\n")
    else:
        with output_path.open("w", encoding="utf-8") as f:
            records = [pred.model_dump(mode="json") for pred in predictions]
            _ = f.write(json.dumps(records, indent=2))
