"""Prepares a blind review sheet for a lawyer, and scores it against the metric.

Every number in this project rests on one unexamined assumption: that matching
the ground-truth path means the answer is correct. `_check_article_match` is a
string comparison. It cannot tell whether the provision it found actually
answers what was asked, and it counts a hit anywhere in the right article even
when the clause returned prices a different offence.

So the question worth putting to an expert is not "is the system good" -- the
automatic metric already estimates that -- but **where does the automatic metric
disagree with a lawyer**, and in which direction. That decides how much every
other figure in the reports can be trusted.

Two commands:

  prepare  Samples questions, runs the engine, writes an HTML sheet holding the
           question and the provision returned. The automatic verdict is *not*
           shown: a reviewer told the machine already thinks this is right will
           agree with it more often, and the whole value here is independence.

  score    Reads the filled sheet back and reports agreement, separately for
           the cases the metric called hits and the ones it called misses.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import html
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from rag_eval.legal.db.connection import close_db_pool, get_db_pool
from rag_eval.legal.eval.smoke_runner import GroundTruth, _check_article_match
from rag_eval.legal.ingestion.xref import address_of_path
from rag_eval.legal.mcp.tools import (
    LegalMCPTools,
    SearchHit,
    SentenceTransformerQueryEmbedder,
)
from rag_eval.legal.retrieval.reranker import CrossEncoderReranker

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def _address_of(path: str) -> str:
    address = address_of_path(path)
    parts = [
        label
        for label in (
            f"Điều {address.dieu}" if address.dieu else "",
            f"Khoản {address.khoan}" if address.khoan else "",
            f"Điểm {address.diem}" if address.diem else "",
        )
        if label
    ]
    return " ".join(parts) or path


_SHEET_CSS = """
body{font:14px/1.6 system-ui,sans-serif;margin:0;background:#f6f7f9;color:#1a1d21}
header{background:#1f2937;color:#fff;padding:18px 28px}
header h1{margin:0 0 4px;font-size:18px}
header p{margin:0;font-size:13px;opacity:.85}
main{max-width:900px;margin:0 auto;padding:24px}
.item{background:#fff;border:1px solid #dfe3e8;border-radius:10px;padding:18px;margin-bottom:16px}
.q{font-weight:600;font-size:15px;margin-bottom:10px}
.addr{display:inline-block;background:#eef2ff;border:1px solid #c7d2fe;border-radius:6px;
      padding:2px 8px;font:600 12px ui-monospace,monospace;color:#3730a3;margin-bottom:8px}
.text{background:#fafbfc;border-left:3px solid #cbd5e1;padding:10px 14px;
      white-space:pre-wrap;font-size:13px;color:#334155}
.ask{margin-top:14px;padding-top:12px;border-top:1px dashed #e2e8f0;font-size:13px}
.ask label{margin-right:16px;cursor:pointer}
textarea{width:100%;margin-top:8px;padding:8px;border:1px solid #cbd5e1;border-radius:6px;
         font:13px system-ui,sans-serif;box-sizing:border-box}
.bar{position:sticky;bottom:0;background:#fff;border-top:1px solid #dfe3e8;padding:14px 28px;
     text-align:center}
button{background:#1f2937;color:#fff;border:0;border-radius:8px;padding:10px 22px;
       font-size:14px;cursor:pointer}
"""

_SHEET_JS = """
function saveSheet(){
  const rows = [['id','verdict','note']];
  document.querySelectorAll('.item').forEach(function(item){
    const id = item.dataset.id;
    const picked = item.querySelector('input[type=radio]:checked');
    const note = item.querySelector('textarea').value.replace(/[\\r\\n]+/g,' ');
    rows.push([id, picked ? picked.value : '', note]);
  });
  const csv = rows.map(function(r){
    return r.map(function(c){ return '"' + String(c).replace(/"/g,'""') + '"'; }).join(',');
  }).join('\\n');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([csv], {type:'text/csv;charset=utf-8'}));
  a.download = 'human_eval_filled.csv';
  a.click();
}
"""


def _write_sheet(path: Path, items: list[dict[str, Any]]) -> None:
    blocks = []
    for item in items:
        blocks.append(
            f"""<div class="item" data-id="{html.escape(item["id"])}">
  <div class="q">{html.escape(item["query"])}</div>
  <div class="addr">{html.escape(item["doc_code"])} &mdash; {html.escape(item["address"])}</div>
  <div class="text">{html.escape(item["text"][:1200])}</div>
  <div class="ask">
    <strong>Điều khoản trên có trả lời được câu hỏi không?</strong><br>
    <label><input type="radio" name="v{html.escape(item["id"])}" value="dung"> Có, trả lời đúng và đủ</label>
    <label><input type="radio" name="v{html.escape(item["id"])}" value="mot_phan"> Liên quan nhưng chưa đủ</label>
    <label><input type="radio" name="v{html.escape(item["id"])}" value="sai"> Không, sai điều khoản</label>
    <textarea rows="2" placeholder="Ghi chú (nếu cần): điều khoản đúng là gì?"></textarea>
  </div>
</div>"""
        )

    path.write_text(
        f"""<!doctype html><html lang="vi"><head><meta charset="utf-8">
<title>Phiếu thẩm định {len(items)} câu trả lời</title><style>{_SHEET_CSS}</style></head>
<body>
<header>
  <h1>Phiếu thẩm định kết quả tra cứu &mdash; {len(items)} câu</h1>
  <p>Với mỗi câu hỏi, hệ thống trả về điều khoản dưới đây. Xin đánh giá điều khoản
  đó có trả lời được câu hỏi không. <strong>Phiếu không hiển thị đánh giá tự động
  của máy</strong>, để nhận định của bạn độc lập.</p>
</header>
<main>{"".join(blocks)}</main>
<div class="bar"><button onclick="saveSheet()">Tải phiếu đã điền (CSV)</button></div>
<script>{_SHEET_JS}</script>
</body></html>""",
        encoding="utf-8",
    )


async def prepare(args: argparse.Namespace) -> int:
    rows = [
        json.loads(line)
        for line in Path(args.source).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    rng = random.Random(args.seed)
    rng.shuffle(rows)

    pool = await get_db_pool()
    reranker = CrossEncoderReranker(max_length=256)
    await reranker.warm()
    tools = LegalMCPTools(
        pool=pool,
        embedding_engine=SentenceTransformerQueryEmbedder(),
        reranker=reranker,
        rerank_by_default=True,
    )

    # Sampled to hold both verdicts, because a sheet of successes measures
    wanted_hits = args.size // 2
    wanted_misses = args.size - wanted_hits
    picked: list[dict[str, Any]] = []
    truth_by_id: dict[str, dict[str, Any]] = {}
    hits = misses = 0

    for row in rows:
        if hits >= wanted_hits and misses >= wanted_misses:
            break
        query = str(row["query"])
        result = await tools.hybrid_search(query=query, limit=1)
        if not result.hits:
            continue
        top: SearchHit = result.hits[0]
        truth = GroundTruth.model_validate(row["ground_truth"])
        automatic = _check_article_match(top, truth)
        if automatic and hits >= wanted_hits:
            continue
        if not automatic and misses >= wanted_misses:
            continue

        item_id = f"h{len(picked):03d}"
        picked.append(
            {
                "id": item_id,
                "query": query,
                "doc_code": top.doc_code,
                "address": _address_of(top.path),
                "text": top.contextualized_text or top.verbatim_text,
            }
        )
        truth_by_id[item_id] = {
            "query": query,
            "style": row.get("domain") or row.get("style") or "unknown",
            "returned_path": top.path,
            "expected": row["ground_truth"],
            "automatic": "hit" if automatic else "miss",
        }
        hits += 1 if automatic else 0
        misses += 0 if automatic else 1

    rng.shuffle(picked)
    sheet = Path(args.out)
    _write_sheet(sheet, picked)
    key = sheet.with_suffix(".key.json")
    key.write_text(
        json.dumps(truth_by_id, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"{len(picked)} câu -> {sheet}")
    print(f"   trong đó máy chấm ĐÚNG {hits}, máy chấm SAI {misses}")
    print(f"   đáp án máy giữ riêng ở {key.name} (phiếu không hiển thị)")
    print("\nGửi file HTML cho người thẩm định, mở bằng trình duyệt, điền xong")
    print("bấm nút tải CSV, rồi chạy:")
    print(
        f"   uv run python scripts/human_eval.py score --key {key} --filled <file.csv>"
    )
    await close_db_pool()
    return 0


def score(args: argparse.Namespace) -> int:
    key = json.loads(Path(args.key).read_text(encoding="utf-8"))
    with Path(args.filled).open(encoding="utf-8-sig", newline="") as handle:
        filled = {row["id"]: row for row in csv.DictReader(handle)}

    # "Partially relevant" counts as not answering: the reader still cannot
    human_correct = {"dung"}
    agree = 0
    table: Counter[tuple[str, str]] = Counter()
    disagreements: list[dict[str, Any]] = []
    by_style: dict[str, Counter[str]] = defaultdict(Counter)
    unanswered = 0

    for item_id, record in key.items():
        row = filled.get(item_id)
        verdict = (row or {}).get("verdict", "").strip()
        if not verdict:
            unanswered += 1
            continue
        human = "hit" if verdict in human_correct else "miss"
        automatic = record["automatic"]
        table[(automatic, human)] += 1
        by_style[record["style"]]["n"] += 1
        if human == automatic:
            agree += 1
            by_style[record["style"]]["agree"] += 1
        else:
            disagreements.append(
                {
                    "query": record["query"],
                    "automatic": automatic,
                    "human": verdict,
                    "returned": record["returned_path"],
                    "note": (row or {}).get("note", ""),
                }
            )

    judged = sum(table.values())
    if not judged:
        print("Chưa có câu nào được chấm.")
        return 1

    print(f"Đã chấm {judged} câu ({unanswered} bỏ trống)\n")
    print(f"  Máy và người ĐỒNG Ý:  {agree}/{judged} = {agree / judged:.1%}\n")
    print("  Bảng đối chiếu:")
    print(f"    máy đúng + người đúng : {table[('hit', 'hit')]:4d}")
    print(f"    máy đúng + người SAI  : {table[('hit', 'miss')]:4d}   <- máy lạc quan")
    print(f"    máy sai  + người ĐÚNG : {table[('miss', 'hit')]:4d}   <- máy bi quan")
    print(f"    máy sai  + người sai  : {table[('miss', 'miss')]:4d}")

    optimistic = table[("hit", "miss")]
    pessimistic = table[("miss", "hit")]
    called_hit = table[("hit", "hit")] + optimistic
    if called_hit:
        print(
            f"\n  Trong số câu máy chấm ĐÚNG, người bác {optimistic}/{called_hit}"
            f" = {optimistic / called_hit:.1%}"
        )
        print("  Đây là mức mà mọi con số Hit@1 trong báo cáo đang bị thổi lên.")
    called_miss = table[("miss", "miss")] + pessimistic
    if called_miss:
        print(
            f"  Trong số câu máy chấm SAI, người cho là được {pessimistic}/{called_miss}"
            f" = {pessimistic / called_miss:.1%}"
        )

    if by_style:
        print("\n  Mức đồng ý theo phong cách câu hỏi:")
        for style, counts in sorted(by_style.items(), key=lambda kv: -kv[1]["n"]):
            n = counts["n"]
            print(f"    {style:22s} n={n:3d}  đồng ý {counts['agree'] / n:6.1%}")

    if disagreements:
        print(f"\n  {len(disagreements)} ca bất đồng:")
        for case in disagreements[:12]:
            print(
                f"    [máy={case['automatic']}, người={case['human']}] {case['query'][:70]}"
            )
            if case["note"]:
                print(f"        ghi chú: {case['note'][:90]}")
    if args.report:
        Path(args.report).write_text(
            json.dumps(disagreements, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\n  Chi tiết bất đồng -> {args.report}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("prepare", help="Dựng phiếu thẩm định mù")
    p.add_argument("--source", default=str(FIXTURES / "qrels_dev.jsonl"))
    p.add_argument("--size", type=int, default=60)
    p.add_argument("--seed", type=int, default=20260906)
    p.add_argument("--out", default="human_eval_sheet.html")

    s = sub.add_parser("score", help="Chấm phiếu đã điền")
    s.add_argument("--key", required=True)
    s.add_argument("--filled", required=True)
    s.add_argument("--report", default=None)

    args = parser.parse_args()
    if args.command == "prepare":
        return asyncio.run(prepare(args))
    return score(args)


from rag_eval.legal.console import use_utf8_stdout

if __name__ == "__main__":
    use_utf8_stdout()
    raise SystemExit(main())
