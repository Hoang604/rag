"""Tells a data table from prose the source wrapped in table markup.

Every fixture below is copied from the live corpus, because the whole question
is whether the rule separates the two populations that actually occur. Invented
examples would only test the rule against my idea of the problem.
"""

from __future__ import annotations

from rag_eval.legal.ingestion.cphc import split_for_embedding
from rag_eval.legal.ingestion.tables import fill_ratio, is_data_table
from rag_eval.legal.mcp.tools import _merge_table_windows


def rows(block: str) -> list[str]:
    """Splits a fixture block into lines.

    The fixtures below are written as blocks rather than lists of quoted
    strings, because a table flattened into one line of comma-separated
    literals cannot be reviewed against the corpus it was copied from.
    """
    return block.splitlines()


# 184/2025/NĐ-CP a_17_2.c_14 — Điều 42, a real provision, arriving as thirteen
PROSE_AS_TABLE = """| | “Điều 42. Thông báo về việc lập hồ sơ, trình tự, thủ tục chuyển hồ sơ đề | | | | | | | | | | | |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| nghị áp dụng biện pháp đưa vào cơ sở cai nghiệp bắt buộc | | | | | | | | | | | | |
| 1. Sau khi hoàn thành việc lập hồ sơ đề nghị, cơ quan lập hồ sơ quy định | | | | | | | | | | | | |"""

# 236/2026/NĐ-CP app_ii — a government form. Two rows do hold two cells, which
FORM_GRID = """| | | | | | | Giấy phép sử | | | | | |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| | | | | | Hình | | | | | | |
| | | | | | | dụng thiết bị | | | Phương | Lãnh | Thu |
| | | | Loại | | thức | | | | | | |"""

# 38/2024/TT-BGTVT a_6.c_2 — speed limits by vehicle class. Fill ratio 100%.
REAL_TABLE = """| Loại xe cơ giới đường bộ | Tốc độ khai thác tối đa (km/h) |
| --- | --- |
| Xe ô tô con, xe ô tô chở người đến 30 chỗ | 90 |
| Xe ô tô chở người trên 30 chỗ | 80 |
| Xe mô tô, xe gắn máy | 60 |"""


def test_a_provision_wrapped_in_pipes_is_not_a_table() -> None:
    """The failure this rule exists to stop.

    Called a table, this provision has its own first line repeated as a header
    and its sentences cut into cells across five windows.
    """
    assert not is_data_table(rows(PROSE_AS_TABLE))


def test_a_form_grid_is_not_a_table() -> None:
    """Passes the weaker rule in `layout.py`, fails this one.

    `is_content_table` asks for two rows holding two cells. This grid has them
    -- and is still a form whose words are split across cells: "Giấy phép sử"
    on one row, "dụng thiết bị" on another.
    """
    assert not is_data_table(rows(FORM_GRID))


def test_a_real_table_is_kept() -> None:
    assert is_data_table(rows(REAL_TABLE))


def test_the_threshold_sits_in_the_gap_between_the_two_populations() -> None:
    """Measured over the live corpus, nothing falls between 32% and 45%.

    Pinning both edges, so a later change to the threshold has to be a
    deliberate one rather than a drift that quietly reclassifies thirteen
    chunks.
    """
    assert fill_ratio(rows(PROSE_AS_TABLE)) < 0.32
    assert fill_ratio(rows(FORM_GRID)) < 0.32
    assert fill_ratio(rows(REAL_TABLE)) > 0.45


def test_a_single_data_row_is_not_a_table() -> None:
    """Below a header and one row the pipes carry no structure worth keeping."""
    assert not is_data_table(["| Tốc độ | 90 |", "| --- | --- |"])


def test_prose_in_pipes_keeps_its_sentences_when_chunked() -> None:
    """The end-to-end consequence, not just the predicate.

    Windowed as a table, the first line becomes a header repeated on every
    part. Windowed as prose, the sentence survives in one piece.
    """
    body = "\n".join(rows(PROSE_AS_TABLE)) + "\n" + "\n".join(rows(PROSE_AS_TABLE))
    windows = split_for_embedding(body, 300)
    header_repeats = sum(1 for w in windows if "Điều 42. Thông báo" in w)
    assert header_repeats <= 2, "dòng đầu bị lặp như header trên mọi window"


