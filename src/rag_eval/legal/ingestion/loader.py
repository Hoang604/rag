"""High-performance idempotent PostgreSQL batch loader for legal ingestion pipeline.

Persists parsed documents, AST hierarchy nodes, CFQC chunks, graph edges, and sign specifications
into PostgreSQL using high-throughput batch operations (conn.executemany) and strict foreign key integrity.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

import asyncpg

from rag_eval.legal.ingestion.parser import ASTNode
from rag_eval.legal.schemas import CanonicalFullyQualifiedChunk

logger = logging.getLogger(__name__)


def _resolve_node_id(path: str | None, node_id_map: dict[str, str]) -> str:
    """Strictly resolves AST node UUID from exact or normalized ltree paths.

    Enforces strict hierarchical path matching from root down to leaf, eliminating
    ambiguous suffix collisions across disparate chapters or structural sections.

    Raises:
        ValueError: If path is empty or cannot be resolved in node_id_map.
    """
    if not path:
        raise ValueError("Cannot resolve node UUID for empty hierarchy path.")
    if path in node_id_map:
        return node_id_map[path]

    # Path segments e.g. ["doc_nd100_2019", "a5", "c1", "p_a"]
    path_segments = path.split(".")
    doc_prefix = path_segments[0]

    # Fallback to document root node if path is document level
    if len(path_segments) == 1 and doc_prefix in node_id_map:
        return node_id_map[doc_prefix]

    # Match hierarchically from root down:
    # Candidate key must start with doc_prefix and contain the path's sub-segments
    # in strict ascending order from root down to leaf.
    matching_candidates: list[tuple[str, str]] = []
    for k, v in node_id_map.items():
        k_segments = k.split(".")
        if k_segments[0] != doc_prefix:
            continue
        # The trailing segment (leaf) MUST match the target leaf segment
        if k_segments[-1] != path_segments[-1]:
            continue

        # Check that all path_segments appear in k_segments in preserved root-to-leaf order
        k_idx = 0
        matched_all = True
        for seg in path_segments:
            while k_idx < len(k_segments) and k_segments[k_idx] != seg:
                k_idx += 1
            if k_idx >= len(k_segments):
                matched_all = False
                break
            k_idx += 1

        if matched_all:
            matching_candidates.append((k, v))

    if len(matching_candidates) == 1:
        return matching_candidates[0][1]
    elif len(matching_candidates) > 1:
        # Sort by candidate path segment count ascending (most direct/specific path match)
        matching_candidates.sort(key=lambda item: len(item[0].split(".")))
        return matching_candidates[0][1]

    raise ValueError(
        f"Strict AST Foreign Key Error: Path '{path}' not found in node_id_map "
        f"(Available paths count: {len(node_id_map)})"
    )


class PostgresBulkLoader:
    """High-performance idempotent database batch loader for legal documents and knowledge graphs."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def load_document(
        self,
        doc_code: str,
        title: str,
        doc_type: str = "NGHI_DINH",
        issuing_authority: str = "Chính phủ",
        signer: str | None = None,
        promulgation_date: str = "2020-01-01",
        effective_date: str = "2020-01-15",
        expiration_date: str | None = None,
        status: str = "EFFECTIVE",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Upserts a legal document into legal_documents, returning its UUID."""
        meta_json = json.dumps(metadata or {})
        query = """
        INSERT INTO legal_documents (
            doc_code, title, doc_type, issuing_authority, signer,
            promulgation_date, effective_date, expiration_date, status, document_metadata
        ) VALUES (
            $1, $2, $3::legal_document_type, $4, $5,
            $6::date, $7::date, $8::date, $9::legal_document_status, $10::jsonb
        )
        ON CONFLICT (doc_code) DO UPDATE SET
            title = EXCLUDED.title,
            doc_type = EXCLUDED.doc_type,
            issuing_authority = EXCLUDED.issuing_authority,
            signer = EXCLUDED.signer,
            effective_date = EXCLUDED.effective_date,
            expiration_date = EXCLUDED.expiration_date,
            status = EXCLUDED.status,
            document_metadata = EXCLUDED.document_metadata,
            updated_at = CURRENT_TIMESTAMP
        RETURNING id;
        """
        async with self.pool.acquire() as conn:
            doc_id = await conn.fetchval(
                query,
                doc_code,
                title,
                doc_type,
                issuing_authority,
                signer,
                promulgation_date,
                effective_date,
                expiration_date,
                status,
                meta_json,
            )
            return str(doc_id)

    async def load_hierarchy_nodes(
        self,
        nodes: list[ASTNode],
        document_id: str,
    ) -> dict[str, str]:
        """Upserts hierarchical AST nodes into legal_hierarchy_nodes via batch executemany.

        Generates deterministic UUIDs and groups inserts by tree depth to satisfy foreign keys.
        """
        path_to_id: dict[str, str] = {}
        if not nodes:
            return path_to_id

        # 1. Pre-calculate deterministic UUIDs for all nodes
        for node in nodes:
            deterministic_uuid = str(
                uuid.uuid5(uuid.NAMESPACE_DNS, f"{document_id}:{node.full_path}")
            )
            path_to_id[node.full_path] = deterministic_uuid

        # 2. Group nodes by depth to enforce parent FK presence
        depth_buckets: dict[int, list[ASTNode]] = {}
        for node in nodes:
            depth_buckets.setdefault(node.depth, []).append(node)

        query = """
        INSERT INTO legal_hierarchy_nodes (
            id, document_id, parent_id, node_type, node_index, title,
            path, depth, display_order, lead_sentence, raw_text, full_path_title, metadata
        ) VALUES (
            $1::uuid, $2::uuid, $3::uuid, $4::legal_node_type, $5, $6,
            $7::ltree, $8, $9, $10, $11, $12, $13::jsonb
        )
        ON CONFLICT (path) DO UPDATE SET
            title = EXCLUDED.title,
            lead_sentence = EXCLUDED.lead_sentence,
            raw_text = EXCLUDED.raw_text,
            full_path_title = EXCLUDED.full_path_title,
            metadata = EXCLUDED.metadata,
            updated_at = CURRENT_TIMESTAMP;
        """

        valid_node_types = {
            "DOCUMENT",
            "PART",
            "CHAPTER",
            "SECTION",
            "SUB_SECTION",
            "ARTICLE",
            "CLAUSE",
            "POINT",
            "APPENDIX",
            "TABLE",
            "CLAUSE_PARAGRAPH",
        }

        async with self.pool.acquire() as conn, conn.transaction():
            for depth in sorted(depth_buckets.keys()):
                bucket = depth_buckets[depth]
                records: list[tuple[Any, ...]] = []
                for node in bucket:
                    node_uuid = path_to_id[node.full_path]
                    parent_uuid = (
                        path_to_id.get(node.parent_path) if node.parent_path else None
                    )
                    meta_json = json.dumps(node.metadata)
                    node_type_val = (
                        node.level if node.level in valid_node_types else "ARTICLE"
                    )

                    records.append(
                        (
                            node_uuid,
                            document_id,
                            parent_uuid,
                            node_type_val,
                            node.index_label,
                            node.title,
                            node.full_path,
                            node.depth,
                            node.display_order,
                            node.lead_sentence,
                            node.raw_text,
                            node.title,
                            meta_json,
                        )
                    )

                if records:
                    await conn.executemany(query, records)

        return path_to_id

    async def load_chunks(
        self,
        chunks: list[CanonicalFullyQualifiedChunk],
        document_id: str,
        node_id_map: dict[str, str],
    ) -> dict[str, str]:
        """Upserts CFQC chunks into legal_chunks table using high-performance batch executemany."""
        path_to_chunk_id: dict[str, str] = {}
        if not chunks:
            return path_to_chunk_id

        query = """
        INSERT INTO legal_chunks (
            id, node_id, document_id, chunk_type, chunk_index, path,
            lead_sentence, verbatim_text, contextualized_text,
            norm_role, primary_actor, vehicle_types, violation_categories,
            min_fine_vnd, max_fine_vnd, additional_sanctions, remedial_measures,
            is_exception, exception_type, effective_date, expiration_date, is_active,
            metadata
        ) VALUES (
            $1::uuid, $2::uuid, $3::uuid, $4, $5, $6::ltree,
            $7, $8, $9,
            $10::legal_norm_role, $11::actor_category, $12::jsonb, $13::jsonb,
            $14, $15, $16::jsonb, $17::jsonb,
            $18, $19, $20::date, $21::date, $22,
            $23::jsonb
        )
        ON CONFLICT (path) DO UPDATE SET
            lead_sentence = EXCLUDED.lead_sentence,
            verbatim_text = EXCLUDED.verbatim_text,
            contextualized_text = EXCLUDED.contextualized_text,
            norm_role = EXCLUDED.norm_role,
            primary_actor = EXCLUDED.primary_actor,
            vehicle_types = EXCLUDED.vehicle_types,
            violation_categories = EXCLUDED.violation_categories,
            min_fine_vnd = EXCLUDED.min_fine_vnd,
            max_fine_vnd = EXCLUDED.max_fine_vnd,
            additional_sanctions = EXCLUDED.additional_sanctions,
            is_exception = EXCLUDED.is_exception,
            is_active = EXCLUDED.is_active,
            updated_at = CURRENT_TIMESTAMP;
        """

        records: list[tuple[Any, ...]] = []
        for chunk in chunks:
            # Strict node UUID resolution - eliminates random uuid.uuid4() fallback
            node_uuid = _resolve_node_id(chunk.hierarchy_path, node_id_map)

            chunk_uuid = (
                chunk.chunk_id
                if getattr(chunk, "chunk_id", None) and len(chunk.chunk_id) == 36
                else str(
                    uuid.uuid5(
                        uuid.NAMESPACE_DNS, f"{document_id}:{chunk.hierarchy_path}"
                    )
                )
            )
            path_to_chunk_id[chunk.hierarchy_path] = chunk_uuid

            # Use canonical 8-member NormRole enum directly
            norm_role_val = chunk.norm_role.value

            chunk_meta: dict[str, Any] = {
                "doc_code": chunk.document_code,
                "norm_roles": [norm_role_val],
            }
            if (
                chunk.additional_sanctions.license_suspension_months_min is not None
                or chunk.additional_sanctions.license_suspension_months_max is not None
                or chunk.additional_sanctions.vehicle_impoundment_days is not None
            ) and "SANCTION_SUPPLEMENTARY" not in chunk_meta["norm_roles"]:
                chunk_meta["norm_roles"].append("SANCTION_SUPPLEMENTARY")
            if (
                chunk.additional_sanctions.demerit_points is not None
                and "SANCTION_POINT_DEDUCTION" not in chunk_meta["norm_roles"]
            ):
                chunk_meta["norm_roles"].append("SANCTION_POINT_DEDUCTION")

            records.append(
                (
                    chunk_uuid,
                    node_uuid,
                    document_id,
                    "LEGAL_RULE",
                    f"Điều {chunk.article_number} Khoản {chunk.clause_number or ''} {chunk.point_letter or ''}".strip(),
                    chunk.hierarchy_path,
                    chunk.synthesized_prefix,
                    chunk.verbatim_text,
                    chunk.contextualized_text,
                    norm_role_val,
                    chunk.primary_actor.value,
                    json.dumps([v.value for v in chunk.vehicle_types]),
                    json.dumps([v.value for v in chunk.violation_categories]),
                    chunk.fine_bounds.min_fine_vnd,
                    chunk.fine_bounds.max_fine_vnd,
                    json.dumps(
                        chunk.additional_sanctions.model_dump(exclude_none=True)
                    ),
                    json.dumps([]),
                    chunk.exceptions_and_overrides.has_exception,
                    chunk.exceptions_and_overrides.exception_type,
                    chunk.effective_date or "2020-01-15",
                    chunk.expiry_date,
                    chunk.is_active,
                    json.dumps(chunk_meta),
                )
            )

        async with self.pool.acquire() as conn, conn.transaction():
            if records:
                await conn.executemany(query, records)

        return path_to_chunk_id

    async def load_graph_edges(
        self,
        edges: list[dict[str, Any]],
        chunk_id_map: dict[str, str],
        node_id_map: dict[str, str],
    ) -> int:
        """Upserts directed graph edges into legal_graph_edges using batch executemany."""
        if not edges:
            return 0

        query = """
        INSERT INTO legal_graph_edges (
            source_chunk_id, target_chunk_id, source_node_id, target_node_id,
            source_path, target_path, target_external_ref, relation_type,
            description, citation_text, confidence_score, condition_expression
        ) VALUES (
            $1::uuid, $2::uuid, $3::uuid, $4::uuid,
            $5::ltree, $6::ltree, $7, $8::graph_relation_type,
            $9, $10, $11, $12
        )
        ON CONFLICT (source_chunk_id, target_chunk_id, relation_type) DO UPDATE SET
            confidence_score = EXCLUDED.confidence_score,
            description = EXCLUDED.description,
            condition_expression = EXCLUDED.condition_expression;
        """

        records: list[tuple[Any, ...]] = []
        for edge in edges:
            source_path = edge["source_path"]
            target_path = edge.get("target_path")

            src_chunk_id = chunk_id_map.get(source_path)
            tgt_chunk_id = chunk_id_map.get(target_path) if target_path else None

            try:
                src_node_id = _resolve_node_id(source_path, node_id_map)
            except ValueError as exc:
                logger.warning("Skipping edge due to unresolvable source node: %s", exc)
                continue

            tgt_node_id = None
            if target_path:
                try:
                    tgt_node_id = _resolve_node_id(target_path, node_id_map)
                except ValueError:
                    # External document reference or unmapped target node -> NULL in DB
                    tgt_node_id = None

            if not src_chunk_id or not src_node_id:
                continue

            records.append(
                (
                    src_chunk_id,
                    tgt_chunk_id,
                    src_node_id,
                    tgt_node_id,
                    source_path,
                    target_path,
                    edge.get("target_external_ref"),
                    edge["relation_type"],
                    edge.get("description"),
                    edge.get("citation_text"),
                    float(edge.get("confidence_score", 1.0)),
                    edge.get("condition_expression"),
                )
            )

        if not records:
            return 0

        async with self.pool.acquire() as conn, conn.transaction():
            await conn.executemany(query, records)

        return len(records)
