"""What `_to_hit_responses` chooses to forward, and what it silently drops.

`is_table` was written into `chunks.metadata` at ingestion and read back
correctly by the MCP layer, which forwards the whole metadata dict. The web
layer forwards named fields instead, and the flag was not one of them -- so
every table hit reached the reviewer UI looking exactly like a provision.

That is the failure this file is here to stop recurring: the shaping function
is a hand-written allowlist, and nothing about adding a field to metadata
makes it appear on the wire.
"""

from __future__ import annotations

from typing import Any

from rag_eval.legal.mcp.tools import SearchHit
from rag_eval.legal.web.router import _to_hit_responses


def _hit(**metadata: Any) -> SearchHit:
    return SearchHit(
        chunk_id="1",
        path="38_2024_tt_bgtvt.c_ii.a_6.c_2.w_2",
        doc_code="38/2024/TT-BGTVT",
        doc_title="Thông tư quy định về tốc độ",
        verbatim_text="| Loại xe | 90 | 80 |",
        contextualized_text="[Điều 6] > [Khoản 2]\nBảng 2\n| Loại xe | 90 | 80 |",
        effective_date="2025-01-01",
        expiration_date=None,
        score=1.0,
        metadata=metadata,
    )


def test_table_flag_reaches_the_wire() -> None:
    """The flag exists in the database; the question is whether it is sent."""
    summary = "Bảng này cho biết tốc độ tối đa ngoài khu đông dân cư."
    [response] = _to_hit_responses([_hit(is_table=True, table_summary=summary)])

    assert response.is_table is True
    assert response.table_summary == summary


def test_a_provision_is_not_marked_as_a_table() -> None:
    """Absent metadata must read as "not a table", never as unknown.

    A default of `None` would push the three-way distinction onto every
    caller; there are only two states here and the absent one is `False`.
    """
    [response] = _to_hit_responses([_hit(provision_role="penalty")])

    assert response.is_table is False
    assert response.table_summary is None


def test_flag_survives_a_json_style_true() -> None:
    """asyncpg decodes jsonb `true` to Python True, but the column has also
    been written by scripts that store the string. Both must read as a table;
    a truthy-string bug here is invisible because the flag is rarely set."""
    [response] = _to_hit_responses([_hit(is_table="true")])

    assert response.is_table is True


def test_the_string_false_does_not_read_as_a_table() -> None:
    """The reason `bool()` could not be used directly.

    A flag that is correct for every value except the one someone set
    deliberately is worse than no flag, and nothing else in the response
    would contradict it.
    """
    [response] = _to_hit_responses([_hit(is_table="false")])

    assert response.is_table is False
