"""Unit tests for baseline chunking, BM25 indexing, and retrieval pipeline."""

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

import pytest

from rag_eval.baseline.bm25 import BM25Index, tokenize
from rag_eval.baseline.chunking import chunk_documents, chunk_text
from rag_eval.baseline.dense import DenseCandidateScorer
from rag_eval.baseline.pipeline import (
    compute_rrf_ranks,
    export_predictions,
    run_baseline_retrieval,
    select_query_subset,
)
from rag_eval.schemas import Document, PredictionResult, Query


def test_tokenize_normalization() -> None:
    """Tokenize normalizes words, discards punctuation, and optionally removes stopwords and stems terms."""
    raw_unfiltered = tokenize(
        "The quick brown Fox, jumps over 42 lazy dogs!",
        stem=False,
        include_bigrams=False,
        filter_stopwords=False,
    )
    assert raw_unfiltered == ["the", "quick", "brown", "fox", "jumps", "over", "42", "lazy", "dogs"]

    filtered_stemmed = tokenize(
        "The quick brown Fox, jumps over 42 lazy dogs!",
        stem=True,
        include_bigrams=False,
        filter_stopwords=True,
    )
    assert filtered_stemmed == ["quick", "brown", "fox", "jump", "42", "lazi", "dog"]

    stemmed_with_bigrams = tokenize(
        "The quick brown Fox, jumps over 42 lazy dogs!",
        stem=True,
        include_bigrams=True,
        filter_stopwords=True,
    )
    assert "jump_42" in stemmed_with_bigrams
    assert "quick_brown" in stemmed_with_bigrams


def test_chunk_text_boundaries() -> None:
    """Sliding window creates expected chunk lengths and overlaps."""
    text = "A" * 1000
    chunks = chunk_text(text=text, doc_id="doc_1", chunk_size=500, chunk_overlap=100)
    assert len(chunks) == 3
    assert chunks[0].start_char == 0
    assert chunks[0].end_char == 500
    assert chunks[1].start_char == 400
    assert chunks[1].end_char == 900
    assert chunks[2].start_char == 800
    assert chunks[2].end_char == 1000
    assert chunks[0].doc_id == "doc_1"


def test_chunk_text_invalid_params() -> None:
    """Invalid chunk parameters raise ValueError."""
    with pytest.raises(ValueError, match="chunk_size must be positive"):
        _ = chunk_text("sample", "doc_1", chunk_size=0)

    with pytest.raises(ValueError, match="chunk_overlap must be in range"):
        _ = chunk_text("sample", "doc_1", chunk_size=100, chunk_overlap=100)


def test_chunk_documents_multiple() -> None:
    """Chunking multiple documents maintains parent doc ids."""
    docs = [
        Document(id="doc_a", text="Short text A"),
        Document(id="doc_b", text="Short text B"),
    ]
    chunks = chunk_documents(docs, chunk_size=100, chunk_overlap=10)
    assert len(chunks) == 2
    assert chunks[0].doc_id == "doc_a"
    assert chunks[1].doc_id == "doc_b"


def test_bm25_ranking_accuracy() -> None:
    """BM25 ranks documents containing matching terms highest."""
    corpus = [
        "Machine learning is a subset of artificial intelligence.",
        "Photosynthesis is the process used by plants to convert light energy.",
        "Artificial intelligence and deep artificial intelligence models drive modern research.",
    ]
    index = BM25Index(corpus=corpus)
    scores = index.get_scores("artificial intelligence")
    assert len(scores) == 3
    assert scores[0] > 0.0
    assert scores[2] > scores[0]
    assert scores[1] == 0.0


def test_compute_rrf_ranks() -> None:
    """RRF rank calculation assigns highest rank to top scores."""
    ranks = compute_rrf_ranks([0.1, 0.9, 0.0, 0.5])
    assert ranks[1] == 1  # 0.9 -> rank 1
    assert ranks[3] == 2  # 0.5 -> rank 2
    assert ranks[0] == 3  # 0.1 -> rank 3
    assert 2 not in ranks  # 0.0 excluded


class MockCandidateScorer:
    """Zero-overhead in-memory candidate scorer for sub-millisecond unit testing."""

    def score_candidates(
        self,
        query: str,
        candidate_texts: Sequence[str],
        log_timings: bool = True,
    ) -> tuple[list[float], float]:
        """Compute keyword-overlap similarity scores instantly in memory."""
        del log_timings
        scores: list[float] = []
        q_lower = query.lower()
        for text in candidate_texts:
            t_lower = text.lower()
            score = sum(1.0 for word in q_lower.split() if word in t_lower)
            scores.append(score)
        return scores, 0.01


@pytest.mark.slow
def test_dense_candidate_scorer() -> None:
    """Dense candidate scorer computes semantic similarity on candidate subsets."""
    scorer = DenseCandidateScorer()
    scores, emb_ms = scorer.score_candidates(
        query="How to terminate a legal agreement?",
        candidate_texts=[
            "Legal contract termination and cancellation clauses.",
            "Biomedical RNA gene sequencing and laboratory methods.",
        ],
    )
    assert len(scores) == 2
    assert scores[0] > scores[1]
    assert emb_ms >= 0.0


