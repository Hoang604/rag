"""High-speed PyTorch Dense Candidate Scorer with FP16 CUDA GPU acceleration."""

import time
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Protocol, cast, final

import numpy as np
from numpy.typing import NDArray
from rich.console import Console

if TYPE_CHECKING:
    import torch

console = Console()


class Tokenizer(Protocol):
    """Protocol for Transformer tokenizer callables returning encoded tensor mappings."""

    def __call__(
        self,
        text: list[str] | Sequence[str],
        *,
        padding: bool = ...,
        truncation: bool = ...,
        max_length: int = ...,
        return_tensors: str = ...,
    ) -> Mapping[str, object]: ...


class TokenizerFactory(Protocol):
    """Factory protocol for AutoTokenizer from_pretrained loader."""

    def from_pretrained(
        self, pretrained_model_name_or_path: str, **kwargs: object
    ) -> object: ...


class ModelFactory(Protocol):
    """Factory protocol for AutoModel from_pretrained loader."""

    def from_pretrained(
        self, pretrained_model_name_or_path: str, **kwargs: object
    ) -> object: ...


class CandidateScorer(Protocol):
    """Structural protocol defining candidate re-scoring engines."""

    def score_candidates(
        self,
        query: str,
        candidate_texts: Sequence[str],
        log_timings: bool = ...,
    ) -> tuple[list[float], float]:
        """Compute similarity scores for candidate passages against a query string."""
        ...


@final
class DenseCandidateScorer:
    """Computes dense cosine similarity scores on-demand for candidate passages using PyTorch and FP16 CUDA."""

    model_name: str
    device: "torch.device"
    use_fp16: bool
    tokenizer: Tokenizer
    model: "torch.nn.Module"

    def __init__(
        self,
        model_name: str = "intfloat/multilingual-e5-small",
        device: str | None = None,
        use_fp16: bool = True,
    ) -> None:
        """Initialize local Transformer bi-encoder model on CUDA GPU with FP16 half precision."""
        import torch
        from transformers import AutoModel, AutoTokenizer

        t0 = time.perf_counter()
        self.model_name = model_name

        if device is not None:
            self.device = torch.device(device)
        else:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        self.use_fp16 = use_fp16 and self.device.type == "cuda"
        tok_factory = cast(TokenizerFactory, AutoTokenizer)
        self.tokenizer = cast(Tokenizer, tok_factory.from_pretrained(model_name))

        model_factory = cast(ModelFactory, AutoModel)
        raw_model = cast(torch.nn.Module, model_factory.from_pretrained(model_name))

        if self.use_fp16:
            self.model = raw_model.to(self.device).half()
        else:
            self.model = raw_model.to(self.device)

        _ = self.model.eval()

        init_ms = (time.perf_counter() - t0) * 1000.0
        precision_tag = "FP16" if self.use_fp16 else "FP32"
        console.print(
            f"[dim][DenseCandidateScorer] PyTorch {precision_tag} model loaded on {self.device} in {init_ms:.2f}ms[/dim]"
        )

    def score_candidates(
        self,
        query: str,
        candidate_texts: Sequence[str],
        log_timings: bool = True,
    ) -> tuple[list[float], float]:
        """Embed query and candidate texts on-demand using PyTorch FP16 CUDA, returning cosine similarity scores."""
        if not candidate_texts or not query.strip():
            return [0.0] * len(candidate_texts), 0.0

        import torch
        import torch.nn.functional as F

        if "e5" in self.model_name.lower():
            formatted_query = (
                query if query.startswith("query: ") else f"query: {query}"
            )
            formatted_cands = [
                c if c.startswith("passage: ") else f"passage: {c}"
                for c in candidate_texts
            ]
            all_texts: list[str] = [formatted_query, *formatted_cands]
        else:
            all_texts = [query, *candidate_texts]

        t0 = time.perf_counter()
        raw_inputs = self.tokenizer(
            all_texts,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        )
        inputs: dict[str, torch.Tensor] = {
            str(k): cast(torch.Tensor, v).to(self.device) for k, v in raw_inputs.items()
        }

        with torch.no_grad():
            outputs = cast(tuple[torch.Tensor, ...], self.model(**inputs))
            if "e5" in self.model_name.lower() and "attention_mask" in inputs:
                token_embeddings = outputs[0]
                mask = (
                    inputs["attention_mask"]
                    .unsqueeze(-1)
                    .expand(token_embeddings.size())
                    .float()
                )
                sum_embeddings = torch.sum(token_embeddings * mask, dim=1)
                sum_mask = torch.clamp(mask.sum(dim=1), min=1e-9)
                pooled: torch.Tensor = sum_embeddings / sum_mask
            else:
                pooled = outputs[0][:, 0]
            normalized_embs: torch.Tensor = F.normalize(
                pooled, p=2.0, dim=1
            )

            q_vec: torch.Tensor = normalized_embs[0:1]  # Shape: (1, dim)
            cand_mat: torch.Tensor = normalized_embs[1:]  # Shape: (num_candidates, dim)

            # Vectorized dot product cosine similarity on GPU
            scores_tensor: torch.Tensor = torch.sum(cand_mat * q_vec, dim=1)

        if self.device.type == "cuda":
            torch.cuda.synchronize()

        emb_ms = (time.perf_counter() - t0) * 1000.0
        float_tensor = scores_tensor.to(dtype=torch.float32)
        scores_arr: NDArray[np.float32] = cast(
            NDArray[np.float32], float_tensor.cpu().numpy()
        )
        scores: list[float] = [
            float(scores_arr.item(idx)) for idx in range(len(candidate_texts))
        ]

        if log_timings:
            per_item = emb_ms / len(all_texts)
            precision_tag = "FP16" if self.use_fp16 else "FP32"
            console.print(
                f"[dim]  └─ [Dense Stage] Embedded {len(all_texts)} texts on {self.device} ({precision_tag}) in {emb_ms:.2f}ms ({per_item:.2f}ms/text)[/dim]"
            )

        return scores, emb_ms
