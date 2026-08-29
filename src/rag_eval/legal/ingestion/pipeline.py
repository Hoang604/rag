"""Legal Ingestion Pipeline Orchestrator.

Orchestrates full end-to-end statutory ingestion from raw text/files through AST parsing,
Context-Preserving Hierarchical Chunking (CPHC), cross-reference graph linking,
and PostgreSQL persistence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rag_eval.legal.ingestion.benchmark_gen import SyntheticBenchmarkGenerator
from rag_eval.legal.ingestion.cphc import CPHCEngine
from rag_eval.legal.ingestion.grammar import VietnameseLegalGrammar
from rag_eval.legal.ingestion.graph_linker import DeterministicGraphLinker
from rag_eval.legal.ingestion.loader import PostgresBulkLoader
from rag_eval.legal.ingestion.parser import ASTNode, LegalASTParser
from rag_eval.legal.schemas import (
    CanonicalFullyQualifiedChunk,
    GraphRelationType,
    LegalNormExtraction,
    SyntheticQAPair,
)


@dataclass
class IngestionResult:
    """Encapsulates the complete artifacts of a legal ingestion run."""

    doc_code: str
    doc_title: str
    ast_root: ASTNode
    hierarchy_nodes: list[ASTNode]
    chunks: list[CanonicalFullyQualifiedChunk]
    norms: list[LegalNormExtraction]
    edges: list[dict[str, Any]]
    persisted_stats: dict[str, int] = field(default_factory=lambda: dict[str, int]())
    benchmarks: list[SyntheticQAPair] = field(
        default_factory=lambda: list[SyntheticQAPair]()
    )


@dataclass
class TemporalDiffResult:
    """Encapsulates the output of an incremental temporal AST diff update."""

    base_doc_code: str
    amending_doc_code: str
    modified_base_chunk_ids: list[str]
    amended_chunks: list[CanonicalFullyQualifiedChunk]
    new_chunks: list[CanonicalFullyQualifiedChunk]
    modifies_edges: list[dict[str, Any]]
    all_active_chunks: list[CanonicalFullyQualifiedChunk]
    persisted_stats: dict[str, int] = field(default_factory=lambda: dict[str, int]())


class TemporalASTDiffEngine:
    """Incremental Temporal AST Diff Engine for amending decrees (NĐ 123/2021, NĐ 168/2024).

    Identifies modified provisions across legislative AST versions, marks superseded units as
    is_amended=True with expiration dates, generates new CanonicalFullyQualifiedChunks for amended
    provisions, and establishes MODIFIES_AND_REPLACES knowledge graph edges without destructive drop.
    """

    AMENDMENT_PATTERN = re.compile(
        r"sửa\s+đổi[,\s\bvà]+bổ\s+sung\s+(?:(?:các\s+)?(?:điểm\s+)?(?P<point>[a-zđ,\s\bvà]+)[\s,]+)?(?:khoản\s+(?P<clause>\d+)[\s,]+)?điều\s+(?P<article>\d+)(?:[\s,]+(?:của\s+)?(?:nghị\s+định|luật|thông\s+tư)?\s*(?:số\s*)?(?P<doc>[0-9/A-ZÀ-Ỹa-zà-ỹĐđ\-]+))?",
        re.IGNORECASE,
    )

    def __init__(
        self,
        grammar: type[VietnameseLegalGrammar] = VietnameseLegalGrammar,
        parser: LegalASTParser | None = None,
        cphc: CPHCEngine | None = None,
        linker: DeterministicGraphLinker | None = None,
    ) -> None:
        self.grammar = grammar
        self.parser = parser or LegalASTParser(grammar)
        self.cphc = cphc or CPHCEngine(grammar)
        self.linker = linker or DeterministicGraphLinker(grammar)

    def diff_and_apply_amendment(
        self,
        base_chunks: list[CanonicalFullyQualifiedChunk],
        amending_doc_code: str,
        amending_raw_text: str,
        amending_doc_title: str | None = None,
        amending_effective_date: str = "2022-01-01",
        base_doc_code: str = "100/2019/NĐ-CP",
    ) -> TemporalDiffResult:
        """Computes incremental AST diff between amending enactment and base decree chunks."""
        title = amending_doc_title or amending_doc_code
        amending_ast = self.parser.parse_document(
            doc_code=amending_doc_code,
            raw_text=amending_raw_text,
            doc_title=title,
            doc_type="NGHI_DINH",
        )

        new_chunks, new_norms = self.cphc.process_ast(
            root=amending_ast,
            effective_date=amending_effective_date,
        )

        modifies_edges = self.linker.extract_edges_from_chunks(
            chunks=new_chunks,
            norms=new_norms,
            ast_root=amending_ast,
        )

        # Index base chunks by path and article/clause/point
        base_chunks_by_path: dict[str, CanonicalFullyQualifiedChunk] = {
            c.hierarchy_path: c for c in base_chunks
        }
        modified_chunk_ids: list[str] = []
        amended_base_chunks: list[CanonicalFullyQualifiedChunk] = []

        # 1. Match from MODIFIES_AND_REPLACES edges
        for edge in modifies_edges:
            if edge.get("relation_type") == GraphRelationType.MODIFIES_AND_REPLACES.value:
                target_path = edge.get("target_path", "")
                for path, b_chunk in base_chunks_by_path.items():
                    if (
                        path == target_path
                        or (target_path and target_path in path)
                        or (
                            b_chunk.article_number
                            and f".a{b_chunk.article_number}" in target_path
                            and (b_chunk.clause_number is None or f".c{b_chunk.clause_number}" in target_path)
                            and (b_chunk.point_letter is None or f".p_{b_chunk.point_letter.lower()}" in target_path)
                        )
                    ):
                        b_chunk.is_amended = True
                        b_chunk.is_active = False
                        b_chunk.expiry_date = amending_effective_date
                        b_chunk.expiration_date = amending_effective_date
                        b_chunk.amended_by = amending_doc_code
                        if b_chunk.chunk_id not in modified_chunk_ids:
                            modified_chunk_ids.append(b_chunk.chunk_id)
                            amended_base_chunks.append(b_chunk)

        # 2. Match from in-text amendment patterns
        for new_c in new_chunks:
            scan_text = f"{new_c.synthesized_prefix}\n{new_c.lead_sentence or ''}\n{new_c.verbatim_text}\n{new_c.contextualized_text}"
            m = self.AMENDMENT_PATTERN.search(scan_text)
            if m:
                pt_group = m.group("point")
                cl_group = m.group("clause")
                art_group = m.group("article")
                target_art = int(art_group) if art_group else None
                target_cl = int(cl_group) if cl_group else None
                target_pts = (
                    [p.strip().lower() for p in pt_group.split(",") if p.strip()]
                    if pt_group
                    else []
                )

                for path, b_chunk in base_chunks_by_path.items():
                    if b_chunk.article_number == target_art:
                        match_clause = (
                            target_cl is None or b_chunk.clause_number == target_cl
                        )
                        match_point = (
                            not target_pts
                            or (
                                b_chunk.point_letter
                                and b_chunk.point_letter.lower() in target_pts
                            )
                        )
                        if match_clause and match_point:
                            b_chunk.is_amended = True
                            b_chunk.is_active = False
                            b_chunk.expiry_date = amending_effective_date
                            b_chunk.expiration_date = amending_effective_date
                            b_chunk.amended_by = amending_doc_code
                            if b_chunk.chunk_id not in modified_chunk_ids:
                                modified_chunk_ids.append(b_chunk.chunk_id)
                                amended_base_chunks.append(b_chunk)

        # Full active set
        all_active_chunks: list[CanonicalFullyQualifiedChunk] = [
            c for c in base_chunks if c.is_active
        ] + [c for c in new_chunks if c.is_active]

        return TemporalDiffResult(
            base_doc_code=base_doc_code,
            amending_doc_code=amending_doc_code,
            modified_base_chunk_ids=modified_chunk_ids,
            amended_chunks=amended_base_chunks,
            new_chunks=new_chunks,
            modifies_edges=modifies_edges,
            all_active_chunks=all_active_chunks,
            persisted_stats={
                "base_chunks_amended": len(modified_chunk_ids),
                "new_chunks_created": len(new_chunks),
                "modifies_edges_created": len(modifies_edges),
            },
        )


class LegalIngestionPipeline:
    """High-level orchestration pipeline for Vietnamese Traffic Law ingestion."""

    def __init__(
        self,
        parser: LegalASTParser | None = None,
        cphc: CPHCEngine | None = None,
        linker: DeterministicGraphLinker | None = None,
        loader: PostgresBulkLoader | None = None,
        benchmark_gen: SyntheticBenchmarkGenerator | None = None,
        diff_engine: TemporalASTDiffEngine | None = None,
    ) -> None:
        self.parser = parser or LegalASTParser(VietnameseLegalGrammar)
        self.cphc = cphc or CPHCEngine(VietnameseLegalGrammar)
        self.linker = linker or DeterministicGraphLinker(VietnameseLegalGrammar)
        self.loader = loader
        self.benchmark_gen = benchmark_gen or SyntheticBenchmarkGenerator(
            VietnameseLegalGrammar
        )
        self.diff_engine = diff_engine or TemporalASTDiffEngine(
            grammar=VietnameseLegalGrammar,
            parser=self.parser,
            cphc=self.cphc,
            linker=self.linker,
        )

    async def ingest_text(
        self,
        doc_code: str,
        raw_text: str,
        doc_title: str | None = None,
        doc_type: str = "NGHI_DINH",
        promulgation_date: str = "2020-01-01",
        effective_date: str = "2020-01-15",
        issuing_authority: str = "Chính phủ",
        signer: str | None = None,
        persist_db: bool = False,
        generate_benchmark: bool = False,
        benchmark_output_path: str | Path | None = None,
    ) -> IngestionResult:
        """Executes the full ingestion pipeline on in-memory raw legal text."""
        title = doc_title or doc_code

        # Step 1: AST Parsing
        ast_root = self.parser.parse_document(
            doc_code=doc_code,
            raw_text=raw_text,
            doc_title=title,
            doc_type=doc_type,
        )
        hierarchy_nodes = ast_root.flatten()

        # Step 2: CPHC Chunking & Context Preservation
        chunks, norms = self.cphc.process_ast(
            root=ast_root,
            effective_date=effective_date,
        )

        # Step 3: Graph Cross-Reference Linking
        edges = self.linker.extract_edges_from_chunks(
            chunks=chunks,
            norms=norms,
            ast_root=ast_root,
        )

        # Step 4: Synthetic Benchmark Generation (Stage 4)
        benchmarks: list[SyntheticQAPair] = []
        if generate_benchmark:
            benchmarks = self.benchmark_gen.generate_benchmark_suite(
                chunks=chunks,
                edges=edges,
                output_path=benchmark_output_path,
            )

        # Step 5: Optional Database Persistence
        persisted_stats: dict[str, int] = {}
        if persist_db and self.loader is not None:
            doc_uuid = await self.loader.load_document(
                doc_code=doc_code,
                title=title,
                doc_type=doc_type,
                issuing_authority=issuing_authority,
                signer=signer,
                promulgation_date=promulgation_date,
                effective_date=effective_date,
            )
            node_id_map = await self.loader.load_hierarchy_nodes(
                nodes=hierarchy_nodes,
                document_id=doc_uuid,
            )
            chunk_id_map = await self.loader.load_chunks(
                chunks=chunks,
                document_id=doc_uuid,
                node_id_map=node_id_map,
            )
            edge_count = await self.loader.load_graph_edges(
                edges=edges,
                chunk_id_map=chunk_id_map,
                node_id_map=node_id_map,
            )
            persisted_stats = {
                "nodes_loaded": len(node_id_map),
                "chunks_loaded": len(chunk_id_map),
                "edges_loaded": edge_count,
            }

        return IngestionResult(
            doc_code=doc_code,
            doc_title=title,
            ast_root=ast_root,
            hierarchy_nodes=hierarchy_nodes,
            chunks=chunks,
            norms=norms,
            edges=edges,
            persisted_stats=persisted_stats,
            benchmarks=benchmarks,
        )

    async def ingest_file(
        self,
        file_path: str | Path,
        doc_code: str,
        doc_title: str | None = None,
        doc_type: str = "NGHI_DINH",
        promulgation_date: str = "2020-01-01",
        effective_date: str = "2020-01-15",
        issuing_authority: str = "Chính phủ",
        signer: str | None = None,
        persist_db: bool = False,
        generate_benchmark: bool = False,
        benchmark_output_path: str | Path | None = None,
    ) -> IngestionResult:
        """Reads text from file and executes ingestion pipeline."""
        path_obj = Path(file_path)
        if not path_obj.exists():
            raise FileNotFoundError(f"Legal document file not found: {file_path}")

        raw_text = path_obj.read_text(encoding="utf-8")
        return await self.ingest_text(
            doc_code=doc_code,
            raw_text=raw_text,
            doc_title=doc_title,
            doc_type=doc_type,
            promulgation_date=promulgation_date,
            effective_date=effective_date,
            issuing_authority=issuing_authority,
            signer=signer,
            persist_db=persist_db,
            generate_benchmark=generate_benchmark,
            benchmark_output_path=benchmark_output_path,
        )

    async def apply_amendment(
        self,
        base_chunks: list[CanonicalFullyQualifiedChunk],
        amending_doc_code: str,
        amending_raw_text: str,
        amending_doc_title: str | None = None,
        amending_effective_date: str = "2022-01-01",
        base_doc_code: str = "100/2019/NĐ-CP",
        persist_db: bool = False,
    ) -> TemporalDiffResult:
        """Applies amending enactment incrementally using AST diffing without destructive drop."""
        result = self.diff_engine.diff_and_apply_amendment(
            base_chunks=base_chunks,
            amending_doc_code=amending_doc_code,
            amending_raw_text=amending_raw_text,
            amending_doc_title=amending_doc_title,
            amending_effective_date=amending_effective_date,
            base_doc_code=base_doc_code,
        )
        if persist_db and self.loader is not None:
            # Persistent DB incremental load can be chained if loader is present
            pass
        return result

