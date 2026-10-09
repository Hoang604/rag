from __future__ import annotations

import datetime
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Final

import asyncpg

from rag_eval.legal.schemas.retrieval import AmendmentNote, SearchHit
from rag_eval.legal.text import address_of_path

_TARGET_ARTICLE: Final = re.compile(r"\bĐiều\s+(\d+[a-zA-Z]?)", re.IGNORECASE)
_TARGET_CLAUSE: Final = re.compile(r"\bkhoản\s+(\d+[a-zA-Z]?)", re.IGNORECASE)

_AMENDING_ARTICLES: Final = r"""
SELECT d.metadata->>'amends' AS target_doc,
       d.doc_code            AS doc_code,
       d.effective_date      AS effective_date,
       min(c.path::text)     AS path,
       'Điều ' || substring(c.path::text from '\.a_([0-9a-z]+)') AS label,
       c.metadata->>'article_title' AS title
FROM chunks c
JOIN documents d ON d.id = c.document_id
WHERE d.metadata->>'amends' IS NOT NULL
  AND c.metadata->>'article_title' IS NOT NULL
GROUP BY d.metadata->>'amends', d.doc_code, d.effective_date,
         substring(c.path::text from '\.a_([0-9a-z]+)'), c.metadata->>'article_title'
"""


def target_articles(title: str) -> list[str]:
    return [match.group(1).lower() for match in _TARGET_ARTICLE.finditer(title)]


def target_clauses(title: str) -> frozenset[str]:
    return frozenset(match.group(1).lower() for match in _TARGET_CLAUSE.finditer(title))


@dataclass(frozen=True)
class AmendmentIndex:
    by_target: dict[tuple[str, str], list[tuple[AmendmentNote, frozenset[str]]]]

    @classmethod
    def from_rows(cls, rows: list[asyncpg.Record] | list[dict[str, object]]) -> AmendmentIndex:
        by_target: dict[tuple[str, str], list[tuple[AmendmentNote, frozenset[str]]]] = defaultdict(list)
        for row in rows:
            title = str(row["title"] or "")
            clauses = target_clauses(title)
            for article in target_articles(title):
                note = AmendmentNote(
                    doc_code=str(row["doc_code"]),
                    label=str(row["label"] or ""),
                    title=title,
                    effective_date=row["effective_date"],
                    path=str(row["path"]),
                )
                by_target[(str(row["target_doc"]), article)].append((note, clauses))
        return cls(by_target=dict(by_target))

    @classmethod
    async def load(cls, pool: asyncpg.Pool) -> AmendmentIndex:
        return cls.from_rows(await pool.fetch(_AMENDING_ARTICLES))

    def notes_for(self, hit: SearchHit, on_date: datetime.date) -> list[AmendmentNote]:
        address = address_of_path(hit.path)
        if not address.dieu:
            return []
        clause = address.khoan.lower() if address.khoan else None
        return [
            note
            for note, clauses in self.by_target.get((hit.doc_code, address.dieu.lower()), [])
            if note.effective_date <= on_date
            and (not clauses or clause is None or clause in clauses)
        ]

    def annotate(self, hits: list[SearchHit], on_date: datetime.date) -> list[SearchHit]:
        return [
            hit.model_copy(update={"amended_by": notes}) if (notes := self.notes_for(hit, on_date)) else hit
            for hit in hits
        ]
