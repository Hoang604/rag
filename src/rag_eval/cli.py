"""Command-line interface for downloading datasets and evaluating RAG systems."""

import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal, cast

import typer
from rich.console import Console
from rich.table import Table

from rag_eval.baseline.pipeline import export_predictions, run_baseline_retrieval
from rag_eval.datasets.base import BenchmarkDataset
from rag_eval.datasets.beir_fiqa import download_beir_fiqa, parse_beir_fiqa_from_disk
from rag_eval.datasets.cuad import download_cuad, parse_cuad_from_disk
from rag_eval.datasets.qasper import download_qasper, parse_qasper_from_disk
from rag_eval.datasets.scifact import download_scifact, parse_scifact_from_disk
from rag_eval.metrics import evaluate_predictions
from rag_eval.schemas import PredictionResult

app = typer.Typer(name="rag-eval", help="RAG Benchmark Evaluation Suite")
console = Console()


@app.command()
def download(
    dataset: Annotated[
        str,
        typer.Option(
            "--dataset",
            "-d",
            help="Dataset name: cuad | qasper | scifact | beir_fiqa | all",
        ),
    ],
    output_dir: Annotated[
        str, typer.Option("--output-dir", "-o", help="Root storage directory")
    ] = "./data",
) -> None:
    """Download and normalize raw datasets into ./data/."""
    out_path = Path(output_dir)
    target = dataset.lower().strip()

    downloaders: dict[str, tuple[str, Callable[[], BenchmarkDataset]]] = {
        "cuad": ("CUAD (Legal Contracts)", lambda: download_cuad(out_path)),
        "qasper": ("QASPER (Academic Papers)", lambda: download_qasper(out_path)),
        "scifact": ("SciFact (Scientific IR)", lambda: download_scifact(out_path)),
        "beir_fiqa": ("BEIR/FiQA (Financial IR)", lambda: download_beir_fiqa(out_path)),
    }

    if target == "all":
        targets_to_run = list(downloaders.keys())
    elif target in downloaders:
        targets_to_run = [target]
    else:
        console.print(
            f"[bold red]Error:[/bold red] Unknown dataset '{dataset}'. Choose from: {list(downloaders.keys())} or 'all'"
        )
        raise typer.Exit(code=1)

    for name in targets_to_run:
        label, dl_fn = downloaders[name]
        console.print(
            f"[cyan]Downloading and normalizing [bold]{label}[/bold]...[/cyan]"
        )
        bmark = dl_fn()
        doc_count = len(bmark.documents)
        query_count = len(bmark.queries)
        gt_count = len(bmark.ground_truths)
        dest = str(out_path / name)
        console.print(
            f"[green]✔ Loaded {doc_count} documents, {query_count} queries, {gt_count} qrels -> {dest}[/green]"
        )


