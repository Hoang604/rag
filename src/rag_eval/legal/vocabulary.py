"""Loads the domain vocabulary that used to sit in `facets.py` and `lexicon.py`.

Those five catalogues -- vehicle names, colloquial synonyms, intent markers --
were Python literals, which meant a decree introducing a vehicle class the
corpus had not seen required a source change and a redeploy. The project's own
rule is that ingesting a new document must work with zero code modification,
and a static catalogue in code is exactly what that rule forbids.

The patterns are data now. `data/vocabulary.toml` is the only place a new
vehicle class, synonym or marker is added.

Read once and cached. The call sites (`classify_query`, `expand_query`) run
inside every search and are synchronous, which is also why this is a file and
not a database table: a table would need an async load threaded through
ingestion, the MCP server and every evaluation script, to buy a runtime edit
nothing currently performs. When something does, this module is the seam.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Final

from rag_eval.legal.text import fold_diacritics

_SOURCE: Final[Path] = Path(__file__).resolve().parent / "data" / "vocabulary.toml"


@dataclass(frozen=True)
class Vocabulary:
    """Every pattern the retrieval layer matches Vietnamese with."""

    vehicle_heading: tuple[tuple[str, re.Pattern[str]], ...]
    vehicle_query: tuple[tuple[str, re.Pattern[str]], ...]
    general_heading: re.Pattern[str]
    role_markers: tuple[tuple[str, str], ...]
    intent: tuple[tuple[str, re.Pattern[str]], ...]
    synonyms: tuple[tuple[re.Pattern[str], str], ...]


def _compiled(entries: list[dict[str, str]], label: str) -> tuple:
    # Folded on the way in, so a rule written with diacritics matches input
    # typed without them and the file stays readable to a person.
    return tuple(
        (entry[label], re.compile(fold_diacritics(entry["pattern"])))
        for entry in entries
    )


@lru_cache(maxsize=1)
def vocabulary() -> Vocabulary:
    """Parses the vocabulary file, once per process."""
    raw = tomllib.loads(_SOURCE.read_text(encoding="utf-8"))
    return Vocabulary(
        vehicle_heading=_compiled(raw["vehicle_heading"], "class"),
        vehicle_query=_compiled(raw["vehicle_query"], "class"),
        general_heading=re.compile(fold_diacritics(raw["general_heading"]["pattern"])),
        role_markers=tuple(
            (entry["role"], fold_diacritics(entry["marker"]))
            for entry in raw["role_marker"]
        ),
        intent=_compiled(raw["intent"], "role"),
        # Order is load-bearing and the file says so: the longest context must
        # be tried first or "vượt đèn đỏ" is consumed by "đèn đỏ".
        synonyms=tuple(
            (re.compile(fold_diacritics(entry["pattern"])), entry["expansion"])
            for entry in raw["synonym"]
        ),
    )
