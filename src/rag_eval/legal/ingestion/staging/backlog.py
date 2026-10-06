from __future__ import annotations

from typing import TYPE_CHECKING

import asyncpg

from rag_eval.legal.ingestion.staging.manager import StagingManager
from rag_eval.legal.schemas.domain import (
    FinalizationState,
    UnresolvedReference,
)
from rag_eval.legal.schemas.staging import (
    UnresolvedBacklogResult,
)

if TYPE_CHECKING:
    from rag_eval.legal.ingestion.staging.session import StagingDocumentSession


class StatutoryBacklogResolver:
    """Unified engine aggregating unfinalized dependencies from staged sessions and PostgreSQL."""

    def __init__(
        self,
        staging_manager: StagingManager | None = None,
        pool: asyncpg.Pool | None = None,
    ) -> None:
        self._staging_manager = staging_manager or StagingManager()
        self._pool = pool

    async def resolve_backlog(
        self,
        doc_code: str | None = None,
        session: StagingDocumentSession | None = None,
        finalization_state: FinalizationState | None = None,
        limit: int = 50,
    ) -> UnresolvedBacklogResult:
        """Aggregates unresolved external references from staged sessions and PostgreSQL."""
        items: list[UnresolvedReference] = []
        seen_keys: set[tuple[str, str | None]] = set()

        # 1. Gather staged external edges from session or all staged sessions on disk
        target_sessions: list[StagingDocumentSession] = []
        if session is not None:
            target_sessions = [session]
        elif doc_code is not None:
            if self._staging_manager.session_exists(doc_code):
                target_sessions = [self._staging_manager.load_session(doc_code)]
        else:
            target_sessions = self._staging_manager.load_all_sessions()

        for s in target_sessions:
            for c in s.chunks:
                for dep in c.dangling_dependencies:
                    key = (c.path, dep.dependency_text)
                    if key not in seen_keys:
                        seen_keys.add(key)
                        if finalization_state and c.finalization_state.value != str(finalization_state):
                            continue
                        items.append(dep)

        # 2. Merge with PostgreSQL context references if pool available
        if self._pool is not None:
            from rag_eval.legal.db.repositories import LegalRepository

            repo = LegalRepository(self._pool)
            fin_state_filter = FinalizationState(finalization_state) if finalization_state else None
            db_items = await repo.context_refs.get_unresolved_backlog(
                doc_code=doc_code or None,
                finalization_state=fin_state_filter,
                limit=limit,
            )
            for db_item in db_items:
                key = (db_item.source_path, db_item.dependency_text)
                if key not in seen_keys:
                    seen_keys.add(key)
                    items.append(db_item)

        total_unresolved = len(items)
        windowed_items = items[:limit]

        return UnresolvedBacklogResult(
            doc_code=doc_code or None,
            total_unresolved=total_unresolved,
            items=windowed_items,
        )
