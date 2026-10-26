from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from pydantic import ValidationError

from rag_eval.legal.ingestion.corpus import SOURCES_DIR, TEXT_DIR, read_meta
from rag_eval.legal.schemas.retrieval import SearchHit

QUOTE_WORDS = 10
RANGE_START_WORDS = (4, 6, 8, 12, 16)
RANGE_END_WORDS = 3
MIN_QUOTE_WORDS = 3
_LEADING_LABEL = re.compile(r"^\s*(?:[a-zđ]\)|\d+(?:\.\d+)*\.)\s*", re.IGNORECASE)
_CLAUSE_END = re.compile(r"[;:\n]|\.(?!\d)")


class _FlatText:
    def __init__(self, raw: str) -> None:
        self.line_offsets: list[int] = []
        pieces: list[str] = []
        cursor = 0
        for line in raw.split("\n"):
            self.line_offsets.append(cursor)
            piece = " ".join(line.split())
            pieces.append(piece)
            cursor += len(piece) + 1
        self.text = " ".join(pieces)
        self.folded = self.text.lower()


@lru_cache(maxsize=1)
def _canonical_texts(sources_dir: Path = SOURCES_DIR, text_dir: Path = TEXT_DIR) -> dict[str, _FlatText]:
    texts: dict[str, _FlatText] = {}
    if not sources_dir.is_dir():
        return texts
    for source_dir in sorted(p for p in sources_dir.iterdir() if (p / "meta.json").is_file()):
        text_path = text_dir / f"{source_dir.name}.txt"
        try:
            meta = read_meta(source_dir)
            texts[meta.doc_code] = _FlatText(text_path.read_text(encoding="utf-8"))
        except (ValidationError, OSError):
            continue
    return texts


def _quote_of(provision: str) -> str:
    sentence = _CLAUSE_END.split(_LEADING_LABEL.sub("", provision), maxsplit=1)[0]
    return " ".join(sentence.split()[:QUOTE_WORDS]).rstrip(",;:.")


def _encode(part: str) -> str:
    return quote(part, safe="").replace("-", "%2D")


def _range_lands(flat: _FlatText, start_text: str, end_text: str, target: int, target_end: int) -> bool:
    start = flat.folded.find(start_text.lower())
    if start < 0:
        return False
    end = flat.folded.find(end_text.lower(), start + len(start_text))
    return target <= end <= target_end


def text_fragment(hit: SearchHit) -> str | None:
    quote_text = _quote_of(hit.verbatim_text)
    if len(quote_text.split()) < MIN_QUOTE_WORDS:
        return None
    single = f"#:~:text={_encode(quote_text)}"
    flat = _canonical_texts().get(hit.doc_code)
    if flat is None:
        return single
    line_index = min(max(hit.start_line - 1, 0), len(flat.line_offsets) - 1)
    target = flat.folded.find(quote_text.lower(), flat.line_offsets[line_index])
    if target < 0:
        return None
    if flat.folded.find(quote_text.lower()) == target:
        return single
    previous_line_start = flat.line_offsets[line_index - 1] if line_index > 0 else 0
    preceding = flat.text[previous_line_start:target].split()
    if preceding and _LEADING_LABEL.fullmatch(preceding[-1] + " "):
        preceding = preceding[:-1]
    end_text = " ".join(quote_text.split()[-RANGE_END_WORDS:])
    for words in RANGE_START_WORDS:
        start_text = " ".join(preceding[-words:])
        if start_text and _range_lands(flat, start_text, end_text, target, target + len(quote_text)):
            return f"#:~:text={_encode(start_text)},{_encode(end_text)}"
    return None


def with_text_fragments(hits: list[SearchHit]) -> list[SearchHit]:
    return [hit.model_copy(update={"source_fragment": text_fragment(hit)}) for hit in hits]
