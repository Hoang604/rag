"""Tests for the signal that decides whether the system claims to have an answer.

This is the only mechanism standing between a question the corpus cannot answer
and a confident-looking citation, so it is worth pinning precisely rather than
leaving to the benchmark. The benchmark measures how often it is right on
average; these fix what it must do in each case, including the two exceptions
that were added for measured reasons and would otherwise look arbitrary.
"""

from __future__ import annotations

import pytest

from rag_eval.legal.mcp.tools import (
    LOW_RERANK,
    LOW_SIMILARITY,
    HybridSearchResult,
    SearchHit,
)


def _hit(
    similarity: float,
    keyword: bool = True,
    rerank: float | None = None,
) -> SearchHit:
    return SearchHit(
        chunk_id="x",
        doc_code="168/2024/ND-CP",
        doc_title="",
        path="168_2024_nd_cp.c_ii.a_7.c_7.p_c",
        verbatim_text="",
        contextualized_text="",
        metadata={},
        effective_date="2025-01-01",
        expiration_date=None,
        score=0.02,
        dense_similarity=similarity,
        keyword_matched=keyword,
        rerank_score=rerank,
    )


def _result(
    hits: list[SearchHit], dense_informative: bool = True
) -> HybridSearchResult:
    return HybridSearchResult(
        total_hits=len(hits),
        hits=hits,
        temporal_as_of="2026-09-06",
        dense_is_informative=dense_informative,
    )


def test_nothing_retrieved_is_reported_as_nothing_found() -> None:
    assert _result([]).confidence == "none"


def test_no_keyword_match_anywhere_is_reported_as_nothing_found() -> None:
    """The sharp signal: 25 of 25 meaningless queries, 0 of 408 real ones."""
    assert (
        _result([_hit(0.95, keyword=False), _hit(0.94, keyword=False)]).confidence
        == "none"
    )


def test_one_keyword_match_is_enough_to_not_abstain() -> None:
    hits = [_hit(0.95, keyword=False), _hit(0.94, keyword=True)]
    assert _result(hits).confidence != "none"


def test_weak_similarity_is_flagged_but_not_suppressed() -> None:
    assert _result([_hit(LOW_SIMILARITY - 0.01)]).confidence == "low"


def test_strong_similarity_passes() -> None:
    assert _result([_hit(LOW_SIMILARITY + 0.01)]).confidence == "high"


def test_the_best_hit_decides_not_the_worst() -> None:
    """One weak neighbour in the list does not make the answer weak."""
    assert _result([_hit(0.95), _hit(0.50), _hit(0.40)]).confidence == "high"


def test_unaccented_queries_are_not_flagged_on_similarity() -> None:
    """The exception that took false warnings from 10.0% to 0.2%.

    The corpus is embedded from accented text, so an unaccented question sits
    far from its own answer in vector space for a reason unrelated to
    relevance. Judging it by cosine flagged every one of them.
    """
    weak = [_hit(LOW_SIMILARITY - 0.05)]
    assert _result(weak, dense_informative=True).confidence == "low"
    assert _result(weak, dense_informative=False).confidence == "high"


def test_the_keyword_signal_still_applies_to_unaccented_queries() -> None:
    """Withholding the cosine warning must not disable abstention entirely.

    Junk input is usually unaccented, and it is exactly what the keyword
    signal is for.
    """
    hits = [_hit(0.99, keyword=False)]
    assert _result(hits, dense_informative=False).confidence == "none"


@pytest.mark.parametrize("similarity", [0.0, 0.5, LOW_SIMILARITY, 1.0])
def test_confidence_is_always_one_of_three_values(similarity: float) -> None:
    for informative in (True, False):
        for keyword in (True, False):
            verdict = _result([_hit(similarity, keyword)], informative).confidence
            assert verdict in {"high", "low", "none"}


def test_the_threshold_sits_where_it_was_measured() -> None:
    """0.86 came from 400 answerable questions against 87 unanswerable ones.

    Pinned because it is a number someone will later be tempted to round.
    """
    assert LOW_SIMILARITY == pytest.approx(0.86)


def test_a_reranker_that_rejects_everything_downgrades_to_low() -> None:
    """The case the other two signals miss entirely.

    "đi xe máy đâm chết người bị phạt bao nhiêu năm tù" returned five helmet
    provisions at `high`: the keywords matched and cosine was 0.88, but every
    cross-encoder score sat near -3 because nothing retrieved answers it --
    criminal liability is Bộ luật Hình sự, and this corpus has none of it.
    """
    hits = [_hit(0.88, rerank=-2.60), _hit(0.88, rerank=-3.19)]
    assert _result(hits).confidence == "low"


def test_one_good_candidate_is_enough_to_stay_high() -> None:
    """The best hit decides. A weak tail is normal and means nothing."""
    hits = [_hit(0.95, rerank=4.90), _hit(0.88, rerank=-3.00)]
    assert _result(hits).confidence == "high"


def test_the_rerank_signal_is_skipped_when_no_scores_are_present() -> None:
    """Reranking is optional, and unaccented queries deliberately skip it.

    Treating a missing score as a bad one would flag every unreranked query.
    """
    assert _result([_hit(0.95, rerank=None)]).confidence == "high"


def test_the_rerank_threshold_sits_where_it_was_measured() -> None:
    """-1.0 came from 99 answerable against 41 unanswerable questions.

    Pinned because it is a number someone will later round to zero.
    """
    assert LOW_RERANK == pytest.approx(-1.0)
    assert _result([_hit(0.95, rerank=LOW_RERANK - 0.01)]).confidence == "low"
    assert _result([_hit(0.95, rerank=LOW_RERANK + 0.01)]).confidence == "high"


def test_junk_still_reports_none_not_low() -> None:
    """The keyword signal outranks the rerank signal, and must keep doing so.

    Meaningless input should say nothing was found, not offer weak results.
    """
    hits = [_hit(0.99, keyword=False, rerank=-5.16)]
    assert _result(hits).confidence == "none"
