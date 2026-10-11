"""Citation hints: phrases in a chunk that cite a provision, resolved on the parsed tree.

A hint gets target paths only when the phrase names a provision of this document without
ambiguity:

- it lies outside quoted text (an amending document quotes another document's wording);
- it is anchored by "này": either a division of the source itself ("khoản 2 Điều này",
  "Mục 1 Chương này") or the instrument that encloses the source ("Điều 5 Thông tư này",
  "Phụ lục I ban hành kèm theo Thông tư này"). An instrument is the document, or an
  appendix carrying its own articles (a Quy chế issued with a Thông tư). The document
  names itself by the type its title opens with, and an attached instrument by the
  generic types of attached instruments, so "Luật này" in a Nghị định anchors nothing;
- every division it names is found by (parent, kind, label) in the tree, uniquely.

Ranges ("từ khoản 1 đến khoản 3") expand over the real sibling order, so inserted
divisions (2a) are included; a range across levels ("từ khoản 1 Điều 1 đến khoản 1
Điều 2") is rejected whole. In a list, a higher division written once at the end is
shared by the items before it ("điểm a, điểm b khoản 6 Điều này"); an item that omits
it after a "này"-anchored item takes it from that item ("khoản 1 Điều này và điểm b
khoản 1"); an item with its own anchor resolves even when a sibling cites another
document. Ingestion turns the targets into edges.
"""

from __future__ import annotations

import bisect
import itertools
import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from rag_eval.legal.db.entities import ChunkEntity
from rag_eval.legal.ingestion.grammar import ORDINAL_WORDS, part_number
from rag_eval.legal.ingestion.parser import ASTNode, NodeType
from rag_eval.legal.ingestion.quotes import QuoteSpans, quote_spans

DivisionKind = Literal["part", "chapter", "section", "subsection", "article", "clause", "point", "appendix", "item"]

_NODE_KIND: dict[NodeType, DivisionKind] = {
    "PART": "part", "CHAPTER": "chapter", "SECTION": "section", "SUBSECTION": "subsection",
    "ARTICLE": "article", "CLAUSE": "clause", "POINT": "point", "APPENDIX": "appendix", "OUTLINE_ITEM": "item",
}
# Divisions cited by label from anywhere inside their instrument ("Điều 5 Thông tư này" under a Chương);
# khoản and điểm are cited only under their own parent, appendices only under the document.
_CITED_FROM_INSTRUMENT: frozenset[DivisionKind] = frozenset({"part", "chapter", "section", "subsection", "article"})

_ORDINAL = "|".join(sorted(ORDINAL_WORDS, key=len, reverse=True))
_ROMAN = r"[IVXLCDM]+"


@dataclass(frozen=True)
class _Keyword:
    """A division word as cited, the shape of one of its labels, the node kinds it names and its rank."""

    words: str
    label: str
    kinds: tuple[DivisionKind, ...]
    rank: int


_KEYWORDS: dict[str, _Keyword] = {
    "point": _Keyword("điểm", r"[a-zđ]\d*|\d+(?:\.\d+)+", ("point",), 0),
    "clause": _Keyword("khoản", r"\d+(?:\.\d+)*[a-zđ]?", ("clause",), 1),
    "article": _Keyword("điều", r"\d+[a-zđ]?", ("article",), 2),
    "subsection": _Keyword("tiểu mục", rf"\d+[a-zđ]?|{_ROMAN}", ("subsection",), 3),
    "section": _Keyword("mục", rf"\d+(?:\.\d+)*[a-zđ]?|{_ROMAN}|[A-Z](?:\.\d+)*", ("section", "item"), 4),
    "chapter": _Keyword("chương", rf"{_ROMAN}[a-zđ]?|\d+[a-zđ]?", ("chapter",), 5),
    "part": _Keyword("phần", rf"(?i:thứ)\s+(?i:{_ORDINAL})|{_ROMAN}[a-zđ]?|\d+[a-zđ]?", ("part",), 6),
    "appendix": _Keyword(
        "phụ lục", rf"(?:số\s+)?(?:{_ROMAN}|\d+|[A-Z])(?:[a-zđ]|[.\-–](?:{_ROMAN}|\d+|[A-Z]))*", ("appendix",), 7
    ),
}
_HEADING_KEYWORDS = frozenset({"part", "chapter", "section", "subsection", "article", "appendix"})

