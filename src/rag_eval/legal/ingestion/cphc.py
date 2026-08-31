"""Context-Preserving Hierarchical Chunking (CPHC) Engine.

Transforms statutory AST nodes into Canonical Fully Qualified Chunks (CFQC) and LegalNormExtraction
models, guaranteeing that all atomic sub-points inherit parent Article titles and Clause lead
sentences with verbatim text preservation.
"""

from __future__ import annotations

import re
import uuid

from rag_eval.legal.ingestion.grammar import VietnameseLegalGrammar
from rag_eval.legal.ingestion.parser import ASTNode, sanitize_ltree_label
from rag_eval.legal.schemas import (
    AdditionalSanctions,
    CanonicalFullyQualifiedChunk,
    ExceptionMetadata,
    FineBounds,
    LegalNormExtraction,
    NormRole,
    ReferencedEntity,
    canonical_doc_slug,
)


def synthesize_cphc_prefix(
    doc_code: str,
    doc_title: str,
    chapter_title: str | None,
    article_num: int,
    article_title: str,
    clause_num: int | None,
    clause_lead: str | None,
    point_letter: str | None,
    point_body: str,
    ast_node: ASTNode | None = None,
    hierarchy_path: str | None = None,
    custom_path: str | None = None,
    clause_tail: str | None = None,
    additional_sanctions_summary: str | None = None,
) -> tuple[str, str]:
    """Synthesizes deterministic ltree path and human/LLM contextualized text."""
    if ast_node is not None:
        ltree_path = ast_node.full_path
    elif hierarchy_path is not None or custom_path is not None:
        ltree_path = hierarchy_path or custom_path or ""
    else:
        root_slug = canonical_doc_slug(doc_code)
        path_parts: list[str] = [root_slug]
        if article_num:
            path_parts.append(f"a{article_num}")
        if clause_num:
            path_parts.append(f"c{clause_num}")
        if point_letter:
            path_parts.append(f"p_{sanitize_ltree_label(point_letter)}")
        ltree_path = ".".join(path_parts)

    header_lines = [
        f"[VĂN BẢN]: {doc_title} (Số hiệu: {doc_code})",
    ]
    if chapter_title:
        header_lines.append(f"[CHƯƠNG]: {chapter_title}")

    if ast_node is not None and ast_node.level in ("SIGN_SPEC", "MARKING_SPEC"):
        if ast_node.lead_sentence:
            header_lines.append(ast_node.lead_sentence)
    else:
        header_lines.append(f"[ĐIỀU {article_num}]: {article_title}")

        if clause_num and clause_lead:
            clean_lead = re.sub(r"^\d+\.\s*", "", clause_lead.strip())
            header_lines.append(f"[KHOẢN {clause_num} - LỜI DẪN]: {clean_lead}")

    prefix = "\n".join(header_lines)

    body_line = (
        f"[ĐIỂM {point_letter}]: {point_body.strip()}"
        if point_letter
        else point_body.strip()
    )
    components = [prefix, body_line]
    if clause_tail:
        components.append(clause_tail.strip())
    if additional_sanctions_summary:
        components.append(
            f"[CHẾ TÀI BỔ SUNG & TRỪ ĐIỂM]: {additional_sanctions_summary.strip()}"
        )

    contextualized_text = "\n".join(components)
    return ltree_path, contextualized_text


