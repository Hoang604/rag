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
    r"(?:\s+này|[^;.:\n]{0,90})))?",
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
# An amending article names its target only in its heading, so that code
# is carried down to clauses that cite a bare "Điều 28".
_DOC_CODE = re.compile(
    r"\b(?:[A-ZĐ]{2,6})?\d{1,4}/(?:\d{4}/)?[A-ZĐ]+\d*(?:[-–][A-ZĐ]+\d*)*\b"
)
_DOC_KEYWORD = re.compile(
    r"^(Nghị định|Luật|Thông tư|Quy chuẩn|Quyết định|Pháp lệnh)", re.IGNORECASE
)
# Gazette footnotes are cut mid-sentence, and windowing turns the newline
# into a space, so a name capture runs into the next footnote. Both cuts
# below anchor on that structure.
_FOOTNOTE_MARKER = re.compile(r"\s\d{1,3}\s+(?=[A-ZĐ])")
_AMENDMENT_NOTE = re.compile(
    r"\s(?:Điểm|Khoản|Điều|Cụm từ|Đoạn)\s+này\b|\s(?:có hiệu lực|được (?:sửa đổi|bãi bỏ|bổ sung|thay thế|bỏ))\b"
)
_MAX_DOC_REF_WORDS = 12


def _clean_doc_ref(raw: str) -> str | None:
    """Reduces a captured document reference to something that names a document.

    Returns None when nothing usable survives, which is the honest outcome for
    a truncated footnote: an edge labelled "Luật số" tells an agent less than an
    edge that admits it could not identify the target.
    """
    text = " ".join(raw.split())
    code = _DOC_CODE.search(text)
    keyword = _DOC_KEYWORD.match(text)
    if code is not None and keyword is not None:
        # A code is unambiguous, so it wins over any surrounding prose.
        return f"{keyword.group(1)} số {code.group(0)}"

    text = _FOOTNOTE_MARKER.split(text)[0]
    text = _AMENDMENT_NOTE.split(text)[0]
    words = text.split()
    if len(words) > _MAX_DOC_REF_WORDS:
        words = words[:_MAX_DOC_REF_WORDS]
    text = " ".join(words).strip(" ,;.:-–")

    # "Luật số" or a bare keyword identifies nothing.
    if _DOC_KEYWORD.fullmatch(text) or re.fullmatch(
        r"(?i)(?:Nghị định|Luật|Thông tư|Quy chuẩn|Quyết định|Pháp lệnh)\s+số", text
    ):
        return None
    return text or None
_LIST_SPLIT = re.compile(r"\s*(?:,|và|hoặc)\s*(?:điểm\s+|khoản\s+|Điều\s+)?", re.IGNORECASE)
# `.a_` anchors the article: `c_` labels both Chương and Khoản, and only
# position separates them. A trailing `.w_<n>` is a window split, not a
# statutory level, so it is consumed rather than blocking the match.
_PATH_ADDRESS = re.compile(
    r"\.a_(?P<dieu>\d+[a-z]?)"
    r"(?:\.c_(?P<khoan>\d+[a-z]?))?"
    r"(?:\.p_(?P<diem>[a-z]+(?:_\d+)?))?"
    r"(?:\.w_\d+)?$"
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
        # Anchored at the cue: unanchored, the bare preposition in "giao thông
        # tại nơi đường giao nhau" scans ahead and invents an edge.
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

        cleaned_doc = _clean_doc_ref(doc_raw) if doc_raw else None
        external = cleaned_doc and not _SELF_DOC.match(cleaned_doc)
        if external:
            target_doc = cleaned_doc
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


def normalize_doc_code(text: str) -> str:
    """Reduces a document code to a comparison key.

    A single decree is written "168/2024/NĐ-CP" in one document and
    "168/2024/ND-CP" in another, and the registry uses the ASCII form. Matching
    on the raw string leaves an edge unresolved for a spelling difference.
    """
    return re.sub(r"[^0-9a-z/]", "", text.replace("Đ", "D").lower())


# A cited title needs the keyword plus two words: "Luật Đường bộ"
# qualifies, "Luật" alone does not. Uniqueness does the real work.
_MIN_TITLE_WORDS = 3


def normalize_title(text: str) -> str:
    """Collapses a document title to a comparison key."""
    return re.sub(r"[\s,;.]+", " ", text).strip().lower()


def match_document(
    reference: str,
    known: dict[str, str],
    titles: dict[str, str] | None = None,
) -> str | None:
    """Finds which known document a citation's target reference names.

    Args:
        reference: the external reference text, e.g. "Điều 13 — 168/2024/ND-CP".
        known: mapping of normalized doc code to the document's own doc_code.
        titles: mapping of normalized document title to doc_code, used only
            when the citation carries no code.

    Returns:
        The matching document's doc_code, or None.

    A code wins whenever present. Falling back to the title is deliberately
    strict -- a unique prefix match of at least `_MIN_TITLE_WORDS` words --
    because the repealed Luật Giao thông đường bộ (2008) is still cited by the
    older decrees and must not be matched onto Luật Đường bộ, whose title it
    resembles. A citation matching two documents is left unresolved rather than
    attached to a guess.
    """
    code = _DOC_CODE.search(reference)
    if code is not None:
        return known.get(normalize_doc_code(code.group(0)))
    if not titles:
        return None

    cited = normalize_title(re.sub(r"^.*?—\s*", "", reference))
    if len(cited.split()) < _MIN_TITLE_WORDS:
        return None
    hits = {doc for title, doc in titles.items() if title.startswith(cited)}
    return hits.pop() if len(hits) == 1 else None


def parse_external_ref(reference: str) -> Address:
    """Reads back the statutory address rendered into an external reference."""
    diem = re.search(r"điểm\s+([a-z0-9_]+)", reference, re.IGNORECASE)
    khoan = re.search(r"khoản\s+(\d+[a-z]?)", reference, re.IGNORECASE)
    dieu = re.search(r"Điều\s+(\d+[a-z]?)", reference, re.IGNORECASE)
    return Address(
        dieu=dieu.group(1) if dieu else None,
        khoan=khoan.group(1) if khoan else None,
        diem=diem.group(1) if diem else None,
    )


def resolve_across_documents(
    reference: str,
    known_codes: dict[str, str],
    indexes: dict[str, dict[Address, str]],
    titles: dict[str, str] | None = None,
) -> tuple[str, str] | None:
    """Resolves an external reference to a chunk path in another document.

    An amending decree carries its whole meaning in these edges: 238/2026/NĐ-CP
    says "Sửa đổi, bổ sung điểm b khoản 8 Điều 13", and until that lands on
    168/2024/NĐ-CP's actual điểm b, both texts sit in the index as equals with
    nothing recording that one supersedes the other.

    Returns the target doc_code and chunk path, or None when the document is
    outside the corpus or the address does not exist in it.
    """
    doc_code = match_document(reference, known_codes, titles)
    if doc_code is None:
        return None
    index = indexes.get(doc_code)
    if not index:
        return None
    address = parse_external_ref(reference)
    if not address:
        return None
    path = index.get(address)
    return (doc_code, path) if path is not None else None


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
