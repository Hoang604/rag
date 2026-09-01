"""Text and document loader/normalizer for legal sources."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path


def clean_legal_text(raw_text: str) -> str:
    """Normalizes whitespace and standardizes statutory section headers with NFC normalization."""
    if not raw_text:
        return ""
    text = unicodedata.normalize("NFC", raw_text)
    text = re.sub(r"\r\n|\r", "\n", text)
    lines = [re.sub(r"[ \t]+", " ", l.strip()) for l in text.split("\n")]
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
