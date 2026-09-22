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
DEFAULT_MODEL: Final = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
DEFAULT_MAX_LENGTH: Final = 256

# Cross-encoder scores are unbounded logits; RRF scores sit near 0.02-0.05.
DEFAULT_BLEND: Final = 1.0

# Global singleton cache for loaded CrossEncoder models to avoid duplicating ~470MB weights
_reranker_model_cache: dict[tuple[str, int], Any] = {}


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
        max_length: int = DEFAULT_MAX_LENGTH,
        blend: float = DEFAULT_BLEND,
        model: Any | None = None,
        max_cache_size: int = 2048,
    ) -> None:
        self._model_name = model_name
        self._max_length = max_length
        self._blend = blend
        # Anything exposing `predict(pairs) -> list[float]`. Supplied, it is
        self._model: Any | None = model
        self._score_cache: dict[tuple[str, str], float] = {}
        self._max_cache_size = max_cache_size

    @property
    def blend(self) -> float:
        """How much of the order comes from the cross-encoder, 0..1."""
        return self._blend

    @blend.setter
    def blend(self, value: float) -> None:
        self._blend = value

    def _load(self) -> Any:
        if self._model is not None:
            return self._model

        cache_key = (self._model_name, self._max_length)
        if cache_key in _reranker_model_cache:
            self._model = _reranker_model_cache[cache_key]
            return self._model

        try:
            import torch
            from sentence_transformers import CrossEncoder

            device = "cuda" if torch.cuda.is_available() else "cpu"
            model = CrossEncoder(
                self._model_name, max_length=self._max_length, device=device
            )
            if hasattr(model, "model") and hasattr(model.model, "eval"):
                model.model.eval()
            if (
                device == "cuda"
                and hasattr(model, "model")
                and hasattr(model.model, "half")
            ):
                model.model.half()
                logger.info(
                    "Loaded CrossEncoder %s on GPU (CUDA FP16).", self._model_name
                )
            else:
                logger.info("Loaded CrossEncoder %s on CPU.", self._model_name)

            _reranker_model_cache[cache_key] = model
            self._model = model
            return model
        except (ImportError, RuntimeError, OSError, ValueError) as exc:
            logger.debug(
                "Failed to load CrossEncoder with acceleration %s: %s, fallback to basic load",
                self._model_name,
                exc,
            )
            from sentence_transformers import CrossEncoder

            model = CrossEncoder(self._model_name, max_length=self._max_length)
            _reranker_model_cache[cache_key] = model
            self._model = model
            return model

    async def warm(self) -> None:
        await asyncio.to_thread(self._load)

    def _score_sync(self, query: str, texts: list[str]) -> list[float]:
        pairs = [(query, text) for text in texts]
        results: list[float | None] = [None] * len(pairs)
        uncached_indices: list[int] = []
        uncached_pairs: list[tuple[str, str]] = []

        for idx, pair in enumerate(pairs):
            if pair in self._score_cache:
                results[idx] = self._score_cache[pair]
            else:
                uncached_indices.append(idx)
                uncached_pairs.append(pair)

        if uncached_pairs:
            model = self._load()
            try:
                import torch

                with torch.inference_mode():
                    raw_scores = model.predict(
                        uncached_pairs,
                        batch_size=32,
                        show_progress_bar=False,
                        convert_to_numpy=True,
                    )
            except (ImportError, AttributeError, TypeError):
                raw_scores = model.predict(uncached_pairs)

            scores_list = [float(s) for s in raw_scores]
            for idx, score in zip(uncached_indices, scores_list, strict=False):
                results[idx] = score
                pair = pairs[idx]
                if len(self._score_cache) >= self._max_cache_size:
                    try:
                        first_key = next(iter(self._score_cache))
                        del self._score_cache[first_key]
                    except StopIteration:
                        pass
                self._score_cache[pair] = score

        return [s if s is not None else 0.0 for s in results]

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
        reordered = []
        for position in order:
            hit = hits[position]
            if hasattr(hit, "model_copy"):
                hit = hit.model_copy(update={"rerank_score": scores[position]})
            reordered.append(hit)
        return reordered[:top_k] if top_k else reordered