# Document types as a document names itself, longest first so "thông tư liên tịch" is not read as "thông tư".
_DOC_TYPES: tuple[str, ...] = (
    "thông tư liên tịch", "nghị quyết liên tịch", "văn bản hợp nhất", "bộ luật", "nghị định", "thông tư",
    "luật", "pháp lệnh", "nghị quyết", "quyết định", "chỉ thị", "quy chuẩn", "quy chế", "quy định", "điều lệ",
    "văn bản",
)
# "văn bản này" names the document whatever its type.
_GENERIC_TYPES = frozenset({"văn bản", "văn bản hợp nhất"})
# The instruments a document issues as attachments ("ban hành kèm theo Thông tư này Quy chế …").
_ATTACHED_TYPES = frozenset({"quy chế", "quy định", "điều lệ", "quy chuẩn", "văn bản"})
_QUY_CHUAN_TAIL = r"(?:\s+kỹ\s+thuật(?:\s+quốc\s+gia)?)?"

_ANCHOR = "này"

Label = str | tuple[str, str]  # one label, or the endpoints of a range


def _words_re(words: str) -> str:
    return r"\s+".join(f"(?i:{word})" for word in words.split())


def _label_re(keyword: _Keyword) -> str:
    # A numeric label is never cut before ".<digit>": "khoản 1.2" is not "khoản 1".
    return rf"(?<!\w)(?:{keyword.label})(?!\w)(?!\.\d)"


def _group_re(keyword: _Keyword) -> str:
    words, label = _words_re(keyword.words), _label_re(keyword)
    labels = rf"{label}(?:\s*(?:,|;|(?i:và|hoặc))\s*{label}|\s+(?i:đến)\s+(?:{words}\s+)?{label})*"
    return rf"(?:(?i:các)\s+)?(?:(?i:từ)\s+)?{words}\s+(?:(?i:{_ANCHOR})(?!\w)|{labels})"


