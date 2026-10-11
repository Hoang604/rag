"""Builds the division tree of one canonical text from its tokens.

The open divisions form a stack. A heading closes every open division that cannot
contain it (a Chương closes the open Điều and Mục, never the Phần above it) and opens
its own; an outline item nests under the open item whose key prefixes its own. A body
line belongs to the innermost open division, except a line that follows a list of
điểm closed by a full stop: it belongs to the list's parent as a TAIL, since the list
has ended -- unless another điểm follows it, which shows the list had not ended and the
text continues the điểm before it. Lines before the first structural token are the PREAMBLE.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from rag_eval.legal.ingestion.lexer import LegalLexer, LegalToken, TokenType
from rag_eval.legal.text import (
    sanitize_index_label,
    sanitize_ltree_label,
    validate_ltree_path,
)

NodeType = Literal[
    "DOCUMENT", "PREAMBLE", "PART", "CHAPTER", "SECTION", "SUBSECTION", "ARTICLE", "CLAUSE", "POINT",
    "APPENDIX", "OUTLINE_ITEM", "FORM", "TAIL", "POSTAMBLE",
]


@dataclass
class ASTNode:
    """One division of a document, with the line range it spans."""

    node_type: NodeType
    index_label: str
    title: str
    full_path: str
    heading_end_line: int  # last title line; start_line - 1 when the node has no title line (CLAUSE/POINT/OUTLINE_ITEM/TAIL/PREAMBLE/POSTAMBLE/FORM and an untitled attachment)
    start_line: int
    end_line: int
    parent_path: str | None = None  # None only for DOCUMENT
    # A clause's or outline item's stem, an article's lead-in: its text before its first child.
    lead_sentence: str = ""
    children: list[ASTNode] = field(default_factory=list)
    # An OUTLINE_ITEM's outline key; empty for every other node.
    outline: tuple[str, ...] = ()


# The divisions each heading may sit directly under; a heading closes open divisions until it reaches one.
_PARENTS: dict[NodeType, frozenset[NodeType]] = {
    "APPENDIX": frozenset({"DOCUMENT"}),
    "POSTAMBLE": frozenset({"DOCUMENT"}),
    "PART": frozenset({"APPENDIX", "DOCUMENT"}),
    "CHAPTER": frozenset({"PART", "APPENDIX", "DOCUMENT"}),
    "SECTION": frozenset({"CHAPTER", "PART", "APPENDIX", "DOCUMENT"}),
    "SUBSECTION": frozenset({"SECTION", "CHAPTER", "PART", "APPENDIX", "DOCUMENT"}),
    "ARTICLE": frozenset({"SUBSECTION", "SECTION", "CHAPTER", "PART", "APPENDIX", "DOCUMENT"}),
    "FORM": frozenset({"APPENDIX"}),
}
_SEGMENT_PREFIX: dict[NodeType, str] = {
    "PART": "part_", "CHAPTER": "c_", "SECTION": "s_", "SUBSECTION": "ss_", "ARTICLE": "a_",
    "CLAUSE": "c_", "POINT": "p_", "APPENDIX": "app_", "OUTLINE_ITEM": "i_", "FORM": "form_",
}
_HEADINGS: dict[TokenType, NodeType] = {
    "PART": "PART", "CHAPTER": "CHAPTER", "SECTION": "SECTION", "SUBSECTION": "SUBSECTION",
    "ARTICLE": "ARTICLE", "APPENDIX": "APPENDIX",
}
_UNNUMBERED_APPENDIX_LABEL = "Phụ lục"
_ATTACHMENT_LABEL = "Văn bản kèm theo"
_POSTAMBLE_LABEL = "Nơi nhận và chữ ký"


def _disambiguate(parent: ASTNode, segment: str) -> str:
    """Returns a segment unique among `parent`'s children, suffixing if needed.

    A label repeats under one parent where the source repeats it (a consolidated text
    restating a list) or where a heading was not recognised. Dropping or overwriting
    the later provision loses statute, so the path is made unique instead; the suffix
    records that the hierarchy here is approximate while the text stays exact.
    """
    taken = {child.full_path.rsplit(".", 1)[-1] for child in parent.children}
    if segment not in taken:
        return segment
    ordinal = 2
    while f"{segment}_{ordinal}" in taken:
        ordinal += 1
    return f"{segment}_{ordinal}"


def _outline_parent(parent: tuple[str, ...], child: tuple[str, ...]) -> bool:
    """True when an item keyed `parent` encloses one keyed `child`: its key is a proper prefix."""
    return len(parent) < len(child) and child[: len(parent)] == parent


def _label_number(token: LegalToken) -> str:
    """The number part of a token's label ("12đ" of "Điều 12đ", "01" of "Mẫu số 01")."""
    if token.token_type == "OUTLINE_ITEM":
        return token.outline[-1]
    words = token.index_label.split()
    return words[-1] if len(words) > 1 else ""


