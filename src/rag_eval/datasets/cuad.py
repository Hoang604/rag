"""CUAD legal contract dataset parser and normalizer."""

import json
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from rag_eval.datasets.base import BenchmarkDataset, row_to_dict
from rag_eval.schemas import Document, GroundTruth, MetadataValue, Query, TextSpan

CUAD_JSON_URL = (
    "https://huggingface.co/datasets/theatticusproject/cuad/resolve/main/CUAD_v1/CUAD_v1.json"
)


def download_cuad(output_dir: Path) -> BenchmarkDataset:
    """Download CUAD legal dataset from Hugging Face raw JSON release and normalize into BenchmarkDataset."""
    temp_dir = output_dir / ".cache"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_file = temp_dir / "CUAD_v1.json"

    if not temp_file.is_file() or temp_file.stat().st_size == 0:
        opener = urllib.request.build_opener()
        opener.addheaders = [("User-Agent", "Mozilla/5.0")]
        urllib.request.install_opener(opener)
        _ = urllib.request.urlretrieve(CUAD_JSON_URL, temp_file)

    parsed_obj: object
    with temp_file.open("r", encoding="utf-8") as f:
        parsed_obj = cast(object, json.loads(f.read()))

    if not isinstance(parsed_obj, Mapping):
        msg = "Invalid CUAD JSON payload format."
        raise TypeError(msg)

    data_mapping = cast(Mapping[str, object], parsed_obj)
    articles_raw = data_mapping.get("data")
    if not isinstance(articles_raw, list):
        msg = "CUAD JSON missing 'data' list."
        raise TypeError(msg)

    articles_list = cast(list[object], articles_raw)

    documents: list[Document] = []
    queries: list[Query] = []
    ground_truths: list[GroundTruth] = []

    for art_obj in articles_list:
        art_dict = row_to_dict(art_obj)
        if not art_dict:
            continue

        title = str(art_dict.get("title", "")).strip()
        doc_id = title if title else f"cuad_doc_{len(documents) + 1}"

        paragraphs_raw = art_dict.get("paragraphs")
        if not isinstance(paragraphs_raw, list):
            continue

        para_texts: list[str] = []
        for para_obj in cast(list[object], paragraphs_raw):
            para_dict = row_to_dict(para_obj)
            if not para_dict:
                continue

            context = str(para_dict.get("context", "")).strip()
            if context:
                para_texts.append(context)

            qas_raw = para_dict.get("qas")
            if isinstance(qas_raw, list):
                for qa_obj in cast(list[object], qas_raw):
                    qa_dict = row_to_dict(qa_obj)
                    if not qa_dict:
                        continue

                    q_id = str(qa_dict.get("id", "")).strip()
                    q_text = str(qa_dict.get("question", "")).strip()
                    if not q_id or not q_text:
                        continue

                    answers_raw = qa_dict.get("answers")
                    answers_list: list[object] = (
                        cast(list[object], answers_raw) if isinstance(answers_raw, list) else []
                    )

                    gold_answers: list[str] = []
                    spans: list[TextSpan] = []

                    for ans_obj in answers_list:
                        ans_dict = row_to_dict(ans_obj)
                        if not ans_dict:
                            continue
                        ans_text = str(ans_dict.get("text", "")).strip()
                        raw_start = ans_dict.get("answer_start")
                        start_char = int(cast(int | str, raw_start)) if raw_start is not None else 0
                        if ans_text:
                            gold_answers.append(ans_text)
                            spans.append(
                                TextSpan(
                                    start_char=start_char,
                                    end_char=start_char + len(ans_text),
                                    text=ans_text,
                                    section_name=title if title else None,
                                )
                            )

                    # Only export queries with labeled clause answers in the test benchmark
                    if gold_answers:
                        queries.append(
                            Query(
                                id=q_id,
                                text=q_text,
                                metadata={"source_doc_id": doc_id, "title": title},
                            )
                        )
                        ground_truths.append(
                            GroundTruth(
                                query_id=q_id,
                                relevant_doc_ids=[doc_id],
                                answers=gold_answers,
                                spans=spans,
                            )
                        )

        full_contract_text = "\n\n".join(para_texts)
        if full_contract_text:
            metadata: dict[str, MetadataValue] = {
                "title": title,
                "category": "legal_contract",
            }
            documents.append(
                Document(
                    id=doc_id,
                    text=full_contract_text,
                    title=title if title else None,
                    metadata=metadata,
                )
            )

    benchmark = BenchmarkDataset(
        name="cuad",
        description="Contract Understanding Atticus Dataset (CUAD) for legal RAG evaluation",
        documents=documents,
        queries=queries,
        ground_truths=ground_truths,
    )

    _ = benchmark.partition_and_export(output_dir)
    return benchmark


def parse_cuad_from_disk(data_dir: Path, split: str = "dev") -> BenchmarkDataset:
    """Parse local CUAD dataset from open dev JSONL or sealed holdout binary vault."""
    if split.lower() in ("test", "holdout"):
        vault_file = data_dir / ".holdout_vault" / "cuad.vault"
        if vault_file.is_file():
            return BenchmarkDataset.load_sealed_holdout(vault_file)
    dev_dir = data_dir / "dev" / "cuad" if (data_dir / "dev" / "cuad").is_dir() else data_dir / "cuad"
    return BenchmarkDataset.load_from_jsonl(
        dataset_dir=dev_dir,
        name="cuad",
        description="Contract Understanding Atticus Dataset (CUAD) for legal RAG evaluation",
    )
