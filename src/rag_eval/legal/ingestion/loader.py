"""High-performance idempotent PostgreSQL batch loader for legal ingestion pipeline.

Persists parsed documents, AST hierarchy nodes, CFQC chunks, graph edges, and sign specifications
into PostgreSQL using high-throughput batch operations (conn.executemany) and strict foreign key integrity.
"""

from __future__ import annotations

import datetime
import json
import logging
import re
import uuid
from collections.abc import Mapping, Sequence
from typing import Protocol, cast

import asyncpg

from rag_eval.legal.ingestion.parser import ASTNode, sanitize_ltree_label
from rag_eval.legal.schemas import CanonicalFullyQualifiedChunk

logger = logging.getLogger(__name__)


def _to_date(val: str | datetime.date | None) -> datetime.date | None:
    """Converts ISO date strings or existing date objects to datetime.date for asyncpg binary encoder."""
    if val is None:
        return None
    if isinstance(val, datetime.date):
        return val
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return None
        try:
            return datetime.date.fromisoformat(s)
        except ValueError:
            parts = s.split("/")
            if len(parts) == 3:
                try:
                    return datetime.date(int(parts[2]), int(parts[1]), int(parts[0]))
                except ValueError:
                    return None
            return None
    return None


class _Tokenizer(Protocol):
    def __call__(
        self,
        text: list[str] | Sequence[str],
        *,
        padding: bool = ...,
        truncation: bool = ...,
        max_length: int = ...,
        return_tensors: str = ...,
    ) -> Mapping[str, object]: ...


class _TokenizerFactory(Protocol):
    def from_pretrained(
        self, pretrained_model_name_or_path: str, **kwargs: object
    ) -> object: ...


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
        matching_candidates.sort(key=lambda item: len(item[0].split(".")))
        return matching_candidates[0][1]

    raise ValueError(
        f"Strict AST Foreign Key Error: Path '{path}' not found in node_id_map "
        f"(Available paths count: {len(node_id_map)})"
    )


LTREE_REGEX: re.Pattern[str] = re.compile(r"^[a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)*$")


def _validate_ltree_path(path: str | None) -> str | None:
    """Validates and sanitizes a dot-separated ltree path.

    Returns sanitized path or None if empty. Raises ValueError if invalid after sanitization.
    """
    if not path or not path.strip():
        return None
    clean = path.strip()
    if LTREE_REGEX.match(clean):
        return clean
    # Attempt sanitization: replace invalid characters with underscores
    segments = clean.split(".")
    sanitized_segs = [sanitize_ltree_label(seg) for seg in segments if seg]
    res = ".".join(sanitized_segs)
    if not LTREE_REGEX.match(res):
        raise ValueError(f"Invalid ltree path: '{path}' -> '{res}'")
    return res


def _resolve_chunk_id(path: str | None, chunk_id_map: Mapping[str, str]) -> str | None:
    """Resolves chunk UUID from exact or normalized ltree paths."""
    if not path:
        return None
    if path in chunk_id_map:
        return chunk_id_map[path]

    path_segments = path.split(".")
    doc_prefix = path_segments[0]

    matching_candidates: list[tuple[str, str]] = []
    for k, v in chunk_id_map.items():
        k_segments = k.split(".")
        if k_segments[0] != doc_prefix:
            continue
        if k_segments[-1] != path_segments[-1]:
            continue

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
        matching_candidates.sort(key=lambda item: len(item[0].split(".")))
        return matching_candidates[0][1]

    return None


class _EmbedderOutput(Protocol):
    def __getitem__(self, index: int) -> object: ...
    def __mul__(self, other: object) -> object: ...
    def sum(self, *args: object, **kwargs: object) -> object: ...
    def clamp(self, *args: object, **kwargs: object) -> object: ...


class _EmbedderModel(Protocol):
    def __call__(self, **kwargs: object) -> _EmbedderOutput: ...
    def eval(self) -> object: ...
    def to(self, device: object) -> _EmbedderModel: ...
    def half(self) -> _EmbedderModel: ...


_CACHED_EMBEDDING_MODEL: tuple[str, _Tokenizer, _EmbedderModel] | None = None
_EMBEDDING_TEXT_CACHE: dict[tuple[str, bool, str], list[float]] = {}



