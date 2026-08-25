"""Type stubs for fastembed."""

from collections.abc import Iterable
from typing import Any

import numpy as np
from numpy.typing import NDArray

class TextEmbedding:
    def __init__(
        self,
        model_name: str = ...,
        cache_dir: str | None = ...,
        threads: int | None = ...,
        **kwargs: Any,
    ) -> None: ...
    def embed(
        self,
        documents: str | Iterable[str],
        batch_size: int = ...,
        parallel: int | None = ...,
        **kwargs: Any,
    ) -> Iterable[NDArray[np.float32]]: ...
