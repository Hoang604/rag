"""High-speed PyTorch Dense Candidate Scorer with FP16 CUDA GPU acceleration."""

import time
from collections.abc import Sequence
from typing import cast, final

import numpy as np
import torch
import torch.nn.functional as F
from numpy.typing import NDArray
from rich.console import Console
from transformers import (
    AutoModel,
    AutoTokenizer,
    PreTrainedModel,
    PreTrainedTokenizerBase,
)

console = Console()


@final
class DenseCandidateScorer:
    """Computes dense cosine similarity scores on-demand for candidate passages using PyTorch and FP16 CUDA."""

    model_name: str
    device: torch.device
    use_fp16: bool
    tokenizer: PreTrainedTokenizerBase
    model: PreTrainedModel

    def __init__(
        self,
        model_name: str = "BAAI/bge-small-en-v1.5",
        device: str | None = None,
        use_fp16: bool = True,
    ) -> None:
        """Initialize local Transformer bi-encoder model on CUDA GPU with FP16 half precision."""
        t0 = time.perf_counter()
        self.model_name = model_name

        if device is not None:
            self.device = torch.device(device)
        else:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        self.use_fp16 = use_fp16 and self.device.type == "cuda"
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        raw_model: PreTrainedModel = AutoModel.from_pretrained(model_name)

        if self.use_fp16:
            self.model = raw_model.to(self.device).half()
        else:
            self.model = raw_model.to(self.device)

        _ = self.model.eval()

        init_ms = (time.perf_counter() - t0) * 1000.0
        precision_tag = "FP16" if self.use_fp16 else "FP32"
        console.print(f"[dim][DenseCandidateScorer] PyTorch {precision_tag} model loaded on {self.device} in {init_ms:.2f}ms[/dim]")

    def score_candidates(
        self,
        query: str,
        candidate_texts: Sequence[str],
        log_timings: bool = True,
    ) -> tuple[list[float], float]:
        """Embed query and candidate texts on-demand using PyTorch FP16 CUDA, returning cosine similarity scores."""
        if not candidate_texts or not query.strip():
            return [0.0] * len(candidate_texts), 0.0

        all_texts: list[str] = [query, *candidate_texts]

        t0 = time.perf_counter()
        inputs = self.tokenizer(
            all_texts,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        ).to(self.device)

        with torch.no_grad():
            outputs: tuple[torch.Tensor, ...] = self.model(**inputs)
            first_token_tensor: torch.Tensor = outputs[0][:, 0]
            normalized_embs: torch.Tensor = F.normalize(first_token_tensor, p=2.0, dim=1)

            q_vec: torch.Tensor = normalized_embs[0:1]  # Shape: (1, dim)
            cand_mat: torch.Tensor = normalized_embs[1:]  # Shape: (num_candidates, dim)

            # Vectorized dot product cosine similarity on GPU
            scores_tensor: torch.Tensor = torch.sum(cand_mat * q_vec, dim=1)

        if self.device.type == "cuda":
            torch.cuda.synchronize()

        emb_ms = (time.perf_counter() - t0) * 1000.0
        float_tensor = scores_tensor.to(dtype=torch.float32)
        scores_arr: NDArray[np.float32] = cast(NDArray[np.float32], float_tensor.cpu().numpy())
        scores: list[float] = [float(scores_arr.item(idx)) for idx in range(len(candidate_texts))]

        if log_timings:
            per_item = emb_ms / len(all_texts)
            precision_tag = "FP16" if self.use_fp16 else "FP32"
            console.print(
                f"[dim]  └─ [Dense Stage] Embedded {len(all_texts)} texts on {self.device} ({precision_tag}) in {emb_ms:.2f}ms ({per_item:.2f}ms/text)[/dim]"
            )

        return scores, emb_ms