_DOC_TYPE_RE = "|".join(
    _words_re(t) + (_QUY_CHUAN_TAIL if t == "quy chuẩn" else "") for t in _DOC_TYPES
)
_ANY_GROUP = "|".join(f"(?:{_group_re(k)})" for k in _KEYWORDS.values())
_QUALIFIER = (
    rf"\s+(?:(?i:của|trong|tại|(?:được\s+)?(?:ban\s+hành\s+)?kèm\s+theo)\s+)?"
    rf"(?P<doctype>{_DOC_TYPE_RE})\s+(?i:{_ANCHOR})(?!\w)"
)
_CHAIN = rf"(?:{_ANY_GROUP})(?:\s+(?:(?i:của)\s+)?(?:{_ANY_GROUP}))*"
_LIST_SEP = r"(?:\s*[,;]\s*(?:(?i:và|hoặc)\s+)?|\s+(?i:và|hoặc)\s+)"
_ITEM = rf"{_CHAIN}(?:\s*\(\s*{_CHAIN}(?:{_LIST_SEP}{_CHAIN})*\s*\))?"
_CITATION_RE = re.compile(rf"(?<!\w){_ITEM}(?:{_LIST_SEP}{_ITEM})*(?P<qualifier>{_QUALIFIER})?")
_TOKEN_RE = re.compile(
    r"(?P<open>\()|(?P<close>\))|(?P<sep>[,;]|(?<!\w)(?i:và|hoặc)(?!\w))|"
    + "|".join(f"(?P<{name}>{_group_re(k)})" for name, k in _KEYWORDS.items())
)
_LABEL_TOKEN_RE: dict[str, re.Pattern[str]] = {
    name: re.compile(rf"(?<!\w)(?i:đến)(?!\w)|{_label_re(k)}") for name, k in _KEYWORDS.items()
}
_GROUP_HEAD_RE: dict[str, re.Pattern[str]] = {
    name: re.compile(rf"^(?:(?i:các)\s+)?(?:(?i:từ)\s+)?{_words_re(k.words)}\s+") for name, k in _KEYWORDS.items()
}
_KEYWORD_WORDS_RE: dict[str, re.Pattern[str]] = {name: re.compile(_words_re(k.words)) for name, k in _KEYWORDS.items()}
# A phrase that names another document after the citation: its trailing items belong to that document.
_EXTERNAL_TAIL = re.compile(rf"\s+(?:(?i:của|trong|tại)\s+)?(?:{_DOC_TYPE_RE}|(?i:số))(?!\w)")
# One end of a range whose other end is a different chain ("từ khoản 1 Điều 1 đến khoản 1 Điều 2").
_RANGE_AFTER = re.compile(
    rf"\s+(?i:đến)\s+(?:(?i:các)\s+)?(?:{'|'.join(_words_re(k.words) for k in _KEYWORDS.values())})(?!\w)"
)
_RANGE_BEFORE = re.compile(r"(?<!\w)(?i:đến)\s+$")
# A division word with a label this grammar does not read ("điểm 5.1.1 tiểu mục 5.1 …"): the citation's lowest
# division was not understood, so what follows is a fragment of it.
_CUT_BEFORE = re.compile(
    rf"(?:(?<!\w)(?:{'|'.join(_words_re(k.words) for k in _KEYWORDS.values())})\s+\S+|(?<!\w)(?i:tiểu))\s+$"
)
_HEADING_TAIL_RE = re.compile(r"[ \t]*(?:[.:]|\n|$)")
_SENTENCE_END = (".", ":", ";", "”", '"')
_CHUNK_SUFFIX = re.compile(r"(?:\.body)?(?:\.w_\d+)?$")
_LEADING_ZEROS = re.compile(r"(?<!\d)0+(?=\d)")


@dataclass(frozen=True)
class CitationHint:
    """A phrase in a chunk that likely cites another provision; target_paths only when unambiguous."""

    text: str
    char_start: int
    char_end: int
    target_paths: tuple[str, ...]


@dataclass
class _Item:
    """One coordinated reference of a citation: labels per keyword, None for "này"."""

    levels: dict[str, list[Label] | None]
    parent: int | None  # the item a parenthesised item narrows
    stated: frozenset[str] = frozenset()  # the keywords written in the item itself, before any borrowing

    @property
    def top(self) -> int:
        return max(_KEYWORDS[k].rank for k in self.levels)

    @property
    def lowest(self) -> int:
        return min(_KEYWORDS[k].rank for k in self.levels)

    @property
    def anchored(self) -> bool:
        return None in self.levels.values()


def _normalize(label: str) -> str:
    """A label in the form both citations and headings reduce to: "số 01" → "1", "I–A" → "i-a"."""
    text = label.strip().removeprefix("số").strip().rstrip(".").replace("–", "-").lower()
    return _LEADING_ZEROS.sub("", text)


def _node_label(node: ASTNode) -> str | None:
    """The normalized label a node is cited by; None for an unnumbered appendix or attachment."""
    if node.node_type == "OUTLINE_ITEM":
        return _normalize(node.index_label)
    if node.node_type == "APPENDIX":
        number = node.index_label.removeprefix("Phụ lục").strip()
        return _normalize(number) if number and node.index_label.startswith("Phụ lục") else None
    words = node.index_label.split()
    return _normalize(words[-1]) if len(words) > 1 else None


