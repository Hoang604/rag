from __future__ import annotations

import atexit
import datetime
import json
import logging
import os
import signal
import sys
from pathlib import Path
from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp.shared.exceptions import MCPError
from mcp.types import CallToolResult, TextContent

from rag_eval.legal.errors import LegalDomainError
from rag_eval.legal.mcp.registry import register_legal_mcp_tools
from rag_eval.legal.mcp.tools import (
    LegalMCPTools,
    LegalRuntimeSensors,
    LegalStagingTools,
    QueryEmbedder,
    SentenceTransformerQueryEmbedder,
)

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
- Đơn vị lưu trữ: Mỗi nút lá quy phạm (Khoản hoặc Điểm) lưu trữ câu chữ nguyên văn (`verbatim_text`), ngữ cảnh phả hệ tích hợp (`contextualized_text`), tọa độ dòng (`start_line`, `end_line`), và danh sách viện dẫn treo (`dangling_dependencies`).
- Khóa phân cấp LTREE: Đường dẫn phân cấp chuẩn hóa theo dot-notation (ví dụ: `100_2019_nd_cp.c_ii.a_5.c_1.p_a`).

## 2. QUY TRÌNH TRUY XUẤT THỜI GIAN THỰC (RUNTIME RETRIEVAL)
1. Kích hoạt song song: Phát lệnh gọi đồng thời `hybrid_search` (truy xuất ngữ nghĩa quy phạm, chuyển đổi khẩu ngữ thành thuật ngữ luật) và `verbatim_grep` (neo chặt số hiệu văn bản, số Điều/Khoản, mã hiệu biển báo, thông số kỹ thuật).
2. Mở rộng ngữ cảnh: Sử dụng `hierarchical_navigate` với `direction="FULL_ARTICLE"` khi cần ngữ cảnh trọn vẹn của Điều luật điều chỉnh để loại trừ rủi ro hiểu sai quy phạm.
3. Duyệt quan hệ đồ thị: Sử dụng `graph_traverse` để truy vết các điều khoản dẫn chiếu, hình thức xử phạt bổ sung, hoặc quy chuẩn kỹ thuật liên quan.
4. Căn cứ độc quyền: Mọi kết luận tư vấn pháp lý bắt buộc phải trích dẫn phân cấp tường minh `[Văn bản > Điều > Khoản > Điểm]` dựa hoàn toàn trên kết quả trả về từ công cụ.

