"""Deterministic evaluation engine for IR ranking and lexical generation metrics."""

import math
import re
import string

from rag_eval.schemas import EvaluationReport, GroundTruth, PredictionResult


class EvaluationError(Exception):
    """Raised when prediction structure or query alignment fails validation."""


def normalize_text(s: str) -> str:
    """Lower text and remove punctuation, articles and extra whitespace."""

    def remove_articles(text: str) -> str:
        return re.sub(r"\b(a|an|the)\b", " ", text)

    def white_space_fix(text: str) -> str:
        return " ".join(text.split())

    def remove_punc(text: str) -> str:
        exclude = set(string.punctuation)
        return "".join(ch for ch in text if ch not in exclude)

    def lower(text: str) -> str:
        return text.lower()

    return white_space_fix(remove_articles(remove_punc(lower(s))))


def calculate_hit_rate(retrieved: list[str], relevant: set[str], k: int) -> float:
    """Calculate binary Hit Rate @ K (1.0 if any relevant doc is in top-K, else 0.0)."""
    if not relevant:
        return 0.0
    top_k = retrieved[:k]
    for doc_id in top_k:
        if doc_id in relevant:
            return 1.0
    return 0.0


def calculate_recall_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    """Calculate Recall @ K (fraction of relevant documents retrieved in top-K)."""
    if not relevant:
        return 0.0
    top_k = retrieved[:k]
    hits = sum(1 for doc_id in top_k if doc_id in relevant)
    return hits / float(len(relevant))


def calculate_precision_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    """Calculate Precision @ K (fraction of top-K retrieved documents that are relevant)."""
    if k <= 0:
        return 0.0
    top_k = retrieved[:k]
    hits = sum(1 for doc_id in top_k if doc_id in relevant)
    return hits / float(k)


def calculate_mrr(retrieved: list[str], relevant: set[str], k: int = 10) -> float:
    """Calculate Mean Reciprocal Rank (MRR) @ K for a single query."""
    if not relevant:
        return 0.0
    top_k = retrieved[:k]
    for rank_idx, doc_id in enumerate(top_k, start=1):
        if doc_id in relevant:
            return 1.0 / float(rank_idx)
    return 0.0


def calculate_ndcg(retrieved: list[str], relevant: set[str], k: int = 10) -> float:
    """Calculate Normalized Discounted Cumulative Gain (NDCG) @ K with binary relevance."""
    if not relevant:
        return 0.0
    top_k = retrieved[:k]
    dcg = 0.0
    for rank_idx, doc_id in enumerate(top_k, start=1):
        if doc_id in relevant:
            dcg += 1.0 / math.log2(float(rank_idx + 1))

    ideal_hits = min(len(relevant), k)
    idcg = sum(1.0 / math.log2(float(r + 1)) for r in range(1, ideal_hits + 1))

    if idcg == 0.0:
        return 0.0
    return dcg / idcg


def calculate_exact_match(prediction: str, ground_truths: list[str]) -> float:
    """Calculate Exact Match (EM) score normalized for whitespace and punctuation."""
    if not ground_truths:
        return 0.0
    norm_pred = normalize_text(prediction)
    for gt in ground_truths:
        if norm_pred == normalize_text(gt):
            return 1.0
    return 0.0


def calculate_token_f1(prediction: str, ground_truths: list[str]) -> float:
    """Calculate unigram Token F1 score against reference answers."""
    if not ground_truths:
        return 0.0

    best_f1 = 0.0
    pred_tokens = normalize_text(prediction).split()

    for gt in ground_truths:
        gt_tokens = normalize_text(gt).split()
        if not pred_tokens or not gt_tokens:
            f1 = 1.0 if pred_tokens == gt_tokens else 0.0
            best_f1 = max(best_f1, f1)
            continue

        common: dict[str, int] = {}
        for token in pred_tokens:
            common[token] = common.get(token, 0) + 1

        overlap = 0
        gt_counts: dict[str, int] = {}
        for token in gt_tokens:
            gt_counts[token] = gt_counts.get(token, 0) + 1

        for token, count in common.items():
            if token in gt_counts:
                overlap += min(count, gt_counts[token])

        if overlap == 0:
            continue

        precision = float(overlap) / float(len(pred_tokens))
        recall = float(overlap) / float(len(gt_tokens))
        f1 = (2.0 * precision * recall) / (precision + recall)
        best_f1 = max(best_f1, f1)

    return best_f1


def calculate_rouge_l(prediction: str, ground_truths: list[str]) -> float:
    """Calculate Longest Common Subsequence (ROUGE-L) F1 score."""
    if not ground_truths:
        return 0.0

    def lcs(x: list[str], y: list[str]) -> int:
        n = len(x)
        m = len(y)
        table = [[0] * (m + 1) for _ in range(n + 1)]
        for i in range(n):
            for j in range(m):
                if x[i] == y[j]:
                    table[i + 1][j + 1] = table[i][j] + 1
                else:
                    table[i + 1][j + 1] = max(table[i + 1][j], table[i][j + 1])
        return table[n][m]

    best_rouge = 0.0
    pred_tokens = normalize_text(prediction).split()

    for gt in ground_truths:
        gt_tokens = normalize_text(gt).split()
        if not pred_tokens or not gt_tokens:
            score = 1.0 if pred_tokens == gt_tokens else 0.0
            best_rouge = max(best_rouge, score)
            continue

        lcs_len = lcs(pred_tokens, gt_tokens)
        if lcs_len == 0:
            continue

        precision = float(lcs_len) / float(len(pred_tokens))
        recall = float(lcs_len) / float(len(gt_tokens))
        rouge_f1 = (2.0 * precision * recall) / (precision + recall)
        best_rouge = max(best_rouge, rouge_f1)

    return best_rouge


