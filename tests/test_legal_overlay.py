"""Unit tests for the overlay's topic key and its exploration mechanism.

The parts that need a database -- the promotion gate, decay, effectiveness
invalidation -- are exercised by `scripts/overlay_eval.py` against the real
corpus. What is tested here is the piece that decides whether the overlay can
fire at all, because two earlier versions of it could not and neither failed
loudly: an exact hash of a question's words matches only that question asked
again in the same words, so the feature would have sat inert while every test
of its plumbing passed.
"""

from __future__ import annotations

import random

from rag_eval.legal.retrieval.overlay import (
    EXPLORATION_RATE,
    MIN_TOPIC_TOKENS,
    TOPIC_TOKENS,
    _topic_tokens,
    lookup_tokens,
)

# Structural words are everywhere in this corpus; offence words are not. Real
FREQUENCY = {
    "bao": 3500,
    "the": 3000,
    "xe": 5000,
    "may": 4000,
    "phat": 3000,
    "dieu": 6000,
    "khoan": 6000,
    "quy": 6000,
    "dinh": 5700,
    "xu": 2000,
    "ly": 2000,
    "vuot": 300,
    "den": 250,
    "do": 240,
    "con": 120,
    "nong": 110,
    "oto": 900,
}


def test_topic_tokens_keep_the_distinctive_words() -> None:
    tokens = _topic_tokens("xe máy vượt đèn đỏ phạt bao nhiêu", FREQUENCY)
    assert {"vuot", "den", "do"} <= set(tokens)


def test_topic_tokens_are_capped_and_sorted() -> None:
    tokens = _topic_tokens(
        "xe máy vượt đèn đỏ phạt bao nhiêu tiền theo quy định hiện hành", FREQUENCY
    )
    assert len(tokens) <= TOPIC_TOKENS
    assert list(tokens) == sorted(tokens)


def test_two_phrasings_of_one_offence_share_most_of_their_key() -> None:
    """The property the exact-hash versions did not have.

    Both name the same offence; neither is a restating of the other. An
    overlay keyed on equality saw two unrelated questions here, which is why
    the stored key is the token set and matching is by overlap.
    """
    a = set(_topic_tokens("xe máy vượt đèn đỏ phạt bao nhiêu", FREQUENCY))
    b = set(_topic_tokens("vượt đèn đỏ với xe máy bị xử lý thế nào", FREQUENCY))
    assert a == b, f"{a} != {b}"


def test_different_offences_do_not_share_a_key() -> None:
    a = set(_topic_tokens("xe máy vượt đèn đỏ phạt bao nhiêu", FREQUENCY))
    b = set(_topic_tokens("nồng độ cồn ô tô phạt bao nhiêu", FREQUENCY))
    shared = a & b
    assert len(shared) / min(len(a), len(b)) < 0.6


def test_unaccented_spelling_gives_the_same_key() -> None:
    assert _topic_tokens(
        "xe máy vượt đèn đỏ phạt bao nhiêu", FREQUENCY
    ) == _topic_tokens("xe may vuot den do phat bao nhieu", FREQUENCY)


def test_a_word_the_corpus_has_never_seen_counts_as_distinctive() -> None:
    tokens = _topic_tokens("xe máy chở lồng chim phạt bao nhiêu", FREQUENCY)
    assert "chim" in tokens


def test_a_query_too_short_to_have_a_subject_is_skipped() -> None:
    assert lookup_tokens("phạt", FREQUENCY, explore=False) is None


def test_exploration_sometimes_ignores_the_overlay() -> None:
    """Mechanism 3: without it, whatever was found first wins forever."""
    rng = random.Random(7)
    query = "xe máy vượt đèn đỏ phạt bao nhiêu"
    skipped = sum(
        1 for _ in range(2000) if lookup_tokens(query, FREQUENCY, rng=rng) is None
    )
    assert 0.05 < skipped / 2000 < 0.16
    assert abs(skipped / 2000 - EXPLORATION_RATE) < 0.04


def test_exploration_is_off_when_asked() -> None:
    query = "xe máy vượt đèn đỏ phạt bao nhiêu"
    assert all(
        lookup_tokens(query, FREQUENCY, explore=False) is not None for _ in range(200)
    )


def test_minimum_topic_size_is_enforced() -> None:
    assert MIN_TOPIC_TOKENS >= 2
    short = lookup_tokens("xe máy", FREQUENCY, explore=False)
    assert short is None or len(short) >= MIN_TOPIC_TOKENS
