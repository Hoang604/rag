"""Derives robustness variants from questions whose answer is already verified.

Writing a thousand fresh questions costs a thousand judgements about what the
right answer is. Perturbing verified ones costs none: the answer is inherited,
and because each transformation is labelled, the report says exactly what each
kind of noise costs -- "dropping diacritics costs 9 points of Hit@1" is a
finding; "accuracy is 74%" is not.

Every transformation is deterministic and seeded by the query itself, so the
set is reproducible.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections.abc import Callable
from pathlib import Path
from typing import Any

# Written the way people type in a hurry, not the way a corpus is written.
_CHAT: tuple[tuple[str, str], ...] = (
    ("bao nhiêu", "bn"),
    ("thế nào", "ntn"),
    ("không", "ko"),
    ("được", "dc"),
    ("người", "ng"),
    ("những", "nhg"),
    ("với", "vs"),
    ("vậy", "v"),
    ("gì", "j"),
    ("phải", "fai"),
    ("trong", "trg"),
    ("nhưng", "nhg"),
)

# The tail carries no information about which provision answers the question.
_TAIL = re.compile(
    r"\s*(thì\s+)?(sẽ\s+)?(bị\s+)?(xử\s+)?(phạt|xử lý|xử phạt)"
    r"(\s+(bao nhiêu|thế nào|ra sao|mấy|như thế nào))?"
    r"(\s+tiền)?\s*[?.]?\s*$",
    re.IGNORECASE,
)
_LEAD = re.compile(
    r"^\s*(cho\s+hỏi|xin\s+hỏi|hỏi|em\s+hỏi|anh\s+ơi|mọi\s+người\s+ơi)[,\s]+",
    re.IGNORECASE,
)

_THOUSANDS = re.compile(r"\b(\d{1,3})\.000\.000\b")
_PADDED = re.compile(r"\b0(\d)\b")
_DECIMAL_COMMA = re.compile(r"\b(\d+),(\d+)\b")

_FILLERS = (
    "cho hỏi ",
    "mọi người ơi ",
    "anh chị cho em hỏi ",
)


def _seed(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)


def strip_diacritics(query: str) -> str:
    """Removes Vietnamese tone and vowel marks, the way a phone keyboard would."""
    decomposed = unicodedata.normalize("NFD", query)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return stripped.replace("đ", "d").replace("Đ", "D")


def chat_abbrev(query: str) -> str:
    """Replaces the words people shorten when typing into a search box."""
    lowered = query
    for full, short in _CHAT:
        lowered = re.sub(re.escape(full), short, lowered, flags=re.IGNORECASE)
    return lowered


def truncate(query: str) -> str:
    """Cuts the question down to the offence itself.

    Real searches are keyword-shaped: "xe máy vượt đèn đỏ", not "xe máy vượt
    đèn đỏ thì bị phạt bao nhiêu tiền?". The trimmed form is harder, because
    everything the ranker could use for a phrase match is in what remains.
    """
    trimmed = _TAIL.sub("", _LEAD.sub("", query)).strip(" ?.,")
    return trimmed if len(trimmed.split()) >= 3 else query


def number_reformat(query: str) -> str:
    """Writes the figures the way a person would, not the way the statute does."""
    out = _THOUSANDS.sub(lambda m: f"{int(m.group(1))} triệu", query)
    out = _PADDED.sub(lambda m: m.group(1), out)
    out = _DECIMAL_COMMA.sub(lambda m: f"{m.group(1)}.{m.group(2)}", out)
    return out


def typo(query: str) -> str:
    """Swaps two adjacent letters inside one longer word."""
    words = query.split()
    candidates = [i for i, w in enumerate(words) if len(w) >= 5 and w.isalpha()]
    if not candidates:
        return query
    index = candidates[_seed(query) % len(candidates)]
    word = words[index]
    cut = 1 + (_seed(word) % (len(word) - 2))
    words[index] = word[:cut] + word[cut + 1] + word[cut] + word[cut + 2 :]
    return " ".join(words)


def noise(query: str) -> str:
    """Adds the filler and punctuation a real message carries."""
    filler = _FILLERS[_seed(query) % len(_FILLERS)]
    return f"{filler}{query.rstrip('?. ')} ???"


TRANSFORMS: dict[str, Callable[[str], str]] = {
    "p_no_diacritics": strip_diacritics,
    "p_chat_abbrev": chat_abbrev,
    "p_truncate": truncate,
    "p_number_reformat": number_reformat,
    "p_typo": typo,
    "p_noise": noise,
}

# Applying a transform to a question already written in that style measures
# nothing, so each source style declines the ones that would be redundant.
_SKIP: dict[str, set[str]] = {
    "no_diacritics": {"p_no_diacritics", "p_typo"},
    "chat_abbrev": {"p_chat_abbrev"},
    "very_short": {"p_truncate"},
    "colloquial": {"p_truncate"},
    "number_format": {"p_number_reformat"},
    "teencode": {"p_chat_abbrev", "p_no_diacritics"},
}


def _carry(row: dict[str, Any]) -> dict[str, Any]:
    """Keeps whatever identifies the answer, in either fixture shape."""
    carried: dict[str, Any] = {}
    for key in ("source_path", "ground_truth", "violation_date", "expect", "domain"):
        if key in row:
            carried[key] = row[key]
    return carried


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+")
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--per-query", type=int, default=2, help="Variants to emit per base question"
    )
    args = parser.parse_args()

    rows: list[dict[str, Any]] = []
    for pattern in args.inputs:
        direct = Path(pattern)
        # Path.glob rejects an absolute pattern, and these files live outside
        # the repo, so an existing path is taken as given.
        found = [direct] if direct.exists() else sorted(Path().glob(pattern))
        for path in found:
            if not path.exists():
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    rows.append(json.loads(line))

    names = list(TRANSFORMS)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    for row in rows:
        query = str(row.get("query", ""))
        if not query.strip() or row.get("expect") == "miss":
            continue
        skip = _SKIP.get(str(row.get("style", "")), set())
        usable = [n for n in names if n not in skip]
        start = _seed(query) % len(usable)
        picked = [usable[(start + i) % len(usable)] for i in range(args.per_query)]

        for name in picked:
            variant = TRANSFORMS[name](query)
            if variant == query or variant.lower() in seen:
                continue
            seen.add(variant.lower())
            out.append(
                {
                    "query": variant,
                    "style": name,
                    "base_query": query,
                    "base_style": row.get("style"),
                    **_carry(row),
                }
            )

    Path(args.out).write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in out) + "\n",
        encoding="utf-8",
    )
    print(f"{len(rows)} câu gốc → {len(out)} biến thể → {args.out}")
    return 0


from rag_eval.legal.console import use_utf8_stdout

if __name__ == "__main__":
    use_utf8_stdout()
    raise SystemExit(main())
