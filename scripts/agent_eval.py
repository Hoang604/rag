"""Runs a Claude Code agent over the MCP tools on sampled fixture questions.

    uv run python scripts/agent_eval.py --n 40
    uv run python scripts/agent_eval.py --report

The agent may call only `hybrid_search` and `hierarchical_navigate`. Its final
citation is scored with the same article match as `bench.py`, and the flat
hybrid top-1 is scored on the same question so the two are directly paired.
Results append to experiments/runs/agent_eval.jsonl, so an interrupted run
resumes where it stopped.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Final

from bench import SETS, CachedEmbedder, answerable, corpus_hits, load_items

from rag_eval.legal.console import use_utf8_stdout
from rag_eval.legal.db.connection import close_db_pool
from rag_eval.legal.eval.smoke_runner import GroundTruth, _check_article_match
from rag_eval.legal.mcp.tools import LegalMCPTools, SearchHit

ROOT: Final = Path(__file__).resolve().parents[1]
OUT: Final = ROOT / "experiments" / "runs" / "agent_eval.jsonl"
SERVER: Final = "law"
TOOLS: Final = f"mcp__{SERVER}__hybrid_search,mcp__{SERVER}__hierarchical_navigate"
SAMPLE_SETS: Final = ("holdout", "colloquial")

PROMPT: Final = """Bạn trả lời câu hỏi về luật giao thông đường bộ Việt Nam chỉ bằng các tool đã cho.

Câu hỏi: {question}

Cách làm:
1. Gọi hybrid_search. Giữ các từ khóa và từ chỉ ý định của người dùng (ví dụ "phạt", "mức phạt"); đọc kỹ chủ đề từng kết quả, vì tìm kiếm có thể trả về điều khoản có từ giống nhưng chủ đề khác.
2. Nếu hỏi về mức phạt, điều đúng là điều khoản chế tài (chứa "phạt tiền"), không phải điều quy định quy tắc.
3. Nếu kết quả lệch chủ đề hoặc chỉ là một phần, gọi lại hybrid_search với cách diễn đạt khác, hoặc dùng hierarchical_navigate (PARENT_CHAIN, FULL_ARTICLE, CHILDREN, SIBLINGS) rồi chọn lại.
Mỗi tool tối đa vài lần gọi.

Kết thúc bằng đúng một dòng JSON, không thêm chữ nào sau nó:
{{"doc_code": "<số hiệu văn bản>", "path": "<trường path của điều khoản được chọn, sao chép nguyên văn từ kết quả tool>"}}
Nếu không tìm được căn cứ: {{"doc_code": null, "path": null}}"""


def mcp_config(database: str) -> dict[str, object]:
    exe = ROOT / ".venv" / "Scripts" / "rag-eval.exe"
    return {
        "mcpServers": {
            SERVER: {
                "command": str(exe),
                "args": ["legal-server"],
                "env": {"DATABASE_URL": f"postgresql://postgres:postgres@localhost:15432/{database}"},
            }
        }
    }


def run_agent(question: str, config_path: Path, model: str) -> dict[str, object]:
    command = [
        shutil.which("claude") or "claude", "-p",
        "--mcp-config", str(config_path), "--strict-mcp-config",
        "--allowedTools", TOOLS, "--output-format", "json",
        "--max-turns", "10", "--model", model,
    ]
    completed = subprocess.run(
        command, input=PROMPT.format(question=question), capture_output=True, text=True, encoding="utf-8",
        timeout=420, check=False, cwd=tempfile.gettempdir(), env={**os.environ},
    )
    try:
        payload = json.loads(completed.stdout)
    except ValueError:
        return {"error": (completed.stderr or completed.stdout)[:300]}
    text = str(payload.get("result", ""))
    match = re.findall(r"\{[^{}]*\"doc_code\"[^{}]*\}", text)
    cited: dict[str, object] = json.loads(match[-1]) if match else {}
    if not cited.get("doc_code") and "CONNECT_TIMEOUT" in text.upper().replace(" ", "_"):
        return {"error": "mcp server did not connect in time"}
    return {
        "cited": cited,
        "turns": payload.get("num_turns"),
        "text": text[-400:],
        "cost_usd": payload.get("total_cost_usd"),
        "is_error": payload.get("is_error"),
    }


def agent_correct(cited: object, truth: GroundTruth) -> bool:
    if not isinstance(cited, dict) or not cited.get("doc_code") or not cited.get("path"):
        return False
    hit = SearchHit(
        chunk_id="",
        doc_code=str(cited["doc_code"]),
        doc_title="",
        path=str(cited["path"]),
        start_line=1,
        end_line=1,
        verbatim_text="",
        contextualized_text="",
        effective_date="",
        score=0.0,
    )
    return _check_article_match(hit, truth)


def report() -> None:
    rows = [json.loads(line) for line in OUT.read_text(encoding="utf-8").splitlines() if line]
    rows = [r for r in rows if "error" not in r]
    n = len(rows)
    both = sum(1 for r in rows if r["flat_ok"] and r["agent_ok"])
    rescued = sum(1 for r in rows if not r["flat_ok"] and r["agent_ok"])
    harmed = sum(1 for r in rows if r["flat_ok"] and not r["agent_ok"])
    flat = sum(1 for r in rows if r["flat_ok"])
    agent = sum(1 for r in rows if r["agent_ok"])
    cost = sum(float(r.get("cost_usd") or 0) for r in rows)
    turns = sum(int(r.get("turns") or 0) for r in rows) / max(n, 1)
    print(f"n={n} flat@1={flat / n:.1%} agent={agent / n:.1%} cứu={rescued} hại={harmed} cả hai đúng={both}")
    print(f"lượt trung bình={turns:.1f} chi phí={cost:.2f} USD")
    for name in SAMPLE_SETS:
        part = [r for r in rows if r["set"] == name]
        if part:
            print(f"  {name}: n={len(part)} flat={sum(r['flat_ok'] for r in part) / len(part):.1%} "
                  f"agent={sum(r['agent_ok'] for r in part) / len(part):.1%}")


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=40)
    parser.add_argument("--model", default="sonnet")
    parser.add_argument("--database", default="rag_legal_main")
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()
    if args.report:
        report()
        return 0

    corpus = await corpus_hits()
    tools = LegalMCPTools.build(embedding_engine=CachedEmbedder())
    rng = random.Random(11)
    sample = []
    for name in SAMPLE_SETS:
        items = [i for i in load_items(SETS[name]) if answerable(i.ground_truth, corpus)]
        sample += [(name, i) for i in rng.sample(items, args.n // len(SAMPLE_SETS))]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    done = (
        {r["query"] for r in map(json.loads, OUT.read_text(encoding="utf-8").splitlines()) if "error" not in r}
        if OUT.exists()
        else set()
    )
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
        json.dump(mcp_config(args.database), handle)
    try:
        for name, item in sample:
            if item.query in done:
                continue
            hits = (await tools.hybrid_search(query=item.query, limit=5)).hits
            result = run_agent(item.query, Path(handle.name), args.model)
            row = {
                "set": name, "query": item.query,
                "flat_ok": bool(hits) and _check_article_match(hits[0], item.ground_truth),
                "agent_ok": agent_correct(result.get("cited"), item.ground_truth),
                **result,
            }
            with OUT.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(f"{name:10s} flat={row['flat_ok']!s:5s} agent={row['agent_ok']!s:5s} {item.query[:60]}", flush=True)
    finally:
        await close_db_pool()
    return 0


if __name__ == "__main__":
    use_utf8_stdout()
    sys.exit(asyncio.run(main()))
