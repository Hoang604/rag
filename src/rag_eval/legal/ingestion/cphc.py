from __future__ import annotations

import datetime
import re
import uuid
from collections import Counter
from dataclasses import dataclass
from typing import Final

from rag_eval.legal.db.entities import ChunkEntity
from rag_eval.legal.errors import (
    E_INVALID_DOCUMENT_HIERARCHY,
    LegalDomainError,
)
from rag_eval.legal.ingestion.parser import ASTNode
from rag_eval.legal.ingestion.tables import is_data_table
from rag_eval.legal.text import (
    get_vietnam_now,
    slice_raw_text,
)

EMBEDDING_CHAR_BUDGET = 25_000
_MIN_BODY_BUDGET = 400


def _fit_prefix(prefix: str) -> str:
    """Caps the synthesized prefix so the provision always keeps room."""
    ceiling = EMBEDDING_CHAR_BUDGET - _MIN_BODY_BUDGET
    if len(prefix) <= ceiling:
        return prefix
    return prefix[: ceiling - 4].rstrip() + " ...]"


_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_SEPARATOR = re.compile(r"^\s*\|(?:\s*-{3,}\s*\|)+\s*$")
_MIN_TABLE_ROWS = 3
_TABLE_CAPTION = re.compile(r"^\s*(?:Bảng|Biểu|BẢNG|BIỂU)\s*[A-Za-z0-9]")


_MAX_CAPTION_TAIL: Final[int] = 3

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
    """True for a run of pipe rows that should be windowed as a table.

    The shape test is not enough on its own. A scraped page rules ordinary
    provisions and government forms, and those arrive as pipe rows too --
    `Điều 42` of 184/2025/NĐ-CP came through as thirteen columns with twelve
    empty. Windowing that repeats the provision's first line as a header and
    cuts the statute into `| | ... | | |` fragments, so the fill test decides
    whether the pipes mean anything.
    """
    if len(lines) < _MIN_TABLE_ROWS or not all(_TABLE_ROW.match(x) for x in lines):
        return False
    return is_data_table(lines)


@dataclass(frozen=True)
class LineWindow:
    """One embeddable part of a provision: its own raw line range plus context it lacks.

    The window's text is always the raw slice of its lines, so it stays
    grounded in the source. `context_stem` holds what a reader of a window that
    opens mid-table needs but the window does not contain -- the table caption
    and header rows -- and belongs in the contextualized text, never the verbatim.
    """

    start_line: int
    end_line: int
    context_stem: str


def window_lines(lines: list[str], first_line: int, budget: int) -> list[LineWindow]:
    """Packs a provision's raw lines into line-aligned windows of at most `budget` characters.

    Lines are never split, so a single line longer than the budget becomes its
    own oversized window rather than breaking the grounding of its text.
    Markdown data tables are packed by row; a window that opens inside a table
    carries the caption and header rows as its context stem.
    """
    last_line = first_line + len(lines) - 1
    if budget <= 0 or len("\n".join(lines).strip()) <= budget:
        return [LineWindow(first_line, last_line, "")]

    table_rows = [bool(_TABLE_ROW.match(line)) for line in lines]
    runs: list[tuple[int, int]] = []
    for idx, is_row in enumerate(table_rows):
        if runs and table_rows[runs[-1][0]] == is_row:
            runs[-1] = (runs[-1][0], idx)
        else:
            runs.append((idx, idx))

    windows: list[LineWindow] = []
    current: list[int] = []
    current_len = 0
    current_stem = ""

    def flush() -> None:
        nonlocal current, current_len
        if any(lines[i].strip() for i in current):
            windows.append(
                LineWindow(first_line + current[0], first_line + current[-1], current_stem)
            )
        current = []
        current_len = 0

    def add(idx: int, stem: str) -> None:
        nonlocal current_len, current_stem
        line = lines[idx]
        if not current and not line.strip():
            return
        stem_cost = len(stem) + 1 if stem else 0
        if current and current_len + len(line) + 1 + stem_cost > budget:
            flush()
            if not line.strip():
                return
        if not current:
            current_stem = stem
        current.append(idx)
        current_len += len(line) + 1

    for run_start, run_end in runs:
        run = lines[run_start : run_end + 1]
        if table_rows[run_start] and _is_table_block(run):
            caption, _ = _trailing_caption(lines[:run_start])
            header_count = 2 if len(run) > 1 and _TABLE_SEPARATOR.match(run[1]) else 1
            stem = "\n".join([*caption, *(line.strip() for line in run[:header_count])])
            for idx in range(run_start, run_end + 1):
                add(idx, stem if idx >= run_start + header_count else "")
        else:
            for idx in range(run_start, run_end + 1):
                add(idx, "")
    flush()
    return windows or [LineWindow(first_line, last_line, "")]


