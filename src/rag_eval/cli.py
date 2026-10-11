from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, cast

import typer
from rich.console import Console
from rich.table import Table

from rag_eval.legal.console import use_utf8_stdout

app = typer.Typer(name="rag-eval", help="Vietnamese Traffic Law Agentic RAG CLI")
console = Console()


@app.command(name="legal-migrate")
def legal_migrate() -> None:
    """Run PostgreSQL database DDL migrations."""
    import asyncio

    from rag_eval.legal.db.connection import close_db_pool, get_db_pool
    from rag_eval.legal.db.migrations import run_migrations

    async def _migrate() -> list[str]:
        try:
            pool = await get_db_pool()
            return await run_migrations(pool)
        finally:
            await close_db_pool()

    console.print("[cyan]Applying legal database schema migrations...[/cyan]")
    applied = asyncio.run(_migrate())
    console.print(
        f"[green]✔ Successfully applied {len(applied)} migration files.[/green]"
    )


@app.command(name="legal-convert")
def legal_convert(
    doc_code: Annotated[
        str | None,
        typer.Option("--doc-code", "-c", help="Convert only this document (e.g. 168/2024/ND-CP)"),
    ] = None,
) -> None:
    """Regenerate each document's canonical text (data/raw/<folder>.txt) from its source folder.

    Every part listed in data/sources/<folder>/meta.json is extracted by the reader for its
    format (Word, PDF) and the blocks go through the single cleaner. Canonical text is never
    edited by hand: fix the extractor or the cleaner and convert again.
    """
    from rag_eval.legal.ingestion.corpus import (
        SOURCES_DIR,
        TEXT_DIR,
        convert,
        read_meta,
    )
    from rag_eval.legal.ingestion.extract import ExtractionGapError, LegacyEncodingError
    from rag_eval.legal.text import sanitize_ltree_label

    folders = sorted(d for d in SOURCES_DIR.iterdir() if (d / "meta.json").exists())
    if doc_code is not None:
        folders = [d for d in folders if sanitize_ltree_label(read_meta(d).doc_code) == sanitize_ltree_label(doc_code)]
        if not folders:
            console.print(f"[red]No source folder for '{doc_code}' in {SOURCES_DIR}.[/red]")
            raise typer.Exit(code=2)
    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    for folder in folders:
        try:
            text = convert(folder)
        except (ExtractionGapError, LegacyEncodingError, RuntimeError) as exc:
            console.print(f"[red]{type(exc).__name__}: {exc}[/red]")
            raise typer.Exit(code=1) from exc
        (TEXT_DIR / f"{folder.name}.txt").write_text(text, encoding="utf-8")
        console.print(f"  {folder.name:26s} {text.count(chr(10)):>6} lines")


@app.command(name="legal-ingest")
def legal_ingest(
    doc_code: Annotated[
        str | None,
        typer.Option("--doc-code", "-c", help="Ingest only this document (e.g. 168/2024/NĐ-CP)"),
    ] = None,
    embed: Annotated[
        bool,
        typer.Option("--embed/--no-embed", help="Compute embeddings for new or changed chunks"),
    ] = True,
) -> None:
    """Parse every corpus document and write its chunks and citation edges straight into PostgreSQL.

    Each document's data/sources/<folder>/meta.json records its title, validity dates and
    what it amends or consolidates; its text is data/raw/<folder>.txt from legal-convert. Re-running replaces each document's chunks, keeps
    every edge whose endpoints and citation text still exist, and adds the
    deterministic citation edges that are missing. A full run lists the documents
    still in the database that are no longer in data/sources; they stay searchable
    until deleted.
    """
    import asyncio

    from rag_eval.legal.db.connection import close_db_pool, get_db_pool
    from rag_eval.legal.db.repositories import LegalRepository
    from rag_eval.legal.errors import LegalDomainError
    from rag_eval.legal.ingestion.corpus import SOURCES_DIR, SourceDocument, load_corpus
    from rag_eval.legal.ingestion.pipeline import IngestReport, ingest_document
    from rag_eval.legal.text import sanitize_ltree_label

    entries = load_corpus()
    if not entries:
        console.print(f"[red]No documents in {SOURCES_DIR}.[/red]")
        raise typer.Exit(code=2)
    if doc_code is not None:
        wanted = sanitize_ltree_label(doc_code)
        entries = [
            e
            for e in entries
            if sanitize_ltree_label(e.doc_code if isinstance(e, SourceDocument) else e[0]) == wanted
        ]
        if not entries:
            console.print(f"[red]No document '{doc_code}' in {SOURCES_DIR}.[/red]")
            raise typer.Exit(code=2)

    async def _ingest() -> tuple[list[IngestReport], list[tuple[str, str]]]:
        reports: list[IngestReport] = []
        failures: list[tuple[str, str]] = []
        try:
            repo = LegalRepository(await get_db_pool())
            for entry in entries:
                if not isinstance(entry, SourceDocument):
                    failures.append((entry[0], str(entry[1])))
                    continue
                try:
                    report = await ingest_document(repo, entry, compute_embeddings=embed)
                except (LegalDomainError, ValueError, RuntimeError) as exc:
                    failures.append((entry.doc_code, f"{type(exc).__name__}: {exc}"))
                    continue
                reports.append(report)
                forms = f" ({report.form_lines} form lines not chunked)" if report.form_lines else ""
                console.print(
                    f"  {report.doc_code:20s} {report.chunk_count:>5} chunks {report.edge_count:>5} edges{forms}"
                )
            if doc_code is None:
                corpus_codes = {e.doc_code if isinstance(e, SourceDocument) else e[0] for e in entries}
                for absent in await repo.documents.list_codes():
                    if absent not in corpus_codes:
                        console.print(
                            f"[yellow]  {absent:20s} is in the database but not in {SOURCES_DIR}; it stays searchable until deleted[/yellow]"
                        )
            if reports:
                await _rebuild_indexes()
        finally:
            await close_db_pool()
        return reports, failures

    reports, failures = asyncio.run(_ingest())
    for failed_code, reason in failures:
        console.print(f"[red]  ✘ {failed_code}: {reason}[/red]")
    invalidated = sum(r.invalidated_edges for r in reports)
    summary = (
        f"✔ Ingested {len(reports)}/{len(entries)} documents: "
        f"{sum(r.chunk_count for r in reports)} chunks, {sum(r.edge_count for r in reports)} edges"
    )
    if invalidated:
        summary += f", {invalidated} edges invalidated"
    console.print(f"[green]{summary}.[/green]")
    if failures:
        raise typer.Exit(code=1)


