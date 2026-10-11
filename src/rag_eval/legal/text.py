from __future__ import annotations

import datetime
import re
import unicodedata
import zoneinfo
from dataclasses import dataclass

_D_LOWER = "đ"
_D_UPPER = "Đ"

VIETNAM_TZ = zoneinfo.ZoneInfo("Asia/Ho_Chi_Minh")


def get_vietnam_now() -> datetime.datetime:
    """Returns current timezone-aware datetime in Vietnam jurisdiction timezone (Asia/Ho_Chi_Minh, UTC+7)."""
    return datetime.datetime.now(VIETNAM_TZ)


def get_vietnam_today() -> datetime.date:
    """Returns current date in Vietnam jurisdiction timezone (Asia/Ho_Chi_Minh, UTC+7)."""
    return datetime.datetime.now(VIETNAM_TZ).date()


def fold_diacritics(text: str) -> str:
    """Returns text with tone marks removed and đ mapped to d. Case is kept.

    Case must survive because this also folds regular-expression sources, and
    case folding a pattern turns `\\W` into `\\w` -- inverting the character
    class and, in this corpus, filing every motorcycle article as a car.
    """
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return stripped.replace(_D_LOWER, "d").replace(_D_UPPER, "D")


def fold_for_match(text: str) -> str:
    """Folds text for comparison against a folded pattern: diacritics and case."""
    return fold_diacritics(text).casefold()


def is_unaccented(text: str) -> bool:
    """Reports whether a Vietnamese query was typed without any tone marks.

    Used to discount the dense ranker: the corpus is embedded from accented
    text, so an unaccented query lands far from its answer in vector space
    while the diacritic-folding text index still finds it exactly.
    """
    stripped = text.strip()
    if len(stripped.split()) < 2:
        return False
    return fold_diacritics(stripped) == stripped


def parse_flexible_date(val: object) -> datetime.date | None:
    """Parses various date representations (ISO, DD/MM/YYYY, DD-MM-YYYY, and Vietnamese statutory date strings)."""
    if val is None:
        return None
    if isinstance(val, datetime.date):
        return val
    s = str(val).strip()
    if not s:
        return None
    try:
        return datetime.date.fromisoformat(s)
    except ValueError:
        pass

    vn_match = re.search(
        r"(?:ngày\s+)?(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})",
        s,
        re.IGNORECASE,
    )
    if vn_match:
        try:
            day, month, year = (
                int(vn_match.group(1)),
                int(vn_match.group(2)),
                int(vn_match.group(3)),
            )
            return datetime.date(year, month, day)
        except ValueError:
            pass

    m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$", s)
    if m:
        try:
            day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return datetime.date(year, month, day)
        except ValueError:
            pass

    m2 = re.match(r"^(\d{4})[/-](\d{1,2})[/-](\d{1,2})$", s)
    if m2:
        try:
            year, month, day = int(m2.group(1)), int(m2.group(2)), int(m2.group(3))
            return datetime.date(year, month, day)
        except ValueError:
            pass

    raise ValueError(f"Unable to parse date string: '{s}'")


LTREE_LABEL_REGEX = re.compile(r"^[a-zA-Z0-9_]+$")
LTREE_PATH_REGEX = re.compile(r"^[a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)*$")

_VN_CHAR_MAP: dict[int, str] = str.maketrans(
    {
        "đ": "d",
        "Đ": "d",
        "ð": "d",
        "Ð": "d",
    }
)

_VN_INDEX_MAP: dict[int, str] = str.maketrans(
    {
        "đ": "dd",
        "Đ": "dd",
        "ă": "aw",
        "Ă": "aw",
        "â": "aa",
        "Â": "aa",
        "ê": "ee",
        "Ê": "ee",
        "ô": "oo",
        "Ô": "oo",
        "ơ": "ow",
        "Ơ": "ow",
        "ư": "uw",
        "Ư": "uw",
    }
)


def sanitize_index_label(label: str) -> str:
    """Sanitizes an enumeration label (điểm letter, appendix letter) injectively.

    Use this wherever the label identifies a sibling among an ordered set, so
    that two different labels can never produce the same ltree segment. Use
    `sanitize_ltree_label` for free text such as titles and document codes,
    where readability matters and collisions are not a correctness problem.
    """
    if not label:
        return "node"
    translated = label.translate(_VN_INDEX_MAP)
    nfkd = unicodedata.normalize("NFKD", translated)
    ascii_text = "".join(c for c in nfkd if not unicodedata.combining(c))
    clean = re.sub(r"[^a-zA-Z0-9_]", "_", ascii_text.strip().lower())
    clean = re.sub(r"_+", "_", clean).strip("_")
    return clean or "node"


def sanitize_ltree_label(label: str) -> str:
    """Sanitizes an arbitrary string into a valid PostgreSQL ltree label with Vietnamese transliteration."""
    if not label:
        return "root"
    text = label.translate(_VN_CHAR_MAP)
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(c for c in nfkd if not unicodedata.combining(c))
    clean = re.sub(r"[^a-zA-Z0-9_]", "_", ascii_text.strip().lower())
    clean = re.sub(r"_+", "_", clean).strip("_")
    if len(clean) > 250:
        clean = clean[:250].rstrip("_")
    return clean or "node"


def validate_ltree_path(path: str) -> str:
    """Validates and normalizes a dot-separated ltree path."""
    if not path or not path.strip():
        raise ValueError("LTREE path cannot be empty")
    clean = path.strip()
    if LTREE_PATH_REGEX.match(clean):
        return clean
    segments = clean.split(".")
    sanitized = [sanitize_ltree_label(s) for s in segments if s]
    res = ".".join(sanitized)
    if not LTREE_PATH_REGEX.match(res):
        raise ValueError(f"Invalid ltree path format: '{path}' -> '{res}'")
    return res


