from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Final

_ROW: Final = re.compile(r"^\s*\|.*\|\s*$")
_SEPARATOR: Final = re.compile(r"^\s*\|(?:\s*-{3,}\s*\|)+\s*$")

MIN_FILL_RATIO: Final[float] = 0.40

MIN_DATA_ROWS: Final[int] = 2


def fill_ratio(lines: Sequence[str]) -> float:
    """Share of cells that hold text, ignoring the `| --- |` separator."""
    filled = total = 0
    for line in lines:
        if _SEPARATOR.match(line) or not _ROW.match(line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        total += len(cells)
        filled += sum(1 for c in cells if c)
    return filled / total if total else 0.0


def is_data_table(lines: Sequence[str]) -> bool:
    """True when a run of pipe rows carries tabular data rather than layout.

    Deliberately conservative in one direction only: a real table wrongly
    called prose keeps its rows in one readable block, while prose wrongly
    called a table gets its sentences cut into cells and its first line
    repeated as a header on every window. The second failure is the one that
    destroys text, so the doubt resolves toward prose.
    """
    data = [x for x in lines if _ROW.match(x) and not _SEPARATOR.match(x)]
    if len(data) < MIN_DATA_ROWS:
        return False
    return fill_ratio(lines) >= MIN_FILL_RATIO
