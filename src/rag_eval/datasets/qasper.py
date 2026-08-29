"""QASPER academic research paper dataset parser and normalizer."""

from collections.abc import Callable
from pathlib import Path
from typing import cast

import datasets

from rag_eval.datasets.base import BenchmarkDataset, get_split_rows, row_to_dict
from rag_eval.schemas import Document, GroundTruth, MetadataValue, Query, TextSpan

_load_dataset = cast(Callable[..., object], datasets.load_dataset)


def download_qasper(output_dir: Path) -> BenchmarkDataset:
    """Download QASPER NLP research paper dataset from Hugging Face and normalize into BenchmarkDataset."""
    hf_data = _load_dataset("allenai/qasper", revision="refs/convert/parquet")
    rows = get_split_rows(hf_data, "test")

    documents_dict: dict[str, Document] = {}
    queries_dict: dict[str, Query] = {}
    ground_truths_dict: dict[str, GroundTruth] = {}

    for raw_row in rows:
        row = row_to_dict(raw_row)
        if not row:
            continue

        doc_id = str(row.get("id", ""))
        title = str(row.get("title", ""))
        abstract = str(row.get("abstract", ""))

        full_text_data = row.get("full_text")
        full_text_dict = row_to_dict(full_text_data)
        section_texts: list[str] = [abstract] if abstract else []
        if full_text_dict:
            paragraphs_list = full_text_dict.get("paragraphs")
            if isinstance(paragraphs_list, list):
                for p_group in cast(list[object], paragraphs_list):
                    if isinstance(p_group, list):
                        for p in cast(list[object], p_group):
                            section_texts.append(str(p))

        full_doc_text = "\n\n".join(section_texts)
        if doc_id and doc_id not in documents_dict:
            metadata: dict[str, MetadataValue] = {
                "title": title,
                "category": "academic_paper",
            }
            documents_dict[doc_id] = Document(
                id=doc_id,
                text=full_doc_text,
                title=title if title else None,
                metadata=metadata,
            )

        qas_data = row.get("qas")
        qas_dict = row_to_dict(qas_data)
        if qas_dict:
            questions = qas_dict.get("question")
            q_ids = qas_dict.get("question_id")
            answers_list = qas_dict.get("answers")

            if isinstance(questions, list):
                questions_list = cast(list[object], questions)
                ids_list = cast(list[object], q_ids) if isinstance(q_ids, list) else []
                answers_arr = (
                    cast(list[object], answers_list)
                    if isinstance(answers_list, list)
                    else []
                )

                for q_idx, q_text in enumerate(questions_list):
                    raw_q_id = (
                        str(ids_list[q_idx])
                        if q_idx < len(ids_list)
                        else f"{doc_id}_q_{q_idx}"
                    )
                    q_id = str(raw_q_id)
                    queries_dict[q_id] = Query(
                        id=q_id,
                        text=str(q_text),
                        metadata={"source_doc_id": doc_id, "title": title},
                    )

                    gold_answers: list[str] = []
                    spans: list[TextSpan] = []
                    if q_idx < len(answers_arr):
                        ans_block = answers_arr[q_idx]
                        ans_block_dict = row_to_dict(ans_block)
                        if ans_block_dict:
                            ans_texts = ans_block_dict.get("answer")
                            if isinstance(ans_texts, list):
                                for a in cast(list[object], ans_texts):
                                    a_dict = row_to_dict(a)
                                    if a_dict:
                                        free_form = a_dict.get("free_form_answer")
                                        if free_form:
                                            gold_answers.append(str(free_form))
                                        evidence = a_dict.get("evidence")
                                        if isinstance(evidence, list):
                                            for ev in cast(list[object], evidence):
                                                spans.append(
                                                    TextSpan(
                                                        start_char=0,
                                                        end_char=len(str(ev)),
                                                        text=str(ev),
                                                        section_name=title
                                                        if title
                                                        else None,
                                                    )
                                                )

                    ground_truths_dict[q_id] = GroundTruth(
                        query_id=q_id,
                        relevant_doc_ids=[doc_id] if doc_id else [],
                        answers=gold_answers,
                        spans=spans,
                    )

    benchmark = BenchmarkDataset(
        name="qasper",
        description="QASPER NLP academic research papers for educational and scientific RAG evaluation",
        documents=list(documents_dict.values()),
        queries=list(queries_dict.values()),
        ground_truths=list(ground_truths_dict.values()),
    )

    _ = benchmark.partition_and_export(output_dir)
    return benchmark


def parse_qasper_from_disk(data_dir: Path, split: str = "dev") -> BenchmarkDataset:
    """Parse local QASPER dataset from open dev JSONL or sealed holdout binary vault."""
    if split.lower() in ("test", "holdout"):
        vault_file = data_dir / ".holdout_vault" / "qasper.vault"
        if vault_file.is_file():
            return BenchmarkDataset.load_sealed_holdout(vault_file)
    dev_dir = (
        data_dir / "dev" / "qasper"
        if (data_dir / "dev" / "qasper").is_dir()
        else data_dir / "qasper"
    )
    return BenchmarkDataset.load_from_jsonl(
        dataset_dir=dev_dir,
        name="qasper",
        description="QASPER NLP academic research papers for educational and scientific RAG evaluation",
    )
