"""FastAPI application factory, CORS middleware, Lifespan handling, and static SPA mounting."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import asyncpg
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from rag_eval.legal.db.connection import close_db_pool, get_db_pool
from rag_eval.legal.ingestion.staging import DEFAULT_STAGING_DIR, StagingManager
from rag_eval.legal.schemas import LegalDomainError
from rag_eval.legal.web.router import router

logger = logging.getLogger(__name__)


def create_app(
    staging_dir: Path | str = DEFAULT_STAGING_DIR,
    db_pool: asyncpg.Pool | None = None,
    static_dir: Path | str | None = None,
) -> FastAPI:
    """Constructs and configures the Legal Staging Reviewer FastAPI application."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Manages application startup and shutdown lifecycle (database pools, caches)."""
        logger.info("Initializing Legal Staging Reviewer Web Backend...")
        app.state.staging_manager = StagingManager(staging_dir=staging_dir)

        if db_pool is not None:
            app.state.pool = db_pool
        else:
            try:
                app.state.pool = await get_db_pool()
            except (RuntimeError, OSError, asyncpg.PostgresError) as exc:
                logger.warning(
                    "Database pool initialization deferred/offline: %s", exc
                )
                app.state.pool = None

        yield

        logger.info("Shutting down Legal Staging Reviewer Web Backend...")
        if db_pool is None and app.state.pool is not None:
            await close_db_pool()

    app = FastAPI(
        title="Vietnamese Traffic Law Staging Reviewer API",
        description="FastAPI Backend Service for Human-in-the-Loop Legal Staging and Promotion",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.staging_manager = StagingManager(staging_dir=staging_dir)
    app.state.pool = db_pool

    # 1. CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 2. Domain & Error Exception Handlers
    @app.exception_handler(LegalDomainError)
    async def legal_domain_error_handler(
        request: Request, exc: LegalDomainError
    ) -> JSONResponse:
        logger.warning("LegalDomainError handled: %s (code: %d)", exc.message, exc.error_code)
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": exc.error_code,
                    "message": exc.message,
                    "data": exc.data,
                }
            },
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(
        request: Request, exc: ValueError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"error": {"code": -32602, "message": str(exc)}},
        )

    # 3. Mount API Routers (both /api and /api/v1 prefixes)
    app.include_router(router, prefix="/api")
    app.include_router(router, prefix="/api/v1")

    # 4. Mount Frontend SPA Static Assets if present
    target_static = Path(static_dir) if static_dir else Path("frontend/dist")
    if target_static.exists() and target_static.is_dir():
        logger.info("Mounting SPA static files from %s", target_static)
        app.mount("/assets", StaticFiles(directory=target_static / "assets"), name="assets")

        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str) -> Any:
            file_path = target_static / full_path
            if file_path.is_file():
                return FileResponse(file_path)
            index_path = target_static / "index.html"
            if index_path.exists():
                return FileResponse(index_path)
            return JSONResponse(status_code=404, content={"message": "Frontend not found"})

    return app
