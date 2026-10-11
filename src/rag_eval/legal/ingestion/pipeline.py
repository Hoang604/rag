"""Deterministic ingestion: raw text -> parse -> chunks -> citation edges -> PostgreSQL.

One transaction per document replaces its chunks. Edges are one kind, whoever
created them: an edge survives a re-ingest while its source and target still
exist and its citation text is still found in the source chunk, and is
otherwise deleted and logged INVALIDATED. Deterministic citation edges are
inserted only where the (source, target, relation) triple is missing.
"""

from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass

from rag_eval.legal.db.entities import (
    DocumentEntity,
    EdgeLogEntity,
    EdgeRow,
    GraphEdgeEntity,
)
from rag_eval.legal.db.repositories import LegalRepository
from rag_eval.legal.ingestion.citations import CitationHint, scan_citation_hints
from rag_eval.legal.ingestion.corpus import CorpusEntryError, SourceDocument
from rag_eval.legal.ingestion.cphc import CPHCEngine, form_lines
from rag_eval.legal.ingestion.embedder import (
    DEFAULT_EMBEDDING_DIM,
    DEFAULT_EMBEDDING_MODEL,
    compute_chunk_embeddings,
)
from rag_eval.legal.ingestion.parser import LegalASTParser
from rag_eval.legal.schemas.domain import StatutoryRelationType
from rag_eval.legal.text import (
    find_normalized_span,
    get_vietnam_now,
)


@dataclass(frozen=True)
class IngestReport:
    doc_code: str
    chunk_count: int
    edge_count: int
    invalidated_edges: int
    form_lines: int  # lines inside forms (biểu mẫu), deliberately left out of every chunk


async def ingest_document(
    repo: LegalRepository, source: SourceDocument, compute_embeddings: bool = True
) -> IngestReport:
    """Parses, chunks and links one document and replaces its DB state in a single transaction."""
    now = get_vietnam_now()
    root = LegalASTParser(source.doc_code).parse(source.raw_text, doc_title=source.title)
    async with repo.transaction() as conn:
        doc_id = await repo.documents.upsert(
            DocumentEntity(
                id=uuid.uuid4(),
                doc_code=source.doc_code,
                title=source.title,
                effective_date=source.effective_date,
                expiration_date=source.expiration_date,
                metadata=source.metadata,
                raw_text=source.raw_text,
                created_at=now,
                updated_at=now,
            ),
            conn,
        )
        chunks = CPHCEngine(
            document_id=doc_id,
            doc_code=source.doc_code,
            doc_title=source.title,
            raw_text=source.raw_text,
            effective_date=source.effective_date,
            expiration_date=source.expiration_date,
        ).chunk_ast(root)
        if not chunks:
            raise CorpusEntryError(f"{source.doc_code}: the parser produced no chunks")
        hints = scan_citation_hints(source.raw_text, root, chunks)
        active_paths = {c.path for c in chunks}

        touching = await repo.graph.list_edges_touching(doc_id, conn)
        removed_paths = set(await repo.chunks.purge_stale_chunks(source.doc_code, sorted(active_paths), conn))
        orphaned = [e for e in touching if e.source_path in removed_paths or e.target_path in removed_paths]
        texts = list(dict.fromkeys(c.contextualized_text for c in chunks))
        vectors = await repo.embeddings.lookup(DEFAULT_EMBEDDING_MODEL, DEFAULT_EMBEDDING_DIM, texts, conn)
        missing = [t for t in texts if t not in vectors]
        if missing and compute_embeddings:
            computed = dict(zip(missing, compute_chunk_embeddings(missing), strict=True))
            await repo.embeddings.store(DEFAULT_EMBEDDING_MODEL, DEFAULT_EMBEDDING_DIM, computed, now, conn)
            vectors |= computed
        path_to_id = await repo.chunks.upsert_batch(chunks, vectors, conn)

        verbatim_by_path = {c.path: c.verbatim_text for c in chunks}
        ungrounded = [
            e
            for e in touching
            if e not in orphaned
            and e.source_path in verbatim_by_path
            and find_normalized_span(verbatim_by_path[e.source_path], e.citation_text) is None
        ]
        for edge in ungrounded:
            await repo.graph.delete_edge(edge.edge_id, conn)

        target_paths = sorted({t for chunk_hints in hints.values() for h in chunk_hints for t in h.target_paths})
        leaves = await repo.chunks.expand_to_leaf_paths(target_paths, conn)
        proposed = _deterministic_edges(hints, path_to_id, leaves, now)
        inserted = await repo.graph.insert_edges(proposed, conn)
        path_of = {cid: path for path, cid in path_to_id.items()}
        await repo.graph.log_edge_events(
            [_invalidated(e, "SOURCE_OR_TARGET_REMOVED", now) for e in orphaned]
            + [_invalidated(e, "CITATION_NO_LONGER_GROUNDED", now) for e in ungrounded]
            + [
                EdgeLogEntity.record(
                    "ADDED",
                    "INGEST",
                    path_of[e.source_chunk_id],
                    path_of[e.target_chunk_id],
                    e.relation_type,
                    e.citation_text,
                    "DETERMINISTIC_CITATION",
                    now,
                )
                for e in inserted
            ],
            conn,
        )

    return IngestReport(
        doc_code=source.doc_code,
        chunk_count=len(chunks),
        edge_count=len(proposed),
        invalidated_edges=len(orphaned) + len(ungrounded),
        form_lines=form_lines(root),
    )


def _deterministic_edges(
    hints: dict[str, list[CitationHint]],
    path_to_id: dict[str, uuid.UUID],
    leaves: dict[str, list[tuple[str, uuid.UUID]]],
    now: datetime.datetime,
) -> list[GraphEdgeEntity]:
    """One REFERENCES edge per (source chunk, leaf target); `leaves` maps each target path to its leaf chunks."""
    edges: dict[tuple[uuid.UUID, uuid.UUID], GraphEdgeEntity] = {}
    for source_path, chunk_hints in hints.items():
        source_id = path_to_id[source_path]
        for hint in chunk_hints:
            for target in hint.target_paths:
                for _, target_id in leaves[target]:
                    if target_id == source_id or (source_id, target_id) in edges:
                        continue
                    edges[(source_id, target_id)] = GraphEdgeEntity(
                        id=uuid.uuid4(),
                        source_chunk_id=source_id,
                        target_chunk_id=target_id,
                        relation_type=StatutoryRelationType.REFERENCES,
                        citation_text=hint.text,
                        created_at=now,
                    )
    return list(edges.values())


def _invalidated(edge: EdgeRow, reason: str, now: datetime.datetime) -> EdgeLogEntity:
    return EdgeLogEntity.record(
        "INVALIDATED", "INGEST", edge.source_path, edge.target_path, edge.relation_type, edge.citation_text, reason, now
    )
