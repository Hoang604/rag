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


# Word markup has no line breaks; stripping tags alone merges adjacent
# paragraphs and table cells, and the lexer works line by line.
_DOCX_BREAK = re.compile(r"(?i)</w:(?:p|tc|tr)>|<w:br\s*/?>")
_DOCX_SPACE = re.compile(r"(?i)<w:tab\s*/?>")
_XML_TAG = re.compile(r"(?s)<[^>]+>")


def docx_to_text(data: bytes) -> str:
    """Extracts the text of a .docx, preserving paragraph and table-cell breaks."""
    import html
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if "word/document.xml" not in archive.namelist():
            raise ValueError("not a Word document: word/document.xml is missing")
        xml = archive.read("word/document.xml").decode("utf-8", errors="replace")

    xml = _DOCX_SPACE.sub(" ", xml)
    xml = _DOCX_BREAK.sub("\n", xml)
    return clean_legal_text(html.unescape(_XML_TAG.sub("", xml)))


def load_docx_file(file_path: Path | str) -> str:
    """Reads a .docx statutory document.

    Used where no official copy carries a text layer: every published PDF of
    Nghị định 100/2019/NĐ-CP is an image scan, and OCR is refused because it
    introduces exactly the digit corruption the ingestion grounding gate exists
    to catch.
    """
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"Source file not found: {file_path}")
    return docx_to_text(p.read_bytes())


def load_legal_document(file_path: Path | str) -> str:
    """Universal loader for legal documents supporting .pdf, .docx, .txt."""
    p = Path(file_path)
    suffix = p.suffix.lower()
    if suffix == ".pdf":
        return load_pdf_file(p)
    if suffix in (".docx", ".docm"):
        return load_docx_file(p)
    return load_text_file(p)