_DIVISION_LABEL = re.compile(r"^((?:Chương|Mục)\s+[IVXLCDM\d]+[a-zđ]?)\b")


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


def _heading(node: ASTNode) -> str:
    return f"{node.index_label} - {node.title}".strip(" -")


def _labelled(label: str, text: str) -> str:
    return f"{label}: {text}".strip(": ")


# The node types whose own text starts at their marker line; every other division's own text starts after its heading.
_STARTS_AT_MARKER: Final = frozenset({"CLAUSE", "POINT", "OUTLINE_ITEM", "TAIL", "PREAMBLE", "POSTAMBLE"})
# The divisions whose heading lines are titles, carried in context rather than in any chunk.
_TITLED: Final = frozenset({"PART", "CHAPTER", "SECTION", "SUBSECTION", "ARTICLE", "APPENDIX"})


@dataclass(frozen=True)
class _Context:
    """What a node's chunks need to know about the divisions enclosing it."""

    trail: tuple[str, ...] = ()  # enclosing context entries, outermost first, after the document title
    article_lead: str = ""  # the enclosing article's lead-in, for its khoản and điểm
    chapter: str = ""
    section: str = ""
    article_title: str = ""

    def own_entry(self, node: ASTNode) -> tuple[str, ...]:
        """The entry that names `node` in its own chunk's context."""
        if node.node_type in ("PART", "CHAPTER", "SECTION", "SUBSECTION", "APPENDIX"):
            return (_heading(node),)
        if node.node_type == "ARTICLE":
            return (_labelled(node.index_label, node.title),)
        if node.node_type in ("CLAUSE", "OUTLINE_ITEM", "PREAMBLE", "POSTAMBLE"):
            return (node.index_label,)
        return ()

    def descend(self, node: ASTNode) -> _Context:
        """The context of `node`'s children."""
        entry: tuple[str, ...] = ()
        updates: dict[str, str] = {}
        if node.node_type == "PART":
            entry = (node.index_label,)
        elif node.node_type == "CHAPTER":
            entry = (_compact_chapter(_heading(node)),)
            updates = {"chapter": _heading(node), "section": ""}
        elif node.node_type in ("SECTION", "SUBSECTION"):
            updates = {"section": _heading(node)}
        elif node.node_type == "APPENDIX":
            entry = (_heading(node),)
        elif node.node_type == "ARTICLE":
            entry = (_labelled(node.index_label, node.title),)
            updates = {"article_lead": node.lead_sentence, "article_title": node.title}
        elif node.node_type in ("CLAUSE", "OUTLINE_ITEM"):
            entry = (_labelled(node.index_label, " ".join(node.lead_sentence.split())),)
        return _Context(
            trail=(*self.trail, *entry),
            article_lead=updates.get("article_lead", self.article_lead),
            chapter=updates.get("chapter", self.chapter),
            section=updates.get("section", self.section),
            article_title=updates.get("article_title", self.article_title),
        )