## 3. QUY TRÌNH THẨM ĐỊNH STAGING STUDIO (STAGING REVIEW LIFECYCLE)
1. Khám phá & Tổng quan phiên: Sử dụng `stg_list_sessions` để rà soát danh mục và trạng thái các phiên làm việc staging đang xử lý trên hệ thống.
2. Rút việc theo hàng đợi: Gọi `stg_poll_pending(doc_code, limit=10)` để lấy đợt quy phạm cần thẩm định từ đầu hàng đợi theo thứ tự đọc tự nhiên (`Điều 1 -> Điều 2`). Công cụ tự động gom nhóm các điểm con dưới ngữ cảnh cấp cha (`parent_context`) và tự động ghi nhận nghĩa vụ thẩm định (`inspected_paths`).
3. Đối soát câu từ nguồn: Khi cần đối chiếu với câu chữ gốc ban đầu, gọi `stg_get_raw(doc_code, start_line, end_line)` theo khoảng dòng hoặc `stg_get_chunk(doc_code, path)` cho từng nút đơn lẻ; sử dụng `stg_grep` để quét từ khóa/biểu thức chính quy xếp hạng phân tầng có trích đoạn highlight (có thể kèm gợi ý `heading_hint`, `body_hint` và quét toàn kho staging khi `doc_code` để trống).
4. Gắn kết đồ thị pháp lý: Đối với các viện dẫn điều khoản nội bộ hoặc liên tài liệu có thực trong corpus, gọi `stg_add_edges` để liên kết `source_path` tới `target_path` chuẩn hóa (target_path bắt buộc phải là chunk có thực trong corpus; cấm tạo cạnh ảo trỏ tới văn bản ngoài). Đối với văn bản ngoài chưa nạp hoặc viện dẫn mở, bắt buộc khai báo cụm từ trích dẫn vào `dangling_dependencies` qua `stg_patch`.
5. Vá lỗi vi phẫu & Cấu trúc: Sử dụng `stg_patch` để cập nhật nguyên văn hoặc danh mục viện dẫn treo; sử dụng `stg_reparent` khi cần di chuyển toàn bộ nhánh cây quy phạm sang vị trí cha mới.
6. Nghiệm thu & Mở lại: Gọi `stg_finalize_chunks(doc_code, paths)` để xác nhận thẩm định từng đợt (bắt buộc phân loại context_type qua stg_patch: SELF_CONTAINED phải có 0 cạnh và 0 dangling; REQUIRES_EXTERNAL_CONTEXT phải có cạnh trong corpus hoặc có dangling_dependencies); sử dụng `stg_unfinalize_chunks` khi cần mở lại các đoạn quy phạm về trạng thái PENDING để chỉnh sửa.
7. Kiểm định an toàn: Gọi `stg_validate(doc_code)` để chạy 9 quy tắc kiểm tra an toàn (Pre-Flight Integrity Gate).
8. Cam kết hoàn tất & Sửa đổi bổ sung: Khi 100% các đoạn quy phạm đạt `REVIEWED` và toàn bộ 9 quy tắc vượt qua, gọi `stg_commit(doc_code)` để chuyển trạng thái sang `AGENT_COMMITTED`. Đối với văn bản đã promote vào cơ sở dữ liệu, sử dụng `stg_reopen_session` để mở phiên sửa đổi bổ sung (AMENDMENT)."""


def render_server_instructions(
    manifest_block: str | None = None,
) -> str:
    """Tạo chỉ dẫn máy chủ đầy đủ, kết hợp quy thức tĩnh và danh mục văn bản động tùy chọn."""
    if not manifest_block or not manifest_block.strip():
        return STATIC_SERVER_INSTRUCTIONS.strip()
    return f"{STATIC_SERVER_INSTRUCTIONS.strip()}\n\n{manifest_block.strip()}"


LEGAL_SERVER_INSTRUCTIONS = render_server_instructions()


def create_default_legal_mcp_tools(
    embedding_engine: QueryEmbedder | None = None,
) -> LegalMCPTools:
    """Composition root factory explicitly assembling runtime sensors and staging tools via pure DI."""
    from rag_eval.legal.ingestion.staging.manager import StagingManager
    from rag_eval.legal.ingestion.staging.service import StagingDomainService

    embedder = embedding_engine or SentenceTransformerQueryEmbedder()
    staging_mgr = StagingManager()
    staging_service = StagingDomainService(staging_manager=staging_mgr)
    sensors = LegalRuntimeSensors(
        embedding_engine=embedder,
    )
    staging = LegalStagingTools(service=staging_service)
    return LegalMCPTools(sensors=sensors, staging=staging)


default_legal_tools = create_default_legal_mcp_tools


def create_legal_mcp_server(
    tools: LegalMCPTools | None = None,
    manifest_block: str | None = None,
) -> MCPServer:
    """Builds and configures the official MCP v2 MCPServer instance with all 19 legal tools in comprehensive Vietnamese."""
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

    def __init__(self, tools: LegalMCPTools | None = None) -> None:
        self.tools = tools if tools is not None else create_default_legal_mcp_tools()
        self.mcp_server = create_legal_mcp_server(self.tools)

    async def get_instructions(self, as_of_date: datetime.date | None = None) -> str:
        manifest = await self.tools.build_dynamic_corpus_manifest(as_of_date=as_of_date)
        return render_server_instructions(manifest_block=manifest)

    async def get_tool_definitions(self) -> list[dict[str, object]]:
        tool_objs = await self.mcp_server.list_tools()
        return [
            {
                "name": t.name,
                "description": t.description or "",
                "inputSchema": t.input_schema,
                "parameters": t.input_schema,
            }
            for t in tool_objs
        ]

    async def execute_tool(self, name: str, args: dict[str, object]) -> dict[str, object]:
        logger.info("[TOOL] START name=%s args=%s", name, args)
        tool_name = name.removeprefix("mcp_traffic_")
        res = await self.mcp_server.call_tool(tool_name, args)
        if isinstance(res, CallToolResult) and res.is_error:
            err_msg = "\n".join(
                c.text for c in res.content if isinstance(c, TextContent)
            )
            logger.error("[TOOL] ERROR name=%s: %s", name, err_msg)
            err_code = -32602
            err_data: dict[str, object] | None = None
            try:
                parsed_err = json.loads(err_msg)
                if isinstance(parsed_err, dict):
                    raw_code = parsed_err.get("error_code") or parsed_err.get("code")
                    if isinstance(raw_code, int):
                        err_code = raw_code
                    if isinstance(parsed_err.get("data"), dict):
                        err_data = parsed_err["data"]
                    if "message" in parsed_err and isinstance(parsed_err["message"], str):
                        err_msg = parsed_err["message"]
            except (json.JSONDecodeError, ValueError):
                pass
            raise LegalDomainError(
                error_code=err_code,
                message=err_msg or f"Lỗi khi thực thi công cụ '{name}'",
                data=err_data,
            )
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

    async def handle_request_dict(self, req: dict[str, object]) -> dict[str, object] | None:
        if not isinstance(req, dict) or req.get("jsonrpc") != "2.0":
            return {
                "jsonrpc": "2.0",
                "id": req.get("id") if isinstance(req, dict) else None,
                "error": {"code": -32600, "message": "Yêu cầu JSON-RPC 2.0 không hợp lệ"},
            }

        req_id = req.get("id")
        method = str(req.get("method") or "")
        params = req.get("params") or {}
        logger.info("[JSON-RPC] >>> method=%s id=%s", method, req_id)

        try:
            if method == "initialize":
                dyn_instructions = await self.get_instructions()
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {
                            "name": SERVER_NAME,
                            "version": SERVER_VERSION,
                        },
                        "instructions": dyn_instructions,
                    },
                }
            if method == "notifications/initialized":
                return None
            if method == "ping":
                return {"jsonrpc": "2.0", "id": req_id, "result": {}}
            if method == "tools/list":
                defs = await self.get_tool_definitions()
                return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": defs}}
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

            clean_method = method.removeprefix("mcp_traffic_")
            all_tool_names = {t.name for t in await self.mcp_server.list_tools()}
            if clean_method in all_tool_names or method.startswith("mcp_traffic_"):
                args = params if isinstance(params, dict) else {}
                out = await self.execute_tool(clean_method, args)
                return {"jsonrpc": "2.0", "id": req_id, "result": out}

            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Không tìm thấy phương thức: {method}"},
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
        logger.info("[RUN] Starting MCPServer transport='%s' (pid=%d, ppid=%d)...", transport, os.getpid(), os.getppid())
        try:
            self.mcp_server.run(transport=transport)
            logger.info("[RUN] MCPServer transport='%s' finished cleanly.", transport)
        except Exception:
            logger.exception("[RUN] MCPServer transport='%s' exited with exception", transport)
            raise


def run_mcp_server(log_file: str | None = None) -> None:
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handler = FlushingFileHandler(str(log_path), encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] (pid=%(process)d) %(name)s: %(message)s"))
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
        signame = signal.Signals(signum).name if signum in signal.Signals.__members__.values() else str(signum)
        logger.warning("[SIGNAL] Caught signal %s (%d) on pid=%d, ppid=%d. Exiting cleanly with status 0...", signame, signum, os.getpid(), os.getppid())
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

    server = LegalMCPServer()
    server.run(transport="stdio")
