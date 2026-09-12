"""Unit tests for the trajectory metric that decides which questions want a sum.

This exists because the first version of that decision was wrong in a way that
made the system look worse than it is. `classify_intent` is built for ranking,
where treating a near-penalty question as a penalty one costs a little
precision and nothing else. Used as a measurement it accepted questions whose
answers are a multiplier or a count, then scored the engine as having failed to
state an amount nobody asked for -- four of five flagged cases, and a reported
88.9% where the honest figure was 100%.
"""

from __future__ import annotations

import pytest

from rag_eval.legal.eval.trajectory import _asks_for_a_sum


@pytest.mark.parametrize(
    "question",
    [
        "xe máy vượt đèn đỏ phạt bao nhiêu tiền",
        "ô tô đi vào đường cấm bị xử phạt thế nào",
        "mức phạt cho hành vi chở quá số người quy định",
        "không đội mũ bảo hiểm bị phạt bao nhiêu",
    ],
)
def test_questions_whose_answer_is_an_amount(question: str) -> None:
    assert _asks_for_a_sum(question)


@pytest.mark.parametrize(
    ("question", "why"),
    [
        ("mức phạt với tổ chức bằng mấy lần cá nhân", "câu trả lời là bội số"),
        ("một vi phạm có bao nhiêu hình thức xử phạt chính", "câu trả lời là số đếm"),
        ("cơ quan nào cấp giấy phép xe ưu tiên", "câu trả lời là một cơ quan"),
        ("thiết bị an toàn cho trẻ em là gì", "câu hỏi định nghĩa"),
        ("ai có thẩm quyền xử phạt tại chỗ", "câu trả lời là chủ thể"),
        ("giấy phép lái xe bị tước bao nhiêu tháng", "câu trả lời là thời hạn"),
    ],
)
def test_questions_that_only_look_like_they_want_an_amount(
    question: str, why: str
) -> None:
    assert not _asks_for_a_sum(question), why
