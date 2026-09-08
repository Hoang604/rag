"""Invariant tests for the cross-encoder stage.

Until now the reranker was only exercised through benchmarks, which measure
whether the ranking got better and say nothing about whether it stayed a
ranking. The properties below are the ones a benchmark cannot fail on: it would
happily report a good Hit@1 for a reranker that silently dropped a candidate,
returned duplicates, or left the order disagreeing with the score it reports.

No model is loaded. A cross-encoder is a black box that maps pairs to numbers,
so a stub that returns chosen numbers tests the surrounding logic exactly and
runs in milliseconds.
"""

from __future__ import annotations

import pytest

from rag_eval.legal.mcp.tools import SearchHit
from rag_eval.legal.retrieval.reranker import CrossEncoderReranker


class StubModel:
    """Returns a fixed score per document text, and counts how it was called."""

    def __init__(self, scores: dict[str, float]) -> None:
        self._scores = scores
        self.calls: list[list[tuple[str, str]]] = []

    def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
        self.calls.append(list(pairs))
        return [self._scores.get(text, 0.0) for _, text in pairs]


def _hit(path: str, text: str, score: float = 0.01) -> SearchHit:
    return SearchHit(
        chunk_id=path,
        doc_code="168/2024/ND-CP",
        doc_title="",
        path=path,
        verbatim_text=text,
        contextualized_text=text,
        metadata={},
        effective_date="2025-01-01",
        expiration_date=None,
        score=score,
    )


def _reranker(
    scores: dict[str, float], blend: float = 1.0
) -> tuple[CrossEncoderReranker, StubModel]:
    stub = StubModel(scores)
    return CrossEncoderReranker(blend=blend, model=stub), stub


HITS = [
    _hit("a", "điều khoản A", 0.05),
    _hit("b", "điều khoản B", 0.04),
    _hit("c", "điều khoản C", 0.03),
]
SCORES = {"điều khoản A": -2.0, "điều khoản B": 5.0, "điều khoản C": 1.0}


@pytest.mark.asyncio
async def test_reordering_by_cross_encoder_score() -> None:
    engine, _ = _reranker(SCORES)
    out = await engine.rerank("câu hỏi", list(HITS))
    assert [h.path for h in out] == ["b", "c", "a"]


@pytest.mark.asyncio
async def test_no_candidate_is_lost_or_duplicated() -> None:
    """The stage reorders. Anything else is a defect a Hit@1 figure would hide."""
    engine, _ = _reranker(SCORES)
    out = await engine.rerank("câu hỏi", list(HITS))
    assert sorted(h.path for h in out) == ["a", "b", "c"]
    assert len({h.path for h in out}) == len(out)


@pytest.mark.asyncio
async def test_returned_order_agrees_with_the_score_it_reports() -> None:
    """The bug that shipped: order from one score, `score` field from another.

    A consumer sorting by the reported score must get back the order it was
    given, or it silently undoes the reranking.
    """
    engine, _ = _reranker(SCORES)
    out = await engine.rerank("câu hỏi", list(HITS))
    reported = [h.rerank_score for h in out]
    assert all(s is not None for s in reported)
    assert reported == sorted(reported, reverse=True)  # type: ignore[type-var]


@pytest.mark.asyncio
async def test_fused_score_is_left_alone() -> None:
    """`score` stays the fusion's, because the confidence signals derive from it."""
    engine, _ = _reranker(SCORES)
    out = await engine.rerank("câu hỏi", list(HITS))
    by_path = {h.path: h.score for h in out}
    assert by_path == {"a": 0.05, "b": 0.04, "c": 0.03}


@pytest.mark.asyncio
async def test_top_k_truncates_after_reordering_not_before() -> None:
    """Truncating first would discard the answer the reranker exists to promote."""
    engine, _ = _reranker(SCORES)
    out = await engine.rerank("câu hỏi", list(HITS), top_k=1)
    assert [h.path for h in out] == ["b"]


@pytest.mark.asyncio
async def test_the_model_reads_the_contextualised_text() -> None:
    """A bare clause says neither which vehicle it governs nor what it costs."""
    engine, stub = _reranker(SCORES)
    await engine.rerank("câu hỏi", list(HITS))
    pairs = stub.calls[0]
    assert [text for _, text in pairs] == [h.contextualized_text for h in HITS]
    assert {query for query, _ in pairs} == {"câu hỏi"}


@pytest.mark.asyncio
@pytest.mark.parametrize("hits", [[], [_hit("solo", "một điều khoản")]])
async def test_nothing_to_reorder_costs_no_model_call(hits: list[SearchHit]) -> None:
    engine, stub = _reranker(SCORES)
    out = await engine.rerank("câu hỏi", list(hits))
    assert [h.path for h in out] == [h.path for h in hits]
    assert stub.calls == []


@pytest.mark.asyncio
async def test_blending_lets_the_fused_order_still_count() -> None:
    """At blend 0.5 a candidate the fusion ranked first is not sent to the back.

    Measured, blending is worse than pure cross-encoder ordering and is not
    what ships -- but the option exists and should do what it says.
    """
    scores = {"điều khoản A": -9.0, "điều khoản B": 0.1, "điều khoản C": 0.0}
    pure = await _reranker(scores, blend=1.0)[0].rerank("q", list(HITS))
    blended = await _reranker(scores, blend=0.5)[0].rerank("q", list(HITS))
    assert pure[-1].path == "a"
    assert blended.index(next(h for h in blended if h.path == "a")) < 2


@pytest.mark.asyncio
async def test_ties_do_not_lose_candidates() -> None:
    flat = dict.fromkeys(SCORES, 1.0)
    engine, _ = _reranker(flat)
    out = await engine.rerank("câu hỏi", list(HITS))
    assert sorted(h.path for h in out) == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_score_caching_avoids_redundant_model_calls() -> None:
    """Repeated calls with identical (query, text) pairs reuse the cached score."""
    engine, stub = _reranker(SCORES)
    out1 = await engine.rerank("câu hỏi", list(HITS))
    assert len(stub.calls) == 1

    # Second call for the same query and hits should hit cache with no new stub model predictions
    out2 = await engine.rerank("câu hỏi", list(HITS))
    assert len(stub.calls) == 1
    assert [h.path for h in out1] == [h.path for h in out2]

