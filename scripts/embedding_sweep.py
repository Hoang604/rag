"""Compares embedding configurations on the evaluation cases' recorded search calls.

    uv run python scripts/embedding_sweep.py
    uv run python scripts/embedding_sweep.py --configs qwen3-512 vietlegal-harrier-1024

Each case's first `search` call is replayed per configuration. Only the semantic branch
depends on the embedding model: its dense ranking is a cosine over that configuration's
passage vectors, its sparse ranking comes from the database, and the two are fused by
reciprocal rank exactly as `hybrid_search` does. The verbatim branch is the live one.
Passage vectors are read from and written to `embedding_cache`, so a configuration is
embedded once. Results are written to experiments/runs/embedding_sweep.json.

When the production configuration is among those run, its replayed outcome is checked
case by case against the live system (`legal-eval`) and every disagreement is listed,
so a drift between this replay and `hybrid_search` cannot go unnoticed.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np

from rag_eval.legal.console import use_utf8_stdout
from rag_eval.legal.db.connection import close_db_pool, get_db_pool
from rag_eval.legal.db.repositories import LegalRepository
from rag_eval.legal.eval.retrieval import EvalCase, load_cases, run_all
from rag_eval.legal.ingestion.embedder import (
    DEFAULT_EMBEDDING_DIM,
    DEFAULT_EMBEDDING_MODEL,
    compute_chunk_embeddings,
    release_embedding_models,
)
from rag_eval.legal.mcp.tools import LegalMCPTools, SentenceTransformerQueryEmbedder
from rag_eval.legal.text import get_vietnam_now, get_vietnam_today

ROOT: Final = Path(__file__).resolve().parents[1]
OUT: Final = ROOT / "experiments" / "runs" / "embedding_sweep.json"
LIMIT: Final = 10
RRF_K: Final = 60
STORE_EVERY: Final = 256


@dataclass(frozen=True)
class Config:
    name: str
    model: str
    dim: int
    query_prompt: str


CONFIGS: Final = (
    Config("qwen3-512", "Qwen/Qwen3-Embedding-0.6B", 512, ""),
    Config(
        "qwen3-512-instruct",
        "Qwen/Qwen3-Embedding-0.6B",
        512,
        "Instruct: Given a web search query, retrieve relevant passages that answer the query\nQuery:",
    ),
    Config(
        "harrier-1024",
        "microsoft/harrier-oss-v1-0.6b",
        1024,
        "Instruct: Given a web search query, retrieve relevant passages that answer the query\nQuery: ",
    ),
    Config(
        "vietlegal-harrier-1024",
        "mainguyen9/vietlegal-harrier-0.6b",
        1024,
        "Instruct: Given a Vietnamese legal question, retrieve relevant legal passages that answer the question\nQuery: ",
    ),
)


@dataclass(frozen=True)
class Chunk:
    path: str
    doc_code: str
    text: str
    effective_date: datetime.date
    expiration_date: datetime.date | None  # None: the document has no announced end of validity


@dataclass(frozen=True)
class Replay:
    """The model-independent parts of one case's search: sparse ranking and verbatim matches."""

    sparse: list[str]
    verbatim: list[str]


def answers(path: str, expected: list[str]) -> bool:
    return any(path == e or path.startswith(e + ".") for e in expected)


async def load_chunks(repo: LegalRepository) -> list[Chunk]:
    rows = await repo.pool.fetch(
        """
        SELECT c.path::text AS path, d.doc_code, c.contextualized_text, c.effective_date, c.expiration_date
        FROM chunks c JOIN documents d ON d.id = c.document_id ORDER BY c.path
        """
    )
    return [
        Chunk(str(r["path"]), str(r["doc_code"]), str(r["contextualized_text"]), r["effective_date"], r["expiration_date"])
        for r in rows
    ]


async def passage_matrix(repo: LegalRepository, config: Config, chunks: list[Chunk]) -> np.ndarray:
    texts = list(dict.fromkeys(c.text for c in chunks))
    vectors = await repo.embeddings.lookup(config.model, config.dim, texts)
    missing = [t for t in texts if t not in vectors]
    print(f"  {config.name}: {len(texts) - len(missing)} cached, {len(missing)} to embed", flush=True)
    for start in range(0, len(missing), STORE_EVERY):
        batch = missing[start : start + STORE_EVERY]
        computed = dict(zip(batch, compute_chunk_embeddings(batch, model_name=config.model, truncate_dim=config.dim), strict=True))
        await repo.embeddings.store(config.model, config.dim, computed, get_vietnam_now())
        vectors |= computed
        print(f"    embedded {min(start + STORE_EVERY, len(missing))}/{len(missing)}", flush=True)
    return np.asarray([vectors[c.text] for c in chunks], dtype=np.float32)


def violation_date(case: EvalCase) -> datetime.date:
    return case.temporal_violation_date or get_vietnam_today()