async def _rebuild_indexes() -> None:
    """Rebuilds the search indexes after a full reload.

    Every ingest upserts each row, and an upsert is a delete plus an
    insert, so the HNSW and GIN indexes accumulate dead entries. Measured on
    the smoke set after four reloads: 240 ms mean latency against 99 ms once
    rebuilt. Parallel maintenance is disabled because the container's default
    64 MB /dev/shm cannot hold the shared segment it asks for.
    """
    from rag_eval.legal.db.connection import get_db_pool
    from rag_eval.legal.db.repositories import LegalRepository

    pool = await get_db_pool()
    repo = LegalRepository(pool)
    try:
        await repo.chunks.reindex_and_vacuum()
    except (OSError, RuntimeError) as exc:
        console.print(f"[yellow]  index rebuild skipped: {exc}[/yellow]")


@app.command(name="legal-eval")
def legal_eval(
    split: Annotated[
        str | None, typer.Option("--split", "-s", help="Only this split (dev or holdout); default both")
    ] = None,
) -> None:
    """Replays every evaluation case's first search call and reports where the expected provision landed.

    Cases live in data/eval/retrieval.jsonl (reviewed and edited on the UI's evaluation tab). Each
    case is scored by the group its expected provision falls in: both (semantic and verbatim),
    semantic only, verbatim only, or missed.
    """
    import asyncio

    from rag_eval.legal.eval.retrieval import load_cases, run_all
    from rag_eval.legal.mcp.tools import LegalMCPTools, SentenceTransformerQueryEmbedder

    cases = [c for c in load_cases() if split is None or c.split == split]
    if not cases:
        console.print(f"[red]No cases for split {split!r}[/red]")
        raise typer.Exit(1)

    async def run() -> None:
        from rag_eval.legal.db.connection import close_db_pool

        try:
            result = await run_all(LegalMCPTools.build(embedding_engine=SentenceTransformerQueryEmbedder()), cases)
        finally:
            await close_db_pool()
        table = Table(title=f"Retrieval evaluation ({len(cases)} cases)")
        for column in ("split", "both", "semantic only", "verbatim only", "missed", "found"):
            table.add_column(column, justify="right")
        for s in result.summaries:
            if s.total:
                found = s.total - s.missed
                table.add_row(
                    s.split, str(s.both), str(s.semantic_only), str(s.verbatim_only), str(s.missed),
                    f"{found}/{s.total} ({found / s.total:.1%})",
                )
        console.print(table)

    asyncio.run(run())


@app.command(name="legal-server")
def legal_server(
    log_file: Annotated[
        str | None,
        typer.Option(
            "--log-file",
            help="Path to write diagnostic log file (defaults to logs/mcp_server.log)",
        ),
    ] = "logs/mcp_server.log",
) -> None:
    """Launch the Vietnamese Traffic Law MCP JSON-RPC 2.0 Server over Stdio."""
    from rag_eval.legal.mcp.server import run_mcp_server

    run_mcp_server(log_file=log_file)


