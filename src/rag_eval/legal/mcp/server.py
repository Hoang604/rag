from __future__ import annotations

import asyncio
import atexit
import datetime
import json
import logging
import os
import signal
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError, UnexpectedToolError
from mcp.shared.exceptions import MCPError
from mcp.types import CallToolResult, TextContent

from rag_eval.legal.db.connection import close_db_pool, get_db_pool
from rag_eval.legal.db.repositories import LegalRepository
from rag_eval.legal.errors import E_INTERNAL_ERROR, E_INVALID_PARAMS, LegalDomainError
from rag_eval.legal.mcp.registry import register_legal_mcp_tools
from rag_eval.legal.mcp.tools import (
    LegalGraphCurationTools,
    LegalMCPTools,
    LegalRuntimeSensors,
    QueryEmbedder,
    SentenceTransformerQueryEmbedder,
)
from rag_eval.legal.schemas.api import DocumentStatsDTO
from rag_eval.legal.text import get_vietnam_today

logger = logging.getLogger("rag_eval.legal.mcp.server")


class FlushingFileHandler(logging.FileHandler):
    """FileHandler that automatically flushes on every emit for immediate persistence."""

    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)
        self.flush()


SERVER_NAME = "vietnamese-traffic-law-mcp"
SERVER_VERSION = "3.0.0"

STATIC_SERVER_INSTRUCTIONS = """# CHỈ DẪN VẬN HÀNH HỆ THỐNG PHÁP LUẬT GIAO THÔNG ĐƯỜNG BỘ

## 1. MÔ HÌNH DỮ LIỆU QUY PHẠM
- Cấu trúc phân cấp: `Văn bản -> Chương -> Mục -> Điều -> Khoản -> Điểm -> Phụ lục`.
- Đơn vị lưu trữ: Mỗi nút lá quy phạm lưu trữ câu chữ nguyên văn, ngữ cảnh phả hệ tích hợp và tọa độ dòng.
- Khóa phân cấp LTREE: Đường dẫn chuẩn hóa theo dot-notation (ví dụ: `168_2024_nd_cp.c_ii.s_1.a_7.c_11.p_b`).

## 2. QUY TRÌNH TRUY XUẤT THỜI GIAN THỰC
1. Tìm kiếm: Gọi `search` với `query` (truy vấn ngữ nghĩa) và `pattern` (cụm từ nguyên văn hoặc regex). Kết quả gom các đoạn cùng văn bản và cùng ngữ cảnh cha thành `groups`: `doc_code` và `context` (Chương > Điều > Khoản, gồm mức phạt và chủ thể) ghi một lần, `provisions` liệt kê từng đoạn với `text` (nguyên văn), `found_in` (`both`: vừa liên quan về nghĩa vừa chứa đúng cụm từ, đáng tin nhất; `semantic_only`; `verbatim_only`) và `rank`. `documents` cho tên và hiệu lực từng văn bản theo `doc_code`. `hierarchical_navigate` và `graph_traverse` trả các đoạn theo cùng dạng nhóm.
2. Mở rộng ngữ cảnh: Gọi `hierarchical_navigate` với path cắt đến Điều (`a_N`) hoặc Khoản (`c_N`) khi cần toàn văn Điều luật điều chỉnh để loại trừ rủi ro hiểu sai quy phạm.
3. Duyệt quan hệ đồ thị: Gọi `graph_traverse` để truy vết các quy phạm dẫn chiếu, chế tài xử phạt hoặc quy chuẩn kỹ thuật liên quan.
4. Đọc văn bản gốc: Khi một đoạn có vẻ bị cắt lệch hoặc thiếu chữ, gọi `get_raw` với `doc_code`, `start_line`, `end_line` của đoạn đó (mở rộng vài dòng) để đọc nguyên văn quanh nó.
5. Căn cứ độc quyền: Mọi kết luận tư vấn pháp lý bắt buộc phải trích dẫn phân cấp tường minh `[Văn bản > Điều > Khoản > Điểm]` dựa hoàn toàn trên kết quả trả về từ công cụ; tên văn bản lấy từ `documents`.

## 3. HIỆU CHỈNH ĐỒ THỊ QUAN HỆ
- Cạnh quan hệ giữa các đoạn quy phạm chỉ có một loại; mọi thay đổi được ghi nhật ký kèm lý do.
- Khi cần thêm hoặc gỡ cạnh dẫn chiếu, gọi `graph_curate_edges` với `reason` (câu hỏi đang trả lời):
  + `add_edges`: thêm cạnh với `citation_text` chép nguyên văn cụm viện dẫn từ nút nguồn.
  + `remove_edges`: gỡ cạnh sai (target_path có thể là nút cha để gỡ toàn bộ các cạnh lá liên quan).
  + Cạnh do hệ thống tạo từ viện dẫn sẽ được tạo lại ở lần nạp sau; cạnh sai lặp lại là lỗi quy tắc cần báo lại."""


