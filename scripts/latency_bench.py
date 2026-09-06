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
) -> float:
    body: dict[str, object] = {"query": query, "limit": 5}
    if rerank is not None:
        body["rerank"] = rerank
    start = time.perf_counter()
    response = await client.post(url, json=body, timeout=120.0)
    response.raise_for_status()
    return (time.perf_counter() - start) * 1000.0


async def _serial(
    client: httpx.AsyncClient, url: str, queries: list[str], rerank: bool | None
) -> list[float]:
    return [await _one(client, url, q, rerank) for q in queries]


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
    queries = _queries(args.queries, args.n + args.warmup)

    async with httpx.AsyncClient() as client:
        health = await client.get(f"{args.base_url.rstrip('/')}/api/health", timeout=30)
        health.raise_for_status()
        print(f"server: {args.base_url}  •  {health.json()}\n")

        print(
            f"{'chế độ':22s}{'p50 ms':>9s}{'p95 ms':>9s}"
            f"{'chậm nhất':>11s}{'req/s @' + str(args.concurrency):>12s}"
        )
        print("-" * 63)

        for label, rerank in (("không rerank", False), ("có rerank", True)):
            await _serial(client, url, queries[: args.warmup], rerank)
            latencies = await _serial(client, url, queries[args.warmup :], rerank)
            latencies.sort()
            p50 = statistics.median(latencies)
            # Nearest-rank p95: no interpolation between samples that exist.
            p95 = latencies[min(len(latencies) - 1, int(0.95 * len(latencies)))]

            elapsed, count = await _concurrent(
                client, url, queries[args.warmup :], rerank, args.concurrency
            )
            throughput = count / elapsed if elapsed else float("nan")
            print(
                f"{label:22s}{p50:9.0f}{p95:9.0f}"
                f"{latencies[-1]:11.0f}{throughput:12.2f}"
            )

    print(
        f"\nn={args.n} mỗi chế độ, bỏ {args.warmup} lượt khởi động."
        "\nSố này chỉ so sánh được khi máy không chạy tác vụ nặng khác."
    )
    return 0


if __name__ == "__main__":
    use_utf8_stdout()
    raise SystemExit(asyncio.run(main()))