@app.command()
def baseline(
    dataset: Annotated[
        str,
        typer.Option(
            "--dataset", "-d", help="Dataset name: cuad | qasper | scifact | beir_fiqa"
        ),
    ],
    output_predictions: Annotated[
        str,
        typer.Option(
            "--output-predictions",
            "-p",
            help="Output path for predictions (.json or .jsonl)",
        ),
    ],
    data_dir: Annotated[
        str, typer.Option("--data-dir", help="Path to cached datasets")
    ] = "./data",
    split: Annotated[
        str, typer.Option("--split", "-s", help="Dataset split: dev | test")
    ] = "dev",
    mode: Annotated[
        str, typer.Option("--mode", "-m", help="Retrieval mode: hybrid | bm25 | dense")
    ] = "hybrid",
    model_name: Annotated[
        str, typer.Option("--model-name", help="Local sentence embedding model")
    ] = "BAAI/bge-small-en-v1.5",
    top_k: Annotated[
        int,
        typer.Option("--top-k", "-k", help="Number of documents to retrieve per query"),
    ] = 10,
    candidate_pool_size: Annotated[
        int,
        typer.Option(
            "--candidate-pool-size",
            help="Number of BM25 candidate passages to re-score",
        ),
    ] = 150,
    chunk_size: Annotated[
        int, typer.Option("--chunk-size", help="Character size per document chunk")
    ] = 512,
    chunk_overlap: Annotated[
        int, typer.Option("--chunk-overlap", help="Character overlap between chunks")
    ] = 64,
    max_queries: Annotated[
        int | None,
        typer.Option(
            "--max-queries",
            "-n",
            help="Optional limit on number of queries to evaluate",
        ),
    ] = None,
    seed: Annotated[
        int | None,
        typer.Option(
            "--seed", help="Optional random seed for representative query sampling"
        ),
    ] = None,
) -> None:
    """Run high-performance baseline retrieval (Two-Stage Hybrid RRF, BM25, or Dense) on a benchmark dataset."""
    d_path = Path(data_dir)
    target = dataset.lower().strip()
    norm_mode = mode.lower().strip()
    if norm_mode not in ("hybrid", "bm25", "dense"):
        console.print(
            f"[bold red]Error:[/bold red] Unknown mode '{mode}'. Choose from: hybrid | bm25 | dense"
        )
        raise typer.Exit(code=1)

    typed_mode: Literal["bm25", "dense", "hybrid"] = (
        "bm25" if norm_mode == "bm25" else "dense" if norm_mode == "dense" else "hybrid"
    )

    loaders: dict[str, tuple[str, Callable[[], BenchmarkDataset]]] = {
        "cuad": ("CUAD", lambda: parse_cuad_from_disk(d_path, split=split)),
        "qasper": ("QASPER", lambda: parse_qasper_from_disk(d_path, split=split)),
        "scifact": ("SciFact", lambda: parse_scifact_from_disk(d_path, split=split)),
        "beir_fiqa": (
            "BEIR/FiQA",
            lambda: parse_beir_fiqa_from_disk(d_path, split=split),
        ),
    }

    if target not in loaders:
        console.print(
            f"[bold red]Error:[/bold red] Unknown dataset '{dataset}'. Choose from: {list(loaders.keys())}"
        )
        raise typer.Exit(code=1)

    label, loader_fn = loaders[target]
    try:
        bmark: BenchmarkDataset = loader_fn()
    except FileNotFoundError as err:
        console.print(
            f"[bold red]Error:[/bold red] Dataset '{target}' not found in '{data_dir}'. Run `rag-eval download -d {target}` first. ({err})"
        )
        raise typer.Exit(code=1) from err

    total_available = len(bmark.queries)
    eval_target_count = (
        min(max_queries, total_available)
        if max_queries is not None
        else total_available
    )
    sample_mode = f" (seeded sample: {seed})" if seed is not None else ""
    console.print(
        f"[cyan]Running [bold]{norm_mode.upper()}[/bold] retrieval on [bold]{label}[/bold] ({len(bmark.documents)} docs, {eval_target_count}/{total_available} queries{sample_mode})...[/cyan]"
    )

    predictions = run_baseline_retrieval(
        documents=bmark.documents,
        queries=bmark.queries,
        top_k=top_k,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        max_queries=max_queries,
        seed=seed,
        mode=typed_mode,
        dense_model_name=model_name,
        candidate_pool_size=candidate_pool_size,
    )

    out_file = Path(output_predictions)
    export_predictions(predictions, out_file)
    console.print(
        f"[green]✔ Generated {len(predictions)} baseline predictions -> {out_file}[/green]"
    )


