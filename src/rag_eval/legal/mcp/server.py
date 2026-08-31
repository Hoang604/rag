"""Vietnamese Traffic Law Model Context Protocol (MCP) Server.

Implements a compliant JSON-RPC 2.0 Stdio transport server exposing the 6 canonical
Agent-First legal tools with Pydantic v2 argument validation.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from rag_eval.legal.mcp.tools import (
    CorpusValidateResult,
    GraphEdgeWriteResult,
    GraphTraverseResult,
    HierarchicalNavigateResult,
    HybridSearchResult,
    LegalMCPTools,
    VerbatimGrepResult,
)
from rag_eval.legal.schemas import (
    LegalDomainError,
)

logger = logging.getLogger("rag_eval.legal.mcp.server")

RPC_PARSE_ERROR = -32700
RPC_INVALID_REQUEST = -32600
RPC_METHOD_NOT_FOUND = -32601
RPC_INVALID_PARAMS = -32602
RPC_INTERNAL_ERROR = -32603


# ------------------------------------------------------------------------------
# Tool Input Parameters
# ------------------------------------------------------------------------------
class MCPBaseParams(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class HybridSearchParams(MCPBaseParams):
    query: str = Field(..., min_length=1, description="Natural language search query")
    dense_vector: list[float] | None = Field(
        None, description="Pre-computed 384-dim dense embedding vector"
    )
    temporal_violation_date: str | None = Field(
        None, description="Date of violation (YYYY-MM-DD) for effectivity filtering"
    )
    limit: int = Field(10, ge=1, le=100, description="Maximum number of hits to return")

    @field_validator("dense_vector", mode="after")
    @classmethod
    def validate_vector(cls, v: list[float] | None) -> list[float] | None:
        if v is not None:
            if len(v) not in (384, 1536):
                raise ValueError(
                    f"Vector dimension must be exactly 384 or 1536 (got {len(v)})"
                )
            for idx, val in enumerate(v):
                if math.isnan(val) or math.isinf(val):
                    raise ValueError(f"Vector contains non-finite float at index {idx}: {val}")
        return v


class VerbatimGrepParams(MCPBaseParams):
    pattern: str = Field(..., min_length=1, description="Exact phrase or regular expression")
    is_regex: bool = Field(False, description="Whether pattern is a regular expression")
    case_sensitive: bool = Field(False, description="Case-sensitive matching flag")
    temporal_violation_date: str | None = Field(
        None, description="Date of violation (YYYY-MM-DD) for effectivity filtering"
    )
    limit: int = Field(20, ge=1, le=200, description="Maximum results")


class HierarchicalNavigateParams(MCPBaseParams):
    chunk_id: str | None = Field(None, description="Target chunk UUID or ID")
    path: str | None = Field(None, description="Dot-separated hierarchical ltree path")
    direction: str = Field(
        "CHILDREN",
        description="Navigation direction: PARENT_CHAIN | CHILDREN | SIBLINGS | FULL_ARTICLE",
    )


class GraphTraverseParams(MCPBaseParams):
    source_chunk_id: str = Field(..., description="Root chunk UUID to start traversal from")
    direction: str = Field("OUTGOING", description="Traversal direction: OUTGOING")
    max_depth: int = Field(2, ge=1, le=5, description="Maximum hops to explore")


class GraphEdgeWriteParams(MCPBaseParams):
    source_chunk_id: str = Field(..., description="Source chunk UUID")
    target_chunk_id: str | None = Field(None, description="Target chunk UUID")
    target_external_ref: str | None = Field(None, description="Target external citation")
    relation_type: str = Field(..., description="Graph relation type")
    citation_text: str | None = Field(None, description="Verbatim statutory citation phrase")
    metadata: dict[str, Any] | None = Field(None, description="Metadata dictionary")


class CorpusValidateParams(MCPBaseParams):
    pass


# ------------------------------------------------------------------------------
# LegalMCPServer
# ------------------------------------------------------------------------------
class LegalMCPServer:
    """Production JSON-RPC 2.0 MCP server for Vietnamese Traffic Law reasoning."""

    PROTOCOL_VERSION = "2024-11-05"
    SERVER_NAME = "vietnamese-traffic-law-mcp"
    SERVER_VERSION = "3.0.0"

    def __init__(self, tools: LegalMCPTools | None = None) -> None:
        self.tools = tools or LegalMCPTools()
        self._is_initialized = False

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """Returns canonical MCP tool definitions."""
        return [
            {
                "name": "mcp_traffic_hybrid_search",
                "description": "Hybrid Dense (HNSW 384-dim) + Lexical Full-Text (tsvector) legal search using Reciprocal Rank Fusion (RRF).",
                "inputSchema": HybridSearchParams.model_json_schema(),
            },
            {
                "name": "mcp_traffic_verbatim_grep",
                "description": "Deterministic verbatim keyword or regular expression search powered by PostgreSQL pg_trgm GIN index.",
                "inputSchema": VerbatimGrepParams.model_json_schema(),
            },
            {
                "name": "mcp_traffic_hierarchical_navigate",
                "description": "Traverse statutory hierarchies (Parent, Children, Siblings, Full Article) using PostgreSQL ltree tree operators.",
                "inputSchema": HierarchicalNavigateParams.model_json_schema(),
            },
            {
                "name": "mcp_traffic_graph_traverse",
                "description": "Multi-hop graph traversal across legislative cross-references, technical standard definitions, and penalty clauses.",
                "inputSchema": GraphTraverseParams.model_json_schema(),
            },
            {
                "name": "mcp_traffic_graph_edge_write",
                "description": "Persist a new directed graph relationship edge between statutory chunks with foreign key integrity.",
                "inputSchema": GraphEdgeWriteParams.model_json_schema(),
            },
            {
                "name": "mcp_traffic_corpus_validate",
                "description": "Validate structural integrity, total counts, and orphan chunks in the legal database.",
                "inputSchema": CorpusValidateParams.model_json_schema(),
            },
        ]

    async def execute_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Dispatches and validates tool execution."""
        clean_name = name.removeprefix("mcp_traffic_")

        if clean_name == "hybrid_search":
            p1 = HybridSearchParams.model_validate(args)
            res1: HybridSearchResult = await self.tools.hybrid_search(
                query=p1.query,
                dense_vector=p1.dense_vector,
                temporal_violation_date=p1.temporal_violation_date,
                limit=p1.limit,
            )
            return res1.model_dump(mode="json")

        elif clean_name == "verbatim_grep":
            p2 = VerbatimGrepParams.model_validate(args)
            res2: VerbatimGrepResult = await self.tools.verbatim_grep(
                pattern=p2.pattern,
                is_regex=p2.is_regex,
                case_sensitive=p2.case_sensitive,
                temporal_violation_date=p2.temporal_violation_date,
                limit=p2.limit,
            )
            return res2.model_dump(mode="json")

        elif clean_name == "hierarchical_navigate":
            p3 = HierarchicalNavigateParams.model_validate(args)
            res3: HierarchicalNavigateResult = await self.tools.hierarchical_navigate(
                path=p3.path,
                chunk_id=p3.chunk_id,
                direction=p3.direction,
            )
            return res3.model_dump(mode="json")

        elif clean_name == "graph_traverse":
            p4 = GraphTraverseParams.model_validate(args)
            res4: GraphTraverseResult = await self.tools.graph_traverse(
                source_chunk_id=p4.source_chunk_id,
                direction=p4.direction,
                max_depth=p4.max_depth,
            )
            return res4.model_dump(mode="json")

        elif clean_name == "graph_edge_write":
            p5 = GraphEdgeWriteParams.model_validate(args)
            res5: GraphEdgeWriteResult = await self.tools.graph_edge_write(
                source_chunk_id=p5.source_chunk_id,
                relation_type=p5.relation_type,
                target_chunk_id=p5.target_chunk_id,
                target_external_ref=p5.target_external_ref,
                citation_text=p5.citation_text,
                metadata=p5.metadata,
            )
            return res5.model_dump(mode="json")

        elif clean_name == "corpus_validate":
            res6: CorpusValidateResult = await self.tools.corpus_validate()
            return res6.model_dump(mode="json")

        raise LegalDomainError(
            error_code=RPC_METHOD_NOT_FOUND,
            message=f"Method '{name}' not found",
        )

    async def handle_request_dict(self, req: dict[str, Any]) -> dict[str, Any] | None:
        """Processes an incoming JSON-RPC 2.0 request."""
        if not isinstance(req, dict) or req.get("jsonrpc") != "2.0":
            return self._error_response(req.get("id"), RPC_INVALID_REQUEST, "Invalid JSON-RPC 2.0 request")

        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params")

        if not isinstance(method, str):
            return self._error_response(req_id, RPC_INVALID_REQUEST, "Missing or invalid method")

        try:
            if method == "initialize":
                self._is_initialized = True
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": self.PROTOCOL_VERSION,
                        "capabilities": {"tools": {}},
                        "serverInfo": {
                            "name": self.SERVER_NAME,
                            "version": self.SERVER_VERSION,
                        },
                    },
                }

            if method == "notifications/initialized":
                return None

            if method == "ping":
                return {"jsonrpc": "2.0", "id": req_id, "result": {}}

            if method == "tools/list":
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"tools": self.get_tool_definitions()},
                }

            if method == "tools/call":
                if not isinstance(params, dict):
                    return self._error_response(req_id, RPC_INVALID_PARAMS, "params must be an object")
                name_arg = params.get("name")
                args_arg = params.get("arguments", {})
                if not isinstance(name_arg, str) or not isinstance(args_arg, dict):
                    return self._error_response(req_id, RPC_INVALID_PARAMS, "Invalid tool call arguments")
                res = await self.execute_tool(name_arg, args_arg)
                return {"jsonrpc": "2.0", "id": req_id, "result": res}

            if method.startswith("mcp_traffic_"):
                args = params if isinstance(params, dict) else {}
                res = await self.execute_tool(method, args)
                return {"jsonrpc": "2.0", "id": req_id, "result": res}

            return self._error_response(req_id, RPC_METHOD_NOT_FOUND, f"Method not found: {method}")

        except ValidationError as v_err:
            return self._error_response(req_id, RPC_INVALID_PARAMS, str(v_err), v_err.errors())
        except LegalDomainError as err:
            return self._error_response(req_id, err.error_code, err.message, err.data)
        except (RuntimeError, ValueError, TypeError, KeyError, OSError) as exc:
            logger.exception("Internal error in MCP server")
            return self._error_response(req_id, RPC_INTERNAL_ERROR, f"Internal server error: {exc}")

    def _error_response(
        self, req_id: Any, code: int, message: str, data: Any = None
    ) -> dict[str, Any]:
        err: dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            err["data"] = data
        return {"jsonrpc": "2.0", "id": req_id, "error": err}


async def run_mcp_server(log_file: str | None = None) -> None:
    """Runs MCP JSON-RPC Server over standard input/output."""
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            filename=log_file,
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )

    server = LegalMCPServer()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    loop = asyncio.get_running_loop()
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    while True:
        line = await reader.readline()
        if not line:
            break
        try:
            req = json.loads(line.decode("utf-8"))
            resp = await server.handle_request_dict(req)
            if resp is not None:
                sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
                sys.stdout.flush()
        except json.JSONDecodeError as err:
            err_resp = server._error_response(None, RPC_PARSE_ERROR, f"Parse error: {err}")
            sys.stdout.write(json.dumps(err_resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()