async def replay(repo: LegalRepository, case: EvalCase) -> Replay:
    candidate_limit = max(LIMIT * 6, 120)
    sparse_hits = await repo.chunks.hybrid_search(
        query_text=case.query,
        query_vector=None,
        t_violation=violation_date(case),
        match_limit=candidate_limit,
        rrf_k=RRF_K,
        doc_codes=case.doc_codes or None,
        path_prefix=None,
    )
    verbatim_hits, _ = await repo.chunks.verbatim_grep(
        query_pattern=case.pattern,
        target_documents=case.doc_codes or None,
        path_prefix=None,
        is_regex=case.is_regex,
        t_violation=violation_date(case),
        match_limit=LIMIT,
    )
    return Replay(sparse=[h.path for h in sparse_hits], verbatim=[h.path for h in verbatim_hits])


def semantic_ranking(case: EvalCase, query_vector: np.ndarray, matrix: np.ndarray, chunks: list[Chunk], sparse: list[str]) -> list[str]:
    on = violation_date(case)
    allowed = np.asarray(
        [
            c.effective_date <= on
            and (c.expiration_date is None or c.expiration_date > on)
            and (not case.doc_codes or c.doc_code in case.doc_codes)
            for c in chunks
        ]
    )
    scores = np.where(allowed, matrix @ query_vector, -np.inf)
    candidate_limit = max(LIMIT * 6, 120)
    top = np.argsort(-scores)[:candidate_limit]
    dense = [chunks[i].path for i in top if np.isfinite(scores[i])]
    fused: dict[str, float] = {}
    for rank, path in enumerate(dense, start=1):
        fused[path] = fused.get(path, 0.0) + 1.0 / (RRF_K + rank)
    for rank, path in enumerate(sparse, start=1):
        fused[path] = fused.get(path, 0.0) + 1.0 / (RRF_K + rank)
    return sorted(fused, key=lambda p: -fused[p])[:LIMIT]


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--configs", nargs="+", choices=[c.name for c in CONFIGS], default=[c.name for c in CONFIGS])
    args = parser.parse_args()

    repo = LegalRepository(await get_db_pool())
    try:
        cases = load_cases()
        chunks = await load_chunks(repo)
        print(f"{len(cases)} cases, {len(chunks)} chunks", flush=True)
        replays = {c.id: await replay(repo, c) for c in cases}
        report: dict[str, dict[str, dict[str, float]]] = {}
        production_found: dict[str, bool] = {}
        for config in (c for c in CONFIGS if c.name in args.configs):
            matrix = await passage_matrix(repo, config, chunks)
            queries = np.asarray(
                compute_chunk_embeddings(
                    [config.query_prompt + c.query for c in cases], model_name=config.model, is_query=True, truncate_dim=config.dim
                ),
                dtype=np.float32,
            )
            rows: dict[str, list[dict[str, float]]] = {"dev": [], "holdout": []}
            for case, query_vector in zip(cases, queries, strict=True):
                semantic = semantic_ranking(case, query_vector, matrix, chunks, replays[case.id].sparse)
                matching = await repo.chunks.paths_matching_pattern(semantic, case.pattern, case.is_regex)
                both = [p for p in semantic if p in matching]
                semantic_only = [p for p in semantic if p not in matching]
                verbatim_only = [p for p in replays[case.id].verbatim if p not in set(semantic)]
                rank = next((i for i, p in enumerate(semantic, start=1) if answers(p, case.expected)), None)
                found = any(answers(p, case.expected) for p in [*both, *semantic_only, *verbatim_only])
                if (config.model, config.dim, config.query_prompt) == (DEFAULT_EMBEDDING_MODEL, DEFAULT_EMBEDDING_DIM, ""):
                    production_found[case.id] = found
                rows[case.split].append(
                    {
                        "found": float(found),
                        "both": float(any(answers(p, case.expected) for p in both)),
                        "semantic_hit": float(rank is not None),
                        "semantic_mrr": 1.0 / rank if rank else 0.0,
                    }
                )
            release_embedding_models()
            report[config.name] = {
                split: {k: sum(r[k] for r in part) / len(part) for k in part[0]} | {"n": float(len(part))}
                for split, part in rows.items()
                if part
            }
            for split, m in report[config.name].items():
                print(
                    f"{config.name:24s} {split:8s} n={int(m['n']):4d} found={m['found']:.1%} both={m['both']:.1%} "
                    f"semantic@{LIMIT}={m['semantic_hit']:.1%} mrr={m['semantic_mrr']:.3f}",
                    flush=True,
                )
        if production_found:
            live = await run_all(LegalMCPTools.build(embedding_engine=SentenceTransformerQueryEmbedder()), cases)
            disagree = sorted(o.id for o in live.outcomes if (o.found_in != "missed") != production_found[o.id])
            print(f"replay vs live system (production config): {len(disagree)} of {len(cases)} cases disagree {disagree}", flush=True)
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    finally:
        await close_db_pool()
    return 0


if __name__ == "__main__":
    use_utf8_stdout()
    sys.exit(asyncio.run(main()))
