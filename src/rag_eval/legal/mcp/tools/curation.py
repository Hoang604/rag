"""Graph curation tools: the agent adds or removes relation edges on the DB while answering questions.

Every edge must rest on a phrase found in its source chunk, and every change is
appended to `graph_edge_log` with the agent's reason.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Literal

import asyncpg
from pydantic import BaseModel, ConfigDict, Field

from rag_eval.legal.db.connection import get_db_pool
from rag_eval.legal.db.entities import EdgeLogEntity, GraphEdgeEntity
from rag_eval.legal.db.repositories import LegalRepository
from rag_eval.legal.errors import E_INVALID_PARAMS, LegalDomainError
from rag_eval.legal.schemas.domain import StatutoryRelationType
from rag_eval.legal.text import (
    find_normalized_span,
    get_vietnam_now,
    validate_ltree_path,
)


class EdgeKey(BaseModel):
    """Identifies one edge: an edge is unique per (source, target, relation)."""

    model_config = ConfigDict(extra="forbid")

    source_path: str
    target_path: str
    relation_type: StatutoryRelationType


class EdgeProposal(EdgeKey):
    """An edge the agent wants to add; target_path may be a container, fanned out to its leaves."""

    citation_text: str = Field(..., min_length=1)


class CurateEdgesResult(BaseModel):
    """Result of an atomic knowledge graph curation operation."""

    added: list[EdgeKey]
    existing: list[EdgeKey]
    removed: list[EdgeKey]
    not_found: list[EdgeKey]
    message: str


class LegalGraphCurationTools:
    """Writes and removes relation edges on behalf of the agent, each change logged with its reason."""

    def __init__(self, pool: asyncpg.Pool | None = None) -> None:
        self._pool = pool
        self._repo: LegalRepository | None = None

    async def _get_repo(self) -> LegalRepository:
        if self._repo is None:
            self._repo = LegalRepository(self._pool or await get_db_pool())
        return self._repo

    async def graph_curate_edges(
        self,
        reason: str,
        add_edges: Sequence[EdgeProposal] | None = None,
        remove_edges: Sequence[EdgeKey] | None = None,
    ) -> CurateEdgesResult:
        """Atomically applies edge additions and removals within a single transaction."""
        clean_reason = _require_reason(reason)
        clean_adds = list(add_edges) if add_edges else []
        clean_removes = list(remove_edges) if remove_edges else []

        if not clean_adds and not clean_removes:
            raise LegalDomainError(
                error_code=E_INVALID_PARAMS,
                message="Cần ít nhất một cạnh trong add_edges hoặc remove_edges.",
                data={"violation_code": "EMPTY_CURATION_REQUEST"},
            )

        repo = await self._get_repo()
        async with repo.transaction() as conn:
            # 1. Removals
            removed_edges: list[EdgeKey] = []
            not_found_edges: list[EdgeKey] = []
            if clean_removes:
                remove_reqs = [
                    EdgeKey(
                        source_path=validate_ltree_path(e.source_path),
                        target_path=validate_ltree_path(e.target_path),
                        relation_type=e.relation_type,
                    )
                    for e in clean_removes
                ]
                remove_targets = await repo.chunks.expand_to_leaf_paths(
                    [e.target_path for e in remove_reqs], conn
                )
                keys_to_delete: list[tuple[str, str, StatutoryRelationType]] = []
                for req in remove_reqs:
                    leaves = remove_targets.get(req.target_path, [])
                    if leaves:
                        for leaf_path, _ in leaves:
                            keys_to_delete.append((req.source_path, leaf_path, req.relation_type))
                    else:
                        keys_to_delete.append((req.source_path, req.target_path, req.relation_type))

                keys_to_delete = list(dict.fromkeys(keys_to_delete))
                found_for_removal = (
                    await repo.graph.find_edges(keys_to_delete, conn) if keys_to_delete else []
                )
                for row in found_for_removal:
                    await repo.graph.delete_edge(row.edge_id, conn)

                removed_edges = [
                    EdgeKey(
                        source_path=r.source_path,
                        target_path=r.target_path,
                        relation_type=r.relation_type,
                    )
                    for r in found_for_removal
                ]
                if removed_edges:
                    await repo.graph.log_edge_events(
                        [
                            _log("REMOVED", key, row.citation_text, clean_reason)
                            for key, row in zip(removed_edges, found_for_removal, strict=True)
                        ],
                        conn,
                    )

                removed_set = {(r.source_path, r.target_path, r.relation_type) for r in removed_edges}
                for req in remove_reqs:
                    leaves = remove_targets.get(req.target_path, [])
                    leaf_paths = {lp for lp, _ in leaves} if leaves else {req.target_path}
                    if not any((req.source_path, lp, req.relation_type) in removed_set for lp in leaf_paths):
                        not_found_edges.append(req)

            # 2. Additions
            added_edges: list[EdgeKey] = []
            existing_edges: list[EdgeKey] = []
            if clean_adds:
                proposals = [
                    e.model_copy(
                        update={
                            "source_path": validate_ltree_path(e.source_path),
                            "target_path": validate_ltree_path(e.target_path),
                        }
                    )
                    for e in clean_adds
                ]
                sources = await repo.chunks.get_verbatim_by_paths(
                    [e.source_path for e in proposals], conn
                )
                targets = await repo.chunks.expand_to_leaf_paths(
                    [e.target_path for e in proposals], conn
                )
                now = get_vietnam_now()
                violations: list[dict[str, object]] = []
                planned: dict[
                    tuple[uuid.UUID, uuid.UUID, StatutoryRelationType],
                    tuple[EdgeKey, GraphEdgeEntity],
                ] = {}

                for proposal in proposals:
                    source = sources.get(proposal.source_path)
                    leaves = targets[proposal.target_path]
                    if source is None:
                        violations.append(
                            _violation("SOURCE_NOT_FOUND", proposal, "Nguồn không phải một chunk trong DB.")
                        )
                        continue
                    if not leaves:
                        violations.append(
                            _violation("TARGET_NOT_FOUND", proposal, "Không có chunk nào tại hoặc dưới đích.")
                        )
                        continue
                    source_id, source_text = source
                    if find_normalized_span(source_text, proposal.citation_text) is None:
                        violations.append(
                            _violation(
                                "UNGROUNDED_CITATION_TEXT",
                                proposal,
                                "citation_text không có trong verbatim_text của chunk nguồn; chép nguyên văn cụm viện dẫn.",
                            )
                        )
                        continue
                    other_leaves = [(path, cid) for path, cid in leaves if cid != source_id]
                    if not other_leaves:
                        violations.append(
                            _violation("SELF_REFERENCING_EDGE", proposal, "Đích chỉ gồm chính chunk nguồn.")
                        )
                        continue
                    for leaf_path, leaf_id in other_leaves:
                        planned.setdefault(
                            (source_id, leaf_id, proposal.relation_type),
                            (
                                EdgeKey(
                                    source_path=proposal.source_path,
                                    target_path=leaf_path,
                                    relation_type=proposal.relation_type,
                                ),
                                GraphEdgeEntity(
                                    id=uuid.uuid4(),
                                    source_chunk_id=source_id,
                                    target_chunk_id=leaf_id,
                                    relation_type=proposal.relation_type,
                                    citation_text=proposal.citation_text,
                                    created_at=now,
                                ),
                            ),
                        )

                if violations:
                    raise LegalDomainError(
                        error_code=E_INVALID_PARAMS,
                        message=f"{len(violations)} cạnh không hợp lệ; không cạnh nào được ghi.",
                        data={
                            "violation_code": violations[0]["violation_code"],
                            "violations": violations,
                        },
                    )

                key_by_id = {entity.id: key for key, entity in planned.values()}
                inserted = await repo.graph.insert_edges(
                    [entity for _, entity in planned.values()], conn
                )
                await repo.graph.log_edge_events(
                    [_log("ADDED", key_by_id[e.id], e.citation_text, clean_reason) for e in inserted],
                    conn,
                )
                inserted_ids = {e.id for e in inserted}
                added_edges = [key for key, entity in planned.values() if entity.id in inserted_ids]
                existing_edges = [key for key, entity in planned.values() if entity.id not in inserted_ids]

        msg_parts: list[str] = []
        if added_edges or existing_edges:
            msg_parts.append(
                f"Đã thêm {len(added_edges)} cạnh; {len(existing_edges)} cạnh đã có sẵn, giữ nguyên."
            )
        if removed_edges or not_found_edges:
            msg_parts.append(
                f"Đã gỡ {len(removed_edges)} cạnh; {len(not_found_edges)} cạnh không tồn tại."
            )
        return CurateEdgesResult(
            added=added_edges,
            existing=existing_edges,
            removed=removed_edges,
            not_found=not_found_edges,
            message=" ".join(msg_parts) or "Không có cạnh nào được xử lý.",
        )


def _require_reason(reason: str) -> str:
    clean = reason.strip()
    if not clean:
        raise LegalDomainError(
            error_code=E_INVALID_PARAMS,
            message="reason là bắt buộc: ghi câu hỏi đang trả lời hoặc lý do sửa cạnh.",
            data={"violation_code": "MISSING_REASON"},
        )
    return clean


def _violation(code: str, proposal: EdgeProposal, hint: str) -> dict[str, object]:
    return {
        "violation_code": code,
        "source_path": proposal.source_path,
        "target_path": proposal.target_path,
        "message": hint,
    }


def _log(action: Literal["ADDED", "REMOVED"], key: EdgeKey, citation_text: str, reason: str) -> EdgeLogEntity:
    return EdgeLogEntity.record(
        action, "AGENT", key.source_path, key.target_path, key.relation_type, citation_text, reason, get_vietnam_now()
    )
