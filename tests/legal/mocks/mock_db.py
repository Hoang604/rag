"""In-memory mock database pool and stored procedures simulation."""

from __future__ import annotations

import datetime
import functools
import hashlib
import re
import unicodedata
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict, cast

from rag_eval.legal.ingestion.cphc import CPHCEngine
from rag_eval.legal.ingestion.parser import LegalASTParser
from rag_eval.legal.mcp.tools import SearchResultItem, TraversalPathItem
from rag_eval.legal.schemas import (
    CanonicalFullyQualifiedChunk,
    GraphRelationType,
)
from tests.legal.fixtures.laws_data import ALL_STATUTORY_CHUNKS
from tests.legal.fixtures.signs_data import ALL_SIGN_CATALOG, SignDefinition

_CACHED_LAW36_CHUNKS: list[CanonicalFullyQualifiedChunk] | None = None


def _load_law36_chunks() -> list[CanonicalFullyQualifiedChunk]:
    global _CACHED_LAW36_CHUNKS
    if _CACHED_LAW36_CHUNKS is not None:
        return _CACHED_LAW36_CHUNKS

    p1 = Path("/home/hoang/python/rag/data/36-2024-qh15.txt")
    p2 = Path("/home/hoang/python/rag/data/36-2024-qh15_tiep.txt")
    t1 = p1.read_text(encoding="utf-8") if p1.exists() else ""
    t2 = p2.read_text(encoding="utf-8") if p2.exists() else ""
    full_text = f"{t1}\n{t2}".strip()

    if not full_text:
        _CACHED_LAW36_CHUNKS = []
        return _CACHED_LAW36_CHUNKS

    parser = LegalASTParser()
    ast = parser.parse_document(
        doc_code="36/2024/QH15",
        raw_text=full_text,
        doc_title="Luật Trật tự, an toàn giao thông đường bộ 2024",
        doc_type="LUAT",
    )
    cphc = CPHCEngine()
    chunks, _ = cphc.process_ast(ast, document_id="doc_luat36")
    _CACHED_LAW36_CHUNKS = chunks
    return _CACHED_LAW36_CHUNKS


class RuntimeKnowledgeCacheEntry(TypedDict, total=False):
    cache_id: str
    id: str
    query_hash: str
    natural_query: str
    synthesized_answer: str
    answer: str
    verified_citations: list[str]
    intent_classification: dict[str, object]
    generated_plan: dict[str, object]
    query_embedding_384: list[float] | None
    validation_status: str
    hit_count: int
    ttl_seconds: int
    similarity_score: float
    is_exact_match: bool


@dataclass
class PrecomputedChunk:
    chunk: CanonicalFullyQualifiedChunk
    v_norm: str
    c_norm: str
    p_norm: str
    l_norm: str
    all_tokens: set[str]
    token_counts: dict[str, int]
    doc_len: int
    veh_values: set[str]


