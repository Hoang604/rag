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


class AddEdgesResult(BaseModel):
    added: list[EdgeKey]
    existing: list[EdgeKey]
    message: str


class RemoveEdgesResult(BaseModel):
    removed: list[EdgeKey]
    not_found: list[EdgeKey]
    message: str


class LegalGraphCurationTools:
    """Writes relation edges on behalf of the agent, each change logged with its reason."""

    def __init__(self, pool: asyncpg.Pool | None = None) -> None:
        self._pool = pool
        self._repo: LegalRepository | None = None

    async def _get_repo(self) -> LegalRepository:
        if self._repo is None:
            self._repo = LegalRepository(self._pool or await get_db_pool())
        return self._repo

    async def graph_add_edges(self, edges: Sequence[EdgeProposal], reason: str) -> AddEdgesResult:
        """Validates all proposals first, then inserts them in one transaction with one ADDED log row per new edge.

        Raises LegalDomainError with data.violation_code SOURCE_NOT_FOUND,
        TARGET_NOT_FOUND, SELF_REFERENCING_EDGE or UNGROUNDED_CITATION_TEXT;
        nothing is written when any proposal is invalid. An existing edge is
        reported in `existing` and left unchanged.
        """
        clean_reason = _require_reason(reason)
        proposals = [
            e.model_copy(
                update={
                    "source_path": validate_ltree_path(e.source_path),
                    "target_path": validate_ltree_path(e.target_path),
                }
            )
            for e in edges
        ]
        repo = await self._get_repo()
        async with repo.transaction() as conn:
            # Reads, validation and writes share one transaction, so a concurrent
            # re-ingest cannot unground an edge between its check and its insert.
            sources = await repo.chunks.get_verbatim_by_paths([e.source_path for e in proposals], conn)
            targets = await repo.chunks.expand_to_leaf_paths([e.target_path for e in proposals], conn)
            now = get_vietnam_now()
            violations: list[dict[str, object]] = []
            planned: dict[tuple[uuid.UUID, uuid.UUID, StatutoryRelationType], tuple[EdgeKey, GraphEdgeEntity]] = {}
            for proposal in proposals:
                source = sources.get(proposal.source_path)
                leaves = targets[proposal.target_path]
                if source is None:
                    violations.append(_violation("SOURCE_NOT_FOUND", proposal, "Nguồn không phải một chunk trong DB."))
                    continue
                if not leaves:
                    violations.append(_violation("TARGET_NOT_FOUND", proposal, "Không có chunk nào tại hoặc dưới đích."))
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
                    violations.append(_violation("SELF_REFERENCING_EDGE", proposal, "Đích chỉ gồm chính chunk nguồn."))
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
                    data={"violation_code": violations[0]["violation_code"], "violations": violations},
                )

            key_by_id = {entity.id: key for key, entity in planned.values()}
            inserted = await repo.graph.insert_edges([entity for _, entity in planned.values()], conn)
            await repo.graph.log_edge_events(
                [_log("ADDED", key_by_id[e.id], e.citation_text, clean_reason) for e in inserted],
                conn,
            )
        inserted_ids = {e.id for e in inserted}
        added = [key for key, entity in planned.values() if entity.id in inserted_ids]
        existing = [key for key, entity in planned.values() if entity.id not in inserted_ids]
        return AddEdgesResult(
            added=added,
            existing=existing,
            message=f"Đã thêm {len(added)} cạnh; {len(existing)} cạnh đã có sẵn, giữ nguyên.",
        )

    async def graph_remove_edges(self, edges: Sequence[EdgeKey], reason: str) -> RemoveEdgesResult:
        """Deletes the matching edges, whoever created them, with one REMOVED log row each.

        An edge created by ingest comes back on the next ingest; a wrong edge
        that keeps coming back points to a defect in the citation rules.
        """
        clean_reason = _require_reason(reason)
        keys = list(
            dict.fromkeys(
                (validate_ltree_path(e.source_path), validate_ltree_path(e.target_path), e.relation_type) for e in edges
            )
        )
        repo = await self._get_repo()
        async with repo.transaction() as conn:
            found = await repo.graph.find_edges(keys, conn)
            for row in found:
                await repo.graph.delete_edge(row.edge_id, conn)
            removed = [
                EdgeKey(source_path=r.source_path, target_path=r.target_path, relation_type=r.relation_type)
                for r in found
            ]
            await repo.graph.log_edge_events(
                [_log("REMOVED", key, row.citation_text, clean_reason) for key, row in zip(removed, found, strict=True)],
                conn,
            )
        found_keys = {(k.source_path, k.target_path, k.relation_type) for k in removed}
        not_found = [
            EdgeKey(source_path=s, target_path=t, relation_type=r) for s, t, r in keys if (s, t, r) not in found_keys
        ]
        return RemoveEdgesResult(
            removed=removed,
            not_found=not_found,
            message=f"Đã gỡ {len(removed)} cạnh; {len(not_found)} cạnh không tồn tại.",
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