class NodeIndex:
    """Lookup of parsed nodes by (parent path, division kind, normalized label); built from the AST, never from chunk paths."""

    def __init__(self, root: ASTNode) -> None:
        self.root = root.full_path
        self._nodes: dict[str, ASTNode] = {}
        self._parent: dict[str, str] = {}
        self._labels: dict[str, str] = {}
        self._instrument: dict[str, str] = {}
        # (parent path, kind) -> [(normalized label, path)] in document order.
        self._children: dict[tuple[str, DivisionKind], list[tuple[str, str]]] = defaultdict(list)
        self._instruments = _attached_instruments(root)
        self._walk(root, [root])

    @classmethod
    def build(cls, root: ASTNode) -> NodeIndex:
        return cls(root)

    def _walk(self, node: ASTNode, ancestors: list[ASTNode]) -> None:
        for child in node.children:
            self._nodes[child.full_path] = child
            self._parent[child.full_path] = node.full_path
            lineage = [*ancestors, child]
            self._instrument[child.full_path] = next(
                (n.full_path for n in reversed(lineage) if n.full_path in self._instruments), self.root
            )
            kind = _NODE_KIND.get(child.node_type)
            label = _node_label(child)
            if kind is not None and label is not None:
                self._labels[child.full_path] = label
                for holder in self._holders(kind, child, ancestors):
                    self._children[(holder, kind)].append((label, child.full_path))
            self._walk(child, lineage)

    def _holders(self, kind: DivisionKind, node: ASTNode, ancestors: list[ASTNode]) -> list[str]:
        """The parent paths a node is cited under: its parent, and for higher divisions every ancestor up to its scope."""
        parent = ancestors[-1].full_path
        if kind not in _CITED_FROM_INSTRUMENT and kind != "item":
            return [parent]
        holders: list[str] = []
        for ancestor in reversed(ancestors):
            holders.append(ancestor.full_path)
            # An outline item is cited within its appendix; a higher division within its instrument.
            if ancestor.node_type == "APPENDIX" and (kind == "item" or ancestor.full_path in self._instruments):
                break
        return holders

    def _candidates(self, parent: str, kind: DivisionKind, label: str) -> list[str]:
        siblings = self._children.get((parent, kind), [])
        found = [path for key, path in siblings if key == label]
        if not found and kind in ("clause", "point") and "." in label:
            # A decimal-numbered khoản or điểm ("6.3." under Điều 6, "6.3.3." under it) is cited with the
            # numbers of its article and khoản in front.
            prefix = self._decimal_prefix(parent)
            if prefix and label.startswith(f"{prefix}."):
                stripped = label.removeprefix(f"{prefix}.")
                return [path for key, path in siblings if key == stripped]
        return found

    def _decimal_prefix(self, parent: str) -> str:
        """The dotted number of a parent within its article ("6" for Điều 6, "6.3" for its khoản 3)."""
        numbers: list[str] = []
        current: str | None = parent
        while current is not None and current in self._labels:
            node_type = self._nodes[current].node_type
            if node_type not in ("ARTICLE", "CLAUSE"):
                break
            numbers.append(self._labels[current])
            if node_type == "ARTICLE":
                return ".".join(reversed(numbers))
            current = self._parent.get(current)
        return ""

    def child(self, parent: str, kind: DivisionKind, label: str) -> str | None:
        """The unique child path, or None when absent or ambiguous."""
        found = self._candidates(parent, kind, _normalize(label))
        return found[0] if len(found) == 1 else None

    def children_between(self, parent: str, kind: DivisionKind, first: str, last: str) -> list[str] | None:
        """Ordered sibling paths from `first` to `last` inclusive; None when either endpoint is missing."""
        start, end = self.child(parent, kind, first), self.child(parent, kind, last)
        if start is None or end is None:
            return None
        order = [path for _, path in self._children[(parent, kind)]]
        lo, hi = order.index(start), order.index(end)
        return order[lo : hi + 1] if lo <= hi else None

    def instrument_of(self, path: str) -> str:
        """The path of the instrument enclosing `path`: the document root, or the attachment/appendix that carries its own articles."""
        return self._instrument.get(path, self.root)

    def node_of_chunk(self, chunk_path: str) -> str:
        """The node a chunk holds text of (its own span `.body` and its windows `.w_n` belong to the node)."""
        path = _CHUNK_SUFFIX.sub("", chunk_path)
        if path not in self._nodes:
            raise KeyError(f"chunk '{chunk_path}' belongs to no node of the parsed tree")
        return path

    def nearest(self, path: str, kinds: tuple[DivisionKind, ...]) -> str | None:
        """The node itself or its nearest ancestor of one of `kinds`, or None."""
        current: str | None = path
        while current is not None and current in self._nodes:
            if _NODE_KIND.get(self._nodes[current].node_type) in kinds:
                return current
            current = self._parent.get(current)
        return None


