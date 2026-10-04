from __future__ import annotations

import logging
from typing import Final

from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

_embedding_model_cache: dict[str, SentenceTransformer] = {}

DEFAULT_EMBEDDING_MODEL: Final[str] = "Qwen/Qwen3-Embedding-0.6B"
DEFAULT_EMBEDDING_DIM: Final[int] = 512


def get_embedding_model(
    model_name: str = DEFAULT_EMBEDDING_MODEL,
    truncate_dim: int = DEFAULT_EMBEDDING_DIM,
) -> SentenceTransformer | None:
    """Loads and caches the SentenceTransformer embedding model with GPU acceleration."""
    cache_key = f"{model_name}:{truncate_dim}"
    if cache_key in _embedding_model_cache:
        return _embedding_model_cache[cache_key]

    try:
        import torch
        from sentence_transformers import SentenceTransformer

        device = "cuda" if torch.cuda.is_available() else "cpu"
        model_kwargs = (
            {"torch_dtype": torch.float16}
            if device == "cuda"
            else {"torch_dtype": torch.float32}
        )
        model = SentenceTransformer(
            model_name,
            truncate_dim=truncate_dim,
            model_kwargs=model_kwargs,
            device=device,
        )
        if model.tokenizer is not None:
            model.tokenizer.padding_side = "left"
        model.eval()
        if device == "cuda":
            logger.info(
                "Loaded embedding model %s (dim=%d) on GPU (CUDA FP16).",
                model_name,
                truncate_dim,
            )
        else:
            logger.info(
                "Loaded embedding model %s (dim=%d) on CPU.",
                model_name,
                truncate_dim,
            )

        _embedding_model_cache[cache_key] = model
        return model
    except (ImportError, RuntimeError, OSError, ValueError) as exc:
        logger.debug(
            "Failed to load sentence-transformers model %s: %s", model_name, exc
        )
        return None


def compute_chunk_embeddings(
    texts: list[str],
    model_name: str = DEFAULT_EMBEDDING_MODEL,
    batch_size: int = 128,
    is_query: bool = False,
    truncate_dim: int = DEFAULT_EMBEDDING_DIM,
) -> list[list[float] | None]:
    """Generates dense vector embeddings using sentence-transformers with GPU FP16 and inference_mode support."""
    if not texts:
        return []

    model = get_embedding_model(model_name, truncate_dim=truncate_dim)
    if model is None:
        return [None] * len(texts)

    try:
        if "e5" in model_name.lower():
            prefix = "query: " if is_query else "passage: "
            formatted = [
                f"{prefix}{t}" if not t.startswith(("query: ", "passage: ")) else t
                for t in texts
            ]
        else:
            formatted = texts

        try:
            import torch

            with torch.inference_mode():
                embeddings = model.encode(
                    formatted,
                    batch_size=batch_size,
                    normalize_embeddings=True,
                    show_progress_bar=len(texts) > 100,
                    convert_to_numpy=True,
                )
        except (ImportError, AttributeError):
            embeddings = model.encode(
                formatted,
                batch_size=batch_size,
                normalize_embeddings=True,
                show_progress_bar=len(texts) > 100,
                convert_to_numpy=True,
            )
        return [emb.tolist() for emb in embeddings]
    except (RuntimeError, ValueError, TypeError) as exc:
        logger.debug("Embedding generation fallback to None: %s", exc)
        return [None] * len(texts)
