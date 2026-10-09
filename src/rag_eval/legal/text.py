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


ROMAN_REGEX = re.compile(
    r"^(?:i|ii|iii|iv|v|vi|vii|viii|ix|x|xi|xii|xiii|xiv|xv|xvi|xvii|xviii|xix|xx|xxi|xxii|xxiii|xxiv|xxv|xxvi|xxvii|xxviii|xxix|xxx)$",
    re.IGNORECASE,
)


def roman_to_int(s: str) -> int | None:
    """Parses lower/upper roman numeral into integer (1-30)."""
    clean = s.lower().strip()
    if not ROMAN_REGEX.match(clean):
        return None
    roman_map = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}
    total = 0
    prev = 0
    for c in reversed(clean):
        curr = roman_map[c]
        if curr >= prev:
            total += curr
        else:
            total -= curr
        prev = curr
    return total


def natural_legal_path_key(path: str) -> list[tuple[str, int, int, str]]:
    """Generates natural hierarchical sort key for Vietnamese legal LTREE paths."""
    keys: list[tuple[str, int, int, str]] = []
    for seg in path.split("."):
        if "_" not in seg:
            keys.append((seg, 0, 0, ""))
            continue
        prefix, rest = seg.split("_", 1)
        if rest.isdigit():
            keys.append((prefix, 0, int(rest), ""))
        else:
            r_int = roman_to_int(rest)
            if r_int is not None:
                keys.append((prefix, 0, r_int, ""))
            else:
                keys.append((prefix, 1, 0, rest.lower()))
    return keys


def deep_merge_dict(base: dict[str, object], delta: dict[str, object]) -> dict[str, object]:
    """Recursively merges delta dictionary into base dictionary without clobbering sibling keys."""
    merged = dict(base)
    for key, value in delta.items():
        base_val = merged.get(key)
        if isinstance(base_val, dict) and isinstance(value, dict):
            merged[key] = deep_merge_dict(base_val, value)
        else:
            merged[key] = value
    return merged


def extract_parent_context(
    contextualized_text: str,
    verbatim_text: str,
    parent_path: str,
    fallback_title: str | None = None,
) -> str:
    """Extracts clean parent breadcrumb context without echoing child provision text."""
    clean_v = verbatim_text.strip()
    clean_ctx = contextualized_text.strip()

    if clean_v and clean_ctx.endswith(clean_v):
        parent_candidate = clean_ctx[: -len(clean_v)].rstrip("\r\n").strip()
        if parent_candidate:
            return parent_candidate

    first_line_v = clean_v.splitlines()[0].strip() if clean_v else ""
    if first_line_v:
        pos = clean_ctx.find(first_line_v)
        if pos > 0:
            parent_candidate = clean_ctx[:pos].rstrip("\r\n").strip()
            if parent_candidate:
                return parent_candidate

    if fallback_title and fallback_title.strip():
        return fallback_title.strip()

    return f"[{parent_path}]"


def slice_raw_text(raw_text: str, start_line: int, end_line: int) -> str:
    """Deterministically slices 1-indexed line-bounded text from immutable raw statutory text."""
    lines = raw_text.splitlines()
    total = len(lines)
    if start_line < 1 or end_line < start_line or end_line > total:
        from rag_eval.legal.errors import E_AST_GROUNDING_VALIDATION, LegalDomainError

        raise LegalDomainError(
            error_code=E_AST_GROUNDING_VALIDATION,
            message=f"Tọa độ dòng [{start_line}..{end_line}] vượt ngoài giới hạn văn bản [1..{total}].",
            data={"start_line": start_line, "end_line": end_line, "total_lines": total},
        )
    return "\n".join(lines[start_line - 1 : end_line]).strip()


def normalize_grounding_text(text: str) -> str:
    """Normalizes whitespace, non-breaking spaces, and blank lines for deterministic legal text grounding comparisons."""
    clean = text.replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in clean.splitlines() if line.strip()]
    return "\n".join(lines)


def is_text_grounded(verbatim: str, expected_slice: str) -> bool:
    """Verifies that chunk verbatim text corresponds to sliced source text under normalized whitespace."""
    return normalize_grounding_text(verbatim) == normalize_grounding_text(expected_slice)


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


