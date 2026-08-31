"""Vietnamese Traffic Law Grammar and Deterministic Regex Tokenizer.

Provides production-grade regular expression patterns for parsing Vietnamese legislative documents
into 6-tier syntactic AST hierarchies, recognizing technical standard sign specs and road markings,
and extracting statutory cross-references, fine bounds, license suspensions, and exception clauses.
"""

from __future__ import annotations

import re
from re import Pattern
from typing import ClassVar


class VietnameseLegalGrammar:
    """Production-grade regex grammar for Vietnamese Traffic Law ingestion and AST modeling.

    Conforms to the Law on Promulgation of Legislative Documents (Luật Ban hành VBQPPL)
    and National Technical Regulation QCVN 41:2019/BGTVT.
    Hardened against ReDoS (Catastrophic Backtracking) via deterministic linear-scan patterns.
    """

    # Level 1: Document Header (Conforms to Law on Promulgation of Legislative Documents 2015/2020)
    DOC_HEADER: ClassVar[Pattern[str]] = re.compile(
        r"^(LUẬT|NGHỊ QUYẾT|PHÁP LỆNH|LỆNH|NGHỊ ĐỊNH|QUYẾT ĐỊNH|THÔNG TƯ|THÔNG TƯ LIÊN TỊCH|QUY CHUẨN KỸ THUẬT QUỐC GIA|TIÊU CHUẨN QUỐC GIA|TIÊU CHUẨN VIỆT NAM|CHỈ THỊ)\s*\n"
        r"(?:Số:\s*([0-9]+/[0-9]+/[A-Z0-9Đ\-]+|(?:QCVN|TCVN)\s*[0-9]+:[0-9]+/[A-Z0-9Đ\-]+))\s*\n"
        r"(?P<title>[^\n]+(?:\n(?!(?:Căn cứ|Chương|Điều|Mục)\b)[^\n]+)*)",
        re.IGNORECASE | re.MULTILINE,
    )

    # Level 2: Chapter (Chương) - Supports both multi-line and single-line syntax
    CHAPTER: ClassVar[Pattern[str]] = re.compile(
        r"^Chương\s+([IVXLCDM0-9]+)\s*(?:[\.\:\-]\s*|\n+|\s+)([^\n]+)",
        re.MULTILINE | re.IGNORECASE,
    )

    # Level 3: Section (Mục) - Supports both multi-line and single-line syntax
    SECTION: ClassVar[Pattern[str]] = re.compile(
        r"^Mục\s+([0-9]+)\s*(?:[\.\:\-]\s*|\n+|\s+)([^\n]+)",
        re.MULTILINE | re.IGNORECASE,
    )

    # Level 3.5: Sub-section (Tiểu mục)
    SUB_SECTION: ClassVar[Pattern[str]] = re.compile(
        r"^Tiểu\s+mục\s+([0-9]+)\s*(?:[\.\:\-]\s*|\n+|\s+)([^\n]+)",
        re.MULTILINE | re.IGNORECASE,
    )

    # Level 4: Article (Điều)
    ARTICLE: ClassVar[Pattern[str]] = re.compile(
        r"^Điều\s+([0-9]+[a-zA-ZđĐ]*)[\.\:\-]?\s*([^\n]+)",
        re.MULTILINE,
    )

    # Level 5: Clause (Khoản) - Leading number followed by period (ReDoS safe)
    CLAUSE: ClassVar[Pattern[str]] = re.compile(
        r"^([0-9]+)\.\s+([^\n]+(?:\n(?![0-9]+\.|\b[a-zđ]\)|\bĐiều\s+[0-9]+|\bChương\s+[IVXLCDM0-9]+|\bMục\s+[0-9]+)[^\n]+)*)",
        re.MULTILINE,
    )

    # Level 6: Point (Điểm) - Lowercase letter followed by closing parenthesis (ReDoS safe)
    POINT: ClassVar[Pattern[str]] = re.compile(
        r"^([a-zđ])\)\s+([^\n]+(?:\n(?![a-zđ]\)|[0-9]+\.|\bĐiều\s+[0-9]+|\bChương\s+[IVXLCDM0-9]+|\bMục\s+[0-9]+)[^\n]+)*)",
        re.MULTILINE,
    )

    # Technical Appendix & Specifications (QCVN 41:2019/BGTVT)
    APPENDIX: ClassVar[Pattern[str]] = re.compile(
        r"^PHỤ LỤC\s+([A-Z0-9]+)\s*(?:[\.\:\-]\s*|\n+|\s+)([^\n]+)",
        re.MULTILINE | re.IGNORECASE,
    )

    # ReDoS-hardened Multi-Family Sign Spec Pattern
    SIGN_SPEC: ClassVar[Pattern[str]] = re.compile(
        r"^(?:Biển\s+số\s+|Biển\s+)?([A-Z]{1,3}\.[0-9]+[a-zđ]?|[A-Z]{1,3}[0-9]+[a-zđ]?|[0-9]+\.[0-9]+[a-zđ]?)\s*[:\.]\s*([^\n]+)\s*\n+"
        r"(?P<body>[^\n]+(?:\n(?!(?:(?:Biển\s+số\s+|Biển\s+)?[A-Z]{1,3}\.[0-9]+|[0-9]+\.[0-9]+|Điều\s+[0-9]+|PHỤ LỤC|\Z)\b)[^\n]+)*)",
        re.MULTILINE | re.IGNORECASE,
    )

    # ReDoS-hardened Road Marking Spec Pattern
    MARKING_SPEC: ClassVar[Pattern[str]] = re.compile(
        r"^(?:Vạch\s+số\s+|Vạch\s+)?([0-9]+\.[0-9]+[a-zđ]?|[A-Z]\.[0-9]+[a-zđ]?|M\.[0-9]+\.[0-9]+)\s*[:\.]\s*([^\n]+)\s*\n+"
        r"(?P<body>[^\n]+(?:\n(?!(?:(?:Vạch\s+số\s+|Vạch\s+)?[0-9]+\.[0-9]+|[A-Z]\.[0-9]+|Điều\s+[0-9]+|PHỤ LỤC|\Z)\b)[^\n]+)*)",
        re.MULTILINE | re.IGNORECASE,
    )

    # Cross-Reference Patterns
    ARTICLE_REF_REGEX: ClassVar[Pattern[str]] = re.compile(
        r"(?:quy định tại|theo quy định tại|tại)?\s*"
        r"(?:(?:các\s+)?điểm\s+(?P<point>[a-zđ])[\s,]+)?"
        r"(?:khoản\s+(?P<clause>\d+)[\s,]+)?"
        r"(?:điều\s+(?P<article>\d+[a-zA-ZđĐ]*|này))"
        r"(?:\s+(?:luật|nghị định|thông tư|văn bản)?\s*(?P<doc_ref>[0-9]+/[0-9]+/[A-Z0-9Đ\-]+|[A-Za-zÀ-Ỹà-ỹĐđ0-9\s]+)?)?",
        re.IGNORECASE,
    )

    # Compound Cross-Reference Regex (Multiple points, e.g. "điểm a, điểm b khoản 3")
    ARTICLE_REF_COMPOUND: ClassVar[Pattern[str]] = re.compile(
        r"(?:quy định tại|theo quy định tại|tại)?\s*"
        r"(?:(?:các\s+)?điểm\s+(?P<points>[a-zđ,\s\bvà]+)[\s,]+)?"
        r"(?:khoản\s+(?P<clause>\d+)[\s,]+)?"
        r"(?:điều\s+(?P<article>\d+[a-zA-ZđĐ]*|này))"
        r"(?:\s+(?:luật|nghị định|thông tư|văn bản)?\s*(?P<doc_ref>[0-9]+/[0-9]+/[A-Z0-9Đ\-]+|[A-Za-zÀ-Ỹà-ỹĐđ0-9\s]+)?)?",
        re.IGNORECASE,
    )

    SIGN_REF_REGEX: ClassVar[Pattern[str]] = re.compile(
        r"(?:biển\s+(?:báo|hiệu)?\s*(?:số)?\s*(?P<sign_code>[A-Z]{1,3}\.[0-9]+[a-zđ]?|[A-Z]{1,3}[0-9]+[a-zđ]?)|"
        r"biển\s+['\"](?P<sign_name>[^'\"]+)['\"])",
        re.IGNORECASE,
    )

    MARKING_REF_REGEX: ClassVar[Pattern[str]] = re.compile(
        r"vạch\s+(?:kẻ đường\s+)?(?:số\s+)?(?P<marking_code>[0-9]+\.[0-9]+[a-zđ]?|M\.[0-9]+\.[0-9]+)",
        re.IGNORECASE,
    )

    DECREE_AMENDMENT_REGEX: ClassVar[Pattern[str]] = re.compile(
        r"(?:sửa đổi|bổ sung|thay thế|bãi bỏ)(?:\s+bởi)?\s+"
        r"(?:Nghị định|NĐ|Thông tư|TT|Luật|Quyết định)?\s*(?:số\s*)?"
        r"(?P<doc_code>[0-9]+/[0-9]+/[A-Z0-9Đ\-]+)",
        re.IGNORECASE,
    )

    # Fine Range Extraction Pattern
    FINE_RANGE_REGEX: ClassVar[Pattern[str]] = re.compile(
        r"Phạt\s+tiền\s+từ\s+"
        r"(?P<min_val>[0-9\.\,]+)\s*(?P<min_unit>đồng|triệu\s+đồng|nghìn\s+đồng|tỷ\s+đồng)?\s+"
        r"đến\s+"
        r"(?P<max_val>[0-9\.\,]+)\s*(?P<max_unit>đồng|triệu\s+đồng|nghìn\s+đồng|tỷ\s+đồng)",
        re.IGNORECASE,
    )

    # Supplementary Sanctions Extraction Patterns (Generalized to all legislative sanctions)
    SUSPENSION_REGEX: ClassVar[Pattern[str]] = re.compile(
        r"tước\s+quyền\s+sử\s+dụng\s+"
        r"(?:Giấy\s+phép\s+lái\s+xe|GPLX|chứng\s+chỉ\s+bồi\s+dưỡng\s+kiến\s+thức[^\n,;]*|phù\s+hiệu[^\n,;]*|giấy\s+chứng\s+nhận[^\n,;]*|giấy\s+phép[^\n,;]*)\s+"
        r"(?:từ\s+(?P<min_months>[0-9]+)\s*(?:tháng)?\s*đến\s*(?P<max_months>[0-9]+)\s*tháng|"
        r"(?P<fixed_months>[0-9]+)\s*tháng)",
        re.IGNORECASE,
    )

    IMPOUNDMENT_REGEX: ClassVar[Pattern[str]] = re.compile(
        r"tạm\s+giữ\s+phương\s+tiện\s+(?:đến|từ\s+[0-9]+\s*đến)?\s*(?P<days>[0-9]+)\s*ngày",
        re.IGNORECASE,
    )

    DEMERIT_REGEX: ClassVar[Pattern[str]] = re.compile(
        r"(?:trừ|bị\s+trừ)\s+(?P<points>[0-9]+)\s*điểm(?:\s+trên\s+Giấy\s+phép\s+lái\s+xe)?",
        re.IGNORECASE,
    )

    EXCEPTION_REGEX: ClassVar[Pattern[str]] = re.compile(
        r"(?:trừ\s+trường\s+hợp|trừ\s+các\s+hành\s+vi|trừ\s+các\s+xe|trừ\s+xe|ngoại\s+trừ)\s+(?P<clause_text>[^\n;\.]+)",
        re.IGNORECASE,
    )


