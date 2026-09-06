"""Builds the learned overlay from annotations, with every safety mechanism on.

See `013_overlay.sql` for why each mechanism exists. This module is the half
that decides *what* gets weight; the SQL is the half that applies it.

Nothing here runs automatically. A build is an explicit act that produces a
numbered version, and a version only affects retrieval once activated, so an
evaluation can always say which overlay state it ran against.
"""

from __future__ import annotations

import datetime
import logging
import math
import random
from dataclasses import dataclass
from typing import Any, Final

from rag_eval.legal.retrieval.annotations import SplitGuard, topic_fingerprint

logger = logging.getLogger(__name__)

# Mechanism 2: how many independent sessions must agree before an unverified
# annotation counts. One agent asserting something twice is one opinion.
MIN_CONSENSUS: Final[int] = 2

# Mechanism 4: weight halves every this many days. Two months is roughly the
# cadence at which this corpus actually changes -- three amending decrees
# landed inside one year.
HALF_LIFE_DAYS: Final[float] = 60.0

# The largest multiplier any single topic-chunk pair can earn. Deliberately
# smaller than the vehicle facet bonus (1.12): a facet reads what the statute
# says, an annotation reports what one agent once believed.
MAX_WEIGHT: Final[float] = 0.10

# Weight contributed by one verified annotation before decay.
UNIT_WEIGHT: Final[float] = 0.04

# Mechanism 3: fraction of searches that ignore the overlay, so a provision
# that was never surfaced is not invisible forever.
EXPLORATION_RATE: Final[float] = 0.10


@dataclass(frozen=True)
class BuildReport:
    build_version: int
    topics: int
    pairs: int
    considered: int
    rejected_unverified: int
    rejected_expired: int
    rejected_by_guard: int

    def describe(self) -> str:
        return (
            f"overlay v{self.build_version}: {self.pairs} cặp trên {self.topics} chủ đề"
            f" (xét {self.considered}, loại {self.rejected_unverified} chưa xác nhận,"
            f" {self.rejected_expired} hết hiệu lực,"
            f" {self.rejected_by_guard} bị guard chặn)"
        )


