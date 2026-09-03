"""Command-line interface for Vietnamese Traffic Law Agent-First RAG Platform."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Annotated, cast

import typer
from rich.console import Console

from rag_eval.legal.schemas import get_vietnam_today, parse_flexible_date

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


@app.command(name="legal-stage")
def legal_stage(
    file_path: Annotated[
        str, typer.Option("--file", "-f", help="Path to legal document text file")
    ],
    doc_code: Annotated[
        str,
        typer.Option(
            "--doc-code",
            "-c",
            help="Statutory document code (e.g. 100/2019/NĐ-CP)",
        ),
    ],
    doc_title: Annotated[
        str | None,
        typer.Option("--doc-title", "-t", help="Official document title"),
    ] = None,
    effective_date: Annotated[
        str | None,
        typer.Option("--effective-date", "-e", help="Effective date YYYY-MM-DD"),
    ] = None,
    amends: Annotated[
        str | None,
        typer.Option(
            "--amends",
            "-a",
            help=(
                "Doc code this document amends. An amending decree's "
                "unqualified citations target the amended document, so "
                "without this they resolve against itself."
            ),
        ),
    ] = None,
    consolidates: Annotated[
        list[str] | None,
        typer.Option(
            "--consolidates",
            help=(
                "Doc code this document is the consolidated text of. "
                "Citations naming the base law resolve into this document."
            ),
        ),
    ] = None,
) -> None:
    """Pre-parse and stage raw statutory text into Staging Area (.cache/stg)."""
    from rag_eval.legal.ingestion.converter import load_legal_document
    from rag_eval.legal.ingestion.staging import StagingManager

    raw_text = load_legal_document(Path(file_path))
    title = doc_title or doc_code
    eff_d = (
        parse_flexible_date(effective_date)
        if effective_date
        else get_vietnam_today()
    )
    assert eff_d is not None

    mgr = StagingManager()
    session = mgr.create_session_from_raw(
        doc_code=doc_code,
        title=title,
        raw_text=raw_text,
        effective_date=eff_d,
        metadata={
            k: v
            for k, v in (("amends", amends), ("consolidates", consolidates))
            if v
        }
        or None,
    )
    resolved = sum(1 for e in session.edges if e.target_path is not None)
    console.print(
        f"[green]✔ Staged '{doc_code}': {len(session.chunks)} chunks, "
        f"{len(session.edges)} cross-reference edges "
        f"({resolved} resolved in-document) into .cache/stg.[/green]"
    )


@app.command(name="legal-bootstrap")
def legal_bootstrap(
    corpus_dir: Annotated[
        str,
        typer.Option("--corpus-dir", "-d", help="Directory of fetched corpus text"),
    ] = "data/raw",
) -> None:
    """Stage every fetched document, then link edges across them.

    Each document's `.meta.json` already records what it amends and which base
    law it consolidates, and both change how citations resolve: an amending
    decree's unqualified references target the amended document, and a
    consolidated text has to answer to the base law's code. Staging by hand
    means restating those per document on every parser change, and getting one
    wrong attributes a run of edges to the wrong statute without any error.
    """
    from rag_eval.legal.ingestion.converter import load_legal_document
    from rag_eval.legal.ingestion.staging import StagingManager

    directory = Path(corpus_dir)
    metas = sorted(directory.glob("*.meta.json"))
    if not metas:
        console.print(
            f"[red]No documents in {directory}. "
            f"Run: uv run python scripts/fetch_corpus.py[/red]"
        )
        raise typer.Exit(code=2)

    manager = StagingManager()
    staged = 0
    failures: list[tuple[str, str]] = []

    for meta_path in metas:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        doc_code = str(meta["doc_code"])
        text_path = meta_path.with_suffix("").with_suffix(".txt")
        if not text_path.exists():
            failures.append((doc_code, f"missing text file {text_path.name}"))
            continue

        metadata = {
            key: value
            for key, value in (
                ("amends", meta.get("amends")),
                ("consolidates", meta.get("consolidates")),
                ("in_force", meta.get("in_force")),
                ("superseded_by", meta.get("superseded_by")),
                ("source_urls", meta.get("source_urls")),
            )
            if value
        }
        effective = parse_flexible_date(meta["effective_date"])
        assert effective is not None
        try:
            session = manager.create_session_from_raw(
                doc_code=doc_code,
                title=str(meta.get("title") or doc_code),
                raw_text=load_legal_document(text_path),
                effective_date=effective,
                metadata=metadata or None,
            )
        except Exception as exc:  # noqa: BLE001 - reported per document below
            failures.append((doc_code, f"{type(exc).__name__}: {exc}"))
            continue

        staged += 1
        console.print(
            f"  {doc_code:20s} {len(session.chunks):>5} chunks "
            f"{len(session.edges):>5} edges"
        )

    resolved = manager.resolve_cross_document_edges()
    linked = sum(resolved.values())

    for doc_code, reason in failures:
        console.print(f"[red]  ✘ {doc_code}: {reason}[/red]")
    console.print(
        f"[green]✔ Staged {staged}/{len(metas)} documents, "
        f"linked {linked} cross-document edges.[/green]"
    )
    if failures:
        raise typer.Exit(code=1)


@app.command(name="legal-link")
def legal_link() -> None:
    """Link staged edges that cite another staged document to its chunks.

    Run after every document is staged: extraction is per-document, so a
    citation out of the document can only be recorded as text until the
    document it names is also present.
    """
    from rag_eval.legal.ingestion.staging import StagingManager

    resolved = StagingManager().resolve_cross_document_edges()
    total = sum(resolved.values())
    for doc_code, count in sorted(resolved.items(), key=lambda kv: -kv[1]):
        if count:
            console.print(f"  {doc_code}: {count} edges linked across documents")
    console.print(
        f"[green]✔ Linked {total} cross-document edges "
        f"across {len(resolved)} staged documents.[/green]"
    )


@app.command(name="legal-ingest")
def legal_ingest(
    file_path: Annotated[
        str, typer.Option("--file", "-f", help="Path to legal document text file")
    ],
    doc_code: Annotated[
        str,
        typer.Option(
            "--doc-code",
            "-c",
            help="Statutory document code (e.g. 100/2019/NĐ-CP)",
        ),
    ],
    doc_title: Annotated[
        str | None,
        typer.Option("--doc-title", "-t", help="Official document title"),
    ] = None,
    effective_date: Annotated[
        str | None,
        typer.Option("--effective-date", "-e", help="Effective date YYYY-MM-DD"),
    ] = None,
    persist_db: Annotated[
        bool,
        typer.Option(
            "--persist-db",
            help="Persist parsed chunks to PostgreSQL",
        ),
    ] = False,
    embed: Annotated[
        bool,
        typer.Option(
            "--embed/--no-embed",
            help="Compute and persist dense vector embeddings (384-dim)",
        ),
    ] = True,
) -> None:
    """Ingest, parse, and chunk (CPHC) statutory legal instruments into the 3-table database."""
    import asyncio

    from rag_eval.legal.ingestion.converter import load_legal_document
    from rag_eval.legal.ingestion.pipeline import LegalIngestionPipeline

    async def _ingest() -> None:
        raw_text = load_legal_document(Path(file_path))
        title = doc_title or doc_code
        eff_d = (
            parse_flexible_date(effective_date)
            if effective_date
            else get_vietnam_today()
        )
        assert eff_d is not None

        pool = None
        if persist_db:
            from rag_eval.legal.db.connection import close_db_pool, get_db_pool

            pool = await get_db_pool()

        try:
            if pool is not None:
                pipeline = LegalIngestionPipeline(pool=pool, compute_embeddings=embed)
                doc_id, chunks = await pipeline.ingest_document(
                    doc_code=doc_code,
                    title=title,
                    raw_text=raw_text,
                    effective_date=eff_d,
                )
                console.print(
                    f"[green]✔ Ingested and persisted document '{doc_code}' ({doc_id}) with {len(chunks)} chunks.[/green]"
                )
            else:
                from rag_eval.legal.ingestion.cphc import CPHCEngine
                from rag_eval.legal.ingestion.parser import LegalASTParser

                parser = LegalASTParser(doc_code=doc_code)
                root = parser.parse(raw_text, doc_title=title)
                cphc = CPHCEngine(
                    document_id=uuid.uuid4(),
                    doc_code=doc_code,
                    doc_title=title,
                    effective_date=eff_d,
                )
                chunks = cphc.chunk_ast(root)
                console.print(
                    f"[green]✔ Ingested (in-memory) document '{doc_code}' with {len(chunks)} atomic chunks.[/green]"
                )
        finally:
            if persist_db:
                from rag_eval.legal.db.connection import close_db_pool

                await close_db_pool()

    console.print(
        f"[cyan]Ingesting statutory document '{doc_code}' from {file_path}...[/cyan]"
    )
    asyncio.run(_ingest())


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
            help="Name of the MCP tool to execute (e.g. mcp_traffic_hybrid_search, stg_preview, stg_commit)"
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


def main() -> None:
    """CLI entrypoint."""
    app()


if __name__ == "__main__":
    main()
