"""Extracts statutory cross-references and resolves them to chunk paths.

Vietnamese statutes are written as a graph, not a list. A clause reading "trừ
các hành vi vi phạm quy định tại điểm a, điểm c khoản 2 Điều 6" is *incomplete*
on its own: retrieved alone it states a penalty whose exceptions are invisible,
and an agent answering from it is confidently wrong. Retrieval cannot recover
what ingestion did not record, so the reference has to become an edge.

Three relation types are assigned, all from explicit drafting cues:

* MODIFIES_AND_REPLACES -- "Sửa đổi, bổ sung điểm b khoản 8 Điều 13". This is
  the whole content of an amending decree: 238/2026/NĐ-CP means nothing except
  as a set of edges into 168/2024/NĐ-CP. Without them both texts sit in the
  index as equals and the superseded figure is as retrievable as the current one.
* EXEMPTS -- "trừ trường hợp quy định tại khoản 5".
* REFERENCES -- everything else.

The remaining types in the schema (SANCTIONS, OVERRIDES, GUIDES) are not
inferred. Deciding that one provision sanctions rather than merely cites
another is a legal judgement the surface text does not license, and a wrong
relation type changes an agent's conclusion -- an over-broad REFERENCES edge
only costs it a look.

Unresolvable targets are kept as `target_external_ref` rather than dropped: a
citation into a document outside the corpus is exactly what an agent needs to
be told, instead of silently answering as though nothing were missing.
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass, field

from rag_eval.legal.schemas import sanitize_index_label

RELATION_MODIFIES = "MODIFIES_AND_REPLACES"
RELATION_EXEMPTS = "EXEMPTS"
RELATION_REFERENCES = "REFERENCES"

# Enumerations are cited as lists sharing a parent: "điểm a, điểm c khoản 2" is
# two points of one clause, and "các khoản 1, 2 và 3 Điều 6" three clauses of
# one article. The list is captured whole and expanded after matching.
_LETTERS = r"[a-zđ](?:\))?(?:\s*(?:,|và|hoặc)\s*(?:điểm\s+)?[a-zđ](?:\))?)*"
_NUMBERS = r"\d+[a-z]?(?:\s*(?:,|và|hoặc)\s*(?:khoản\s+|Điều\s+)?\d+[a-z]?)*"

# A citation is written most-specific-first. Every part is optional, but a match
# is only kept when it carries at least one addressable level.
_CITATION = re.compile(
    rf"(?:điểm\s+(?P<diem>{_LETTERS})\s*)?"
    rf"(?:khoản\s+(?P<khoan>{_NUMBERS})\s*)?"
    rf"(?:Điều\s+(?P<dieu>{_NUMBERS})\s*)?"
    r"(?P<relative>Điều này|khoản này|Mục này|Chương này)?\s*"
    r"(?:(?:của|thuộc)\s+(?P<doc>(?:Nghị định|Luật|Thông tư|Quy chuẩn|Quyết định|Pháp lệnh)"
    r"(?:\s+này|[^,;.:\n]{0,70})))?",
    re.IGNORECASE,
)

# What introduces a citation. Ordered longest-first so the specific exemption
# and amendment cues win over the bare preposition they contain.
_CUES: tuple[tuple[str, str], ...] = (
    (r"trừ\s+(?:trường hợp|các|quy định)[^.;:\n]{0,80}?quy định\s+tại", RELATION_EXEMPTS),
    (r"trừ\s+(?:trường hợp|các)[^.;:\n]{0,80}?tại", RELATION_EXEMPTS),
    (r"[Ss]ửa đổi,?\s*bổ sung", RELATION_MODIFIES),
    (r"[Bb]ổ sung", RELATION_MODIFIES),
    (r"[Bb]ãi bỏ", RELATION_MODIFIES),
    (r"[Tt]hay thế", RELATION_MODIFIES),
    (r"(?:quy định|nêu|nói|xác định|liệt kê)\s+(?:tại|ở)", RELATION_REFERENCES),
    (r"theo\s+(?:quy định\s+)?tại", RELATION_REFERENCES),
    (r"(?:tại|theo)\b", RELATION_REFERENCES),
)
_CUE_RE = re.compile(
    "|".join(f"(?P<c{i}>{pattern})" for i, (pattern, _) in enumerate(_CUES)),
    re.IGNORECASE,
)
_CUE_RELATIONS = tuple(relation for _, relation in _CUES)

_SELF_DOC = re.compile(
    r"(?:Nghị định|Luật|Thông tư|Quy chuẩn|Quyết định)\s+này", re.IGNORECASE
)
# An amending article names its target once, in its own heading, and then omits
# it from every clause below: "Điều 52. Sửa đổi, bổ sung một số điều của Nghị
# định số 100/2019/NĐ-CP" is followed by "Sửa đổi, bổ sung điểm d khoản 6 Điều
# 28" with no document named. Read literally each of those cites this decree's
# own Điều 28, which is a different provision entirely, so the heading's
# document code is carried down to them.
_DOC_CODE = re.compile(r"\b\d{1,4}/\d{4}/[A-ZĐ]+(?:[-–][A-ZĐ]+)*\b")
_LIST_SPLIT = re.compile(r"\s*(?:,|và|hoặc)\s*(?:điểm\s+|khoản\s+|Điều\s+)?", re.IGNORECASE)
# `.a_` anchors the article, which disambiguates the `c_` segment: the same
# prefix labels both Chương and Khoản, and only position tells them apart.
_PATH_ADDRESS = re.compile(
    r"\.a_(?P<dieu>\d+[a-z]?)(?:\.c_(?P<khoan>\d+[a-z]?))?(?:\.p_(?P<diem>[a-z0-9_]+))?$"
)


@dataclass(frozen=True)
class Address:
    """A statutory address: Điều, optionally Khoản, optionally Điểm."""

    dieu: str | None = None
    khoan: str | None = None
    diem: str | None = None

    def __bool__(self) -> bool:
        return any((self.dieu, self.khoan, self.diem))


@dataclass(frozen=True)
class Citation:
    """One resolved or unresolved reference found in a chunk's text."""

    source_path: str
    relation_type: str
    citation_text: str
    address: Address
    target_path: str | None = None
    target_external_ref: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


