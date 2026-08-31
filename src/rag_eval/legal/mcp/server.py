"""Model Context Protocol (MCP) JSON-RPC 2.0 Server.

Provides a standalone JSON-RPC 2.0 server supporting standard MCP methods
(`initialize`, `notifications/initialized`, `ping`, `tools/list`, `tools/call`)
and the 8 canonical legal tools:
- mcp_traffic_hybrid_search
- mcp_traffic_verbatim_grep
- mcp_traffic_hierarchical_navigate
- mcp_traffic_graph_traverse
- mcp_traffic_graph_edge_write
- mcp_traffic_sign_catalog_lookup
- mcp_traffic_corpus_validate
- mcp_traffic_knowledge_cache_query / write
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import sys
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from rag_eval.legal.mcp.tools import (
    LegalMCPTools,
)
from rag_eval.legal.schemas import (
    InvalidParamsError,
    LegalDomainError,
)

# Standard JSON-RPC 2.0 error codes
RPC_PARSE_ERROR = -32700
RPC_INVALID_REQUEST = -32600
RPC_METHOD_NOT_FOUND = -32601
RPC_INVALID_PARAMS = -32602
RPC_INTERNAL_ERROR = -32603

# Domain-specific JSON-RPC error codes (-32001 to -32008)
E_STORAGE_CONNECTION = -32001
E_AST_GROUNDING_VALIDATION = -32002
E_CITATION_INTEGRITY_VIOLATION = -32002
E_VECTOR_DIMENSION_MISMATCH = -32003
E_UNIT_NOT_FOUND = -32004
E_CORPUS_NOT_FOUND = -32004
E_HIERARCHY_NAVIGATION = -32005
E_KNOWLEDGE_CACHE_MISS = -32006
E_PRECEDENCE_CONFLICT = -32007
E_STATEMENT_TIMEOUT = -32008
E_INVALID_LTREE_PATH = -32602
E_INVALID_PARAMS = -32602

logger = logging.getLogger("mcp_server")


class MethodNotFoundError(LegalDomainError):
    error_code = RPC_METHOD_NOT_FOUND


class HybridSearchParams(BaseModel):
    query: str = Field(description="Natural language or keywords legal search query")
    limit: int = Field(default=10, ge=1, le=100, description="Max candidate chunks")
    document_codes: list[str] | None = Field(default=None, description="Filter document codes")
    fine_min_vnd: int | None = Field(default=None, ge=0, description="Minimum fine filter in VND")
    fine_max_vnd: int | None = Field(default=None, ge=0, description="Maximum fine filter in VND")
    effective_at: str | None = Field(default=None, description="Date for temporal validity check (YYYY-MM-DD)")


class VerbatimGrepParams(BaseModel):
    pattern: str = Field(description="Exact substring or regex pattern")
    is_regex: bool = Field(default=False, description="Whether pattern is regular expression")
    limit: int = Field(default=20, ge=1, le=100, description="Max matches")
    document_codes: list[str] | None = Field(default=None, description="Filter document codes")
    fine_min_vnd: int | None = Field(default=None, ge=0, description="Minimum fine filter in VND")
    fine_max_vnd: int | None = Field(default=None, ge=0, description="Maximum fine filter in VND")
    case_sensitive: bool = Field(default=False, description="Case-sensitive search")
    effective_at: str | None = Field(default=None, description="Date for temporal validity check (YYYY-MM-DD)")


class HierarchicalNavigateParams(BaseModel):
    target_path: str = Field(description="ltree hierarchy path, e.g. 'doc_nd100_2019.a5.c3.p_a'")
    direction: str = Field(
        default="children", description="Navigation direction: children, parent_chain, siblings, full_article"
    )
    include_verbatim: bool = Field(default=True, description="Whether to include full verbatim text")
    depth: int = Field(default=1, ge=1, le=10, description="Hierarchy traversal depth")


class GraphTraverseParams(BaseModel):
    start_chunk_id: str = Field(description="Starting chunk UUID")
    direction: str = Field(default="both", description="Traversal direction")
    relation_types: list[str] | None = Field(default=None, description="Filter edge relation types")
    max_depth: int = Field(default=2, ge=1, le=5, description="Max traversal depth")


class GraphEdgeWriteParams(BaseModel):
    model_config = ConfigDict(extra="allow")

    source_chunk_id: str | None = Field(default=None, description="Source chunk UUID")
    source_id: str | None = Field(default=None, description="Source chunk UUID alias")
    target_chunk_id: str | None = Field(default=None, description="Target chunk UUID")
    target_id: str | None = Field(default=None, description="Target chunk UUID alias")
    target_path: str | None = Field(default=None, description="Target ltree path")
    relation_type: str = Field(default="REFERENCES_TECHNICAL_STANDARD", description="Canonical edge relation type")
    confidence_score: float | None = Field(default=None, ge=0.0, le=1.0, description="Edge confidence score")
    confidence: float | None = Field(default=None, ge=0.0, le=1.0, description="Confidence alias")
    is_bidirectional: bool = Field(default=False, description="Whether to insert reverse edge")
    condition_expression: str | None = Field(default=None, description="Condition expression for CONDITIONAL edges")


class SignCatalogLookupParams(BaseModel):
    sign_code: str | None = Field(default=None, description="Sign code, e.g. P.102")
    keywords: str | None = Field(default=None, description="Keywords to match sign name/meaning")
    query: str | None = Field(default=None, description="Query string alias")
    category: str | None = Field(default=None, description="Sign category filter")
    limit: int = Field(default=10, ge=1, le=50, description="Max signs returned")


class CorpusValidateParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: str = Field(default="", description="Document UUID")
    document_code: str = Field(default="", description="Official document code, e.g. 100/2019/ND-CP")


class KnowledgeCacheQueryParams(BaseModel):
    query: str = Field(default="", description="User query string")
    natural_query: str = Field(default="", description="User natural query string")
    query_hash: str | None = Field(default=None, description="SHA-256 query hash")
    query_vector: list[float] | None = Field(default=None, description="Query embedding vector")
    similarity_threshold: float = Field(default=0.965, ge=0.0, le=1.0, description="Cosine similarity threshold")

    @field_validator("query_vector", mode="after")
    @classmethod
    def validate_vector(cls, v: list[float] | None) -> list[float] | None:
        if v is not None:
            if any(math.isnan(x) or math.isinf(x) for x in v):
                raise ValueError("Query vector contains non-finite values (NaN or Inf)")
            if len(v) not in (384, 1536):
                raise ValueError(f"Invalid vector dimension: {len(v)} (expected 384 or 1536)")
        return v


class KnowledgeCacheWriteParams(BaseModel):
    query: str = Field(default="", description="User query string")
    natural_query: str = Field(default="", description="User natural query string")
    synthesized_answer: str = Field(default="", description="Synthesized legal answer")
    answer: str = Field(default="", description="Legal answer")
    citations: list[str] | list[dict[str, object]] = Field(default_factory=list, description="Citations")
    retrieved_chunk_ids: list[str] = Field(default_factory=list, description="Referenced chunk IDs")
    verified_citations: list[dict[str, object]] | list[str] = Field(default_factory=list, description="Verified citations")
    intent_classification: dict[str, object] | None = Field(default=None, description="Intent metadata")
    generated_plan: dict[str, object] | None = Field(default=None, description="Execution plan")
    traversed_edge_ids: list[str] = Field(default_factory=list, description="Traversed edge IDs")
    ttl_hours: int = Field(default=720, ge=1, le=8760, description="TTL in hours")


class JSONRPCRequest(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: str | int | None = None
    method: str
    params: dict[str, object] | list[object] | None = None


class JSONRPCError(BaseModel):
    code: int
    message: str
    data: object | None = None


class JSONRPCResponse(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    result: object | None = None
    error: JSONRPCError | None = None
    id: str | int | None = None


# Backward-compatible alias
MCPResponse = JSONRPCResponse


class MCPServer:
    """Production JSON-RPC 2.0 Model Context Protocol Server."""

    def __init__(self, tools: LegalMCPTools | None = None) -> None:
        self.tools = tools or LegalMCPTools()
        self._shutdown_event = asyncio.Event()

    def get_tool_definitions(self) -> list[dict[str, object]]:
        """Returns the canonical schema definitions for the 8 legal MCP tools."""
        return [
            {
                "name": "mcp_traffic_hybrid_search",
                "description": "Performs Reciprocal Rank Fusion (RRF) hybrid dense vector + lexical tsvector search over Vietnamese Traffic Law chunks.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Natural language query or keywords"},
                        "limit": {"type": "integer", "default": 10, "minimum": 1, "maximum": 100},
                        "document_codes": {"type": "array", "items": {"type": "string"}},
                        "fine_min_vnd": {"type": "integer"},
                        "fine_max_vnd": {"type": "integer"},
                        "effective_at": {"type": "string", "description": "YYYY-MM-DD"},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "mcp_traffic_verbatim_grep",
                "description": "Performs Trigram GIN accelerated verbatim substring and regex search over statutory texts with ReDoS protection.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string", "description": "Exact text or regex pattern"},
                        "is_regex": {"type": "boolean", "default": False},
                        "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 100},
                        "document_codes": {"type": "array", "items": {"type": "string"}},
                        "case_sensitive": {"type": "boolean", "default": False},
                        "effective_at": {"type": "string", "description": "YYYY-MM-DD"},
                    },
                    "required": ["pattern"],
                },
            },
            {
                "name": "mcp_traffic_hierarchical_navigate",
                "description": "Navigates statutory hierarchy using PostgreSQL ltree (parents, children, siblings, full article).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "target_path": {"type": "string", "description": "ltree path e.g. doc_100_2019_nd_cp.c2.a5"},
                        "direction": {"type": "string", "enum": ["children", "parents", "parent_chain", "siblings", "full_article", "descendants"], "default": "children"},
                        "include_verbatim": {"type": "boolean", "default": True},
                    },
                    "required": ["target_path"],
                },
            },
            {
                "name": "mcp_traffic_graph_traverse",
                "description": "Traverses normative property graph edges (sanctions, standards, exceptions, amendments).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "start_chunk_id": {"type": "string", "description": "Starting chunk UUID"},
                        "relation_types": {"type": "array", "items": {"type": "string"}},
                        "direction": {"type": "string", "enum": ["outgoing", "incoming", "both"], "default": "both"},
                        "max_depth": {"type": "integer", "default": 2, "minimum": 1, "maximum": 5},
                    },
                    "required": ["start_chunk_id"],
                },
            },
            {
                "name": "mcp_traffic_graph_edge_write",
                "description": "Creates or updates an explicit graph relation edge between legal chunks.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "source_chunk_id": {"type": "string"},
                        "target_chunk_id": {"type": "string"},
                        "target_path": {"type": "string"},
                        "relation_type": {"type": "string"},
                        "confidence_score": {"type": "number", "default": 1.0},
                    },
                    "required": ["relation_type"],
                },
            },
            {
                "name": "mcp_traffic_sign_catalog_lookup",
                "description": "Looks up traffic signs, signals, and road markings under standard QCVN 41:2019.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "sign_code": {"type": "string"},
                        "keywords": {"type": "string"},
                        "limit": {"type": "integer", "default": 10},
                    },
                },
            },
            {
                "name": "mcp_traffic_corpus_validate",
                "description": "Validates structural integrity, orphaned nodes, broken graph edges, and missing embeddings of a document.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "document_id": {"type": "string"},
                        "document_code": {"type": "string"},
                    },
                },
            },
            {
                "name": "mcp_traffic_knowledge_cache_query",
                "description": "Queries the runtime verified knowledge cache via SHA-256 exact match and single-pass HNSW vector similarity.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "similarity_threshold": {"type": "number", "default": 0.965},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "mcp_traffic_knowledge_cache_write",
                "description": "Writes a verified legal answer, citation chain, and plan to runtime cache with auto-invalidation triggers.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "synthesized_answer": {"type": "string"},
                        "retrieved_chunk_ids": {"type": "array", "items": {"type": "string"}},
                        "verified_citations": {"type": "array", "items": {"type": "object"}},
                        "intent_classification": {"type": "object"},
                        "generated_plan": {"type": "object"},
                        "traversed_edge_ids": {"type": "array", "items": {"type": "string"}},
                        "ttl_hours": {"type": "integer", "default": 720},
                    },
                    "required": ["query", "synthesized_answer"],
                },
            },
        ]

    async def handle_tool_call(self, tool_name: str, arguments: dict[str, object]) -> dict[str, object]:
        """Dispatches tool execution directly to LegalMCPTools."""
        if tool_name == "mcp_traffic_hybrid_search":
            p = HybridSearchParams.model_validate(arguments)
            res = await self.tools.hybrid_search(
                query=p.query,
                limit=p.limit,
                document_codes=p.document_codes,
                effective_at=p.effective_at,
            )
            return res.model_dump()

        if tool_name == "mcp_traffic_verbatim_grep":
            p_grep = VerbatimGrepParams.model_validate(arguments)
            res = await self.tools.verbatim_grep(
                pattern=p_grep.pattern,
                is_regex=p_grep.is_regex,
                limit=p_grep.limit,
                document_codes=p_grep.document_codes,
                case_sensitive=p_grep.case_sensitive,
                effective_at=p_grep.effective_at,
            )
            return res.model_dump()

        if tool_name == "mcp_traffic_hierarchical_navigate":
            p_nav = HierarchicalNavigateParams.model_validate(arguments)
            res = await self.tools.hierarchical_navigate(
                target_path=p_nav.target_path,
                direction=p_nav.direction,
                include_verbatim=p_nav.include_verbatim,
            )
            return res.model_dump()

        if tool_name == "mcp_traffic_graph_traverse":
            p_trav = GraphTraverseParams.model_validate(arguments)
            res = await self.tools.graph_traverse(
                start_chunk_id=p_trav.start_chunk_id,
                relation_types=p_trav.relation_types,
                direction=p_trav.direction,
                max_depth=p_trav.max_depth,
            )
            return res.model_dump()

        if tool_name == "mcp_traffic_graph_edge_write":
            p_edge = GraphEdgeWriteParams.model_validate(arguments)
            src_id = p_edge.source_chunk_id or p_edge.source_id or ""
            tgt_id = p_edge.target_chunk_id or p_edge.target_id
            conf = p_edge.confidence_score if p_edge.confidence_score is not None else (p_edge.confidence if p_edge.confidence is not None else 1.0)
            res = await self.tools.graph_edge_write(
                source_id=src_id,
                target_id=tgt_id,
                target_path=p_edge.target_path,
                relation_type=p_edge.relation_type,
                confidence_score=conf,
            )
            return res.model_dump()

        if tool_name == "mcp_traffic_sign_catalog_lookup":
            p_sign = SignCatalogLookupParams.model_validate(arguments)
            res = await self.tools.sign_catalog_lookup(
                sign_code=p_sign.sign_code,
                query_keyword=p_sign.keywords,
                limit=p_sign.limit,
            )
            return res.model_dump()

        if tool_name == "mcp_traffic_corpus_validate":
            p_val = CorpusValidateParams.model_validate(arguments)
            res = await self.tools.corpus_validate(
                document_id=p_val.document_id or None,
            )
            return res.model_dump()

        if tool_name == "mcp_traffic_knowledge_cache_query":
            p_cq = KnowledgeCacheQueryParams.model_validate(arguments)
            q = p_cq.natural_query or p_cq.query
            res = await self.tools.knowledge_cache_query(
                natural_query=q,
                query_vector=p_cq.query_vector,
                similarity_threshold=p_cq.similarity_threshold,
                query_hash=p_cq.query_hash,
            )
            return res.model_dump()

        if tool_name == "mcp_traffic_knowledge_cache_write":
            p_cw = KnowledgeCacheWriteParams.model_validate(arguments)
            q = p_cw.natural_query or p_cw.query
            ans = p_cw.synthesized_answer or p_cw.answer
            cits = p_cw.verified_citations or p_cw.citations
            res = await self.tools.knowledge_cache_write(
                natural_query=q,
                synthesized_answer=ans,
                retrieved_chunk_ids=p_cw.retrieved_chunk_ids,
                verified_citations=cast(list[object], cits),
                intent_classification=p_cw.intent_classification,
                generated_plan=p_cw.generated_plan,
                traversed_edge_ids=p_cw.traversed_edge_ids,
                ttl_seconds=p_cw.ttl_hours * 3600,
            )
            return res.model_dump()

        raise MethodNotFoundError(f"Method not found or unknown tool: {tool_name}")

    async def handle_request_dict(self, request_data: dict[str, object]) -> dict[str, object]:
        """Dispatches an incoming JSON-RPC dictionary request and returns response dictionary."""
        req_id = request_data.get("id")
        method = str(request_data.get("method") or "")
        params = request_data.get("params")

        try:
            if method == "initialize":
                self.initialized = True
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {"listChanged": False}},
                        "serverInfo": {"name": "vietnamese-traffic-law-mcp", "version": "2.0.0"},
                    },
                }

            if method == "notifications/initialized":
                return {}

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
                    raise InvalidParamsError("Invalid params: params must be an object")
                name = str(params.get("name") or "")
                arguments = params.get("arguments") or {}
                if not isinstance(arguments, dict):
                    raise InvalidParamsError("Invalid arguments: arguments must be an object")
                res = await self.handle_tool_call(name, arguments)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": res,
                }

            if method.startswith("mcp_traffic_"):
                arguments = params if isinstance(params, dict) else {}
                res = await self.handle_tool_call(method, arguments)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": res,
                }

            return self._error_response(req_id, RPC_METHOD_NOT_FOUND, f"Method not found: {method}")

        except ValidationError as v_err:
            err_str = str(v_err).lower()
            if "non-finite" in err_str or "dimension" in err_str or "vector" in err_str:
                return self._error_response(req_id, E_VECTOR_DIMENSION_MISMATCH, str(v_err), v_err.errors())
            return self._error_response(req_id, RPC_INVALID_PARAMS, str(v_err), v_err.errors())
        except LegalDomainError as err:
            return self._error_response(req_id, err.error_code, err.message, err.data)
        except (RuntimeError, ValueError, TypeError, OSError, KeyError, AttributeError):
            logger.exception("Unhandled exception processing request %s", method)
            return self._error_response(req_id, RPC_INTERNAL_ERROR, "Internal server error")

    def _error_response(self, req_id: object, code: int, message: str, data: object | None = None) -> dict[str, object]:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": code,
                "message": message,
                "data": data,
            },
        }

    async def handle_request(self, request_data: dict[str, object] | str) -> dict[str, object] | None:
        """Handles a single JSON-RPC request from dict or string."""
        if isinstance(request_data, str):
            res_str = await self.handle_raw_line(request_data)
            return json.loads(res_str) if res_str else None

        if not isinstance(request_data, dict):
            return self._error_response(None, RPC_INVALID_REQUEST, "Invalid request")

        req_id = request_data.get("id")
        if request_data.get("jsonrpc") != "2.0" or "method" not in request_data:
            return self._error_response(req_id, RPC_INVALID_REQUEST, "Invalid JSON-RPC 2.0 request")

        method = str(request_data.get("method") or "")
        if method == "notifications/initialized":
            return None

        return await self.handle_request_dict(request_data)

    async def call_tool(self, tool_name: str, arguments: dict[str, object], req_id: str | int = 1) -> dict[str, object]:
        """Convenience method to execute a tool via JSON-RPC 2.0 tools/call."""
        req: dict[str, object] = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }
        res = await self.handle_request(req)
        return res or {}

    async def handle_raw_line(self, line: str) -> str:
        """Processes a single raw JSON-RPC string line."""
        clean = line.strip()
        if not clean:
            return ""
        try:
            req_dict = json.loads(clean)
            if not isinstance(req_dict, dict):
                return json.dumps(self._error_response(None, RPC_INVALID_REQUEST, "Invalid request"))
        except json.JSONDecodeError as err:
            return json.dumps(self._error_response(None, RPC_PARSE_ERROR, f"Parse error: {err}"))

        res = await self.handle_request_dict(req_dict)
        return json.dumps(res) if res else ""

    async def run_stdio_server(self) -> None:
        """Runs the MCP server over standard I/O (stdio)."""
        logger.info("Starting Vietnamese Traffic Law MCP Server on stdio...")
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await asyncio.get_running_loop().connect_read_pipe(lambda: protocol, sys.stdin)

        while not self._shutdown_event.is_set():
            line_bytes = await reader.readline()
            if not line_bytes:
                break
            line_str = line_bytes.decode("utf-8")
            response_json = await self.handle_raw_line(line_str)
            if response_json:
                sys.stdout.write(response_json + "\n")
                sys.stdout.flush()


LegalMCPServer = MCPServer


async def run_mcp_server(
    log_file: str | None = "logs/mcp_server.log",
) -> None:
    """Entry point for running MCP server asynchronously."""
    server = MCPServer()
    await server.run_stdio_server()


def main() -> None:
    """CLI entrypoint for standalone MCP server."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    server = MCPServer()
    try:
        asyncio.run(server.run_stdio_server())
    except (KeyboardInterrupt, SystemExit):
        logger.info("MCP server stopped.")


if __name__ == "__main__":
    main()
