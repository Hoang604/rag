# Symmetrical Ingestion & Chunking Strategy Architecture
## Context-Preserving Hierarchical Chunking (CPHC), Multi-Stage Ingestion Agents, Pydantic Extraction Rubrics, Automated Graph Linkers & Synthetic Benchmark Generation

**Document Version:** 1.0.0  
**Author:** Ingestion & Chunking Strategy Technical Author (`worker_doc04_ingestion`)  
**Target Delivery Path:** `docs/04_ingestion_and_chunking_strategy.md`  
**Date:** 2026-08-29  
**Status:** Complete Production Specification

---

## Table of Contents
1. [Ingestion Philosophy & Symmetrical Coupling](#1-ingestion-philosophy--symmetrical-coupling)
   - 1.1. [Architectural Thesis: Ingestion-Retrieval Duality](#11-architectural-thesis-ingestion-retrieval-duality)
   - 1.2. [Failure Modes of Naive Chunking on Vietnamese Legislation](#12-failure-modes-of-naive-chunking-on-vietnamese-legislation)
   - 1.3. [End-to-End Symmetrical Ingestion-Retrieval Architecture](#13-end-to-end-symmetrical-ingestion-retrieval-architecture)
2. [Context-Preserving Hierarchical Chunking (CPHC) Algorithm](#2-context-preserving-hierarchical-chunking-cphc-algorithm)
   - 2.1. [Vietnamese Statutory Syntactic Hierarchy (AST Modeling)](#21-vietnamese-statutory-syntactic-hierarchy-ast-modeling)
   - 2.2. [Deterministic Regular Expression Grammar](#22-deterministic-regular-expression-grammar)
   - 2.3. [Prefix Synthesis & Lead Sentence Inheritance Algorithm](#23-prefix-synthesis--lead-sentence-inheritance-algorithm)
   - 2.4. [Canonical Fully Qualified Chunk (CFQC) Structure](#24-canonical-fully-qualified-chunk-cfqc-structure)
   - 2.5. [Granularity & Chunk Type Taxonomy](#25-granularity--chunk-type-taxonomy)
3. [Multi-Stage Ingestion Agent Workflows & System Prompts](#3-multi-stage-ingestion-agent-workflows--system-prompts)
   - 3.1. [4-Stage Autonomous Pipeline Architecture](#31-4-stage-autonomous-pipeline-architecture)
   - 3.2. [Stage 1: Document Structure & AST Parser Agent](#32-stage-1-document-structure--ast-parser-agent)
   - 3.3. [Stage 2: Semantic Enricher & Pydantic Extraction Agent](#33-stage-2-semantic-enricher--pydantic-extraction-agent)
   - 3.4. [Stage 3: Cross-Reference Graph Linker Agent](#34-stage-3-cross-reference-graph-linker-agent)
   - 3.5. [Stage 4: Validation & Quality Control Agent](#35-stage-4-validation--quality-control-agent)
4. [Structured Pydantic Extraction Rubrics](#4-structured-pydantic-extraction-rubrics)
   - 4.1. [Core Domain Schemas & Controlled Vocabularies](#41-core-domain-schemas--controlled-vocabularies)
   - 4.2. [Fine Bounds & Administrative Sanction Package Schema](#42-fine-bounds--administrative-sanction-package-schema)
   - 4.3. [Demerit Points & License Revocation Schema (2024-2025 Mandates)](#43-demerit-points--license-revocation-schema-2024-2025-mandates)
   - 4.4. [Exceptions & Scope Overrides Schema](#44-exceptions--scope-overrides-schema)
   - 4.5. [Master `LegalNormExtraction` Pydantic v2 Implementation](#45-master-legalnormextraction-pydantic-v2-implementation)
5. [Automated Relationship Linking & Knowledge Graph Construction](#5-automated-relationship-linking--knowledge-graph-construction)
   - 5.1. [Legal Graph Edge Topology](#51-legal-graph-edge-topology)
   - 5.2. [Deterministic Regex Linker Engine](#52-deterministic-regex-linker-engine)
   - 5.3. [LLM-Assisted Relative & Anaphoric Reference Resolution](#53-llm-assisted-relative--anaphoric-reference-resolution)
   - 5.4. [Graph Construction & Idempotent Database Loading](#54-graph-construction--idempotent-database-loading)
6. [Synthetic Multi-Hop Benchmark Generation](#6-synthetic-multi-hop-benchmark-generation)
   - 6.1. [Closed-Loop Evaluation Philosophy](#61-closed-loop-evaluation-philosophy)
   - 6.2. [3-Tier Synthetic Benchmark Taxonomy](#62-3-tier-synthetic-benchmark-taxonomy)
   - 6.3. [Benchmark Generation Algorithm & Automated Gold Paths](#63-benchmark-generation-algorithm--automated-gold-paths)
   - 6.4. [Test Set Data Format & Verification Rubrics](#64-test-set-data-format--verification-rubrics)
7. [Operational Ingestion Pipeline & Traceability Matrix](#7-operational-ingestion-pipeline--traceability-matrix)
   - 7.1. [CLI Ingestion Workflow & Pipeline Orchestration](#71-cli-ingestion-workflow--pipeline-orchestration)
   - 7.2. [Temporal Diffing & Incremental Update Engine](#72-temporal-diffing--incremental-update-engine)
   - 7.3. [Comprehensive Ingestion-Retrieval Traceability Matrix](#73-comprehensive-ingestion-retrieval-traceability-matrix)

---

## 1. Ingestion Philosophy & Symmetrical Coupling

### 1.1. Architectural Thesis: Ingestion-Retrieval Duality

In state-of-the-art Agentic Retrieval-Augmented Generation (RAG) systems, **ingestion and retrieval are not independent pipelines**; they are mathematical and architectural duals of one another. The retrieval engine cannot infer semantic relationships, filter by operational metadata, traverse normative triads, or execute priority override algebra unless those structural dimensions were explicitly parsed, standardized, enriched, and materialized during the ingestion phase.

```
%%{init: {"flowchart": {"defaultRenderer": "elk"}}}%%
flowchart LR
    subgraph INGESTION["Symmetrical Ingestion (Encoding Phase)"]
        Raw["Raw Legal Text<br/>(Luật, NĐ, QCVN)"] --> AST["AST Syntactic Parsing<br/>(Hierarchical Units)"]
        AST --> Enriched["Context Synthesis &<br/>Pydantic Extraction"]
        Enriched --> Graph["Graph Edge Linking<br/>(Triad & Overrides)"]
        Graph --> DB[("PostgreSQL 16<br/>pgvector + JSONB + ltree")]
    end

    subgraph RETRIEVAL["Symmetrical Retrieval (Decoding Phase)"]
        Query["User Query"] --> Decomp["Intent Decomposition<br/>& Query Planning"]
        Decomp --> MCP["MCP Tool Suite<br/>(Hybrid + Graph Search)"]
        DB <--> MCP
        MCP --> Reason["Multi-Hop Traversal<br/>& Override Engine"]
        Reason --> Answer["Verifiable Legal Answer<br/>+ Gold Chain of Custody"]
    end
```

Every dimension extracted during ingestion directly mirrors a retrieval capability:
1. **Syntactic Lineage (`ltree`)** $\iff$ Sub-millisecond hierarchical expansion and sibling aggregation (`mcp_traffic_hierarchical_navigate`).
2. **Dense Vector Embeddings (`vector(1536)`)** $\iff$ Paraphrase-invariant semantic search over fully qualified units (`mcp_traffic_hybrid_search`).
3. **Structured Entity Arrays (`JSONB`)** $\iff$ Deterministic metadata pre-filtering on vehicle classes and violation categories, completely preventing cross-vehicle hallucination.
4. **Relational Edges (`legal_graph_edges`)** $\iff$ Deterministic beam-search traversal across the decoupled normative triad: Law $\rightarrow$ Decree $\rightarrow$ QCVN (`mcp_traffic_graph_traverse`).
5. **Exception & Priority Flags** $\iff$ Execution of statutory precedence rules (Police $>$ Lights $>$ Signs $>$ Markings; Emergency privileges; "Trừ trường hợp...") via `mcp_traffic_scope_override_detect`.
6. **Synthetic QA Generation** $\iff$ Ingestion-time generation of multi-hop benchmarks with gold citation paths, providing automated regression evaluation.

---

### 1.2. Failure Modes of Naive Chunking on Vietnamese Legislation

Standard RAG architectures rely on character-based, recursive character, or fixed-token sliding-window chunking (e.g., 512 tokens with 50-token overlap). When applied to Vietnamese traffic legislation (*Luật Giao thông đường bộ 2008*, *Luật Trật tự, an toàn giao thông đường bộ 2024*, *Nghị định 100/2019/NĐ-CP*, *Nghị định 123/2021/NĐ-CP*, *Nghị định 168/2024/NĐ-CP*, and *QCVN 41:2019/BGTVT*), naive chunking induces catastrophic retrieval failure modes:

| Failure Mode | Root Cause in Vietnamese Legal Drafting | Observable Consequence in Retrieval |
|---|---|---|
| **Dangling Sub-points ("Điểm mồ côi")** | Administrative decrees declare the vehicle category in the **Điều (Article)** title and the fine bracket in the **Khoản (Clause)** lead sentence. The **Điểm (Sub-point)** contains only the behavior (e.g., *"a) Không chấp hành hiệu lệnh của đèn tín hiệu giao thông"*). | An isolated chunk of "Điểm a" has zero mention of "ô tô" or "800.000đ - 1.000.000đ". Semantic vector search matches the text to motorcycle queries, causing wrong penalty calculations. |
| **Normative Triad Fragmentation** | Vietnamese legal norms are physically decoupled across instruments: Definition/Duty in **Luật**, Sanction/Fine in **Nghị định**, and Physical Signs/Markings in **QCVN**. | A query about Sign P.102 ("Biển cấm đi ngược chiều") retrieves only QCVN definitions; the retriever cannot locate the fine in Decree 100 or behavioral obligation in Law without graph edges. |
| **Separated Additional Sanctions** | Additional penalties (*Tước quyền sử dụng GPLX*, *Tịch thu phương tiện*, *Trừ 12 điểm GPLX*) are codified in dedicated supplemental clauses at the end of each Article (e.g., *Khoản 11 Điều 5*), referencing preceding clauses by index. | The retriever fetches the main fine clause (*Khoản 3 Điểm a*) but completely misses the mandatory 1–3 month license suspension in *Khoản 11 Điểm b*. |
| **Blindness to Exceptions & Overrides** | Exclusion clauses (*"trừ các hành vi vi phạm quy định tại..."*) and emergency vehicle privileges (*Điều 22 Luật 2008*) modify general rules. | Naive retrieval asserts a violation even when the user context qualifies for statutory exemption (e.g., ambulance on emergency duty). |
| **Temporal Version Collision** | Amending decrees (*NĐ 123/2021*) modify specific fine brackets of base decrees (*NĐ 100/2019*); *NĐ 168/2024* introduces demerit points. | Vector search retrieves superseded provisions alongside active ones, producing conflicting fine quotes. |

---

### 1.3. End-to-End Symmetrical Ingestion-Retrieval Architecture

To eliminate these failure modes, the ingestion architecture operates as a deterministic, multi-stage processing pipeline that converts raw unstructured legal text into a structured, fully contextualized, and graph-linked relational knowledge base.

```
%%{init: {"flowchart": {"defaultRenderer": "elk"}}}%%
flowchart TD
    RawDocs["Raw Legal Corpus<br/>(Markdown / PDF / Official Gazette)"] --> Stage1["Stage 1: Document Structure & AST Parser Agent<br/>(Regex Tokenizer + Hierarchy Tree + Lineage Stack)"]
    
    Stage1 --> ASTNodes["Hierarchical AST Nodes<br/>(Document → Chapter → Section → Article → Clause → Point)"]
    
    Stage1 --> Stage2["Stage 2: Semantic Enricher & Pydantic Extractor<br/>(Prefix Synthesis + Entity Extraction + JSON Schema Validation)"]
    
    Stage2 --> CFQC["Canonical Fully Qualified Chunks (CFQC)<br/>(Contextualized Text + Embeddings + Rich JSONB)"]
    
    CFQC --> Stage3["Stage 3: Cross-Reference Graph Linker Agent<br/>(Deterministic Regex Linking + LLM Disambiguation)"]
    
    Stage3 --> KnowledgeGraph["Directed Legal Graph<br/>(DEFINES_SANCTION_FOR, REFERENCES_TECHNICAL_STANDARD, MODIFIES_AND_REPLACES, OVERRIDES_PRIORITY)"]
    
    KnowledgeGraph --> Stage4["Stage 4: Validation & Synthetic Benchmark Generator<br/>(Triad Consistency Checks + 3-Tier QA Generation)"]
    
    Stage4 --> PostgresStore[("PostgreSQL 16 Unified Database Engine<br/>- legal_documents<br/>- legal_chunks (ltree + HNSW vector)<br/>- legal_graph_edges<br/>- sign_catalog<br/>- synthetic_benchmarks")]
```

---

## 2. Context-Preserving Hierarchical Chunking (CPHC) Algorithm

### 2.1. Vietnamese Statutory Syntactic Hierarchy (AST Modeling)

Vietnamese traffic legislation conforms to a strict 6-tier nested syntactic hierarchy governed by the Law on Promulgation of Legislative Documents (*Luật Ban hành văn bản quy phạm pháp luật*):

$$\text{Văn bản (Document)} \longrightarrow \text{Chương (Chapter)} \longrightarrow \text{Mục (Section)} \longrightarrow \text{Điều (Article)} \longrightarrow \text{Khoản (Clause)} \longrightarrow \text{Điểm (Point)}$$

Technical standards (*QCVN 41:2019/BGTVT*) introduce supplemental structures:
$$\text{Quy chuẩn (Standard)} \longrightarrow \text{Phần (Part)} \longrightarrow \text{Chương (Chapter)} \longrightarrow \text{Điều (Article)} \longrightarrow \text{Phụ lục (Appendix)} \longrightarrow \text{Biển báo / Vạch kẻ (Sign/Marking)}$$

```
%%{init: {"flowchart": {"defaultRenderer": "elk"}}}%%
flowchart TD
    DocNode["Văn bản (Document)<br/>e.g., Nghị định 100/2019/NĐ-CP"]
    DocNode --> ChapNode["Chương II: Hành vi vi phạm, hình thức, mức xử phạt..."]
    ChapNode --> SecNode["Mục 1: Vi phạm quy tắc giao thông đường bộ"]
    SecNode --> ArtNode["Điều 5: Xử phạt người điều khiển xe ô tô..."]
    ArtNode --> ClsNode["Khoản 3: Phạt tiền từ 800.000 đồng đến 1.000.000 đồng..."]
    ClsNode --> PtNode1["Điểm a: Không chấp hành hiệu lệnh đèn tín hiệu"]
    ClsNode --> PtNode2["Điểm b: Đi vào đường cấm, khu vực cấm..."]
    ArtNode --> SuppCls["Khoản 11: Hình thức xử phạt bổ sung"]
    SuppCls --> SuppPt1["Điểm b: Tước quyền sử dụng GPLX từ 01 đến 03 tháng..."]
```

---

### 2.2. Deterministic Regular Expression Grammar

The AST Parser Agent employs a strict regular expression grammar designed specifically for Vietnamese legislative conventions:

```python
import re
from typing import Pattern

class VietnameseLegalGrammar:
    """
    Production-grade regex grammar for parsing Vietnamese legal documents into AST nodes.
    Handles accent variations, uppercase/lowercase roman numerals, and technical appendixes.
    """
    
    # Level 1: Document Header
    DOC_HEADER: Pattern[str] = re.compile(
        r"^(LUẬT|NGHỊ ĐỊNH|THÔNG TƯ|QUY CHUẨN KỸ THUẬT QUỐC GIA|QUYẾT ĐỊNH)\s*\n"
        r"(?:Số:\s*([0-9]+/[0-9]+/(?:QH[0-9]+|NĐ-CP|TT-BGTVT|TT-BCA|QĐ-[A-Z]+)|QCVN\s*[0-9]+:[0-9]+/[A-Z]+))\s*\n"
        r"((?:.|\n)+?)(?=\n(?:Căn cứ|Chương|Điều|\Z))",
        re.IGNORECASE | re.MULTILINE
    )
    
    # Level 2: Chapter (Chương)
    CHAPTER: Pattern[str] = re.compile(
        r"^Chương\s+([IVXLCDM]+|[0-9]+)\s*\n+([^\n]+)",
        re.MULTILINE | re.IGNORECASE
    )
    
    # Level 3: Section (Mục)
    SECTION: Pattern[str] = re.compile(
        r"^Mục\s+([0-9]+)\s*\n+([^\n]+)",
        re.MULTILINE | re.IGNORECASE
    )
    
    # Level 4: Article (Điều)
    ARTICLE: Pattern[str] = re.compile(
        r"^Điều\s+([0-9]+)\.\s*([^\n]+)",
        re.MULTILINE
    )
    
    # Level 5: Clause (Khoản) - Leading number followed by period
    CLAUSE: Pattern[str] = re.compile(
        r"^([0-9]+)\.\s+([^\n]+(?:\n(?![0-9]+\.|\b[a-zđ]\)|\bĐiều\s+[0-9]+|\bChương\s+[IVXLCDM]+)[^\n]+)*)",
        re.MULTILINE
    )
    
    # Level 6: Point (Điểm) - Lowercase letter followed by closing parenthesis
    POINT: Pattern[str] = re.compile(
        r"^([a-zđ])\)\s+([^\n]+(?:\n(?![a-zđ]\)|[0-9]+\.|\bĐiều\s+[0-9]+|\bChương\s+[IVXLCDM]+)[^\n]+)*)",
        re.MULTILINE
    )
    
    # Special: Technical Appendix & Sign Specifications (QCVN 41:2019)
    APPENDIX: Pattern[str] = re.compile(
        r"^PHỤ LỤC\s+([A-Z])\s*\n+([^\n]+)",
        re.MULTILINE | re.IGNORECASE
    )
    
    SIGN_SPEC: Pattern[str] = re.compile(
        r"^(Biển\s+số\s+|Vạch\s+số\s+)?([A-Z]\.[0-9]+[a-z]?|[0-9]+\.[0-9]+[a-z]?)\s*[:\.]\s*([^\n]+)\s*\n+((?:.|\n)+?)(?=\n(?:(?:Biển\s+số\s+|Vạch\s+số\s+)?[A-Z]\.[0-9]+|[0-9]+\.[0-9]+|Điều\s+[0-9]+|PHỤ LỤC|\Z))",
        re.MULTILINE
    )
```

---

### 2.3. Prefix Synthesis & Lead Sentence Inheritance Algorithm

To solve context collapse, CPHC computes a contextualized string representation $T_{chunk}$ for each atomic point. Let:
- $D$ be Document provenance metadata (Title, Document Code, Amending Lineage).
- $C$ be Chapter and Section breadcrumbs.
- $A$ be the Article number and title (declaring primary actor and vehicle category).
- $K_{lead}$ be the parent Clause lead sentence (declaring fine range, condition, or obligation).
- $P_{body}$ be the verbatim text of the atomic sub-point.
- $S_{supp}$ be any linked supplemental penalty or demerit points.

The contextualized text $T_{chunk}$ is computed as:

$$T_{chunk} = \operatorname{FormatHeader}(D, C, A) \mathbin{\Vert} \operatorname{FormatLead}(K_{lead}) \mathbin{\Vert} \operatorname{FormatBody}(P_{body}) \mathbin{\Vert} \operatorname{FormatSupp}(S_{supp})$$

```python
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
    additional_sanctions_summary: str | None = None
) -> tuple[str, str]:
    """
    Synthesizes Contextualized Text (for embedding & semantic search)
    and Path string (for ltree relational storage).
    """
    # 1. Build deterministic ltree hierarchy path
    slug = doc_code.lower().replace("/", "_").replace("-", "_").replace(".", "_")
    path_parts = [f"doc_{slug}"]
    if article_num:
        path_parts.append(f"a{article_num}")
    if clause_num:
        path_parts.append(f"c{clause_num}")
    if point_letter:
        path_parts.append(f"p_{point_letter}")
    ltree_path = ".".join(path_parts)
    
    # 2. Synthesize Human-Readable Context Header
    header_lines = [
        f"[VĂN BẢN]: {doc_title} (Số hiệu: {doc_code})",
    ]
    if chapter_title:
        header_lines.append(f"[CHƯƠNG]: {chapter_title}")
    header_lines.append(f"[ĐIỀU {article_num}]: {article_title}")
    
    if clause_num and clause_lead:
        header_lines.append(f"[KHOẢN {clause_num} - LỜI DẪN]: {clause_lead.strip()}")
        
    prefix = "\n".join(header_lines)
    
    # 3. Assemble Full Contextualized Representation
    body_line = f"[ĐIỂM {point_letter}]: {point_body.strip()}" if point_letter else point_body.strip()
    
    contextualized_components = [prefix, body_line]
    if additional_sanctions_summary:
        contextualized_components.append(f"[CHẾ TÀI BỔ SUNG & TRỪ ĐIỂM]: {additional_sanctions_summary.strip()}")
        
    contextualized_text = "\n".join(contextualized_components)
    
    return ltree_path, contextualized_text
```

---

### 2.4. Canonical Fully Qualified Chunk (CFQC) Structure

A **Canonical Fully Qualified Chunk (CFQC)** is the standard output unit of the CPHC engine.

```
+-----------------------------------------------------------------------------------------------------------------------+
| [VĂN BẢN]: Nghị định 100/2019/NĐ-CP (sửa đổi, bổ sung bởi Nghị định 123/2021/NĐ-CP và Nghị định 168/2024/NĐ-CP)       |
| [CHƯƠNG]: Chương II - Hành vi vi phạm, hình thức, mức xử phạt và biện pháp khắc phục hậu quả                          |
| [MỤC]: Mục 1 - Vi phạm quy tắc giao thông đường bộ                                                                    |
| [ĐIỀU 5]: Xử phạt người điều khiển xe ô tô và các loại xe tương tự xe ô tô vi phạm quy tắc giao thông đường bộ        |
| [KHOẢN 3 - LỜI DẪN]: 3. Phạt tiền từ 800.000 đồng đến 1.000.000 đồng đối với người điều khiển xe thực hiện một trong   |
|                      các hành vi vi phạm sau đây:                                                                     |
+-----------------------------------------------------------------------------------------------------------------------+
| [ĐIỂM a - NỘI DUNG]: a) Không chấp hành hiệu lệnh của đèn tín hiệu giao thông;                                        |
+-----------------------------------------------------------------------------------------------------------------------+
| [CHẾ TÀI BỔ SUNG]: Tước quyền sử dụng Giấy phép lái xe từ 01 tháng đến 03 tháng (Khoản 11 Điểm b Điều 5).             |
| [TRỪ ĐIỂM GPLX (NĐ 168/2024)]: Trừ 02 điểm trên Giấy phép lái xe.                                                     |
| [NGOẠI LỆ / ƯU TIÊN]: Không áp dụng với xe ưu tiên đang phát tín hiệu ưu tiên làm nhiệm vụ (Điều 22 Luật GTĐB).       |
+-----------------------------------------------------------------------------------------------------------------------+
```

---

### 2.5. Granularity & Chunk Type Taxonomy

The CPHC engine partitions legal documents into six standardized chunk types:

| Chunk Type | Syntactic Level | Primary Target Content | Chunking Strategy | Primary Query Role |
|---|---|---|---|---|
| `LEGAL_ARTICLE_OVERVIEW` | Điều (Article) | Article Title, Scope, Subject Actor, Summary of Clauses | 1 chunk per Article | High-level actor routing, vehicle category filtering |
| `LEGAL_CLAUSE_ATOMIC` | Điểm (Point) / Khoản đơn | Synthesized Prefix + Clause Lead + Atomic Violation Subpoint | 1 chunk per Point or standalone Clause | Core target for penalty retrieval & fine calculation |
| `LEGAL_SANCTION_SUPPLEMENT` | Khoản bổ sung | License suspension durations, vehicle impoundment, demerit points | Extracted and embedded in parent Article + linked as graph edges | Multi-hop penalty aggregation |
| `TECHNICAL_SIGN_SPEC` | Biển báo / Vạch kẻ | Sign Code, Name, Meaning, Physical Shape, Color, Placement Rules | 1 chunk per Sign/Marking in QCVN 41 | Visual & technical verification queries |
| `EXCEPTION_OVERRIDE_RULE` | Quy tắc ưu tiên | Hierarchy of signals (Police > Light > Sign > Marking), Emergency exemptions | 1 chunk per Priority Rule (`is_override_rule=true`) | Conflict resolution & scope override reasoning |
| `TEMPORAL_AMENDMENT_DELTA` | Điều khoản sửa đổi | Diff text, replaced fine brackets, effective dates | 1 chunk per amendment clause + `AMENDS` edge | Temporal validity & active law resolution |

---

## 3. Multi-Stage Ingestion Agent Workflows & System Prompts

### 3.1. 4-Stage Autonomous Pipeline Architecture

The ingestion pipeline executes across four specialized agents in strict sequence:

```
%%{init: {"flowchart": {"defaultRenderer": "elk"}}}%%
flowchart LR
    subgraph S1["Stage 1: AST Parser Agent"]
        D1["Raw Text Files"] --> P1["Regex Grammar Tokenizer"]
        P1 --> T1["Document AST Hierarchy Tree"]
    end

    subgraph S2["Stage 2: Semantic Enricher Agent"]
        T1 --> P2["LLM Semantic Enricher<br/>(Structured Pydantic Extraction)"]
        P2 --> T2["CFQC Contextualized Chunks"]
    end

    subgraph S3["Stage 3: Graph Linker Agent"]
        T2 --> P3["Deterministic Regex Linker<br/>+ LLM Reference Resolver"]
        P3 --> T3["Knowledge Graph Edges"]
    end

    subgraph S4["Stage 4: Validation & Benchmark Agent"]
        T3 --> P4["Integrity Verification Gate<br/>+ Synthetic QA Generator"]
        P4 --> T4["Persisted Database & Benchmark Suite"]
    end

    S1 --> S2 --> S3 --> S4
```

---

### 3.2. Stage 1: Document Structure & AST Parser Agent

The **Document Structure & AST Parser Agent** performs deterministic text segmentation into a hierarchical AST tree:

```python
from dataclasses import dataclass, field
from typing import Literal

@dataclass
class ASTNode:
    level: Literal["DOCUMENT", "CHAPTER", "SECTION", "ARTICLE", "CLAUSE", "POINT", "APPENDIX", "SIGN_SPEC"]
    index_label: str
    title: str
    raw_text: str
    lead_sentence: str | None = None
    children: list["ASTNode"] = field(default_factory=list)
    parent_path: str = ""
    
    @property
    def full_path(self) -> str:
        clean_idx = self.index_label.lower().replace(" ", "_").replace(".", "_")
        return f"{self.parent_path}.{clean_idx}" if self.parent_path else clean_idx

class LegalASTParser:
    """
    Parses full Vietnamese legal text documents into an in-memory Abstract Syntax Tree.
    """
    def __init__(self, grammar: type[VietnameseLegalGrammar] = VietnameseLegalGrammar):
        self.grammar = grammar

    def parse_document(self, doc_code: str, raw_text: str) -> ASTNode:
        root = ASTNode(
            level="DOCUMENT",
            index_label=doc_code,
            title=doc_code,
            raw_text=raw_text[:500],
            parent_path=""
        )
        
        # Split into chapters / articles
        articles = self.grammar.ARTICLE.split(raw_text)
        # Traverse articles and recursively extract clauses (Khoản) and points (Điểm)
        # Attaches lead sentences to child points
        return root
```

---

### 3.3. Stage 2: Semantic Enricher & Pydantic Extraction Agent

The **Semantic Enricher Agent** evaluates each leaf AST node through an LLM to extract structured entities, actors, vehicle types, violation classes, numerical fine intervals, and exception rules.

#### Complete Production System Prompt:
```markdown
You are the Vietnamese Traffic Law Semantic Extraction Agent (VT-LSE).
Your mission is to perform rigorous, deterministic legal norm extraction on an atomic legislative unit from Vietnamese Traffic Law.

### STATUTORY INSTRUMENTS UNDER MANAGEMENT:
1. Luật Giao thông đường bộ 2008 & Luật Trật tự, an toàn giao thông đường bộ 2024
2. Nghị định 100/2019/NĐ-CP, Nghị định 123/2021/NĐ-CP & Nghị định 168/2024/NĐ-CP
3. Quy chuẩn kỹ thuật quốc gia QCVN 41:2019/BGTVT (Báo hiệu đường bộ)

### EXTRACTION RULES & INVARIANTS:
1. ACTOR & VEHICLE SCOPE:
   - Primary actor must be classified strictly from: ["DRIVER", "PASSENGER", "PEDESTRIAN", "VEHICLE_OWNER", "TRANSPORT_BUSINESS", "ROAD_AUTHORITY", "OTHER"].
   - Vehicle categories must be extracted from the controlled taxonomy: ["CAR_PASSENGER", "CAR_TRUCK", "CAR_BUS", "CAR_TRACTOR", "MOTORCYCLE", "MOPED", "E_MOPED", "E_BICYCLE", "BICYCLE_PRIMITIVE", "SPECIALIZED_MACHINE", "PRIORITY_VEHICLE"].
   - INHERITANCE: If the Point does not explicitly state the vehicle, extract it from the parent Article title.

2. PENALTY BOUNDS (VND):
   - Extract exact integer values for `min_fine_vnd` and `max_fine_vnd`.
   - If the text specifies "Phạt tiền từ 800.000 đồng đến 1.000.000 đồng", output `min_fine_vnd: 800000` and `max_fine_vnd: 1000000`.
   - If the unit defines no monetary fine (e.g. behavioral rule in Law or sign spec in QCVN), both fields must be `null`.

3. ADDITIONAL SANCTIONS & DEMERIT POINTS:
   - License suspension: Extract minimum and maximum months (e.g., "tước quyền sử dụng Giấy phép lái xe từ 01 tháng đến 03 tháng" -> min: 1, max: 3).
   - Vehicle impoundment: Extract duration in days (e.g., "tạm giữ phương tiện đến 07 ngày" -> 7).
   - Demerit points (Luật 2024 / NĐ 168/2024): Extract integer points deducted (2, 3, 4, 6, 10, or 12).

4. EXCEPTIONS & SCOPE OVERRIDES:
   - If the clause contains "trừ trường hợp...", "trừ các hành vi...", or applies to priority vehicles, set `has_exception: true` and extract `exception_clause_text`.

5. STRICT OUTPUT FORMAT:
   - You must output raw, valid JSON conforming strictly to the provided Pydantic schema without markdown codeblocks, explanations, or commentary.
```

#### Few-Shot In-Context Example:
```json
{
  "input_context": {
    "doc_code": "100/2019/NĐ-CP",
    "article_title": "Điều 5. Xử phạt người điều khiển xe ô tô và các loại xe tương tự xe ô tô vi phạm quy tắc giao thông đường bộ",
    "clause_lead": "Khoản 3. Phạt tiền từ 800.000 đồng đến 1.000.000 đồng đối với người điều khiển xe thực hiện một trong các hành vi vi phạm sau đây:",
    "point_text": "a) Không chấp hành hiệu lệnh của đèn tín hiệu giao thông;"
  },
  "expected_output": {
    "norm_role": "SANCTION",
    "primary_actor": "DRIVER",
    "vehicle_types": ["CAR_PASSENGER", "CAR_TRUCK", "CAR_BUS", "CAR_TRACTOR"],
    "violation_categories": ["SIGNAL_COMPLIANCE", "RED_LIGHT"],
    "behavior_summary": "Không chấp hành hiệu lệnh của đèn tín hiệu giao thông khi điều khiển xe ô tô",
    "min_fine_vnd": 800000,
    "max_fine_vnd": 1000000,
    "additional_sanctions": {
      "license_suspension_months_min": 1,
      "license_suspension_months_max": 3,
      "vehicle_impoundment_days": 0,
      "demerit_points": 2
    },
    "remedial_measures": [],
    "exceptions_and_overrides": {
      "has_exception": true,
      "exception_type": "EMERGENCY_VEHICLE",
      "exception_clause_text": "Không áp dụng đối với xe ưu tiên đang phát tín hiệu ưu tiên đi làm nhiệm vụ",
      "overridden_by": ["POLICE_COMMAND", "EMERGENCY_MISSION"]
    },
    "referenced_entities": {
      "law_articles": ["Luật GTĐB 2008: Điều 10 Khoản 3"],
      "qcvn_signs": [],
      "qcvn_markings": []
    }
  }
}
```

---

### 3.4. Stage 3: Cross-Reference Graph Linker Agent

The **Cross-Reference Graph Linker Agent** scans legal clauses to identify intra-document and inter-document statutory relationships:

```markdown
You are the Vietnamese Traffic Law Graph Linker Agent (VT-GLA).
Your objective is to identify and resolve all explicit and implicit statutory references within legal provisions.

### RELATIONSHIP TAXONOMY:
- `DEFINES_SANCTION_FOR`: An administrative decree clause penalizes a behavior defined in Law ($Node_{Decree} \rightarrow Node_{Law}$).
- `HAS_ADDITIONAL_SANCTION`: A primary violation clause is linked to a supplemental sanction clause in the same or related article ($Node_{Decree\_Violation} \rightarrow Node_{Decree\_Supp}$).
- `REFERENCES_TECHNICAL_STANDARD`: A decree or law references a technical sign, marking, or signal defined in QCVN 41:2019 ($Node_{Decree} \rightarrow Node_{QCVN}$).
- `MODIFIES_AND_REPLACES`: An amending decree modifies, replaces, or supplements a base decree clause ($Node_{Amending\_Decree} \rightarrow Node_{Base\_Decree}$).
- `REPEALS`: Explicitly repeals an obsolete clause ($Node_{Amending\_Decree} \rightarrow Node_{Repealed\_Decree}$).
- `OVERRIDES_PRIORITY`: A priority authority (CSGT, Traffic Light, Emergency Vehicle) overrides subordinate rules or signs ($Node_{Higher\_Tier} \rightarrow Node_{Subordinate\_Tier}$).
- `EXEMPTS_CONDITION`: Connects exception provisions to general restrictions ($Node_{Exception} \rightarrow Node_{General\_Rule}$).
- `GUIDES`: Detailed ministerial implementation guidance ($Node_{Circular} \rightarrow Node_{Decree}$).
- `DEFINES_TERM`: Terminology definition mapping ($Node_{Definition} \rightarrow Node_{Rule}$).

### INSTRUCTIONS:
Given the source unit and the full context, extract all outbound edges, resolve the target `ltree` path, and extract the exact statutory quote span. Output a valid JSON list of graph edge objects.
```

---

### 3.5. Stage 4: Validation & Quality Control Agent

The **Validation & Quality Control Agent** enforces strict invariant verification before committing any chunk or edge to PostgreSQL:
1. **Numerical Sanity Check**: `min_fine_vnd <= max_fine_vnd`, fines $\ge 0$, suspension months $\in [1, 24]$.
2. **Hierarchy Path Validation**: Verify parent nodes exist in `legal_chunks` (`parent_id` foreign key validation).
3. **Ontology Integrity**: Verify all vehicle types and violation categories belong to the controlled enum set.
4. **Bi-directional Edge Consistency**: Verify that target units referenced in `legal_graph_edges` resolve to active database records.

---

## 4. Structured Pydantic Extraction Rubrics

### 4.1. Core Domain Schemas & Controlled Vocabularies

```python
from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator

class ActorCategory(str, Enum):
    DRIVER = "DRIVER"
    PASSENGER = "PASSENGER"
    PEDESTRIAN = "PEDESTRIAN"
    VEHICLE_OWNER = "VEHICLE_OWNER"
    TRANSPORT_BUSINESS = "TRANSPORT_BUSINESS"
    ROAD_AUTHORITY = "ROAD_AUTHORITY"
    OTHER = "OTHER"

class VehicleCategory(str, Enum):
    CAR_PASSENGER = "CAR_PASSENGER"         # Ô tô con (<= 9 chỗ, pickup < 950kg)
    CAR_TRUCK = "CAR_TRUCK"                 # Ô tô tải (>= 950kg)
    CAR_BUS = "CAR_BUS"                     # Ô tô khách (> 9 chỗ)
    CAR_TRACTOR = "CAR_TRACTOR"             # Ô tô đầu kéo, sơ mi rơ moóc
    MOTORCYCLE = "MOTORCYCLE"               # Xe mô tô (dung tích >= 50cc hoặc điện > 4kW)
    MOPED = "MOPED"                         # Xe gắn máy (< 50cc, vận tốc <= 50km/h)
    E_MOPED = "E_MOPED"                     # Xe máy điện (<= 4kW, <= 50km/h)
    E_BICYCLE = "E_BICYCLE"                 # Xe đạp điện (<= 250W, có bàn đạp)
    BICYCLE_PRIMITIVE = "BICYCLE_PRIMITIVE" # Xe đạp, xe thô sơ, xích lô, xe súc vật kéo
    SPECIALIZED_MACHINE = "SPECIALIZED_MACHINE" # Xe máy chuyên dùng (thi công, nông nghiệp)
    PRIORITY_VEHICLE = "PRIORITY_VEHICLE"   # Xe ưu tiên (Cứu thương, Chữa cháy, Công an, Quân sự)

class ViolationCategory(str, Enum):
    ALCOHOL_DRUGS = "ALCOHOL_DRUGS"
    SPEED_DISTANCE = "SPEED_DISTANCE"
    LANE_DIRECTION = "LANE_DIRECTION"
    SIGNAL_COMPLIANCE = "SIGNAL_COMPLIANCE"
    RED_LIGHT = "RED_LIGHT"
    STOP_PARK = "STOP_PARK"
    EQUIPMENT_SAFETY = "EQUIPMENT_SAFETY"
    LOAD_PASSENGER = "LOAD_PASSENGER"
    DOCUMENTATION = "DOCUMENTATION"
    PRIORITY_VIOLATION = "PRIORITY_VIOLATION"

class NormRole(str, Enum):
    HYPOTHESIS = "HYPOTHESIS"               # Giả định (Điều kiện kích hoạt)
    PRESCRIPTION = "PRESCRIPTION"           # Quy định (Bổn phận, điều cấm, quy tắc)
    SANCTION = "SANCTION"                   # Chế tài (Xử phạt hành chính)
    TECHNICAL_SPEC = "TECHNICAL_SPEC"       # Quy chuẩn kỹ thuật (Biển báo, vạch kẻ)
    DEFINITION = "DEFINITION"               # Định nghĩa thuật ngữ
    EXCEPTION = "EXCEPTION"                 # Ngoại lệ loại trừ trách nhiệm
    PROCEDURAL = "PROCEDURAL"               # Thủ tục, thẩm quyền xử lý
```

---

### 4.2. Fine Bounds & Administrative Sanction Package Schema

```python
class FineBounds(BaseModel):
    min_fine_vnd: int | None = Field(None, ge=0, description="Minimum fine in VND")
    max_fine_vnd: int | None = Field(None, ge=0, description="Maximum fine in VND")
    average_fine_vnd: int | None = Field(None, ge=0, description="Midpoint fine in VND")

    @model_validator(mode="after")
    def validate_fine_range(self) -> "FineBounds":
        if self.min_fine_vnd is not None and self.max_fine_vnd is not None:
            if self.min_fine_vnd > self.max_fine_vnd:
                raise ValueError(f"min_fine_vnd ({self.min_fine_vnd}) cannot exceed max_fine_vnd ({self.max_fine_vnd})")
            if self.average_fine_vnd is None:
                self.average_fine_vnd = (self.min_fine_vnd + self.max_fine_vnd) // 2
        return self

class AdditionalSanctions(BaseModel):
    license_suspension_months_min: int | None = Field(None, ge=1, le=36, description="Min months of driving license suspension")
    license_suspension_months_max: int | None = Field(None, ge=1, le=36, description="Max months of driving license suspension")
    vehicle_impoundment_days: int | None = Field(None, ge=0, le=30, description="Days of temporary vehicle impoundment")
    demerit_points: int | None = Field(None, ge=0, le=12, description="Driving license demerit points (Luật 2024 / NĐ 168/2024)")

    @model_validator(mode="after")
    def validate_suspension_range(self) -> "AdditionalSanctions":
        if self.license_suspension_months_min and self.license_suspension_months_max:
            if self.license_suspension_months_min > self.license_suspension_months_max:
                raise ValueError("license_suspension_months_min cannot exceed max")
        return self
```

---

### 4.3. Demerit Points & License Revocation Schema (2024-2025 Mandates)

Under the 2024 Law on Road Traffic Order and Safety (*Luật Trật tự, an toàn giao thông đường bộ 2024*) and *Nghị định 168/2024/NĐ-CP*, driving licenses carry a total bank of **12 points per year**. The extraction rubric mandates capturing explicit point deductions:

```python
class DemeritPointDeduction(BaseModel):
    is_demerit_applicable: bool = Field(False, description="Whether points deduction applies to this violation")
    points_deducted: Literal[0, 2, 3, 4, 6, 10, 12] = Field(0, description="Exact points deducted from 12-point license bank")
    legal_basis: str = Field("Nghị định 168/2024/NĐ-CP", description="Statutory provision establishing point deduction")
```

---

### 4.4. Exceptions & Scope Overrides Schema

```python
class ExceptionMetadata(BaseModel):
    has_exception: bool = Field(False, description="Whether this unit contains an exemption or override clause")
    exception_type: str | None = Field(None, description="Category: EMERGENCY_VEHICLE, POLICE_ESCORT, TECHNICAL_MALFUNCTION")
    exception_clause_text: str | None = Field(None, description="Verbatim text of the exception clause")
    overridden_by: list[str] = Field(default_factory=list, description="Authorities overriding this rule: POLICE_COMMAND, TRAFFIC_LIGHT")
    exempt_vehicle_categories: list[VehicleCategory] = Field(default_factory=list, description="Vehicles exempt from this sanction")
```

---

### 4.5. Master `LegalNormExtraction` Pydantic v2 Implementation

```python
class ReferencedEntity(BaseModel):
    law_articles: list[str] = Field(default_factory=list, description="Referenced Law Articles (e.g. 'Luật GTĐB Điều 10')")
    qcvn_signs: list[str] = Field(default_factory=list, description="Referenced Sign codes (e.g. 'P.102', 'W.201')")
    qcvn_markings: list[str] = Field(default_factory=list, description="Referenced Road Marking codes (e.g. '1.1', '2.2')")
    amending_decrees: list[str] = Field(default_factory=list, description="Amending decree references (e.g. '123/2021/NĐ-CP')")

class LegalNormExtraction(BaseModel):
    """
    Master production extraction model enforcing 100% schema alignment with PostgreSQL legal_chunks.
    """
    chunk_id: str = Field(..., description="Deterministic UUID string")
    hierarchy_path: str = Field(..., pattern=r"^doc_[a-z0-9_]+(?:\.[a-z0-9_]+)*$", description="Valid ltree dot-separated path")
    document_code: str = Field(..., description="e.g. '100/2019/NĐ-CP'")
    document_type: Literal["LUAT", "NGHI_DINH", "THONG_TU", "QUY_CHUAN_KY_THUAT", "QUYET_DINH"]
    
    article_number: int = Field(..., ge=1)
    clause_number: int | None = Field(None, ge=1)
    point_letter: str | None = Field(None, pattern=r"^[a-zđ]$")
    
    norm_role: NormRole
    primary_actor: ActorCategory
    vehicle_types: list[VehicleCategory] = Field(min_length=1)
    violation_categories: list[ViolationCategory] = Field(min_length=1)
    
    behavior_summary: str = Field(..., min_length=10, description="Clear, concise Vietnamese behavior summary")
    fine_bounds: FineBounds
    additional_sanctions: AdditionalSanctions
    remedial_measures: list[str] = Field(default_factory=list)
    
    exceptions_and_overrides: ExceptionMetadata
    referenced_entities: ReferencedEntity
    
    contextualized_text: str = Field(..., min_length=20, description="Full CPHC synthesized text for vector embedding")
```

---

## 5. Automated Relationship Linking & Knowledge Graph Construction

### 5.1. Legal Graph Edge Topology

The ingestion engine establishes typed, directed graph edges linking legal provisions across instruments:

```
%%{init: {"flowchart": {"defaultRenderer": "elk"}}}%%
flowchart TD
    LawNode["Luật GTĐB 2008 / TTATGTĐB 2024<br/>Điều 10: Hệ thống báo hiệu đường bộ"]
    DecreeNode["Nghị định 100/2019/NĐ-CP<br/>Điều 5 Khoản 3 Điểm a: Vượt đèn đỏ ô tô"]
    DecreeSuppNode["Nghị định 100/2019/NĐ-CP<br/>Điều 5 Khoản 11 Điểm b: Tước GPLX 1-3 tháng"]
    QCVNNode["QCVN 41:2019/BGTVT<br/>Điều 10: Ý nghĩa tín hiệu đèn giao thông"]
    AmendingNode["Nghị định 123/2021/NĐ-CP<br/>Khoản 3 Điều 2: Sửa đổi mức phạt NĐ 100"]

    has_exception: bool = False
    exception_meta: ExceptionMetadata | None = None
    effective_date: date
    expiration_date: date | None = None
```

---

## 5. Automated Graph Construction & Cross-Reference Linker

### 5.1. Triad Linker Architecture

The **Cross-Reference Graph Linker Agent** resolves statutory dependencies across decoupled legal instruments.

```
%%{init: {"flowchart": {"defaultRenderer": "elk"}}}%%
flowchart LR
    subgraph NormativeTriad["Decoupled Normative Triad"]
        NodeLaw["Luật GTĐB 2008 / TTATGTĐB 2024<br/>(Prescription: Rules of Conduct)"]
        NodeDecree["Nghị định 100/2019 / NĐ 168/2024<br/>(Sanction: Administrative Fines)"]
        NodeQCVN["QCVN 41:2019/BGTVT<br/>(Technical Spec: Signs & Markings)"]
    end
    
    NodeDecree -->|DEFINES_SANCTION_FOR| NodeLaw
    NodeDecree -->|REFERENCES_TECHNICAL_STANDARD| NodeQCVN
    NodeDecree -->|HAS_ADDITIONAL_SANCTION| NodeDecree
```

### 5.2. Deterministic Regex Linker Implementation

```python
import re
from typing import Any

class DeterministicGraphLinker:
    """
    High-precision deterministic rule extractor for explicit cross-references.
    """
    ARTICLE_REF_REGEX = re.compile(
        r"(?:quy định tại|theo quy định tại)\s+(?:điểm\s+(?P<point>[a-zđ]),\s+)?(?:khoản\s+(?P<clause>\d+),\s+)?(?:điều\s+(?P<article>\d+))",
        re.IGNORECASE
    )
    SIGN_REF_REGEX = re.compile(
        r"biển\s+(?:báo|hiệu)?\s*(?:số)?\s*(?P<sign_code>[P|W|R|I|S|DP]\.\d+[a-z]?)",
        re.IGNORECASE
    )
    
    def extract_deterministic_edges(self, chunk: LegalNormExtraction) -> list[dict[str, Any]]:
        edges = []
        
        # 1. Extract Sign Standards (REFERENCES_TECHNICAL_STANDARD)
        for match in self.SIGN_REF_REGEX.finditer(chunk.verbatim_text):
            sign_code = match.group("sign_code").upper()
            edges.append({
                "relation_type": "REFERENCES_TECHNICAL_STANDARD",
                "target_external_ref": f"QCVN 41:2019/BGTVT - Biển {sign_code}",
                "target_path": f"doc_qcvn41_2019.app_b.{sign_code.lower().replace('.', '_')}",
                "description": f"Dẫn chiếu quy chuẩn kỹ thuật biển báo {sign_code}",
                "confidence_score": 1.0
            })
            
        # 2. Extract Additional Sanction Links (HAS_ADDITIONAL_SANCTION)
        if chunk.additional_sanctions.license_suspension_months_min or chunk.additional_sanctions.demerit_points:
            edges.append({
                "relation_type": "HAS_ADDITIONAL_SANCTION",
                "target_path": chunk.hierarchy_path,
                "description": "Hình thức xử phạt bổ sung: Tước quyền sử dụng GPLX",
                "confidence_score": 0.98
            })
            
        return edges
```

---

### 5.4. Graph Construction & Idempotent Database Loading

Edges are persisted to PostgreSQL `legal_graph_edges` using an **idempotent `ON CONFLICT DO NOTHING`** strategy:

```sql
INSERT INTO legal_graph_edges (
    source_chunk_id,
    target_chunk_id,
    source_path,
    target_path,
    target_external_ref,
    relation_type,
    description,
    confidence_score
) VALUES (
    $1, $2, $3, $4, $5, $6, $7, $8
)
ON CONFLICT (source_chunk_id, target_chunk_id, relation_type) 
DO UPDATE SET 
    confidence_score = EXCLUDED.confidence_score,
    description = EXCLUDED.description;
```

---

## 6. Synthetic Multi-Hop Benchmark Generation

### 6.1. Closed-Loop Evaluation Philosophy

To guarantee zero regression and verify that every ingested unit is retrievable, the Ingestion Engine automatically generates a **Synthetic Multi-Hop Benchmark Suite** during the indexing phase. Each synthetic test case is bound to a verified **Gold Citation Path (Chain of Custody)**.

```
%%{init: {"flowchart": {"defaultRenderer": "elk"}}}%%
flowchart TD
    IngestedGraph["Ingested Knowledge Graph<br/>(Law ↔ Decree ↔ QCVN)"] --> GenAgent["Synthetic QA Benchmark Generator Agent"]
    
    GenAgent --> T1["Tier 1: Single-Hop Factual Queries<br/>(Direct penalty lookup)"]
    GenAgent --> T2["Tier 2: Multi-Hop Triad Traversals<br/>(Sign → Behavior → Sanction)"]
    GenAgent --> T3["Tier 3: Scope Overrides & Exceptions<br/>(Emergency vehicles, Signal hierarchy)"]
    
    T1 --> Gold1["Gold Path: [ND100.D6.K4.De]"]
    T2 --> Gold2["Gold Path: [QCVN.P102 → ND100.D5.K5.Dc → ND100.D5.K11.Dc]"]
    T3 --> Gold3["Gold Path: [LUAT.D11 → LUAT.D22 → QCVN.D4 → ND100.D5.K3.Da]"]
    
    Gold1 & Gold2 & Gold3 --> Registry[("Benchmark Evaluation Registry<br/>data/dev/synthetic_traffic_law_qa.jsonl")]
```

---

## 7. Operational Ingestion Pipeline & Traceability Matrix

### 7.1. CLI Ingestion Workflow & Pipeline Orchestration

The ingestion pipeline is invoked via the project's standardized CLI commands:

```bash
# 1. Ingest raw legal corpus and execute AST parsing + Pydantic extraction
uv run rag-eval ingest --dataset all --output-dir ./data

# 2. Build dense HNSW vector index and compute embeddings
uv run rag-eval index --dataset all

# 3. Generate synthetic multi-hop benchmark validation suite
uv run rag-eval generate-benchmark --dataset all --output ./data/dev/synthetic_traffic_law_qa.jsonl
```

### 7.2. Temporal Diffing & Incremental Update Engine

When amending decrees (*Nghị định 123/2021/NĐ-CP*, *Nghị định 168/2024/NĐ-CP*) are published, the ingestion pipeline avoids destructive full re-indexing. Instead, it executes an **Incremental Temporal Diff**:

```
%%{init: {"flowchart": {"defaultRenderer": "elk"}}}%%
flowchart TD
    NewDecree["New Amending Decree<br/>(NĐ 123/2021 / NĐ 168/2024)"] --> DiffParser["AST Diff Parser<br/>(Detects modified Articles/Clauses)"]
    
    DiffParser --> MarkObsolete["Update Target Units<br/>(Set expiration_date & status = PARTIALLY_EXPIRED)"]
    
    DiffParser --> InsertNewUnits["Insert New/Amended Units<br/>(effective_date = 01/01/2022 / 01/01/2025)"]
    
    InsertNewUnits --> AddAmendsEdge["Create MODIFIES_AND_REPLACES Edges<br/>(Links Amending Unit → Base Unit)"]
    
    AddAmendsEdge --> RecomputeEmbedding["Recompute Embeddings & Update HNSW Index"]
```

### 7.3. Comprehensive Ingestion-Retrieval Traceability Matrix

The following matrix establishes strict **1-to-1 functional symmetry** between ingested metadata and the retrieval/reasoning operations they power:

| Ingested Metadata / Artifact | Extraction Source & Format | Database Storage Column | Direct Retrieval / Reasoning Operation | Enabled MCP Tool |
|---|---|---|---|---|
| **Hierarchical Path** | AST Parser (`doc_nd100.c2.s1.a5.c3.p_a`) | `hierarchy_path` (`ltree`) | Scope scoping, parent clause expansion, sibling retrieval | `mcp_traffic_hierarchical_navigate` |
| **Contextualized Prefix** | CPHC Prefix Engine (Doc + Art + Clause lead) | `contextualized_text` + Embedding | High-accuracy dense semantic matching without vehicle ambiguity | `mcp_traffic_hybrid_search` |
| **Vehicle Categories** | LLM Extractor (`['CAR_PASSENGER', 'CAR_TRUCK']`) | `vehicle_types` (`jsonb` / GIN) | Hard SQL metadata filtering; prevents showing motorcycle penalties for cars | `mcp_traffic_hybrid_search(vehicle_types=...)` |
| **Violation Classes** | LLM Extractor (`['SIGNAL_COMPLIANCE', 'RED_LIGHT']`) | `violation_categories` (`jsonb` / GIN) | Multi-intent clustering, behavioral disambiguation | `mcp_traffic_hybrid_search(violation_categories=...)` |
| **Fine Bounds (Min/Max)** | LLM Extractor (`800000`, `1000000`) | `min_fine_vnd`, `max_fine_vnd` (`bigint`) | Range queries ("phạt trên 10 triệu?"), precise numerical synthesis | `mcp_traffic_hybrid_search(min_fine, max_fine)` |
| **Additional Sanctions** | LLM Extractor (`license_suspension_months`) | `additional_sanctions` (`jsonb`) | Immediate aggregation of supplemental penalties without secondary latency | `mcp_traffic_hybrid_search` |
| **Normative Role** | LLM Extractor (`HYPOTHESIS`, `SANCTION`, etc.) | `norm_role` (`legal_norm_role`) | Triad assembly (Behavior $\leftrightarrow$ Sanction $\leftrightarrow$ Technical Rule) | `mcp_traffic_graph_traverse` |
| **Exception Flags** | LLM Extractor (`has_exception: true`) | `is_exception` (`bool`), `exception_meta` (`jsonb`) | Priority & override reasoning, conditional exemption matching | `mcp_traffic_scope_override_detect` |
| **Technical Sign Links** | Automated Linker (`P.102`, `Vạch 1.1`) | `legal_graph_edges` (`REFERENCES_TECHNICAL_STANDARD`) | 1-hop instant graph traversal from behavior to sign visual/spec | `mcp_traffic_sign_catalog_lookup` |
| **Amendment Directed Edges** | Temporal Linker (`MODIFIES_AND_REPLACES`, `REPEALS`) | `legal_graph_edges` (`MODIFIES_AND_REPLACES`) | Lex posterior resolution; automatic forwarding from old to new fine brackets | `mcp_traffic_graph_traverse` |
| **Synthetic QA Benchmarks** | Benchmark Gen (`synthetic_qa.jsonl`) | Dedicated benchmark table / JSONL registry | Closed-loop automated retrieval regression testing & CI evaluation | `mcp_traffic_corpus_validate` |

---

## 8. Summary of Implementation Invariants

1. **Zero Character-Based Chunking**: Chunk boundaries are governed strictly by the legal AST (`Văn bản → Chương → Mục → Điều → Khoản → Điểm`).
2. **Mandatory Prefix Synthesis**: Every atomic sub-point inherits its parent document metadata, chapter, article title, and clause lead sentence before embedding.
3. **Strict Pydantic Validation**: All extracted attributes (actors, vehicles, fines, suspensions, demerit points) must pass Pydantic v2 validation before database insertion.
4. **Automated Triad Graph Edge Construction**: Every administrative sanction is explicitly linked to its behavioral rule in Law and technical standard in QCVN via `legal_graph_edges`.
5. **Closed-Loop Synthetic Evaluation**: Ingestion automatically emits 3-tier QA benchmark pairs with gold citation paths for automated retrieval verification.