def render_corpus_manifest(docs: Sequence[DocumentStatsDTO], on_date: datetime.date) -> str | None:
    """The documents the database holds, as a block of the server instructions; None when it holds none."""
    if not docs:
        return None
    lines = [
        f"## DANH MỤC VĂN BẢN TRONG CƠ SỞ DỮ LIỆU (tính đến {on_date:%d/%m/%Y})",
        "Truyền mã văn bản vào `doc_codes` của `search` để giới hạn tìm kiếm trong các văn bản đó; `search` đã lọc theo hiệu lực tại ngày vi phạm.",
    ]
    for doc in docs:
        ended = f", hết hiệu lực: {doc.expiration_date}" if doc.expiration_date else ""
        lines.append(f"- **{doc.doc_code}**: {doc.title} (hiệu lực: {doc.effective_date}{ended})")
    return "\n".join(lines)


async def load_corpus_manifest() -> str | None:
    """Reads the manifest on a pool of its own: a pool belongs to the event loop that made it, and the
    server runs on another."""
    try:
        docs = await LegalRepository(await get_db_pool()).documents.list_with_stats()
    finally:
        await close_db_pool()
    return render_corpus_manifest(docs, get_vietnam_today())


def render_server_instructions(
    manifest_block: str | None = None,
) -> str:
    """Tạo chỉ dẫn máy chủ đầy đủ, kết hợp quy thức tĩnh và danh mục văn bản động tùy chọn."""
    if not manifest_block or not manifest_block.strip():
        return STATIC_SERVER_INSTRUCTIONS.strip()
    return f"{STATIC_SERVER_INSTRUCTIONS.strip()}\n\n{manifest_block.strip()}"



def create_default_legal_mcp_tools(
    embedding_engine: QueryEmbedder | None = None,
) -> LegalMCPTools:
    """Composition root assembling the runtime sensors and the graph curation tools."""
    embedder = embedding_engine or SentenceTransformerQueryEmbedder()
    return LegalMCPTools(
        sensors=LegalRuntimeSensors(embedding_engine=embedder),
        curation=LegalGraphCurationTools(),
    )



def create_legal_mcp_server(
    tools: LegalMCPTools | None = None,
    manifest_block: str | None = None,
) -> MCPServer:
    """Builds and configures the official MCP v2 MCPServer instance with the legal tools described in Vietnamese."""
    tool_impl = tools if tools is not None else create_default_legal_mcp_tools()
    instructions_text = render_server_instructions(manifest_block=manifest_block)
    server = MCPServer(
        SERVER_NAME,
        version=SERVER_VERSION,
        description="Máy chủ Giao thức Ngữ cảnh Mô hình (MCP) Pháp luật Giao thông Đường bộ Việt Nam",
        instructions=instructions_text,
    )
    register_legal_mcp_tools(server=server, tool_impl=tool_impl)
    return server