class CPHCEngine:
    """Context-Preserving Hierarchical Chunking Engine (Pure AST)."""

    def __init__(
        self, grammar: type[VietnameseLegalGrammar] = VietnameseLegalGrammar
    ) -> None:
        self.grammar = grammar

    def process_ast(
        self,
        root: ASTNode,
        document_id: str | None = None,
        effective_date: str | None = None,
        expiration_date: str | None = None,
    ) -> tuple[list[CanonicalFullyQualifiedChunk], list[LegalNormExtraction]]:
        """Processes an AST hierarchy into CanonicalFullyQualifiedChunks and LegalNormExtractions."""
        doc_id = document_id or str(
            uuid.uuid5(uuid.NAMESPACE_DNS, root.index_label)
        )
        doc_code = root.index_label
        doc_title = root.title

        chunks: list[CanonicalFullyQualifiedChunk] = []
        extractions: list[LegalNormExtraction] = []

        self._traverse_and_chunk(
            node=root,
            doc_id=doc_id,
            doc_code=doc_code,
            doc_title=doc_title,
            current_chapter=None,
            current_article=None,
            current_clause=None,
            effective_date=effective_date,
            expiration_date=expiration_date,
            out_chunks=chunks,
            out_extractions=extractions,
        )

        return chunks, extractions

    def _traverse_and_chunk(
        self,
        node: ASTNode,
        doc_id: str,
        doc_code: str,
        doc_title: str,
        current_chapter: ASTNode | None,
        current_article: ASTNode | None,
        current_clause: ASTNode | None,
        effective_date: str | None,
        expiration_date: str | None,
        out_chunks: list[CanonicalFullyQualifiedChunk],
        out_extractions: list[LegalNormExtraction],
    ) -> None:
        """Recursive traversal generating CFQC chunks for atomic nodes."""
        if node.level == "CHAPTER":
            current_chapter = node
        elif node.level == "ARTICLE":
            current_article = node
        elif node.level == "CLAUSE":
            current_clause = node

        is_point = node.level == "POINT"
        is_standalone_clause = node.level == "CLAUSE" and not node.children
        is_sign_spec = node.level in ("SIGN_SPEC", "MARKING_SPEC")

        if is_point or is_standalone_clause or is_sign_spec:
            art_num = 1
            if current_article:
                art_raw = current_article.metadata.get("article_number", 1)
                art_num = int(art_raw or 1) if isinstance(art_raw, (int, str)) and str(art_raw).isdigit() else 1

            art_title = current_article.title if current_article else doc_title

            cl_num: int | None = None
            if current_clause:
                cl_raw = current_clause.metadata.get("clause_number")
                if cl_raw is not None and isinstance(cl_raw, (int, str)) and str(cl_raw).isdigit():
                    cl_num = int(cl_raw)

            cl_lead = current_clause.lead_sentence if current_clause else None
            pt_letter: str | None = None
            if is_point:
                pt_raw = node.metadata.get("point_letter")
                if pt_raw is not None:
                    pt_letter = str(pt_raw)

            clause_tail_text: str | None = None
            if current_clause and "clause_tail" in current_clause.metadata:
                clause_tail_text = str(current_clause.metadata["clause_tail"])

            ltree_path, contextualized_text = synthesize_cphc_prefix(
                doc_code=doc_code,
                doc_title=doc_title,
                chapter_title=current_chapter.title
                if current_chapter
                else None,
                article_num=art_num,
                article_title=art_title,
                clause_num=cl_num,
                clause_lead=cl_lead,
                point_letter=pt_letter,
                point_body=node.raw_text,
                ast_node=node,
                clause_tail=clause_tail_text,
            )

            exceptions = self._extract_exceptions(node.raw_text)
            refs = self._extract_references(node.raw_text)

            chunk_id = f"chk_{uuid.uuid5(uuid.NAMESPACE_DNS, ltree_path)}"
            norm_role = NormRole.HYPOTHESIS_CONDITION

            cfqc = CanonicalFullyQualifiedChunk(
                chunk_id=chunk_id,
                document_id=doc_id,
                document_code=doc_code,
                hierarchy_path=ltree_path,
                article_number=art_num,
                article_index=f"Điều {art_num}"
                if current_article
                else art_title,
                clause_number=cl_num,
                point_letter=pt_letter,
                synthesized_prefix=node.lead_sentence
                or f"[{node.level}]: {node.title}"
                if is_sign_spec
                else (
                    f"[ĐIỀU {art_num}]: {art_title}\n[KHOẢN {cl_num}]: {cl_lead or ''}"
                    + (
                        f"\n{clause_tail_text}"
                        if clause_tail_text
                        else ""
                    )
                ),
                verbatim_text=node.raw_text,
                contextualized_text=contextualized_text,
                norm_role=norm_role,
                exceptions_and_overrides=exceptions,
                referenced_entities=refs,
                effective_date=effective_date,
                expiry_date=expiration_date,
                is_active=True,
            )
            out_chunks.append(cfqc)

            doc_type = (
                str(node.metadata.get("document_type"))
                if node.metadata.get("document_type")
                else (
                    str(current_article.metadata.get("document_type"))
                    if current_article and current_article.metadata.get("document_type")
                    else (
                        str(current_chapter.metadata.get("document_type"))
                        if current_chapter and current_chapter.metadata.get("document_type")
                        else "LUAT"
                    )
                )
            )
            norm_ext = LegalNormExtraction(
                chunk_id=chunk_id,
                hierarchy_path=ltree_path,
                document_code=doc_code,
                document_type=doc_type,
                article_number=art_num,
                article_index=f"Điều {art_num}"
                if current_article
                else art_title,
                clause_number=cl_num,
                point_letter=pt_letter,
                norm_role=norm_role,
                behavior_summary=node.raw_text[:200].strip(),
                fine_bounds=FineBounds(),
                additional_sanctions=AdditionalSanctions(),
                remedial_measures=[],
                exceptions_and_overrides=exceptions,
                referenced_entities=refs,
                contextualized_text=contextualized_text,
                verbatim_text=node.raw_text,
            )
            out_extractions.append(norm_ext)

        for child in node.children:
            self._traverse_and_chunk(
                node=child,
                doc_id=doc_id,
                doc_code=doc_code,
                doc_title=doc_title,
                current_chapter=current_chapter,
                current_article=current_article,
                current_clause=current_clause,
                effective_date=effective_date,
                expiration_date=expiration_date,
                out_chunks=out_chunks,
                out_extractions=out_extractions,
            )

    def _extract_exceptions(self, text: str) -> ExceptionMetadata:
        """Extracts statutory exception metadata."""
        match = self.grammar.EXCEPTION_REGEX.search(text)
        if match:
            clause_text = (
                match.group("clause_text").strip() or match.group(0).strip()
            )
            return ExceptionMetadata(
                has_exception=True,
                exception_type="STATUTORY_EXCEPTION",
                exception_clause_text=clause_text,
                overridden_by=[],
            )
        return ExceptionMetadata(has_exception=False)

    def _extract_references(self, text: str) -> ReferencedEntity:
        """Extracts referenced law articles, signs, markings, and amending decrees."""
        laws: list[str] = []
        signs: list[str] = []
        markings: list[str] = []
        amends: list[str] = []

        for m in self.grammar.ARTICLE_REF_REGEX.finditer(text):
            art = m.group("article")
            cl = m.group("clause")
            pt = m.group("point")
            doc = m.group("doc_ref")
            ref_str = f"Điều {art}"
            if cl:
                ref_str = f"Khoản {cl} {ref_str}"
            if pt:
                ref_str = f"Điểm {pt} {ref_str}"
            if doc:
                ref_str = f"{ref_str} ({doc})"
            matched_slice = text[
                max(0, m.start() - 25) : min(len(text), m.end() + 30)
            ].lower()
            if doc or "luật" in matched_slice:
                laws.append(ref_str)

        for m in self.grammar.SIGN_REF_REGEX.finditer(text):
            if m.group("sign_code"):
                signs.append(m.group("sign_code").upper())
            elif m.group("sign_name"):
                signs.append(m.group("sign_name"))

        for m in self.grammar.MARKING_REF_REGEX.finditer(text):
            markings.append(m.group("marking_code"))

        for m in self.grammar.DECREE_AMENDMENT_REGEX.finditer(text):
            amends.append(m.group("doc_code"))

        return ReferencedEntity(
            law_articles=laws,
            qcvn_signs=signs,
            qcvn_markings=markings,
            amending_decrees=amends,
        )
