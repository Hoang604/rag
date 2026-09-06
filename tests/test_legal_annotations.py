"""Unit tests for the evaluation-leakage guard on agent relevance feedback.

These are the tests for the failure the plan rates as risk 1: an agent records
where a held-out question's answer lives, the index memorises the split, and
every score on it stays high while meaning nothing. It does not crash and it
does not warn, so nothing but a test stands between it and a report full of
numbers that are wrong in the flattering direction.
"""

from __future__ import annotations

import pytest

from rag_eval.legal.retrieval.annotations import (
    SplitGuard,
    content_tokens,
    query_fingerprint,
    topic_fingerprint,
)

HELD_OUT = (
    "Đi xe máy không đúng phần đường, làn đường quy định thì bị phạt bao nhiêu tiền?"
)


@pytest.mark.parametrize(
    ("label", "disguise"),
    [
        ("nguyên văn", HELD_OUT),
        (
            "không dấu",
            "Di xe may khong dung phan duong, lan duong quy dinh thi bi phat bao nhieu tien?",
        ),
        ("viết hoa", HELD_OUT.upper()),
        ("thêm filler", f"cho hỏi {HELD_OUT} ạ ???"),
        ("lịch sự", f"anh chị cho em hỏi {HELD_OUT} vậy ạ"),
        ("đảo trật tự", " ".join(reversed(HELD_OUT.replace("?", "").split()))),
        ("teencode", HELD_OUT.replace("không", "ko").replace("bao nhiêu", "bn")),
        ("cắt cụt", "Đi xe máy không đúng phần đường, làn đường quy định"),
        ("bỏ dấu câu", HELD_OUT.replace(",", "").replace("?", "")),
    ],
)
def test_guard_blocks_every_disguise(label: str, disguise: str) -> None:
    """A held-out question must not leak through any restating of it."""
    guard = SplitGuard.from_queries([HELD_OUT])
    assert guard.blocks(disguise), f"{label} lọt qua guard"


def test_guard_passes_an_unrelated_question() -> None:
    """The guard must not be a blanket refusal, or it destroys all signal."""
    guard = SplitGuard.from_queries([HELD_OUT])
    assert not guard.blocks("thủ tục sang tên xe máy cũ gồm những bước nào")


def test_guard_blocks_every_question_in_its_own_split() -> None:
    split = [
        HELD_OUT,
        "Ô tô vượt đèn đỏ phạt bao nhiêu?",
        "Nồng độ cồn vượt quá 0,4 miligam thì xử lý thế nào?",
    ]
    guard = SplitGuard.from_queries(split)
    assert all(guard.blocks(query) for query in split)


def test_guard_withholds_when_there_is_too_little_to_judge() -> None:
    """A one-word annotation cannot be cleared, so it is refused."""
    guard = SplitGuard.from_queries([HELD_OUT])
    assert guard.blocks("phạt")


def test_none_guard_blocks_nothing() -> None:
    assert not SplitGuard.none().blocks(HELD_OUT)


def test_fingerprint_ignores_accents_case_and_punctuation() -> None:
    assert query_fingerprint("Xe máy vượt đèn đỏ?") == query_fingerprint(
        "xe may vuot den do"
    )


def test_topic_fingerprint_ignores_order_and_listed_filler() -> None:
    assert topic_fingerprint("xin hỏi xe máy vượt đèn đỏ ạ") == topic_fingerprint(
        "đèn đỏ vượt xe máy"
    )


def test_filler_outside_the_stoplist_is_caught_by_containment_not_the_hash() -> None:
    """ "cho" stays a content word because "chở" folds onto it.

    So padding with "cho hỏi" does move the fingerprint, and the guard has to
    catch it the other way. This asserts the division of labour rather than
    pretending the hash covers everything.
    """
    padded = "cho hỏi xe máy vượt đèn đỏ"
    assert topic_fingerprint(padded) != topic_fingerprint("xe máy vượt đèn đỏ")
    assert SplitGuard.from_queries(["xe máy vượt đèn đỏ"]).blocks(padded)


def test_content_tokens_drop_particles_and_single_letters() -> None:
    assert content_tokens("cho hỏi xe máy vượt đèn đỏ ạ") == {
        "cho",
        "xe",
        "may",
        "vuot",
        "den",
        "do",
    }


def test_distinct_questions_keep_distinct_fingerprints() -> None:
    assert topic_fingerprint("xe máy vượt đèn đỏ") != topic_fingerprint(
        "ô tô đi vào đường cấm"
    )
