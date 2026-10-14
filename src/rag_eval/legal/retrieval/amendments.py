from __future__ import annotations

import datetime
import itertools
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Final

import asyncpg

from rag_eval.legal.ingestion.citations import CitedLevels, Label, cited_divisions
from rag_eval.legal.ingestion.quotes import quote_spans
from rag_eval.legal.schemas.retrieval import AmendmentNote, SearchHit
from rag_eval.legal.text import Address, address_of_path, fold_diacritics

_VERB: Final = r"(?:sửa\s+đổi|bổ\s+sung|bãi\s+bỏ|thay\s+thế|hủy\s+bỏ|huỷ\s+bỏ|bỏ)"
_INSTRUCTION: Final = re.compile(
    rf"^\s*(?:(?:\d+[a-zđ]?\.|[a-zđ]\d*\))\s+)?(?P<action>{_VERB}(?:(?:\s*,\s*|\s+(?:và\s+)?){_VERB})*)(?!\w)",
    re.IGNORECASE,
)
_WORDING: Final = re.compile(r"^\s*(?:một\s+số\s+)?(?:cụm\s+)?từ(?!\w)", re.IGNORECASE)
_AT: Final = re.compile(r"(?<!\w)tại(?!\w)", re.IGNORECASE)
_REPLACEMENT: Final = re.compile(r"(?<!\w)bằng(?!\w)", re.IGNORECASE)
_POSITION: Final = re.compile(r"(?<!\w)vào\s+(?:sau|trước|cuối|đầu)(?!\w)", re.IGNORECASE)
_SEGMENT_END: Final = re.compile(r"(?<!\w)(?:vào\s+(?:sau|trước|cuối|đầu)|bằng|như\s+sau)(?!\w)|:", re.IGNORECASE)
_HEADING: Final = re.compile(r"(?<!\w)tên\s*$", re.IGNORECASE)
_TAIL_END: Final = re.compile(r"(?<!\w)như\s+sau(?!\w)|:", re.IGNORECASE)
_DOC_NUMBER: Final = re.compile(r"(?<![\w/])\d+(?:/\d{4})?/[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*")
_CHUNK_SUFFIX: Final = re.compile(r"\.(?:body|tail_\d+|w_\d+)$")

_LEVELS: Final = ("article", "clause", "point")

_CHUNKS: Final = r"""
SELECT d.doc_code                     AS doc_code,
       d.metadata->>'amends'          AS amends,
       c.path::text                   AS path,
       c.verbatim_text                AS text,
       c.metadata->>'article_title'   AS article_title,
       c.effective_date               AS effective_date
FROM chunks c
JOIN documents d ON d.id = c.document_id
ORDER BY d.doc_code, c.start_line
"""

Target = tuple[str | None, str | None, str | None, str | None]
Levels = dict[str, list[Label]]


@dataclass(frozen=True)
class _Instruction:
    doc_code: str
    node: str
    depth: int
    action: str
    text: str
    title: str
    effective_date: datetime.date
    declared_target: str | None


@dataclass(frozen=True)
class _Scope:
    doc_code: str | None
    levels: Levels


@dataclass(frozen=True)
class Amendment:
    doc_code: str
    label: str
    title: str
    action: str
    effective_date: datetime.date
    path: str
    target_doc: str
    targets: tuple[Target, ...]
    headings: frozenset[Target]


def _target(appendix: str | None, values: list[str | None]) -> Target:
    padded = [*values, None, None, None]
    return (appendix, padded[0], padded[1], padded[2])


@dataclass
class _Siblings:
    order: dict[tuple[str, Target, str], list[str]] = field(default_factory=dict)

    def add(self, doc_code: str, address: Address) -> None:
        values: list[str | None] = [address.dieu, address.khoan, address.diem]
        for depth, level in enumerate(_LEVELS):
            label = values[depth]
            if label is None:
                return
            labels = self.order.setdefault((doc_code, _target(address.appendix, values[:depth]), level), [])
            if label.lower() not in labels:
                labels.append(label.lower())

    def between(self, doc_code: str, parent: Target, level: str, first: str, last: str) -> list[str]:
        labels = self.order.get((doc_code, parent, level), [])
        if first not in labels or last not in labels:
            return []
        start, end = labels.index(first), labels.index(last)
        return labels[start : end + 1] if start <= end else []


def _masked(text: str) -> str:
    chars = list(text)
    for start, end in quote_spans(text).spans:
        for offset in range(start, end):
            if chars[offset] != "\n":
                chars[offset] = " "
    return "".join(chars)


def _node_of(chunk_path: str) -> str:
    return _CHUNK_SUFFIX.sub("", chunk_path)