def _split_list(raw: str) -> list[str]:
    return [part.strip(" )") for part in _LIST_SPLIT.split(raw.strip()) if part.strip(" )")]


def address_of_path(path: str) -> Address:
    """Reads the statutory address a chunk path encodes."""
    match = _PATH_ADDRESS.search(path)
    if match is None:
        return Address()
    return Address(
        dieu=match.group("dieu"),
        khoan=match.group("khoan"),
        diem=match.group("diem"),
    )


def build_path_index(paths: list[str]) -> dict[Address, str]:
    """Maps every addressable level of a document to a chunk path.

    A citation to "khoản 2 Điều 6" must resolve even when khoản 2 has no chunk
    of its own because it is a stem whose points were chunked instead. The
    coarser keys are filled from the first descendant, so the reference lands on
    real text rather than being reported as unresolvable.
    """
    index: dict[Address, str] = {}
    for path in paths:
        address = address_of_path(path)
        if not address:
            continue
        index.setdefault(address, path)
        if address.diem is not None:
            index.setdefault(Address(dieu=address.dieu, khoan=address.khoan), path)
        if address.khoan is not None:
            index.setdefault(Address(dieu=address.dieu), path)
    return index


def _resolve(address: Address, index: dict[Address, str]) -> tuple[str | None, str]:
    """Looks the address up exactly, never approximately.

    Widening a miss to the enclosing khoản or Điều looks helpful and is not.
    Điều 52 of 168/2024/NĐ-CP amends *other* decrees, so "Sửa đổi, bổ sung điểm
    d khoản 6 Điều 28" names a provision of a different document; widening
    resolved it to this decree's own Điều 28, producing an edge that asserts a
    relationship between two unrelated provisions. An unresolved citation with
    its text preserved tells an agent something true; a confidently wrong edge
    does not.

    The case widening was meant to serve -- a khoản with no chunk of its own
    because its points were chunked instead -- is already handled by
    `build_path_index` registering the coarser keys, so the exact lookup finds it.
    """
    hit = index.get(address)
    return (hit, "exact") if hit is not None else (None, "unresolved")


def _expand(
    diem_raw: str | None, khoan_raw: str | None, dieu_raw: str | None
) -> list[Address]:
    """Turns a citation's captured lists into individual addresses."""
    diems = _split_list(diem_raw) if diem_raw else [None]
    khoans = _split_list(khoan_raw) if khoan_raw else [None]
    dieus = _split_list(dieu_raw) if dieu_raw else [None]
    return [
        Address(
            dieu=dieu,
            khoan=khoan,
            diem=sanitize_index_label(diem) if diem else None,
        )
        for diem, khoan, dieu in itertools.product(diems, khoans, dieus)
    ]


def _relation_for(match: re.Match[str]) -> str:
    for i, relation in enumerate(_CUE_RELATIONS):
        if match.group(f"c{i}") is not None:
            return relation
    return RELATION_REFERENCES