class CPHCEngine:
    """Transforms an AST hierarchy into a flat list of ChunkEntity instances."""

    def __init__(
        self,
        document_id: uuid.UUID,
        doc_code: str,
        doc_title: str,
        raw_text: str,
        effective_date: datetime.date,
        expiration_date: datetime.date | None = None,
    ) -> None:
        self.document_id = document_id
        self.raw_text = raw_text
        self._raw_lines = raw_text.splitlines()
        self.doc_code = doc_code
        self.doc_title = doc_title
        self.effective_date = effective_date
        self.expiration_date = expiration_date

    def chunk_ast(self, root: ASTNode) -> list[ChunkEntity]:
        """Chunks every node's own text; raises LegalDomainError when a non-exempt line is covered 0 or ≥2 times."""
        chunks: list[ChunkEntity] = []

        def traverse(node: ASTNode, context: _Context, own_context: tuple[str, ...]) -> None:
            if node.node_type not in ("DOCUMENT", "FORM"):
                chunks.extend(self._chunks_of(node, context, own_context))
            inner = context.descend(node)
            for child in node.children:
                # A TAIL closes its parent's list, so it reads in its parent's own context.
                child_own = own_context if child.node_type == "TAIL" else (*inner.trail, *inner.own_entry(child))
                traverse(child, inner, child_own)

        base = _Context()
        traverse(root, base, ())
        _assert_paths_unique(chunks, self.doc_code)
        self._assert_line_coverage(root, chunks)
        return chunks

    def _own_span(self, node: ASTNode) -> tuple[int, int, str, str] | None:
        """(first line, last line, path, label) of the node's own text, or None when it has none."""
        first = node.start_line if node.node_type in _STARTS_AT_MARKER else node.heading_end_line + 1
        if node.children:
            last, path, label = node.children[0].start_line - 1, f"{node.full_path}.body", f"{node.index_label} (phần mở đầu)"
        else:
            last, path, label = node.end_line, node.full_path, node.index_label
        if not any(line.strip() for line in self._raw_lines[first - 1 : last]):
            return None
        return first, last, path, label

    def _chunks_of(self, node: ASTNode, context: _Context, own_context: tuple[str, ...]) -> list[ChunkEntity]:
        span = self._own_span(node)
        if span is None:
            return []
        span_start, span_end, span_path, span_label = span
        prefix = " > ".join(f"[{part}]" for part in (self.doc_title, *own_context) if part)
        if context.article_lead and node.node_type in ("CLAUSE", "POINT", "TAIL"):
            prefix = f"{prefix}\n{context.article_lead}"
        prefix = _fit_prefix(prefix)
        body_budget = EMBEDDING_CHAR_BUDGET - len(prefix) - 1
        windows = window_lines(self._raw_lines[span_start - 1 : span_end], span_start, body_budget)

        out: list[ChunkEntity] = []
        for position, window in enumerate(windows, start=1):
            verbatim = slice_raw_text(self.raw_text, window.start_line, window.end_line)
            body = f"{window.context_stem}\n{verbatim}" if window.context_stem else verbatim
            if len(windows) == 1:
                path, label = span_path, span_label
            else:
                path, label = f"{span_path}.w_{position}", f"{span_label} (phần {position}/{len(windows)})"
            now = get_vietnam_now()
            out.append(
                ChunkEntity(
                    id=uuid.uuid5(uuid.NAMESPACE_DNS, f"{self.doc_code}:{path}"),
                    document_id=self.document_id,
                    path=path,
                    verbatim_text=verbatim,
                    contextualized_text=f"{prefix}\n{body}",
                    start_line=window.start_line,
                    end_line=window.end_line,
                    effective_date=self.effective_date,
                    expiration_date=self.expiration_date,
                    created_at=now,
                    updated_at=now,
                    metadata={
                        "node_type": node.node_type,
                        "index_label": label,
                        "chapter_title": context.chapter or None,
                        "section_title": context.section or None,
                        "article_title": (node.title if node.node_type == "ARTICLE" else context.article_title) or None,
                    },
                )
            )
        return out

    def _assert_line_coverage(self, root: ASTNode, chunks: list[ChunkEntity]) -> None:
        """Fails the parse unless every non-empty line is in exactly one chunk (I-01).

        Division titles are carried in context, and forms are not chunked, so their lines
        are exempt; any other line in no chunk is statute lost to every search, and a line
        in two chunks is a parser defect that splits one provision's identity.
        """
        exempt: set[int] = set()

        def collect(node: ASTNode) -> None:
            if node.node_type in _TITLED:
                exempt.update(range(node.start_line, node.heading_end_line + 1))
            elif node.node_type == "FORM":
                exempt.update(range(node.start_line, node.end_line + 1))
            for child in node.children:
                collect(child)

        collect(root)
        cover = Counter(line for chunk in chunks for line in range(chunk.start_line, chunk.end_line + 1))
        faults = [
            (number, cover[number])
            for number, text in enumerate(self._raw_lines, start=1)
            if text.strip() and number not in exempt and cover[number] != 1
        ]
        if faults:
            preview = " ".join(f"L{number}×{count} {self._raw_lines[number - 1][:60]!r}" for number, count in faults[:5])
            raise LegalDomainError(
                error_code=E_INVALID_DOCUMENT_HIERARCHY,
                message=(
                    f"{len(faults)} line(s) of '{self.doc_code}' are in no chunk (×0) or in several (×2+): {preview}"
                ),
                data={"doc_code": self.doc_code, "faults": faults[:50]},
            )


def form_lines(root: ASTNode) -> int:
    """How many lines of the document lie inside forms, which are not chunked."""
    own = sum(node.end_line - node.start_line + 1 for node in root.children if node.node_type == "FORM")
    return own + sum(form_lines(child) for child in root.children if child.node_type != "FORM")


def _assert_paths_unique(
    chunks: list[ChunkEntity], doc_code: str
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
            label = str(chunk.metadata.get("index_label") or "?")
            collisions.append(f"{chunk.path} ({previous!r} vs {label!r})")
        else:
            seen[chunk.path] = str(chunk.metadata.get("index_label") or "?")

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