def evaluate_predictions(
    dataset_name: str,
    ground_truths: list[GroundTruth],
    predictions: list[PredictionResult],
    k_values: list[int] | None = None,
) -> EvaluationReport:
    """Pure evaluation pipeline comparing ground truths against RAG predictions."""
    if k_values is None:
        k_values = [1, 3, 5, 10]

    gt_by_query_id: dict[str, GroundTruth] = {gt.query_id: gt for gt in ground_truths}
    pred_by_query_id: dict[str, PredictionResult] = {p.query_id: p for p in predictions}

    total_queries = len(ground_truths)
    evaluated_queries = len(pred_by_query_id)

    if evaluated_queries == 0:
        msg = "Predictions list is empty; no queries to evaluate."
        raise EvaluationError(msg)

    hit_rate_accumulators: dict[int, list[float]] = {k: [] for k in k_values}
    recall_accumulators: dict[int, list[float]] = {k: [] for k in k_values}
    precision_accumulators: dict[int, list[float]] = {k: [] for k in k_values}
    mrr_accumulators: list[float] = []
    ndcg_accumulators: list[float] = []

    em_accumulators: list[float] = []
    f1_accumulators: list[float] = []
    rouge_accumulators: list[float] = []

    per_query_scores: list[dict[str, str | float]] = []

    for q_id, gt in gt_by_query_id.items():
        if q_id not in pred_by_query_id:
            continue

        pred = pred_by_query_id[q_id]
        rel_set = set(gt.relevant_doc_ids)

        q_score: dict[str, str | float] = {"query_id": q_id}

        # Retrieval metrics
        for k in k_values:
            hr = calculate_hit_rate(pred.retrieved_doc_ids, rel_set, k)
            rec = calculate_recall_at_k(pred.retrieved_doc_ids, rel_set, k)
            prec = calculate_precision_at_k(pred.retrieved_doc_ids, rel_set, k)

            hit_rate_accumulators[k].append(hr)
            recall_accumulators[k].append(rec)
            precision_accumulators[k].append(prec)

            q_score[f"hit_rate@{k}"] = hr
            q_score[f"recall@{k}"] = rec
            q_score[f"precision@{k}"] = prec

        mrr_val = calculate_mrr(pred.retrieved_doc_ids, rel_set, k=10)
        ndcg_val = calculate_ndcg(pred.retrieved_doc_ids, rel_set, k=10)

        mrr_accumulators.append(mrr_val)
        ndcg_accumulators.append(ndcg_val)

        q_score["mrr@10"] = mrr_val
        q_score["ndcg@10"] = ndcg_val

        # Generation metrics (if predictions or ground truth answers exist)
        if pred.generated_answer is not None and gt.answers:
            em_val = calculate_exact_match(pred.generated_answer, gt.answers)
            f1_val = calculate_token_f1(pred.generated_answer, gt.answers)
            rouge_val = calculate_rouge_l(pred.generated_answer, gt.answers)

            em_accumulators.append(em_val)
            f1_accumulators.append(f1_val)
            rouge_accumulators.append(rouge_val)

            q_score["exact_match"] = em_val
            q_score["token_f1"] = f1_val
            q_score["rouge_l"] = rouge_val

        per_query_scores.append(q_score)

    retrieval_metrics: dict[str, float] = {}
    count = float(len(per_query_scores)) if per_query_scores else 1.0

    for k in k_values:
        retrieval_metrics[f"hit_rate@{k}"] = sum(hit_rate_accumulators[k]) / count
        retrieval_metrics[f"recall@{k}"] = sum(recall_accumulators[k]) / count
        retrieval_metrics[f"precision@{k}"] = sum(precision_accumulators[k]) / count

    retrieval_metrics["mrr@10"] = sum(mrr_accumulators) / count
    retrieval_metrics["ndcg@10"] = sum(ndcg_accumulators) / count

    generation_metrics: dict[str, float] = {}
    gen_count = float(len(em_accumulators)) if em_accumulators else 1.0
    if em_accumulators:
        generation_metrics["exact_match"] = sum(em_accumulators) / gen_count
        generation_metrics["token_f1"] = sum(f1_accumulators) / gen_count
        generation_metrics["rouge_l"] = sum(rouge_accumulators) / gen_count

    return EvaluationReport(
        dataset_name=dataset_name,
        total_queries=total_queries,
        evaluated_queries=evaluated_queries,
        retrieval_metrics=retrieval_metrics,
        generation_metrics=generation_metrics,
        per_query_scores=per_query_scores,
    )