@app.command(name="legal-tool")
def legal_tool(
    tool_name: Annotated[
        str,
        typer.Argument(
            help="Name of the MCP tool to execute (e.g. search, graph_traverse)"
        ),
    ],
    args: Annotated[
        str,
        typer.Option(
            "--args",
            "-a",
            help="JSON string of arguments to pass to the tool",
        ),
    ] = "{}",
    output_file: Annotated[
        str | None,
        typer.Option(
            "--output",
            "-o",
            help="Optional path to write raw JSON result",
        ),
    ] = None,
    raw: Annotated[
        bool,
        typer.Option(
            "--raw/--no-raw",
            "-r",
            help="Output raw JSON-RPC response without extra console styling",
        ),
    ] = True,
) -> None:
    """Direct headless runner for all Vietnamese Traffic Law MCP tools."""
    import asyncio

    from rag_eval.legal.db.connection import close_db_pool
    from rag_eval.legal.mcp.server import LegalMCPServer

    try:
        raw_parsed = json.loads(args.strip() if args else "{}")
        if not isinstance(raw_parsed, dict):
            console.print(
                f"[bold red]Error:[/bold red] Tool arguments must be a JSON object, got {type(raw_parsed).__name__}"
            )
            raise typer.Exit(code=1)
        parsed_args = cast(dict[str, object], raw_parsed)
    except (json.JSONDecodeError, ValueError) as err:
        console.print(f"[bold red]Error parsing JSON arguments:[/bold red] {err}")
        raise typer.Exit(code=1) from err

    async def _execute() -> dict[str, object]:
        try:
            server = LegalMCPServer()
            res = await server.handle_request_dict(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": tool_name.strip(), "arguments": parsed_args},
                }
            )
            return res or {}
        finally:
            await close_db_pool()

    res = asyncio.run(_execute())
    formatted_json = json.dumps(res, indent=2, ensure_ascii=False)
    if output_file:
        out_p = Path(output_file)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(formatted_json, encoding="utf-8")
        if not raw:
            console.print(f"[green]✔ Tool output written to {out_p}[/green]")
    else:
        print(formatted_json)

    if "error" in res:
        raise typer.Exit(code=1)


@app.command(name="api")
def api(
    host: Annotated[
        str,
        typer.Option("--host", "-h", help="Bind host address"),
    ] = "127.0.0.1",
    port: Annotated[
        int,
        typer.Option("--port", "-p", help="Bind port number"),
    ] = 8000,
    reload: Annotated[
        bool,
        typer.Option(
            "--reload/--no-reload",
            help="Enable hot reloading on code changes in src/",
        ),
    ] = True,
) -> None:
    """Launch the FastAPI backend for statutory lookup and answers."""
    import uvicorn

    src_dir = Path(__file__).resolve().parents[1]
    console.print(
        f"[bold green]Starting Legal RAG API at http://{host}:{port}[/bold green]"
    )
    if reload:
        uvicorn.run(
            "rag_eval.legal.web.app:create_app",
            factory=True,
            host=host,
            port=port,
            reload=True,
            reload_dirs=[str(src_dir)],
            log_level="info",
        )
    else:
        from rag_eval.legal.web.app import create_app

        uvicorn_app = create_app()
        uvicorn.run(uvicorn_app, host=host, port=port, log_level="info")


@app.command(name="ui")
def ui(
    host: Annotated[
        str,
        typer.Option("--host", "-h", help="Bind host address"),
    ] = "127.0.0.1",
    port: Annotated[
        int,
        typer.Option("--port", "-p", help="Bind port number"),
    ] = 8000,
    open_browser: Annotated[
        bool,
        typer.Option(
            "--open/--no-open",
            help="Automatically open default web browser upon startup",
        ),
    ] = True,
) -> None:
    """Launch the legal lookup and answer web application."""
    import shutil
    import subprocess
    import threading
    import time
    import webbrowser

    frontend_dir = Path("frontend")
    dist_dir = frontend_dir / "dist"

    npm = shutil.which("npm")
    if npm is None:
        console.print(
            "[bold red]Không tìm thấy `npm` trong PATH.[/bold red] "
            "Cài Node.js, hoặc chạy riêng backend:\n"
            "  uv run rag-eval api"
        )
        raise typer.Exit(code=1)

    if not (dist_dir.exists() and (dist_dir / "index.html").exists()):
        console.print(
            "[cyan]Building frontend SPA assets (dist/ missing)...[/cyan]"
        )
        try:
            subprocess.run([npm, "install"], cwd=str(frontend_dir), check=True)
            subprocess.run([npm, "run", "build"], cwd=str(frontend_dir), check=True)
            console.print(
                "[green]✔ Successfully built frontend SPA bundle into dist/.[/green]"
            )
        except (subprocess.CalledProcessError, FileNotFoundError) as err:
            console.print(f"[bold red]Frontend build failed:[/bold red] {err}")
            raise typer.Exit(code=1) from err

    url = f"http://{host}:{port}"
    console.print(
        f"[bold green]Starting Legal RAG Web Application at {url}[/bold green]"
    )
    if open_browser:

        def _open() -> None:
            time.sleep(1.0)
            webbrowser.open(url)

        threading.Timer(1.0, _open).start()

    import uvicorn

    from rag_eval.legal.web.app import create_app

    uvicorn_app = create_app(static_dir=dist_dir)
    uvicorn.run(uvicorn_app, host=host, port=port, log_level="info")


def main() -> None:
    """CLI entrypoint.

    The encoding fix runs here, before any command does. `legal-migrate`
    prints a "✔" and died with UnicodeEncodeError the moment its output was
    redirected to a file -- the same defect already fixed across `scripts/`,
    missed here because the structural test only scanned that directory.
    """
    use_utf8_stdout()
    app()


if __name__ == "__main__":
    main()