def _article_of(node: str) -> str | None:
    segments = node.split(".")
    for index, segment in enumerate(segments):
        if segment.startswith("a_"):
            return ".".join(segments[: index + 1])
    return None


def _encloses(ancestor: _Instruction, node: _Instruction) -> bool:
    if ancestor.node == node.node:
        return ancestor.depth < node.depth
    return node.node.startswith(f"{ancestor.node}.")


def _named_document(text: str, known: dict[str, str]) -> str | None:
    match = _DOC_NUMBER.search(fold_diacritics(text))
    if match is None:
        return None
    return known.get(match.group(0).upper(), "")


def _target_segments(instruction: str) -> tuple[str, str]:
    if _WORDING.match(instruction):
        at = _AT.search(instruction)
        return (instruction[at.end() :] if at else "", "")
    end = _SEGMENT_END.search(instruction)
    segment = instruction[: end.start()] if end else instruction
    position = _POSITION.search(instruction)
    if position is None:
        return segment, ""
    tail = instruction[position.end() :]
    tail_end = _TAIL_END.search(tail)
    return segment, tail[: tail_end.start()] if tail_end else tail


def _lowered(label: Label) -> Label:
    if isinstance(label, tuple):
        return (label[0].lower(), label[1].lower())
    return label.lower()


def _levels_of(item: CitedLevels) -> Levels:
    return {
        str(name): [_lowered(label) for label in labels]
        for name, labels in item.items()
        if name in (*_LEVELS, "appendix")
    }


def _filled(levels: Levels, donors: list[Levels]) -> Levels:
    present = [index for index, level in enumerate(_LEVELS) if level in levels]
    if not present:
        return levels
    filled = dict(levels)
    for donor in donors:
        for level in _LEVELS[: min(present)]:
            if level not in filled and level in donor:
                filled[level] = donor[level]
    return filled


def _expand(levels: Levels, doc_code: str, siblings: _Siblings) -> list[Target]:
    appendices: list[str | None] = [str(label).upper() for label in levels.get("appendix", []) if isinstance(label, str)]
    if "article" not in levels:
        return [_target(appendix, []) for appendix in appendices]
    targets: list[Target] = [_target(appendix, []) for appendix in appendices or [None]]
    for depth, level in enumerate(_LEVELS):
        labels = levels.get(level)
        if labels is None:
            break
        grown: list[Target] = []
        for target in targets:
            for label in labels:
                named = siblings.between(doc_code, target, level, *label) if isinstance(label, tuple) else [label]
                grown.extend(_target(target[0], [*target[1 : depth + 1], value]) for value in named)
        targets = grown
    return targets


def _format_target(target: Target) -> str:
    appendix, dieu, khoan, diem = target
    return Address(dieu=dieu, khoan=khoan, diem=diem, appendix=appendix).format()


def _covers(target: Target, address: Address, heading: bool) -> bool:
    if target[0] != address.appendix:
        return False
    actual_levels = (address.dieu, address.khoan, address.diem)
    if heading:
        depth = sum(value is not None for value in target[1:])
        if depth < 3 and actual_levels[depth] is not None:
            return False
    for wanted, actual in zip(target[1:], actual_levels, strict=True):
        if wanted is None or actual is None:
            return True
        if wanted != actual.lower():
            return False
    return True


def _instructions(rows: list[asyncpg.Record]) -> list[_Instruction]:
    found: list[_Instruction] = []
    titled: set[str] = set()
    for row in rows:
        doc_code = str(row["doc_code"])
        node = _node_of(str(row["path"]))
        article = _article_of(node)
        title = str(row["article_title"] or "")
        effective_date: datetime.date = row["effective_date"]
        declared: str | None = row["amends"]
        lines: list[tuple[str, int, str]] = []
        if article is not None and title and article not in titled:
            titled.add(article)
            lines.append((article, 0, _masked(title)))
        lines.extend((node, 1, line) for line in _masked(str(row["text"])).split("\n"))
        for owner, depth, line in lines:
            match = _INSTRUCTION.match(line)
            if match is None:
                continue
            found.append(
                _Instruction(
                    doc_code=doc_code,
                    node=owner,
                    depth=depth,
                    action=" ".join(match.group("action").split()).lower(),
                    text=line[match.end() :],
                    title=title,
                    effective_date=effective_date,
                    declared_target=declared,
                )
            )
    return found