def test_a_real_table_still_repeats_its_header_after_the_filter() -> None:
    body = "\n".join(rows(REAL_TABLE))
    windows = [w for w in split_for_embedding(body, 120) if "---" in w]
    assert len(windows) > 1
    for window in windows:
        assert "Loại xe cơ giới đường bộ" in window


# ------------------------------------------- rejoining what chunking split

W1 = """Bảng 2 - Hệ số kích thước biển báo
| Loại đường | Hệ số |
| --- | --- |
| Đường cao tốc | 2,0 |
| Đường đôi ngoài đô thị | 1,5 |"""

W2 = """Bảng 2 - Hệ số kích thước biển báo
| Loại đường | Hệ số |
| --- | --- |
| Đường ô tô thông thường | 1,0 |
| Đường đô thị | 0,7 |"""


def test_the_repeated_header_is_kept_once() -> None:
    """Each window repeats caption and header so it reads alone. Concatenated
    raw, that block would reappear between every few rows."""
    merged = _merge_table_windows([W1, W2], 10_000)
    assert merged.count("Bảng 2 - Hệ số kích thước biển báo") == 1
    assert merged.count("| Loại đường | Hệ số |") == 1
    assert merged.count("| --- | --- |") == 1


def test_every_row_from_every_window_survives() -> None:
    merged = _merge_table_windows([W1, W2], 10_000)
    for row in (
        "Đường cao tốc",
        "Đường đôi ngoài đô thị",
        "Đường ô tô thông thường",
        "Đường đô thị",
    ):
        assert row in merged


def test_rows_keep_their_order_across_windows() -> None:
    merged = _merge_table_windows([W1, W2], 10_000)
    assert merged.index("Đường cao tốc") < merged.index("Đường đô thị")


def test_windows_with_nothing_in_common_are_simply_joined() -> None:
    """Prose windows share no leading lines, and must not lose their first."""
    merged = _merge_table_windows(["Câu thứ nhất.", "Câu thứ hai."], 10_000)
    assert "Câu thứ nhất." in merged
    assert "Câu thứ hai." in merged


def test_an_oversize_table_is_cut_on_a_row_boundary_and_says_so() -> None:
    """A table cut mid-row would let a model read a value out of the wrong
    column, which is worse than a table it knows is incomplete."""
    merged = _merge_table_windows([W1, W2], 120)
    assert "lược bớt" in merged
    for line in merged.split("\n"):
        assert not line.startswith("|") or line.endswith("|")


def test_the_retrieved_window_survives_a_tight_budget() -> None:
    """The window retrieval matched is the one that must not be dropped.

    The first version filled the budget from the first window forward. For
    `Phụ lục G.1.1` -- six prose windows before the table in `w_10` -- that
    meant the matched window was cut and the merge handed back prose about
    lane markings, ending in a truncation marker exactly where the table
    should have been. Three questions went from right to unanswerable, and
    only because expansion ran.
    """
    prose = [f"Đoạn văn xuôi số {i}. " + "x" * 300 for i in range(6)]
    merged = _merge_table_windows([*prose, W1], 900, focus=6)

    assert "Đường cao tốc" in merged, "cửa sổ được truy hồi bị bỏ mất"
    assert "lược bớt" in merged


def test_a_focus_beyond_the_windows_does_not_raise() -> None:
    """`focus` comes from a path suffix, so a renumbered corpus can hand in an
    index that no longer exists. Clamping beats an IndexError in the answer
    path."""
    merged = _merge_table_windows([W1, W2], 10_000, focus=99)
    assert "Đường đô thị" in merged


def test_nothing_is_elided_when_everything_fits() -> None:
    """The marker has to mean something. A merge that always announced an
    elision would train a reader to ignore it."""
    merged = _merge_table_windows([W1, W2], 10_000, focus=1)
    assert "lược bớt" not in merged
