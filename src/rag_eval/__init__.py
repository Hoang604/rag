"""RAG Evaluation and Ingestion Benchmark Suite."""

from rag_eval.metrics import (
    calculate_exact_match,
    calculate_hit_rate,
    calculate_mrr,
    calculate_ndcg,
    calculate_recall_at_k,
    calculate_rouge_l,
    calculate_token_f1,
    evaluate_predictions,
)
from rag_eval.schemas import (
    Document,
    EvaluationReport,
    GroundTruth,
    MetricScore,
    PredictionResult,
    Query,
    TextSpan,
)

__all__ = [
    "Document",
    "EvaluationReport",
    "GroundTruth",
    "MetricScore",
    "PredictionResult",
    "Query",
    "TextSpan",
    "calculate_exact_match",
    "calculate_hit_rate",
    "calculate_mrr",
    "calculate_ndcg",
    "calculate_recall_at_k",
    "calculate_rouge_l",
    "calculate_token_f1",
    "evaluate_predictions",
]
