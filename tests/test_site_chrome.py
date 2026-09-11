"""Tests for dropping the publisher's page furniture at ingestion time.

The defect this guards against reached production data: eleven chunks of
chinhphu.vn sidebar and masthead were stored as continuation nodes of three
documents' final articles, so they carried a real citation address and no law.
One of them outranked a genuine provision on a plausible question.

`scripts/purge_web_boilerplate.py` cleaned the rows that were already there.
These tests cover the other half -- that a re-ingest does not put them back.
"""

from __future__ import annotations

import logging

import pytest

from rag_eval.legal.ingestion.converter import clean_legal_text, strip_site_chrome

STATUTE = """NGHỊ ĐỊNH
Quy định xử phạt vi phạm hành chính về trật tự, an toàn giao thông

Điều 7. Xử phạt người điều khiển xe mô tô, xe gắn máy
7. Phạt tiền từ 4.000.000 đồng đến 6.000.000 đồng đối với người điều khiển xe
thực hiện một trong các hành vi vi phạm sau đây:
c) Không chấp hành hiệu lệnh của đèn tín hiệu giao thông;

Điều 55. Hiệu lực thi hành
1. Nghị định này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2025.
"""

# Reproduced from what was actually stored, shortened. The sidebar label comes
CHROME = """Tham khảo thêm
Mức phạt với người chưa đủ tuổi điều khiển phương tiện giao thông từ 1/1/2025
(Chinhphu.vn) - Tổng Bí thư Tô Lâm đã ký ban hành Nghị quyết số 57-NQ/TW
Chi tiết PHỔ ĐIỂM KỲ THI TỐT NGHIỆP THPT 2026
Gọi tổng đài Góp ý qua Zalo
BÁO ĐIỆN TỬ CHÍNH PHỦ Tổng Biên tập: Nguyễn Hồng Sâm
Giấy phép số: 19/GP-CBC, cấp ngày 10/5/2024.
Trụ sở: 16 Lê Hồng Phong - Ba Đình - Hà Nội.
Email: thongtinchinhphu@chinhphu.vn.
"""

# A statute long enough that the furniture lands in the tail, as it does in the
BODY = STATUTE * 4


def test_the_furniture_goes_and_the_statute_stays() -> None:
    cleaned = strip_site_chrome(BODY + CHROME)
    assert "Tham khảo thêm" not in cleaned
    assert "Tổng Biên tập" not in cleaned
    assert "PHỔ ĐIỂM" not in cleaned
    # The last real provision has to survive intact -- the chrome hangs off it,
    assert "Điều 55. Hiệu lực thi hành" in cleaned
    assert "01 tháng 01 năm 2025" in cleaned
    assert "4.000.000 đồng đến 6.000.000 đồng" in cleaned


def test_a_clean_document_is_returned_unchanged() -> None:
    """Ten of the thirteen corpus documents carry no marker at all."""
    assert strip_site_chrome(BODY) == BODY


def test_a_marker_inside_the_body_is_refused_not_cut(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The safe failure is to keep everything and say so.

    A decree about electronic notification could genuinely name the government
    portal. Truncating on a marker found early would silently drop real
    provisions, which is worse than leaving furniture in.
    """
    text = "Tham khảo thêm\n" + BODY
    with caplog.at_level(logging.WARNING):
        assert strip_site_chrome(text) == text
    assert "not truncating" in caplog.text


def test_cutting_twice_changes_nothing_the_second_time() -> None:
    once = strip_site_chrome(BODY + CHROME)
    assert strip_site_chrome(once) == once


def test_the_whole_loader_path_applies_it() -> None:
    """Asserts on `clean_legal_text`, because that is the funnel every loader --
    txt, pdf, docx -- passes through. A guard wired into only one of them is the
    kind of half-fix this project keeps finding."""
    cleaned = clean_legal_text(BODY + CHROME)
    assert "GP-CBC" not in cleaned
    assert "Điều 55. Hiệu lực thi hành" in cleaned


def test_the_words_that_must_not_trigger_a_cut() -> None:
    """`chinhphu.vn` and Zalo identify the chrome but never anchor the cut.

    Both can appear in a real provision, so they were deliberately left out of
    the pattern. This pins that decision: a document whose tail mentions them
    without any masthead phrase is kept whole.
    """
    text = BODY + "\n2. Thông báo được gửi qua Zalo hoặc cổng chinhphu.vn.\n"
    assert strip_site_chrome(text) == text


def test_the_fixture_really_does_put_the_chrome_in_the_tail() -> None:
    """Guards the guard.

    Every cut test above is only meaningful if the marker sits past the 70%
    line. Shorten BODY and they would pass for the wrong reason: returning the
    text unchanged while asserting on a substring that was never removed.
    """
    text = BODY + CHROME
    assert text.index("Tham khảo thêm") / len(text) > 0.70
