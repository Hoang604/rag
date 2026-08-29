"""Database connection pool lifecycle management and health check probes.

Provides thread-safe and async-safe asyncpg connection pool initialization,
graceful termination, connection recycling, health probing, and database DSN resolution.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Final

import asyncpg

logger = logging.getLogger(__name__)

DEFAULT_DATABASE_URL: Final[str] = (
    "postgresql://postgres:postgres@localhost:54329/rag_legal"
)

# Global connection pool instance and synchronization lock
_pool: asyncpg.Pool | None = None
_pool_lock: asyncio.Lock = asyncio.Lock()


def resolve_database_url(dsn: str | None = None) -> str:
    """Resolves target database DSN from explicit argument, environment, or default fallback.

    Args:
        dsn: Optional explicit connection string.

    Returns:
        Resolved normalized PostgreSQL connection string.
    """
    if dsn is not None and dsn.strip():
        return dsn.strip()
    env_dsn = os.getenv("DATABASE_URL")
    if env_dsn is not None and env_dsn.strip():
        return env_dsn.strip()
    return DEFAULT_DATABASE_URL


async def get_db_pool(
    dsn: str | None = None,
    min_size: int = 1,
    max_size: int = 10,
    timeout: float = 30.0,
    command_timeout: float = 60.0,
    max_inactive_connection_lifetime: float = 300.0,
) -> asyncpg.Pool:
    """Returns or creates an asynchronous PostgreSQL connection pool using asyncpg.

    Args:
        dsn: Database connection URL (e.g. postgresql://user:pass@host:port/db).
        min_size: Minimum number of connections in the pool.
        max_size: Maximum number of connections in the pool.
        timeout: Timeout in seconds for establishing a connection.
        command_timeout: Default timeout in seconds for executing commands.
        max_inactive_connection_lifetime: Maximum idle time before connection is recycled (default 300s).

    Returns:
        Active asyncpg.Pool instance.

    Raises:
        RuntimeError: If connection pool creation fails.
    """
    global _pool
    if _pool is not None and not _pool._closed:
        return _pool

    async with _pool_lock:
        if _pool is not None and not _pool._closed:
            return _pool

        target_dsn = resolve_database_url(dsn)
        try:
            pool = await asyncpg.create_pool(
                dsn=target_dsn,
                min_size=min_size,
                max_size=max_size,
                timeout=timeout,
                command_timeout=command_timeout,
                max_inactive_connection_lifetime=max_inactive_connection_lifetime,
                max_queries=50000,
                statement_cache_size=1000,
            )
            if pool is None:
                raise RuntimeError("asyncpg.create_pool returned None")
            _pool = pool
            logger.info("Successfully initialized PostgreSQL connection pool at %s", target_dsn)
            return _pool
        except (
            OSError,
            TimeoutError,
            RuntimeError,
            asyncpg.PostgresError,
            asyncpg.InterfaceError,
            asyncpg.CannotConnectNowError,
        ) as exc:
            logger.error("Failed to initialize PostgreSQL pool: %s", exc)
            raise RuntimeError(
                f"Failed to connect to database at {target_dsn}: {exc}"
            ) from exc


async def close_db_pool() -> None:
    """Gracefully closes the global database connection pool and resets references."""
    global _pool
    async with _pool_lock:
        if _pool is not None:
            if not _pool._closed:
                await _pool.close()
            _pool = None
            logger.info("Closed PostgreSQL connection pool.")


async def check_db_health(
    pool: asyncpg.Pool | None = None, dsn: str | None = None
) -> bool:
    """Probes database availability by executing a lightweight ping query.

    Args:
        pool: Optional active connection pool to probe. If None, acquires one via get_db_pool.
        dsn: Optional connection URL if pool needs to be acquired.

    Returns:
        True if database responds successfully to ping, False otherwise.
    """
    try:
        active_pool = pool if pool is not None else await get_db_pool(dsn=dsn)
        async with active_pool.acquire() as conn:
            result = await conn.fetchval("SELECT 1;")
            return result == 1
    except (
        OSError,
        TimeoutError,
        RuntimeError,
        asyncpg.PostgresError,
        asyncpg.InterfaceError,
        asyncpg.CannotConnectNowError,
    ) as exc:
        logger.debug("Database health check ping failed: %s", exc)
        return False
