"""Tells a data table apart from prose the source wrapped in table markup.

The corpus is scraped HTML, and the scraper preserves whatever the page used
for layout. Some of what arrives as a Markdown pipe table is a real table --
speed limits by vehicle class, sign dimensions by sign type -- and some is a
government form, or an ordinary provision that the page happened to rule.

Treating the second kind as a table is not cosmetic damage. `Điều 42` of
184/2025/NĐ-CP arrives as a thirteen-column grid with twelve columns empty, so
the chunker repeats the provision's own first line as a table header and splits
the statute across five windows of `| | ... | | | | |`. The provision is still
in the index, but as fragments wrapped in pipes.

The test is the share of cells that hold anything. Measured over every table
chunk in the live corpus, the two populations do not overlap:

    8%-32%   13 chunks   forms and framed prose, every one of them
      gap
    45%-100% 25 chunks   genuine tables, every one of them

Nothing sits between 32% and 45%, so the threshold is read off that gap rather
than guessed. `layout.py` already refuses framed prose on the PDF path with a
weaker rule -- two rows holding two cells -- which passes the 236/2026 form
grid: it has two such rows out of sixteen. Fill ratio catches what that misses.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Final

_ROW: Final = re.compile(r"^\s*\|.*\|\s*$")
_SEPARATOR: Final = re.compile(r"^\s*\|(?:\s*-{3,}\s*\|)+\s*$")

# Read off the empty band between the two populations, not chosen a priori.
MIN_FILL_RATIO: Final[float] = 0.40

# One data row and a header is the smallest thing worth calling a table; below
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