def _amendments(instructions: list[_Instruction], known: dict[str, str], siblings: _Siblings) -> list[Amendment]:
    found: list[Amendment] = []
    ordered = sorted(instructions, key=lambda item: (item.doc_code, item.node.count("."), item.depth))
    for _, group in itertools.groupby(ordered, key=lambda item: item.doc_code):
        members = list(group)
        scopes: list[_Scope] = []
        for index, instruction in enumerate(members):
            parent = next((i for i in reversed(range(index)) if _encloses(members[i], instruction)), None)
            if parent is None:
                declared = fold_diacritics(instruction.declared_target or "").upper()
                inherited = _Scope(doc_code=known.get(declared), levels={})
            else:
                inherited = scopes[parent]
            replacement = _REPLACEMENT.search(instruction.text)
            named = _named_document(instruction.text[: replacement.start()] if replacement else instruction.text, known)
            doc_code = inherited.doc_code if named is None or named == instruction.doc_code else named or None
            segment, tail = _target_segments(instruction.text)
            positions = [_levels_of(item.levels) for item in cited_divisions(tail)]
            targets: list[Target] = []
            headings: set[Target] = set()
            if doc_code is not None:
                for item in cited_divisions(segment):
                    levels = _filled(_levels_of(item.levels), [*positions, inherited.levels])
                    expanded = _expand(levels, doc_code, siblings)
                    targets.extend(expanded)
                    if item.opens_citation and _HEADING.search(segment[: item.start]):
                        headings.update(expanded)
            targets = list(dict.fromkeys(targets))
            scope_levels: Levels = inherited.levels
            if len(targets) == 1:
                scope_levels = {
                    level: [value] for level, value in zip(_LEVELS, targets[0][1:], strict=True) if value is not None
                }
            scopes.append(_Scope(doc_code=doc_code, levels=scope_levels))
            if doc_code is None or not targets or any(_encloses(instruction, other) for other in members[index + 1 :]):
                continue
            found.append(
                Amendment(
                    doc_code=instruction.doc_code,
                    label=address_of_path(instruction.node).format(),
                    title=instruction.title,
                    action=instruction.action,
                    effective_date=instruction.effective_date,
                    path=instruction.node,
                    target_doc=doc_code,
                    targets=tuple(targets),
                    headings=frozenset(headings),
                )
            )
    return found


IndexKey = tuple[str, str | None, str | None]


@dataclass(frozen=True)
class AmendmentIndex:
    amendments: tuple[Amendment, ...]
    by_target: dict[IndexKey, list[tuple[Amendment, Target]]]

    @classmethod
    def from_rows(cls, rows: list[asyncpg.Record]) -> AmendmentIndex:
        known = {fold_diacritics(str(row["doc_code"])).upper(): str(row["doc_code"]) for row in rows}
        siblings = _Siblings()
        for row in rows:
            siblings.add(str(row["doc_code"]), address_of_path(str(row["path"])))
        amendments = _amendments(_instructions(rows), known, siblings)
        by_target: dict[IndexKey, list[tuple[Amendment, Target]]] = defaultdict(list)
        for amendment in amendments:
            for target in amendment.targets:
                by_target[(amendment.target_doc, target[0], target[1])].append((amendment, target))
        return cls(amendments=tuple(amendments), by_target=dict(by_target))

    @classmethod
    async def load(cls, pool: asyncpg.Pool) -> AmendmentIndex:
        return cls.from_rows(await pool.fetch(_CHUNKS))

    def notes_for(self, hit: SearchHit, on_date: datetime.date) -> list[AmendmentNote]:
        address = address_of_path(hit.path)
        dieu = address.dieu.lower() if address.dieu else None
        keys: list[IndexKey] = [(hit.doc_code, address.appendix, dieu)]
        if address.appendix is not None and dieu is not None:
            keys.append((hit.doc_code, address.appendix, None))
        matched: dict[tuple[str, str], tuple[Amendment, list[Target]]] = {}
        for key in keys:
            for amendment, target in self.by_target.get(key, []):
                if amendment.effective_date > on_date or not _covers(target, address, target in amendment.headings):
                    continue
                entry = matched.setdefault((amendment.path, amendment.action), (amendment, []))
                if target not in entry[1]:
                    entry[1].append(target)
        ordered = sorted(matched.values(), key=lambda entry: (entry[0].effective_date, entry[0].path))
        return [
            AmendmentNote(
                doc_code=amendment.doc_code,
                label=amendment.label,
                title=amendment.title,
                action=amendment.action,
                target="; ".join(_format_target(target) for target in targets),
                effective_date=amendment.effective_date,
                path=amendment.path,
            )
            for amendment, targets in ordered
        ]

    def annotate(self, hits: list[SearchHit], on_date: datetime.date) -> list[SearchHit]:
        return [
            hit.model_copy(update={"amended_by": notes}) if (notes := self.notes_for(hit, on_date)) else hit
            for hit in hits
        ]
