"""Mock MCP JSON-RPC 2.0 Client & Server implementing the 7 specialized tools."""

from __future__ import annotations

import datetime

from tests.legal.mocks.mock_db import MockDatabasePool


class MockMCPServer:
    """Mock MCP JSON-RPC 2.0 Server handling all 7 specialized domain tools."""

    def __init__(self, db_pool: MockDatabasePool | None = None) -> None:
        self.db = db_pool or MockDatabasePool()

    async def call_tool(
        self, tool_name: str, arguments: dict[str, object]
    ) -> dict[str, object]:
        """Dispatch MCP tool execution with standardized error handling and schemas."""
        handler = getattr(self, f"handle_{tool_name}", None)
        if not handler:
            return {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32601,
                    "message": f"Method '{tool_name}' not found",
                },
            }
        try:
            result = await handler(arguments)
            return {"jsonrpc": "2.0", "result": result}
        except (
            RuntimeError,
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
            OSError,
        ) as err:
            return {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32000,
                    "message": f"Internal execution error: {err}",
                },
            }

    async def handle_mcp_traffic_corpus_validate(
        self, args: dict[str, object]
    ) -> dict[str, object]:
        doc_id = str(args.get("document_id", "doc_nd100"))
        has_chunks = len(self.db.chunks) > 0
        has_edges = len(self.db.graph_edges) > 0
        is_valid = has_chunks and has_edges
        anomalies: list[str] = []
        if not has_chunks:
            anomalies.append("No statutory chunks registered in corpus")
        if not has_edges:
            anomalies.append("No relational graph edges registered in corpus")

        return {
            "status": "success" if is_valid else "error",
            "document_id": doc_id,
            "doc_code": "100/2019/ND-CP",
            "is_valid": is_valid,
            "total_chunks_scanned": len(self.db.chunks),
            "total_edges_scanned": len(self.db.graph_edges),
            "summary": "Corpus validation successful" if is_valid else f"Corpus validation failed: {len(anomalies)} anomalies detected",
            "anomalies": anomalies,
            "validation_timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
        }


    async def handle_mcp_traffic_hybrid_search(
        self, args: dict[str, object]
    ) -> dict[str, object]:
        query_val = args.get("query", "")
        query = str(query_val) if query_val is not None else ""
        limit_val = args.get("limit", 10)
        limit = int(str(limit_val)) if limit_val is not None else 10

        doc_codes_val = args.get("document_codes")
        doc_codes: list[str] | None = (
            [str(d) for d in doc_codes_val] if isinstance(doc_codes_val, list) else None
        )

        results = await self.db.execute_hybrid_search(
            query, document_codes=doc_codes, limit=limit
        )
        return {
            "status": "success",
            "total_hits": len(results),
            "results": results,
        }

    async def handle_mcp_traffic_hierarchical_navigate(
        self, args: dict[str, object]
    ) -> dict[str, object]:
        target_path_val = args.get("target_path", "")
        target_path = str(target_path_val) if target_path_val is not None else ""
        direction_val = args.get("direction", "PARENT_CHAIN")
        direction = str(direction_val) if direction_val is not None else "PARENT_CHAIN"

        nodes: list[dict[str, object]] = []
        for chunk in self.db.chunks.values():
            if chunk.hierarchy_path.startswith(target_path) or target_path.startswith(
                chunk.hierarchy_path
            ):
                nodes.append(
                    {
                        "chunk_id": chunk.chunk_id,
                        "parent_id": None,
                        "path": chunk.hierarchy_path,
                        "depth": len(chunk.hierarchy_path.split(".")),
                        "chunk_level": "POINT" if chunk.point_letter else "ARTICLE",
                        "chunk_index": chunk.article_index,
                        "title": chunk.doc_title,
                        "lead_sentence": chunk.lead_sentence,
                        "raw_text": chunk.verbatim_text,
                        "contextualized_text": chunk.contextualized_text,
                        "norm_role": chunk.norm_role.value,
                    }
                )

        return {
            "status": "success",
            "target_path": target_path,
            "direction": direction,
            "total_nodes": len(nodes),
            "nodes": nodes,
        }

    async def handle_mcp_traffic_graph_traverse(
        self, args: dict[str, object]
    ) -> dict[str, object]:
        start_chunk_id_val = args.get("start_chunk_id", "")
        start_chunk_id = str(start_chunk_id_val) if start_chunk_id_val is not None else ""
        allowed_val = args.get("relation_types")
        allowed: list[str] | None = (
            [str(x) for x in allowed_val] if isinstance(allowed_val, list) else None
        )
        max_depth_val = args.get("max_depth", 2)
        max_depth = int(str(max_depth_val)) if max_depth_val is not None else 2

        paths = await self.db.execute_graph_traversal(
            start_chunk_id, allowed_edge_types=allowed, max_depth=max_depth
        )
        return {
            "status": "success",
            "start_chunk_id": start_chunk_id,
            "total_paths": len(paths),
            "traversal_paths": paths,
        }

    async def handle_mcp_traffic_sign_catalog_lookup(
        self, args: dict[str, object]
    ) -> dict[str, object]:
        sign_code_val = args.get("sign_code", "")
        sign_code = str(sign_code_val).upper().strip() if sign_code_val is not None else ""
        sign = self.db.signs.get(sign_code)
        if not sign:
            # Fuzzy match
            for s in self.db.signs.values():
                if sign_code.replace(".", "") in s.sign_code.replace(".", ""):
                    sign = s
                    break
        if not sign:
            return {"status": "not_found", "sign_code": sign_code}

        return {
            "status": "success",
            "sign_code": sign.sign_code,
            "sign_name": sign.sign_name,
            "category": sign.category,
            "shape": sign.shape,
            "primary_color": sign.primary_color,
            "meaning": sign.meaning,
            "placement_rules": sign.placement_rules,
            "penalty_references": sign.penalty_references,
        }

    async def handle_mcp_traffic_knowledge_cache_query(
        self, args: dict[str, object]
    ) -> dict[str, object]:
        query_hash_val = args.get("query_hash", "")
        query_hash = str(query_hash_val) if query_hash_val is not None else ""
        cached = self.db.runtime_cache.get(query_hash)
        if cached:
            return {"status": "hit", "cache_entry": cached}
        return {"status": "miss"}

    async def handle_mcp_traffic_knowledge_cache_write(
        self, args: dict[str, object]
    ) -> dict[str, object]:
        query_hash_val = args.get("query_hash", "")
        query_hash = str(query_hash_val) if query_hash_val is not None else ""
        self.db.runtime_cache[query_hash] = args
        return {"status": "written", "query_hash": query_hash}