@app.command()
def evaluate(
    dataset: Annotated[
        str,
        typer.Option(
            "--dataset", "-d", help="Dataset name: cuad | qasper | scifact | beir_fiqa"
        ),
    ],
    predictions: Annotated[
        str,
        typer.Option(
            "--predictions", "-p", help="Path to predictions JSON or JSONL file"
        ),
    ],
    data_dir: Annotated[
        str, typer.Option("--data-dir", help="Path to cached datasets")
    ] = "./data",
    split: Annotated[
        str,
        typer.Option("--split", "-s", help="Evaluation ground truth split: dev | test"),
    ] = "test",
    output_report: Annotated[
        str | None,
        typer.Option(
            "--output-report",
            "-r",
            help="Optional explicit file or directory path to save JSON report. Overrides the default timestamped path.",
        ),
    ] = None,
    output_dir: Annotated[
        str,
        typer.Option(
            "--output-dir", "-o", help="Base directory for default timestamped reports"
        ),
    ] = "./reports",
) -> None:
    """Evaluate a RAG system predictions file against benchmark ground truths."""
    d_path = Path(data_dir)
    pred_path = Path(predictions)

    if not pred_path.is_file():
        console.print(
            f"[bold red]Error:[/bold red] Predictions file not found: {pred_path}"
        )
        raise typer.Exit(code=1)

    loaders: dict[str, tuple[str, Callable[[], BenchmarkDataset]]] = {
        "cuad": ("CUAD", lambda: parse_cuad_from_disk(d_path, split=split)),
        "qasper": ("QASPER", lambda: parse_qasper_from_disk(d_path, split=split)),
        "scifact": ("SciFact", lambda: parse_scifact_from_disk(d_path, split=split)),
        "beir_fiqa": (
            "BEIR/FiQA",
            lambda: parse_beir_fiqa_from_disk(d_path, split=split),
        ),
    }

    target = dataset.lower().strip()
    if target not in loaders:
        console.print(
            f"[bold red]Error:[/bold red] Unknown dataset '{dataset}'. Choose from: {list(loaders.keys())}"
        )
        raise typer.Exit(code=1)

    label, loader_fn = loaders[target]
    try:
        bmark: BenchmarkDataset = loader_fn()
    except FileNotFoundError as err:
        console.print(
            f"[bold red]Error:[/bold red] Dataset '{target}' not found in '{data_dir}'. Run `rag-eval download -d {target}` first. ({err})"
        )
        raise typer.Exit(code=1) from err

    # Parse predictions
    preds: list[PredictionResult] = []
    if pred_path.suffix.lower() == ".jsonl":
        with pred_path.open("r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if s:
                    preds.append(PredictionResult.model_validate_json(s))
    else:
        with pred_path.open("r", encoding="utf-8") as f:
            raw_content = f.read()
            raw_obj = cast(object, json.loads(raw_content))
            if isinstance(raw_obj, list):
                for item in cast(list[object], raw_obj):
                    if isinstance(item, Mapping):
                        preds.append(PredictionResult.model_validate(item))
            elif isinstance(raw_obj, Mapping) and "predictions" in raw_obj:
                pred_list = cast(Mapping[str, object], raw_obj)["predictions"]
                if isinstance(pred_list, list):
                    for item in cast(list[object], pred_list):
                        if isinstance(item, Mapping):
                            preds.append(PredictionResult.model_validate(item))
            else:
                msg = "Predictions JSON must be a list of PredictionResult objects or dict with 'predictions' key."
                console.print(f"[bold red]Error:[/bold red] {msg}")
                raise typer.Exit(code=1)

    report = evaluate_predictions(
        dataset_name=target,
        ground_truths=bmark.ground_truths,
        predictions=preds,
    )

    # Render summary table
    table = Table(title=f"RAG Evaluation Report: {label}")
    table.add_column("Metric Category", style="cyan", justify="left")
    table.add_column("Metric Name", style="magenta", justify="left")
    table.add_column("Score", style="green bold", justify="right")

    for k, v in report.retrieval_metrics.items():
        table.add_row("Retrieval (IR)", k, f"{v:.4f}")

    for k, v in report.generation_metrics.items():
        table.add_row("Generation", k, f"{v:.4f}")

    console.print(table)
    console.print(
        f"[dim]Total Dataset Queries: {report.total_queries} | Evaluated Queries: {report.evaluated_queries}[/dim]\n"
    )

    if output_report is not None:
        out_file = Path(output_report)
        if out_file.is_dir() or output_report.endswith(("/", "\\")):
            out_file = out_file / f"{target}_eval.json"
    else:
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        out_file = Path(output_dir) / timestamp / f"{target}_eval.json"

    out_file.parent.mkdir(parents=True, exist_ok=True)
    with out_file.open("w", encoding="utf-8") as f:
        _ = f.write(report.model_dump_json(indent=2))
    console.print(f"[green]✔ Report saved to {out_file}[/green]")


@app.command(name="legal-migrate")
def legal_migrate() -> None:
    """Run PostgreSQL database DDL migrations."""
    import asyncio

    from rag_eval.legal.db.connection import get_db_pool
    from rag_eval.legal.db.migrations import run_migrations

    async def _migrate() -> list[str]:
        pool = await get_db_pool()
        return await run_migrations(pool)

    console.print("[cyan]Applying legal database schema migrations...[/cyan]")
    applied = asyncio.run(_migrate())
    console.print(
        f"[green]✔ Successfully applied {len(applied)} migration files.[/green]"
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
    doc_type: Annotated[
        str,
        typer.Option(
            "--doc-type",
            help="Document type: LUAT | NGHI_DINH | THONG_TU | QUY_CHUAN_KY_THUAT",
        ),
    ] = "NGHI_DINH",
    persist_db: Annotated[
        bool,
        typer.Option(
            "--persist-db",
            help="Persist parsed chunks and graph edges to PostgreSQL",
        ),
    ] = False,
) -> None:
    """Ingest, parse, chunk (CPHC), and link Vietnamese traffic legal instruments."""
    import asyncio

    from rag_eval.legal.ingestion.pipeline import LegalIngestionPipeline

    console.print(
        f"[cyan]Ingesting statutory document '{doc_code}' from {file_path}...[/cyan]"
    )
    pipeline = LegalIngestionPipeline()
    result = asyncio.run(
        pipeline.ingest_file(
            file_path=Path(file_path),
            doc_code=doc_code,
            doc_title=doc_title,
            doc_type=doc_type,
            persist_db=persist_db,
        )
    )
    console.print(
        f"[green]✔ Ingestion successful: {len(result.hierarchy_nodes)} AST nodes, {len(result.chunks)} CFQC chunks, {len(result.edges)} graph edges.[/green]"
    )


@app.command(name="legal-server")
def legal_server() -> None:
    """Launch the Vietnamese Traffic Law MCP JSON-RPC 2.0 Server over Stdio."""
    import asyncio

    from rag_eval.legal.mcp.server import run_mcp_server

    asyncio.run(run_mcp_server())




@app.command(name="legal-query")
def legal_query(
    query: Annotated[
        str, typer.Argument(help="Natural language Vietnamese traffic law query")
    ],
) -> None:
    """Execute end-to-end multi-hop legal reasoning and scope override evaluation."""
    import asyncio

    from rag_eval.legal.reasoning.pipeline import LegalReasoningPipeline

    console.print(
        f"[cyan]Executing legal reasoning query:[/cyan] [bold]{query}[/bold]\n"
    )
    pipeline = LegalReasoningPipeline()
    result = asyncio.run(pipeline.execute_query(query))

    console.print(
        f"[magenta]Primary Intent:[/magenta] {result['plan'].primary_intent.value}"
    )
    if result["plan"].extracted_entities.vehicle_category:
        console.print(
            f"[magenta]Vehicle Class:[/magenta] {result['plan'].extracted_entities.vehicle_category.value}"
        )

    console.print(
        f"\n[green]Retrieved Citations ({len(result['retrieved_matches'])}):[/green]"
    )
    for idx, match in enumerate(result["retrieved_matches"], start=1):
        lead = match.get("lead_sentence") or match.get("raw_text", "")
        preview = lead[:100] if lead else ""
        console.print(
            f"  {idx}. [bold]{match.get('doc_code')}[/bold] - {match.get('chunk_index')}: {preview}..."
        )

    if result.get("override_ruling"):
        ruling = result["override_ruling"]
        console.print(
            f"\n[yellow]Scope Override Status:[/yellow] {ruling.get('ruling_rationale')}"
        )

    console.print(
        f"\n[cyan]Chain of Custody:[/cyan] Trace ID {result['chain_of_custody'].trace_id} (Grounded: {result['chain_of_custody'].anti_hallucination_audit.is_grounded})"
    )


def main() -> None:
    """CLI entrypoint."""
    app()


if __name__ == "__main__":
    main()
