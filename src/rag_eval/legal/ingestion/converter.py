"""Text and document loader/normalizer for legal sources."""

from __future__ import annotations

import re
from pathlib import Path


def clean_legal_text(raw_text: str) -> str:
    """Normalizes whitespace and standardizes statutory section headers."""
    if not raw_text:
        return ""
    text = re.sub(r"\r\n|\r", "\n", raw_text)
    lines = [re.sub(r"[ \t]+", " ", l.strip()) for l in text.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def load_text_file(file_path: Path | str) -> str:
    """Reads a UTF-8 encoded text file with clean whitespace normalization."""
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"Source file not found: {file_path}")
    raw = p.read_text(encoding="utf-8")
    return clean_legal_text(raw)
