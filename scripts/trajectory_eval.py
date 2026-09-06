"""Runs trajectory evaluation: success, tool calls, tokens read, citation exactness.

Required by Gate S2 to S3. Reports what an agent spends per question, not what
one ranker returns, and compares policies so the cost of verifying an answer is
visible next to the benefit.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path
from typing import Any

from rag_eval.legal.db.connection import close_db_pool, get_db_pool
from rag_eval.legal.eval.trajectory import ScriptedPolicy, VerifyingPolicy, score_policy
from rag_eval.legal.mcp.tools import LegalMCPTools, SentenceTransformerQueryEmbedder

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
SETS = {
    "tuned": FIXTURES / "smoke_queries.jsonl",
    "dev": FIXTURES / "smoke_queries_holdout.jsonl",
    "test": FIXTURES / "smoke_queries_test.jsonl",
}


def _load(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument(
        "--trace", type=str, default=None, help="Write trajectories here"
    )
    args = parser.parse_args()

    pool = await get_db_pool()
    tools = LegalMCPTools(
        pool=pool, embedding_engine=SentenceTransformerQueryEmbedder()
    )

    policies = [ScriptedPolicy(limit=args.limit), VerifyingPolicy(limit=args.limit)]

    print(
        f"{'tập':7s}{'chính sách':19s}{'thành công':>11s}{'nêu được mức phạt':>19s}"
        f"{'trích đúng khoản':>18s}{'lượt gọi':>10s}{'token':>8s}{'ms':>7s}"
    )
    print("-" * 96)

    all_traces: list[dict[str, Any]] = []
    for name, path in SETS.items():
        items = _load(path)
        for policy in policies:
            score, trajectories = await score_policy(tools, policy, items)
            print(
                f"{name:7s}{score.policy:19s}"
                f"{score.success_rate:10.1%}{score.answer_carried:19.1%}"
                f"{score.citation_exactness:18.1%}{score.calls_per_question:10.2f}"
                f"{score.tokens_per_question:8.0f}{score.ms_per_question:7.0f}"
            )
            if args.trace:
                for trajectory in trajectories:
                    all_traces.append(
                        {
                            "split": name,
                            "policy": score.policy,
                            "question": trajectory.question,
                            "cited_path": trajectory.cited_path,
                            "gave_up": trajectory.gave_up,
                            "calls": [c.name for c in trajectory.calls],
                            "tokens": trajectory.tokens_read,
                        }
                    )
        print()

    if args.trace:
        Path(args.trace).write_text(
            "\n".join(json.dumps(t, ensure_ascii=False) for t in all_traces) + "\n",
            encoding="utf-8",
        )
        shapes = Counter(tuple(t["calls"]) for t in all_traces)
        print(f"{len(all_traces)} quỹ đạo đã ghi vào {args.trace}")
        print("\nHình dạng quỹ đạo:")
        for shape, n in shapes.most_common(6):
            print(f"  {n:5d}  {' -> '.join(shape) or '(không gọi tool nào)'}")

    await close_db_pool()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