def test_select_query_subset() -> None:
    """Query subset selection supports sequential slicing and seeded sampling."""
    queries = [Query(id=f"q_{i}", text=f"Query {i}") for i in range(10)]

    # None returns all
    assert len(select_query_subset(queries, max_queries=None)) == 10

    # Sequential head slicing
    head_subset = select_query_subset(queries, max_queries=3)
    assert len(head_subset) == 3
    assert [q.id for q in head_subset] == ["q_0", "q_1", "q_2"]

    # Seeded sampling (reproducible)
    sample_a = select_query_subset(queries, max_queries=4, seed=42)
    sample_b = select_query_subset(queries, max_queries=4, seed=42)
    assert len(sample_a) == 4
    assert [q.id for q in sample_a] == [q.id for q in sample_b]

    # Invalid max_queries raises ValueError
    with pytest.raises(ValueError, match="max_queries must be positive"):
        _ = select_query_subset(queries, max_queries=0)


def test_run_baseline_retrieval_hybrid_mode() -> None:
    """End-to-end baseline retrieval supports two-stage hybrid mode with injected CandidateScorer."""
    docs = [
        Document(id="doc_law", text="Termination for convenience requires thirty days written notice.", title="Contract"),
        Document(id="doc_bio", text="CRISPR Cas9 enables targeted RNA and DNA genetic editing.", title="Genetics"),
        Document(id="doc_fin", text="Quarterly dividend yield increased by fifteen percent year over year.", title="Finance"),
    ]
    queries = [
        Query(id="q_1", text="What is the notice period for contract cancellation?"),
        Query(id="q_2", text="How does RNA gene editing operate?"),
    ]

    mock_scorer = MockCandidateScorer()

    preds = run_baseline_retrieval(
        documents=docs,
        queries=queries,
        top_k=2,
        chunk_size=100,
        chunk_overlap=20,
        max_queries=2,
        mode="hybrid",
        candidate_pool_size=5,
        dense_scorer=mock_scorer,
    )
    assert len(preds) == 2
    assert preds[0].query_id == "q_1"
    assert "doc_law" in preds[0].retrieved_doc_ids
    assert preds[1].query_id == "q_2"
    assert "doc_bio" in preds[1].retrieved_doc_ids


def test_custom_scorer_injection() -> None:
    """Custom CandidateScorer returning zero scores is safely handled in hybrid RRF."""
    docs = [Document(id="d1", text="Alpha beta gamma")]
    queries = [Query(id="q1", text="Alpha")]

    class ZeroScorer:
        def score_candidates(
            self,
            query: str,
            candidate_texts: Sequence[str],
            log_timings: bool = True,
        ) -> tuple[list[float], float]:
            del query, log_timings
            return [0.0] * len(candidate_texts), 0.0

    preds = run_baseline_retrieval(
        documents=docs,
        queries=queries,
        mode="hybrid",
        dense_scorer=ZeroScorer(),
    )
    assert len(preds) == 1
    assert preds[0].retrieved_doc_ids == ["d1"]


def test_dense_mode_only_mocked() -> None:
    """Pure dense mode runs candidate scorer directly."""
    docs = [
        Document(id="d_target", text="Quantum mechanics computing qubit"),
        Document(id="d_other", text="Culinary recipes and baking bread"),
    ]
    queries = [Query(id="q1", text="Quantum computing")]

    preds = run_baseline_retrieval(
        documents=docs,
        queries=queries,
        mode="dense",
        dense_scorer=MockCandidateScorer(),
    )
    assert len(preds) == 1
    assert "d_target" in preds[0].retrieved_doc_ids


def test_export_predictions_json_and_jsonl(tmp_path: Path) -> None:
    """Predictions export properly in both JSON and JSONL formats."""
    preds = [
        PredictionResult(query_id="q_1", retrieved_doc_ids=["doc_1", "doc_2"], latency_ms=1.23),
        PredictionResult(query_id="q_2", retrieved_doc_ids=["doc_3"], latency_ms=0.45),
    ]

    # JSONL Export
    jsonl_path = tmp_path / "preds.jsonl"
    export_predictions(preds, jsonl_path)
    assert jsonl_path.is_file()
    with jsonl_path.open("r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
        assert len(lines) == 2
        p0 = PredictionResult.model_validate_json(lines[0])
        assert p0.query_id == "q_1"
        assert p0.retrieved_doc_ids == ["doc_1", "doc_2"]

    # JSON Export
    json_path = tmp_path / "preds.json"
    export_predictions(preds, json_path)
    assert json_path.is_file()
    with json_path.open("r", encoding="utf-8") as f:
        raw_json: object = cast(object, json.loads(f.read()))
        assert isinstance(raw_json, list)
        loaded = cast(list[object], raw_json)
        assert len(loaded) == 2
        first_item = loaded[0]
        assert isinstance(first_item, Mapping)
        first_dict = cast(Mapping[str, object], first_item)
        assert first_dict["query_id"] == "q_1"