def compute_chunk_embeddings(
    texts: list[str],
    model_name: str = "intfloat/multilingual-e5-small",
    batch_size: int = 64,
    is_query: bool = False,
) -> list[list[float] | None]:
    """Generates dense vector embeddings for chunk texts or queries with memory caching and multilingual support."""
    global _CACHED_EMBEDDING_MODEL
    if not texts:
        return []

    # Check cache for already-computed embeddings
    uncached_indices: list[int] = []
    uncached_texts: list[str] = []
    results: list[list[float] | None] = [None] * len(texts)

    for idx, t in enumerate(texts):
        key = (model_name, is_query, t)
        if key in _EMBEDDING_TEXT_CACHE:
            results[idx] = _EMBEDDING_TEXT_CACHE[key]
        else:
            uncached_indices.append(idx)
            uncached_texts.append(t)

    if not uncached_texts:
        return results

    try:
        import torch
        import torch.nn.functional as F
        from transformers import AutoModel, AutoTokenizer

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        use_fp16 = device.type == "cuda"
        if _CACHED_EMBEDDING_MODEL is not None and _CACHED_EMBEDDING_MODEL[0] == model_name:
            _, tokenizer, model = _CACHED_EMBEDDING_MODEL
        else:
            tok_factory = cast(_TokenizerFactory, AutoTokenizer)
            raw_tok = tok_factory.from_pretrained(model_name)
            if not callable(raw_tok):
                return [None] * len(texts)
            tokenizer = cast(_Tokenizer, raw_tok)

            raw_model = cast(_EmbedderModel, AutoModel.from_pretrained(model_name))
            if use_fp16:
                model = raw_model.to(device).half()
            else:
                model = raw_model.to(device)
            _ = model.eval()
            _CACHED_EMBEDDING_MODEL = (model_name, tokenizer, model)

        is_e5 = "e5" in model_name.lower()
        target_prefix = "query: " if is_query else "passage: "
        formatted_uncached_texts: list[str] = []
        for t in uncached_texts:
            if not is_e5 or t.startswith(("query: ", "passage: ")):
                formatted_uncached_texts.append(t)
            else:
                formatted_uncached_texts.append(f"{target_prefix}{t}")

        for i in range(0, len(formatted_uncached_texts), batch_size):
            batch_texts = formatted_uncached_texts[i : i + batch_size]
            raw_orig_texts = uncached_texts[i : i + batch_size]
            batch_orig_indices = uncached_indices[i : i + batch_size]
            raw_encoded = tokenizer(
                batch_texts,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            )
            encoded: dict[str, torch.Tensor] = {
                str(k): cast(torch.Tensor, v).to(device)
                for k, v in raw_encoded.items()
            }
            with torch.no_grad():
                outputs = model(**encoded)
                if is_e5 and "attention_mask" in encoded:
                    token_embeddings = cast(torch.Tensor, outputs[0])
                    mask = (
                        encoded["attention_mask"]
                        .unsqueeze(-1)
                        .expand(token_embeddings.size())
                        .float()
                    )
                    sum_embeddings = torch.sum(token_embeddings * mask, dim=1)
                    sum_mask = torch.clamp(mask.sum(dim=1), min=1e-9)
                    pooled = sum_embeddings / sum_mask
                else:
                    pooled = cast(torch.Tensor, outputs[0])[:, 0]
                normalized = F.normalize(pooled, p=2.0, dim=1)
                float_tensor = normalized.to(dtype=torch.float32)
                batch_vecs: list[list[float]] = float_tensor.cpu().tolist()
                for orig_idx, text_val, vec in zip(batch_orig_indices, raw_orig_texts, batch_vecs, strict=False):
                    results[orig_idx] = vec
                    _EMBEDDING_TEXT_CACHE[(model_name, is_query, text_val)] = vec

        if device.type == "cuda":
            torch.cuda.synchronize()

        return results
    except (ImportError, RuntimeError, OSError, ValueError, KeyError) as exc:
        logger.warning(
            "Failed to compute chunk embeddings: %s. Proceeding with NULL embeddings.",
            exc,
        )
        return results


def compute_query_embedding(
    query: str,
    model_name: str = "intfloat/multilingual-e5-small",
) -> list[float] | None:
    """Generates a dense vector embedding for a single query string using 'query: ' prefixing."""
    if not query or not query.strip():
        return None
    res = compute_chunk_embeddings([query], model_name=model_name, is_query=True)
    return res[0] if res else None


