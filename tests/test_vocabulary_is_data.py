"""Domain vocabulary must live in the vocabulary file, not in Python.

Vehicle names and colloquial synonyms used to be Python literals. A decree
introducing a class the corpus had not seen -- "xe bốn bánh có gắn động cơ" --
therefore needed a source change and a redeploy, which is precisely what the
project's own rule forbids: ingesting a new document must work with no code
modification at all.

The distinction these tests draw is between the *grammar* of a legal document
and its *vocabulary*. `\\[Điều\\s+...\\]` is grammar: every decree ever written
uses that structure, and a parser for it generalises by construction. "xe tay
ga" is vocabulary: it is a fact about this domain at this moment, it will grow,
and it belongs in data.

Nothing fails at runtime when a catalogue creeps back into a module, so this
is the only thing that would notice.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from rag_eval.legal.vocabulary import document_type_alternation, vocabulary

SOURCE = Path(__file__).resolve().parents[1] / "src" / "rag_eval" / "legal"

# Accented Vietnamese, which is what a vocabulary literal looks like. The
# grammar patterns that legitimately stay in code -- "Điều", "Khoản", "Bảng" --
# are exempted by name below rather than by character, because they are a
# closed set and a new one deserves the argument this test forces.
_VIETNAMESE = re.compile(
    r"[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợ"
    r"ùúủũụưừứửữựỳýỷỹỵđ]",
    re.IGNORECASE,
)

# Structure words. A document's skeleton, not its subject matter.
_GRAMMAR = frozenset(
    {
        "điều",
        "khoản",
        "điểm",
        "chương",
        "mục",
        "phần",
        "bảng",
        "biểu",
        "phụ lục",
        "đơn vị tính",
    }
)

_STRING = re.compile(r'(?:r|rb|br)?"((?:[^"\\]|\\.)*)"')

# The two modules that held catalogues. Named explicitly: a blanket scan of the
# package would flag error messages and log lines, which are prose for a person
# and not rules the matcher consults.
_MUST_STAY_DATA = ("ingestion/facets.py", "retrieval/lexicon.py")


def _code_only(text: str) -> str:
    """Drops comments and docstrings, leaving what the interpreter acts on."""
    without_docstrings = re.sub(r'"""(?:.|\n)*?"""', "", text)
    return "\n".join(
        line
        for line in without_docstrings.splitlines()
        if not line.strip().startswith("#")
    )


@pytest.mark.parametrize("relative", _MUST_STAY_DATA)
def test_no_vietnamese_vocabulary_left_in_code(relative: str) -> None:
    """The catalogues are gone and may not come back one literal at a time."""
    code = _code_only((SOURCE / relative).read_text(encoding="utf-8"))

    offenders = [
        literal
        for literal in _STRING.findall(code)
        if _VIETNAMESE.search(literal)
        and not any(word in literal.lower() for word in _GRAMMAR)
    ]

    assert not offenders, (
        f"{relative} chứa {len(offenders)} chuỗi từ vựng tiếng Việt trong mã. "
        f"Thêm vào data/vocabulary.toml thay vì vào đây: {offenders[:3]}"
    )


def test_the_vocabulary_file_actually_loads() -> None:
    """A test that only forbids things would pass on an empty file."""
    loaded = vocabulary()

    assert len(loaded.vehicle_heading) >= 6
    assert len(loaded.vehicle_query) >= 6
    assert len(loaded.synonyms) >= 15
    assert loaded.role_markers and loaded.intent


def test_every_synonym_pattern_compiles_and_is_folded() -> None:
    """A pattern written with diacritics must match input typed without them.

    Both sides are folded, so a rule that somehow reached the matcher still
    accented would silently never fire -- no error, just a synonym that stops
    working.
    """
    for pattern, expansion in vocabulary().synonyms:
        assert not _VIETNAMESE.search(pattern.pattern), (
            f"mẫu chưa được bỏ dấu nên sẽ không bao giờ khớp: {pattern.pattern!r}"
        )
        assert expansion.strip()


def test_longer_synonym_contexts_are_tried_first() -> None:
    """Order is load-bearing: "đèn đỏ" must not consume "vượt đèn đỏ"."""
    patterns = [pattern.pattern for pattern, _ in vocabulary().synonyms]
    joined = next(p for p in patterns if "den do" in p)

    assert joined.index("vuot den do") < joined.index("|den do"), (
        "cụm dài phải đứng trước trong cùng một mẫu, nếu không cụm ngắn nuốt mất"
    )


def test_document_types_are_ordered_longest_first() -> None:
    """A short name placed first swallows every longer one sharing its tail.

    `Luật` before `Bộ luật` means a citation of a code is read as a citation of
    a law, and `Thông tư` before `Thông tư liên tịch` loses the joint circular.
    Nothing errors -- the reference just resolves to the wrong document.
    """
    types = vocabulary().document_types

    swallowed = [
        (early, late)
        for index, early in enumerate(types)
        for late in types[index + 1 :]
        if late.lower().endswith(early.lower())
    ]

    assert not swallowed, f"tên ngắn đứng trước sẽ nuốt tên dài: {swallowed}"


def test_the_types_the_corpus_actually_cites_are_all_covered() -> None:
    """The list was incomplete in a way only the corpus could reveal.

    `Nghị quyết` was missing from all three copies of this list, so four real
    citations -- including "Điều 8 của Nghị quyết số 190/2025/QH15" -- resolved
    to nothing and said nothing. These are the types this corpus cites.
    """
    cited = ("Nghị quyết", "Nghị định", "Thông tư", "Luật", "Pháp lệnh", "Bộ luật")
    known = {name.lower() for name in vocabulary().document_types}

    assert all(name.lower() in known for name in cited), (
        f"thiếu loại văn bản mà kho có trích dẫn: "
        f"{[n for n in cited if n.lower() not in known]}"
    )


def test_the_alternation_matches_every_type_it_was_built_from() -> None:
    r"""`xref.py` held this list three times and the three had drifted.

    Asserted by matching, not by substring: `re.escape` escapes the space, so
    the alternation contains `Pháp\ lệnh` and a substring check on the plain
    name fails while the pattern works perfectly. Testing the string rather
    than the behaviour is how a correct implementation gets "fixed" into a
    broken one.
    """
    pattern = re.compile(rf"^(?:{document_type_alternation()})$", re.IGNORECASE)

    for name in vocabulary().document_types:
        assert pattern.match(name), f"alternation không khớp `{name}`"

    assert pattern.match("Pháp lệnh")
    assert pattern.match("Nghị quyết")
    assert not pattern.match("Công văn")
