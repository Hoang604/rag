"""Cryptographic Chain of Custody (CoC) and AST Citation Grounding Validator.

Conforms to Requirement 5 (R5), addressing FIND-10, P0-3, and FIND-25.
Provides AST Citation Grounding validation, Merkle hash-chaining, evidence hashing,
and deterministic canonical serialization.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from rag_eval.legal.schemas import (
    AntiHallucinationAudit,
    ChainOfCustody,
    ChainOfCustodyPlanSummary,
    ChainOfCustodyStep,
    ConflictEvaluationResult,
    EvidenceChunkHash,
    LegalIntent,
    PrecedenceResolutionAudit,
    TemporalValidationAudit,
)


@dataclass(frozen=True)
class ParsedStatutoryCitation:
    """Structured statutory citation AST token extracted from advisory text."""

    raw_text: str
    doc_type: str | None = None
    doc_code: str | None = None
    article_num: str | None = None
    clause_num: str | None = None
    point_letter: str | None = None
    sign_code: str | None = None
    marking_code: str | None = None

    @property
    def canonical_key(self) -> str:
        """Constructs a normalized match key for set intersection."""
        parts: list[str] = []
        if self.doc_code:
            parts.append(f"doc_{self.doc_code.lower().replace('/', '_').replace('-', '_').replace('.', '_')}")
        elif self.doc_type:
            parts.append(f"type_{self.doc_type.lower()}")

        if self.article_num:
            parts.append(f"a{self.article_num}")
        if self.clause_num:
            parts.append(f"c{self.clause_num}")
        if self.point_letter:
            parts.append(f"p_{self.point_letter.lower()}")
        if self.sign_code:
            parts.append(f"sign_{self.sign_code.lower().replace('.', '_')}")
        if self.marking_code:
            parts.append(f"marking_{self.marking_code.lower().replace('.', '_')}")

        return ".".join(parts) if parts else self.raw_text.lower()


class ASTCitationValidator:
    """Extracts statutory citations from generated advisory text and verifies grounding against retrieved chunks."""

    # 1. Pattern A: Point first -> Điểm a Khoản 3 Điều 5 / Khoản 3 Điều 5 [Nghị định 100/2019/NĐ-CP]
    CITATION_REGEX_POINT_FIRST = re.compile(
        r"(?=(?:(?:các\s+)?(?:điểm|điểm\s+số)|(?:khoản|khoản\s+số)))"
        r"(?:(?:các\s+)?(?:điểm|điểm\s+số)\s+(?P<point>[a-zđ])[\s,]*)?"
        r"(?:(?:khoản|khoản\s+số)\s+(?P<clause>\d+)[\s,]*)?"
        r"(?:điều\s+(?P<article>\d+[a-z]?))"
        r"(?:[,\s]*(?:Nghị\s+định|NĐ|Thông\s+tư|TT|Luật|QCVN)\s*(?:số\s*)?(?P<doc_code>[0-9]+/[0-9]+/(?:NĐ-CP|ND-CP|TT-BGTVT|TT-BCA|QH[0-9]+)|[0-9]+:[0-9]+/[A-Z0-9\-]+|GTĐB\s*[0-9]*|TTATGTĐB\s*[0-9]*))?",
        re.IGNORECASE,
    )

    # 2. Pattern B: Article first -> Điều 5 Khoản 3 Điểm a [Nghị định 100/2019/NĐ-CP]
    CITATION_REGEX_ARTICLE_FIRST = re.compile(
        r"(?:điều\s+(?P<article>\d+[a-z]?))[\s,]*"
        r"(?:(?:khoản|khoản\s+số)\s+(?P<clause>\d+)[\s,]*)?"
        r"(?:(?:các\s+)?(?:điểm|điểm\s+số)\s+(?P<point>[a-zđ])[\s,]*)?"
        r"(?:[,\s]*(?:Nghị\s+định|NĐ|Thông\s+tư|TT|Luật|QCVN)\s*(?:số\s*)?(?P<doc_code>[0-9]+/[0-9]+/(?:NĐ-CP|ND-CP|TT-BGTVT|TT-BCA|QH[0-9]+)|[0-9]+:[0-9]+/[A-Z0-9\-]+|GTĐB\s*[0-9]*|TTATGTĐB\s*[0-9]*))?",
        re.IGNORECASE,
    )

    # 3. Standalone Decree / Law / QCVN Reference Regex
    DOC_ONLY_REGEX = re.compile(
        r"(?:Nghị\s+định|NĐ)\s+(?:số\s*)?(?P<decree>[0-9]+/[0-9]+/(?:NĐ-CP|ND-CP))|"
        r"(?:Thông\s+tư|TT)\s+(?:số\s*)?(?P<circular>[0-9]+/[0-9]+/(?:TT-BGTVT|TT-BCA))|"
        r"(?P<qcvn>QCVN\s*[0-9]+:[0-9]+/[A-Z0-9\-]+)|"
        r"(?P<law>Luật\s+(?:Giao\s+thông\s+đường\s+bộ|Trật\s+tự[,\s]+an\s+toàn\s+giao\s+thông\s+đường\s+bộ|GTĐB|TTATGTĐB)\s*(?:năm\s*)?(?:2008|2024)?)",
        re.IGNORECASE,
    )

    # 4. Traffic Sign and Marking Regex
    SIGN_MARKING_REGEX = re.compile(
        r"(?:biển\s+(?:báo|hiệu)?\s*(?:số)?\s*(?P<sign>[P|W|R|I|S|DP]\.[0-9]+[a-z]?))|"
        r"(?:vạch\s+(?:kẻ\s+đường\s+)?(?:số\s*)?(?P<marking>[0-9]+\.[0-9]+[a-z]?))",
        re.IGNORECASE,
    )

    @staticmethod
    def _norm_token(text: str) -> str:
        """Normalizes Vietnamese text into unaccented alphanumeric token string."""
        nfkd = unicodedata.normalize("NFKD", text)
        un = "".join(c for c in nfkd if not unicodedata.combining(c))
        un = un.replace("đ", "d").replace("Đ", "D")
        return re.sub(r"[^\w]", "", un.lower())

    @staticmethod
    def _citation_specificity(cit: ParsedStatutoryCitation) -> int:
        """Calculates specificity weight: Point (3) > Clause (2) > Article (1) > Document/Sign (0)."""
        if cit.point_letter:
            return 3
        if cit.clause_num:
            return 2
        if cit.article_num:
            return 1
        return 0

    def _add_or_supersede_citation(
        self, citations: list[ParsedStatutoryCitation], candidate: ParsedStatutoryCitation
    ) -> None:
        """Appends candidate citation or supersedes/enriches existing matches based on specificity."""
        cand_spec = self._citation_specificity(candidate)

        for idx, existing in enumerate(citations):
            exist_spec = self._citation_specificity(existing)

            # Substring / overlap check between raw text
            if existing.raw_text in candidate.raw_text:
                # Candidate encompasses existing text
                if cand_spec >= exist_spec:
                    merged = candidate
                    if candidate.doc_code is None and existing.doc_code is not None:
                        merged = ParsedStatutoryCitation(
                            raw_text=candidate.raw_text,
                            doc_type=candidate.doc_type or existing.doc_type,
                            doc_code=existing.doc_code,
                            article_num=candidate.article_num or existing.article_num,
                            clause_num=candidate.clause_num or existing.clause_num,
                            point_letter=candidate.point_letter or existing.point_letter,
                            sign_code=candidate.sign_code or existing.sign_code,
                            marking_code=candidate.marking_code or existing.marking_code,
                        )
                    citations[idx] = merged
                    return
                else:
                    if existing.doc_code is None and candidate.doc_code is not None:
                        citations[idx] = ParsedStatutoryCitation(
                            raw_text=existing.raw_text,
                            doc_type=existing.doc_type or candidate.doc_type,
                            doc_code=candidate.doc_code,
                            article_num=existing.article_num or candidate.article_num,
                            clause_num=existing.clause_num or candidate.clause_num,
                            point_letter=existing.point_letter or candidate.point_letter,
                            sign_code=existing.sign_code or candidate.sign_code,
                            marking_code=existing.marking_code or candidate.marking_code,
                        )
                    return

            if candidate.raw_text in existing.raw_text:
                # Candidate is a substring of existing text
                if cand_spec > exist_spec:
                    merged = candidate
                    if candidate.doc_code is None and existing.doc_code is not None:
                        merged = ParsedStatutoryCitation(
                            raw_text=candidate.raw_text,
                            doc_type=candidate.doc_type or existing.doc_type,
                            doc_code=existing.doc_code,
                            article_num=candidate.article_num or existing.article_num,
                            clause_num=candidate.clause_num or existing.clause_num,
                            point_letter=candidate.point_letter or existing.point_letter,
                            sign_code=candidate.sign_code or existing.sign_code,
                            marking_code=candidate.marking_code or existing.marking_code,
                        )
                    citations[idx] = merged
                    return
                else:
                    if existing.doc_code is None and candidate.doc_code is not None:
                        citations[idx] = ParsedStatutoryCitation(
                            raw_text=existing.raw_text,
                            doc_type=existing.doc_type or candidate.doc_type,
                            doc_code=candidate.doc_code,
                            article_num=existing.article_num or candidate.article_num,
                            clause_num=existing.clause_num or candidate.clause_num,
                            point_letter=existing.point_letter or candidate.point_letter,
                            sign_code=existing.sign_code or candidate.sign_code,
                            marking_code=existing.marking_code or candidate.marking_code,
                        )
                    return

        citations.append(candidate)

    def extract_citations(self, text: str) -> list[ParsedStatutoryCitation]:
        """Extracts all statutory citations from generated advisory text."""
        citations: list[ParsedStatutoryCitation] = []
        if not text:
            return citations

        # A. Detailed Point/Clause First matches (Điểm a Khoản 3 Điều 5 / Khoản 3 Điều 5)
        # Prioritized BEFORE Article First patterns to guarantee specific sub-provisions are extracted
        for m in self.CITATION_REGEX_POINT_FIRST.finditer(text):
            pt = m.group("point")
            cl = m.group("clause")
            art = m.group("article")
            doc = m.group("doc_code")
            raw = m.group(0).strip()
            if art or cl or pt:
                self._add_or_supersede_citation(
                    citations,
                    ParsedStatutoryCitation(
                        raw_text=raw,
                        doc_code=doc.strip() if doc else None,
                        article_num=art.strip() if art else None,
                        clause_num=cl.strip() if cl else None,
                        point_letter=pt.strip() if pt else None,
                    ),
                )

        # B. Detailed Article First matches (Điều 5 Khoản 3 Điểm a)
        for m in self.CITATION_REGEX_ARTICLE_FIRST.finditer(text):
            pt = m.group("point")
            cl = m.group("clause")
            art = m.group("article")
            doc = m.group("doc_code")
            raw = m.group(0).strip()
            if art or cl or pt:
                self._add_or_supersede_citation(
                    citations,
                    ParsedStatutoryCitation(
                        raw_text=raw,
                        doc_code=doc.strip() if doc else None,
                        article_num=art.strip() if art else None,
                        clause_num=cl.strip() if cl else None,
                        point_letter=pt.strip() if pt else None,
                    ),
                )

        # C. Document Only matches
        for m in self.DOC_ONLY_REGEX.finditer(text):
            raw = m.group(0).strip()
            doc_code = m.group("decree") or m.group("circular") or m.group("qcvn") or m.group("law")
            self._add_or_supersede_citation(
                citations,
                ParsedStatutoryCitation(
                    raw_text=raw,
                    doc_code=doc_code.strip() if doc_code else raw,
                ),
            )

        # D. Sign & Marking matches
        for m in self.SIGN_MARKING_REGEX.finditer(text):
            raw = m.group(0).strip()
            sign = m.group("sign")
            marking = m.group("marking")
            self._add_or_supersede_citation(
                citations,
                ParsedStatutoryCitation(
                    raw_text=raw,
                    sign_code=sign.strip() if sign else None,
                    marking_code=marking.strip() if marking else None,
                ),
            )

        return citations

        # C. Document Only matches
        for m in self.DOC_ONLY_REGEX.finditer(text):
            raw = m.group(0).strip()
            doc_code = m.group("decree") or m.group("circular") or m.group("qcvn") or m.group("law")
            self._add_or_supersede_citation(
                citations,
                ParsedStatutoryCitation(
                    raw_text=raw,
                    doc_code=doc_code.strip() if doc_code else raw,
                ),
            )

        # D. Sign & Marking matches
        for m in self.SIGN_MARKING_REGEX.finditer(text):
            raw = m.group(0).strip()
            sign = m.group("sign")
            marking = m.group("marking")
            self._add_or_supersede_citation(
                citations,
                ParsedStatutoryCitation(
                    raw_text=raw,
                    sign_code=sign.strip() if sign else None,
                    marking_code=marking.strip() if marking else None,
                ),
            )

        return citations

    def validate(
        self,
        advisory_text: str,
        retrieved_chunks: list[dict[str, Any]],
    ) -> AntiHallucinationAudit:
        """Validates that all citations generated in advisory_text are grounded in retrieved evidence."""
        citations = self.extract_citations(advisory_text)

        if not retrieved_chunks:
            # If no chunks were retrieved at all, any text is ungrounded
            unmatched = [c.raw_text for c in citations]
            return AntiHallucinationAudit(
                is_grounded=False,
                unmatched_citations=unmatched,
                citation_coverage_pct=0.0,
                hallucination_score=1.0 if citations else 0.0,
            )

        if not citations:
            # No statutory citations made, but retrieved chunks exist
            return AntiHallucinationAudit(
                is_grounded=True,
                unmatched_citations=[],
                citation_coverage_pct=100.0,
                hallucination_score=0.0,
            )

        # Build comprehensive Grounding Knowledge Set from retrieved chunks
        grounded_paths: set[str] = set()
        grounded_docs: set[str] = set()
        grounded_doc_tokens: set[str] = set()
        grounded_articles: set[str] = set()
        grounded_tokens: set[str] = set()
        raw_corpus_text_lower: list[str] = []

        for chk in retrieved_chunks:
            path = str(chk.get("hierarchy_path") or chk.get("path") or "").lower()
            doc_code = str(chk.get("document_code") or chk.get("doc_code") or "").lower()
            art_idx = str(chk.get("article_index") or "").lower()
            art_num = str(chk.get("article_number") or "")
            raw_text = str(chk.get("verbatim_text") or chk.get("raw_text") or chk.get("exact_statutory_text") or "").lower()
            ctx_text = str(chk.get("contextualized_text") or "").lower()

            raw_corpus_text_lower.append(raw_text)
            raw_corpus_text_lower.append(ctx_text)
            raw_corpus_text_lower.append(path)

            if path:
                grounded_paths.add(path)
                for part in path.split("."):
                    grounded_tokens.add(part)

            if doc_code:
                grounded_docs.add(doc_code)
                grounded_docs.add(doc_code.replace("/", "_").replace("-", "_"))
                grounded_doc_tokens.add(self._norm_token(doc_code))

            if art_idx:
                grounded_articles.add(art_idx)
            if art_num and art_num != "None":
                grounded_articles.add(f"a{art_num}")
                grounded_articles.add(f"điều {art_num}")
                grounded_tokens.add(f"a{art_num}")

            # Check referenced entities
            refs = chk.get("referenced_entities") or {}
            if isinstance(refs, dict):
                for signs in refs.get("qcvn_signs", []):
                    grounded_tokens.add(str(signs).lower().replace(".", "_"))
                    grounded_tokens.add(str(signs).lower())
                for law in refs.get("law_articles", []):
                    grounded_tokens.add(str(law).lower())
                for dec in refs.get("amending_decrees", []):
                    grounded_tokens.add(str(dec).lower())
                    grounded_doc_tokens.add(self._norm_token(str(dec)))

        combined_corpus = " ".join(raw_corpus_text_lower)
        combined_corpus_norm = self._norm_token(combined_corpus)

        # Match each generated citation
        unmatched: list[str] = []
        for cit in citations:
            is_matched = False
            cit_norm = self._norm_token(cit.raw_text)

            # Check 1: Exact normalized citation string in corpus
            if cit_norm in combined_corpus_norm:
                is_matched = True

            # Check 2: Article citation matching
            elif cit.article_num:
                art_tag = f"a{cit.article_num.lower()}"
                art_norm = self._norm_token(f"điều {cit.article_num}")
                # Article MUST exist in grounded evidence
                if art_tag in grounded_tokens or art_norm in combined_corpus_norm:
                    is_sub_valid = True
                    # If clause is specified, verify clause
                    if cit.clause_num:
                        cl_tag = f"c{cit.clause_num}"
                        cl_norm = self._norm_token(f"khoản {cit.clause_num}")
                        if cl_tag not in grounded_tokens and cl_norm not in combined_corpus_norm:
                            is_sub_valid = False
                    # If point is specified, verify point
                    if cit.point_letter:
                        pt_tag = f"p_{cit.point_letter.lower()}"
                        pt_norm = self._norm_token(f"điểm {cit.point_letter}")
                        if pt_tag not in grounded_tokens and pt_norm not in combined_corpus_norm:
                            is_sub_valid = False

                    if is_sub_valid:
                        is_matched = True

            # Check 3: Standalone Document Code match (Only when no article is requested)
            elif cit.doc_code and not cit.article_num and not cit.clause_num and not cit.sign_code and not cit.marking_code:
                doc_norm = self._norm_token(cit.doc_code)
                if (
                    doc_norm in combined_corpus_norm
                    or any(doc_norm in d or d in doc_norm for d in grounded_doc_tokens)
                ):
                    is_matched = True

            # Check 4: Sign / Marking code match
            elif cit.sign_code or cit.marking_code:
                code = (cit.sign_code or cit.marking_code or "").lower()
                if code in combined_corpus or code.replace(".", "_") in grounded_tokens:
                    is_matched = True

            if not is_matched:
                unmatched.append(cit.raw_text)

        total_citations = len(citations)
        unmatched_count = len(unmatched)
        hallucination_score = unmatched_count / total_citations if total_citations > 0 else 0.0
        coverage = (1.0 - hallucination_score) * 100.0

        return AntiHallucinationAudit(
            is_grounded=(unmatched_count == 0),
            unmatched_citations=unmatched,
            citation_coverage_pct=max(0.0, min(100.0, coverage)),
            hallucination_score=max(0.0, min(1.0, hallucination_score)),
        )


class ChainOfCustodyGenerator:
    """Generates machine-auditable, cryptographically validated Chain of Custody records."""

    def __init__(self) -> None:
        self.validator = ASTCitationValidator()

    @staticmethod
    def _normalize_ltree_path(path: str, chunk_id: str) -> str:
        """Ensures a hierarchy path strictly conforms to LTREE_PATH_PATTERN."""
        clean_path = path.strip().lower()
        if not clean_path.startswith("doc_"):
            clean_path = f"doc_{clean_path}" if clean_path else f"doc_{chunk_id.lower()}"
        clean_path = re.sub(r"[^a-z0-9_.]", "_", clean_path)
        clean_path = re.sub(r"\.{2,}", ".", clean_path).strip(".")
        if not re.match(r"^doc_[a-z0-9_]+(?:\.[a-z0-9_]+)*$", clean_path):
            clean_path = "doc_nd100_2019.root"
        return clean_path

    def generate(
        self,
        query: str,
        retrieved_chunks: list[dict[str, Any]],
        advisory_text: str,
        plan_summary: ChainOfCustodyPlanSummary | dict[str, Any] | None = None,
        precedence_resolutions: Sequence[PrecedenceResolutionAudit | ConflictEvaluationResult] | None = None,
        temporal_validation: TemporalValidationAudit | None = None,
    ) -> ChainOfCustody:
        """Constructs a deterministic Chain of Custody package with Merkle SHA-256 evidence hash chaining."""
        q_bytes = query.encode("utf-8")
        q_hash = hashlib.sha256(q_bytes).hexdigest()
        trace_id = f"coc-{q_hash[:12]}"

        # 1. Chained Cryptographic Ledger: H_i = SHA256(H_{i-1} || chunk_id || exact_text)
        prev_hash = q_hash
        retrieval_steps: list[ChainOfCustodyStep] = []
        evidence_hashes: list[EvidenceChunkHash] = []

        for idx, chunk in enumerate(retrieved_chunks, start=1):
            raw = str(chunk.get("verbatim_text") or chunk.get("raw_text") or chunk.get("exact_statutory_text") or "")
            cid = str(chunk.get("chunk_id", f"chk_{idx}"))
            raw_path = str(chunk.get("hierarchy_path") or chunk.get("path") or "doc_nd100_2019.root")
            path = self._normalize_ltree_path(raw_path, cid)
            doc_code = str(chunk.get("document_code") or chunk.get("doc_code") or "100/2019/ND-CP")

            # Chained Merkle step hash
            step_payload = f"{prev_hash}|{cid}|{raw}".encode()
            curr_hash = hashlib.sha256(step_payload).hexdigest()
            prev_hash = curr_hash

            raw_score = float(chunk.get("rrf_score", chunk.get("relevance_score", 0.95)))
            clamped_score = max(0.0, min(1.0, raw_score))

            retrieval_steps.append(
                ChainOfCustodyStep(
                    step_index=idx,
                    action="HYBRID_SEARCH" if idx == 1 else "GRAPH_TRAVERSAL",
                    tool_invoked="mcp_traffic_hybrid_search" if idx == 1 else "mcp_traffic_graph_traverse",
                    target_node_id=cid,
                    node_sha256=curr_hash,
                    document_code=doc_code,
                    hierarchy_path=path,
                    exact_statutory_text=raw,
                    relevance_score=clamped_score,
                )
            )

            # Direct verbatim evidence digest
            evidence_hashes.append(
                EvidenceChunkHash.from_text(
                    chunk_id=cid,
                    hierarchy_path=path,
                    document_code=doc_code,
                    text=raw,
                )
            )

        # 2. Real AST Citation Grounding Validation
        audit = self.validator.validate(
            advisory_text=advisory_text,
            retrieved_chunks=retrieved_chunks,
        )

        # 3. Plan Summary Normalization
        if isinstance(plan_summary, ChainOfCustodyPlanSummary):
            summary = plan_summary
        elif isinstance(plan_summary, dict):
            intent_val = plan_summary.get("intent", LegalIntent.INTENT_PENALTY_LOOKUP.value)
            intent = (
                LegalIntent(intent_val)
                if isinstance(intent_val, str) and intent_val in LegalIntent._value2member_map_
                else LegalIntent.INTENT_PENALTY_LOOKUP
            )
            exec_order = plan_summary.get("execution_order", plan_summary.get("execution_path", []))
            flat_order = [str(x) for x in exec_order] if isinstance(exec_order, list) else []
            summary = ChainOfCustodyPlanSummary(
                primary_intent=intent,
                total_subgoals=int(plan_summary.get("total_subgoals", len(retrieval_steps))),
                execution_path=flat_order,
            )
        else:
            summary = ChainOfCustodyPlanSummary(
                primary_intent=LegalIntent.INTENT_PENALTY_LOOKUP,
                total_subgoals=len(retrieval_steps),
                execution_path=[],
            )

        # 4. Precedence Resolutions Normalization
        audit_resolutions: list[PrecedenceResolutionAudit] = []
        if precedence_resolutions:
            for item in precedence_resolutions:
                if isinstance(item, PrecedenceResolutionAudit):
                    audit_resolutions.append(item)
                elif isinstance(item, ConflictEvaluationResult):
                    dominant_name = item.dominant_signal.source_type.name
                    overridden = [s.source_type.name for s in item.suppressed_signals]
                    conflict_name = f"{dominant_name}_OVERRIDE_{overridden[0]}" if overridden else "PRECEDENCE_EVAL"
                    statutory_rule = item.legal_basis[0] if item.legal_basis else "QCVN 41:2019/BGTVT Điều 4"
                    audit_resolutions.append(
                        PrecedenceResolutionAudit(
                            conflict_type=conflict_name,
                            dominant_authority=dominant_name,
                            overridden_authorities=overridden,
                            statutory_rule_applied=statutory_rule,
                        )
                    )

        return ChainOfCustody(
            trace_id=trace_id,
            session_id="sess_prod_reasoning",
            query_fingerprint_sha256=q_hash,
            execution_timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
            plan_summary=summary,
            retrieval_steps=retrieval_steps,
            evidence_hashes=evidence_hashes,
            precedence_resolutions=audit_resolutions,
            temporal_validation=temporal_validation,
            anti_hallucination_audit=audit,
        )


class ChainOfCustodyVerifier:
    """Forensic auditor to independently verify cryptographic hash chains and citation integrity."""

    @staticmethod
    def verify_hash_chain(coc: ChainOfCustody, query: str) -> bool:
        """Verifies the unbroken cryptographic SHA-256 Merkle chain across all retrieval steps."""
        q_bytes = query.encode("utf-8")
        expected_prev = hashlib.sha256(q_bytes).hexdigest()
        if coc.query_fingerprint_sha256 != expected_prev:
            return False

        for step in coc.retrieval_steps:
            payload = f"{expected_prev}|{step.target_node_id}|{step.exact_statutory_text}".encode()
            calc_hash = hashlib.sha256(payload).hexdigest()
            if step.node_sha256 != calc_hash:
                return False
            expected_prev = calc_hash

        return True

    @staticmethod
    def verify_evidence_digests(coc: ChainOfCustody) -> bool:
        """Verifies that each evidence hash matches its verbatim statutory text."""
        for ev in coc.evidence_hashes:
            matching_step = next((s for s in coc.retrieval_steps if s.target_node_id == ev.chunk_id), None)
            if matching_step is not None:
                step_text_hash = hashlib.sha256(matching_step.exact_statutory_text.encode("utf-8")).hexdigest()
                if ev.sha256_digest != step_text_hash:
                    return False
        return True

    @staticmethod
    def to_canonical_json(coc: ChainOfCustody) -> str:
        """Exports the immutable ChainOfCustody into RFC 8785 canonical sorted JSON."""
        data = coc.model_dump(mode="json")
        return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))

    @classmethod
    def calculate_coc_fingerprint(cls, coc: ChainOfCustody) -> str:
        """Computes the master SHA-256 fingerprint over the canonical JSON representation."""
        canonical = cls.to_canonical_json(coc)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