class LegalMCPServer:
    """Wrapper providing direct execution, JSON-RPC bridge, and SDK lifecycle management."""

    def __init__(self, tools: LegalMCPTools | None = None, manifest_block: str | None = None) -> None:
        self.tools = tools if tools is not None else create_default_legal_mcp_tools()
        self.mcp_server = create_legal_mcp_server(self.tools, manifest_block=manifest_block)

    async def execute_tool(
        self, name: str, args: dict[str, object]
    ) -> dict[str, object]:
        logger.info("[TOOL] START name=%s args=%s", name, args)
        try:
            res = await self.mcp_server.call_tool(name, args)
        except UnexpectedToolError as exc:
            logger.error("[TOOL] CRASH name=%s", name, exc_info=exc.__cause__ or exc)
            raise LegalDomainError(
                error_code=E_INTERNAL_ERROR, message=f"{exc}: {exc.__cause__}"
            ) from exc
        except ToolError as exc:
            logger.error("[TOOL] ERROR name=%s: %s", name, exc)
            raise LegalDomainError(error_code=E_INVALID_PARAMS, message=str(exc)) from exc
        if isinstance(res, CallToolResult):
            for item in res.content:
                if isinstance(item, TextContent):
                    try:
                        parsed = json.loads(item.text)
                        logger.info("[TOOL] SUCCESS name=%s", name)
                        if isinstance(parsed, dict):
                            return parsed
                        return {"result": parsed}
                    except (json.JSONDecodeError, ValueError):
                        logger.info("[TOOL] SUCCESS name=%s (raw text)", name)
                        return {"result": item.text}
        logger.info("[TOOL] SUCCESS name=%s (empty)", name)
        return {}

    async def handle_request_dict(
        self, req: dict[str, object]
    ) -> dict[str, object] | None:
        if not isinstance(req, dict) or req.get("jsonrpc") != "2.0":
            return {
                "jsonrpc": "2.0",
                "id": req.get("id") if isinstance(req, dict) else None,
                "error": {
                    "code": -32600,
                    "message": "Yêu cầu JSON-RPC 2.0 không hợp lệ",
                },
            }

        req_id = req.get("id")
        method = str(req.get("method") or "")
        params = req.get("params") or {}
        logger.info("[JSON-RPC] >>> method=%s id=%s", method, req_id)

        try:
            if method == "tools/call":
                if not isinstance(params, dict):
                    return {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {
                            "code": -32602,
                            "message": "params bắt buộc phải là một đối tượng JSON",
                        },
                    }
                t_name = str(params.get("name", ""))
                t_args = params.get("arguments", {})
                if not isinstance(t_args, dict):
                    return {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {
                            "code": -32602,
                            "message": "arguments bắt buộc phải là một đối tượng JSON",
                        },
                    }
                out = await self.execute_tool(t_name, t_args)
                return {"jsonrpc": "2.0", "id": req_id, "result": out}

            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32601,
                    "message": f"Không tìm thấy phương thức: {method}",
                },
            }

        except (LegalDomainError, MCPError) as err:
            code = err.error_code if isinstance(err, LegalDomainError) else err.code
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": code,
                    "message": err.message,
                    "data": err.data,
                },
            }
        except (RuntimeError, ValueError, TypeError, KeyError, OSError) as exc:
            logger.exception("Error handling request")
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32603, "message": str(exc)},
            }

    def run(self, transport: Literal["stdio", "sse"] = "stdio") -> None:
        logger.info(
            "[RUN] Starting MCPServer transport='%s' (pid=%d, ppid=%d)...",
            transport,
            os.getpid(),
            os.getppid(),
        )
        try:
            self.mcp_server.run(transport=transport)
            logger.info("[RUN] MCPServer transport='%s' finished cleanly.", transport)
        except Exception:
            logger.exception(
                "[RUN] MCPServer transport='%s' exited with exception", transport
            )
            raise


def run_mcp_server(log_file: str | None = None) -> None:
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handler = FlushingFileHandler(str(log_path), encoding="utf-8")
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] (pid=%(process)d) %(name)s: %(message)s"
            )
        )
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        root_logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)

    logger.info("=== MCP SERVER PROCESS LAUNCHED ===")
    logger.info("PID: %d | PPID: %d | CWD: %s", os.getpid(), os.getppid(), os.getcwd())
    logger.info("Command line: %s", sys.argv)
    logger.info("Python: %s", sys.executable)

    def _sig_handler(signum: int, frame: object) -> None:
        signame = (
            signal.Signals(signum).name
            if signum in signal.Signals.__members__.values()
            else str(signum)
        )
        logger.warning(
            "[SIGNAL] Caught signal %s (%d) on pid=%d, ppid=%d. Exiting cleanly with status 0...",
            signame,
            signum,
            os.getpid(),
            os.getppid(),
        )
        for h in list(logger.handlers) + list(logging.getLogger().handlers):
            h.flush()
        sys.exit(0)

    try:
        signal.signal(signal.SIGTERM, _sig_handler)
        signal.signal(signal.SIGINT, _sig_handler)
        if hasattr(signal, "SIGHUP"):
            signal.signal(signal.SIGHUP, _sig_handler)
        logger.info("[SIGNALS] Registered SIGTERM, SIGINT, SIGHUP handlers.")
    except (ValueError, OSError) as exc:
        logger.warning("[SIGNALS] Could not register signal handlers: %s", exc)

    def _on_exit() -> None:
        logger.info("[EXIT] atexit hook triggered for pid=%d.", os.getpid())
        for h in list(logger.handlers) + list(logging.getLogger().handlers):
            h.flush()

    atexit.register(_on_exit)

    server = LegalMCPServer(manifest_block=asyncio.run(load_corpus_manifest()))
    server.run(transport="stdio")
