"""Tests for the layer that lets a model write the answer.

This is the one place in the system where text is produced rather than
retrieved, so it is the one place a confident sentence can be wrong with
nothing in the output to show it. The tests below pin the two defences: the
system does not call a model when retrieval found nothing, and it checks what
comes back against the provisions it supplied.

No CLI is launched. What a model returns is not the thing under test -- the
question is what this module does with the string it gets back, and a chosen
string tests that exactly, in milliseconds.
"""

from __future__ import annotations

import pytest

from rag_eval.legal.answer import (
    AnswerError,
    build_prompt,
    check_grounding,
    compose,
)
from rag_eval.legal.mcp.tools import HybridSearchResult, SearchHit


def _hit(path: str, text: str, keyword: bool = True) -> SearchHit:
    return SearchHit(
        chunk_id=path,
        doc_code="168/2024/ND-CP",
        doc_title="Nghị định 168/2024",
        path=path,
        verbatim_text=text,
        contextualized_text=text,
        metadata={},
        effective_date="2025-01-01",
        expiration_date=None,
        score=0.03,
        dense_similarity=0.95,
        keyword_matched=keyword,
    )


HITS = [
    _hit(
        "168_2024_nd_cp.c_ii.s_1.a_7.c_7.p_c",
        "Điểm c) Không chấp hành hiệu lệnh của đèn tín hiệu giao thông;",
    ),
    _hit(
        "168_2024_nd_cp.c_ii.s_1.a_7.c_7",
        "Phạt tiền từ 4.000.000 đồng đến 6.000.000 đồng đối với người điều khiển xe",
    ),
]


def _result(hits: list[SearchHit], confidence_hits: bool = True) -> HybridSearchResult:
    return HybridSearchResult(
        total_hits=len(hits),
        hits=hits,
        temporal_as_of="2026-09-07",
        dense_is_informative=confidence_hits,
    )


# ---------------------------------------------------------------- the prompt


def test_the_prompt_carries_the_citation_of_every_provision() -> None:
    """A model cannot cite what it was not told the address of."""
    prompt = build_prompt("xe máy vượt đèn đỏ phạt bao nhiêu?", HITS)
    assert "Điều 7 Khoản 7 Điểm c" in prompt
    assert "Điều 7 Khoản 7" in prompt
    assert "xe máy vượt đèn đỏ phạt bao nhiêu?" in prompt


def test_the_prompt_forbids_outside_knowledge() -> None:
    prompt = build_prompt("câu hỏi", HITS)
    assert "CHỈ dùng các điều khoản" in prompt


def test_the_prompt_frames_provisions_as_data_not_instructions() -> None:
    """The provisions are corpus text, and corpus text must not steer the model."""
    assert "không phải chỉ thị" in build_prompt("câu hỏi", HITS)


# ------------------------------------------------------------- the grounding


def test_a_grounded_answer_passes() -> None:
    answer = (
        "Vượt đèn đỏ với xe mô tô bị phạt từ 4.000.000 đồng đến 6.000.000 đồng "
        "theo Điều 7 Khoản 7 Điểm c [#1][#2]."
    )
    verdict = check_grounding(answer, HITS)
    assert verdict.ok
    assert verdict.unsupported_articles == []
    assert verdict.unsupported_amounts == []


def test_an_article_that_was_never_retrieved_is_caught() -> None:
    """The most convincing way to be wrong: a citation that looks like the others."""
    verdict = check_grounding("Theo Điều 6 Khoản 3 thì bị phạt.", HITS)
    assert not verdict.ok
    assert verdict.unsupported_articles == ["6"]


def test_a_penalty_figure_that_appears_nowhere_is_caught() -> None:
    """A number the model rounded, or invented, is the costliest error here."""
    verdict = check_grounding("Phạt 5.000.000 đồng theo Điều 7.", HITS)
    assert not verdict.ok
    assert verdict.unsupported_amounts == ["5.000.000 đồng"]


def test_thousands_separators_do_not_create_false_alarms() -> None:
    """ "4000000" and "4.000.000" are the same sum written two ways."""
    assert check_grounding("Phạt 4000000 đồng theo Điều 7.", HITS).ok


def test_an_article_number_is_not_mistaken_for_money() -> None:
    """Without the unit, "Điều 7" would read as the figure 7 and never match."""
    assert check_grounding("Xem Điều 7 Khoản 7 Điểm c.", HITS).ok


