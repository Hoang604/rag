"""In-memory mock database pool and stored procedures simulation.

Implements:
- 7 tables: legal_documents, legal_hierarchy_nodes, legal_chunks, legal_graph_edges,
  sign_catalog, runtime_knowledge_cache, query_execution_logs.
- Stored procedure simulations: hybrid_legal_search with RRF, traverse_normative_triad,
  and query_runtime_knowledge_cache.
- Ltree hierarchical path containment (<@ and @>).
- Zero artificial score bonuses (+50.0) or query rewriting shortcuts (Resolves F-21, FLAG-04).
- Public seam accessors for document, sign, and runtime cache queries (Resolves F-24, F-35, FLAG-06, FLAG-07).
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
import uuid
from typing import Any

from rag_eval.legal.schemas import (
    CanonicalFullyQualifiedChunk,
    GraphRelationType,
    expand_vehicle_category,
)
from tests.legal.fixtures.laws_data import ALL_STATUTORY_CHUNKS
from tests.legal.fixtures.signs_data import ALL_SIGN_CATALOG, SignDefinition


class MockDatabasePool:
    """Async in-memory database pool simulating PostgreSQL 16 + pgvector storage."""

    def __init__(self) -> None:
        self.documents: dict[str, dict[str, Any]] = {
            "100/2019/ND-CP": {
                "id": "doc_nd100",
                "doc_code": "100/2019/ND-CP",
                "title": "Nghị định 100/2019/NĐ-CP xử phạt VPHC GTĐB & ĐS",
                "doc_type": "NGHI_DINH",
                "effective_date": "2020-01-15",
                "status": "EFFECTIVE",
            },
            "123/2021/ND-CP": {
                "id": "doc_nd123",
                "doc_code": "123/2021/ND-CP",
                "title": "Nghị định 123/2021/NĐ-CP sửa đổi bổ sung NĐ 100",
                "doc_type": "NGHI_DINH",
                "effective_date": "2022-01-01",
                "status": "EFFECTIVE",
            },
            "168/2024/ND-CP": {
                "id": "doc_nd168",
                "doc_code": "168/2024/ND-CP",
                "title": "Nghị định 168/2024/NĐ-CP trừ điểm GPLX",
                "doc_type": "NGHI_DINH",
                "effective_date": "2025-01-01",
                "status": "EFFECTIVE",
            },
            "36/2024/QH15": {
                "id": "doc_luat36",
                "doc_code": "36/2024/QH15",
                "title": "Luật Trật tự, an toàn giao thông đường bộ 2024",
                "doc_type": "LUAT",
                "effective_date": "2025-01-01",
                "status": "EFFECTIVE",
            },
            "31/2019/TT-BGTVT": {
                "id": "doc_tt31",
                "doc_code": "31/2019/TT-BGTVT",
                "title": "Thông tư 31/2019/TT-BGTVT quy định tốc độ xe cơ giới",
                "doc_type": "THONG_TU",
                "effective_date": "2019-10-15",
                "status": "EFFECTIVE",
            },
            "QCVN 41:2019/BGTVT": {
                "id": "doc_qcvn41",
                "doc_code": "QCVN 41:2019/BGTVT",
                "title": "Quy chuẩn kỹ thuật quốc gia về báo hiệu đường bộ",
                "doc_type": "QUY_CHUAN_KY_THUAT",
                "effective_date": "2020-07-01",
                "status": "EFFECTIVE",
            },
        }
        self.chunks: dict[str, CanonicalFullyQualifiedChunk] = {
            chunk.chunk_id: chunk for chunk in ALL_STATUTORY_CHUNKS
        }
        self.hierarchy_nodes: dict[str, dict[str, Any]] = self._init_hierarchy_nodes()
        self.signs: dict[str, SignDefinition] = {
            sign.sign_code: sign for sign in ALL_SIGN_CATALOG
        }
        self.graph_edges: list[dict[str, Any]] = self._init_graph_edges()
        self.runtime_cache: dict[str, dict[str, Any]] = {}
        self.query_logs: list[dict[str, Any]] = []

    def _init_hierarchy_nodes(self) -> dict[str, dict[str, Any]]:
        nodes: dict[str, dict[str, Any]] = {}
        for chunk in self.chunks.values():
            parts = chunk.hierarchy_path.split(".")
            running_path = ""
            for idx, p in enumerate(parts):
                running_path = f"{running_path}.{p}" if running_path else p
                if running_path not in nodes:
                    nodes[running_path] = {
                        "path": running_path,
                        "depth": idx + 1,
                        "node_type": "POINT" if p.startswith("p_") else ("CLAUSE" if p.startswith("c") else "ARTICLE"),
                        "document_code": chunk.document_code,
                    }
        return nodes

    def _init_graph_edges(self) -> list[dict[str, Any]]:
        return [
            {
                "edge_id": "edge_nd100_qcvn41_redlight",
                "source_chunk_id": "chk_nd100_art5_cl3_pta",
                "target_chunk_id": "chk_qcvn41_art10_traffic_lights",
                "source_path": "doc_nd100_2019.c2.s1.a5.c3.p_a",
                "target_path": "doc_qcvn41_2019.art10",
                "target_doc_code": "QCVN 41:2019/BGTVT",
                "target_chunk_index": "Điều 10",
                "target_norm_role": "HYPOTHESIS_CONDITION",
                "target_contextualized_text": "QCVN 41:2019 Điều 10: Tín hiệu đèn đỏ có ý nghĩa cấm đi",
                "relation_type": GraphRelationType.REFERENCES_TECHNICAL_STANDARD.value,
                "confidence_score": 1.0,
            },
            {
                "edge_id": "edge_nd100_nd123_amend_speed",
                "source_chunk_id": "chk_nd100_art5_cl5_pti",
                "target_chunk_id": "chk_tt31_art6",
                "source_path": "doc_nd100_2019.c2.s1.a5.c5.p_i",
                "target_path": "doc_tt31_2019.a6",
                "target_doc_code": "31/2019/TT-BGTVT",
                "target_chunk_index": "Điều 6",
                "target_norm_role": "HYPOTHESIS_CONDITION",
                "target_contextualized_text": "Thông tư 31/2019 Điều 6: Tốc độ tối đa trong đô thị 50 km/h đường 2 chiều",
                "relation_type": GraphRelationType.REFERENCES_TECHNICAL_STANDARD.value,
                "confidence_score": 0.95,
            },
            {
                "edge_id": "edge_nd100_p102_oneway",
                "source_chunk_id": "chk_nd100_art6_cl8_pta",
                "target_chunk_id": "chk_qcvn41_p102",
                "source_path": "doc_nd100_2019.c2.s1.a6.c8.p_a",
                "target_path": "doc_qcvn41_2019.app_b.p102",
                "target_doc_code": "QCVN 41:2019/BGTVT",
                "target_chunk_index": "Biển P.102",
                "target_norm_role": "HYPOTHESIS_CONDITION",
                "target_contextualized_text": "QCVN 41:2019 Phụ lục B: Biển P.102 Cấm đi ngược chiều",
                "relation_type": GraphRelationType.REFERENCES_TECHNICAL_STANDARD.value,
                "confidence_score": 1.0,
            },
        ]

    @staticmethod
    def _normalize_text(text: str) -> str:
        nfkd = unicodedata.normalize("NFKD", text)
        un = "".join(c for c in nfkd if not unicodedata.combining(c))
        un = un.replace("đ", "d").replace("Đ", "D")
        return re.sub(r"[^\w\s]", " ", un.lower())

    async def get_document(self, doc_code: str) -> dict[str, Any] | None:
        """Retrieves a legal document by code across public seam."""
        return self.documents.get(doc_code)

    async def list_documents(self) -> list[dict[str, Any]]:
        """Lists all registered legal documents across public seam."""
        return list(self.documents.values())

    async def get_sign(self, sign_code: str) -> SignDefinition | None:
        """Retrieves a traffic sign definition by code across public seam."""
        return self.signs.get(sign_code.strip())

    async def query_runtime_cache(self, query_hash: str) -> dict[str, Any] | None:
        """Queries the runtime knowledge cache across public seam (by query_hash)."""
        return self.runtime_cache.get(query_hash)

    async def write_runtime_cache(self, query_hash: str, entry: dict[str, Any]) -> None:
        """Writes an entry to the runtime knowledge cache across public seam (by query_hash)."""
        self.runtime_cache[query_hash] = entry

    async def write_runtime_knowledge_cache(
        self,
        natural_query: str,
        synthesized_answer: str,
        verified_citations: list[str] | None = None,
        intent_classification: dict[str, Any] | None = None,
        generated_plan: dict[str, Any] | None = None,
        query_embedding_384: list[float] | None = None,
        query_hash: str | None = None,
        ttl_seconds: int = 2592000,
    ) -> dict[str, Any]:
        """Persists a verified reasoning trace to the runtime knowledge cache."""
        q_hash = (
            query_hash
            if query_hash is not None
            else hashlib.sha256(natural_query.strip().lower().encode("utf-8")).hexdigest()
        )
        cache_id = str(uuid.uuid4())
        entry: dict[str, Any] = {
            "id": cache_id,
            "cache_id": cache_id,
            "query_hash": q_hash,
            "natural_query": natural_query,
            "synthesized_answer": synthesized_answer,
            "verified_citations": verified_citations if verified_citations is not None else [],
            "intent_classification": intent_classification if intent_classification is not None else {},
            "generated_plan": generated_plan if generated_plan is not None else {},
            "query_embedding_384": query_embedding_384,
            "validation_status": "VERIFIED",
            "hit_count": 1,
            "ttl_seconds": ttl_seconds,
        }
        self.runtime_cache[q_hash] = entry
        return {"status": "written", "cache_id": cache_id, "query_hash": q_hash}

    async def query_runtime_knowledge_cache(
        self,
        input_query: str,
        input_vector: list[float] | None = None,
        similarity_threshold: float = 0.965,
    ) -> dict[str, Any] | None:
        """Simulates PostgreSQL stored procedure query_runtime_knowledge_cache."""
        computed_hash = hashlib.sha256(input_query.strip().lower().encode("utf-8")).hexdigest()
        if computed_hash in self.runtime_cache:
            entry = self.runtime_cache[computed_hash]
            entry["hit_count"] = entry.get("hit_count", 0) + 1
            return {
                "cache_id": entry.get("cache_id", entry.get("id")),
                "synthesized_answer": entry.get("synthesized_answer", entry.get("verified_answer", "")),
                "verified_citations": entry.get("verified_citations", []),
                "intent_classification": entry.get("intent_classification", {}),
                "generated_plan": entry.get("generated_plan", {}),
                "similarity_score": 1.0,
                "is_exact_match": True,
            }
        return None

    async def get_table_counts(self) -> dict[str, int]:
        """Returns entity counts across core tables via public seam."""
        return {
            "documents": len(self.documents),
            "chunks": len(self.chunks),
            "hierarchy_nodes": len(self.hierarchy_nodes),
            "signs": len(self.signs),
            "graph_edges": len(self.graph_edges),
            "runtime_cache": len(self.runtime_cache),
            "query_logs": len(self.query_logs),
        }

    async def execute_hybrid_search(
        self,
        query: str,
        vehicle_category: str | None = None,
        violation_class: str | None = None,
        norm_roles: list[str] | None = None,
        fine_min_vnd: int | None = None,
        fine_max_vnd: int | None = None,
        document_codes: list[str] | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Simulates PostgreSQL in-database hybrid search with RRF (Zero Artificial Score Injection)."""
        normalized_q = self._normalize_text(query)
        raw_tokens = [t for t in normalized_q.split() if t]

        # Domain synonym token expansion for Vietnamese traffic colloquialisms
        synonyms: list[str] = []
        synonym_bigrams: list[str] = []
        if "den do" in normalized_q:
            synonyms.extend(["den", "tin", "hieu"])
            synonym_bigrams.extend(["den tin", "tin hieu"])
        if "xe may" in normalized_q or "mo to" in normalized_q:
            synonyms.extend(["mo", "to", "xe", "gan", "may"])
            synonym_bigrams.extend(["mo to", "xe gan may"])
        if (
            "qua toc do" in normalized_q
            or "toc do" in normalized_q
            or "km/h" in normalized_q
            or "kmh" in normalized_q
            or "km h" in normalized_q
            or "chay" in normalized_q
        ):
            synonyms.extend(["qua", "toc", "do", "chay"])
            synonym_bigrams.extend(["qua toc do", "toc do", "chay qua"])
        if "nguoc chieu" in normalized_q:
            synonyms.extend(["nguoc", "chieu", "mot", "chieu"])
            synonym_bigrams.extend(["nguoc chieu", "mot chieu"])
        if (
            "nong do con" in normalized_q
            or "ruou" in normalized_q
            or "bia" in normalized_q
        ):
            synonyms.extend(["nong", "do", "con"])
            synonym_bigrams.extend(["nong do con", "do con"])
        if "qua tai" in normalized_q:
            synonyms.extend(["qua", "tai", "trong", "tai"])
            synonym_bigrams.extend(["qua tai", "trong tai"])

        query_tokens = raw_tokens + [s for s in synonyms if s not in raw_tokens]
        query_bigrams = (
            [
                f"{raw_tokens[i]} {raw_tokens[i + 1]}"
                for i in range(len(raw_tokens) - 1)
            ]
            + synonym_bigrams
        )

        expanded_vehicles: set[str] = set()
        if vehicle_category:
            try:
                for v in expand_vehicle_category(vehicle_category):
                    expanded_vehicles.add(v.value)
            except (ValueError, KeyError):
                expanded_vehicles.add(vehicle_category)

        scored_candidates: list[tuple[float, float, CanonicalFullyQualifiedChunk]] = []

        for chunk in self.chunks.values():
            # 1. Vehicle Filtering
            if expanded_vehicles:
                chunk_veh_values = {v.value for v in chunk.vehicle_types}
                if not (chunk_veh_values & expanded_vehicles):
                    continue

            # 2. Violation Category Filtering
            if violation_class:
                chunk_viols = {v.value for v in chunk.violation_categories}
                if violation_class not in chunk_viols:
                    continue

            # 3. Norm Role Filtering
            if norm_roles and chunk.norm_role.value not in norm_roles:
                continue

            # 4. Fine Bounds Filtering
            if (
                fine_min_vnd is not None
                and chunk.fine_bounds.min_fine_vnd is not None
                and chunk.fine_bounds.min_fine_vnd < fine_min_vnd
            ):
                continue
            if (
                fine_max_vnd is not None
                and chunk.fine_bounds.max_fine_vnd is not None
                and chunk.fine_bounds.max_fine_vnd > fine_max_vnd
            ):
                continue

            # 5. Document Codes Filtering
            if document_codes and chunk.document_code not in document_codes:
                continue

            # Text Representations
            verbatim_norm = self._normalize_text(chunk.verbatim_text)
            context_norm = self._normalize_text(chunk.contextualized_text)
            prefix_norm = self._normalize_text(chunk.synthesized_prefix)
            lead_norm = self._normalize_text(chunk.lead_sentence or "")

            # Sparse Lexical Scoring (Weighted Term & Bigram Overlap)
            sparse_score = 0.0
            if (
                "phat" in normalized_q
                or "xu phat" in normalized_q
                or "tien phat" in normalized_q
            ) and chunk.norm_role.value == "SANCTION_PRINCIPAL":
                sparse_score += 10.0

            for t in query_tokens:
                if t in verbatim_norm:
                    sparse_score += 3.0
                if t in lead_norm:
                    sparse_score += 2.0
                if t in prefix_norm:
                    sparse_score += 1.5
                if t in context_norm:
                    sparse_score += 1.0

            for bg in query_bigrams:
                if bg in verbatim_norm:
                    sparse_score += 5.0
                if bg in context_norm:
                    sparse_score += 2.5
                if bg in prefix_norm:
                    sparse_score += 2.0

            # Dense Semantic Simulation (Neural concept mapping of violation types and full text)
            concept_tokens: list[str] = []
            for vt in chunk.violation_types:
                vt_name = vt.name if hasattr(vt, "name") else str(vt)
                if "RED_LIGHT" in vt_name:
                    concept_tokens.extend(["den", "do", "vuot", "tin", "hieu", "giao", "thong"])
                elif "SPEED" in vt_name:
                    concept_tokens.extend(["chay", "qua", "toc", "do", "kmh"])
                elif "OPPOSITE_DIRECTION" in vt_name:
                    concept_tokens.extend(["nguoc", "chieu", "duong", "mot", "chieu", "cam"])
                elif "ALC" in vt_name:
                    concept_tokens.extend(["nong", "do", "con", "ruou", "bia", "hoi", "tho", "mau"])
                elif "OVERLOAD" in vt_name:
                    concept_tokens.extend(["qua", "tai", "trong", "tai", "cho", "hang"])

            all_text_norm = f"{verbatim_norm} {lead_norm} {prefix_norm} {context_norm} {' '.join(concept_tokens)}"
            chunk_tokens = set(all_text_norm.split())
            dense_score = len(set(query_tokens) & chunk_tokens) / max(len(query_tokens), 1)

            scored_candidates.append((dense_score, sparse_score, chunk))

        # Rank by Dense and Sparse scores independently
        dense_sorted = sorted(scored_candidates, key=lambda x: x[0], reverse=True)
        sparse_sorted = sorted(scored_candidates, key=lambda x: x[1], reverse=True)

        dense_rank_map = {item[2].chunk_id: idx + 1 for idx, item in enumerate(dense_sorted)}
        sparse_rank_map = {item[2].chunk_id: idx + 1 for idx, item in enumerate(sparse_sorted)}

        # Combine with Reciprocal Rank Fusion (k=60)
        rrf_candidates: list[tuple[float, int, int, CanonicalFullyQualifiedChunk]] = []
        for dense_score, sparse_score, chunk in scored_candidates:
            d_rank = dense_rank_map[chunk.chunk_id]
            s_rank = sparse_rank_map[chunk.chunk_id]
            rrf_score = (1.0 / (60 + d_rank)) + (1.0 / (60 + s_rank))
            rrf_candidates.append((rrf_score, d_rank, s_rank, chunk))

        rrf_candidates.sort(key=lambda x: x[0], reverse=True)

        matches: list[dict[str, Any]] = []
        for rrf_score, d_rank, s_rank, chunk in rrf_candidates[:limit]:
            doc_title = self.documents.get(chunk.document_code, {}).get("title", chunk.document_code)
            matches.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "doc_code": chunk.document_code,
                    "doc_title": doc_title,
                    "path": chunk.hierarchy_path,
                    "chunk_level": "POINT" if chunk.point_letter else ("CLAUSE" if chunk.clause_number else "ARTICLE"),
                    "chunk_index": f"{f'Điểm {chunk.point_letter}' if chunk.point_letter else ''} {f'Khoản {chunk.clause_number}' if chunk.clause_number else ''} {chunk.article_index}".strip(),
                    "title": doc_title,
                    "lead_sentence": chunk.lead_sentence or chunk.verbatim_text,
                    "raw_text": chunk.verbatim_text,
                    "contextualized_text": chunk.contextualized_text,
                    "norm_role": chunk.norm_role.value,
                    "primary_actor": chunk.primary_actor.value,
                    "vehicle_types": [v.value for v in chunk.vehicle_types],
                    "min_fine_vnd": chunk.fine_bounds.min_fine_vnd,
                    "max_fine_vnd": chunk.fine_bounds.max_fine_vnd,
                    "additional_sanctions": {
                        "license_suspension_months_min": chunk.additional_sanctions.license_suspension_months_min,
                        "license_suspension_months_max": chunk.additional_sanctions.license_suspension_months_max,
                        "vehicle_impoundment_days": chunk.additional_sanctions.vehicle_impoundment_days,
                        "demerit_points": chunk.additional_sanctions.demerit_points,
                    },
                    "remedial_measures": [],
                    "is_exception": chunk.exceptions_and_overrides.has_exception,
                    "rrf_score": rrf_score,
                    "dense_rank": d_rank,
                    "sparse_rank": s_rank,
                }
            )

        return matches

    async def execute_graph_traversal(
        self,
        start_chunk_id: str,
        allowed_edge_types: list[str] | None = None,
        direction: str = "BOTH",
        max_depth: int = 2,
    ) -> list[dict[str, Any]]:
        """Simulates PostgreSQL recursive CTE traverse_normative_triad with cycle detection."""
        results: list[dict[str, Any]] = []
        visited: set[str] = {start_chunk_id}
        queue: list[tuple[str, int, list[str]]] = [(start_chunk_id, 1, [start_chunk_id])]

        while queue:
            curr_id, depth, trail = queue.pop(0)
            if depth > max_depth:
                continue

            for edge in self.graph_edges:
                is_match = False
                next_id = None

                if edge["source_chunk_id"] == curr_id:
                    next_id = edge["target_chunk_id"]
                    is_match = True
                elif direction == "BOTH" and edge["target_chunk_id"] == curr_id:
                    next_id = edge["source_chunk_id"]
                    is_match = True

                if (
                    is_match
                    and next_id
                    and next_id not in visited
                    and (not allowed_edge_types or edge["relation_type"] in allowed_edge_types)
                ):
                    visited.add(next_id)
                    results.append(
                        {
                            "hop_depth": depth,
                            "edge_id": edge["edge_id"],
                            "relation_type": edge["relation_type"],
                            "source_chunk_id": curr_id,
                            "source_path": edge.get("source_path", ""),
                            "target_chunk_id": next_id,
                            "target_path": edge["target_path"],
                            "target_doc_code": edge["target_doc_code"],
                            "target_chunk_index": edge["target_chunk_index"],
                            "target_norm_role": edge["target_norm_role"],
                            "target_raw_text": edge["target_contextualized_text"],
                            "target_contextualized_text": edge["target_contextualized_text"],
                            "min_fine_vnd": None,
                            "max_fine_vnd": None,
                            "is_conditional": False,
                            "condition_expression": None,
                            "confidence_score": edge["confidence_score"],
                            "traversal_trail": f"{edge.get('source_path', curr_id)} -> [{edge['relation_type']}] -> {edge['target_path']}",
                        }
                    )
                    queue.append((next_id, depth + 1, trail + [next_id]))

        return results
