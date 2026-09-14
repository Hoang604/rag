"""Command-line interface for Vietnamese Traffic Law Agent-First RAG Platform."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, cast

import typer
from rich.console import Console

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
    dev: Annotated[
        bool,
        typer.Option(
            "--dev",
            help="Run in development mode with concurrent Vite HMR frontend server",
        ),
    ] = False,
    open_browser: Annotated[
        bool,
        typer.Option(
            "--open/--no-open",
            help="Automatically open default web browser upon startup",
        ),
    ] = True,
) -> None:
    """Launch the Human-in-the-Loop Legal Staging Reviewer Web Application."""
    import subprocess
    import sys
    import threading
    import time
    import webbrowser

    frontend_dir = Path("frontend")
    dist_dir = frontend_dir / "dist"

    if not dev:
        if not (dist_dir.exists() and (dist_dir / "index.html").exists()):
            console.print("[cyan]Building frontend SPA assets (dist/ missing)...[/cyan]")
            try:
                subprocess.run(["npm", "install"], cwd=str(frontend_dir), check=True)
                subprocess.run(["npm", "run", "build"], cwd=str(frontend_dir), check=True)
                console.print(
                    "[green]✔ Successfully built frontend SPA bundle into dist/.[/green]"
                )
            except (subprocess.CalledProcessError, FileNotFoundError) as err:
                console.print(f"[bold red]Frontend build failed:[/bold red] {err}")
                raise typer.Exit(code=1) from err

        url = f"http://{host}:{port}"
        console.print(
            f"[bold green]Starting Legal Reviewer Web Application at {url}[/bold green]"
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
    else:
        console.print(
            "[cyan]Starting development servers (FastAPI backend + Vite HMR)...[/cyan]"
        )
        backend_proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "rag_eval.legal.web.app:create_app",
                "--factory",
                "--host",
                host,
                "--port",
                str(port),
                "--reload",
            ]
        )
        vite_proc = subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=str(frontend_dir),
        )

        if open_browser:

            def _open_dev() -> None:
                time.sleep(2.0)
                webbrowser.open("http://127.0.0.1:5173")

            threading.Timer(2.0, _open_dev).start()

        try:
            backend_proc.wait()
        except KeyboardInterrupt:
            console.print("\n[yellow]Shutting down development servers...[/yellow]")
        finally:
            backend_proc.terminate()
            vite_proc.terminate()
            backend_proc.wait()
            vite_proc.wait()


def main() -> None:
    """CLI entrypoint."""
    app()


if __name__ == "__main__":
    main()

