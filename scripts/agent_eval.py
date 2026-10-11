"""Runs a Claude Code agent over the MCP tools on sampled evaluation cases.

    uv run python scripts/agent_eval.py --n 40 --split holdout
    uv run python scripts/agent_eval.py --report

The agent may call only `search`, `hierarchical_navigate`, `graph_traverse` and `get_raw`. Its
final citation is correct when it answers the case (the expected path or a provision
under it). Each case's recorded first `search` call is replayed on the same question,
so the agent's answer and the single-call retrieval are directly paired. Results
append to experiments/runs/agent_eval.jsonl, so an interrupted run resumes.
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

from rag_eval.legal.console import use_utf8_stdout
from rag_eval.legal.db.connection import close_db_pool
from rag_eval.legal.eval.retrieval import EvalCase, load_cases, run_case
from rag_eval.legal.mcp.tools import LegalMCPTools, SentenceTransformerQueryEmbedder

ROOT: Final = Path(__file__).resolve().parents[1]
OUT: Final = ROOT / "experiments" / "runs" / "agent_eval.jsonl"
SERVER: Final = "law"
TOOLS: Final = f"mcp__{SERVER}__search,mcp__{SERVER}__hierarchical_navigate,mcp__{SERVER}__graph_traverse,mcp__{SERVER}__get_raw"
EXE: Final = ROOT / ".venv" / ("Scripts/rag-eval.exe" if os.name == "nt" else "bin/rag-eval")

PROMPT: Final = """Bạn trả lời câu hỏi về luật giao thông đường bộ Việt Nam chỉ bằng các tool đã cho.

Câu hỏi: {question}

Cách làm:
1. Gọi search với query viết bằng thuật ngữ văn bản luật (chủ thể, phương tiện, hành vi; ví dụ "vượt đèn đỏ" là "không chấp hành hiệu lệnh của đèn tín hiệu giao thông", "xe máy" là "xe mô tô, xe gắn máy"), giữ ý định của câu hỏi (ví dụ "phạt tiền"), và pattern là cụm từ ngắn chắc chắn có nguyên văn trong điều khoản cần tìm; ưu tiên nhóm both, đọc kỹ chủ đề từng kết quả (context và text), vì tìm kiếm có thể trả về điều khoản có từ giống nhưng chủ đề khác.
2. Nếu hỏi về mức phạt, điều đúng là điều khoản chế tài (chứa "phạt tiền"), không phải điều quy định quy tắc.
3. Nếu kết quả lệch chủ đề hoặc chỉ là một phần, gọi lại search với cách diễn đạt khác, hoặc dùng hierarchical_navigate với path cắt đến Điều (a_N) hoặc Khoản (c_N) của kết quả để đọc toàn văn rồi chọn lại. Nếu điều khoản viện dẫn điều khác (ví dụ "vi phạm quy định tại điểm a khoản 2 Điều này"), gọi graph_traverse với path của điều khoản đó để đọc điều được viện dẫn.
Mỗi tool tối đa vài lần gọi.

Kết thúc bằng đúng một dòng JSON, không thêm chữ nào sau nó:
{{"doc_code": "<số hiệu văn bản>", "path": "<trường path của điều khoản được chọn, sao chép nguyên văn từ kết quả tool>"}}
Nếu không tìm được căn cứ: {{"doc_code": null, "path": null}}"""


def mcp_config(database: str) -> dict[str, object]:
    return {
        "mcpServers": {
            SERVER: {
                "command": str(EXE),
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


def agent_correct(cited: object, case: EvalCase) -> bool:
    if not isinstance(cited, dict) or not cited.get("path"):
        return False
    path = str(cited["path"])
    return any(path == e or path.startswith(e + ".") for e in case.expected)


def report() -> None:
    rows = [json.loads(line) for line in OUT.read_text(encoding="utf-8").splitlines() if line]
    rows = [r for r in rows if "error" not in r]
    n = len(rows)
    if not n:
        print("no completed rows")
        return
    rescued = sum(1 for r in rows if not r["search_ok"] and r["agent_ok"])
    harmed = sum(1 for r in rows if r["search_ok"] and not r["agent_ok"])
    search = sum(1 for r in rows if r["search_ok"])
    agent = sum(1 for r in rows if r["agent_ok"])
    cost = sum(float(r.get("cost_usd") or 0) for r in rows)
    turns = sum(int(r.get("turns") or 0) for r in rows) / n
    print(f"n={n} first-search={search / n:.1%} agent={agent / n:.1%} cứu={rescued} hại={harmed}")
    print(f"lượt trung bình={turns:.1f} chi phí={cost:.2f} USD")


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=40)
    parser.add_argument("--split", choices=("dev", "holdout"), default="holdout")
    parser.add_argument("--model", default="sonnet")
    parser.add_argument("--database", default="rag_legal")
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()
    if args.report:
        report()
        return 0

    tools = LegalMCPTools.build(embedding_engine=SentenceTransformerQueryEmbedder())
    cases = [c for c in load_cases() if c.split == args.split]
    sample = random.Random(11).sample(cases, min(args.n, len(cases)))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    done = (
        {r["id"] for r in map(json.loads, OUT.read_text(encoding="utf-8").splitlines()) if "error" not in r}
        if OUT.exists()
        else set()
    )
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
        json.dump(mcp_config(args.database), handle)
    try:
        for case in sample:
            if case.id in done:
                continue
            first = await run_case(tools, case)
            result = run_agent(case.question, Path(handle.name), args.model)
            row = {
                "id": case.id,
                "split": case.split,
                "question": case.question,
                "search_ok": first.outcome.found_in != "missed",
                "agent_ok": agent_correct(result.get("cited"), case),
                **result,
            }
            with OUT.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(f"{case.id} search={row['search_ok']!s:5s} agent={row['agent_ok']!s:5s} {case.question[:60]}", flush=True)
    finally:
        await close_db_pool()
    return 0


if __name__ == "__main__":
    use_utf8_stdout()
    sys.exit(asyncio.run(main()))
