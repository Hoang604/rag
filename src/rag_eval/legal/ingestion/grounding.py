"""Grounding verification: proves chunk text is traceable to the source document.

A retrieval metric cannot detect a corrupted chunk. If `verbatim_text` says
"phạt tiền từ 8.000.000 đồng" where the statute says "18.000.000 đồng", the
chunk is still retrieved for the right query and every ranking metric stays
green -- the system answers confidently with the wrong penalty. The only defence
is verifying at ingestion time that chunk text derives from the source.

Two checks with deliberately different severities:

* NUMERIC (fatal): every digit run in the chunk must occur in the source.
  Catches dropped, added or transposed digits in fines, speeds, and dates. This
  is whitespace- and layout-independent, so it does not produce false positives
  on legitimate reflowing performed by the lexer.

* CONTIGUITY (warning): the whitespace-normalised chunk should appear verbatim
  in the whitespace-normalised source. Legitimate parser behaviour -- multiline
  title stitching, table reflow into Markdown pipes -- can break contiguity, so
  a violation here is reported for review rather than raised.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)

_DIGIT_RUN = re.compile(r"\d[\d.,]*\d|\d")
_WHITESPACE = re.compile(r"\s+")
# Glue thousands groups before tokenising so 18.000.000, 18,000,000 and
# 18 000 000 compare equal; a reflowed separator is not corruption.
_THOUSANDS_GROUP = re.compile(r"(\d)[.,\s](\d{3})(?!\d)")
# CPHC prepends a synthesised label ("Điểm c)" for a source "c)"), so it
# is stripped before the contiguity check.
_SYNTHESIZED_LABEL = re.compile(
    r"^\s*(?:Chương\s+[IVXLCDM]+|Mục\s+\d+|Điều\s+\d+\.|Khoản\s+\d+\.|Điểm\s+[a-zđ]\))\s*"
)

Severity = Literal["fatal", "warning"]


@dataclass(frozen=True)
class GroundingViolation:
    """A single chunk failing to trace back to its source document."""

    chunk_path: str
    check: Literal["numeric", "contiguity"]
    severity: Severity
    detail: str


def _normalize_whitespace(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip()


def _glue_thousands(text: str) -> str:
    """Collapses thousands separators so 18.000.000 / 18 000 000 become 18000000."""
    previous = None
    current = text
    while current != previous:
        previous = current
        current = _THOUSANDS_GROUP.sub(r"\1\2", current)
    return current


def _digit_runs(text: str) -> list[str]:
    """Extracts digit runs, keeping internal separators (18.000.000, 05, 1,5)."""
    return _DIGIT_RUN.findall(text)


def _canonical_digit_runs(text: str) -> set[str]:
    """Digit runs reduced to bare digits, with a leading-zero-stripped alias.

    Membership is tested per run rather than against one concatenated blob: a
    blob accepts 8.000.000 as a substring of 18.000.000 and lets exactly the
    dangerous corruption through.
    """
    runs: set[str] = set()
    for run in _digit_runs(_glue_thousands(text)):
        bare = re.sub(r"[^\d]", "", run)
        if not bare:
            continue
        runs.add(bare)
        runs.add(bare.lstrip("0") or "0")
    return runs


def verify_chunk_grounding(
    chunk_texts: dict[str, str],
    source_text: str,
) -> list[GroundingViolation]:
    """Checks every chunk against the source document it was parsed from.

    Args:
        chunk_texts: mapping of chunk path (for reporting) to its verbatim text.
        source_text: the cleaned document text the chunks were parsed from.

    Returns:
        All violations found, fatal ones first. An empty list means every chunk
        is fully grounded.
    """
    normalized_source = _normalize_whitespace(source_text)
    source_digit_runs = _canonical_digit_runs(source_text)

    fatal: list[GroundingViolation] = []
    warnings: list[GroundingViolation] = []

    for path, text in chunk_texts.items():
        for run in _digit_runs(_glue_thousands(text)):
            bare = re.sub(r"[^\d]", "", run)
            if not bare:
                continue
            if bare not in source_digit_runs:
                fatal.append(
                    GroundingViolation(
                        chunk_path=path,
                        check="numeric",
                        severity="fatal",
                        detail=f"digit run {run!r} does not occur in the source document",
                    )
                )

        body = _normalize_whitespace(_SYNTHESIZED_LABEL.sub("", text))
        if body and body not in normalized_source:
            warnings.append(
                GroundingViolation(
                    chunk_path=path,
                    check="contiguity",
                    severity="warning",
                    detail="chunk body is not a contiguous span of the source",
                )
            )

    return fatal + warnings


class ChunkGroundingError(RuntimeError):
    """Raised when chunk text contains numbers absent from the source document."""

    def __init__(self, violations: list[GroundingViolation]) -> None:
        self.violations = violations
        preview = "; ".join(f"{v.chunk_path}: {v.detail}" for v in violations[:5])
        suffix = f" (+{len(violations) - 5} more)" if len(violations) > 5 else ""
        super().__init__(
            f"{len(violations)} chunk(s) contain numbers absent from the source document. "
            f"Ingestion aborted to avoid persisting corrupted statutory figures. {preview}{suffix}"
        )


def enforce_chunk_grounding(
    chunk_texts: dict[str, str],
    source_text: str,
    *,
    strict: bool = True,
) -> list[GroundingViolation]:
    """Verifies grounding, raising on fatal violations when strict.

    Warnings are always logged. Returns every violation found so callers can
    record the contiguity rate for a corpus.
    """
    violations = verify_chunk_grounding(chunk_texts, source_text)
    fatal = [v for v in violations if v.severity == "fatal"]

    for violation in violations:
        if violation.severity == "warning":
            logger.warning(
                "Grounding contiguity: %s -- %s", violation.chunk_path, violation.detail
            )

    if fatal and strict:
        raise ChunkGroundingError(fatal)
    for violation in fatal:
        logger.error("Grounding numeric: %s -- %s", violation.chunk_path, violation.detail)

    return violations
