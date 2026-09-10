"""Context-Preserving Hierarchical Chunking (CPHC) Engine.

Synthesizes self-contained atomic chunks by inheriting full ancestral lineage
from Document -> Chapter -> Article -> Clause down to each individual Point.
"""

from __future__ import annotations

import datetime
import re
import uuid
from typing import Final

from rag_eval.legal.ingestion.parser import ASTNode
from rag_eval.legal.schemas import (
    E_INVALID_DOCUMENT_HIERARCHY,
    CanonicalFullyQualifiedChunk,
    LegalDomainError,
)

# The embedding model truncates at 512 tokens silently. Calibrated on this
# corpus at 2.09 chars/token worst case, so 1,000 chars always fits. Counting
# characters keeps parsing free of an ML dependency.
EMBEDDING_CHAR_BUDGET = 1_000
_PASSAGE_PREFIX_ALLOWANCE = len("passage: ")
# Statutory prose breaks at these marks. Splitting only on whitespace runs
# guarantees no token -- and so no monetary figure -- is ever cut in half.
_SENTENCE_BREAK = re.compile(r"(?<=[.;:])\s+|\n+")
_WHITESPACE_RUN = re.compile(r"\s+")
# When a lead sentence makes the synthesized prefix so long that little room is
# left, the prefix yields rather than the statute. Context is regenerable; text
# is not.
_MIN_BODY_BUDGET = 400


def _fit_prefix(prefix: str) -> str:
    """Caps the synthesized prefix so the provision always keeps room."""
    ceiling = EMBEDDING_CHAR_BUDGET - _PASSAGE_PREFIX_ALLOWANCE - _MIN_BODY_BUDGET
    if len(prefix) <= ceiling:
        return prefix
    return prefix[: ceiling - 4].rstrip() + " ...]"


def _pack(pieces: list[str], budget: int) -> list[str]:
    """Greedily groups pieces into runs no longer than `budget`."""
    parts: list[str] = []
    current = ""
    for piece in pieces:
        candidate = f"{current} {piece}".strip() if current else piece
        if current and len(candidate) > budget:
            parts.append(current)
            current = piece
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts


_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_SEPARATOR = re.compile(r"^\s*\|(?:\s*-{3,}\s*\|)+\s*$")
_MIN_TABLE_ROWS = 3
_TABLE_CAPTION = re.compile(r"^\s*(?:Bảng|Biểu|BẢNG|BIỂU)\s*[A-Za-z0-9]")


# How many short lines may sit between a caption and its table. Statutes put a
# unit note there -- "Đơn vị tính: mm" -- and occasionally a second qualifier.
_MAX_CAPTION_TAIL: Final[int] = 3

# A note belonging to the table is short. A full paragraph between the caption
# and the rows means the two are not associated, and dragging it into every
# window would bury the figures it was supposed to introduce.
_MAX_ANNOTATION_CHARS: Final[int] = 80