# A segment the chunker appends to a node's path: a container's own text, a list's closing text, a passage window.
_CHUNK_SUFFIX_RE = re.compile(r"\.(?:body|tail_\d+|w_\d+)$")
# A disambiguation suffix ("a_5_2": a second Điều 5 under one parent); enumeration labels never contain "_".
_REPEAT_SUFFIX_RE = re.compile(r"_\d+$")
_SEGMENT_RE = re.compile(r"^(?P<kind>pre|part|c|s|ss|a|p|app|i)_(?P<label>[a-z0-9_]+)$")


def _enumeration_label(label: str) -> str:
    """The cited form of an encoded Điều/Khoản/Điểm label: repeat suffix dropped, "dd" decoded to "đ"."""
    return _REPEAT_SUFFIX_RE.sub("", label).replace("dd", "đ")


@dataclass(frozen=True)
class Address:
    """A statutory address: the preamble, or Phần / Phụ lục, mục / Điều, Khoản, Điểm."""

    dieu: str | None = None
    khoan: str | None = None
    diem: str | None = None
    is_preamble: bool = False
    # The appendix label; "" for an unnumbered appendix or attached text; None outside appendices.
    appendix: str | None = None
    item: str | None = None  # the outline item inside an appendix ("2.3", "II.1")
    part: str | None = None

    def __bool__(self) -> bool:
        return self.is_preamble or any((self.dieu, self.khoan, self.diem, self.item, self.part)) or self.appendix is not None

    def format(self) -> str:
        """Formats canonical human-readable citation label."""
        if self.is_preamble:
            return "Căn cứ ban hành"
        parts: list[str] = []
        if self.appendix is not None:
            parts.append(f"Phụ lục {self.appendix}" if self.appendix else "Văn bản kèm theo")
        if self.item:
            parts.append(f"mục {self.item}")
        if self.part and not self.dieu:
            parts.append(f"Phần {self.part}")
        if self.dieu:
            parts.append(f"Điều {self.dieu}")
        if self.khoan:
            parts.append(f"Khoản {self.khoan}")
        if self.diem:
            parts.append(f"Điểm {self.diem}")
        return ", ".join(parts)


def address_of_path(path: str) -> Address:
    """Reads the statutory address a chunk path encodes; the first segment is the document code."""
    segments = _CHUNK_SUFFIX_RE.sub("", path.strip().lower()).split(".")[1:]
    fields: dict[str, str] = {}
    items: list[str] = []
    for segment in segments:
        match = _SEGMENT_RE.match(segment)
        if match is None:
            continue
        kind, label = match.group("kind"), match.group("label")
        if kind == "pre":
            return Address(is_preamble=True)
        if kind == "app":
            # app_u<k> is the k-th unnumbered appendix; a numbered label keeps its encoded form ("i_a" of "I-A").
            fields["appendix"] = "" if re.fullmatch(r"u\d+", label) else label.upper().replace("_", "-")
        elif kind == "i":
            items.append(_REPEAT_SUFFIX_RE.sub("", label).upper())
        elif kind == "part":
            fields["part"] = _REPEAT_SUFFIX_RE.sub("", label)
        elif kind == "a":
            fields["dieu"] = _enumeration_label(label)
        elif kind == "c" and "dieu" in fields:
            fields["khoan"] = _enumeration_label(label)
        elif kind == "p":
            fields["diem"] = _enumeration_label(label)
    return Address(
        dieu=fields.get("dieu"),
        khoan=fields.get("khoan"),
        diem=fields.get("diem"),
        appendix=fields.get("appendix"),
        item=".".join(items) or None,
        part=fields.get("part"),
    )


def format_path_address(path: str) -> str:
    """Formats canonical human-readable citation address from LTREE path."""
    addr = address_of_path(path)
    return addr.format() if addr else ""


ROMAN_REGEX = re.compile(
    r"^(?:i|ii|iii|iv|v|vi|vii|viii|ix|x|xi|xii|xiii|xiv|xv|xvi|xvii|xviii|xix|xx|xxi|xxii|xxiii|xxiv|xxv|xxvi|xxvii|xxviii|xxix|xxx)$",
    re.IGNORECASE,
)


def slice_raw_text(raw_text: str, start_line: int, end_line: int) -> str:
    """The exact lines start_line..end_line (1-indexed, inclusive), joined by "\\n", unstripped."""
    lines = raw_text.splitlines()
    total = len(lines)
    if start_line < 1 or end_line < start_line or end_line > total:
        from rag_eval.legal.errors import E_AST_GROUNDING_VALIDATION, LegalDomainError

        raise LegalDomainError(
            error_code=E_AST_GROUNDING_VALIDATION,
            message=f"Tọa độ dòng [{start_line}..{end_line}] vượt ngoài giới hạn văn bản [1..{total}].",
            data={"start_line": start_line, "end_line": end_line, "total_lines": total},
        )
    return "\n".join(lines[start_line - 1 : end_line])


def find_normalized_span(text: str, query: str) -> tuple[int, int] | None:
    """Finds exact character span (start, end) of query within text, normalizing whitespace.

    Matches query words in sequence allowing any non-empty whitespace (including newlines)
    between them. Returns 0-indexed [start, end) offsets in original text, or None if no match.
    """
    if not text or not query:
        return None
    words = query.strip().split()
    if not words:
        return None
    pattern = re.compile(r"\s+".join(re.escape(w) for w in words))
    match = pattern.search(text)
    if match is None:
        return None
    return match.start(), match.end()


def normalize_whitespace(text: str) -> str:
    """Collapses all whitespace sequences (spaces, tabs, newlines, NBSP) into single spaces."""
    return " ".join(text.split())


