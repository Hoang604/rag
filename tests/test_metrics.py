"""Unit tests for mathematical accuracy of IR and generation metrics."""

import math

import pytest

from rag_eval.metrics import (
    EvaluationError,
    calculate_exact_match,
    calculate_hit_rate,
    calculate_mrr,
    calculate_ndcg,
    calculate_precision_at_k,
    calculate_recall_at_k,
    calculate_rouge_l,
    calculate_token_f1,
    evaluate_predictions,
    normalize_text,
)
from rag_eval.schemas import GroundTruth, PredictionResult


def test_text_normalization() -> None:
    """Test article removal, lowercase, and punctuation stripping."""
    assert normalize_text("The Quick, Brown FOX!") == "quick brown fox"
    assert normalize_text("An apple a day...") == "apple day"


def test_hit_rate_calculation() -> None:
    """Test HitRate@K for present and missing hits."""
    retrieved = ["doc_1", "doc_2", "doc_3"]
    relevant = {"doc_2", "doc_5"}

    assert calculate_hit_rate(retrieved, relevant, k=1) == 0.0
    assert calculate_hit_rate(retrieved, relevant, k=2) == 1.0
    assert calculate_hit_rate(retrieved, relevant, k=3) == 1.0
    assert calculate_hit_rate(retrieved, set(), k=5) == 0.0


def test_recall_and_precision_calculation() -> None:
    """Test Recall@K and Precision@K."""
    retrieved = ["doc_1", "doc_2", "doc_3", "doc_4"]
    relevant = {"doc_2", "doc_4"}

    assert calculate_recall_at_k(retrieved, relevant, k=1) == 0.0
    assert calculate_recall_at_k(retrieved, relevant, k=2) == 0.5
    assert calculate_recall_at_k(retrieved, relevant, k=4) == 1.0

    assert calculate_precision_at_k(retrieved, relevant, k=2) == 0.5
    assert calculate_precision_at_k(retrieved, relevant, k=4) == 0.5


def test_mrr_calculation() -> None:
    """Test Mean Reciprocal Rank (MRR)."""
    relevant = {"doc_target"}

    assert calculate_mrr(["doc_target", "doc_other"], relevant, k=10) == 1.0
    assert calculate_mrr(["doc_other", "doc_target"], relevant, k=10) == 0.5
    assert calculate_mrr(["d1", "d2", "doc_target"], relevant, k=10) == 1.0 / 3.0
    assert calculate_mrr(["d1", "d2", "d3"], relevant, k=2) == 0.0


def test_ndcg_calculation() -> None:
    """Test Normalized Discounted Cumulative Gain (NDCG)."""
    relevant = {"doc_1", "doc_2"}

    # Perfect ranking
    perfect_ndcg = calculate_ndcg(["doc_1", "doc_2", "doc_3"], relevant, k=3)
    assert perfect_ndcg == 1.0

    # Inverted ranking with distractor in between
    imperfect_ndcg = calculate_ndcg(["doc_3", "doc_1", "doc_2"], relevant, k=3)
    ideal_dcg = (1.0 / math.log2(2.0)) + (1.0 / math.log2(3.0))
    actual_dcg = (1.0 / math.log2(3.0)) + (1.0 / math.log2(4.0))
    expected = actual_dcg / ideal_dcg
    assert math.isclose(imperfect_ndcg, expected, rel_tol=1e-5)


def test_exact_match_and_f1() -> None:
    """Test Exact Match and Token F1 calculations."""
    ground_truths = ["30 days notice", "one month"]

    assert calculate_exact_match("30 days notice.", ground_truths) == 1.0
    assert calculate_exact_match("45 days", ground_truths) == 0.0

    # Token F1
    f1_perfect = calculate_token_f1("30 days notice", ground_truths)
    assert f1_perfect == 1.0

    f1_partial = calculate_token_f1("30 days prior written notice", ground_truths)
    # prediction tokens: ['30', 'days', 'prior', 'written', 'notice'] (len 5)
    # gt tokens: ['30', 'days', 'notice'] (len 3)
    # overlap: 3
    # precision = 3/5 = 0.6, recall = 3/3 = 1.0, f1 = 2 * 0.6 * 1.0 / 1.6 = 0.75
    assert math.isclose(f1_partial, 0.75, rel_tol=1e-5)


def test_rouge_l() -> None:
    """Test ROUGE-L calculation."""
    gt = ["the cat sat on the mat"]
    pred = "the cat was sitting on the mat"

    rouge = calculate_rouge_l(pred, gt)
    assert rouge > 0.6


def test_evaluate_predictions_pipeline() -> None:
    """Test full evaluation pipeline end-to-end with mock data."""
    ground_truths = [
        GroundTruth(query_id="q1", relevant_doc_ids=["d1"], answers=["answer one"]),
        GroundTruth(query_id="q2", relevant_doc_ids=["d2"], answers=["answer two"]),
    ]

    predictions = [
        PredictionResult(query_id="q1", retrieved_doc_ids=["d1", "d9"], generated_answer="answer one"),
        PredictionResult(query_id="q2", retrieved_doc_ids=["d8", "d2"], generated_answer="wrong answer"),
    ]

    report = evaluate_predictions(
        dataset_name="test_bench",
        ground_truths=ground_truths,
        predictions=predictions,
        k_values=[1, 2],
    )

    assert report.dataset_name == "test_bench"
    assert report.total_queries == 2
    assert report.evaluated_queries == 2

    # q1 HitRate@1 = 1.0, q2 HitRate@1 = 0.0 -> avg = 0.5
    assert report.retrieval_metrics["hit_rate@1"] == 0.5
    # q1 HitRate@2 = 1.0, q2 HitRate@2 = 1.0 -> avg = 1.0
    assert report.retrieval_metrics["hit_rate@2"] == 1.0
    # q1 MRR = 1.0, q2 MRR = 0.5 -> avg = 0.75
    assert report.retrieval_metrics["mrr@10"] == 0.75

    # Generation metrics
    assert report.generation_metrics["exact_match"] == 0.5
    assert report.generation_metrics["token_f1"] == 0.75


def test_evaluate_predictions_empty_error() -> None:
    """Test error raised when predictions list is empty."""
    with pytest.raises(EvaluationError):
        _ = evaluate_predictions("test", [GroundTruth(query_id="q1")], [])
