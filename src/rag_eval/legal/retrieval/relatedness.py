"""Corpus-learned term relatedness, used only where the hand lexicon is silent.

`lexicon.py` holds fifteen colloquial-to-statutory pairs, each written and
checked by a person. That is what makes it trustworthy, and also what caps it
at fifteen. This module covers the questions those fifteen do not reach, using
`term_relatedness` -- which words share a provision more often than chance,
mined by `scripts/build_relatedness.py`.

Three rules shape how little it is allowed to do, and each exists because the
sparse ranker punishes the alternative:

1. **Only when the hand lexicon found nothing.** Where a verified statutory
   phrase is available it is strictly better than a bag of syllables, and
   stacking both would dilute the phrase that was going to work.
2. **At most a few terms.** `expand_query` already caps hand expansions at four
   for a measured reason: every added token spreads `ts_rank` across the whole
   candidate pool. Learned terms are single syllables and dilute harder.
3. **Never expand a term the query already carries**, and never expand the
   interrogatives. On the 118 colloquial questions the most frequent tokens
   clearing any usable floor were `bao`, `thế`, `khác` -- question words, not
   traffic vocabulary. Expanding those reaches everything and ranks nothing.

Loaded once into memory. The table is roughly six thousand rows and the lookup
sits inside every query, so a round trip per term would cost more than the
expansion is worth.
"""

from __future__ import annotations

from typing import Final

import asyncpg

from rag_eval.legal.retrieval.annotations import content_tokens

# Interrogatives and framing words. They pass `content_tokens` because that
_NOT_A_SUBJECT: Final[frozenset[str]] = frozenset(
    {
        "bao",
        "nhieu",
        "the",
        "nao",
        "gi",
        "khac",
        "sao",
        "may",
        "dau",
        "nhu",
        "duoc",
        "phai",
        "co",
        "khong",
        "bi",
        "thi",
        "va",
        "hoac",
    }
)

# How many neighbours a single query term may contribute, and how many terms
MAX_PER_TERM: Final[int] = 2
MAX_TERMS: Final[int] = 3

# A pair below this PPMI is not evidence of anything; the distribution has a
MIN_SCORE: Final[float] = 1.5


class Relatedness:
    """An in-memory view of `term_relatedness`, or an empty one."""

    def __init__(
        self,
        neighbours: dict[str, tuple[str, ...]] | None = None,
        frequency: dict[str, int] | None = None,
    ) -> None:
        self._neighbours = neighbours or {}
        self._frequency = frequency or {}

    @property
    def loaded(self) -> bool:
        return bool(self._neighbours)

    @classmethod
    async def load(cls, pool: asyncpg.Pool) -> Relatedness:
        """Reads the table, or returns an empty instance if it is not there.

        An absent or empty table is a normal state -- the builder has to be run
        after ingestion -- and must degrade to "no learned expansion" rather
        than to an error inside every search.
        """
        try:
            rows = await pool.fetch(
                "SELECT term, related FROM term_relatedness "
                "WHERE score >= $1 ORDER BY term, score DESC",
                MIN_SCORE,
            )
            counts = await pool.fetch("SELECT token, df FROM token_df")
        except asyncpg.PostgresError:
            return cls()

        grouped: dict[str, list[str]] = {}
        for row in rows:
            bucket = grouped.setdefault(str(row["term"]), [])
            if len(bucket) < MAX_PER_TERM:
                bucket.append(str(row["related"]))
        return cls(
            {term: tuple(items) for term, items in grouped.items()},
            {str(r["token"]): int(r["df"]) for r in counts},
        )

    def expand(self, query: str) -> list[str]:
        """Returns the learned terms worth appending to the sparse text.

        Terms already in the query are skipped: re-stating a token the tsquery
        already has adds nothing and costs a slot.
        """
        if not self._neighbours:
            return []

        present = content_tokens(query)
        # Rarest first. Sorted alphabetically -- the first version -- the walk
        subjects = sorted(
            (t for t in present if t not in _NOT_A_SUBJECT),
            key=lambda t: (self._frequency.get(t, 0), t),
        )

        added: list[str] = []
        for term in subjects:
            if len(added) >= MAX_TERMS:
                break
            for related in self._neighbours.get(term, ()):
                if len(added) >= MAX_TERMS:
                    break
                if related in present or related in added:
                    continue
                added.append(related)
        return added
