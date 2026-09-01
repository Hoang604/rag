"""Text and document loader/normalizer for legal sources."""

from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path

logger = logging.getLogger(__name__)


def clean_legal_text(raw_text: str) -> str:
    """Normalizes whitespace and standardizes statutory section headers with NFC normalization."""
    if not raw_text:
        return ""
    text = unicodedata.normalize("NFC", raw_text)
    text = re.sub(r"\r\n|\r", "\n", text)
    lines = [re.sub(r"[ \t]+", " ", line.strip()) for line in text.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def load_text_file(file_path: Path | str) -> str:
    """Reads a UTF-8 encoded text file with clean whitespace and Unicode NFC normalization."""
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"Source file not found: {file_path}")
    raw = p.read_text(encoding="utf-8")
    return clean_legal_text(raw)


def load_pdf_file(file_path: Path | str) -> str:
    """Extracts and normalizes text and tables from a statutory PDF document without table duplication."""
    from rag_eval.legal.ingestion.layout import PDFLayoutExtractor

    extractor = PDFLayoutExtractor()
    text = extractor.extract_document_text(file_path)
    return clean_legal_text(text)


def load_legal_document(file_path: Path | str) -> str:
    """Universal loader for legal documents supporting .pdf, .txt, and other text formats."""
    p = Path(file_path)
    if p.suffix.lower() == ".pdf":
        return load_pdf_file(p)
    return load_text_file(p)
