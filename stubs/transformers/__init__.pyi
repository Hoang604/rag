"""Type stubs for transformers."""

from collections.abc import Sequence
from typing import Any

import torch
from torch import nn

__all__ = [
    "AutoModel",
    "AutoTokenizer",
    "BatchEncoding",
    "PreTrainedModel",
    "PreTrainedTokenizerBase",
]


class BatchEncoding(dict[str, Any]):
    def to(self, device: torch.device | str) -> BatchEncoding: ...


class PreTrainedTokenizerBase:
    def __call__(
        self,
        text: str | Sequence[str],
        padding: bool | str = ...,
        truncation: bool | str = ...,
        max_length: int | None = ...,
        return_tensors: str | None = ...,
        **kwargs: Any,
    ) -> BatchEncoding: ...


class AutoTokenizer:
    @classmethod
    def from_pretrained(
        cls,
        pretrained_model_name_or_path: str,
        **kwargs: Any,
    ) -> PreTrainedTokenizerBase: ...


class PreTrainedModel(nn.Module):
    def __call__(self, *args: Any, **kwargs: Any) -> tuple[torch.Tensor, ...]: ...
    def to(self, device: torch.device | str | None = ..., dtype: torch.dtype | None = ...) -> PreTrainedModel: ...  # pyright: ignore[reportIncompatibleMethodOverride]
    def half(self) -> PreTrainedModel: ...
    def eval(self) -> PreTrainedModel: ...


class AutoModel:
    @classmethod
    def from_pretrained(
        cls,
        pretrained_model_name_or_path: str,
        **kwargs: Any,
    ) -> PreTrainedModel: ...
