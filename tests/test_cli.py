"""Unit tests for Typer CLI commands including timestamped evaluation reporting."""

from pathlib import Path

from typer.testing import CliRunner

from rag_eval.cli import app
from rag_eval.datasets.base import BenchmarkDataset
from rag_eval.schemas import (
    Document,
    EvaluationReport,
    GroundTruth,
    PredictionResult,
    Query,
)

runner = CliRunner()


def test_cli_evaluate_default_timestamped_report(tmp_path: Path) -> None:
    """Evaluate command saves into timestamped subfolder by default when output-report is omitted."""
    data_dir = tmp_path / "data"
    dataset_dir = data_dir / "scifact"
    bmark = BenchmarkDataset(
        name="scifact",
        description="SciFact benchmark",
        documents=[Document(id="doc_1", text="Sample text", title="Sample Title")],
        queries=[Query(id="q_1", text="Sample query")],
        ground_truths=[GroundTruth(query_id="q_1", relevant_doc_ids=["doc_1"])],
    )
    bmark.export_to_jsonl(dataset_dir)

    pred_file = tmp_path / "preds.jsonl"
    pred = PredictionResult(query_id="q_1", retrieved_doc_ids=["doc_1"])
    with pred_file.open("w", encoding="utf-8") as f:
        _ = f.write(pred.model_dump_json() + "\n")

    reports_base = tmp_path / "reports"

    result = runner.invoke(
        app,
        [
            "evaluate",
            "--dataset",
            "scifact",
            "--predictions",
            str(pred_file),
            "--data-dir",
            str(data_dir),
            "--output-dir",
            str(reports_base),
        ],
    )
    assert result.exit_code == 0
    assert "Report saved to" in result.stdout

    timestamp_dirs = [p for p in reports_base.iterdir() if p.is_dir()]
    assert len(timestamp_dirs) == 1

    report_file = timestamp_dirs[0] / "scifact_eval.json"
    assert report_file.is_file()

    report_data = EvaluationReport.model_validate_json(report_file.read_text(encoding="utf-8"))
    assert report_data.dataset_name == "scifact"
    assert report_data.total_queries == 1


def test_cli_evaluate_explicit_override_file(tmp_path: Path) -> None:
    """Evaluate command writes directly to specified file when output-report is provided."""
    data_dir = tmp_path / "data"
    dataset_dir = data_dir / "scifact"
    bmark = BenchmarkDataset(
        name="scifact",
        description="SciFact benchmark",
        documents=[Document(id="doc_1", text="Sample text", title="Sample Title")],
        queries=[Query(id="q_1", text="Sample query")],
        ground_truths=[GroundTruth(query_id="q_1", relevant_doc_ids=["doc_1"])],
    )
    bmark.export_to_jsonl(dataset_dir)

    pred_file = tmp_path / "preds.jsonl"
    pred = PredictionResult(query_id="q_1", retrieved_doc_ids=["doc_1"])
    with pred_file.open("w", encoding="utf-8") as f:
        _ = f.write(pred.model_dump_json() + "\n")

    explicit_report = tmp_path / "custom_location" / "custom_eval.json"

    result = runner.invoke(
        app,
        [
            "evaluate",
            "--dataset",
            "scifact",
            "--predictions",
            str(pred_file),
            "--data-dir",
            str(data_dir),
            "--output-report",
            str(explicit_report),
        ],
    )
    assert result.exit_code == 0
    assert explicit_report.is_file()


def test_cli_evaluate_explicit_override_directory(tmp_path: Path) -> None:
    """Evaluate command writes dataset_eval.json inside specified directory when output-report is a dir."""
    data_dir = tmp_path / "data"
    dataset_dir = data_dir / "scifact"
    bmark = BenchmarkDataset(
        name="scifact",
        description="SciFact benchmark",
        documents=[Document(id="doc_1", text="Sample text", title="Sample Title")],
        queries=[Query(id="q_1", text="Sample query")],
        ground_truths=[GroundTruth(query_id="q_1", relevant_doc_ids=["doc_1"])],
    )
    bmark.export_to_jsonl(dataset_dir)

    pred_file = tmp_path / "preds.jsonl"
    pred = PredictionResult(query_id="q_1", retrieved_doc_ids=["doc_1"])
    with pred_file.open("w", encoding="utf-8") as f:
        _ = f.write(pred.model_dump_json() + "\n")

    custom_dir = tmp_path / "my_custom_reports"
    custom_dir.mkdir(parents=True, exist_ok=True)

    result = runner.invoke(
        app,
        [
            "evaluate",
            "--dataset",
            "scifact",
            "--predictions",
            str(pred_file),
            "--data-dir",
            str(data_dir),
            "--split",
            "dev",
            "--output-report",
            str(custom_dir),
        ],
    )
    assert result.exit_code == 0
    assert (custom_dir / "scifact_eval.json").is_file()


def test_cli_evaluate_sealed_vault_split(tmp_path: Path) -> None:
    """Evaluate command successfully loads and evaluates against sealed holdout vault."""
    data_dir = tmp_path / "data"
    bmark = BenchmarkDataset(
        name="scifact",
        description="SciFact benchmark",
        documents=[Document(id="doc_1", text="Sample text", title="Sample Title")],
        queries=[Query(id="q_1", text="Sample query"), Query(id="q_2", text="Sample query 2")],
        ground_truths=[
            GroundTruth(query_id="q_1", relevant_doc_ids=["doc_1"]),
            GroundTruth(query_id="q_2", relevant_doc_ids=["doc_1"]),
        ],
    )
    _ = bmark.partition_and_export(data_dir, dev_ratio=0.5, seed=42)

    pred_file = tmp_path / "preds.jsonl"
    pred = PredictionResult(query_id="q_1", retrieved_doc_ids=["doc_1"])
    with pred_file.open("w", encoding="utf-8") as f:
        _ = f.write(pred.model_dump_json() + "\n")

    report_file = tmp_path / "vault_report.json"
    result = runner.invoke(
        app,
        [
            "evaluate",
            "--dataset",
            "scifact",
            "--predictions",
            str(pred_file),
            "--data-dir",
            str(data_dir),
            "--split",
            "test",
            "--output-report",
            str(report_file),
        ],
    )
    assert result.exit_code == 0
    assert report_file.is_file()