def _attached_instruments(root: ASTNode) -> frozenset[str]:
    """Paths of the appendices that carry their own articles: instruments issued with the document."""

    def has_articles(node: ASTNode) -> bool:
        return any(child.node_type == "ARTICLE" or has_articles(child) for child in node.children)

    return frozenset(child.full_path for child in root.children if child.node_type == "APPENDIX" and has_articles(child))


def _doc_type(words: str) -> str:
    """A document type as named ("Quy chuẩn kỹ thuật quốc gia" → "quy chuẩn")."""
    text = " ".join(words.lower().split())
    return next(t for t in _DOC_TYPES if text.startswith(t))


def _own_type(title: str) -> str | None:
    """The type a document's title opens with ("Nghị định quy định …" → "nghị định"); None when it names none."""
    text = " ".join(title.lower().split())
    return next((t for t in _DOC_TYPES if text.startswith(f"{t} ") or text == t), None)


@dataclass(frozen=True)
class _Scanner:
    index: NodeIndex
    own_type: str | None
    quotes: QuoteSpans
    line_starts: list[int]

    def instrument(self, doctype: str, source: str) -> str | None:
        """The instrument a "<type> này" qualifier names from `source`, or None when it names none."""
        named = _doc_type(doctype)
        enclosing = self.index.instrument_of(source)
        if enclosing == self.index.root:
            ok = self.own_type is None or self._names_document(named) or named in _GENERIC_TYPES
            return enclosing if ok else None
        if self._names_document(named):
            return self.index.root
        return enclosing if named in _ATTACHED_TYPES else None

    def _names_document(self, named: str) -> bool:
        """True when a type names this document, in full or shortened ("Thông tư này" in a Thông tư liên tịch)."""
        own = self.own_type
        return own is not None and (named == own or own.startswith(f"{named} "))

    def hints(self, chunk: ChunkEntity) -> list[CitationHint]:
        text = chunk.verbatim_text
        source = self.index.node_of_chunk(chunk.path)
        offsets = list(itertools.accumulate((len(line) + 1 for line in text.split("\n")), initial=0))

        def raw_offset(position: int) -> int:
            line = bisect.bisect_right(offsets, position) - 1
            return self.line_starts[chunk.start_line - 1 + line] + position - offsets[line]

        hints: list[CitationHint] = []
        for match in _CITATION_RE.finditer(text):
            items = _parse_items(match.group(0))
            doctype = match.group("doctype")
            if doctype is None and _is_heading(text, match, items):
                continue
            start, end = match.start(), match.end()
            quoted = self.quotes.contains(raw_offset(start)) or self.quotes.contains(raw_offset(end - 1))
            ranged = bool(_RANGE_AFTER.match(text, end)) or bool(_RANGE_BEFORE.search(text, max(0, start - 8), start))
            cut = bool(_CUT_BEFORE.search(text, max(0, start - 40), start))
            targets: list[str] = []
            if not quoted and not ranged and not cut:
                external = doctype is None and bool(_EXTERNAL_TAIL.match(text, end))
                instrument = self.instrument(doctype, source) if doctype is not None else None
                resolved = self._resolve_items(items, source, instrument, borrow_back=not external)
                if resolved is not None:
                    targets = [t for t in resolved if t != chunk.path and not chunk.path.startswith(f"{t}.")]
                    if not targets:
                        # Every item names the chunk itself or a division that contains it: no edge can exist.
                        continue
            hints.append(CitationHint(text=match.group(0), char_start=start, char_end=end, target_paths=tuple(targets)))
        return hints

    def _resolve_items(self, items: list[_Item], source: str, instrument: str | None, *, borrow_back: bool) -> list[str] | None:
        """Targets of a citation's items, or None when nothing resolves with certainty.

        An item anchored by its own "này" resolves on its own; the others depend on a shared
        tail or the qualifier, so they resolve together or not at all.
        """
        if borrow_back:
            _borrow_backward(items)
        # A parenthesised item that borrows its parent's divisions narrows it, so the parent is no target itself.
        narrowed = {
            item.parent for item in items
            if item.parent is not None and item.parent >= 0 and any(k not in item.stated for k in items[item.parent].stated)
        }
        own: list[str] = []
        shared: list[str] = []
        shared_ok = True
        for idx, item in enumerate(items):
            if idx in narrowed:
                continue
            paths = self._resolve(item, source, instrument)
            if item.anchored and item.stated & {k for k, v in item.levels.items() if v is None}:
                own.extend(paths or [])
            elif paths is None:
                shared_ok = False
            else:
                shared.extend(paths)
        found = own + (shared if shared_ok else [])
        return list(dict.fromkeys(found)) if found else None

    def _resolve(self, item: _Item, source: str, instrument: str | None) -> list[str] | None:
        anchors = [k for k, labels in item.levels.items() if labels is None]
        if len(anchors) > 1:
            return None
        if anchors:
            anchor = _KEYWORDS[anchors[0]]
            if item.top > anchor.rank:
                return None
            base = self.index.nearest(source, anchor.kinds)
            below = [k for k in item.levels if _KEYWORDS[k].rank < anchor.rank]
        else:
            base = instrument
            below = list(item.levels)
        if base is None:
            return None
        paths = [base]
        spread = 0
        for name in sorted(below, key=lambda k: _KEYWORDS[k].rank, reverse=True):
            labels = item.levels[name]
            assert labels is not None
            if len(labels) > 1 or isinstance(labels[0], tuple):
                spread += 1
                if spread > 1:
                    return None  # "điểm a, b khoản 1, 2": which points of which khoản is not stated
            found: list[str] = []
            for parent in paths:
                for label in labels:
                    hit = self._lookup(parent, _KEYWORDS[name].kinds, label)
                    if hit is None:
                        return None
                    found.extend(hit)
            paths = found
        return paths

    def _lookup(self, parent: str, kinds: tuple[DivisionKind, ...], label: Label) -> list[str] | None:
        """The nodes a label (or range) names under `parent`; with several kinds ("mục"), exactly one kind must answer."""
        answers: list[list[str]] = []
        for kind in kinds:
            if isinstance(label, tuple):
                between = self.index.children_between(parent, kind, *label)
                if between is not None:
                    answers.append(between)
            else:
                hit = self.index.child(parent, kind, label)
                if hit is not None:
                    answers.append([hit])
        return answers[0] if len(answers) == 1 else None


