"""Deterministic Multi-Hop Beam Search Graph Traverser over PostgreSQL and MCP."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Any, ClassVar

from rag_eval.legal.mcp.tools import LegalMCPTools
from rag_eval.legal.schemas import remove_vietnamese_diacritics

logger = logging.getLogger(__name__)


@dataclass
class TraversalNode:
    """Individual legal node in the multi-hop reasoning path."""

    node_id: str
    hierarchy_path: str
    document_code: str
    normative_role: str
    content_text: str
    metadata: dict[str, Any]
    score: float


@dataclass
class TraversalPath:
    """Complete traversal path representing an evolving statutory chain."""

    nodes: list[TraversalNode] = field(default_factory=lambda: list[TraversalNode]())
    edge_types: list[str] = field(default_factory=lambda: list[str]())
    cumulative_score: float = 0.0

    @property
    def current_node(self) -> TraversalNode:
        return self.nodes[-1]

    @property
    def visited_node_ids(self) -> set[str]:
        return {n.node_id for n in self.nodes}

    @property
    def visited_paths(self) -> set[str]:
        return {n.hierarchy_path for n in self.nodes if n.hierarchy_path}


class DeterministicTriadTraverser:
    """Executes bounded, parallelized deterministic beam search across Law, Decree, and QCVN relational edges."""

    # Precedence weights for relational edge types
    EDGE_PRIORITIES: ClassVar[dict[str, float]] = {
        "MODIFIES_AND_REPLACES": 1.00,
        "REPEALS": 1.00,
        "HAS_ADDITIONAL_SANCTION": 0.95,
        "REFERENCES_TECHNICAL_STANDARD": 0.90,
        "OVERRIDES_PRIORITY": 0.85,
        "DEFINES_SANCTION_FOR": 0.80,
        "EXEMPTS_CONDITION": 0.80,
        "GUIDES": 0.70,
        "DEFINES_TERM": 0.60,
    }

    def __init__(
        self,
        tools: LegalMCPTools | None = None,
        beam_width: int = 3,
        max_depth: int = 4,
        alpha_semantic: float = 0.35,
        beta_edge: float = 0.35,
        gamma_triad: float = 0.20,
        delta_depth: float = 0.10,
    ) -> None:
        self.tools = tools or LegalMCPTools()
        self.beam_width = beam_width
        self.max_depth = max_depth
        self.alpha = alpha_semantic
        self.beta = beta_edge
        self.gamma = gamma_triad
        self.delta = delta_depth

    async def traverse(
        self,
        query: str,
        vehicle_category: str | None = None,
        seed_chunks: list[dict[str, Any]] | None = None,
        seed_chunk_ids: list[str] | None = None,
        query_vector: list[float] | None = None,
    ) -> list[TraversalPath]:
        """Executes bounded parallel beam search across Law, Decree, and QCVN graphs.

        Eliminates double-querying by accepting pre-retrieved seed chunks from pipeline.py.
        """
        # 1. Initialize Seed Nodes (Bypasses hybrid_search if seeds are passed directly)
        active_beam: list[TraversalPath] = []

        if seed_chunks is not None and len(seed_chunks) > 0:
            for m in seed_chunks[: self.beam_width]:
                score = float(m.get("rrf_score", 0.032))
                node = TraversalNode(
                    node_id=str(m.get("chunk_id", "")),
                    hierarchy_path=str(m.get("path", "")),
                    document_code=str(m.get("doc_code", "100/2019/ND-CP")),
                    normative_role=str(m.get("norm_role", "SANCTION_PRINCIPAL")),
                    content_text=str(m.get("contextualized_text") or m.get("raw_text") or ""),
                    metadata=m,
                    score=score,
                )
                active_beam.append(
                    TraversalPath(
                        nodes=[node],
                        edge_types=[],
                        cumulative_score=score,
                    )
                )
        elif seed_chunk_ids is not None and len(seed_chunk_ids) > 0:
            for cid in seed_chunk_ids[: self.beam_width]:
                nav_res = await self.tools.hierarchical_navigate(target_path=cid, direction="PARENT_CHAIN")
                nodes = nav_res.get("nodes", [])
                node_data = nodes[0] if nodes else {}
                score = 1.0
                node = TraversalNode(
                    node_id=cid,
                    hierarchy_path=str(node_data.get("path", "")),
                    document_code=str(node_data.get("title", "100/2019/ND-CP")),
                    normative_role=str(node_data.get("norm_role", "SANCTION_PRINCIPAL")),
                    content_text=str(node_data.get("contextualized_text") or node_data.get("raw_text") or ""),
                    metadata=node_data,
                    score=score,
                )
                active_beam.append(
                    TraversalPath(
                        nodes=[node],
                        edge_types=[],
                        cumulative_score=score,
                    )
                )
        else:
            # Fallback only when no seeds are supplied
            search_res = await self.tools.hybrid_search(
                query=query,
                query_vector=query_vector,
                vehicle_types=[vehicle_category] if vehicle_category else None,
                limit=self.beam_width,
            )
            matches = search_res.get("results", [])
            for m in matches:
                score = float(m.get("rrf_score", 0.032))
                active_beam.append(
                    TraversalPath(
                        nodes=[
                            TraversalNode(
                                node_id=str(m.get("chunk_id", "")),
                                hierarchy_path=str(m.get("path", "")),
                                document_code=str(m.get("doc_code", "100/2019/ND-CP")),
                                normative_role=str(m.get("norm_role", "SANCTION_PRINCIPAL")),
                                content_text=str(m.get("contextualized_text") or m.get("raw_text") or ""),
                                metadata=m,
                                score=score,
                            )
                        ],
                        edge_types=[],
                        cumulative_score=score,
                    )
                )

        if not active_beam:
            return []

        completed_paths: list[TraversalPath] = []
        normalized_query = self._normalize_vietnamese(query)

        # 2. Iterative Graph Expansion using asyncio.gather for Parallel Fan-Out
        for depth in range(self.max_depth):
            # Concurrently dispatch graph_traverse for all active beam nodes
            tasks = [
                self.tools.graph_traverse(
                    start_chunk_id=path.current_node.node_id,
                    max_depth=1,
                )
                for path in active_beam
            ]
            traverse_results = await asyncio.gather(*tasks, return_exceptions=True)

            candidate_paths: list[TraversalPath] = []
            has_expansion = False

            for path, res in zip(active_beam, traverse_results):
                if isinstance(res, Exception) or not isinstance(res, dict):
                    logger.debug("Graph traverse error at depth %d: %s", depth, res)
                    completed_paths.append(path)
                    continue

                edges = res.get("traversal_paths", [])
                valid_edges: list[dict[str, Any]] = []

                for edge in edges:
                    tgt_id = str(edge.get("target_chunk_id") or edge.get("target_path", ""))
                    tgt_path = str(edge.get("target_path", ""))

                    # Strict Cycle & Self-Loop Prevention
                    if not tgt_id or tgt_id == path.current_node.node_id:
                        continue
                    if tgt_id in path.visited_node_ids:
                        continue
                    if tgt_path and tgt_path in path.visited_paths:
                        continue

                    valid_edges.append(edge)

                if not valid_edges:
                    completed_paths.append(path)
                    continue

                has_expansion = True
                for edge in valid_edges:
                    tgt_id = str(edge.get("target_chunk_id") or edge.get("target_path", ""))
                    tgt_path = str(edge.get("target_path", ""))
                    tgt_doc = str(edge.get("target_doc_code", "QCVN 41:2019/BGTVT"))
                    tgt_role = str(edge.get("target_norm_role", "HYPOTHESIS_CONDITION"))
                    tgt_text = str(
                        edge.get("target_contextualized_text")
                        or edge.get("target_raw_text")
                        or ""
                    )
                    rel_type = str(edge.get("relation_type", ""))
                    edge_conf = float(edge.get("confidence_score", 1.0))

                    # Multi-Hop Composite Score Calculation
                    semantic_sim = self._compute_semantic_similarity(
                        normalized_query=normalized_query,
                        node_text=tgt_text,
                        vehicle_category=vehicle_category,
                        metadata=edge,
                        query_vector=query_vector,
                    )
                    rel_weight = self._get_edge_priority(rel_type)
                    triad_completeness = self._compute_triad_completeness(path.nodes, tgt_role, tgt_doc)
                    depth_bonus = self._compute_hierarchy_depth_bonus(tgt_path)

                    step_score = (
                        self.alpha * semantic_sim
                        + self.beta * (rel_weight * edge_conf)
                        + self.gamma * triad_completeness
                        + self.delta * depth_bonus
                    )
                    new_cum_score = path.cumulative_score + step_score

                    new_node = TraversalNode(
                        node_id=tgt_id,
                        hierarchy_path=tgt_path,
                        document_code=tgt_doc,
                        normative_role=tgt_role,
                        content_text=tgt_text,
                        metadata=edge,
                        score=step_score,
                    )

                    candidate_paths.append(
                        TraversalPath(
                            nodes=path.nodes + [new_node],
                            edge_types=path.edge_types + [rel_type],
                            cumulative_score=new_cum_score,
                        )
                    )

            if not has_expansion or not candidate_paths:
                break

            # Sort and prune active beam to top K
            candidate_paths.sort(key=lambda p: p.cumulative_score, reverse=True)
            active_beam = candidate_paths[: self.beam_width]

            # Early convergence check: if top path has complete triad and no amendment edges
            if depth >= 2 and all(self._is_triad_fully_closed(p) for p in active_beam):
                break

        completed_paths.extend(active_beam)
        # Deduplicate paths by visited node signature
        unique_paths: dict[str, TraversalPath] = {}
        for p in completed_paths:
            sig = "->".join(n.node_id for n in p.nodes)
            if sig not in unique_paths or p.cumulative_score > unique_paths[sig].cumulative_score:
                unique_paths[sig] = p

        sorted_results = sorted(unique_paths.values(), key=lambda p: p.cumulative_score, reverse=True)
        return sorted_results[: self.beam_width]

    def _get_edge_priority(self, edge_type: str) -> float:
        """Assigns statutory priority weights to relational graph edge types."""
        return self.EDGE_PRIORITIES.get(edge_type, 0.50)

    @staticmethod
    def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
        """Computes cosine similarity between two float vectors."""
        if not vec_a or not vec_b or len(vec_a) != len(vec_b):
            return 0.0
        dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = sum(a * a for a in vec_a) ** 0.5
        norm_b = sum(b * b for b in vec_b) ** 0.5
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        sim = dot_product / (norm_a * norm_b)
        return max(0.0, min(1.0, sim))

    def _compute_semantic_similarity(
        self,
        normalized_query: str,
        node_text: str,
        vehicle_category: str | None,
        metadata: dict[str, Any],
        query_vector: list[float] | None = None,
        target_vector: list[float] | None = None,
    ) -> float:
        """Computes query semantic affinity score for a newly expanded target node."""
        if not node_text and not metadata:
            return 0.20

        dense_score: float | None = None

        # 1. Check for explicit or extracted target vector
        t_vec = (
            target_vector
            or metadata.get("embedding_vector")
            or metadata.get("target_embedding")
            or metadata.get("dense_embedding")
            or metadata.get("dense_embedding_384")
            or metadata.get("dense_embedding_1536")
        )
        if query_vector is not None and t_vec is not None and isinstance(t_vec, list):
            dense_score = self._cosine_similarity(query_vector, t_vec)
        elif "semantic_similarity" in metadata and isinstance(metadata["semantic_similarity"], (int, float)):
            dense_score = float(metadata["semantic_similarity"])
        elif "similarity_score" in metadata and isinstance(metadata["similarity_score"], (int, float)):
            dense_score = float(metadata["similarity_score"])
        elif "cosine_similarity" in metadata and isinstance(metadata["cosine_similarity"], (int, float)):
            dense_score = float(metadata["cosine_similarity"])

        # 2. Lexical Jaccard token overlap
        norm_text = self._normalize_vietnamese(node_text) if node_text else ""
        query_words = set(normalized_query.split())
        text_words = set(norm_text.split()) if norm_text else set()

        if query_words and text_words:
            intersection = query_words.intersection(text_words)
            jaccard = len(intersection) / len(query_words)
            lexical_score = min(0.70, jaccard * 1.5)
        else:
            lexical_score = 0.50 if not query_words else 0.20

        if dense_score is not None:
            dense_clamped = max(0.0, min(1.0, dense_score))
            score = 0.70 * dense_clamped + 0.30 * lexical_score
        else:
            score = lexical_score

        # 3. Vehicle category alignment bonus (+0.15)
        if vehicle_category and norm_text:
            norm_veh = self._normalize_vietnamese(vehicle_category)
            if norm_veh in norm_text or any(w in norm_text for w in norm_veh.split()):
                score += 0.15

        # 4. Key statutory tokens bonus (+0.15)
        statutory_tokens = ["phat tien", "tuoc quyen", "giay phep", "bien bao", "hieu lenh", "diem tru"]
        if norm_text and any(tok in norm_text for tok in statutory_tokens if tok in normalized_query):
            score += 0.15

        return max(0.0, min(1.0, score))

    def _compute_triad_completeness(
        self,
        existing_nodes: list[TraversalNode],
        candidate_role: str,
        candidate_doc: str,
    ) -> float:
        """Calculates normative triad coverage (Hypothesis, Prescription, Sanction)."""
        roles = {n.normative_role for n in existing_nodes} | {candidate_role}
        docs = {n.document_code for n in existing_nodes} | {candidate_doc}

        has_hypothesis = (
            "HYPOTHESIS_CONDITION" in roles
            or any("qcvn" in d.lower() or "tt" in d.lower() or "thong tu" in d.lower() for d in docs)
        )
        has_prescription = (
            any(r in roles for r in ["PRESCRIPTION_DUTY", "PRESCRIPTION_PROHIBITION", "PRESCRIPTION_PERMISSION"])
            or any("luat" in d.lower() for d in docs)
        )
        has_sanction = (
            any(r in roles for r in ["SANCTION_PRINCIPAL", "SANCTION_SUPPLEMENTARY", "SANCTION_POINT_DEDUCTION", "REMEDIAL_MEASURE"])
            or any("100" in d or "123" in d or "168" in d or "nghi dinh" in d.lower() for d in docs)
        )

        count = sum([has_hypothesis, has_prescription, has_sanction])
        return count / 3.0

    def _is_triad_fully_closed(self, path: TraversalPath) -> bool:
        """Checks if a traversal path has fully integrated all 3 legs of the normative triad."""
        roles = {n.normative_role for n in path.nodes}
        docs = {n.document_code.lower() for n in path.nodes}

        has_hyp = "HYPOTHESIS_CONDITION" in roles or any("qcvn" in d for d in docs)
        has_pres = any("PRESCRIPTION" in r for r in roles) or any("luat" in d for d in docs)
        has_sanc = any("SANCTION" in r for r in roles) or any("100" in d or "123" in d for d in docs)
        return has_hyp and has_pres and has_sanc

    def _compute_hierarchy_depth_bonus(self, hierarchy_path: str) -> float:
        """Rewards fine-grained statutory sub-points over broad document nodes."""
        if not hierarchy_path:
            return 0.30
        if ".p_" in hierarchy_path:  # Point (Điểm) level
            return 1.00
        if ".c" in hierarchy_path:   # Clause (Khoản) level
            return 0.70
        if ".a" in hierarchy_path:   # Article (Điều) level
            return 0.40
        return 0.20

    @staticmethod
    def _normalize_vietnamese(text: str) -> str:
        """Normalizes Vietnamese text using consolidated remove_vietnamese_diacritics helper."""
        return re.sub(r"[^\w\s]", " ", remove_vietnamese_diacritics(text).lower().replace("_", " ")).strip()