class LegalASTParser:
    """Parses canonical statutory text into a tree of ASTNode objects."""

    def __init__(self, doc_code: str) -> None:
        self.doc_code = doc_code
        self.doc_prefix = sanitize_ltree_label(doc_code)
        self.lexer = LegalLexer()

    def parse(self, text: str, doc_title: str = "") -> ASTNode:
        """Parses the whole document text into a root ASTNode with nested children."""
        root = ASTNode(
            node_type="DOCUMENT",
            index_label=self.doc_code,
            title=doc_title or self.doc_code,
            full_path=self.doc_prefix,
            heading_end_line=0,
            start_line=1,
            end_line=max(1, len(text.splitlines())),
        )
        _Build(root).run(self.lexer.tokenize(text))
        return root


class _Build:
    """The open-division stack of one parse."""

    def __init__(self, root: ASTNode) -> None:
        self.root = root
        self.stack: list[ASTNode] = [root]
        self.unnumbered_appendices = 0

    def run(self, tokens: list[LegalToken]) -> None:
        for token in tokens:
            self._token(token)
        _close_end_lines(self.root)

    @property
    def top(self) -> ASTNode:
        return self.stack[-1]

    def _push(self, node_type: NodeType, segment: str, token: LegalToken, *, title: str = "", lead: str = "", heading_end: int | None = None) -> ASTNode:
        parent = self.top
        path = validate_ltree_path(f"{parent.full_path}.{_disambiguate(parent, segment)}")
        node = ASTNode(
            node_type=node_type,
            index_label=token.index_label,
            title=title,
            full_path=path,
            heading_end_line=token.line_number - 1 if heading_end is None else heading_end,
            start_line=token.line_number,
            end_line=max(token.line_number, token.last_line),
            parent_path=parent.full_path,
            lead_sentence=lead,
            outline=token.outline,
        )
        parent.children.append(node)
        self.stack.append(node)
        return node

    def _close_until(self, parents: frozenset[NodeType]) -> None:
        while self.top.node_type not in parents:
            self.stack.pop()

    def _token(self, token: LegalToken) -> None:
        kind = token.token_type
        if kind == "APPENDIX" and token.index_label == _UNNUMBERED_APPENDIX_LABEL or kind == "ATTACHMENT":
            self._close_until(_PARENTS["APPENDIX"])
            self._push_unnumbered_appendix(token)
        elif kind in _HEADINGS:
            node_type = _HEADINGS[kind]
            self._close_until(_PARENTS[node_type])
            self._push(node_type, f"{_SEGMENT_PREFIX[node_type]}{sanitize_index_label(_label_number(token))}", token,
                       title=token.title, heading_end=token.last_line,
                       lead=token.content if kind == "ARTICLE" and token.last_line < token.line_number else "")
        elif kind == "POSTAMBLE":
            self._close_until(_PARENTS["POSTAMBLE"])
            self._push("POSTAMBLE", "postamble", token).index_label = _POSTAMBLE_LABEL
        elif kind == "FORM":
            self._close_until(_PARENTS["FORM"])
            self._push("FORM", f"form_{sanitize_index_label(_label_number(token))}", token)
        elif kind == "OUTLINE_ITEM":
            while self.top.node_type in ("POINT", "TAIL", "FORM", "CLAUSE", "ARTICLE") or (
                self.top.node_type == "OUTLINE_ITEM" and not _outline_parent(self.top.outline, token.outline)
            ):
                self.stack.pop()
            self._push("OUTLINE_ITEM", f"i_{sanitize_index_label(token.outline[-1])}", token, lead=token.content)
        elif kind == "CLAUSE":
            self._enumeration(token, "CLAUSE", frozenset({"ARTICLE"}), frozenset({"POINT", "TAIL", "CLAUSE"}))
        elif kind == "POINT":
            self._enumeration(token, "POINT", frozenset({"CLAUSE", "ARTICLE", "OUTLINE_ITEM", "APPENDIX"}), frozenset({"POINT", "TAIL"}))
        else:
            self._body(token)

    def _push_unnumbered_appendix(self, token: LegalToken) -> None:
        self.unnumbered_appendices += 1
        node = self._push("APPENDIX", f"app_u{self.unnumbered_appendices}", token, title=token.title, heading_end=token.last_line)
        if token.token_type == "ATTACHMENT":
            node.index_label = _ATTACHMENT_LABEL

    def _enumeration(self, token: LegalToken, node_type: NodeType, parents: frozenset[NodeType], closes: frozenset[NodeType]) -> None:
        """Opens a khoản or điểm under its parent; with no parent open, the line is body text of what is open."""
        depth = len(self.stack)
        while self.stack[depth - 1].node_type in closes:
            depth -= 1
        if self.stack[depth - 1].node_type not in parents:
            self._body(token)
            return
        del self.stack[depth:]
        siblings = self.top.children
        if node_type == "POINT" and len(siblings) >= 2 and siblings[-1].node_type == "TAIL" and siblings[-2].node_type == "POINT":
            # Closing text follows a list's last điểm; text followed by another điểm continues the one before it.
            tail = siblings.pop()
            siblings[-1].end_line = tail.end_line
        self._push(node_type, f"{_SEGMENT_PREFIX[node_type]}{sanitize_index_label(_label_number(token))}", token, lead=token.content)

    def _body(self, token: LegalToken) -> None:
        line = token.line_number
        node = self.top
        if node is self.root:
            preamble = self.root.children[-1] if self.root.children else None
            if preamble is None or preamble.node_type != "PREAMBLE":
                self._push("PREAMBLE", "pre_1", token).index_label = "Căn cứ ban hành"
                self.stack.pop()  # the preamble holds body lines only while nothing structural has opened
                return
            node = preamble
        elif node.node_type == "POINT" and _closes_list(token, node):
            self.stack.pop()
            tails = sum(child.node_type == "TAIL" for child in self.top.children)
            self._push("TAIL", f"tail_{tails + 1}", token)
            return
        node.end_line = line
        if not node.children and node.node_type in ("CLAUSE", "POINT", "OUTLINE_ITEM", "ARTICLE"):
            node.lead_sentence = f"{node.lead_sentence}\n{token.content}".strip()


def _closes_list(token: LegalToken, point: ASTNode) -> bool:
    """True when a body line follows a list of điểm the open điểm closed with a full stop, and starts a new sentence.

    Drafting ends each điểm with ";" and the last with ".", so a capitalised line after a
    full stop is no longer part of the list but text of the division that holds it.
    """
    text = token.content
    return point.lead_sentence.rstrip().endswith(".") and text[:1].isupper()


def _close_end_lines(node: ASTNode) -> int:
    """Extends every node's end_line over its descendants and returns it."""
    for child in node.children:
        node.end_line = max(node.end_line, _close_end_lines(child))
    return node.end_line
