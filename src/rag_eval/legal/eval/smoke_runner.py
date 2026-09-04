"""Smoke Evaluation Runner for Legal Traffic Law RAG.

Evaluates 30 real-world statutory queries against the hybrid retrieval engine,
measuring Hit@k, Mean Reciprocal Rank (MRR), and Citation Exactness.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import unicodedata
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from rich.console import Console
from rich.table import Table

from rag_eval.legal.ingestion.xref import address_of_path
from rag_eval.legal.mcp.tools import LegalMCPTools, SearchHit
from rag_eval.legal.schemas import LegalDomainError, sanitize_index_label

logger = logging.getLogger(__name__)


class GroundTruth(BaseModel):
    """Ground truth statutory citation target."""

    model_config = ConfigDict(extra="ignore")

    doc_code: str
    # An appendix provision has no Điều/Khoản, so it is addressed by path.
    article: int | None = None
    clause: int | None = None
    point: str | None = None
    path_suffix: str | None = None
    keywords: list[str] = Field(default_factory=list)


class SmokeQueryItem(BaseModel):
    """Single test query item with metadata and ground truth."""

    model_config = ConfigDict(extra="ignore")

    id: str
    query: str
    domain: str
    ground_truth: GroundTruth


class QueryResultEvaluation(BaseModel):
    """Evaluation result for an individual query."""

    model_config = ConfigDict(extra="ignore")

    query_id: str
    query: str
    hit_at_1: bool = False
    hit_at_3: bool = False
    hit_at_5: bool = False
    reciprocal_rank: float = 0.0
    citation_exact: bool = False
    top_hit_path: str | None = None
    top_hit_doc: str | None = None
    latency_ms: float = 0.0


class SmokeEvaluationReport(BaseModel):
    """Aggregated evaluation metrics across the smoke test set."""

    model_config = ConfigDict(extra="ignore")

    total_queries: int
    hit_at_1: float
    hit_at_3: float
    hit_at_5: float
    mean_reciprocal_rank: float
    citation_exactness: float
    average_latency_ms: float
    timestamp: float
    results: list[QueryResultEvaluation] = Field(default_factory=list)



def _check_doc_match(hit_doc: str, gt_doc: str) -> bool:
    """Normalises and checks if document codes match, handling Vietnamese diacritics."""
    def _clean(val: str) -> str:
        s = val.replace("đ", "d").replace("Đ", "D")
        nfkd = unicodedata.normalize("NFKD", s)
        no_marks = "".join(c for c in nfkd if not unicodedata.combining(c))
        return re.sub(r"[^a-zA-Z0-9]", "", no_marks.lower())

    norm_hit = _clean(hit_doc)
    norm_gt = _clean(gt_doc)
    return norm_gt in norm_hit or norm_hit in norm_gt


def _check_article_match(hit: SearchHit, gt: GroundTruth) -> bool:
    """Verifies whether a SearchHit covers the target article."""
    if not _check_doc_match(hit.doc_code, gt.doc_code):
        return False
    if gt.path_suffix is not None:
        return hit.path.startswith(gt.path_suffix)
    return address_of_path(hit.path).dieu == str(gt.article)


def _check_citation_exactness(hit: SearchHit, gt: GroundTruth) -> bool:
    """Strictly checks document, article, clause, and point match."""
    if not _check_article_match(hit, gt):
        return False
    if gt.path_suffix is not None:
        return True
    address = address_of_path(hit.path)
    if gt.clause is not None and address.khoan != str(gt.clause):
        return False
    return gt.point is None or address.diem == sanitize_index_label(gt.point)


async def evaluate_smoke_set(
    tools: LegalMCPTools,
    smoke_path: Path | None = None,
    limit: int = 5,
) -> SmokeEvaluationReport:
    """Executes all 30 smoke queries against LegalMCPTools and scores metrics."""
    if smoke_path is None:
        # Default fixture location
        base_dir = Path(__file__).resolve().parents[4]
        smoke_path = base_dir / "tests" / "fixtures" / "smoke_queries_30.jsonl"

    if not smoke_path.exists():
        raise FileNotFoundError(f"Smoke test dataset not found: {smoke_path}")

    items: list[SmokeQueryItem] = []
    with smoke_path.open("r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped:
                items.append(SmokeQueryItem.model_validate_json(stripped))

    # A resident server pays the model load once at startup. Left inside the
    # first query it lands entirely in the latency average.
    if items:
        try:
            await tools.hybrid_search(query=items[0].query, limit=limit)
        except (LegalDomainError, RuntimeError, OSError, ValueError) as exc:
            logger.warning("Warm-up query failed: %s", exc)

    eval_results: list[QueryResultEvaluation] = []

    for item in items:
        start_time = time.perf_counter()
        try:
            search_res = await tools.hybrid_search(
                query=item.query,
                limit=limit,
            )
            hits = search_res.hits
        except (LegalDomainError, RuntimeError, OSError, ValueError) as exc:
            logger.warning("Query failed during evaluation for %s: %s", item.id, exc)
            hits = []

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        hit_at_1 = False
        hit_at_3 = False
        hit_at_5 = False
        rr = 0.0
        exact = False
        top_path: str | None = None
        top_doc: str | None = None

        if hits:
            top_path = hits[0].path
            top_doc = hits[0].doc_code

        for rank_idx, hit in enumerate(hits, start=1):
            is_match = _check_article_match(hit, item.ground_truth)
            if is_match:
                if rank_idx == 1:
                    hit_at_1 = True
                if rank_idx <= 3:
                    hit_at_3 = True
                if rank_idx <= 5:
                    hit_at_5 = True

                if rr == 0.0:
                    rr = 1.0 / float(rank_idx)

                if _check_citation_exactness(hit, item.ground_truth):
                    exact = True

        eval_results.append(
            QueryResultEvaluation(
                query_id=item.id,
                query=item.query,
                hit_at_1=hit_at_1,
                hit_at_3=hit_at_3,
                hit_at_5=hit_at_5,
                reciprocal_rank=rr,
                citation_exact=exact,
                top_hit_path=top_path,
                top_hit_doc=top_doc,
                latency_ms=elapsed_ms,
            )
        )

    total = len(eval_results)
    if total == 0:
        return SmokeEvaluationReport(
            total_queries=0,
            hit_at_1=0.0,
            hit_at_3=0.0,
            hit_at_5=0.0,
            mean_reciprocal_rank=0.0,
            citation_exactness=0.0,
            average_latency_ms=0.0,
            timestamp=time.time(),
            results=[],
        )

    hit1_ratio = sum(1 for r in eval_results if r.hit_at_1) / total
    hit3_ratio = sum(1 for r in eval_results if r.hit_at_3) / total
    hit5_ratio = sum(1 for r in eval_results if r.hit_at_5) / total
    mrr = sum(r.reciprocal_rank for r in eval_results) / total
    exact_ratio = sum(1 for r in eval_results if r.citation_exact) / total
    avg_latency = sum(r.latency_ms for r in eval_results) / total

    report = SmokeEvaluationReport(
        total_queries=total,
        hit_at_1=round(hit1_ratio, 4),
        hit_at_3=round(hit3_ratio, 4),
        hit_at_5=round(hit5_ratio, 4),
        mean_reciprocal_rank=round(mrr, 4),
        citation_exactness=round(exact_ratio, 4),
        average_latency_ms=round(avg_latency, 2),
        timestamp=time.time(),
        results=eval_results,
    )

    return report


def render_report_table(report: SmokeEvaluationReport) -> None:
    """Prints a styled Rich summary table of evaluation metrics."""
    console = Console()
    table = Table(title="Legal RAG — Smoke Evaluation Baseline (Sprint 1)")

    table.add_column("Chỉ số đo lường", style="cyan", justify="left")
    table.add_column("Kết quả đạt được", style="bold green", justify="right")
    table.add_column("Mục tiêu Gate S1", style="yellow", justify="right")

    table.add_row("Tổng số câu hỏi", str(report.total_queries), "30")
    table.add_row("Hit@1 (Top 1 đúng Điều)", f"{report.hit_at_1 * 100:.1f}%", ">= 50.0%")
    table.add_row("Hit@3 (Top 3 đúng Điều)", f"{report.hit_at_3 * 100:.1f}%", ">= 70.0%")
    table.add_row("Hit@5 (Top 5 đúng Điều)", f"{report.hit_at_5 * 100:.1f}%", ">= 75.0%")
    table.add_row("MRR (Mean Reciprocal Rank)", f"{report.mean_reciprocal_rank:.4f}", ">= 0.6000")
    table.add_row("Citation Exactness (Khoản/Điểm)", f"{report.citation_exactness * 100:.1f}%", ">= 40.0%")
    table.add_row("Độ trễ trung bình (Latency)", f"{report.average_latency_ms:.1f} ms", "< 150 ms")

    console.print(table)


async def main() -> None:
    """CLI entry point for running smoke evaluation."""
    from rag_eval.legal.mcp.tools import SentenceTransformerQueryEmbedder

    embedder = SentenceTransformerQueryEmbedder()
    tools = LegalMCPTools(embedding_engine=embedder)

    try:
        report = await evaluate_smoke_set(tools=tools)
        render_report_table(report)

        # Save results to experiments/smoke_eval_results.json
        output_dir = Path(__file__).resolve().parents[4] / "experiments"
        output_dir.mkdir(exist_ok=True)
        out_file = output_dir / "smoke_eval_results.json"
        with out_file.open("w", encoding="utf-8") as f:
            f.write(report.model_dump_json(indent=2))
        print(f"Results saved to {out_file}")
    except (LegalDomainError, RuntimeError, OSError, ValueError) as exc:
        print(f"Evaluation encountered an error: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
