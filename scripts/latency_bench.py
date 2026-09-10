"""Measures request latency and throughput against a running API.

The progress report quotes 207 ms without reranking and about 1.3 s with it,
and 10.29 against 1.95 requests per second. Those came from ad-hoc timings
typed at a shell, which makes them the only figures in the report that nobody
can reproduce. This script exists so they can be.

Three decisions, because the naive version of this measures the wrong thing.

A mean is not reported. Latency distributions here are skewed -- the first
request after startup pays for a cold cross-encoder -- so a mean hides the
shape. p50 and p95 are reported, and warm-up requests are discarded rather
than averaged in.

Throughput is measured separately from latency, at a concurrency the caller
sets. Dividing one by the other is wrong in both directions: it ignores
queueing under load, and it ignores that a reranking server spends its time
in a model that does not release the GIL cooperatively.

Queries come from a fixture, not from one repeated string, because repeating a
single query measures the database's cache rather than the system.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from pathlib import Path

import httpx

from rag_eval.legal.console import use_utf8_stdout

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def _queries(path: Path, count: int) -> list[str]:
    seen: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            seen.append(json.loads(line)["query"])
    if not seen:
        raise SystemExit(f"không có truy vấn nào trong {path}")
    # Cycled rather than sampled, so every run issues the same work.
    return [seen[i % len(seen)] for i in range(count)]


async def _one(
    client: httpx.AsyncClient, url: str, query: str, rerank: bool | None
) -> tuple[float, bool]:
    body: dict[str, object] = {"query": query, "limit": 5}
    if rerank is not None:
        body["rerank"] = rerank
    start = time.perf_counter()
    response = await client.post(url, json=body, timeout=120.0)
    response.raise_for_status()
    elapsed = (time.perf_counter() - start) * 1000.0
    # Whether this request was actually reranked, not whether it asked to be.
    # Reranking is switched off for unaccented queries by design, and
    # `qrels_dev.jsonl` holds 29 of them clustered together. A slice that lands
    # on them measures the cheap path in both modes and reports that reranking
    # is free -- which is how I first read a +9 ms cost as +0 ms.
    hits = response.json().get("hits") or []
    reranked = bool(hits) and hits[0].get("rerank_score") is not None
    return elapsed, reranked


async def _serial(
    client: httpx.AsyncClient, url: str, queries: list[str], rerank: bool | None
) -> tuple[list[float], int]:
    rows = [await _one(client, url, q, rerank) for q in queries]
    return [ms for ms, _ in rows], sum(1 for _, done in rows if done)


async def _concurrent(
    client: httpx.AsyncClient,
    url: str,
    queries: list[str],
    rerank: bool | None,
    concurrency: int,
) -> tuple[float, int]:
    """Returns wall-clock seconds and how many requests succeeded."""
    gate = asyncio.Semaphore(concurrency)
    done = 0

    async def run(query: str) -> None:
        nonlocal done
        async with gate:
            await _one(client, url, query, rerank)
            done += 1

    start = time.perf_counter()
    await asyncio.gather(*(run(q) for q in queries))
    return time.perf_counter() - start, done


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--queries", type=Path, default=FIXTURES / "qrels_dev.jsonl")
    parser.add_argument("--n", type=int, default=40, help="requests measured per mode")
    parser.add_argument("--warmup", type=int, default=3, help="discarded requests")
    parser.add_argument("--concurrency", type=int, default=8)
    args = parser.parse_args()

    url = f"{args.base_url.rstrip('/')}/api/search"
    # Three disjoint slices, not two. The throughput phase used to replay the
    # queries the latency phase had just sent, which was harmless until a query
    # embedding cache was added: every one of them then hit the cache, and the
    # measurement reported 11.76 req/s with rerank on -- above the 7.5 req/s
    # ceiling that 8 workers at a 1,072 ms median can physically reach. The
    # number was measuring the cache.
    total = args.warmup + args.n * 2
    queries = _queries(args.queries, total)
    if len(queries) < total:
        raise SystemExit(
            f"cần {total} câu hỏi khác nhau ({args.warmup} khởi động + {args.n} đo "
            f"độ trễ + {args.n} đo thông lượng), bộ đề chỉ có {len(queries)}"
        )
    warm = queries[: args.warmup]
    for_latency = queries[args.warmup : args.warmup + args.n]
    for_throughput = queries[args.warmup + args.n :]

    async with httpx.AsyncClient() as client:
        health = await client.get(f"{args.base_url.rstrip('/')}/api/health", timeout=30)
        health.raise_for_status()
        print(f"server: {args.base_url}  •  {health.json()}\n")

        print(
            f"{'chế độ':22s}{'p50 ms':>9s}{'p95 ms':>9s}"
            f"{'chậm nhất':>11s}{'req/s @' + str(args.concurrency):>12s}"
            f"{'đã chấm lại':>14s}"
        )
        print("-" * 77)

        for label, rerank in (("không rerank", False), ("có rerank", True)):
            await _serial(client, url, warm, rerank)
            latencies, reranked = await _serial(client, url, for_latency, rerank)
            latencies.sort()
            p50 = statistics.median(latencies)
            # Nearest-rank p95: no interpolation between samples that exist.
            p95 = latencies[min(len(latencies) - 1, int(0.95 * len(latencies)))]

            elapsed, count = await _concurrent(
                client, url, for_throughput, rerank, args.concurrency
            )
            throughput = count / elapsed if elapsed else float("nan")
            print(
                f"{label:22s}{p50:9.0f}{p95:9.0f}"
                f"{latencies[-1]:11.0f}{throughput:12.2f}"
                f"{f'{reranked}/{len(latencies)}':>14s}"
            )

    print(
        f"\nn={args.n} mỗi chế độ, bỏ {args.warmup} lượt khởi động."
        "\nSố này chỉ so sánh được khi máy không chạy tác vụ nặng khác."
    )
    return 0


if __name__ == "__main__":
    use_utf8_stdout()
    raise SystemExit(asyncio.run(main()))