def scan_citation_hints(raw_text: str, root: ASTNode, chunks: Sequence[ChunkEntity]) -> dict[str, list[CitationHint]]:
    """Citation hints per chunk path; targets only for "này"-anchored citations outside quotes that resolve uniquely in the tree."""
    scanner = _Scanner(
        index=NodeIndex.build(root),
        own_type=_own_type(root.title),
        quotes=quote_spans(raw_text),
        line_starts=list(itertools.accumulate((len(line) for line in raw_text.splitlines(keepends=True)), initial=0)),
    )
    return {chunk.path: scanner.hints(chunk) for chunk in chunks}


def _parse_items(citation: str) -> list[_Item]:
    """Splits a citation into its coordinated items and fills each item's missing higher divisions from later items.

    A new item starts at every list separator, wherever a division does not climb above
    the previous one ("điểm b khoản 8, khoản 9" is two items), and after a "này" anchor,
    which always closes its item. A parenthesised item belongs to the item before the
    parenthesis ("Điều 20 (điểm c khoản 3)") and takes its divisions. Any other item
    lacking a higher division takes it from the nearest later item that states it above
    that item's own lowest division -- the shared tail.
    """
    items: list[_Item] = []
    parents: list[int] = []
    current: _Item | None = None
    for token in _TOKEN_RE.finditer(citation):
        name = token.lastgroup
        if name == "open":
            parents.append(len(items) - 1)
            current = None
        elif name == "close":
            if parents:
                parents.pop()
            current = None
        elif name == "sep":
            current = None
        elif name is not None:
            rank = _KEYWORDS[name].rank
            if current is None or current.anchored or current.top >= rank:
                current = _Item(levels={}, parent=parents[-1] if parents else None)
                items.append(current)
            current.levels[name] = _parse_labels(name, token.group(0))

    for item in items:
        item.stated = frozenset(item.levels)
    for idx, item in enumerate(items):
        for name in sorted(_KEYWORDS, key=lambda k: _KEYWORDS[k].rank):
            if name in item.levels or _KEYWORDS[name].rank <= item.top or item.anchored:
                continue
            if item.parent is not None and item.parent >= 0:
                parent = items[item.parent]
                if name in parent.levels:
                    item.levels[name] = parent.levels[name]
                continue
            for donor in items[idx + 1 :]:
                if donor.parent is None and name in donor.stated and _KEYWORDS[name].rank > donor.lowest:
                    item.levels[name] = donor.levels[name]
                    break
    return items