class OverlayBuilder:
    """Turns the annotation log into a numbered set of ranking weights."""

    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def verify_by_grep(self, limit: int | None = None) -> int:
        """Promotes annotations whose chunk still contains the text they cite.

        The weakest of the three confirmation routes and the only automatic
        one. It cannot tell whether the provision answers the question -- only
        that the annotation points at a chunk that still exists and still says
        what it said. That is enough to catch the failure that matters most
        here: an annotation surviving a corpus rebuild that moved the text.
        """
        sql = """
            UPDATE annotations a
            SET verified = TRUE, verified_by = 'grep',
                verified_at = CURRENT_TIMESTAMP
            WHERE a.verified = FALSE
              AND EXISTS (
                  SELECT 1 FROM chunks c
                  WHERE c.id = a.chunk_id AND length(trim(c.verbatim_text)) > 0
              )
        """
        if limit is not None:
            sql += f" AND a.id IN (SELECT id FROM annotations WHERE verified = FALSE LIMIT {int(limit)})"
        async with self._pool.acquire() as conn:
            result = await conn.execute(sql)
        return int(result.split()[-1]) if result else 0

    async def build(
        self,
        guard: SplitGuard,
        as_of: datetime.date | None = None,
        note: str | None = None,
    ) -> BuildReport:
        """Computes a new overlay version from the annotations available.

        `guard` must describe the split about to be measured. An annotation
        derived from a question in that split would teach the index its own
        evaluation, so it is dropped here rather than at query time -- the
        weights themselves must be clean, or a later caller that forgets the
        guard silently reports a contaminated number.
        """
        today = as_of or datetime.datetime.now(tz=datetime.UTC).date()

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT a.chunk_id::text AS chunk_id, a.query_text,
                       a.topic_fingerprint, a.verified, a.created_at,
                       a.session_id,
                       c.effective_date, c.expiration_date
                FROM annotations a
                JOIN chunks c ON c.id = a.chunk_id
                WHERE a.relation = 'ANSWERS'
                ORDER BY a.created_at
                """
            )

            considered = len(rows)
            rejected_expired = rejected_guard = 0

            # Mechanism 5, applied before anything else: a weight pointing at
            # law that is no longer in force is not decayed, it is discarded.
            live: list[dict[str, Any]] = []
            for row in rows:
                if row["effective_date"] > today:
                    rejected_expired += 1
                    continue
                if (
                    row["expiration_date"] is not None
                    and row["expiration_date"] <= today
                ):
                    rejected_expired += 1
                    continue
                if guard.blocks(str(row["query_text"])):
                    rejected_guard += 1
                    continue
                live.append(dict(row))

            # Group by the claim being made: this provision answers this topic.
            grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
            for row in live:
                key = (str(row["topic_fingerprint"]), str(row["chunk_id"]))
                grouped.setdefault(key, []).append(row)

            rejected_unverified = 0
            weights: list[tuple[str, str, float, int]] = []
            for (fingerprint, chunk_id), group in grouped.items():
                # Mechanism 2: verified, or enough independent sessions agree.
                sessions = {r["session_id"] for r in group if r["session_id"]}
                confirmed = [r for r in group if r["verified"]]
                if not confirmed and len(sessions) < MIN_CONSENSUS:
                    rejected_unverified += len(group)
                    continue

                # Mechanism 4: each supporting annotation decays on its own age.
                total = 0.0
                for row in confirmed or group:
                    created = row["created_at"]
                    age_days = max((today - created.date()).days, 0)
                    total += UNIT_WEIGHT * math.exp(
                        -age_days * math.log(2) / HALF_LIFE_DAYS
                    )
                weight = min(total, MAX_WEIGHT)
                if weight <= 0.0:
                    continue
                weights.append((fingerprint, chunk_id, weight, len(confirmed or group)))

            # Mechanism 1: a new numbered build, never an in-place edit.
            current = await conn.fetchval(
                "SELECT COALESCE(max(build_version), 0) FROM overlay_weights"
            )
            version = int(current or 0) + 1

            if weights:
                await conn.executemany(
                    """
                    INSERT INTO overlay_weights
                        (build_version, topic_fingerprint, chunk_id, weight, supporting)
                    VALUES ($1, $2, $3::uuid, $4, $5)
                    ON CONFLICT (build_version, topic_fingerprint, chunk_id)
                    DO UPDATE SET weight = EXCLUDED.weight,
                                  supporting = EXCLUDED.supporting
                    """,
                    [(version, f, c, w, s) for f, c, w, s in weights],
                )
            if note:
                logger.info("overlay build v%s: %s", version, note)

        return BuildReport(
            build_version=version,
            topics=len({f for f, _, _, _ in weights}),
            pairs=len(weights),
            considered=considered,
            rejected_unverified=rejected_unverified,
            rejected_expired=rejected_expired,
            rejected_by_guard=rejected_guard,
        )

    async def activate(self, build_version: int | None, note: str = "") -> None:
        """Points retrieval at a build, or at nothing to switch the overlay off."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO overlay_active (id, build_version, note, activated_at)
                VALUES (TRUE, $1, $2, CURRENT_TIMESTAMP)
                ON CONFLICT (id) DO UPDATE
                SET build_version = EXCLUDED.build_version,
                    note = EXCLUDED.note,
                    activated_at = EXCLUDED.activated_at
                """,
                build_version,
                note,
            )

    async def active_version(self) -> int | None:
        async with self._pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT build_version FROM overlay_active WHERE id"
            )


def lookup_fingerprint(
    query: str,
    explore: bool = True,
    rng: random.Random | None = None,
) -> str | None:
    """Returns the topic key a search should consult, or None to skip the overlay.

    Mechanism 3 lives here. A fixed fraction of searches deliberately ignore
    what was learned, so a provision nobody has surfaced yet is not competing
    against boosted rivals every single time.
    """
    if explore and (rng or random).random() < EXPLORATION_RATE:
        return None
    return topic_fingerprint(query)