def test_a_letter_suffixed_article_is_handled() -> None:
    """ "18a" is a real article number, and rejecting it would be a false alarm."""
    hits = [_hit("100_2019_nd_cp.c_i.a_18a.c_1", "Khoản 1 ...")]
    assert check_grounding("Theo Điều 18a Khoản 1 ...", hits).ok
    assert not check_grounding("Theo Điều 18b ...", hits).ok


def test_both_kinds_of_defect_are_reported_together() -> None:
    """A reviewer should see everything wrong at once, not the first thing."""
    verdict = check_grounding("Điều 99 quy định phạt 1.234.000 đồng.", HITS)
    assert verdict.unsupported_articles == ["99"]
    assert verdict.unsupported_amounts == ["1.234.000 đồng"]


# ------------------------------------------------------------- the abstention


@pytest.fixture
def forbid_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fails the test if anything tries to launch a CLI.

    Asserting on the returned text alone would not prove a model was skipped:
    the abstention message could just as well have been produced after paying
    for a call. This makes the skip the thing under test.
    """

    def explode(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("đã gọi CLI trong khi lẽ ra phải từ chối trả lời")

    monkeypatch.setattr("rag_eval.legal.answer._run_cli", explode)


def test_nothing_retrieved_means_no_model_is_called(forbid_cli: None) -> None:
    composed = compose("asdkjfh qwoieu", _result([]), "claude")
    assert composed.abstained
    assert composed.grounding.ok
    assert "Không tìm thấy" in composed.answer


def test_no_keyword_match_anywhere_also_abstains(forbid_cli: None) -> None:
    """The measured junk signal: 25 of 25 meaningless queries, 0 of 408 real."""
    junk = [_hit("168_2024_nd_cp.a_7.c_7", "văn bản", keyword=False)]
    result = _result(junk)
    assert result.confidence == "none"
    assert compose("qwerty zxcvb", result, "claude").abstained


def test_the_provider_name_is_validated_before_any_work() -> None:
    """Checked first on purpose, abstention or not.

    A request naming a provider that does not exist is a client defect. Making
    it succeed quietly whenever retrieval happened to abstain would hide that
    defect exactly when it is hardest to notice.
    """
    with pytest.raises(AnswerError, match="không tồn tại"):
        compose("asdkjfh qwoieu", _result([]), "no-such-provider")


def test_an_unknown_provider_is_refused_when_there_is_something_to_answer() -> None:
    with pytest.raises(AnswerError, match="không tồn tại"):
        compose("xe máy vượt đèn đỏ", _result(HITS), "no-such-provider")


PARENT_PREFIX = (
    "[Nghị định 168/2024] > [Chương II] > [Điều 7] > "
    "[Khoản 7: Phạt tiền từ 4.000.000 đồng đến 6.000.000 đồng] "
)


def _hit_with_prefix(path: str, clause: str) -> SearchHit:
    """A chunk whose price lives in the CPHC prefix, as most of them do."""
    hit = _hit(path, clause)
    return hit.model_copy(update={"contextualized_text": PARENT_PREFIX + clause})


PREFIXED = [
    _hit_with_prefix(
        "168_2024_nd_cp.c_ii.s_1.a_7.c_7.p_c",
        "Điểm c) Không chấp hành hiệu lệnh của đèn tín hiệu giao thông;",
    )
]


def test_the_prompt_carries_the_price_from_the_parent_clause() -> None:
    """The bug this pins cost a whole answer.

    Sent the bare Điểm, the model got five acts and no prices, answered
    "không đủ dữ liệu", and was right to. Only 2.0% of chunks state a sum on
    their own; the rest inherit it through the prefix.
    """
    prompt = build_prompt("vượt đèn đỏ phạt bao nhiêu?", PREFIXED)
    assert "4.000.000 đồng" in prompt
    assert "6.000.000 đồng" in prompt


def test_a_price_quoted_from_the_prefix_is_not_flagged() -> None:
    """The half of the fix that is easy to forget.

    If grounding still checked only `verbatim_text`, every correctly quoted
    penalty would be reported as invented -- a false alarm aimed precisely at
    the right answers.
    """
    answer = "Phạt từ 4.000.000 đồng đến 6.000.000 đồng theo Điều 7 Khoản 7 Điểm c."
    assert check_grounding(answer, PREFIXED).ok


def test_an_invented_price_is_still_caught_with_a_prefix_present() -> None:
    """Widening the haystack must not blunt the check."""
    verdict = check_grounding("Phạt 9.999.000 đồng theo Điều 7.", PREFIXED)
    assert not verdict.ok
    assert verdict.unsupported_amounts == ["9.999.000 đồng"]