def parse_vnd_amount(val_str: str, unit_str: str | None = None) -> int | None:
    """Parses Vietnamese numeric strings and unit multipliers into an exact integer VND value.

    Args:
        val_str: Numeric string (e.g. '800.000', '1.000.000', '4', '0,4').
        unit_str: Unit string (e.g. 'đồng', 'triệu đồng', 'nghìn đồng', 'tỷ đồng').

    Returns:
        Exact integer amount in VND, or None if parsing fails.
    """
    clean_val = val_str.strip().replace(" ", "")
    if not clean_val:
        return None

    if "." in clean_val and "," in clean_val:
        clean_val = clean_val.replace(".", "").replace(",", ".")
    elif "," in clean_val:
        clean_val = clean_val.replace(",", ".")
    elif "." in clean_val:
        parts = clean_val.split(".")
        if all(len(p) == 3 for p in parts[1:]):
            clean_val = clean_val.replace(".", "")

    try:
        base_val = float(clean_val)
    except (ValueError, TypeError):
        return None

    unit = (unit_str or "đồng").lower().strip()
    if "tỷ" in unit:
        return round(base_val * 1_000_000_000)
    if "triệu" in unit or "tr" in unit:
        return round(base_val * 1_000_000)
    if "nghìn" in unit or "ngàn" in unit or "k" in unit:
        return round(base_val * 1_000)

    return round(base_val)
