"""Relevance feedback from the agent, and the guard that keeps it out of eval.

`add_metadata` lets an agent record that a chunk answered a question it had to
hunt for. That is relevance feedback -- the same signal click-through data has
carried in IR for decades, except stronger: a click means "this looked
relevant", while this means "I searched, read, and confirmed the answer is
here".

It is also the single most dangerous thing in the system, for a reason that
leaves no trace. If an agent runs the dev questions and records where their
answers live, the index has memorised the evaluation set. Retrieval scores on
that split stay high and stop meaning anything, and no checksum catches it: the
sealed file on disk is untouched, what changed is the index. The failure does
not crash, does not warn, and produces numbers that look better than before.

So the annotation is written with a fingerprint of the question that produced
it, and any consumer measuring a split must exclude every annotation whose
fingerprint appears in that split. `AnnotationStore.for_scoring` is the only
supported read path and it demands the exclusion set, so forgetting it is not
possible by omission -- only by deliberately passing an empty set.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from typing import Any, Final

from rag_eval.legal.text import fold_for_match

# Everything that is not a letter or a digit is separator: statutory questions
# differ by punctuation far more often than they differ in meaning.
_NON_WORD: Final = re.compile(r"[^0-9a-z]+")

# Words carrying no topic. The list is short on purpose: folding away tone
# marks makes function words collide with content words, and in this corpus the
# collisions land on the commonest terms there are -- "đèn" folds onto "đến",
# "đỏ" and "độ" onto "đó", "báo" onto "bao", "mức" onto "muc", "người" onto
# "nguoi". Treating those as filler stripped "vượt đèn đỏ" down to "vượt". A
# word stays here only when nothing in traffic law folds onto it.
# fmt: off
_STOPWORDS: Final = frozenset((
    "la", "thi", "va", "hoac", "cua", "voi", "tu", "ngoai", "tren", "duoi",
    "ra", "bi", "duoc", "co", "khong", "chua", "se", "da", "nhe", "oi", "kia",
    "nay", "nhieu", "nao", "sao", "nhu", "vay", "gi", "j", "toi", "em", "anh",
    "chi", "minh", "ho", "ai", "xin", "hoi", "tra", "biet", "giup", "vui",
    "lam", "mot", "cac", "nhung", "moi", "tung",
))
# fmt: on


def _normalise(query: str) -> str:
    """Folds a question to its comparable form: no accents, no case, no marks."""
    return _NON_WORD.sub(" ", fold_for_match(query)).strip()


def query_fingerprint(query: str) -> str:
    """Fingerprints the exact wording, ignoring accents, case and punctuation.

    Accented and unaccented spellings of one question collide here on purpose:
    they are the same evaluation item, so an annotation from one must be
    excluded when scoring the other.
    """
    return hashlib.sha256(_normalise(query).encode("utf-8")).hexdigest()


def topic_fingerprint(query: str) -> str:
    """Fingerprints the content words alone, order and filler discarded.

    The exact fingerprint misses a question padded with "cho hỏi" or trimmed to
    keywords, and those are precisely the forms a robustness set is built from.
    Two different questions sharing a content-word set is possible and would
    exclude an annotation that was in fact safe; that costs a little overlay
    signal. Missing a leak costs the credibility of every number on the split,
    permanently. The asymmetry decides the direction to err in.
    """
    # Single letters go too. Vietnamese politeness particles -- "ạ", "à", "ơi"
    # -- are one syllable and endlessly variable, so enumerating them loses to
    # the next one someone types; length is the property they share.
    tokens = sorted(
        {t for t in _normalise(query).split() if len(t) > 1 and t not in _STOPWORDS}
    )
    return hashlib.sha256(" ".join(tokens).encode("utf-8")).hexdigest()


def content_tokens(query: str) -> frozenset[str]:
    """Returns the topic-bearing tokens of a question."""
    return frozenset(
        t for t in _normalise(query).split() if len(t) > 1 and t not in _STOPWORDS
    )


# An annotation is treated as derived from a split question when this much of
# the smaller token set is shared. Containment rather than Jaccard, because the
# dangerous case is asymmetric: a question trimmed to keywords has few tokens,
# all of them drawn from the held-out original, and Jaccard would score that
# pair low precisely when the leak is total.
_CONTAINMENT_BLOCK: Final = 0.8

# The looser setting, for annotations that provably did not come from running
# the split. Only a near-verbatim restating counts as reuse.
_CONTAINMENT_REUSE: Final = 0.95
_MIN_TOKENS: Final = 2


@dataclass(frozen=True)
class SplitGuard:
    """The set of questions whose annotations must not be visible while scoring.

    Hash equality alone is not enough. It stops a held-out question restated
    without accents, padded with politeness or reordered, but not one where a
    word was abbreviated ("không" to "ko") or the tail was trimmed -- and those
    are exactly the shapes a robustness set is made of. Measured against eight
    disguises of one held-out question, fingerprints caught six; adding
    containment caught all eight.

    There are two levels, and choosing between them is a judgement about where
    the annotations came from, not a tuning knob.

    `topic_level=True`, the default, blocks anything about the same subject. It
    is the only safe setting when the annotations might have been produced by
    running the split itself -- an agent that answered the dev questions and
    logged where it looked has memorised them, and paraphrase does not undo
    that.

    `topic_level=False` blocks only a near-verbatim restating. It is correct
    when the annotations demonstrably predate the evaluation and came from
    different questions, which is the situation the overlay is designed for:
    real users repeat topics, and treating that repetition as contamination
    would define the feature out of existence.

    The collision this resolves is worth stating exactly. The overlay fires on
    equality of content-token sets; the strict guard blocks at 0.8 containment,
    which includes every such equality. Its blocked set therefore contains the
    overlay's firing set outright, so under the strict guard an overlay cannot
    show a benefit on a measured split no matter how well it works. Running the
    experiment that way would quietly prove nothing.
    """

    fingerprints: frozenset[str]
    token_sets: tuple[frozenset[str], ...]
    # token -> indices of split questions containing it, so a candidate is
    # compared only against questions it shares a word with.
    _index: dict[str, tuple[int, ...]]
    # How much shared vocabulary is treated as the same question. See
    # `from_queries` for why this is not one fixed number.
    threshold: float = _CONTAINMENT_BLOCK

    @classmethod
    def from_queries(cls, queries: list[str], topic_level: bool = True) -> SplitGuard:
        fingerprints: set[str] = set()
        token_sets: list[frozenset[str]] = []
        index: dict[str, list[int]] = {}
        for position, query in enumerate(queries):
            fingerprints.add(query_fingerprint(query))
            fingerprints.add(topic_fingerprint(query))
            tokens = content_tokens(query)
            token_sets.append(tokens)
            for token in tokens:
                index.setdefault(token, []).append(position)
        return cls(
            fingerprints=frozenset(fingerprints),
            token_sets=tuple(token_sets),
            _index={token: tuple(rows) for token, rows in index.items()},
            threshold=_CONTAINMENT_BLOCK if topic_level else _CONTAINMENT_REUSE,
        )

    def blocks(self, query: str) -> bool:
        """Reports whether an annotation from this question would leak the split."""
        if query_fingerprint(query) in self.fingerprints:
            return True
        if topic_fingerprint(query) in self.fingerprints:
            return True

        tokens = content_tokens(query)
        if len(tokens) < _MIN_TOKENS:
            # Too little to judge. Withholding is the cheap error at topic
            # level; at reuse level there is nothing to withhold from.
            return self.threshold <= _CONTAINMENT_BLOCK

        overlaps: dict[int, int] = {}
        for token in tokens:
            for position in self._index.get(token, ()):
                overlaps[position] = overlaps.get(position, 0) + 1

        for position, shared in overlaps.items():
            smaller = min(len(tokens), len(self.token_sets[position]))
            if smaller and shared / smaller >= self.threshold:
                return True
        return False

    @classmethod
    def none(cls) -> SplitGuard:
        """A guard that blocks nothing. Correct only when scoring nothing."""
        return cls(fingerprints=frozenset(), token_sets=(), _index={})


ANSWERS: Final = "ANSWERS"
RELEVANT: Final = "RELEVANT"
MISLEADING: Final = "MISLEADING"
_RELATIONS: Final = frozenset({ANSWERS, RELEVANT, MISLEADING})


@dataclass(frozen=True)
class Annotation:
    chunk_id: str
    query_text: str
    relation: str
    note: str | None
    source: str
    session_id: str | None


class AnnotationStore:
    """Writes and reads agent annotations, never mixing them into the corpus.

    Annotations live in their own table rather than in `chunks.metadata`. Two
    reasons, both load-bearing. Writing into the corpus would make retrieval
    non-reproducible -- running an evaluation twice would give two answers,
    because the first run taught the index. And it would make the annotation
    impossible to withdraw once a split turned out to be contaminated.
    """

    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def record(
        self,
        chunk_id: str,
        query_text: str,
        relation: str = ANSWERS,
        note: str | None = None,
        source: str = "agent",
        session_id: str | None = None,
    ) -> str:
        """Logs one annotation and returns its id."""
        if relation not in _RELATIONS:
            raise ValueError(
                f"relation must be one of {sorted(_RELATIONS)}, got {relation!r}"
            )
        if not query_text.strip():
            raise ValueError("query_text is required: without it there is no guard")

        annotation_id = str(uuid.uuid4())
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO annotations
                    (id, chunk_id, query_text, query_fingerprint,
                     topic_fingerprint, relation, note, source, session_id)
                VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, $8, $9)
                """,
                annotation_id,
                chunk_id,
                query_text,
                query_fingerprint(query_text),
                topic_fingerprint(query_text),
                relation,
                note,
                source,
                session_id,
            )
        return annotation_id

    async def for_scoring(self, guard: SplitGuard) -> list[dict[str, Any]]:
        """Returns annotations safe to use while measuring a split.

        `guard` must be built from every question in the split being measured.
        The fingerprint half runs in SQL because it is an index lookup; the
        containment half runs here, over what survives.
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id::text, chunk_id::text, query_text, relation, note,
                       source, session_id, created_at
                FROM annotations
                WHERE NOT (query_fingerprint = ANY($1::text[]))
                  AND NOT (topic_fingerprint = ANY($1::text[]))
                ORDER BY created_at
                """,
                list(guard.fingerprints),
            )
        return [dict(row) for row in rows if not guard.blocks(str(row["query_text"]))]

    async def counts(self) -> dict[str, int]:
        """Returns how much feedback has accumulated, by relation."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT relation, count(*) AS n FROM annotations GROUP BY relation"
            )
        return {str(row["relation"]): int(row["n"]) for row in rows}
