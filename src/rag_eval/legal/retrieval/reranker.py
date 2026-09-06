"""Cross-encoder reranking over the candidates the fusion returns.

The fusion decides an order by combining two rankings, and never reads a
question and a provision together. A cross-encoder does exactly that, which is
why it is the standard second stage and why the plan expects it to be the
largest single quality gain left.

The measurement that motivates it: over 12,241 scored queries, 916 of 2,573
failures had the right provision sitting at rank 2, and 1,616 had it somewhere
in the top five. Nothing needs to be retrieved better; something needs to
choose better among what was already found.

The candidate text is the contextualised form, not the bare clause. A leaf
provision reads "Điểm c) Không chấp hành hiệu lệnh của đèn tín hiệu giao
thông;" -- which does not say which vehicle it governs or what it costs, both
of which live in the prefix. Scoring the bare text would ask the model to judge
relevance from the fragment a reader cannot use.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Final, Protocol

logger = logging.getLogger(__name__)

# Multilingual MS MARCO reranker: no Vietnamese word segmentation needed, and
# small enough to run on CPU inside a request.
DEFAULT_MODEL: Final = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"

# Cross-encoder scores are unbounded logits; RRF scores sit near 0.02-0.05.
# Blending them additively would let either drown the other, so the fused score
# contributes as a rank-based term instead.
DEFAULT_BLEND: Final = 1.0


class Reranked(Protocol):
    path: str
    contextualized_text: str
    score: float


class CrossEncoderReranker:
    """Reorders retrieved provisions by reading them against the question.

    The model loads lazily and once. Left to the first request it costs several
    seconds on the person waiting, so callers that care should warm it.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        max_length: int = 512,
        blend: float = DEFAULT_BLEND,
    ) -> None:
        self._model_name = model_name
        self._max_length = max_length
        self._blend = blend
        self._model: Any | None = None

    @property
    def blend(self) -> float:
        """How much of the order comes from the cross-encoder, 0..1."""
        return self._blend

    @blend.setter
    def blend(self, value: float) -> None:
        self._blend = value

    def _load(self) -> Any:
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self._model_name, max_length=self._max_length)
        return self._model

    async def warm(self) -> None:
        await asyncio.to_thread(self._load)

    def _score_sync(self, query: str, texts: list[str]) -> list[float]:
        model = self._load()
        pairs = [(query, text) for text in texts]
        return [float(s) for s in model.predict(pairs)]

    async def score(self, query: str, texts: list[str]) -> list[float]:
        if not texts:
            return []
        return await asyncio.to_thread(self._score_sync, query, texts)

    async def rerank(
        self, query: str, hits: list[Any], top_k: int | None = None
    ) -> list[Any]:
        """Returns hits reordered by cross-encoder relevance.

        When `blend` is below 1.0 the original fused order still counts, mixed
        in by reciprocal rank so that two incomparable score scales never have
        to be added together.
        """
        if len(hits) <= 1:
            return hits[:top_k] if top_k else hits

        texts = [h.contextualized_text or h.verbatim_text for h in hits]
        scores = await self.score(query, texts)

        if self._blend >= 1.0:
            order = sorted(range(len(hits)), key=lambda i: -scores[i])
        else:
            by_ce = sorted(range(len(hits)), key=lambda i: -scores[i])
            ce_rank = {index: rank for rank, index in enumerate(by_ce, start=1)}
            order = sorted(
                range(len(hits)),
                key=lambda i: (
                    -(
                        self._blend / (60 + ce_rank[i])
                        + (1.0 - self._blend) / (60 + i + 1)
                    )
                ),
            )

        # Record what actually decided the order. Leaving only the fused score
        # on a reranked list makes the payload self-contradictory -- rank 1
        # carrying a lower number than rank 3 -- and any consumer that sorts
        # by score undoes the reranking it just paid for.
        reordered = []
        for position in order:
            hit = hits[position]
            if hasattr(hit, "model_copy"):
                hit = hit.model_copy(update={"rerank_score": scores[position]})
            reordered.append(hit)
        return reordered[:top_k] if top_k else reordered