def _borrow_backward(items: list[_Item]) -> None:
    """An item still without an anchor takes the higher divisions of the "này"-anchored item just before it."""
    for previous, item in itertools.pairwise(items):
        if item.parent is not None or item.anchored or previous.parent is not None or not previous.anchored:
            continue
        for name, labels in previous.levels.items():
            if name not in item.levels and _KEYWORDS[name].rank > item.top:
                item.levels[name] = labels


def _parse_labels(name: str, group_text: str) -> list[Label] | None:
    body = _GROUP_HEAD_RE[name].sub("", group_text)
    if re.fullmatch(rf"(?i:{_ANCHOR})", body):
        return None
    body = _KEYWORD_WORDS_RE[name].sub(" ", body)
    labels: list[Label] = []
    pending_range = False
    for token in _LABEL_TOKEN_RE[name].finditer(body):
        value = token.group(0)
        if value.lower() == "đến":
            pending_range = True
            continue
        if name == "part":
            value = part_number(" ".join(value.split()))
        previous = labels[-1] if labels else None
        if pending_range and isinstance(previous, str):
            labels[-1] = (previous, value)
        else:
            labels.append(value)
        pending_range = False
    return labels


def _is_heading(text: str, match: re.Match[str], items: list[_Item]) -> bool:
    """True for a division heading line such as "Điều 2. Đối tượng áp dụng" or a quoted "“Điều 5. …".

    A heading opens its own line after a finished sentence (or the text start); the same
    words wrapped onto a new line mid-sentence are a citation.
    """
    line_start = text.rfind("\n", 0, match.start()) + 1
    if text[line_start : match.start()].strip().lstrip("“\""):
        return False
    if line_start > 0:
        previous = text[:line_start].rstrip("\n").rsplit("\n", 1)[-1].strip()
        if previous and not previous.endswith(_SENTENCE_END) and not previous.isupper():
            return False
    if len(items) != 1 or len(items[0].levels) != 1:
        return False
    name, labels = next(iter(items[0].levels.items()))
    if name not in _HEADING_KEYWORDS or labels is None or len(labels) != 1:
        return False
    return _HEADING_TAIL_RE.match(text, match.end()) is not None
