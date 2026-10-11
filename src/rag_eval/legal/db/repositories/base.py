from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg

from rag_eval.legal.errors import (
    E_AST_GROUNDING_VALIDATION,
    E_STORAGE_CONNECTION,
    LegalDomainError,
)

logger = logging.getLogger(__name__)


class BaseRepository:
    """Base repository encapsulating connection scope, transaction boundaries, and error translation."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @asynccontextmanager
    async def _connection_scope(
        self, conn: asyncpg.Connection | None = None
    ) -> AsyncIterator[asyncpg.Connection]:
        if conn is not None:
            yield conn
        else:
            async with self._pool.acquire() as acquired:
                yield acquired

    def _translate_error(self, operation: str, exc: Exception) -> LegalDomainError:
        logger.error("Database operation '%s' failed: %s", operation, exc)
        if isinstance(exc, (asyncpg.DataError, asyncpg.PostgresSyntaxError)):
            return LegalDomainError(
                error_code=E_AST_GROUNDING_VALIDATION,
                message=f"Database input validation or syntax error in '{operation}': {exc}",
                data={"operation": operation, "original_error": str(exc)},
            )
        return LegalDomainError(
            error_code=E_STORAGE_CONNECTION,
            message=f"Database operation '{operation}' failed: {exc}",
            data={"operation": operation, "original_error": str(exc)},
        )

    @staticmethod
    def _parse_metadata(raw: object) -> dict[str, object]:
        """The jsonb codec decodes a stored object to a dict; anything else is a corrupt row."""
        if not isinstance(raw, dict):
            raise TypeError(f"metadata is a {type(raw).__name__}, expected a JSON object")
        return dict(raw)
