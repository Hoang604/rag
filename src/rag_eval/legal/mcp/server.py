"""Vietnamese Traffic Law Model Context Protocol (MCP) Server.

Implements the official MCP Python SDK v2 MCPServer exposing the 10 canonical
Agent-First legal tools (6 runtime sensors + 4 staging lifecycle tools).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.shared.exceptions import MCPError
from mcp.types import CallToolResult, TextContent

from rag_eval.legal.mcp.tools import (
    CorpusValidateResult,
    GraphEdgeWriteResult,
    GraphTraverseResult,
    HierarchicalNavigateResult,
    HybridSearchResult,
    LegalMCPTools,
    StgAddEdgesResult,
    StgCommitResult,
    StgPatchResult,
    StgPreviewResult,
    VerbatimGrepResult,
)
from rag_eval.legal.schemas import LegalDomainError

logger = logging.getLogger("rag_eval.legal.mcp.server")

SERVER_NAME = "vietnamese-traffic-law-mcp"
SERVER_VERSION = "3.0.0"


def create_legal_mcp_server(tools: LegalMCPTools | None = None) -> MCPServer:
    """Builds and configures the official MCP v2 MCPServer instance with all 10 legal tools."""
    tool_impl = tools or LegalMCPTools()
    server = MCPServer(
        SERVER_NAME,
        version=SERVER_VERSION,
        description="Vietnamese Traffic Law Model Context Protocol Server",
    )

    # 1. Hybrid Search
    @server.tool(
        name="mcp_traffic_hybrid_search",
        description="Hybrid Dense (HNSW 384-dim) + Lexical Full-Text (tsvector) legal search using Reciprocal Rank Fusion (RRF).",
    )
    async def hybrid_search(
        query: str,
        dense_vector: list[float] | None = None,
        temporal_violation_date: str | None = None,
        limit: int = 10,
    ) -> HybridSearchResult:
        return await tool_impl.hybrid_search(
            query=query,
            dense_vector=dense_vector,
            temporal_violation_date=temporal_violation_date,
            limit=limit,
        )

    # 2. Verbatim Grep
    @server.tool(
        name="mcp_traffic_verbatim_grep",
        description="Deterministic verbatim keyword or regular expression search powered by PostgreSQL pg_trgm GIN index.",
    )
    async def verbatim_grep(
        pattern: str,
        is_regex: bool = False,
        case_sensitive: bool = False,
        temporal_violation_date: str | None = None,
        limit: int = 20,
    ) -> VerbatimGrepResult:
        return await tool_impl.verbatim_grep(
            pattern=pattern,
            is_regex=is_regex,
            case_sensitive=case_sensitive,
            temporal_violation_date=temporal_violation_date,
            limit=limit,
        )

    # 3. Hierarchical Navigate
    @server.tool(
        name="mcp_traffic_hierarchical_navigate",
        description="Traverse statutory hierarchies (Parent, Children, Siblings, Full Article) using PostgreSQL ltree tree operators.",
    )
    async def hierarchical_navigate(
        path: str | None = None,
        chunk_id: str | None = None,
        direction: str = "CHILDREN",
    ) -> HierarchicalNavigateResult:
        return await tool_impl.hierarchical_navigate(
            path=path,
            chunk_id=chunk_id,
            direction=direction,
        )

    # 4. Graph Traverse
    @server.tool(
        name="mcp_traffic_graph_traverse",
        description="Multi-hop graph traversal across legislative cross-references, technical standard definitions, and penalty clauses.",
    )
    async def graph_traverse(
        source_chunk_id: str,
        direction: str = "OUTGOING",
        max_depth: int = 2,
    ) -> GraphTraverseResult:
        return await tool_impl.graph_traverse(
            source_chunk_id=source_chunk_id,
            direction=direction,
            max_depth=max_depth,
        )

    # 5. Graph Edge Write
    @server.tool(
        name="mcp_traffic_graph_edge_write",
        description="Persist a new directed graph relationship edge between statutory chunks with foreign key integrity.",
    )
    async def graph_edge_write(
        source_chunk_id: str,
        relation_type: str,
        target_chunk_id: str | None = None,
        target_external_ref: str | None = None,
        citation_text: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> GraphEdgeWriteResult:
        return await tool_impl.graph_edge_write(
            source_chunk_id=source_chunk_id,
            relation_type=relation_type,
            target_chunk_id=target_chunk_id,
            target_external_ref=target_external_ref,
            citation_text=citation_text,
            metadata=metadata,
        )

    # 6. Corpus Validate
    @server.tool(
        name="mcp_traffic_corpus_validate",
        description="Validate structural integrity, total counts, and orphan chunks in the legal database.",
    )
    async def corpus_validate() -> CorpusValidateResult:
        return await tool_impl.corpus_validate()

    # 7. Staging Preview
    @server.tool(
        name="mcp_traffic_stg_preview",
        description="Preview lightweight hierarchical chunk structure in staging (.cache/stg) before promoting to PostgreSQL.",
    )
    async def stg_preview(
        doc_code: str,
        path_prefix: str | None = None,
    ) -> StgPreviewResult:
        return await tool_impl.stg_preview(
            doc_code=doc_code,
            path_prefix=path_prefix,
        )

    # 8. Staging Patch
    @server.tool(
        name="mcp_traffic_stg_patch",
        description="Surgically modify or remove candidate chunks in a staging session.",
    )
    async def stg_patch(
        doc_code: str,
        updated_chunks: list[dict[str, Any]] | None = None,
        removed_paths: list[str] | None = None,
    ) -> StgPatchResult:
        return await tool_impl.stg_patch(
            doc_code=doc_code,
            updated_chunks=updated_chunks or [],
            removed_paths=removed_paths,
        )

    # 9. Staging Add Edges
    @server.tool(
        name="mcp_traffic_stg_add_edges",
        description="Attach and deduplicate relational graph edges in a staging session.",
    )
    async def stg_add_edges(
        doc_code: str,
        edges: list[dict[str, Any]],
    ) -> StgAddEdgesResult:
        return await tool_impl.stg_add_edges(
            doc_code=doc_code,
            edges=edges,
        )

    # 10. Staging Commit
    @server.tool(
        name="mcp_traffic_stg_commit",
        description="Single-Gateway promotion from staging (.cache/stg) into live 3-table PostgreSQL with vector embeddings.",
    )
    async def stg_commit(
        doc_code: str,
        compute_embeddings: bool = True,
    ) -> StgCommitResult:
        return await tool_impl.stg_commit(
            doc_code=doc_code,
            compute_embeddings=compute_embeddings,
        )

    return server


class LegalMCPServer:
    """Wrapper providing direct execution, JSON-RPC bridge, and SDK lifecycle management."""

    def __init__(self, tools: LegalMCPTools | None = None) -> None:
        self.tools = tools or LegalMCPTools()
        self.mcp_server = create_legal_mcp_server(self.tools)

    async def get_tool_definitions(self) -> list[dict[str, Any]]:
        """Returns registered tool definitions formatted for inspection."""
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
        """Dispatches tool execution through the official MCPServer tool manager."""
        tool_name = name if name.startswith("mcp_traffic_") else f"mcp_traffic_{name}"
        res = await self.mcp_server.call_tool(tool_name, args)
        if isinstance(res, CallToolResult) and res.is_error:
            err_msg = "\n".join(
                c.text for c in res.content if isinstance(c, TextContent)
            )
            raise LegalDomainError(
                error_code=-32603,
                message=err_msg or f"Error executing tool '{name}'",
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
        """Processes JSON-RPC 2.0 requests with standardized envelope for headless CLI & tests."""
        if not isinstance(req, dict) or req.get("jsonrpc") != "2.0":
            return {
                "jsonrpc": "2.0",
                "id": req.get("id") if isinstance(req, dict) else None,
                "error": {"code": -32600, "message": "Invalid JSON-RPC 2.0 request"},
            }

        req_id = req.get("id")
        method = req.get("method", "")
        params = req.get("params") or {}

        try:
            if method == "initialize":
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
                            "message": "params must be an object",
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
                            "message": "arguments must be an object",
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
                "error": {"code": -32601, "message": f"Method not found: {method}"},
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
        """Runs the official MCPServer transport."""
        self.mcp_server.run(transport=transport)  # type: ignore


def run_mcp_server(log_file: str | None = None) -> None:
    """Entry point to run the official MCP Server over Stdio."""
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