def extract_citations(
    source_path: str,
    text: str,
    *,
    path_index: dict[Address, str],
    default_external_doc: str | None = None,
    context_text: str | None = None,
    own_doc_code: str | None = None,
) -> list[Citation]:
    """Finds every cross-reference in one chunk and resolves what it can.

    Args:
        source_path: the citing chunk's ltree path.
        text: that chunk's verbatim text.
        path_index: `build_path_index` output for the citing document.
        default_external_doc: the document an unqualified citation targets when
            it is not this one. An amending decree's "Sửa đổi, bổ sung khoản 3
            Điều 6" means Điều 6 of the *amended* decree, so resolving it
            against itself would point every amendment at the wrong statute.
        context_text: the citing chunk's contextualized text, whose ancestor
            headings may name the document an amendment targets.
        own_doc_code: this document's code, so a heading naming it is not
            mistaken for a reference out of the document.

    Returns:
        One citation per addressed provision, deduplicated on
        (target, relation).
    """
    own = address_of_path(source_path)
    found: dict[tuple[str | None, str | None, str], Citation] = {}

    # Applied to amendments only. A clause that merely mentions another decree
    # in passing must not have all of its references redirected there.
    amendment_scope = default_external_doc
    if context_text:
        named = [
            code
            for code in _DOC_CODE.findall(context_text)
            if own_doc_code is None or code.replace("Đ", "D") != own_doc_code.replace("Đ", "D")
        ]
        if named:
            amendment_scope = named[0]

    for cue in _CUE_RE.finditer(text):
        relation = _relation_for(cue)
        # The citation must begin immediately after the cue. Anchoring the match
        # is what keeps the bare preposition in "giao thông tại nơi đường giao
        # nhau" from scanning ahead and inventing an edge, so only the
        # whitespace separating cue from citation is skipped.
        raw_tail = text[cue.end() : cue.end() + 240]
        tail = raw_tail.lstrip()
        citation = _CITATION.match(tail)
        if citation is None:
            continue

        diem_raw, khoan_raw = citation.group("diem"), citation.group("khoan")
        dieu_raw, relative = citation.group("dieu"), citation.group("relative")
        doc_raw = citation.group("doc")
        if not any((diem_raw, khoan_raw, dieu_raw, relative)):
            continue

        # "khoản 1 Điều này" / "điểm a khoản này" inherit from the citing chunk.
        if relative is not None:
            lowered = relative.lower()
            if lowered.startswith("điều") and dieu_raw is None:
                dieu_raw = own.dieu
            elif lowered.startswith("khoản") and khoan_raw is None:
                khoan_raw = own.khoan
        if dieu_raw is None and (khoan_raw or diem_raw):
            dieu_raw = own.dieu

        external = doc_raw and not _SELF_DOC.match(doc_raw.strip())
        if external:
            target_doc = doc_raw.strip()
        elif relation == RELATION_MODIFIES:
            target_doc = amendment_scope
        else:
            target_doc = default_external_doc
        offset = len(raw_tail) - len(tail)
        verbatim = text[cue.start() : cue.end() + offset + citation.end()].strip()

        for address in _expand(diem_raw, khoan_raw, dieu_raw):
            if not address:
                continue
            if target_doc is not None:
                key = (None, _format_address(address, target_doc), relation)
                found.setdefault(
                    key,
                    Citation(
                        source_path=source_path,
                        relation_type=relation,
                        citation_text=verbatim,
                        address=address,
                        target_external_ref=_format_address(address, target_doc),
                        metadata={"resolution": "external"},
                    ),
                )
                continue

            target_path, precision = _resolve(address, path_index)
            if target_path is None:
                key = (None, _format_address(address, None), relation)
                found.setdefault(
                    key,
                    Citation(
                        source_path=source_path,
                        relation_type=relation,
                        citation_text=verbatim,
                        address=address,
                        target_external_ref=_format_address(address, None),
                        metadata={"resolution": "unresolved"},
                    ),
                )
                continue
            if target_path == source_path:
                continue
            key = (target_path, None, relation)
            found.setdefault(
                key,
                Citation(
                    source_path=source_path,
                    relation_type=relation,
                    citation_text=verbatim,
                    address=address,
                    target_path=target_path,
                    metadata={"resolution": precision},
                ),
            )

    return list(found.values())


def _format_address(address: Address, doc: str | None) -> str:
    """Renders an address as the citation a reader would recognise."""
    parts: list[str] = []
    if address.diem:
        parts.append(f"điểm {address.diem}")
    if address.khoan:
        parts.append(f"khoản {address.khoan}")
    if address.dieu:
        parts.append(f"Điều {address.dieu}")
    rendered = " ".join(parts) or "?"
    return f"{rendered} — {doc}" if doc else rendered


def extract_document_citations(
    chunk_texts: dict[str, str],
    *,
    default_external_doc: str | None = None,
    chunk_contexts: dict[str, str] | None = None,
    own_doc_code: str | None = None,
) -> list[Citation]:
    """Extracts every cross-reference in a document, resolving within it."""
    path_index = build_path_index(list(chunk_texts))
    citations: list[Citation] = []
    for path, text in chunk_texts.items():
        citations.extend(
            extract_citations(
                path,
                text,
                path_index=path_index,
                default_external_doc=default_external_doc,
                context_text=(chunk_contexts or {}).get(path),
                own_doc_code=own_doc_code,
            )
        )
    return citations
