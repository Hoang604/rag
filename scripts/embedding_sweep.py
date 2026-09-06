"""Compares embedding models on this corpus, by measurement rather than reputation.

`intfloat/multilingual-e5-small` was chosen before there was a harness to
choose with. Sprint 2 asks for the comparison to be redone properly, and the
baselines make it worth doing: dense retrieval alone is the strongest single
mode there is -- 80.0 Hit@1 on `test` against 80.0 for the whole fusion -- so
the embedding is carrying the system and a better one moves everything.

No database is touched. The comparison is dense-only, the corpus is 7,112
chunks, and brute-force cosine over that in memory is both faster than
maintaining a vector column per candidate and immune to an index accidentally
becoming part of what is being compared.

Each model is scored on the same splits, with the same temporal filter, at both
granularities.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from rag_eval.legal.db.connection import close_db_pool, get_db_pool
from rag_eval.legal.eval.smoke_runner import (
    GroundTruth,
    _check_article_match,
    _check_citation_exactness,
)
from rag_eval.legal.mcp.tools import SearchHit
from rag_eval.legal.schemas import get_vietnam_today

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
SETS = {
    "tuned": FIXTURES / "smoke_queries.jsonl",
    "dev": FIXTURES / "smoke_queries_holdout.jsonl",
    "test": FIXTURES / "smoke_queries_test.jsonl",
    "qrels200": FIXTURES / "qrels_dev.jsonl",
}


@dataclass(frozen=True)
class Candidate:
    """A model and the input convention it was trained with.

    The prefixes are not decoration. e5 is trained asymmetrically, and a query
    embedded without "query: " lands in the wrong region of its space -- the
    kind of mistake that looks like the model being bad at Vietnamese.
    """

    name: str
    query_prefix: str = ""
    passage_prefix: str = ""
    note: str = ""


CANDIDATES: tuple[Candidate, ...] = (
    Candidate(
        "intfloat/multilingual-e5-small",
        "query: ",
        "passage: ",
        "đang dùng, 384 chiều",
    ),
    Candidate(
        "intfloat/multilingual-e5-base", "query: ", "passage: ", "cùng họ, 768 chiều"
    ),
    Candidate(
        "bkai-foundation-models/vietnamese-bi-encoder",
        note="huấn luyện riêng cho tiếng Việt, 768",
    ),
    Candidate("keepitreal/vietnamese-sbert", note="tiếng Việt, 768"),
    Candidate("BAAI/bge-m3", note="đa ngữ cỡ lớn, 1024"),
)


def _load_set(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _encode(model: Any, texts: list[str], prefix: str, batch: int) -> np.ndarray:
    vectors = model.encode(
        [prefix + t for t in texts] if prefix else texts,
        batch_size=batch,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return np.asarray(vectors, dtype=np.float32)


def _score(
    query_vectors: np.ndarray,
    passage_vectors: np.ndarray,
    live_mask: np.ndarray,
    chunks: list[dict[str, Any]],
    items: list[dict[str, Any]],
    strict: bool,
) -> dict[str, float]:
    matches = _check_citation_exactness if strict else _check_article_match
    hit1 = hit5 = 0
    reciprocal = 0.0

    # Cosine over normalised vectors is a dot product. Expired provisions are
    # pushed below every live one rather than removed, so the row indices stay
    # aligned with `chunks`.
    similarity = query_vectors @ passage_vectors.T
    similarity[:, ~live_mask] = -2.0

    top = np.argpartition(-similarity, kth=5, axis=1)[:, :5]
    for row, item in enumerate(items):
        order = top[row][np.argsort(-similarity[row, top[row]])]
        truth = GroundTruth.model_validate(item["ground_truth"])
        for rank, index in enumerate(order, start=1):
            chunk = chunks[int(index)]
            hit = SearchHit(
                chunk_id="",
                doc_code=chunk["doc_code"],
                doc_title="",
                path=chunk["path"],
                verbatim_text="",
                contextualized_text="",
                metadata={},
                effective_date="",
                expiration_date=None,
                score=0.0,
            )
            if matches(hit, truth):
                if rank == 1:
                    hit1 += 1
                hit5 += 1
                reciprocal += 1.0 / rank
                break
    total = len(items) or 1
    return {"hit1": hit1 / total, "hit5": hit5 / total, "mrr": reciprocal / total}


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=int, default=64)
    parser.add_argument("--models", nargs="*", default=None)
    args = parser.parse_args()

    pool = await get_db_pool()
    today = get_vietnam_today()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT c.path::text AS path, c.contextualized_text, d.doc_code,
                   c.effective_date, c.expiration_date
            FROM chunks c JOIN documents d ON d.id = c.document_id
            ORDER BY c.path
            """
        )
    await close_db_pool()

    chunks = [dict(r) for r in rows]
    texts = [c["contextualized_text"] for c in chunks]
    live_mask = np.array(
        [
            c["effective_date"] <= today
            and (c["expiration_date"] is None or c["expiration_date"] > today)
            for c in chunks
        ]
    )
    print(f"{len(chunks)} chunk, {int(live_mask.sum())} còn hiệu lực\n")

    loaded = {name: _load_set(path) for name, path in SETS.items()}
    wanted = args.models or [c.name for c in CANDIDATES]

    from sentence_transformers import SentenceTransformer

    for candidate in CANDIDATES:
        if candidate.name not in wanted:
            continue
        print(f"--- {candidate.name}  ({candidate.note}) ---")
        try:
            started = time.perf_counter()
            model = SentenceTransformer(candidate.name)
            load_s = time.perf_counter() - started
        except (OSError, ValueError, RuntimeError) as exc:
            print(f"    không tải được: {str(exc)[:110]}\n")
            continue

        started = time.perf_counter()
        passages = _encode(model, texts, candidate.passage_prefix, args.batch)
        encode_s = time.perf_counter() - started
        print(
            f"    tải {load_s:.0f}s, nhúng {len(texts)} chunk trong {encode_s:.0f}s,"
            f" {passages.shape[1]} chiều"
        )

        for strict in (False, True):
            level = "Khoản/Điểm" if strict else "Điều    "
            cells = []
            for name, items in loaded.items():
                queries = _encode(
                    model,
                    [i["query"] for i in items],
                    candidate.query_prefix,
                    args.batch,
                )
                s = _score(queries, passages, live_mask, chunks, items, strict)
                cells.append(
                    f"{name} {s['hit1'] * 100:5.1f}/{s['hit5'] * 100:5.1f}/{s['mrr']:.3f}"
                )
            print(f"    {level}  " + "   ".join(cells))
        print()
        del model

    print("Hit@1/Hit@5/MRR. Trích dẫn cột `test`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
