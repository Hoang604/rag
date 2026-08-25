"""Shared pytest fixtures for RAG evaluation suite."""

import pytest

from rag_eval.schemas import Document, GroundTruth, PredictionResult, Query, TextSpan


@pytest.fixture
def sample_documents() -> list[Document]:
    """Provide a list of sample domain documents."""
    return [
        Document(
            id="doc_law_001",
            text="Termination for convenience requires thirty days advance written notice.",
            title="Master Services Agreement",
            metadata={"category": "legal_contract"},
        ),
        Document(
            id="doc_bio_002",
            text="CRISPR Cas9 endonuclease enables targeted RNA-guided genome editing.",
            title="Genome Engineering Review",
            metadata={"category": "scientific_abstract"},
        ),
        Document(
            id="doc_fin_003",
            text="Quarterly dividend yields increased by fifteen percent across retail banking.",
            title="Q3 Financial Report",
            metadata={"category": "financial_report"},
        ),
    ]


@pytest.fixture
def sample_queries() -> list[Query]:
    """Provide a list of sample test queries."""
    return [
        Query(
            id="q_law",
            text="What is the notice period for contract termination?",
            metadata={"category": "legal_query"},
        ),
        Query(
            id="q_bio",
            text="How does CRISPR Cas9 perform genome editing?",
            metadata={"category": "bio_query"},
        ),
    ]


@pytest.fixture
def sample_ground_truths() -> list[GroundTruth]:
    """Provide reference ground truths matching the sample queries."""
    return [
        GroundTruth(
            query_id="q_law",
            relevant_doc_ids=["doc_law_001"],
            answers=["thirty days advance written notice"],
            spans=[
                TextSpan(
                    start_char=35,
                    end_char=71,
                    text="thirty days advance written notice",
                    section_name="Master Services Agreement",
                )
            ],
        ),
        GroundTruth(
            query_id="q_bio",
            relevant_doc_ids=["doc_bio_002"],
            answers=["targeted RNA-guided genome editing"],
            spans=[
                TextSpan(
                    start_char=35,
                    end_char=69,
                    text="targeted RNA-guided genome editing",
                    section_name="Genome Engineering Review",
                )
            ],
        ),
    ]


@pytest.fixture
def sample_predictions() -> list[PredictionResult]:
    """Provide sample predictions matching the queries and ground truths."""
    return [
        PredictionResult(
            query_id="q_law",
            retrieved_doc_ids=["doc_law_001", "doc_bio_002"],
            generated_answer="thirty days advance written notice.",
            latency_ms=12.5,
        ),
        PredictionResult(
            query_id="q_bio",
            retrieved_doc_ids=["doc_bio_002"],
            generated_answer="CRISPR Cas9 enables RNA-guided genome editing.",
            latency_ms=8.3,
        ),
    ]