class MockConnection:
    """Emulates asyncpg.Connection interface for MockDatabasePool."""

    def __init__(self, pool: MockDatabasePool) -> None:
        self.pool = pool

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        q_upper = query.upper()
        if "HYBRID_LEGAL_SEARCH" in q_upper or "TSV_VI @@" in q_upper:
            q_text = str(args[0]) if len(args) > 0 and args[0] is not None else ""
            limit = int(args[2]) if len(args) > 2 and isinstance(args[2], int) else (int(args[4]) if len(args) > 4 and isinstance(args[4], int) else 20)
            res = await self.pool.execute_hybrid_search(
                query=q_text,
                limit=limit,
            )
            return [
                {
                    "chunk_id": str(r.get("chunk_id", "") if isinstance(r, dict) else getattr(r, "chunk_id", "")),
                    "path": str(r.get("path", "") if isinstance(r, dict) else getattr(r, "path", "")),
                    "chunk_index": str(r.get("chunk_index", "") if isinstance(r, dict) else getattr(r, "chunk_index", "")),
                    "contextualized_text": str(r.get("contextualized_text", "") if isinstance(r, dict) else getattr(r, "contextualized_text", "")),
                    "min_fine_vnd": r.get("min_fine_vnd") if isinstance(r, dict) else getattr(r, "min_fine_vnd", None),
                    "max_fine_vnd": r.get("max_fine_vnd") if isinstance(r, dict) else getattr(r, "max_fine_vnd", None),
                    "rrf_score": float(r.get("score", 1.0) if isinstance(r, dict) else getattr(r, "score", 1.0)),
                    "dense_rank": 1,
                    "sparse_rank": 1,
                    "lead_sentence": str(r.get("lead_sentence", "") if isinstance(r, dict) else getattr(r, "lead_sentence", "")),
                    "verbatim_text": str(r.get("verbatim_text") or r.get("raw_text") or ""),
                    "norm_role": str(r.get("norm_role", "PRESCRIPTION_DUTY") if isinstance(r, dict) else getattr(r, "norm_role", "PRESCRIPTION_DUTY")),
                    "additional_sanctions": r.get("additional_sanctions", {}) if isinstance(r, dict) else getattr(r, "additional_sanctions", {}),
                    "remedial_measures": r.get("remedial_measures", []) if isinstance(r, dict) else getattr(r, "remedial_measures", []),
                    "is_exception": False,
                    "doc_code": str(r.get("doc_code", "100/2019/ND-CP") if isinstance(r, dict) else getattr(r, "document_code", "100/2019/ND-CP")),
                    "doc_title": str(r.get("doc_title", "Nghị định 100/2019/NĐ-CP") if isinstance(r, dict) else getattr(r, "doc_title", "Nghị định 100/2019/NĐ-CP")),
                }
                for r in res
            ]
        elif "VERBATIM_LEGAL_GREP" in q_upper:
            pattern = str(args[0]) if len(args) > 0 and args[0] is not None else ""
            is_regex = bool(args[1]) if len(args) > 1 and args[1] is not None else False
            case_sens = bool(args[2]) if len(args) > 2 and args[2] is not None else False
            doc_codes = args[3] if len(args) > 3 and isinstance(args[3], list) else None
            limit = int(args[4]) if len(args) > 4 and isinstance(args[4], int) else 20
            res = await self.pool.execute_verbatim_grep(
                query_pattern=pattern,
                is_regex=is_regex,
                case_sensitive=case_sens,
                target_documents=doc_codes,
                match_limit=limit,
            )
            return [
                {
                    "chunk_id": str(r.get("chunk_id", "") if isinstance(r, dict) else getattr(r, "chunk_id", "")),
                    "path": str(r.get("path", "") if isinstance(r, dict) else getattr(r, "path", "")),
                    "chunk_index": str(r.get("chunk_index", "") if isinstance(r, dict) else getattr(r, "chunk_index", "")),
                    "contextualized_text": str(r.get("contextualized_text", "") if isinstance(r, dict) else getattr(r, "contextualized_text", "")),
                    "verbatim_text": str(r.get("verbatim_text", "") if isinstance(r, dict) else getattr(r, "verbatim_text", "")),
                    "norm_role": str(r.get("norm_role", "PRESCRIPTION_DUTY") if isinstance(r, dict) else getattr(r, "norm_role", "PRESCRIPTION_DUTY")),
                    "min_fine_vnd": r.get("min_fine_vnd") if isinstance(r, dict) else getattr(r, "min_fine_vnd", None),
                    "max_fine_vnd": r.get("max_fine_vnd") if isinstance(r, dict) else getattr(r, "max_fine_vnd", None),
                    "match_headline": str(r.get("match_headline", r.get("verbatim_text", "")) if isinstance(r, dict) else getattr(r, "verbatim_text", "")),
                    "doc_code": str(r.get("doc_code", "100/2019/ND-CP") if isinstance(r, dict) else getattr(r, "document_code", "100/2019/ND-CP")),
                    "doc_title": str(r.get("doc_title", "Nghị định 100/2019/NĐ-CP") if isinstance(r, dict) else getattr(r, "doc_title", "Nghị định 100/2019/NĐ-CP")),
                }
                for r in res
            ]
        elif "SIGN_CATALOG" in q_upper:
            code_pat = str(args[0]).replace("%", "").strip().upper() if len(args) > 0 and args[0] else None
            kw_pat = str(args[1]).replace("%", "").strip().lower() if len(args) > 1 and args[1] else None
            cat_pat = str(args[2]).strip().upper() if len(args) > 2 and args[2] else None
            limit = int(args[3]) if len(args) > 3 and isinstance(args[3], int) else 5

            c_clean = code_pat.replace(".", "") if code_pat else None
            matched: list[dict[str, object]] = []
            for s in self.pool.signs.values():
                s_u = s.sign_code.upper()
                s_c = s_u.replace(".", "")
                matches = False
                if code_pat and (code_pat in s_u or (c_clean and c_clean in s_c)) or kw_pat and (kw_pat in s.sign_name.lower() or kw_pat in s.meaning.lower()) or not code_pat and not kw_pat:
                    matches = True
                if cat_pat and str(s.category).upper() != cat_pat:
                    matches = False
                if matches:
                    matched.append(
                        {
                            "sign_code": s.sign_code,
                            "sign_name": s.sign_name,
                            "category": str(s.category),
                            "shape": s.shape,
                            "primary_color": s.primary_color,
                            "meaning": s.meaning,
                            "placement_rules": s.placement_rules,
                            "penalty_references": s.penalty_references,
                        }
                    )
            return matched[:limit]
        elif "LEGAL_GRAPH_EDGES" in q_upper or "RECURSIVE TRAVERSAL" in q_upper or "TRAVERSE_NORMATIVE_TRIAD" in q_upper:
            start_id = str(args[0]) if len(args) > 0 and args[0] is not None else ""
            direction = str(args[1]) if len(args) > 1 and args[1] is not None else "BOTH"
            rel_types = args[2] if len(args) > 2 and isinstance(args[2], list) else None

            edges = []
            for edge in self.pool.graph_edges:
                src_id = str(edge.get("source_chunk_id") or "")
                src_path = str(edge.get("source_path") or "")
                tgt_id = str(edge.get("target_chunk_id") or "")
                tgt_path = str(edge.get("target_path") or "")

                src_match = (src_id == start_id or src_path == start_id)
                tgt_match = (tgt_id == start_id or tgt_path == start_id)
                is_match = (
                    (direction == "OUTGOING" and src_match)
                    or (direction == "INCOMING" and tgt_match)
                    or (direction == "BOTH" and (src_match or tgt_match))
                )
                if is_match:
                    rel_type = str(edge.get("relation_type", ""))
                    if rel_types is None or rel_type in rel_types:
                        edges.append({
                            "edge_id": edge.get("edge_id", str(edge.get("id", "e1"))),
                            "hop_depth": 1,
                            "relation_type": rel_type,
                            "confidence_score": float(str(edge.get("confidence_score", "1.0"))),
                            "is_conditional": bool(edge.get("is_conditional", False)),
                            "condition_expression": edge.get("condition_expression"),
                            "source_chunk_id": src_id or "c1",
                            "source_path": src_path or "",
                            "target_chunk_id": tgt_id,
                            "target_path": tgt_path or "",
                            "target_doc_code": edge.get("target_doc_code", "QCVN 41:2019/BGTVT" if "qcvn" in tgt_id.lower() or "qcvn" in tgt_path.lower() else "100/2019/ND-CP"),
                            "target_chunk_index": edge.get("target_chunk_index", "Điều 10"),
                            "target_norm_role": edge.get("target_norm_role", "HYPOTHESIS_CONDITION"),
                            "target_raw_text": edge.get("target_contextualized_text", ""),
                            "target_contextualized_text": edge.get("target_contextualized_text", ""),
                            "min_fine_vnd": None,
                            "max_fine_vnd": None,
                        })
            return edges
        elif "LEGAL_CHUNKS" in q_upper and ("@>" in query or "<@" in query or "SUBPATH" in q_upper or "NLEVEL" in q_upper):
            target_path = str(args[0]) if len(args) > 0 and args[0] is not None else ""
            target_clean = target_path.strip()
            nodes: list[dict[str, object]] = []
            parts = target_clean.split(".")
            art_seg = ""
            art_prefix = ""
            for p in parts:
                art_prefix = f"{art_prefix}.{p}" if art_prefix else p
                if p.startswith(("a", "art")):
                    art_seg = p
                    break

            for chunk in self.pool.chunks.values():
                c_path = chunk.hierarchy_path
                matches = False
                if "@>" in query:
                    matches = target_clean.startswith(c_path) or c_path.startswith(target_clean)
                elif "<@" in query and "!=" in query:
                    matches = c_path.startswith(target_clean) and c_path != target_clean
                elif "SUBPATH" in q_upper and "INDEX" in q_upper:
                    matches = (art_seg and f".{art_seg}." in f".{c_path}.") or c_path.startswith(art_prefix) or art_prefix.startswith(c_path)
                elif "SUBPATH" in q_upper:
                    p_target = ".".join(target_clean.split(".")[:-1])
                    p_chunk = ".".join(c_path.split(".")[:-1])
                    matches = (p_target == p_chunk) and len(c_path.split(".")) == len(target_clean.split("."))
                else:
                    matches = c_path.startswith(target_clean)

                if matches:
                    level = "POINT" if chunk.point_letter else ("CLAUSE" if chunk.clause_number else "ARTICLE")
                    nodes.append(
                        {
                            "chunk_id": chunk.chunk_id,
                            "path": chunk.hierarchy_path,
                            "depth": len(chunk.hierarchy_path.split(".")),
                            "chunk_level": level,
                            "chunk_index": chunk.article_index,
                            "verbatim_text": chunk.verbatim_text,
                            "contextualized_text": chunk.contextualized_text,
                            "lead_sentence": chunk.lead_sentence,
                            "norm_role": getattr(chunk.norm_role, "value", str(chunk.norm_role)),
                            "doc_code": chunk.document_code,
                            "doc_title": chunk.doc_title,
                        }
                    )
            return nodes
        return []

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        q_upper = query.upper()
        if "LEGAL_DOCUMENTS" in q_upper:
            doc_id_or_code = str(args[0]) if len(args) > 0 and args[0] else None
            if doc_id_or_code:
                for d in self.pool.documents.values():
                    if d.get("id") == doc_id_or_code or d.get("doc_code") == doc_id_or_code:
                        return {"id": d["id"], "doc_code": d["doc_code"], "title": d["title"]}
            first_doc = next(iter(self.pool.documents.values()), None)
            if first_doc:
                return {"id": first_doc["id"], "doc_code": first_doc["doc_code"], "title": first_doc["title"]}
            return None
        elif "RUNTIME_KNOWLEDGE_CACHE" in q_upper or "QUERY_RUNTIME_KNOWLEDGE_CACHE" in q_upper:
            q_hash = str(args[0]) if len(args) > 0 and args[0] else None
            entry = self.pool.runtime_cache.get(q_hash) if q_hash else None
            if not entry and len(args) > 1 and args[1]:
                nat_q = str(args[1])
                for v in self.pool.runtime_cache.values():
                    if v.get("natural_query") == nat_q:
                        entry = v
                        break
            if not entry and q_hash:
                for v in self.pool.runtime_cache.values():
                    if v.get("query_hash") == q_hash:
                        entry = v
                        break
            if entry:
                return {
                    "cache_id": str(entry.get("cache_id") or entry.get("id") or ""),
                    "query_hash": str(entry.get("query_hash") or q_hash or ""),
                    "natural_query": str(entry.get("natural_query") or ""),
                    "synthesized_answer": str(entry.get("synthesized_answer") or entry.get("answer") or ""),
                    "verified_answer": str(entry.get("synthesized_answer") or entry.get("answer") or ""),
                    "retrieved_chunk_ids": entry.get("retrieved_chunk_ids", []),
                    "verified_citations": entry.get("verified_citations", []),
                    "generated_plan": entry.get("generated_plan", {}),
                    "plan_dag": entry.get("generated_plan", {}),
                    "similarity_score": 1.0,
                    "is_exact_match": True,
                }
            return None
        return None

    async def fetchval(self, query: str, *args: object) -> object:
        q_upper = query.upper()
        if "COUNT(*)" in q_upper and "LEGAL_CHUNKS" in q_upper:
            return len(self.pool.chunks)
        elif "COUNT(*)" in q_upper and "LEGAL_GRAPH_EDGES" in q_upper:
            return len(self.pool.graph_edges)
        return 0

    async def execute(self, query: str, *args: object) -> str:
        q_upper = query.upper()
        if "INSERT INTO RUNTIME_KNOWLEDGE_CACHE" in q_upper:
            cid = str(args[0]) if len(args) > 0 else str(uuid.uuid4())
            q_hash = str(args[1]) if len(args) > 1 else ""
            nat_q = str(args[2]) if len(args) > 2 else ""
            ans = str(args[3]) if len(args) > 3 else ""
            cits = args[4] if len(args) > 4 else []
            plan = args[5] if len(args) > 5 else {}
            entry: dict[str, object] = {
                "id": cid,
                "cache_id": cid,
                "query_hash": q_hash,
                "natural_query": nat_q,
                "synthesized_answer": ans,
                "answer": ans,
                "verified_citations": cits if isinstance(cits, list) else [],
                "generated_plan": plan if isinstance(plan, dict) else {},
                "validation_status": "VERIFIED",
                "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
            }
            if q_hash:
                self.pool.runtime_cache[q_hash] = entry
            return "INSERT 0 1"
        elif "INSERT INTO LEGAL_GRAPH_EDGES" in q_upper:
            self.pool.graph_edges.append({"source_id": args[0] if args else "", "target_id": args[1] if len(args) > 1 else ""})
            return "INSERT 0 1"
        return "OK"


