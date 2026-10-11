from __future__ import annotations

import logging
import threading
from typing import Final

import torch
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

_embedding_model_cache: dict[str, SentenceTransformer] = {}
_model_load_lock = threading.Lock()

DEFAULT_EMBEDDING_MODEL: Final[str] = "Qwen/Qwen3-Embedding-0.6B"
DEFAULT_EMBEDDING_DIM: Final[int] = 512
_REGROW_AFTER: Final[int] = 8


def get_embedding_model(
    model_name: str = DEFAULT_EMBEDDING_MODEL,
    truncate_dim: int = DEFAULT_EMBEDDING_DIM,
    device: str | None = None,
) -> SentenceTransformer:
    """Loads and caches the embedding model: FP16 on GPU, FP32 on CPU; `device` None picks GPU when available."""
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    cache_key = f"{model_name}:{truncate_dim}:{device}"
    with _model_load_lock:
        if cache_key not in _embedding_model_cache:
            _embedding_model_cache[cache_key] = _load_model(model_name, truncate_dim, device)
        return _embedding_model_cache[cache_key]


def _load_model(model_name: str, truncate_dim: int, device: str) -> SentenceTransformer:
    dtype = torch.float16 if device == "cuda" else torch.float32
    model = SentenceTransformer(
        model_name,
        truncate_dim=truncate_dim,
        model_kwargs={"torch_dtype": dtype},
        device=device,
    )
    if model.tokenizer is not None:
        model.tokenizer.padding_side = "left"
    model.eval()
    logger.info("Loaded embedding model %s (dim=%d) on %s (%s).", model_name, truncate_dim, device, dtype)
    return model


def compute_chunk_embeddings(
    texts: list[str],
    model_name: str = DEFAULT_EMBEDDING_MODEL,
    batch_size: int = 32,
    truncate_dim: int = DEFAULT_EMBEDDING_DIM,
) -> list[list[float]]:
    """Embeds texts in input order, longest first, halving the batch on GPU out-of-memory.

    A single text too long for the GPU is embedded on the CPU instead.
    """
    if not texts:
        return []

    model = get_embedding_model(model_name, truncate_dim=truncate_dim)
    order = sorted(range(len(texts)), key=lambda i: -len(texts[i]))
    vectors: dict[int, list[float]] = {}
    size = batch_size
    streak = 0
    position = 0
    with torch.inference_mode():
        while position < len(order):
            batch = order[position : position + size]
            try:
                encoded = model.encode(
                    [texts[i] for i in batch],
                    batch_size=len(batch),
                    normalize_embeddings=True,
                    show_progress_bar=False,
                    convert_to_numpy=True,
                )
            except torch.cuda.OutOfMemoryError:
                torch.cuda.empty_cache()
                if size == 1:
                    logger.warning("Text of %d chars does not fit the GPU, embedding it on the CPU", len(texts[batch[0]]))
                    cpu_model = get_embedding_model(model_name, truncate_dim=truncate_dim, device="cpu")
                    encoded = cpu_model.encode(
                        [texts[batch[0]]], normalize_embeddings=True, show_progress_bar=False, convert_to_numpy=True
                    )
                    vectors[batch[0]] = encoded[0].tolist()
                    position += 1
                    continue
                size //= 2
                streak = 0
                logger.warning("GPU out of memory, embedding batch reduced to %d", size)
                continue
            for index, vector in zip(batch, encoded, strict=True):
                vectors[index] = vector.tolist()
            position += len(batch)
            streak += 1
            if size < batch_size and streak >= _REGROW_AFTER:
                size = min(batch_size, size * 2)
                streak = 0
            if len(texts) > 100 and streak % 10 == 0:
                logger.info("Embedded %d/%d texts (batch %d)", position, len(texts), size)
    return [vectors[i] for i in range(len(texts))]


def release_embedding_models() -> None:
    """Drops every cached embedding model and frees the GPU memory they held."""
    with _model_load_lock:
        _embedding_model_cache.clear()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
