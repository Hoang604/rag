"""Model Context Protocol (MCP) JSON-RPC 2.0 Server.

Provides a standalone JSON-RPC 2.0 server supporting the standard MCP methods
(`initialize`, `notifications/initialized`, `ping`, `tools/list`, `tools/call`)
and the 7 specialized legal tools:
- mcp_traffic_corpus_validate
- mcp_traffic_hybrid_search
- mcp_traffic_hierarchical_navigate
- mcp_traffic_graph_traverse
- mcp_traffic_scope_override_detect
- mcp_traffic_sign_catalog_lookup
- mcp_traffic_knowledge_cache_query / write
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

if TYPE_CHECKING:
    from rag_eval.legal.mcp.tools import LegalMCPTools

logger = logging.getLogger(__name__)

# Standard JSON-RPC 2.0 Error Codes
RPC_PARSE_ERROR = -32700
RPC_INVALID_REQUEST = -32600
RPC_METHOD_NOT_FOUND = -32601
RPC_INVALID_PARAMS = -32602
RPC_INTERNAL_ERROR = -32603

# Domain-Specific Legal Retrieval Error Codes (docs/03 Section 5.1)
E_STORAGE_CONNECTION = -32001
E_UNIT_NOT_FOUND = -32001
E_CORPUS_NOT_FOUND = -32002
E_INVALID_LTREE_PATH = -32002
E_VECTOR_DIMENSION_MISMATCH = -32003
E_DISCONNECTED_GRAPH_EDGE = -32003
E_HIERARCHY_NAVIGATION = -32004
E_AMBIGUOUS_VEHICLE_SCOPE = -32004
E_KNOWLEDGE_CACHE_MISS = -32005
E_TEMPORAL_OUT_OF_BOUNDS = -32005
E_PRECEDENCE_CONFLICT = -32006
E_CORPUS_VALIDATION_FAILED = -32006
E_AST_GROUNDING_VALIDATION = -32007
E_RATE_LIMIT_EXCEEDED = -32007
E_STATEMENT_TIMEOUT = -32008


# ==============================================================================
# Domain Error Hierarchy (F-13)
# ==============================================================================


class LegalDomainError(Exception):
    """Base exception class for Vietnamese Legal Domain Model Context Protocol errors."""

    def __init__(
        self,
        message: str,
        code: int = RPC_INTERNAL_ERROR,
        data: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data: dict[str, Any] = data or {}


class StorageConnectionError(LegalDomainError):
    """Raised when database or storage backend connection fails or errors (-32001)."""

    def __init__(
        self,
        message: str = "Database storage connection failed",
        data: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, code=E_STORAGE_CONNECTION, data=data)


class CorpusNotFoundError(LegalDomainError):
    """Raised when a requested corpus, document, or legal unit is not found (-32002)."""

    def __init__(
        self,
        message: str = "Corpus or legal document unit not found",
        data: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, code=E_CORPUS_NOT_FOUND, data=data)


class VectorDimensionMismatchError(LegalDomainError):
    """Raised when dense embedding vector dimensions do not match expected index schema (-32003)."""

    def __init__(
        self,
        message: str = "Vector dimension mismatch in dense query",
        data: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, code=E_VECTOR_DIMENSION_MISMATCH, data=data)


class HierarchyNavigationError(LegalDomainError):
    """Raised when statutory hierarchy navigation fails or encounters invalid ltree syntax (-32004)."""

    def __init__(
        self,
        message: str = "Hierarchy tree navigation failed",
        data: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, code=E_HIERARCHY_NAVIGATION, data=data)


class KnowledgeCacheMissError(LegalDomainError):
    """Raised when a required knowledge cache entry is missing or inaccessible (-32005)."""

    def __init__(
        self,
        message: str = "Knowledge cache entry not found",
        data: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, code=E_KNOWLEDGE_CACHE_MISS, data=data)


class PrecedenceConflictError(LegalDomainError):
    """Raised when an unresolvable conflict occurs during statutory precedence evaluation (-32006)."""

    def __init__(
        self,
        message: str = "Unresolvable precedence conflict between statutory provisions",
        data: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, code=E_PRECEDENCE_CONFLICT, data=data)


class ASTGroundingValidationError(LegalDomainError):
    """Raised when AST grounding or structural corpus validation encounters fatal anomalies (-32007)."""

    def __init__(
        self,
        message: str = "AST grounding validation failed",
        data: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, code=E_AST_GROUNDING_VALIDATION, data=data)


class StatementTimeoutError(LegalDomainError):
    """Raised when database query execution exceeds statement timeout threshold (-32008)."""

    def __init__(
        self,
        message: str = "Query execution exceeded 5000ms statement timeout threshold",
        data: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, code=E_STATEMENT_TIMEOUT, data=data)


# Aliases for backward compatibility and spec alignment
UnitNotFoundError = CorpusNotFoundError
InvalidLtreePathError = HierarchyNavigationError
DisconnectedGraphEdgeError = HierarchyNavigationError
AmbiguousVehicleScopeError = LegalDomainError
TemporalOutOfBoundsError = LegalDomainError
CorpusValidationFailedError = ASTGroundingValidationError
RateLimitExceededError = LegalDomainError



# ==============================================================================
# Pydantic v2 Tool Input Parameter Schemas
# ==============================================================================


class CorpusValidateParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: str = Field(
        ...,
        description="UUID or document identifier in legal_documents table.",
    )
    check_orphaned_points: bool = Field(
        default=True,
        description="Check for Points lacking parent Khoản lead sentences.",
    )
    check_missing_embeddings: bool = Field(
        default=True,
        description="Verify that all contextualized legal chunks have dense embeddings.",
    )
    check_broken_edges: bool = Field(
        default=True,
        description="Audit outgoing legal_graph_edges for unresolvable pointers.",
    )
    check_path_continuity: bool = Field(
        default=True,
        description="Verify that all ltree paths correctly reflect hierarchy depth.",
    )


class HybridSearchParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(
        ...,
        description="Natural language query or legal search text in Vietnamese.",
    )
    query_vector: list[float] | None = Field(
        default=None,
        description="Optional dense embedding vector (384 or 1536 dim).",
    )
    vehicle_types: list[str] | None = Field(
        default=None,
        description="Target vehicle categories (e.g. ['CAR_PASSENGER', 'MOTORCYCLE', 'CAR']).",
    )
    actor_category: str | None = Field(
        default=None,
        description="Primary legal actor subject (e.g. 'DRIVER', 'PEDESTRIAN').",
    )
    norm_roles: list[str] | None = Field(
        default=None,
        description="Filter by statutory norm roles (e.g. ['SANCTION_PRINCIPAL']).",
    )
    fine_min_vnd: int | None = Field(
        default=None, ge=0, description="Minimum penalty fine threshold in VND."
    )
    fine_max_vnd: int | None = Field(
        default=None, ge=0, description="Maximum penalty fine threshold in VND."
    )
    document_codes: list[str] | None = Field(
        default=None,
        description="Whitelist of statutory document codes (e.g. ['100/2019/ND-CP']).",
    )
    effective_as_of: str | None = Field(
        default=None,
        description="ISO date (YYYY-MM-DD) to enforce temporal validity filtering.",
    )
    limit: int = Field(
        default=10, ge=1, le=50, description="Maximum number of results to return."
    )


class HierarchicalNavigateParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_path: str = Field(
        ...,
        description="Ltree path of target node (e.g. 'doc_100_2019_nd_cp.a5.c3.p_a').",
    )
    direction: Literal["PARENT_CHAIN", "CHILDREN", "SIBLINGS", "FULL_ARTICLE"] = Field(
        default="PARENT_CHAIN",
        description="Navigation trajectory relative to target ltree path.",
    )
    include_verbatim: bool = Field(
        default=True,
        description="Whether to return verbatim statutory text with headers.",
    )


class GraphTraverseParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_chunk_id: str = Field(
        ...,
        description="UUID or chunk identifier of originating legal chunk node.",
    )
    relation_types: list[str] | None = Field(
        default=None,
        description="Edge types to follow (e.g. ['REFERENCES_TECHNICAL_STANDARD']).",
    )
    direction: Literal["OUTGOING", "INCOMING", "BOTH"] = Field(
        default="BOTH", description="Direction of graph traversal."
    )
    max_depth: int = Field(
        default=2, ge=1, le=4, description="Maximum traversal depth hops (1..4)."
    )


class ScopeOverrideContextConditions(BaseModel):
    model_config = ConfigDict(extra="allow")
    is_emergency_vehicle: bool = Field(
        default=False,
        description="True if vehicle belongs to a privileged emergency category.",
    )
    emergency_type: str = Field(
        default="NONE",
        description="Privileged category (e.g. 'AMBULANCE_ON_DUTY', 'FIRE_TRUCK').",
    )
    emergency_signals_active: bool = Field(
        default=False,
        description="Whether emergency siren/beacon lights were engaged.",
    )
    conflicting_signals: list[str] = Field(
        default_factory=list,
        description="List of co-present conflicting traffic signals.",
    )
    police_signal_instruction: str = Field(
        default="", description="Command given by traffic police officer."
    )


class ScopeOverrideDetectParams(BaseModel):
    model_config = ConfigDict(extra="allow")
    candidate_chunk_id: str | None = Field(
        default=None, description="UUID of candidate violation chunk."
    )
    scenario_type: str | None = Field(
        default=None,
        description="Scenario alias string (e.g. 'POLICE_OVERRIDE_RED_LIGHT').",
    )
    context_conditions: ScopeOverrideContextConditions | dict[str, Any] | None = Field(
        default=None, description="Structured scenario context conditions."
    )


class SignCatalogLookupParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sign_code: str | None = Field(
        default=None,
        description="Exact or partial sign code (e.g. 'P.102', 'W.207', 'R.420').",
    )
    query_keyword: str | None = Field(
        default=None,
        description="Semantic keyword or phrase describing the sign.",
    )
    category: str | None = Field(
        default=None, description="Filter by sign technical classification."
    )
    limit: int = Field(
        default=5, ge=1, le=20, description="Maximum number of matches to return."
    )


class KnowledgeCacheQueryParams(BaseModel):
    model_config = ConfigDict(extra="allow")
    query_hash: str | None = Field(
        default=None, description="SHA-256 hash of query."
    )
    natural_query: str | None = Field(
        default=None, description="Verbatim natural language query."
    )
    query_vector: list[float] | None = Field(
        default=None, description="Dense embedding vector for cosine similarity search."
    )
    similarity_threshold: float = Field(
        default=0.92,
        ge=0.0,
        le=1.0,
        description="Cosine similarity cutoff threshold.",
    )


class KnowledgeCacheWriteParams(BaseModel):
    model_config = ConfigDict(extra="allow")
    query_hash: str | None = Field(
        default=None, description="SHA-256 hash of query."
    )
    natural_query: str | None = Field(
        default=None, description="Verbatim natural query."
    )
    plan: dict[str, Any] | None = Field(
        default=None, description="Decomposed plan executed."
    )
    intent_classification: dict[str, Any] | None = Field(
        default=None, description="Structured intent extracted."
    )
    generated_plan: dict[str, Any] | None = Field(
        default=None, description="Execution plan DAG."
    )
    retrieved_chunk_ids: list[str] | None = Field(
        default=None, description="Evidentiary chunk UUIDs."
    )
    traversed_edge_ids: list[str] | None = Field(
        default=None, description="Traversed edge UUIDs."
    )
    verified_citations: list[Any] | None = Field(
        default=None, description="Verified citations list."
    )
    synthesized_answer: str | None = Field(
        default=None, description="Synthesized legal response text."
    )
    answer: str | None = Field(default=None, description="Answer text alias.")
    citations: list[str] | None = Field(
        default=None, description="Citations alias."
    )
    verifier_proof: str | None = Field(
        default=None, description="Forensic audit token."
    )


# ==============================================================================
# LegalMCPServer Implementation
# ==============================================================================


class LegalMCPServer:
    """Production JSON-RPC 2.0 MCP Server for Vietnamese Traffic Law RAG."""

    def __init__(self, tools: LegalMCPTools | None = None) -> None:
        if tools is None:
            from rag_eval.legal.mcp.tools import LegalMCPTools

            self.tools = LegalMCPTools()
        else:
            self.tools = tools
        self._is_initialized = False

    def _error_response(
        self, req_id: Any, code: int, message: str, data: Any = None
    ) -> dict[str, Any]:
        resp: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": code, "message": message},
        }
        if data is not None:
            resp["error"]["data"] = data
        return resp

    def get_tool_manifests(self) -> list[dict[str, Any]]:
        """Returns JSON Schema Draft 2020-12 manifests for all 7 specialized tools."""
        return [
            {
                "name": "mcp_traffic_corpus_validate",
                "description": "Validates structural and relational integrity of ingested legal documents in PostgreSQL.",
                "inputSchema": CorpusValidateParams.model_json_schema(),
            },
            {
                "name": "mcp_traffic_hybrid_search",
                "description": "Executes hybrid dense vector + sparse Vietnamese lexical search with RRF fusion and structured filtering.",
                "inputSchema": HybridSearchParams.model_json_schema(),
            },
            {
                "name": "mcp_traffic_hierarchical_navigate",
                "description": "Navigates the statutory syntax tree (ltree) along parent chains, children, siblings, or full articles.",
                "inputSchema": HierarchicalNavigateParams.model_json_schema(),
            },
            {
                "name": "mcp_traffic_graph_traverse",
                "description": "Traverses the directed statutory cross-reference graph across Luật, Nghị định, and QCVN 41:2019.",
                "inputSchema": GraphTraverseParams.model_json_schema(),
            },
            {
                "name": "mcp_traffic_scope_override_detect",
                "description": "Evaluates statutory signal precedence hierarchies (Police > Light > Sign > Marking) and emergency exemptions.",
                "inputSchema": ScopeOverrideDetectParams.model_json_schema(),
            },
            {
                "name": "mcp_traffic_sign_catalog_lookup",
                "description": "Retrieves official specifications, shapes, meanings, placement rules, and penalty mappings from QCVN 41:2019.",
                "inputSchema": SignCatalogLookupParams.model_json_schema(),
            },
            {
                "name": "mcp_traffic_knowledge_cache_query",
                "description": "Probes runtime knowledge cache in PostgreSQL for verified query plans, citation subgraphs, and answers.",
                "inputSchema": KnowledgeCacheQueryParams.model_json_schema(),
            },
            {
                "name": "mcp_traffic_knowledge_cache_write",
                "description": "Persists verified reasoning plans, citation subgraphs, and synthesized answers to runtime cache.",
                "inputSchema": KnowledgeCacheWriteParams.model_json_schema(),
            },
        ]

    async def call_tool(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Convenience method for direct tool invocation via server interface."""
        req_payload = {
            "jsonrpc": "2.0",
            "id": "direct_call",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }
        res = await self.handle_request(req_payload)
        return res or {"jsonrpc": "2.0", "result": None}

    async def handle_request(
        self, request_payload: dict[str, Any] | object
    ) -> dict[str, Any] | None:
        """Processes an incoming JSON-RPC 2.0 request or notification payload."""
        if not isinstance(request_payload, dict) or request_payload.get("jsonrpc") != "2.0":
            req_id = request_payload.get("id") if isinstance(request_payload, dict) else None
            return self._error_response(req_id, RPC_INVALID_REQUEST, "Invalid JSON-RPC 2.0 request payload")

        req_id = request_payload.get("id")
        method = request_payload.get("method")
        params = request_payload.get("params", {})

        if not isinstance(method, str) or not method:
            return self._error_response(req_id, RPC_INVALID_REQUEST, "Missing or invalid 'method' field")

        if not isinstance(params, dict):
            return self._error_response(req_id, RPC_INVALID_PARAMS, "Parameters must be a JSON object")

        # ----------------------------------------------------------------------
        # 1. Standard MCP Lifecycle & Handshake Methods
        # ----------------------------------------------------------------------
        if method == "initialize":
            self._is_initialized = True
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {
                        "name": "vietnamese-traffic-law-mcp",
                        "version": "1.0.0",
                    },
                },
            }

        elif method == "notifications/initialized":
            self._is_initialized = True
            return None  # Notification: no response packet emitted

        elif method == "ping":
            return {"jsonrpc": "2.0", "id": req_id, "result": {}}

        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": self.get_tool_manifests()},
            }

        # ----------------------------------------------------------------------
        # 2. Tool Execution (`tools/call` and direct method invocations)
        # ----------------------------------------------------------------------
        target_tool = method
        tool_args = params

        if method == "tools/call":
            call_name = params.get("name")
            if not isinstance(call_name, str):
                return self._error_response(req_id, RPC_INVALID_PARAMS, "Missing 'name' in tools/call params")
            target_tool = call_name
            tool_args = params.get("arguments", {})
            if not isinstance(tool_args, dict):
                return self._error_response(req_id, RPC_INVALID_PARAMS, "'arguments' in tools/call must be an object")

        return await self._dispatch_tool(req_id, target_tool, tool_args)

    async def _dispatch_tool(
        self, req_id: Any, tool_name: str, args: dict[str, Any]
    ) -> dict[str, Any]:
        """Validates input arguments with Pydantic and executes tool business logic with timeout."""
        try:
            async with asyncio.timeout(5.0):
                if tool_name in ("mcp_traffic_corpus_validate", "corpus_validate"):
                    parsed_c = CorpusValidateParams(**args)
                    result = await self.tools.corpus_validate(
                        document_id=parsed_c.document_id,
                        check_orphaned_points=parsed_c.check_orphaned_points,
                        check_missing_embeddings=parsed_c.check_missing_embeddings,
                        check_broken_edges=parsed_c.check_broken_edges,
                        check_path_continuity=parsed_c.check_path_continuity,
                    )

                elif tool_name in ("mcp_traffic_hybrid_search", "hybrid_search", "search_legal_norms"):
                    parsed_h = HybridSearchParams(**args)
                    result = await self.tools.hybrid_search(
                        query=parsed_h.query,
                        query_vector=parsed_h.query_vector,
                        vehicle_types=parsed_h.vehicle_types,
                        actor_category=parsed_h.actor_category,
                        norm_roles=parsed_h.norm_roles,
                        fine_min_vnd=parsed_h.fine_min_vnd,
                        fine_max_vnd=parsed_h.fine_max_vnd,
                        document_codes=parsed_h.document_codes,
                        effective_as_of=parsed_h.effective_as_of,
                        limit=parsed_h.limit,
                    )

                elif tool_name in ("mcp_traffic_hierarchical_navigate", "hierarchical_navigate"):
                    parsed_n = HierarchicalNavigateParams(**args)
                    result = await self.tools.hierarchical_navigate(
                        target_path=parsed_n.target_path,
                        direction=parsed_n.direction,
                        include_verbatim=parsed_n.include_verbatim,
                    )

                elif tool_name in ("mcp_traffic_graph_traverse", "graph_traverse", "traverse_triad"):
                    parsed_g = GraphTraverseParams(**args)
                    result = await self.tools.graph_traverse(
                        start_chunk_id=parsed_g.start_chunk_id,
                        relation_types=parsed_g.relation_types,
                        direction=parsed_g.direction,
                        max_depth=parsed_g.max_depth,
                    )

                elif tool_name in ("mcp_traffic_scope_override_detect", "scope_override_detect", "resolve_precedence"):
                    parsed_s = ScopeOverrideDetectParams(**args)
                    ctx_dict = None
                    if parsed_s.context_conditions is not None:
                        if isinstance(parsed_s.context_conditions, BaseModel):
                            ctx_dict = parsed_s.context_conditions.model_dump()
                        elif isinstance(parsed_s.context_conditions, dict):
                            ctx_dict = parsed_s.context_conditions

                    result = await self.tools.scope_override_detect(
                        scenario_type=parsed_s.scenario_type or "POLICE_OVERRIDE_RED_LIGHT",
                        candidate_chunk_id=parsed_s.candidate_chunk_id,
                        context_conditions=ctx_dict,
                    )

                elif tool_name in ("mcp_traffic_sign_catalog_lookup", "sign_catalog_lookup", "lookup_sign"):
                    parsed_sig = SignCatalogLookupParams(**args)
                    result = await self.tools.sign_catalog_lookup(
                        sign_code=parsed_sig.sign_code or "",
                        query_keyword=parsed_sig.query_keyword,
                        category=parsed_sig.category,
                        limit=parsed_sig.limit,
                    )

                elif tool_name in ("mcp_traffic_knowledge_cache_query", "knowledge_cache_query"):
                    parsed_kq = KnowledgeCacheQueryParams(**args)
                    result = await self.tools.knowledge_cache_query(
                        query_hash=parsed_kq.query_hash,
                        natural_query=parsed_kq.natural_query,
                        query_vector=parsed_kq.query_vector,
                        similarity_threshold=parsed_kq.similarity_threshold,
                    )

                elif tool_name in ("mcp_traffic_knowledge_cache_write", "knowledge_cache_write"):
                    parsed_kw = KnowledgeCacheWriteParams(**args)
                    result = await self.tools.knowledge_cache_write(
                        query_hash=parsed_kw.query_hash,
                        natural_query=parsed_kw.natural_query,
                        plan=parsed_kw.plan,
                        answer=parsed_kw.answer or parsed_kw.synthesized_answer or "",
                        citations=parsed_kw.citations or [str(c) for c in (parsed_kw.verified_citations or [])],
                        intent_classification=parsed_kw.intent_classification,
                        generated_plan=parsed_kw.generated_plan,
                        retrieved_chunk_ids=parsed_kw.retrieved_chunk_ids,
                        traversed_edge_ids=parsed_kw.traversed_edge_ids,
                        verifier_proof=parsed_kw.verifier_proof,
                    )

                else:
                    return self._error_response(
                        req_id, RPC_METHOD_NOT_FOUND, f"Method '{tool_name}' not found"
                    )

            return {"jsonrpc": "2.0", "id": req_id, "result": result}

        except LegalDomainError as dom_err:
            logger.warning(
                "Domain error during tool execution '%s': %s (code %d)",
                tool_name,
                dom_err.message,
                dom_err.code,
            )
            return self._error_response(
                req_id,
                dom_err.code,
                dom_err.message,
                data=dom_err.data if dom_err.data else None,
            )
        except ValidationError as val_err:
            return self._error_response(
                req_id,
                RPC_INVALID_PARAMS,
                f"Invalid tool arguments: {val_err}",
                data={"errors": val_err.errors()},
            )
        except TimeoutError:
            return self._error_response(
                req_id,
                E_STATEMENT_TIMEOUT,
                "Query execution exceeded 5000ms statement timeout threshold",
            )
        except (RuntimeError, ValueError, TypeError, KeyError, OSError) as exc:
            logger.exception("Internal execution error on method %s", tool_name)
            return self._error_response(req_id, RPC_INTERNAL_ERROR, f"Internal execution error: {exc}")

    async def run_stdio(self) -> None:
        """Runs the MCP server over standard input/output (Stdio)."""
        logger.info("Starting Legal MCP JSON-RPC 2.0 server on Stdio...")
        loop = asyncio.get_running_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)

        while True:
            line = await reader.readline()
            if not line:
                break
            line_str = line.decode("utf-8").strip()
            if not line_str:
                continue

            try:
                payload = json.loads(line_str)
            except (json.JSONDecodeError, UnicodeDecodeError) as err:
                err_resp = self._error_response(None, RPC_PARSE_ERROR, f"Parse error: {err}")
                sys.stdout.write(json.dumps(err_resp) + "\n")
                sys.stdout.flush()
                continue

            response = await self.handle_request(payload)
            if response is not None:
                sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
                sys.stdout.flush()


async def run_mcp_server() -> None:
    """Entry point for standalone MCP server process."""
    server = LegalMCPServer()
    await server.run_stdio()
