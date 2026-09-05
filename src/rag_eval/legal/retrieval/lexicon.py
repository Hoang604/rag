"""Colloquial-to-statutory query expansion for the sparse half of retrieval.

Nobody asks "không chấp hành hiệu lệnh của đèn tín hiệu giao thông" -- they ask
"vượt đèn đỏ". The two share no lexeme, so the sparse ranker scored the correct
provision 821st while dense had it 12th. Expansion appends the statutory wording
to the text the tsquery is built from; the dense vector is still computed from
what the user actually wrote, so the two halves keep their independence and a
wrong expansion cannot poison both.

Every replacement below is a phrase verified to occur in the corpus.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Final

# Ordered longest-context-first so "vượt đèn đỏ" is not consumed by "đèn đỏ".
_SYNONYMS: Final[tuple[tuple[re.Pattern[str], str], ...]] = tuple(
    (re.compile(pattern), expansion)
    for pattern, expansion in (
        (
            r"vượt đèn đỏ|vượt đèn|đèn đỏ|vượt đèn tín hiệu",
            "không chấp hành hiệu lệnh của đèn tín hiệu giao thông",
        ),
        (r"kẹp ba|kẹp 3|chở ba|chở 3", "chở theo từ 03 người trở lên trên xe"),
        (r"mũ bảo hiểm|nón bảo hiểm", "mũ bảo hiểm cho người đi mô tô, xe máy"),
        (r"ngược chiều", "đi ngược chiều của đường một chiều"),
        (r"quá tốc độ|chạy nhanh|vượt tốc độ", "chạy quá tốc độ quy định"),
        (r"nồng độ cồn|có cồn|uống rượu|uống bia|say rượu", "trong máu hoặc hơi thở có nồng độ cồn"),
        (r"bằng lái|gplx|giấy phép lái", "giấy phép lái xe"),
        (r"trừ điểm", "trừ điểm giấy phép lái xe"),
        (r"điện thoại", "dùng tay cầm và sử dụng điện thoại"),
        (r"xi nhan|si nhan|không báo rẽ", "không có tín hiệu báo hướng rẽ"),
        (r"đèn pha|pha xa", "sử dụng đèn chiếu xa"),
        (r"làn khẩn cấp|làn dừng khẩn cấp", "làn dừng xe khẩn cấp"),
        (r"dây an toàn|dây đai", "không thắt dây đai an toàn"),
        (r"biển số|bảng số", "không gắn đủ biển số"),
        (r"vỉa hè|lề đường", "dừng xe không sát theo lề đường, vỉa hè phía bên phải"),
    )
)

# Statutes write small counts zero-padded -- "chở theo từ 03 người" -- and the
# tokeniser makes "3" and "03" different lexemes, so a question phrased with a
# bare digit never matches the clause that answers it.
_BARE_DIGIT = re.compile(r"(?<![\d,.])([1-9])(?![\d,.])")

MAX_EXPANSIONS: Final[int] = 4


def _fold(text: str) -> str:
    return unicodedata.normalize("NFC", text).casefold()


def expand_query(query: str) -> str:
    """Returns the query with statutory phrasings appended for sparse matching.

    The original text is kept in front: a literal quotation must still win the
    phrase bonus. At most four expansions are appended, because each one adds
    syllable pairs that dilute ts_rank across the whole candidate pool.
    """
    folded = _fold(query)
    additions: list[str] = []

    for pattern, expansion in _SYNONYMS:
        if len(additions) >= MAX_EXPANSIONS:
            break
        if pattern.search(folded) and _fold(expansion) not in folded:
            additions.append(expansion)

    padded = _BARE_DIGIT.sub(lambda m: f"0{m.group(1)}", query)
    if padded != query:
        additions.append(padded)

    if not additions:
        return query
    return " ".join([query, *additions])