class MockDatabasePool:
    """Async in-memory database pool simulating PostgreSQL 16 + pgvector storage."""

    @asynccontextmanager
    async def acquire(self):
        """Yields an emulated asyncpg connection."""
        yield MockConnection(self)

    def __init__(self) -> None:
        self.documents: dict[str, dict[str, object]] = {
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
        all_chunks = list(ALL_STATUTORY_CHUNKS) + _load_law36_chunks()
        self.chunks: dict[str, CanonicalFullyQualifiedChunk] = {
            chunk.chunk_id: chunk for chunk in all_chunks
        }
        self.hierarchy_nodes: dict[str, dict[str, object]] = self._init_hierarchy_nodes()
        self.signs: dict[str, SignDefinition] = {
            sign.sign_code: sign for sign in ALL_SIGN_CATALOG
        }
        self.graph_edges: list[dict[str, object]] = self._init_graph_edges()
        self.runtime_cache: dict[str, dict[str, object]] = {}
        self.query_logs: list[dict[str, object]] = []
        self._idf: dict[str, float] = {}
        self._avgdl: float = 1.0
        self._precomputed_chunks: list[PrecomputedChunk] = self._init_precomputed_chunks()
        self._trigram_index: dict[str, set[str]] = {}
        self._trigram_indexed_count: int = 0
        self._build_trigram_index()

    def _build_trigram_index(self) -> None:
        index: dict[str, set[str]] = {}
        for chunk in self.chunks.values():
            texts = [chunk.verbatim_text.lower(), chunk.contextualized_text.lower()]
            if chunk.lead_sentence:
                texts.append(chunk.lead_sentence.lower())
            for text in texts:
                for i in range(len(text) - 2):
                    tg = text[i : i + 3]
                    if tg not in index:
                        index[tg] = set()
                    index[tg].add(chunk.chunk_id)
        self._trigram_index = index
        self._trigram_indexed_count = len(self.chunks)

    def _ensure_trigram_index(self) -> None:
        if self._trigram_indexed_count != len(self.chunks):
            self._build_trigram_index()

    def _init_precomputed_chunks(self) -> list[PrecomputedChunk]:
        precomputed: list[PrecomputedChunk] = []
        df_counts: dict[str, int] = {}
        total_len = 0

        for chunk in self.chunks.values():
            v_norm = self._normalize_text(chunk.verbatim_text)
            c_norm = self._normalize_text(chunk.contextualized_text)
            p_norm = self._normalize_text(chunk.synthesized_prefix)
            l_norm = self._normalize_text(chunk.lead_sentence or "")
            d_norm = self._normalize_text(chunk.document_code)
            h_norm = self._normalize_text(chunk.hierarchy_path.replace(".", " "))

            all_text_combined = f"{d_norm} {h_norm} {v_norm} {l_norm} {p_norm} {c_norm}"
            words = [w for w in all_text_combined.split() if w]
            doc_len = len(words)
            total_len += doc_len

            token_counts: dict[str, int] = {}
            for w in words:
                token_counts[w] = token_counts.get(w, 0) + 1

            bigrams = [f"{words[i]} {words[i + 1]}" for i in range(len(words) - 1)]
            for bg in bigrams:
                token_counts[bg] = token_counts.get(bg, 0) + 1

            all_tokens = set(words)
            all_tokens.update(bigrams)
            for word in words:
                if len(word) >= 3:
                    for i in range(len(word) - 2):
                        tg = word[i : i + 3]
                        all_tokens.add(tg)
                        token_counts[tg] = token_counts.get(tg, 0) + 1

            for token in all_tokens:
                df_counts[token] = df_counts.get(token, 0) + 1

            precomputed.append(
                PrecomputedChunk(
                    chunk=chunk,
                    v_norm=v_norm,
                    c_norm=c_norm,
                    p_norm=p_norm,
                    l_norm=l_norm,
                    all_tokens=all_tokens,
                    token_counts=token_counts,
                    doc_len=doc_len,
                    veh_values=set(),
                )
            )

        import math
        n_docs = max(len(self.chunks), 1)
        self._avgdl = total_len / n_docs if n_docs > 0 else 1.0
        self._idf = {
            t: math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))
            for t, df in df_counts.items()
        }
        return precomputed

    def _init_hierarchy_nodes(self) -> dict[str, dict[str, object]]:
        nodes: dict[str, dict[str, object]] = {}
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

    def _init_graph_edges(self) -> list[dict[str, object]]:
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
    @functools.lru_cache(maxsize=16384)
    def _normalize_text(text: str) -> str:
        nfkd = unicodedata.normalize("NFKD", text)
        un = "".join(c for c in nfkd if not unicodedata.combining(c))
        un = un.replace("đ", "d").replace("Đ", "D")
        return re.sub(r"[^\w\s]", " ", un.lower())

    @staticmethod
    def _compute_trigram_similarity(pattern: str, text: str) -> float:
        p = pattern.strip().lower()
        t = text.strip().lower()
        if not p or not t:
            return 0.0
        if p in t:
            len_ratio = len(p) / max(len(t), 1)
            return min(1.0, max(0.6, len_ratio + 0.5))

        def get_trigrams(s: str) -> set[str]:
            padded = f"  {s} "
            return {padded[i : i + 3] for i in range(len(padded) - 2)}

        trigrams_p = get_trigrams(p)
        trigrams_t = get_trigrams(t)
        if not trigrams_p or not trigrams_t:
            return 0.0
        intersection = trigrams_p & trigrams_t
        union = trigrams_p | trigrams_t
        return len(intersection) / len(union) if union else 0.0

    async def get_document(self, doc_code: str) -> dict[str, object] | None:
        return self.documents.get(doc_code)

    async def list_documents(self) -> list[dict[str, object]]:
        return list(self.documents.values())

    async def get_sign(self, sign_code: str) -> SignDefinition | None:
        return self.signs.get(sign_code.strip())

    async def query_runtime_cache(
        self,
        query_hash: object = None,
        query_vector: object = None,
        similarity_threshold: float = 0.92,
        **kwargs: object,
    ) -> RuntimeKnowledgeCacheEntry | None:
        qh_str = str(query_hash) if query_hash is not None else None
        if qh_str and qh_str in self.runtime_cache:
            return cast(RuntimeKnowledgeCacheEntry, self.runtime_cache[qh_str])

        if not qh_str and kwargs.get("input_query"):
            q_str = str(kwargs["input_query"])
            h = hashlib.sha256(q_str.strip().lower().encode("utf-8")).hexdigest()
            if h in self.runtime_cache:
                return cast(RuntimeKnowledgeCacheEntry, self.runtime_cache[h])

        natural_query = cast(str | None, kwargs.get("natural_query"))
        if natural_query:
            for v in self.runtime_cache.values():
                if v.get("natural_query") == natural_query:
                    return cast(RuntimeKnowledgeCacheEntry, v)

        return None

    async def write_runtime_cache(self, query_hash: str, entry: dict[str, object]) -> None:
        self.runtime_cache[query_hash] = entry

    async def write_runtime_knowledge_cache(
        self,
        natural_query: str,
        synthesized_answer: str,
        verified_citations: list[str] | None = None,
        intent_classification: dict[str, object] | None = None,
        generated_plan: dict[str, object] | None = None,
        query_embedding_384: list[float] | None = None,
        query_hash: str | None = None,
        ttl_seconds: int = 2592000,
    ) -> dict[str, object]:
        q_hash = (
            query_hash
            if query_hash is not None
            else hashlib.sha256(natural_query.strip().lower().encode("utf-8")).hexdigest()
        )
        cache_id = str(uuid.uuid4())
        entry: dict[str, object] = {
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
    ) -> dict[str, object] | None:
        computed_hash = hashlib.sha256(input_query.strip().lower().encode("utf-8")).hexdigest()
        if computed_hash in self.runtime_cache:
            entry = self.runtime_cache[computed_hash]
            hit_count = entry.get("hit_count", 0)
            entry["hit_count"] = (int(hit_count) if isinstance(hit_count, (int, float)) else 0) + 1
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
        return {
            "documents": len(self.documents),
            "chunks": len(self.chunks),
            "hierarchy_nodes": len(self.hierarchy_nodes),
            "signs": len(self.signs),
            "graph_edges": len(self.graph_edges),
            "runtime_cache": len(self.runtime_cache),
            "query_logs": len(self.query_logs),
        }

    async def execute_verbatim_grep(
        self,
        query_pattern: str,
        target_documents: list[str] | None = None,
        target_vehicles: list[str] | None = None,
        is_regex: bool = False,
        case_sensitive: bool = False,
        t_violation: str | datetime.date | None = None,
        match_limit: int = 20,
    ) -> list[SearchResultItem]:
        self._ensure_trigram_index()
        clean_pattern = query_pattern.strip()
        if not clean_pattern:
            return []

        t_viol_date_str: str | None = None
        if t_violation is not None:
            if isinstance(t_violation, datetime.date):
                t_viol_date_str = t_violation.isoformat()
            else:
                t_viol_date_str = str(t_violation).strip()

        expanded_vehicles: set[str] = set()
        if target_vehicles:
            for v in target_vehicles:
                if v:
                    expanded_vehicles.add(str(v).strip().upper())

        compiled_regex: re.Pattern[str] | None = None
        if is_regex:
            flags = 0 if case_sensitive else re.IGNORECASE
            try:
                compiled_regex = re.compile(clean_pattern, flags)
            except re.error:
                return []

        matched_candidates: list[tuple[float, CanonicalFullyQualifiedChunk]] = []

        pat_lower = clean_pattern.lower()
        for chunk in self.chunks.values():
            if t_viol_date_str is not None:
                chunk_eff = chunk.effective_date
                chunk_exp = chunk.expiration_date
                if chunk_eff is not None and t_viol_date_str < chunk_eff:
                    continue
                if chunk_exp is not None and t_viol_date_str >= chunk_exp:
                    continue

            if (
                target_documents
                and len(target_documents) > 0
                and chunk.document_code not in target_documents
            ):
                continue

            verbatim = chunk.verbatim_text
            ctx = chunk.contextualized_text

            if is_regex and compiled_regex is not None:
                match_v = compiled_regex.search(verbatim)
                match_c = compiled_regex.search(ctx)
                if not match_v and not match_c:
                    continue
                sim_score = 1.0 if match_v else 0.85
            else:
                if case_sensitive:
                    match_v = clean_pattern in verbatim
                    match_c = clean_pattern in ctx
                else:
                    match_v = pat_lower in verbatim.lower()
                    match_c = pat_lower in ctx.lower()

                if not match_v and not match_c:
                    continue

                sim_score = 1.0 if match_v else 0.85

            matched_candidates.append((sim_score, chunk))

        matched_candidates.sort(
            key=lambda x: (
                -x[0],
                x[1].document_code,
                x[1].hierarchy_path,
            ),
        )

        results: list[SearchResultItem] = []
        for sim_score, chunk in matched_candidates[:match_limit]:
            point_part = f"Điểm {chunk.point_letter}" if chunk.point_letter else ""
            clause_part = f"Khoản {chunk.clause_number}" if chunk.clause_number else ""
            chunk_idx = f"{point_part} {clause_part} {chunk.article_index}".strip()
            results.append(
                SearchResultItem.model_validate(
                    {
                        "chunk_id": chunk.chunk_id,
                        "path": chunk.hierarchy_path,
                        "doc_code": chunk.document_code,
                        "doc_title": chunk.document_code,
                        "title": chunk.document_code,
                        "lead_sentence": chunk.lead_sentence or chunk.verbatim_text,
                        "chunk_index": chunk_idx,
                        "raw_text": chunk.verbatim_text,
                        "verbatim_text": chunk.verbatim_text,
                        "contextualized_text": chunk.contextualized_text,
                        "min_fine_vnd": chunk.fine_bounds.min_fine_vnd,
                        "max_fine_vnd": chunk.fine_bounds.max_fine_vnd,
                        "similarity_score": sim_score,
                        "effective_date": chunk.effective_date,
                        "expiration_date": chunk.expiration_date,
                        "norm_role": chunk.norm_role.value if hasattr(chunk.norm_role, "value") else str(chunk.norm_role),
                    }
                )
            )

        return results

    async def verbatim_legal_grep(
        self,
        query_pattern: str,
        target_documents: list[str] | None = None,
        target_vehicles: list[str] | None = None,
        is_regex: bool = False,
        case_sensitive: bool = False,
        t_violation: str | datetime.date | None = None,
        match_limit: int = 20,
    ) -> list[SearchResultItem]:
        return await self.execute_verbatim_grep(
            query_pattern=query_pattern,
            target_documents=target_documents,
            target_vehicles=target_vehicles,
            is_regex=is_regex,
            case_sensitive=case_sensitive,
            t_violation=t_violation,
            match_limit=match_limit,
        )

    async def execute_hybrid_search(
        self,
        query: str,
        vehicle_category: str | None = None,
        norm_roles: list[str] | None = None,
        fine_min_vnd: int | None = None,
        fine_max_vnd: int | None = None,
        document_codes: list[str] | None = None,
        t_violation: str | datetime.date | None = None,
        limit: int = 10,
    ) -> list[SearchResultItem]:
        normalized_q = self._normalize_text(query)
        raw_tokens = [t for t in normalized_q.split() if t]

        query_words = raw_tokens
        query_bigrams = [
            f"{raw_tokens[i]} {raw_tokens[i + 1]}"
            for i in range(len(raw_tokens) - 1)
        ]
        query_terms = query_words + query_bigrams

        query_subwords: list[str] = []
        for w in query_words:
            if len(w) >= 3:
                for i in range(len(w) - 2):
                    query_subwords.append(w[i : i + 3])

        t_viol_date_str = None
        if t_violation is not None:
            t_viol_date_str = t_violation.isoformat() if isinstance(t_violation, datetime.date) else str(t_violation).strip()

        scored_candidates: list[tuple[float, float, CanonicalFullyQualifiedChunk]] = []

        for p_item in self._precomputed_chunks:
            chunk = p_item.chunk

            if t_viol_date_str is not None:
                if chunk.effective_date is not None and t_viol_date_str < chunk.effective_date:
                    continue
                if chunk.expiration_date is not None and t_viol_date_str >= chunk.expiration_date:
                    continue

            if document_codes and chunk.document_code not in document_codes:
                continue

            k1 = 1.2
            b = 0.75
            dl = p_item.doc_len
            denom = dl / max(self._avgdl, 1.0)

            sparse_score = 0.0
            for term in query_terms:
                tf = p_item.token_counts.get(term, 0)
                if tf > 0:
                    idf = self._idf.get(term, 1.0)
                    term_score = idf * (tf * (k1 + 1.0)) / (tf + k1 * (1.0 - b + b * denom))
                    if " " in term:
                        term_score *= 2.5
                    sparse_score += term_score

            chunk_tokens = p_item.all_tokens
            matched_terms_idf = sum(self._idf.get(t, 1.0) for t in query_terms if t in chunk_tokens)
            total_terms_idf = sum(self._idf.get(t, 1.0) for t in query_terms) or 1.0

            matched_subwords_idf = sum(self._idf.get(sw, 0.5) for sw in query_subwords if sw in chunk_tokens)
            total_subwords_idf = sum(self._idf.get(sw, 0.5) for sw in query_subwords) or 1.0

            dense_score = (matched_terms_idf / total_terms_idf * 0.7) + (matched_subwords_idf / total_subwords_idf * 0.3)

            scored_candidates.append((dense_score, sparse_score, chunk))

        dense_sorted = sorted(scored_candidates, key=lambda x: x[0], reverse=True)
        sparse_sorted = sorted(scored_candidates, key=lambda x: x[1], reverse=True)

        dense_rank_map = {item[2].chunk_id: idx + 1 for idx, item in enumerate(dense_sorted)}
        sparse_rank_map = {item[2].chunk_id: idx + 1 for idx, item in enumerate(sparse_sorted)}

        rrf_candidates: list[tuple[float, int, int, CanonicalFullyQualifiedChunk]] = []
        for dense_score, sparse_score, chunk in scored_candidates:
            d_rank = dense_rank_map[chunk.chunk_id]
            s_rank = sparse_rank_map[chunk.chunk_id]
            rrf_score = (1.0 / (60 + d_rank)) + (1.0 / (60 + s_rank))
            rrf_candidates.append((rrf_score, d_rank, s_rank, chunk))

        rrf_candidates.sort(
            key=lambda x: (
                x[0],
                -x[1],
                -x[2],
            ),
            reverse=True,
        )

        matches: list[SearchResultItem] = []
        for rrf_score, d_rank, s_rank, chunk in rrf_candidates[:limit]:
            doc_info = self.documents.get(chunk.document_code, {})
            doc_title = str(doc_info.get("title", chunk.document_code))
            matches.append(
                SearchResultItem.model_validate(
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
                        "verbatim_text": chunk.verbatim_text,
                        "contextualized_text": chunk.contextualized_text,
                        "norm_role": chunk.norm_role.value if hasattr(chunk.norm_role, "value") else str(chunk.norm_role),
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
            )

        return matches

    async def execute_graph_traversal(
        self,
        start_chunk_id: str,
        allowed_edge_types: list[str] | None = None,
        direction: str = "BOTH",
        max_depth: int = 2,
        t_violation: str | datetime.date | None = None,
    ) -> list[TraversalPathItem]:
        t_viol_date_str = None
        if t_violation is not None:
            t_viol_date_str = t_violation.isoformat() if isinstance(t_violation, datetime.date) else str(t_violation).strip()

        results: list[TraversalPathItem] = []
        visited: set[str] = {start_chunk_id}
        queue: list[tuple[str, int, list[str]]] = [(start_chunk_id, 1, [start_chunk_id])]

        while queue:
            curr_id, depth, trail = queue.pop(0)
            if depth > max_depth:
                continue

            for edge in self.graph_edges:
                is_match = False
                next_id: str | None = None

                src_id = str(edge.get("source_chunk_id") or "")
                tgt_id = str(edge.get("target_chunk_id") or "")

                if src_id == curr_id:
                    next_id = tgt_id
                    is_match = True
                elif direction == "BOTH" and tgt_id == curr_id:
                    next_id = src_id
                    is_match = True

                if (
                    is_match
                    and next_id
                    and next_id not in visited
                    and (not allowed_edge_types or edge["relation_type"] in allowed_edge_types)
                ):
                    next_chunk = self.chunks.get(next_id)
                    if next_chunk and t_viol_date_str is not None:
                        if next_chunk.effective_date is not None and t_viol_date_str < next_chunk.effective_date:
                            continue
                        if next_chunk.expiration_date is not None and t_viol_date_str >= next_chunk.expiration_date:
                            continue

                    visited.add(next_id)
                    conf_raw = edge.get("confidence_score")
                    conf_f = float(conf_raw) if isinstance(conf_raw, (int, float, str)) else 1.0
                    results.append(
                        TraversalPathItem.model_validate(
                            {
                                "hop_depth": depth,
                                "edge_id": str(edge.get("edge_id", "")),
                                "relation_type": str(edge.get("relation_type", "")),
                                "source_chunk_id": curr_id,
                                "source_path": str(edge.get("source_path") or curr_id),
                                "target_chunk_id": next_id,
                                "target_path": str(edge.get("target_path") or ""),
                                "target_doc_code": str(edge.get("target_doc_code") or ""),
                                "target_chunk_index": str(edge.get("target_chunk_index") or ""),
                                "target_norm_role": str(edge.get("target_norm_role") or ""),
                                "target_raw_text": str(edge.get("target_contextualized_text") or edge.get("target_raw_text") or ""),
                                "target_contextualized_text": str(edge.get("target_contextualized_text") or ""),
                                "min_fine_vnd": None,
                                "max_fine_vnd": None,
                                "is_conditional": bool(edge.get("is_conditional", False)),
                                "condition_expression": str(edge["condition_expression"]) if edge.get("condition_expression") else None,
                                "confidence_score": conf_f,
                                "traversal_trail": f"{edge.get('source_path', curr_id)} -> [{edge.get('relation_type', '')}] -> {edge.get('target_path', '')}",
                            }
                        )
                    )
                    queue.append((next_id, depth + 1, trail + [next_id]))

        return results
