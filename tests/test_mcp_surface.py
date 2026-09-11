"""What the MCP interface lets an agent see and control.

The architecture's central claim is that the language model sits outside the
retrieval system and drives it. Three things contradicted that claim, and none
of them was a decision -- each was an omission that nothing failed on:

  * `confidence` was a plain `@property`, so `model_dump` dropped it. The
    three-signal abstention ran on every search and reached only the web path.
    Asked an out-of-scope question the system decided `none` and handed the
    agent three unrelated provisions with nothing to say so.
  * `hybrid_search` accepted `doc_codes` and `rerank`; the MCP schema exposed
    neither. The reviewer UI had both, so a person had strictly more control
    over retrieval than the agent the system was built for.
  * The sparse ranker matched on an expanded query the caller never saw, so a
    miss caused by the expansion was indistinguishable from a miss caused by
    the agent's own wording.

These tests pin the interface, not the ranking. They fail if a field stops
being serialised or a parameter stops being forwarded -- the two ways this
regresses silently.
"""

from __future__ import annotations

from typing import Any

from rag_eval.legal.mcp.tools import HybridSearchResult, SearchHit


def _hit(**overrides: Any) -> SearchHit:
    base: dict[str, Any] = {
        "chunk_id": "1",
        "path": "168_2024_nd_cp.c_ii.s_1.a_7.c_7.p_c",
        "doc_code": "168/2024/ND-CP",
        "doc_title": "Nghị định 168",
        "verbatim_text": "Điểm c) Không chấp hành hiệu lệnh của đèn tín hiệu;",
        "contextualized_text": "[Điều 7] > [Khoản 7] ...",
        "effective_date": "2025-01-01",
        "score": 1.0,
        "dense_similarity": 0.91,
        "keyword_matched": True,
    }
    base.update(overrides)
    return SearchHit(**base)


def test_confidence_is_serialised_not_just_computed() -> None:
    """The failure was that it existed and never left the process."""
    result = HybridSearchResult(total_hits=1, hits=[_hit()], expanded_query="x")

    dumped = result.model_dump()

    assert "confidence" in dumped, (
        "confidence không nằm trong model_dump — agent sẽ không bao giờ thấy "
        "tín hiệu từ chối trả lời, đúng lỗi mà bài kiểm thử này sinh ra để chặn"
    )
    assert dumped["confidence"] == result.confidence


def test_an_unanswerable_result_says_so_on_the_wire() -> None:
    """`none` has to survive serialisation, not just evaluation."""
    result = HybridSearchResult(
        total_hits=1,
        hits=[_hit(keyword_matched=False)],
        expanded_query="giết người thì đi tù bao nhiêu năm",
    )

    assert result.model_dump()["confidence"] == "none"


def test_the_query_actually_searched_is_reported() -> None:
    """A miss from the expansion must be distinguishable from a miss from the
    agent's own wording, and only this field can tell them apart."""
    expanded = "vượt đèn đỏ không chấp hành hiệu lệnh của đèn tín hiệu giao thông"
    result = HybridSearchResult(total_hits=1, hits=[_hit()], expanded_query=expanded)

    assert result.model_dump()["expanded_query"] == expanded


def test_the_mcp_schema_exposes_scoping_and_rerank() -> None:
    """The parameters existed on the implementation and not on the interface.

    Read off the function signature rather than a live server, so the test
    stays a statement about the contract and needs no database.
    """
    import inspect

    from rag_eval.legal.mcp import server as server_module

    source = inspect.getsource(server_module)
    start = source.index("mcp_traffic_hybrid_search")
    end = source.index("mcp_traffic_verbatim_grep")
    schema = source[start:end]

    for parameter in ("doc_codes", "rerank"):
        assert f"{parameter}=" in schema, (
            f"`{parameter}` không được chuyển tiếp xuống tool_impl — agent mất "
            "quyền điều khiển mà giao diện web vẫn có"
        )
        assert f"{parameter}:" in schema, f"`{parameter}` không có trong schema MCP"
