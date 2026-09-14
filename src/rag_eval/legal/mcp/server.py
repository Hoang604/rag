"""Vietnamese Traffic Law Model Context Protocol (MCP) Server.

Implements the official MCP Python SDK v2 MCPServer exposing the 10 canonical
Agent-First legal tools with constructive contracts and dynamic corpus topology instructions.
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.shared.exceptions import MCPError
from mcp.types import CallToolResult, TextContent

from rag_eval.legal.mcp.registry import register_legal_mcp_tools
from rag_eval.legal.mcp.tools import (
    LegalMCPTools,
    LegalRuntimeSensors,
    LegalStagingTools,
    QueryEmbedder,
    SentenceTransformerQueryEmbedder,
)
from rag_eval.legal.schemas import LegalDomainError, get_vietnam_today

logger = logging.getLogger("rag_eval.legal.mcp.server")

SERVER_NAME = "vietnamese-traffic-law-mcp"
SERVER_VERSION = "3.0.0"

STATIC_SERVER_INSTRUCTIONS = """# VIETNAMESE TRAFFIC LAW REASONING PROTOCOL

## 1. MÔ HÌNH DỮ LIỆU (Data Topology)
- CẤU TRÚC CÂY PHÂN CẤP: Văn bản được phân rã theo 7 cấp: `Document -> Chapter -> Section -> Article -> Clause -> Point -> Appendix`.
- NGUYÊN TẮC LƯU TRỮ NÚT LÁ (Leaf Nodes): Cơ sở dữ liệu chỉ lưu trữ các nút lá trên cây cú pháp. Nút cha (Điều/Khoản không có điểm con) được lưu trực tiếp; nút cha có các điểm con được phân rã thành các nút lá tương ứng.
- NGỮ CẢNH TỔNG HỢP: Mỗi nút lá chứa văn bản nguyên văn (`verbatim_text`) và văn bản đã tổng hợp toàn bộ chuỗi ngữ cảnh phả hệ cha (`contextualized_text`).

## 2. NGUYÊN TẮC BẢO CHỨNG & TỪ CHỐI (Grounding & Abstention)
- Trích dẫn căn cứ pháp lý bắt buộc theo định danh phân cấp: `[Tên Văn bản > Điều > Khoản > Điểm]` lấy trực tiếp từ kết quả truy xuất của công cụ.
- Khi không tìm thấy kết quả trong cơ sở dữ liệu (`total_hits == 0` hoặc không có quy định liên quan): Thông báo rõ ràng hệ thống chưa có dữ liệu và dừng lại; không suy đoán hay bổ sung thông tin ngoài kết quả công cụ."""


def render_server_instructions(
    manifest_block: str | None = None,
    as_of_date: datetime.date | None = None,
) -> str:
    """Renders full server instructions combining static topology rules and dynamic corpus manifest in Vietnam timezone."""
    target_date = as_of_date or get_vietnam_today()
    date_str = target_date.strftime("%d/%m/%Y")
    manifest = (
        manifest_block
        if manifest_block
        else f"## DANH MỤC VĂN BẢN TRONG CƠ SỞ DỮ LIỆU (TÍNH ĐẾN: {date_str})\n- (Cơ sở dữ liệu đang ngoại tuyến hoặc chưa kết nối)"
    )
    return f"{STATIC_SERVER_INSTRUCTIONS}\n\n{manifest}".strip()


LEGAL_SERVER_INSTRUCTIONS = render_server_instructions()


def create_default_legal_mcp_tools(
    embedding_engine: QueryEmbedder | None = None,
) -> LegalMCPTools:
    """Composition root factory explicitly assembling runtime sensors and staging tools via pure DI."""
    from rag_eval.legal.ingestion.staging.manager import StagingManager

    embedder = embedding_engine or SentenceTransformerQueryEmbedder()
    staging_mgr = StagingManager()
    sensors = LegalRuntimeSensors(embedding_engine=embedder, staging_manager=staging_mgr)
    staging = LegalStagingTools(staging_manager=staging_mgr)
    return LegalMCPTools(sensors=sensors, staging=staging)


def create_legal_mcp_server(
    tools: LegalMCPTools | None = None,
    manifest_block: str | None = None,
    as_of_date: datetime.date | None = None,
) -> MCPServer:
    """Builds and configures the official MCP v2 MCPServer instance with all 14 legal tools in comprehensive Vietnamese."""
    tool_impl = tools if tools is not None else create_default_legal_mcp_tools()
    instructions_text = render_server_instructions(manifest_block=manifest_block, as_of_date=as_of_date)
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
        return render_server_instructions(manifest_block=manifest, as_of_date=as_of_date)

    async def get_tool_definitions(self) -> list[dict[str, Any]]:
        tool_objs = await self.mcp_server.list_tools()
        return [
            {
                "name": t.name,
                "description": t.description or "",
                "inputSchema": t.input_schema,
            }
            for t in tool_objs
        ]

    async def execute_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        tool_name = name if name.startswith("mcp_traffic_") else f"mcp_traffic_{name}"
        res = await self.mcp_server.call_tool(tool_name, args)
        if isinstance(res, CallToolResult) and res.is_error:
            err_msg = "\n".join(
                c.text for c in res.content if isinstance(c, TextContent)
            )
            raise LegalDomainError(
                error_code=-32603,
                message=err_msg or f"Lỗi khi thực thi công cụ '{name}'",
            )
        if isinstance(res, CallToolResult):
            for item in res.content:
                if isinstance(item, TextContent):
                    try:
                        parsed = json.loads(item.text)
                        if isinstance(parsed, dict):
                            return parsed
                        return {"result": parsed}
                    except (json.JSONDecodeError, ValueError):
                        return {"result": item.text}
        return {}

    async def handle_request_dict(self, req: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(req, dict) or req.get("jsonrpc") != "2.0":
            return {
                "jsonrpc": "2.0",
                "id": req.get("id") if isinstance(req, dict) else None,
                "error": {"code": -32600, "message": "Yêu cầu JSON-RPC 2.0 không hợp lệ"},
            }

        req_id = req.get("id")
        method = req.get("method", "")
        params = req.get("params") or {}

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

            if method.startswith("mcp_traffic_"):
                args = params if isinstance(params, dict) else {}
                out = await self.execute_tool(method, args)
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

    def run(self, transport: str = "stdio") -> None:
        self.mcp_server.run(transport=transport)  # type: ignore


def run_mcp_server(log_file: str | None = None) -> None:
    if log_file:
        from pathlib import Path

        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            filename=log_file,
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )
    server = LegalMCPServer()
    server.run(transport="stdio")