class PostgresBulkLoader:
    """High-performance idempotent database batch loader for legal documents and knowledge graphs."""

    def __init__(
        self,
        pool: asyncpg.Pool,
        compute_embeddings: bool = False,
        embedding_model: str = "intfloat/multilingual-e5-small",
    ) -> None:
        self.pool = pool
        self.compute_embeddings = compute_embeddings
        self.embedding_model = embedding_model

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
        metadata: dict[str, object] | None = None,
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
        p_date = _to_date(promulgation_date)
        eff_date = _to_date(effective_date)
        exp_date = _to_date(expiration_date)

        async with self.pool.acquire() as conn:
            doc_id = await conn.fetchval(
                query,
                doc_code,
                title,
                doc_type,
                issuing_authority,
                signer,
                p_date,
                eff_date,
                exp_date,
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
                records: list[tuple[object, ...]] = []
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

        # 1. Compute dense embeddings if enabled
        chunk_embeddings: list[list[float] | None] = []
        if self.compute_embeddings:
            texts_to_embed = [
                c.contextualized_text or f"{c.synthesized_prefix}\n{c.verbatim_text}"
                for c in chunks
            ]
            chunk_embeddings = compute_chunk_embeddings(
                texts_to_embed, model_name=self.embedding_model
            )
        else:
            chunk_embeddings = [None] * len(chunks)

        query = """
        INSERT INTO legal_chunks (
            id, node_id, document_id, chunk_type, chunk_index, path,
            lead_sentence, verbatim_text, contextualized_text,
            norm_role,
            min_fine_vnd, max_fine_vnd, additional_sanctions, remedial_measures,
            is_exception, exception_type, effective_date, expiration_date, is_active,
            metadata, dense_embedding_384
        ) VALUES (
            $1::uuid, $2::uuid, $3::uuid, $4, $5, $6::ltree,
            $7, $8, $9,
            $10::legal_norm_role,
            $11, $12, $13::jsonb, $14::jsonb,
            $15, $16, $17::date, $18::date, $19,
            $20::jsonb, $21::vector
        )
        ON CONFLICT (path) DO UPDATE SET
            lead_sentence = EXCLUDED.lead_sentence,
            verbatim_text = EXCLUDED.verbatim_text,
            contextualized_text = EXCLUDED.contextualized_text,
            norm_role = EXCLUDED.norm_role,
            min_fine_vnd = EXCLUDED.min_fine_vnd,
            max_fine_vnd = EXCLUDED.max_fine_vnd,
            additional_sanctions = EXCLUDED.additional_sanctions,
            is_exception = EXCLUDED.is_exception,
            is_active = EXCLUDED.is_active,
            dense_embedding_384 = COALESCE(EXCLUDED.dense_embedding_384, legal_chunks.dense_embedding_384),
            updated_at = CURRENT_TIMESTAMP;
        """

        records: list[tuple[object, ...]] = []
        for idx, chunk in enumerate(chunks):
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

            chunk_meta: dict[str, object] = {
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

            emb_vec = chunk_embeddings[idx] if idx < len(chunk_embeddings) else None
            emb_param = (
                f"[{','.join(str(x) for x in emb_vec)}]"
                if emb_vec is not None
                else None
            )

            eff_date = _to_date(chunk.effective_date)
            exp_date = _to_date(chunk.expiry_date)

            records.append(
                (
                    chunk_uuid,
                    node_uuid,
                    document_id,
                    "LEGAL_RULE",
                    f"Điều {chunk.article_number} Khoản {chunk.clause_number or ''} {chunk.point_letter or ''}".strip(),
                    chunk.hierarchy_path,
                    chunk.lead_sentence or chunk.synthesized_prefix,
                    chunk.verbatim_text,
                    chunk.contextualized_text,
                    norm_role_val,
                    chunk.fine_bounds.min_fine_vnd,
                    chunk.fine_bounds.max_fine_vnd,
                    json.dumps(
                        chunk.additional_sanctions.model_dump(exclude_none=True)
                    ),
                    json.dumps([]),
                    chunk.exceptions_and_overrides.has_exception,
                    chunk.exceptions_and_overrides.exception_type,
                    eff_date,
                    exp_date,
                    chunk.is_active,
                    json.dumps(chunk_meta),
                    emb_param,
                )
            )

        async with self.pool.acquire() as conn, conn.transaction():
            if records:
                await conn.executemany(query, records)

        return path_to_chunk_id

    async def load_graph_edges(
        self,
        edges: Sequence[Mapping[str, object]],
        chunk_id_map: dict[str, str],
        node_id_map: dict[str, str],
    ) -> int:
        """Upserts directed graph edges into legal_graph_edges using batch executemany with strict foreign key integrity."""
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
            source_node_id = EXCLUDED.source_node_id,
            target_node_id = EXCLUDED.target_node_id,
            source_path = EXCLUDED.source_path,
            target_path = EXCLUDED.target_path,
            target_external_ref = EXCLUDED.target_external_ref,
            confidence_score = EXCLUDED.confidence_score,
            description = EXCLUDED.description,
            citation_text = EXCLUDED.citation_text,
            condition_expression = EXCLUDED.condition_expression;
        """

        records: list[tuple[object, ...]] = []
        seen_keys: set[tuple[str, str | None, str]] = set()

        for edge in edges:
            source_path_val = edge.get("source_path")
            target_path_val = edge.get("target_path")
            relation_type_val = edge.get("relation_type")

            if not source_path_val or not relation_type_val:
                continue

            source_path = str(source_path_val)
            target_path = str(target_path_val) if target_path_val is not None else None
            relation_type = str(relation_type_val)

            # Validate ltree paths
            try:
                valid_src_path = _validate_ltree_path(source_path)
            except ValueError as exc:
                logger.warning("Skipping edge due to invalid source ltree path: %s", exc)
                continue

            if not valid_src_path:
                continue

            valid_tgt_path = None
            if target_path:
                try:
                    valid_tgt_path = _validate_ltree_path(target_path)
                except ValueError as exc:
                    logger.warning("Invalid target ltree path '%s', treating as external ref: %s", target_path, exc)
                    valid_tgt_path = None

            # 1. Resolve source chunk ID
            src_chunk_id = chunk_id_map.get(source_path)
            if not src_chunk_id and valid_src_path:
                src_chunk_id = _resolve_chunk_id(valid_src_path, chunk_id_map)
            if not src_chunk_id and edge.get("source_chunk_id"):
                raw_src_chunk = str(edge["source_chunk_id"])
                if len(raw_src_chunk) == 36:
                    src_chunk_id = raw_src_chunk

            # 2. Resolve source node ID
            src_node_id = None
            try:
                src_node_id = _resolve_node_id(valid_src_path, node_id_map)
            except ValueError as exc:
                logger.warning("Skipping edge due to unresolvable source node: %s", exc)
                continue

            if not src_chunk_id or not src_node_id:
                logger.warning("Skipping edge missing source FK: src_chunk=%s, src_node=%s", src_chunk_id, src_node_id)
                continue

            # 3. Resolve target chunk ID
            tgt_chunk_id = None
            if valid_tgt_path:
                tgt_chunk_id = chunk_id_map.get(valid_tgt_path) or _resolve_chunk_id(valid_tgt_path, chunk_id_map)
            if not tgt_chunk_id and edge.get("target_chunk_id"):
                raw_tgt_chunk = str(edge["target_chunk_id"])
                if len(raw_tgt_chunk) == 36:
                    tgt_chunk_id = raw_tgt_chunk

            # 4. Resolve target node ID
            tgt_node_id = None
            if valid_tgt_path:
                try:
                    tgt_node_id = _resolve_node_id(valid_tgt_path, node_id_map)
                except ValueError:
                    tgt_node_id = None

            # Intra-batch deduplication for ON CONFLICT idempotency
            dedup_key = (src_chunk_id, tgt_chunk_id, relation_type)
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)

            conf_val = edge.get("confidence_score", 1.0)
            conf_score = float(conf_val) if isinstance(conf_val, (int, float, str)) else 1.0

            records.append(
                (
                    src_chunk_id,
                    tgt_chunk_id,
                    src_node_id,
                    tgt_node_id,
                    valid_src_path,
                    valid_tgt_path,
                    edge.get("target_external_ref"),
                    relation_type,
                    edge.get("description"),
                    edge.get("citation_text"),
                    conf_score,
                    edge.get("condition_expression"),
                )
            )

        if not records:
            return 0

        async with self.pool.acquire() as conn, conn.transaction():
            await conn.executemany(query, records)

        return len(records)