def _trailing_caption(lines: list[str]) -> tuple[list[str], int]:
    """Returns the preamble a prose run ends with, and how many lines it spans.

    The preamble is the `Bảng N - ...` caption plus any short note between it
    and the table. Both matter to a reader of one window: the caption says
    which table this is, and the note says what the numbers mean.

    Scanning back rather than reading only the last line, because the last line
    is frequently the unit. QCVN 41 writes

        Bảng 1 - Kích thước cơ bản của biển báo hệ số 1
        Đơn vị tính: mm
        | Loại biển | Kích thước | Độ lớn |

    and a last-line-only check returned "" for it, leaving the caption stranded
    in the preceding prose window while the rows travelled alone. The stored
    chunk then read `| Biển tròn | Đường kính ngoài của biển báo, D | 700 |`
    with no table name and no millimetres anywhere in it.
    """
    tail: list[str] = []
    for line in reversed(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if _TABLE_CAPTION.match(line):
            return [stripped, *reversed(tail)], len(tail) + 1
        if len(tail) >= _MAX_CAPTION_TAIL or len(stripped) > _MAX_ANNOTATION_CHARS:
            return [], 0
        tail.append(stripped)
    return [], 0


def _is_table_block(lines: list[str]) -> bool:
    return len(lines) >= _MIN_TABLE_ROWS and all(_TABLE_ROW.match(x) for x in lines)


def _segment_table_blocks(body: str) -> list[tuple[bool, list[str]]]:
    """Splits a body into alternating prose and Markdown-table runs."""
    segments: list[tuple[bool, list[str]]] = []
    for line in body.split("\n"):
        is_row = bool(_TABLE_ROW.match(line))
        if segments and segments[-1][0] == is_row:
            segments[-1][1].append(line)
        else:
            segments.append((is_row, [line]))
    return segments


def _strip_trailing(lines: list[str], count: int) -> list[str]:
    """Drops the last `count` non-blank lines, and any blanks after them."""
    if count <= 0:
        return lines
    kept = list(lines)
    while kept and count:
        if kept[-1].strip():
            count -= 1
        kept.pop()
    return kept


def _split_table(
    lines: list[str], budget: int, preamble: list[str] | None = None
) -> list[str]:
    """Windows a Markdown table by rows, repeating its header in each window.

    A table split by sentence boundaries loses two things at once: the rows are
    rejoined with spaces, so the pipes stop delimiting anything, and every
    window after the first carries figures with no column names above them.
    The caption travels with each window for the same reason the header does:
    "Bảng 2 - Hệ số kích thước biển báo" is what says which table this is.
    """
    header = (
        lines[:2] if len(lines) > 1 and _TABLE_SEPARATOR.match(lines[1]) else lines[:1]
    )
    data = lines[len(header) :]
    header = [*(preamble or []), *header]
    stem = "\n".join(header)
    if not data or len(stem) >= budget:
        return ["\n".join(header + data)]

    windows: list[str] = []
    current: list[str] = []
    for row in data:
        candidate = current + [row]
        if current and len(stem) + 1 + sum(len(x) + 1 for x in candidate) > budget:
            windows.append("\n".join(header + current))
            current = [row]
        else:
            current = candidate
    if current:
        windows.append("\n".join(header + current))
    return windows


def split_for_embedding(body: str, budget: int) -> list[str]:
    """Splits text into windows that fit `budget` characters, never mid-token.

    Sentence boundaries are preferred; a single sentence over budget falls back
    to whitespace runs. Markdown tables are windowed by row instead, so each
    part stays a readable table. Nothing is dropped and no word is broken.
    """
    if len(body) <= budget or budget <= 0:
        return [body]

    segments = _segment_table_blocks(body)
    if any(is_row and _is_table_block(lines) for is_row, lines in segments):
        windows: list[str] = []
        preamble: list[str] = []
        for is_row, lines in segments:
            block = "\n".join(lines)
            if not block.strip():
                continue
            if is_row and _is_table_block(lines):
                windows.extend(_split_table(lines, budget, preamble))
                preamble = []
            else:
                # The preamble is re-emitted inside every window of the table
                # it introduces, so a window holding it alone says nothing --
                # and a window of figures without it says nothing either.
                preamble, consumed = _trailing_caption(lines)
                remainder = chr(10).join(_strip_trailing(lines, consumed)).strip()
                if remainder:
                    windows.extend(_split_prose(remainder, budget))
        return windows or [body]

    return _split_prose(body, budget)


def _split_prose(body: str, budget: int) -> list[str]:
    """Windows ordinary statutory prose on sentence, then whitespace, breaks."""
    if len(body) <= budget:
        return [body]

    parts = _pack([p for p in _SENTENCE_BREAK.split(body) if p and p.strip()], budget)
    if all(len(part) <= budget for part in parts):
        return parts

    resolved: list[str] = []
    for part in parts:
        if len(part) <= budget:
            resolved.append(part)
        else:
            resolved.extend(_pack(_WHITESPACE_RUN.split(part), budget))
    return resolved


_DIVISION_LABEL = re.compile(r"^((?:Chương|Mục)\s+[IVXLCDM\d]+[a-z]?)\b")
_DOC_TITLE_CHARS = 90


def _compact_doc_title(title: str) -> str:
    """Trims a document title to its first clause, on a word boundary."""
    head = title.strip().split(";")[0].strip()
    if len(head) <= _DOC_TITLE_CHARS:
        return head
    return head[:_DOC_TITLE_CHARS].rsplit(" ", 1)[0]


def _compact_chapter(heading: str) -> str:
    """Reduces a chapter or section heading to its label.

    Every chunk of Chương II carried its 208-character all-caps title, so 843
    chunks of the penalty decree opened with 361 identical characters -- 61% of
    the average embedded string, crowding out the article title that is the
    only thing separating ô tô from xe máy. Appendix headings are left whole:
    there the heading *is* the classification.
    """
    match = _DIVISION_LABEL.match(heading.strip())
    return match.group(1) if match else heading.strip()


def synthesize_cphc_prefix(
    doc_title: str,
    chapter_title: str = "",
    article_label: str = "",
    article_title: str = "",
    clause_label: str = "",
    lead_sentence: str = "",
) -> str:
    """Synthesizes a standardized hierarchical context prefix for embedding and LLM comprehension."""
    parts: list[str] = [f"[{_compact_doc_title(doc_title)}]"]
    if chapter_title.strip():
        parts.append(f"[{_compact_chapter(chapter_title)}]")
    if article_label.strip() or article_title.strip():
        art_str = f"{article_label}: {article_title}".strip(": ")
        parts.append(f"[{art_str}]")
    if clause_label.strip() or lead_sentence.strip():
        cl_str = f"{clause_label}: {lead_sentence}".strip(": ")
        parts.append(f"[{cl_str}]")
    return " > ".join(parts)


class CPHCEngine:
    """Transforms an AST hierarchy into a flat list of CanonicalFullyQualifiedChunks."""

    def __init__(
        self,
        document_id: uuid.UUID,
        doc_code: str,
        doc_title: str,
        effective_date: datetime.date,
        expiration_date: datetime.date | None = None,
    ) -> None:
        self.document_id = document_id
        self.doc_code = doc_code
        self.doc_title = doc_title
        self.effective_date = effective_date
        self.expiration_date = expiration_date

    def chunk_ast(self, root: ASTNode) -> list[CanonicalFullyQualifiedChunk]:
        """Flattens the AST into atomic leaf chunks with full context lineage."""
        chunks: list[CanonicalFullyQualifiedChunk] = []

        def _traverse(
            node: ASTNode,
            chap_title: str,
            art_label: str,
            art_title: str,
            cl_label: str,
            lead: str,
            appendix: str = "",
        ) -> None:
            cur_chap = (
                f"{node.index_label} - {node.title}".strip(" -")
                if node.node_type == "CHAPTER"
                else chap_title
            )
            cur_art_label = (
                node.index_label if node.node_type == "ARTICLE" else art_label
            )
            cur_art_title = node.title if node.node_type == "ARTICLE" else art_title
            cur_cl_label = (
                node.index_label
                if node.node_type in ("CLAUSE", "APPENDIX_ITEM")
                else cl_label
            )
            cur_appendix = (
                f"{node.index_label} - {node.title}".strip(" -")
                if node.node_type == "APPENDIX"
                else appendix
            )

            # Inherit lead sentence from container stem clauses
            cur_lead = (
                node.lead_sentence
                if node.node_type in ("CLAUSE", "APPENDIX_ITEM", "APPENDIX")
                and node.clause_kind == "CONTAINER_STEM"
                else lead
            )

            if not node.children and node.node_type in (
                "POINT",
                "CLAUSE",
                "ARTICLE",
                "APPENDIX",
                "APPENDIX_ITEM",
            ):
                verbatim = node.raw_text.strip()

                if node.node_type == "POINT":
                    prefix = synthesize_cphc_prefix(
                        doc_title=self.doc_title or self.doc_code,
                        chapter_title=cur_chap or cur_appendix,
                        article_label=cur_art_label,
                        article_title=cur_art_title,
                        clause_label=cur_cl_label,
                        lead_sentence=cur_lead,
                    )
                elif node.node_type == "CLAUSE":
                    # Standalone clause rule: omit lead_sentence to prevent redundant duplication
                    prefix = synthesize_cphc_prefix(
                        doc_title=self.doc_title or self.doc_code,
                        chapter_title=cur_chap,
                        article_label=cur_art_label,
                        article_title=cur_art_title,
                        clause_label=node.index_label,
                        lead_sentence="",
                    )
                elif node.node_type == "ARTICLE":
                    prefix = synthesize_cphc_prefix(
                        doc_title=self.doc_title or self.doc_code,
                        chapter_title=cur_chap,
                        article_label=node.index_label,
                        article_title=node.title,
                    )
                elif node.node_type == "APPENDIX_ITEM":
                    # The appendix heading carries the classification: an item
                    # of Phụ lục B is a prohibitory sign, of Phụ lục C a warning.
                    prefix = (
                        f"[{_compact_doc_title(self.doc_title or self.doc_code)}] > "
                        f"[{cur_appendix}] > [{node.index_label}]"
                    )
                else:  # APPENDIX
                    prefix = (
                        f"[{_compact_doc_title(self.doc_title or self.doc_code)}] > "
                        f"[{node.index_label}: {node.title}]".strip(": ]")
                        + "]"
                    )

                # Where lead and body compete for the window, the synthesized context
                # gives way: it can be regenerated, statute cannot.
                prefix = _fit_prefix(prefix)
                body_budget = (
                    EMBEDDING_CHAR_BUDGET - _PASSAGE_PREFIX_ALLOWANCE - len(prefix) - 1
                )
                windows = split_for_embedding(verbatim, body_budget)

                for position, window in enumerate(windows, start=1):
                    # A single-window provision keeps its own path; a split one gets sibling
                    # `.w_<n>` paths, each carrying the full hierarchy prefix.
                    if len(windows) == 1:
                        path = node.full_path
                        label = node.index_label
                    else:
                        path = f"{node.full_path}.w_{position}"
                        label = f"{node.index_label} (phần {position}/{len(windows)})"
                    chunks.append(
                        CanonicalFullyQualifiedChunk(
                            id=uuid.uuid5(
                                uuid.NAMESPACE_DNS, f"{self.doc_code}:{path}"
                            ),
                            document_id=self.document_id,
                            path=path,
                            verbatim_text=window,
                            contextualized_text=f"{prefix}\n{window}"
                            if prefix
                            else window,
                            effective_date=self.effective_date,
                            expiration_date=self.expiration_date,
                            metadata={
                                "doc_code": self.doc_code,
                                "node_type": node.node_type,
                                "index_label": label,
                                "clause_kind": getattr(node, "clause_kind", "NONE"),
                                "chapter_title": cur_chap,
                                "article_title": cur_art_title,
                            }
                            | (
                                {}
                                if len(windows) == 1
                                else {
                                    "window": str(position),
                                    "window_count": str(len(windows)),
                                    "provision_path": node.full_path,
                                }
                            ),
                        )
                    )

            for child in node.children:
                _traverse(
                    child,
                    cur_chap,
                    cur_art_label,
                    cur_art_title,
                    cur_cl_label,
                    cur_lead,
                    cur_appendix,
                )

        _traverse(root, "", "", "", "", "", "")
        _assert_paths_unique(chunks, self.doc_code)
        return chunks


def _assert_paths_unique(
    chunks: list[CanonicalFullyQualifiedChunk], doc_code: str
) -> None:
    """Fails the parse when two chunks claim the same ltree path.

    `chunks.path` is UNIQUE in the schema, so a collision reaching the database
    either aborts the load or overwrites a real provision -- and the overwrite
    is silent, leaving retrieval to answer with the wrong clause. Checking here
    turns that into a parse failure naming the paths, because the collision is
    a defect in label encoding rather than in the source document.
    """
    seen: dict[str, str] = {}
    collisions: list[str] = []
    for chunk in chunks:
        previous = seen.get(chunk.path)
        if previous is not None:
            label = str(chunk.metadata.get("index_label", "?"))
            collisions.append(f"{chunk.path} ({previous!r} vs {label!r})")
        else:
            seen[chunk.path] = str(chunk.metadata.get("index_label", "?"))

    if collisions:
        preview = "; ".join(collisions[:5])
        suffix = f" (+{len(collisions) - 5} more)" if len(collisions) > 5 else ""
        raise LegalDomainError(
            error_code=E_INVALID_DOCUMENT_HIERARCHY,
            message=(
                f"{len(collisions)} chunk path collision(s) in '{doc_code}'. "
                f"Distinct provisions would overwrite each other. {preview}{suffix}"
            ),
            data={"doc_code": doc_code, "collisions": collisions[:50]},
        )
