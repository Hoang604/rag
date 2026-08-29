# Vietnamese Traffic Legal Information Structure
## Formal Domain Architecture, Shared Ontology, and Knowledge Graph Specification for Agentic RAG

**Document Reference**: `SPEC-DOC-01-LEGAL-STRUCTURE`  
**System Milestone**: Milestone 1 (M1) — Domain Modeling & Shared Ontology Design  
**Target Platform**: PostgreSQL 16+ (pgvector + JSONB) | Model Context Protocol (MCP) Multi-Agent Engine  
**Jurisprudential Framework**: Vietnam Road Traffic Legal System (Luật 2008 & 2024, Nghị định 100/123/168, QCVN 41:2019/BGTVT, TT 31/2019)  
**Status**: Authoritative Technical Architecture Specification  

---

## Table of Contents
1. [Executive Summary & Foundational Legal Principles](#1-executive-summary--foundational-legal-principles)
   - [1.1 Legal Domain Nature & Jurisprudential Context](#11-legal-domain-nature--jurisprudential-context)
   - [1.2 System Mission & Failure Modes of Naive RAG](#12-system-mission--failure-modes-of-naive-rag)
   - [1.3 Core Architectural Invariants](#13-core-architectural-invariants)
2. [Domain Taxonomy & Syntactic Hierarchy Breakdown](#2-domain-taxonomy--syntactic-hierarchy-breakdown)
   - [2.1 Formal 6-Tier Legislative Hierarchy](#21-formal-6-tier-legislative-hierarchy)
   - [2.2 The "Dangling Point" Problem (Hiện tượng Điểm mồ côi)](#22-the-dangling-point-problem-hiện-tượng-điểm-mồ-côi)
   - [2.3 Canonical Fully Qualified Chunks (CFQC) Architecture](#23-canonical-fully-qualified-chunks-cfqc-architecture)
   - [2.4 AST Representation & Context Enrichment Pipeline](#24-ast-representation--context-enrichment-pipeline)
3. [Physically Decoupled Normative Triad](#3-physically-decoupled-normative-triad)
   - [3.1 Jurisprudential Triad Theory: Giả định – Quy định – Chế tài](#31-jurisprudential-triad-theory-giả-định--quy-định--chế-tài)
   - [3.2 Cross-Instrument Tripartite Decoupling Matrix](#32-cross-instrument-tripartite-decoupling-matrix)
   - [3.3 Multi-Hop Statutory Traversal Walkthroughs](#33-multi-hop-statutory-traversal-walkthroughs)
     - [3.3.1 Speeding in Non-Divided Urban Corridor](#331-speeding-in-non-divided-urban-corridor)
     - [3.3.2 Red Light vs CSGT Manual Overrides](#332-red-light-vs-csgt-manual-overrides)
     - [3.3.3 Emergency Vehicle Privileges & Exclusion Clauses](#333-emergency-vehicle-privileges--exclusion-clauses)
     - [3.3.4 License Point Deduction Mechanics (12-Point System)](#334-license-point-deduction-mechanics-12-point-system)
4. [Shared Ontology & Controlled Vocabulary](#4-shared-ontology--controlled-vocabulary)
   - [4.1 Controlled Vehicle Taxonomy (VehicleType)](#41-controlled-vehicle-taxonomy-vehicletype)
   - [4.2 Exhaustive Violation Category Taxonomy (ViolationCategory & ViolationType)](#42-exhaustive-violation-category-taxonomy-violationcategory--violationtype)
   - [4.3 Norm Roles & Functional Classification (NormRole)](#43-norm-roles--functional-classification-normrole)
   - [4.4 Graph Edge Relations & Directionality Constraints (RelationType)](#44-graph-edge-relations--directionality-constraints-relationtype)
   - [4.5 Formal JSON Schema Specifications](#45-formal-json-schema-specifications)
5. [Formal Mathematical & Knowledge Graph Modeling](#5-formal-mathematical--knowledge-graph-modeling)
   - [5.1 Directed Attributed Property Graph Definition: G = (V, E)](#51-directed-attributed-property-graph-definition-g--v-e)
   - [5.2 Operational Signal Precedence Algebra](#52-operational-signal-precedence-algebra)
   - [5.3 Jurisprudential Scope Overrides & Exception Logic](#53-jurisprudential-scope-overrides--exception-logic)
   - [5.4 Temporal Active Windows & Dynamic Amendment Diff Chains](#54-temporal-active-windows--dynamic-amendment-diff-chains)
6. [Downstream System Architecture Directives](#6-downstream-system-architecture-directives)
   - [6.1 Directives for PostgreSQL + pgvector Schema Design (`docs/02`)](#61-directives-for-postgresql--pgvector-schema-design-docs02)
   - [6.2 Directives for MCP Tool Ecosystem & JSON-RPC Protocols (`docs/03`)](#62-directives-for-mcp-tool-ecosystem--json-rpc-protocols-docs03)
   - [6.3 Directives for Symmetrical Ingestion & CPHC Chunking (`docs/04`)](#63-directives-for-symmetrical-ingestion--cphc-chunking-docs04)
   - [6.4 Directives for Multi-Hop Retrieval & Reasoning Engine (`docs/05`)](#64-directives-for-multi-hop-retrieval--reasoning-engine-docs05)

---

## 1. Executive Summary & Foundational Legal Principles

### 1.1 Legal Domain Nature & Jurisprudential Context
The Vietnamese statutory framework governing road traffic constitutes a codified Civil Law system characterized by a strict constitutional and legislative hierarchy. Statutory rules are not encapsulated within a monolithic legal code; rather, they are distributed across legislative, executive, and technical regulatory tiers enacted under the *Law on Promulgation of Legislative Documents* (Luật Ban hành văn bản quy phạm pháp luật — Law No. 80/2015/QH13, amended by Law No. 63/2020/QH14).

In this system:
1. **Primary Legislative Authority (Quốc hội)** establishes behavioral mandates, definitions, civil duties, and statutory prohibitions via parliamentary statutes (*Luật*).
2. **Executive Regulatory Authority (Chính phủ & Bộ ngành)** prescribes administrative sanctions, fine brackets, procedural coercions, and executive instructions via governmental decrees (*Nghị định*) and ministerial circulars (*Thông tư*).
3. **National Technical Standards (Bộ Giao thông Vận tải / Bộ Công an)** dictate the exact geometric, colorimetric, semantic, and operational parameters of physical road signals, markings, and infrastructure via mandatory national technical regulations (*Quy chuẩn kỹ thuật quốc gia - QCVN*).

```
%%{init: {"flowchart": {"defaultRenderer": "elk"}}}%%
flowchart TB
    subgraph TIERS["HỆ THỐNG VĂN BẢN QUY PHẠM PHÁP LUẬT GIAO THÔNG"]
        direction TB
        T1["TẦNG 1: QUỐC HỘI (Parliamentary Statutes)<br/>• Luật Giao thông đường bộ 2008 (Luật số 23/2008/QH12)<br/>• Luật Trật tự, an toàn GTĐB 2024 (Luật số 36/2024/QH15)<br/>• Luật Đường bộ 2024 (Luật số 35/2024/QH15)"]
        T2["TẦNG 2: CHÍNH PHỦ (Governmental Decrees)<br/>• Nghị định 100/2019/NĐ-CP (Xử phạt VPHC GTĐB & ĐS)<br/>• Nghị định 123/2021/NĐ-CP (Sửa đổi, bổ sung NĐ 100)<br/>• Nghị định 168/2024/NĐ-CP (Thay thế NĐ 100/123, Trừ điểm GPLX)"]
        T3["TẦNG 3: BỘ NGÀNH (Technical Regulations & Circulars)<br/>• QCVN 41:2019/BGTVT (Báo hiệu đường bộ: Biển báo, Vạch kẻ, Đèn tín hiệu)<br/>• Thông tư 31/2019/TT-BGTVT (Tốc độ & Khoảng cách an toàn xe cơ giới)<br/>• Thông tư 24/2023/TT-BCA & Thông tư 28/2024/TT-BCA (Đăng ký biển số & VNeID)"]
    end
    
    T1 -->|"Trao quyền quy định chế tài & chi tiết hóa"| T2
    T1 -->|"Quy chuẩn hóa kỹ thuật báo hiệu & vận hành"| T3
    T2 -->|"Dẫn chiếu tiêu chuẩn kỹ thuật & điều kiện áp dụng"| T3
```

### 1.2 System Mission & Failure Modes of Naive RAG
The mission of this Agentic RAG architecture is to deliver legally sound, deterministic, explainable, and fully auditable legal counsel and violation triage for Vietnamese road traffic scenarios. 

Standard Retrieval-Augmented Generation systems ("Naive RAG") relying on character-count or fixed-token chunking coupled with vanilla dense vector search catastrophically fail in the Vietnamese legal domain due to five fundamental structural breakdowns:

1. **Context Fragmentation via the "Dangling Point" Problem**:
   Standard chunkers slice text at fixed character boundaries or naive paragraph breaks, isolating a legislative "Điểm" (Point) from its mandatory "Khoản" (Clause) lead sentence. The resulting vector chunk loses the vehicle category (`Loại phương tiện`), the penalty bracket (`Khung tiền phạt`), and the syntactic conjunction/disjunction operators, rendering semantic similarity matching hallucination-prone.
2. **Physical Triad Decoupling**:
   A single user query (e.g., *"Driving a car at 68 km/h on an undivided urban road: fine and license penalty?"*) cannot be answered by any single document. The speed limit ($50\text{ km/h}$) is defined in a Ministerial Circular (TT 31/2019); the duty to obey limits is in a Parliamentary Law (Luật GTĐB); while the monetary fine ($4.000.000\text{đ} - 6.000.000\text{đ}$) and license suspension ($1 - 3\text{ months}$) reside in an Executive Decree (NĐ 100/2019 amended by NĐ 123/2021). Naive RAG retrieves isolated fragments and fails to synthesize the complete normative triad.
3. **Statutory Signal Hierarchy Inversion**:
   In Vietnamese traffic law, traffic signals follow a strict statutory partial order: $\text{Traffic Police (CSGT)} \succ \text{Traffic Lights} \succ \text{Road Signs} \succ \text{Pavement Markings}$. Naive lexical or dense vector matching cannot prioritize a police officer's hand signal overriding a static red light, leading to incorrect violation assertions.
4. **Scope Overrides & Lex Specialis Neglect**:
   General duties are subject to explicit statutory exemptions (*Trừ trường hợp...*, emergency vehicles under Article 22 Law 2008 / Article 20 Law 2024). Naive RAG lacks a formal override evaluation engine, asserting violations against emergency responders or permitted turn maneuvers.
5. **Temporal Validity & Amendment Blindness**:
   Statutory instruments undergo progressive amendments (NĐ 100 $\to$ NĐ 123 $\to$ NĐ 168; Luật 2008 $\to$ Luật 36/2024). Naive semantic retrieval mingles superseded fine schedules with active provisions, returning invalid penalties or obsolete point systems.

### 1.3 Core Architectural Invariants
To resolve these failure modes, this specification establishes six foundational architectural invariants:

* **Invariant 1 (Contextual Integrity)**: No legislative node below the `Điều` (Article) level shall ever be embedded or ingested into vector storage without its complete hierarchical ancestry and syntactic lead clause (Canonical Fully Qualified Chunk — CFQC).
* **Invariant 2 (Symmetrical Schema Coupling)**: Every domain entity, taxonomy code, and relational edge generated during ingestion must strictly map to dedicated JSONB schemas and PostgreSQL relational structures queried by the retrieval engine.
* **Invariant 3 (Normative Triad Completeness)**: Every legal advice response generated by the system must resolve all three legs of the normative triad ($\text{Hypothesis } \mathcal{H} \to \text{Prescription } \mathcal{P} \to \text{Sanction } \mathcal{S}$) across the relevant multi-document chain.
* **Invariant 4 (Strict Precedence Execution)**: Conflicting road signal inputs must be resolved through a deterministic algebra implementing statutory priority before violation evaluation occurs.
* **Invariant 5 (Deterministic Temporal Pinning)**: Every retrieval query is bound to a temporal evaluation timestamp $t_{\text{query}}$ to filter out inactive, expired, or not-yet-effective legal nodes.
* **Invariant 6 (Verifiable Chain of Custody)**: All factual assertions must produce an immutable, machine-verifiable citation path down to the exact `Văn bản` $\to$ `Điều` $\to$ `Khoản` $\to$ `Điểm`.

---

## 2. Domain Taxonomy & Syntactic Hierarchy Breakdown

### 2.1 Formal 6-Tier Legislative Hierarchy
Vietnamese statutory instruments adhere strictly to a standardized 6-tier structural nesting defined by Law No. 80/2015/QH13:

$$\text{Document (Văn bản)} \longrightarrow \text{Chapter (Chương)} \longrightarrow \text{Section (Mục)} \longrightarrow \text{Article (Điều)} \longrightarrow \text{Clause (Khoản)} \longrightarrow \text{Point (Điểm)}$$

```
%%{init: {"flowchart": {"defaultRenderer": "elk"}}}%%
flowchart TD
    D["TẦNG 1: VĂN BẢN (Document)<br/>Mã: document_id | Ví dụ: ND-100-2019-ND-CP"]
    C["TẦNG 2: CHƯƠNG (Chapter)<br/>Mã: chapter_id | Ví dụ: Chương II - Hành vi vi phạm & Xử phạt"]
    S["TẦNG 3: MỤC (Section - Optional)<br/>Mã: section_id | Ví dụ: Mục 1 - Vi phạm quy tắc GTĐB"]
    A["TẦNG 4: ĐIỀU (Article)<br/>Mã: article_id | Ví dụ: Điều 6 - Xử phạt người điều khiển xe mô tô, xe gắn máy"]
    K["TẦNG 5: KHOẢN (Clause)<br/>Mã: clause_id | Lời dẫn (Lead Sentence) & Khung phạt chính"]
    P["TẦNG 6: ĐIỂM (Point)<br/>Mã: point_id | Hành vi vi phạm vi mô / Trường hợp cụ thể"]

    D --> C --> S --> A --> K --> P
```

#### Detailed Specification of Structural Tiers:

| Level | Vietnamese Name | Canonical ID Format | Mandatory Metadata Attributes | Semantic Function & Scope |
| :--- | :--- | :--- | :--- | :--- |
| **Level 1** | **Văn bản** (Document) | `doc::{type}::{number}::{year}` (e.g., `doc::nd::100::2019`) | `doc_type`, `official_number`, `title`, `promulgation_date`, `effective_date`, `expiry_date`, `issuer_authority`, `status` | The apex legal instrument enacting norms, definitions, or sanctions. |
| **Level 2** | **Chương** (Chapter) | `{doc_id}::c::{roman_num}` (e.g., `doc::nd::100::2019::c::II`) | `chapter_number`, `chapter_title`, `scope_summary` | Broad thematic domain partition (e.g., General Provisions, Violations & Sanctions, Enforcement Authority). |
| **Level 3** | **Mục** (Section) | `{chapter_id}::s::{arabic_num}` (e.g., `doc::nd::100::2019::c::II::s::1`) | `section_number`, `section_title` | Sub-thematic grouping within large chapters (optional in smaller instruments). |
| **Level 4** | **Điều** (Article) | `{doc_id}::art::{arabic_num}` (e.g., `doc::nd::100::2019::art::6`) | `article_number`, `article_title`, `target_subject_scope` | Primary statutory unit defining a discrete violation topic, vehicle category, or regulatory mandate. |
| **Level 5** | **Khoản** (Clause) | `{article_id}::cl::{arabic_num}` (e.g., `doc::nd::100::2019::art::6::cl::1`) | `clause_number`, `lead_text`, `tail_text`, `fine_min`, `fine_max`, `conjunction_type` | Structural clause containing the mandatory **Lead Sentence** (defining subject and penalty bracket) or standalone norm. |
| **Level 6** | **Điểm** (Point) | `{clause_id}::pt::{letter}` (e.g., `doc::nd::100::2019::art::6::cl::1::pt::a`) | `point_letter`, `content_text`, `action_code`, `exception_clause` | Granular prohibited behavior, specific condition, or discrete operational trigger. |

*Technical Standards (QCVN 41:2019/BGTVT) Extension*:
In addition to the standard 6 tiers, technical standards introduce:
- **Phụ lục (Appendix)**: e.g., `qcvn::41::2019::app::B` (Catalog of Regulatory Prohibition Signs - Biển báo cấm).
- **Tiểu mục / Tiết (Sub-point)**: Granular geometric dimensions, optical retroreflection values, and installation tolerances.

---

### 2.2 The "Dangling Point" Problem (Hiện tượng Điểm mồ côi)

#### 2.2.1 Linguistic and Legal Anatomy
In Vietnamese legislative drafting conventions for administrative sanction decrees, an individual `Điểm` (Point) **never constitutes an independent semantic statement**. It is syntactically and legally subordinate to the `Khoản` (Clause) lead sentence and the `Điều` (Article) title.

Consider the concrete statutory construction of **Decree No. 100/2019/NĐ-CP, Article 6, Clause 1, Point a**:

```text
[ĐIỀU 6]: Xử phạt người điều khiển xe mô tô, xe gắn máy (kể cả xe máy điện), các loại xe tương tự xe mô tô và các loại xe tương tự xe gắn máy vi phạm quy tắc giao thông đường bộ
  [KHOẢN 1 - LỜI DẪN (Lead Sentence)]: Phạt tiền từ 100.000 đồng đến 200.000 đồng đối với người điều khiển xe thực hiện một trong các hành vi vi phạm sau đây:
    [ĐIỂM a]: a) Không chấp hành hiệu lệnh, chỉ dẫn của biển báo hiệu, vạch kẻ đường, trừ các hành vi vi phạm quy định tại điểm c, điểm đ, điểm g, điểm h khoản 2; điểm a, điểm d, điểm đ, điểm e, điểm k khoản 3; điểm a, điểm b, điểm đ, điểm k khoản 4; điểm a khoản 5; điểm b khoản 6; điểm b khoản 7; điểm d khoản 8 Điều này;
```

#### 2.2.2 Pathologies of Naive Chunking
If a chunking engine splits this text by `Điểm`, the resulting isolated text payload is:
> *"a) Không chấp hành hiệu lệnh, chỉ dẫn của biển báo hiệu, vạch kẻ đường, trừ các hành vi vi phạm quy định tại điểm c, điểm đ, điểm g, điểm h khoản 2..."*

When embedded into dense vector space, this naive chunk suffers from catastrophic semantic deficits:
1. **Zero Subject Context**: The words *"xe mô tô"*, *"xe gắn máy"*, *"xe máy điện"* are completely absent (they exist solely in the Article 6 title). The embedding cannot distinguish this violation from an automobile violation under Article 5.
2. **Zero Penalty Context**: The monetary penalty range *"Phạt tiền từ 100.000 đồng đến 200.000 đồng"* is completely absent (it exists solely in the Clause 1 lead sentence).
3. **Zero Logical Operator**: The disjunctive logic operator *"thực hiện một trong các hành vi"* ($\bigvee$) is lost.
4. **Unresolved Exception Reference**: The point contains an explicit exclusion clause (*"trừ các hành vi quy định tại..."*) pointing to 17 other sub-clauses within Article 6. Without resolving these cross-references, an agent will misclassify high-severity violations (e.g., speeding, wrong lane) under this generic 100k–200k penalty bucket.

#### 2.2.3 Supplementary Sanction Decoupling (Hình thức xử phạt bổ sung)
In Vietnamese penalty decrees, supplementary sanctions (such as driver's license suspension — *Tước quyền sử dụng Giấy phép lái xe* or vehicle impoundment — *Tịch thu phương tiện*) are not co-located with the violation behavior point. Instead, they are aggregated in a dedicated closing clause of the Article (e.g., Clause 10 or Clause 11 of Article 5/6/7).

```
%%{init: {"flowchart": {"defaultRenderer": "elk"}}}%%
flowchart LR
    subgraph ART6["ĐIỀU 6 NGHỊ ĐỊNH 100/2019/NĐ-CP (Xử phạt xe máy)"]
        direction TB
        CL8["Khoản 8 Điểm a (Hành vi & Phạt chính)<br/>• Hành vi: Đi ngược chiều trên đường một chiều<br/>• Phạt tiền: 1.000.000đ - 2.000.000đ"]
        CL10["Khoản 10 Điểm c (Xử phạt bổ sung)<br/>• Quy định tước GPLX áp dụng cho Điểm a Khoản 8:<br/>• Thời hạn tước: Từ 02 tháng đến 04 tháng"]
    end
    
    Q["Truy vấn người dùng:<br/>'Đi xe máy ngược chiều bị phạt bao nhiêu tiền và có bị tước bằng không?'"]
    Q -->|"Bắt buộc kết hợp đồng thời"| CL8
    Q -->|"Bắt buộc kết hợp đồng thời"| CL10
    CL8 -.->|"Được dẫn chiếu chế tài bổ sung bởi"| CL10
```

---

### 2.3 Canonical Fully Qualified Chunks (CFQC) Architecture
To resolve the Dangling Point problem permanently, every indexed chunk in the system must be constructed as a **Canonical Fully Qualified Chunk (CFQC)**. 

A CFQC is a self-contained, context-complete semantic unit that synthesizes the entire structural lineage, primary behavior, statutory lead text, penalty brackets, supplementary sanctions, point deductions, and cross-reference exception flags into a unified representation.

```
+==================================================================================================+
| CANONICAL FULLY QUALIFIED CHUNK (CFQC) STRUCTURE                                                 |
+==================================================================================================+
| [HIERARCHICAL PATH]:                                                                             |
| Nghị định 100/2019/NĐ-CP (Sửa đổi bởi NĐ 123/2021) > Chương II > Điều 6 (Xe mô tô, xe gắn máy)  |
| > Khoản 1 > Điểm a                                                                               |
|                                                                                                  |
| [TARGET SUBJECT / VEHICLE]:                                                                      |
| Xe mô tô, xe gắn máy, xe máy điện, các loại xe tương tự xe mô tô/xe gắn máy                      |
|                                                                                                  |
| [PRIMARY NORMATIVE BEHAVIOR]:                                                                    |
| Không chấp hành hiệu lệnh, chỉ dẫn của biển báo hiệu, vạch kẻ đường                              |
|                                                                                                  |
| [LEAD CLAUSE STATUTORY CONTEXT]:                                                                 |
| Phạt tiền từ 100.000 đồng đến 200.000 đồng đối với người điều khiển xe thực hiện một trong các    |
| hành vi vi phạm sau đây                                                                          |
|                                                                                                  |
| [SANCTION SUMMARY]:                                                                              |
| - Phạt tiền: 100.000 VNĐ – 200.000 VNĐ                                                           |
| - Xử phạt bổ sung: Không áp dụng                                                                 |
| - Điểm GPLX bị trừ (NĐ 168/2024 / Luật 2024): 0 điểm                                             |
|                                                                                                  |
| [EXCLUSION OVERRIDES & EXCEPTIONS]:                                                              |
| Ngoại lệ: Không áp dụng nếu hành vi vi phạm thuộc các trường hợp quy định tại:                   |
| Điều 6.2.c, 6.2.đ, 6.2.g, 6.2.h, 6.3.a, 6.3.d, 6.3.đ, 6.3.e, 6.3.k, 6.4.a, 6.4.b, 6.4.đ,       |
| 6.4.k, 6.5.a, 6.6.b, 6.7.b, 6.8.d (Ưu tiên áp dụng điều khoản riêng biệt - Lex Specialis).     |
+==================================================================================================+
```

---

### 2.4 AST Representation & Context Enrichment Pipeline
During data ingestion, raw legislative Markdown/HTML documents are parsed into an Abstract Syntax Tree (AST). The AST parser navigates the 6-tier hierarchy, extracts structural nodes, binds lead sentences, resolves intra-article cross-references, and emits normalized CFQCs.

```
%%{init: {"flowchart": {"defaultRenderer": "elk"}}}%%
flowchart LR
    RAW["Raw Statutory Text<br/>(Luật, Nghị định, QCVN)"]
    AST_P["Legal AST Parser<br/>(6-Tier Structural Tokenizer)"]
    CTX_E["Context Enrichment Engine<br/>(Lead Clause Binding + Target Vehicle Injection)"]
    SANCT_L["Supplementary Sanction Linker<br/>(Clause 10/11 Cross-Article Linker)"]
    CFQC_OUT["Canonical Fully Qualified Chunk (CFQC)<br/>& Structured Vector + JSONB Metadata"]

    RAW --> AST_P --> CTX_E --> SANCT_L --> CFQC_OUT
```

---

## 3. Physically Decoupled Normative Triad

### 3.1 Jurisprudential Triad Theory: Giả định – Quy định – Chế tài
In formal jurisprudential doctrine (*Lý luận chung về Nhà nước và Pháp luật*), every complete legal norm ($\mathcal{N}$) is structured as a tripartite proposition:

$$\mathcal{N} = \langle \text{Giả định } (\mathcal{H}), \text{ Quy định } (\mathcal{P}), \text{ Chế tài } (\mathcal{S}) \rangle$$

1. **Giả định (Hypothesis / Condition - $\mathcal{H}$)**: Defines the legal subject, temporal window, spatial boundaries, and technical environmental preconditions under which the rule activates (*Who? Where? Under what technical conditions?*).
2. **Quy định (Prescription / Duty / Prohibition - $\mathcal{P}$)**: Defines the required conduct, statutory prohibition, or legal permission (*What must / must not / may the subject do?*).
3. **Chế tài (Sanction / Consequence - $\mathcal{S}$)**: Defines the coercive legal consequence, fine bracket, license deprivation, or administrative penalty imposed if the subject breaches $\mathcal{P}$ under condition $\mathcal{H}$.

---

### 3.2 Cross-Instrument Tripartite Decoupling Matrix
In Vietnamese road traffic governance, these three constituent components are **physically decoupled across distinct legislative tiers**:

```
%%{init: {"flowchart": {"defaultRenderer": "elk"}}}%%
flowchart LR
    subgraph DECOUPLED_TRIAD["TAM ĐOÀN QUY PHẠM PHÁP LÝ PHÂN TÁCH VẬT LÝ"]
        direction TB
        H["1. GIẢ ĐỊNH & THÔNG SỐ KỸ THUẬT (Hypothesis - H)<br/>• QCVN 41:2019/BGTVT: Nhận diện biển P.102, vạch 1.1, tín hiệu đèn vàng<br/>• Thông tư 31/2019/TT-BGTVT: Quy chuẩn tốc độ tối đa theo cung đường"]
        P["2. QUY ĐỊNH & LỆNH CẤM HÀNH VI (Prescription - P)<br/>• Luật GTĐB 2008 (Điều 9, 10, 11, 12): Nghĩa vụ chấp hành biển báo, vạch kẻ, quy tắc làn<br/>• Luật TTATGTĐB 2024 (Điều 10, 11, 12, 13): Cấm tuyệt đối nồng độ cồn, bảo vệ trẻ em"]
        S["3. CHẾ TÀI & HÌNH PHẠT HÀNH CHÍNH (Sanction - S)<br/>• Nghị định 100/2019 & NĐ 123/2021: Khung tiền phạt, tước GPLX, tạm giữ xe<br/>• Nghị định 168/2024/NĐ-CP: Cơ chế trừ điểm GPLX (12 điểm/năm)"]
    end

    H -->|"Kích hoạt điều kiện cấu thành"| P
    P -->|"Xác lập hành vi bị trừng phạt bởi"| S
```

#### Systematic Mapping Table across Legislative Instruments:

| Legislative Tier | Instrument Name | Competent Authority | Primary Norm Component | Concrete Traffic Example |
| :--- | :--- | :--- | :--- | :--- |
| **Quy chuẩn Kỹ thuật (QCVN)** | QCVN 41:2019/BGTVT | Bộ Giao thông Vận tải | **Giả định ($\mathcal{H}$)**: Technical definitions, signal dimensions, line marking semantics, optical parameters. | *Article 10.3*: Amber signal requires vehicles to stop before the stop line, unless the vehicle has already crossed the line. *Sign P.102*: "No Entry" dimensions, retroreflection, and placement geometry. |
| **Luật Cơ bản (Statutes)** | • Luật GTĐB 2008 (Luật 23)<br/>• Luật TTATGTĐB 2024 (Luật 36)<br/>• Luật Đường bộ 2024 (Luật 35) | Quốc hội | **Quy định ($\mathcal{P}$)**: Behavioral duties, statutory prohibitions, emergency vehicle rights, general rules of the road. | *Article 9 Clause 1 Law 2008 / Article 10 Law 2024*: Drivers must travel on the right-hand side, maintain lane discipline, and obey traffic signals. *Article 8*: Absolute prohibition of driving with alcohol in blood/breath. |
| **Nghị định Xử phạt (Decrees)** | • Nghị định 100/2019/NĐ-CP<br/>• Nghị định 123/2021/NĐ-CP<br/>• Nghị định 168/2024/NĐ-CP | Chính phủ | **Chế tài ($\mathcal{S}$)**: Administrative fine brackets, driving license suspension, vehicle confiscation, license point deductions. | *Article 5 Clause 3 Point a NĐ 100*: Fine of 800.000đ – 1.000.000đ for failing to obey traffic signals. *Article 5 Clause 11 Point b*: License suspension of 1–3 months. *NĐ 168/2024*: Deduction of 2 license points. |
| **Thông tư Hướng dẫn (Circulars)** | • Thông tư 31/2019/TT-BGTVT<br/>• Thông tư 24/2023/TT-BCA<br/>• Thông tư 28/2024/TT-BCA | Bộ trưởng Bộ GTVT / Bộ Công an | **Giả định Chi tiết & Thủ tục ($\mathcal{H}_{\text{proc}}$)**: Speed thresholds by road type, digital license validation via VNeID. | *Article 6, 7 TT 31/2019*: Speed limit of 50 km/h on two-way roads without median in populated areas; 60 km/h on divided roads. |

---

### 3.3 Multi-Hop Statutory Traversal Walkthroughs

#### 3.3.1 Speeding in Non-Divided Urban Corridor
*Scenario*: A driver operates a 5-seat passenger car (`CAR_PASSENGER`) at $68\text{ km/h}$ on a two-way street without a central median strip located inside a densely populated area (*khu vực đông dân cư*). What are the exact violations, monetary penalties, license suspension periods, and point deductions?

```
%%{init: {"flowchart": {"defaultRenderer": "elk"}}}%%
flowchart TD
    Q["User Query: Car at 68 km/h in urban area (2-way road, no median)"]
    
    H1["HOP 1: Tra cứu Giới hạn Tốc độ Kỹ thuật<br/>[Thông tư 31/2019/TT-BGTVT - Điều 6 Khoản 1]<br/>• Khu vực đông dân cư, đường 2 chiều không có dải phân cách giữa<br/>• Tốc độ tối đa cho phép v_max = 50 km/h"]
    
    CALC["TÍNH TOÁN ĐỘ VƯỢT TỐC ĐỘ (Speed Delta):<br/>Δv = 68 km/h - 50 km/h = 18 km/h<br/>→ Thuộc khung: Chạy quá tốc độ từ 10 km/h đến 20 km/h"]
    
    H2["HOP 2: Xác định Nghĩa vụ Hành vi Cơ bản<br/>[Luật GTĐB 2008 - Điều 12 / Luật 36/2024 - Điều 12]<br/>• Người lái xe phải tuân thủ quy định về tốc độ xe chạy trên đường"]
    
    H3["HOP 3: Tra cứu Khung Phạt Tiền & Tước GPLX<br/>[Nghị định 100/2019/NĐ-CP - Điều 5 (Sửa đổi bởi NĐ 123/2021)]<br/>• Khoản 5 Điểm i: Phạt tiền từ 4.000.000 đồng đến 6.000.000 đồng<br/>• Khoản 11 Điểm b: Tước quyền sử dụng GPLX từ 01 tháng đến 03 tháng"]
    
    H4["HOP 4: Tra cứu Cơ chế Trừ điểm GPLX (Áp dụng từ 2025)<br/>[Nghị định 168/2024/NĐ-CP / Luật 36/2024/QH15]<br/>• Trừ 02 điểm trên Giấy phép lái xe"]
    
    Q --> H1 --> CALC --> H2 --> H3 --> H4
```

*Deterministic Multi-Hop Proof Trace*:
1. **Hop 1 (Circular / Technical Trigger $\mathcal{H}$)**: Match TT 31/2019/TT-BGTVT Art 6.1 $\implies v_{\max} = 50\text{ km/h}$.
2. **Mathematical Evaluation**: $\Delta v = 68 - 50 = 18\text{ km/h} \in [10, 20]\text{ km/h}$.
3. **Hop 2 (Statute / Duty $\mathcal{P}$)**: Match Law 2008 Art 12 / Law 2024 Art 12 $\implies$ Breach of statutory speed limit duty.
4. **Hop 3 (Decree / Administrative Sanction $\mathcal{S}_{\text{fine}} + \mathcal{S}_{\text{suspension}}$)**:
   - Primary Fine: Decree 100/2019 Art 5.5.i $\implies 4.000.000\text{đ} - 6.000.000\text{đ}$.
   - Supplementary Sanction: Decree 100/2019 Art 5.11.b $\implies$ License suspension from 1 to 3 months.
5. **Hop 4 (Decree 168/2024 / Point Deduction $\mathcal{S}_{\text{points}}$)**: Under 2025+ validity window $\implies$ Deduct 2 points from the 12-point driver license pool.

---

#### 3.3.2 Red Light vs CSGT Manual Overrides
*Scenario*: An automobile approaches an intersection where the traffic light is solid Red (`RED_LIGHT`), but a Traffic Police Officer (`CSGT`) stationed at the center of the junction gestures forward, signaling vehicles to proceed. If the driver proceeds through the red light, does this constitute a violation?

*Deterministic Reasoning Chain*:
1. **Signal State Formulation**: $S = \langle s_{\text{csgt}} = \text{"GO"}, s_{\text{light}} = \text{"RED"}, s_{\text{sign}} = \emptyset, s_{\text{mark}} = \emptyset \rangle$.
2. **Statutory Hierarchy Lookup**: QCVN 41:2019/BGTVT Article 4.1 & Law 2008 Article 11.2 (Law 2024 Article 11.2) establish the strict precedence:
   $$\mathcal{H}_{\text{CSGT}} \succ \mathcal{H}_{\text{Light}} \succ \mathcal{H}_{\text{Sign}} \succ \mathcal{H}_{\text{Marking}}$$
3. **Precedence Resolution Algorithm**:
   $$\operatorname{ResolveSignal}(S) = \operatorname{Command}(s_{\text{csgt}}) = \text{"GO"}$$
4. **Legal Liability Evaluation**:
   - Primary Duty: Driver is statutorily obligated under Article 11.2 to obey the Traffic Police Officer.
   - Non-Violation Determination: $\text{IsViolation}(\text{Action} = \text{PROCEED}, S) = \text{FALSE}$.
   - Exclusion of Sanction: Decree 100/2019 Art 5.3.a (Red light fine) is nullified and rendered inapplicable by QCVN 41:2019 Article 4.

---

#### 3.3.3 Emergency Vehicle Privileges & Exclusion Clauses
*Scenario*: An ambulance (`PRIORITY_VEHICLE`) transporting a critical patient operates with flashing beacon lights and active siren, proceeding at $85\text{ km/h}$ through a red light on a $50\text{ km/h}$ street. Does this trigger speeding and red-light penalties?

*Deterministic Reasoning Chain*:
1. **Subject Categorization**: Vehicle classified under ontology as `PRIORITY_VEHICLE` (Xe cấp cứu đang thực hiện nhiệm vụ cấp cứu).
2. **Statutory Privilege Activation**: Law 2008 Article 22 Clause 2 (Law 2024 Article 20 Clause 2):
   $$\forall v \in \text{Vehicles}, \quad \text{IsPriorityActive}(v) \implies \operatorname{Exempt}(v, \{\text{RED\_LIGHT}, \text{ONE\_WAY}, \text{SPEED\_LIMIT}\})$$
3. **Exclusion Check**: Ambulance is exempt from speed restrictions and red light prohibitions, subject only to obeying the manual commands of Traffic Police ($\mathcal{H}_{\text{CSGT}}$).
4. **Conclusion**: Zero administrative fine, zero license suspension, zero point deduction.

---

#### 3.3.4 License Point Deduction Mechanics (12-Point System)
Under Law No. 36/2024/QH15 (effective 01/01/2025) and Decree No. 168/2024/NĐ-CP, Vietnam institutes a comprehensive 12-point driver license management regime:
- **Baseline Allocation**: Every issued driving license contains exactly **12 points** per 12-month rolling cycle.
- **Deduction Granularity**: Discrete violations incur statutory deductions of **2, 3, 4, 6, 8, 10, or 12 points**.
- **Total Depletion Consequence**: When points reach 0, the license is invalidated. The driver must pass a mandatory legal knowledge examination after a minimum statutory rehabilitation window (6 months) to restore points.
- **Annual Point Restoration**: If a driver commits no violations for 12 consecutive months from the date of the latest point deduction, the system automatically restores the full 12-point balance.

---

## 4. Shared Ontology & Controlled Vocabulary

To guarantee 100% mutual contract agreement between data ingestion and query planning, this section formalizes the shared ontology, taxonomic codes, norm roles, and graph edge types.

### 4.1 Controlled Vehicle Taxonomy (VehicleType)

```
%%{init: {"flowchart": {"defaultRenderer": "elk"}}}%%
flowchart TD
    VEH["Vehicle (Phương tiện tham gia GTĐB)"]
    
    MOTOR["Xe Cơ giới (Motor Vehicle)"]
    PRIMITIVE["Xe Thô sơ (Non-motorized / Primitive)"]
    SPECIAL["Xe Máy Chuyên dùng (Specialized Machinery)"]
    
    VEH --> MOTOR
    VEH --> PRIMITIVE
    VEH --> SPECIAL
    
    CAR["Xe Ô tô (Automobile)"]
    MOTO["Xe Mô tô (Motorcycle)"]
    MOPED["Xe Gắn máy (Moped / E-Moped)"]
    
    MOTOR --> CAR
    MOTOR --> MOTO
    MOTOR --> MOPED
    
    CAR_PASS["CAR_PASSENGER (<= 9 chỗ, Pickup < 950kg)"]
    CAR_TRK["CAR_TRUCK (Xe tải >= 950kg)"]
    CAR_BS["CAR_BUS (Xe khách >= 10 chỗ)"]
    CAR_TRAC["CAR_TRACTOR (Xe đầu kéo rơ-moóc)"]
    
    CAR --> CAR_PASS
    CAR --> CAR_TRK
    CAR --> CAR_BS
    CAR --> CAR_TRAC
    
    MOTO_2["MOTORCYCLE (>= 50cc / > 4kW, > 50km/h)"]
    MOPED_ALL["MOPED / E_MOPED (< 50cc / <= 4kW, <= 50km/h)"]
    
    MOTO --> MOTO_2
    MOPED --> MOPED_ALL
    
    E_BIKE["E_BICYCLE (Xe đạp điện <= 250W, <= 25km/h)"]
    BIKE["BICYCLE_PRIMITIVE (Xe đạp, xích lô, xe súc vật)"]
    
    PRIMITIVE --> E_BIKE
    PRIMITIVE --> BIKE
```

#### Controlled Vehicle Vocabulary Table:

| Taxonomy Enum Code | Vietnamese Legal Term | Quantitative & Structural Technical Criteria | Legal Source Definition |
| :--- | :--- | :--- | :--- |
| `CAR_PASSENGER` | Xe ô tô con | Passenger automobile $\le 9$ seats (including driver), or pickup truck with permissible payload $< 950\text{ kg}$. | QCVN 41:2019 Art 3.20 |
| `CAR_TRUCK` | Xe ô tô tải | Motor vehicle designed for cargo transport with permissible payload $\ge 950\text{ kg}$. | QCVN 41:2019 Art 3.25 |
| `CAR_BUS` | Xe ô tô khách | Passenger automobile with $\ge 10$ seats (including driver). | QCVN 41:2019 Art 3.22 |
| `CAR_TRACTOR` | Xe ô tô đầu kéo | Motor tractor designed to haul semi-trailers or full trailers. | QCVN 41:2019 Art 3.26 |
| `MOTORCYCLE` | Xe mô tô (xe máy) | Two- or three-wheeled motor vehicle with engine displacement $\ge 50\text{ cm}^3$ or electric motor $> 4\text{ kW}$, design speed $> 50\text{ km/h}$. | QCVN 41:2019 Art 3.39 |
| `MOPED` | Xe gắn máy (xăng) | Two- or three-wheeled vehicle with engine displacement $< 50\text{ cm}^3$, design speed $\le 50\text{ km/h}$. | QCVN 41:2019 Art 3.40 |
| `E_MOPED` | Xe máy điện | Moped powered by electric motor $\le 4\text{ kW}$, design speed $\le 50\text{ km/h}$. | QCVN 41:2019 Art 3.40 |
| `E_BICYCLE` | Xe đạp điện | Non-motorized category two-wheeled bicycle fitted with auxiliary electric motor $\le 250\text{ W}$, speed $\le 25\text{ km/h}$, equipped with operational pedals. | QCVN 41:2019 Art 3.43 |
| `BICYCLE_PRIMITIVE` | Xe thô sơ / Xe đạp | Primitive non-motorized vehicles: pedal bicycles, pedicabs (xích lô), wheelchairs, animal-drawn carts. | Law 2008 Art 3.19 |
| `SPECIALIZED_MACHINE` | Xe máy chuyên dùng | Construction machinery, agricultural/forestry tractors, specialized defense/security tracked or wheeled machinery. | Law 2008 Art 3.20 |
| `PRIORITY_VEHICLE` | Xe ưu tiên | Fire engines, military/police emergency convoys, ambulances on duty, disaster rescue convoys with active siren/light beacons. | Law 2008 Art 22 / Law 2024 Art 20 |

---

### 4.2 Exhaustive Violation Category Taxonomy (ViolationCategory & ViolationType)

The controlled ontology specifies 8 core violation categories and 36 granular violation types:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "VietnameseTrafficViolationTaxonomy",
  "type": "object",
  "properties": {
    "categories": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["category_code", "name_vi", "types"],
        "properties": {
          "category_code": {
            "type": "string",
            "enum": [
              "ALCOHOL_DRUGS",
              "SPEED_DISTANCE",
              "LANE_DIRECTION",
              "SIGNAL_COMPLIANCE",
              "STOP_PARK",
              "EQUIPMENT_SAFETY",
              "LOAD_PASSENGER",
              "DOCUMENTATION_VNEID"
            ]
          },
          "name_vi": { "type": "string" },
          "types": {
            "type": "array",
            "items": {
              "type": "object",
              "required": ["type_code", "name_vi", "quantitative_threshold"],
              "properties": {
                "type_code": { "type": "string" },
                "name_vi": { "type": "string" },
                "quantitative_threshold": { "type": "string" }
              }
            }
          }
        }
      }
    }
  }
}
```

#### Detailed Taxonomy Mapping Table:

| Category Code | Type Code (`enum`) | Vietnamese Violation Name | Statutory Quantitative Bracket / Threshold |
| :--- | :--- | :--- | :--- |
| **`ALCOHOL_DRUGS`** | `ALC_BRACKET_1` | Nồng độ cồn mức 1 | $\le 50\text{ mg}/100\text{ ml}$ blood or $\le 0.25\text{ mg}/1\text{ L}$ breath. |
| | `ALC_BRACKET_2` | Nồng độ cồn mức 2 | $> 50 - 80\text{ mg}/100\text{ ml}$ blood or $> 0.25 - 0.40\text{ mg}/1\text{ L}$ breath. |
| | `ALC_BRACKET_3` | Nồng độ cồn mức 3 | $> 80\text{ mg}/100\text{ ml}$ blood or $> 0.40\text{ mg}/1\text{ L}$ breath / Refusal to test. |
| | `DRUG_POSITIVE` | Điều khiển xe có chất ma túy | Positive chemical detection of narcotics in bodily fluids. |
| **`SPEED_DISTANCE`** | `SPEED_OVER_5_10` | Chạy quá tốc độ từ 5 đến dưới 10 km/h | $5\text{ km/h} \le \Delta v < 10\text{ km/h}$. |
| | `SPEED_OVER_10_20` | Chạy quá tốc độ từ 10 đến 20 km/h | $10\text{ km/h} \le \Delta v \le 20\text{ km/h}$. |
| | `SPEED_OVER_20_35` | Chạy quá tốc độ từ 20 đến 35 km/h | $20\text{ km/h} < \Delta v \le 35\text{ km/h}$. |
| | `SPEED_OVER_35_PLUS` | Chạy quá tốc độ trên 35 km/h | $\Delta v > 35\text{ km/h}$. |
| | `SPEED_UNDER_MIN` | Chạy dưới tốc độ tối thiểu | $v < v_{\min}$ on designated expressways/arterials. |
| | `DISTANCE_UNSAFE` | Không giữ khoảng cách an toàn | Breach of statutory headway distance (TT 31/2019 Art 11). |
| **`LANE_DIRECTION`** | `WRONG_LANE` | Đi không đúng làn đường (Sai làn) | Driving in lane designated for other vehicle classes (Biển R.412/R.415). |
| | `WRONG_ROAD_PORTION` | Đi không đúng phần đường quy định | Crossing solid center lines / Driving on sidewalk or shoulder. |
| | `OPPOSITE_DIRECTION` | Đi ngược chiều trên đường 1 chiều | Traveling against flow on one-way road or sign P.102. |
| | `HIGHWAY_REVERSE` | Lùi xe, quay đầu, đi ngược chiều cao tốc | Traveling in reverse or wrong way on designated expressway. |
| | `TURN_NO_SIGNAL` | Chuyển hướng không có tín hiệu (Không xi nhan) | Turning at intersection without direction indicator signal. |
| | `LANE_CHANGE_NO_SIGNAL` | Chuyển làn không có tín hiệu báo trước | Changing lanes without directional indicator signal. |
| **`SIGNAL_COMPLIANCE`** | `RED_LIGHT` | Không chấp hành hiệu lệnh đèn đỏ | Crossing stop line when traffic light signal is Red. |
| | `AMBER_LIGHT` | Không chấp hành hiệu lệnh đèn vàng | Failing to stop before stop line on Amber (unless already crossed). |
| | `POLICE_COMMAND` | Không chấp hành hiệu lệnh CSGT | Failing to obey manual commands of Traffic Police. |
| | `SIGN_MARKING` | Không chấp hành biển báo, vạch kẻ | Disregarding regulatory signs (P/W series) or pavement lines. |
| | `PROHIBITED_ZONE` | Đi vào đường cấm, khu vực cấm | Entering roads with vehicle-specific prohibition signs. |
| **`STOP_PARK`** | `ILLEGAL_STOP_PARK` | Dừng xe, đỗ xe trái quy định | Stopping/parking where sign P.130/P.131 is posted or unsafe locations. |
| | `HIGHWAY_STOP_PARK` | Dừng, đỗ xe trên cao tốc trái phép | Stopping/parking on expressway outside designated emergency bays. |
| | `BRIDGE_TUNNEL_STOP` | Dừng, đỗ trên cầu, hầm đường bộ | Stopping/parking inside tunnels, on bridge decks, or pedestrian crossings. |
| **`EQUIPMENT_SAFETY`** | `HELMET_VIOLATION` | Không đội mũ bảo hiểm / Không cài quai | Operating/riding motorcycle without certified helmet correctly fastened. |
| | `SEATBELT_VIOLATION` | Không thắt dây an toàn | Driver or passengers in equipped seats failing to fasten seatbelts. |
| | `PHONE_HANDHELD` | Dùng tay sử dụng điện thoại | Manually holding/operating smartphone while operating vehicle. |
| | `HEADLIGHT_NIGHT` | Không bật đèn chiếu sáng 19h - 5h | Operating vehicle without low-beam headlights between 19h and 05h. |
| | `HIGHBEAM_URBAN` | Sử dụng đèn chiếu xa trong đô thị | Operating high-beam headlights in urban/populated residential areas. |
| **`LOAD_PASSENGER`** | `OVERLOAD_VEHICLE` | Chở hàng vượt quá tải trọng thiết kế | Exceeding certified vehicle payload $> 10\%, > 20\%, > 50\%$. |
| | `OVERLOAD_INFRA` | Vượt quá tải trọng cầu, đường | Exceeding bridge/road permissible gross vehicle weight. |
| | `OVER_PASSENGER` | Chở quá số người quy định | Carrying passengers exceeding licensed seating capacity by $> 1, > 2$. |
| **`DOCUMENTATION_VNEID`** | `NO_LICENSE` | Không có Giấy phép lái xe | Operating without valid license / unsuited class / revoked. |
| | `EXPIRED_LICENSE` | Giấy phép lái xe hết hạn | License expired $< 3\text{ months}$ or $\ge 3\text{ months}$. |
| | `NO_REGISTRATION` | Không có Giấy đăng ký xe | Operating vehicle without certified vehicle registration certificate. |
| | `NO_INSPECTION` | Không có Tem kiểm định an toàn | Vehicle lacking valid technical safety & emissions inspection certificate. |
| | `NO_CIVIL_INSURANCE` | Không có Bảo hiểm TNDS bắt buộc | Lacking mandatory civil liability insurance certificate. |
| | `VNEID_INTEGRATION` | Kiểm tra giấy tờ qua VNeID | Presenting and validating digital credentials via level 2 VNeID account. |

---

### 4.3 Norm Roles & Functional Classification (NormRole)

Each decomposed legal chunk or relational node is tagged with exactly one functional normative role (`NormRole`):

```json
{
  "norm_roles": [
    {
      "role_code": "HYPOTHESIS_CONDITION",
      "description": "Defines the subject, physical conditions, spatial boundaries, and technical preconditions (Giả định)."
    },
    {
      "role_code": "PRESCRIPTION_MANDATORY",
      "description": "Statutory positive mandate: what the subject MUST perform (Nghĩa vụ, bổn phận)."
    },
    {
      "role_code": "PRESCRIPTION_PROHIBITION",
      "description": "Statutory negative mandate: what the subject is STRICTLY FORBIDDEN from performing (Lệnh cấm)."
    },
    {
      "role_code": "PRESCRIPTION_PERMISSION",
      "description": "Statutory legal privilege, exemption, or permitted discretion (Quyền hạn, trường hợp cho phép)."
    },
    {
      "role_code": "SANCTION_PRINCIPAL",
      "description": "Primary administrative penalty: monetary fine bracket or warning (Phạt tiền, Phạt cảnh cáo)."
    },
    {
      "role_code": "SANCTION_SUPPLEMENTARY",
      "description": "Supplementary penalty: driver license suspension, vehicle confiscation (Tước GPLX, Tịch thu phương tiện)."
    },
    {
      "role_code": "SANCTION_POINT_DEDUCTION",
      "description": "Statutory deduction of driving license points: 2, 3, 4, 6, 8, 10, or 12 points (Trừ điểm GPLX)."
    },
    {
      "role_code": "REMEDIAL_MEASURE",
      "description": "Mandatory corrective restitution: forced cargo unloading, dismantling illegal modifications (Biện pháp khắc phục hậu quả)."
    }
  ]
}
```

---

### 4.4 Graph Edge Relations & Directionality Constraints (GraphRelationType)

The knowledge graph $G = (V, E)$ defines 9 typed, directed relations governing statutory interaction across the normative triad:

| Edge Relation Code (`enum`) | Source Node Type ($u$) $\longrightarrow$ Target Node Type ($v$) | Legal & Semantic Definition | Algorithmic Traversal Invariant |
| :--- | :--- | :--- | :--- |
| `DEFINES_SANCTION_FOR` | Decree / Circular $\longrightarrow$ Law | Executive instrument details, implements, or provides fine schedules for a statutory duty. | Traverse downstream from Law to Decree to locate fine schedules; traverse upstream from Decree to Law for legal foundation. |
| `HAS_ADDITIONAL_SANCTION` | Primary Sanction Node ($\mathcal{S}$) $\longrightarrow$ Supplementary Sanction Node | Links a primary administrative penalty clause to supplementary penalties (license suspension, impoundment, point deduction). | Mandatory hop when synthesizing complete legal consequences for a user query. |
| `REFERENCES_TECHNICAL_STANDARD` | Decree / Law $\longrightarrow$ QCVN Standard Node | Binds a statutory offense to physical sign codes, line markings, or technical specifications. | Mandatory hop to resolve geometric, color, or speed thresholds. |
| `MODIFIES_AND_REPLACES` | Amending Instrument $\longrightarrow$ Base Instrument | Modifies, replaces, or amends specific words, phrases, clauses, or articles of a prior enactment. | Apply diff transformation logic to generate consolidated view at $t_{\text{query}}$. |
| `REPEALS` | New Enactment $\longrightarrow$ Old Enactment | Completely repeals and substitutes an entire legal instrument or specific provision. | Enforce temporal boundary: verify target is inactive if $t_{\text{query}} \ge t_{\text{effective}}(u)$. |
| `OVERRIDES_PRIORITY` | Higher Priority Node $\longrightarrow$ Lower Priority Node | Encodes hierarchical signal precedence ($\text{CSGT} \succ \text{Light} \succ \text{Sign} \succ \text{Mark}$) or Lex Specialis. | Query engine nullifies lower-priority node constraints when higher-priority conditions hold. |
| `EXEMPTS_CONDITION` | General Rule Node $\longrightarrow$ Specific Exception Node | Establishes an explicit statutory exclusion (*"Trừ các trường hợp...", "Trừ xe ưu tiên..."*). | Query engine must evaluate exception conditions before asserting a violation. |
| `GUIDES` | Circular $\longrightarrow$ Decree / Law | Ministerial circular providing detailed technical or procedural implementation instructions. | Graph expansion hop to gather implementation guidance into context window. |
| `DEFINES_TERM` | Statutory Definition $\longrightarrow$ Ontology Concept Node | Establishes the authoritative statutory definition of a technical term or vehicle category. | Used by query planner for synonym expansion and term disambiguation. |

---

### 4.5 Formal JSON Schema Specifications

#### 4.5.1 Schema for Canonical Fully Qualified Chunk (CFQC)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "CanonicalFullyQualifiedChunk",
  "type": "object",
  "required": [
    "chunk_id",
    "document_id",
    "lineage",
    "vehicle_types",
    "violation_types",
    "norm_role",
    "canonical_text",
    "temporal_window"
  ],
  "properties": {
    "chunk_id": {
      "type": "string",
      "pattern": "^chunk::[a-z0-9_-]+::art::[0-9]+::cl::[0-9]+(::pt::[a-z])?$"
    },
    "document_id": { "type": "string" },
    "lineage": {
      "type": "object",
      "required": ["chapter", "article", "clause"],
      "properties": {
        "chapter": { "type": "string" },
        "section": { "type": ["string", "null"] },
        "article": { "type": "string" },
        "clause": { "type": "string" },
        "point": { "type": ["string", "null"] }
      }
    },
    "vehicle_types": {
      "type": "array",
      "items": { "type": "string" }
    },
    "violation_types": {
      "type": "array",
      "items": { "type": "string" }
    },
    "norm_role": { "type": "string" },
    "lead_sentence": { "type": ["string", "null"] },
    "raw_text": { "type": "string" },
    "canonical_text": { "type": "string" },
    "sanctions": {
      "type": "object",
      "properties": {
        "fine_min_vnd": { "type": ["integer", "null"] },
        "fine_max_vnd": { "type": ["integer", "null"] },
        "license_suspension_min_months": { "type": ["integer", "null"] },
        "license_suspension_max_months": { "type": ["integer", "null"] },
        "points_deducted": { "type": ["integer", "null"] },
        "vehicle_impoundment_days": { "type": ["integer", "null"] }
      }
    },
    "exception_refs": {
      "type": "array",
      "items": { "type": "string" }
    },
    "temporal_window": {
      "type": "object",
      "required": ["effective_date"],
      "properties": {
        "effective_date": { "type": "string", "format": "date" },
        "expiry_date": { "type": ["string", "null"], "format": "date" }
      }
    }
  }
}
```

---

## 5. Formal Mathematical & Knowledge Graph Modeling

### 5.1 Directed Attributed Property Graph Definition: G = (V, E)
The legal domain knowledge base is modeled as a formal Directed Attributed Property Graph:

$$G = (V, E, \Phi_V, \Phi_E)$$

```
%%{init: {"flowchart": {"defaultRenderer": "elk"}}}%%
flowchart TB
    subgraph GRAPH_SPACE["KHÔNG GIAN ĐỒ THỊ TRI THỨC PHÁP LÝ G = (V, E)"]
        direction TB
        subgraph VERTICES["TẬP ĐỈNH (Vertex Set V)"]
            V_DOC["V_doc: Đỉnh Văn bản (Luật, Nghị định, QCVN)"]
            V_STR["V_struct: Đỉnh Cấu trúc (Chương, Điều, Khoản, Điểm)"]
            V_NORM["V_norm: Đỉnh Quy phạm (Giả định H, Quy định P, Chế tài S)"]
            V_CON["V_concept: Đỉnh Bản thể luận (Loại xe, Nhóm vi phạm)"]
            V_TECH["V_tech: Đỉnh Kỹ thuật (Mã biển P.102, Vạch kẻ 1.1)"]
        end
        
        subgraph EDGES["TẬP CẠNH (Edge Set E)"]
            E_SPEC["DEFINES_SANCTION_FOR (Decree -> Law)"]
            E_SANCT["HAS_ADDITIONAL_SANCTION (Sanction -> Extra Sanction)"]
            E_TECH["REFERENCES_TECHNICAL_STANDARD (Decree/Law -> QCVN)"]
            E_AMEND["MODIFIES_AND_REPLACES (ND123 -> ND100)"]
            E_REP["REPEALS (ND168 -> ND100)"]
            E_OVER["OVERRIDES_PRIORITY (CSGT > Light > Sign > Mark)"]
            E_EXCP["EXEMPTS_CONDITION (Rule -> Exception)"]
            E_GUIDE["GUIDES (Circular -> Decree)"]
            E_TERM["DEFINES_TERM (Art 3 -> Concept)"]
        end
    end
    
    V_DOC --> V_STR --> V_NORM
    V_NORM --> V_CON
    V_NORM --> V_TECH
```

#### 1. Vertex Set Decomposition ($V$):
$$V = V_{\text{doc}} \cup V_{\text{struct}} \cup V_{\text{norm}} \cup V_{\text{concept}} \cup V_{\text{tech}}$$

- **$V_{\text{doc}}$ (Legal Document Nodes)**: $v = \langle \text{doc\_id}, \text{type}, \text{number}, \text{promulgation\_date}, \text{effective\_date}, \text{expiry\_date}, \text{status} \rangle$
- **$V_{\text{struct}}$ (Structural AST Nodes)**: $v = \langle \text{struct\_id}, \text{level}, \text{raw\_text}, \text{lead\_clause\_id}, \text{lineage\_path} \rangle$
- **$V_{\text{norm}}$ (Normative Triad Nodes)**: $v = \langle \text{norm\_id}, \text{role}, \text{subject\_types}, \text{action\_code}, \text{fine\_min}, \text{fine\_max}, \text{suspension\_range}, \text{points} \rangle$
- **$V_{\text{concept}}$ (Ontology Concept Nodes)**: $v = \langle \text{concept\_code}, \text{standard\_term\_vi}, \text{synonyms\_list}, \text{parent\_concept} \rangle$
- **$V_{\text{tech}}$ (Technical Specification Nodes)**: $v = \langle \text{tech\_code}, \text{sign\_group}, \text{geometry}, \text{retroreflection}, \text{meaning\_vi} \rangle$

#### 2. Edge Set Formulation ($E$):
$$E \subseteq V \times V \times \mathcal{T}_E \times \mathcal{W}_E$$

Where $\mathcal{T}_E = \{\text{DEFINES\_SANCTION\_FOR}, \text{HAS\_ADDITIONAL\_SANCTION}, \text{REFERENCES\_TECHNICAL\_STANDARD}, \text{MODIFIES\_AND\_REPLACES}, \text{REPEALS}, \text{OVERRIDES\_PRIORITY}, \text{EXEMPTS\_CONDITION}, \text{GUIDES}, \text{DEFINES\_TERM}\}$ and $\mathcal{W}_E$ encapsulates dynamic edge properties (e.g., temporal validity interval $\mathcal{I}_e = [t_{\text{start}}, t_{\text{end}})$).

---

### 5.2 Operational Signal Precedence Algebra

Under QCVN 41:2019/BGTVT Article 4 and Law 2008 Article 11 (Law 2024 Article 11), traffic signals present at the same junction establish a **Strict Partial Order $(\mathcal{S}, \succ)$**:

$$\mathcal{H}_{\text{CSGT}} \succ \mathcal{H}_{\text{Light}} \succ \mathcal{H}_{\text{Sign\_Temp}} \succ \mathcal{H}_{\text{Sign\_Fixed}} \succ \mathcal{H}_{\text{Marking}}$$

```
%%{init: {"flowchart": {"defaultRenderer": "elk"}}}%%
flowchart TD
    IN["Trạng thái Tín hiệu Đầu vào: S = ⟨s_csgt, s_light, s_sign, s_mark⟩"]
    
    Q1{"Có Hiệu lệnh CSGT / Người ĐKGT?<br/>(s_csgt != ∅)"}
    ACT1["TUÂN THỦ HIỆU LỆNH CSGT<br/>Action = Command(s_csgt)<br/>(Phủ quyết hoàn toàn Đèn, Biển, Vạch)"]
    
    Q2{"Có Đèn Tín hiệu Giao thông?<br/>(s_light != ∅)"}
    ACT2["TUÂN THỦ ĐÈN TÍN HIỆU<br/>Action = Command(s_light)<br/>(Phủ quyết Biển báo & Vạch kẻ)"]
    
    Q3{"Có Biển Báo hiệu Đường bộ?<br/>(s_sign != ∅)"}
    ACT3["TUÂN THỦ BIỂN BÁO HIỆU<br/>Action = Command(s_sign)<br/>(Biển tạm thời > Biển cố định > Vạch)"]
    
    ACT4["TUÂN THỦ VẠCH KẺ ĐƯỜNG<br/>Action = Command(s_mark)"]
    
    IN --> Q1
    Q1 -- "ĐÚNG (Có hiệu lệnh)" --> ACT1
    Q1 -- "SAI (null)" --> Q2
    Q2 -- "ĐÚNG (Có đèn)" --> ACT2
    Q2 -- "SAI (null)" --> Q3
    Q3 -- "ĐÚNG (Có biển)" --> ACT3
    Q3 -- "SAI (null)" --> ACT4
```

#### Deterministic Signal Resolution Function:
$$\text{Action}_{\text{valid}} = \operatorname{ResolveSignal}(S) = \begin{cases}
\operatorname{Command}(s_{\text{csgt}}), & \text{if } s_{\text{csgt}} \neq \emptyset \\
\operatorname{Command}(s_{\text{light}}), & \text{if } s_{\text{csgt}} = \emptyset \land s_{\text{light}} \neq \emptyset \\
\operatorname{Command}(s_{\text{sign\_temp}}), & \text{if } s_{\text{csgt}} = s_{\text{light}} = \emptyset \land s_{\text{sign\_temp}} \neq \emptyset \\
\operatorname{Command}(s_{\text{sign\_fixed}}), & \text{if } s_{\text{csgt}} = s_{\text{light}} = s_{\text{sign\_temp}} = \emptyset \land s_{\text{sign\_fixed}} \neq \emptyset \\
\operatorname{Command}(s_{\text{mark}}), & \text{if } s_{\text{csgt}} = s_{\text{light}} = s_{\text{sign}} = \emptyset \land s_{\text{mark}} \neq \emptyset
\end{cases}$$

#### Conflict Resolution Truth Table:

| Officer Command ($s_{\text{csgt}}$) | Light Signal ($s_{\text{light}}$) | Road Sign ($s_{\text{sign}}$) | Pavement Mark ($s_{\text{mark}}$) | Legally Binding Duty ($\text{Action}_{\text{valid}}$) | Nullified Elements | Legal Exemption Justification |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **PROCEED (Đi)** | **RED (Đỏ)** | STOP (P.122) | Solid Stop Line | **PROCEED (Đi)** | Light, Sign, Marking | QCVN 41:2019 Art 4.1 & Law 2008 Art 11.2 |
| **STOP (Dừng)** | **GREEN (Xanh)** | — | Broken Line | **STOP (Dừng)** | Light | QCVN 41:2019 Art 4.1 & Law 2008 Art 11.2 |
| $\emptyset$ | **GREEN (Xanh)** | NO_RIGHT_TURN (P.103c) | Right-Turn Arrow | **OBEY LIGHT / TURN** | Road Sign | QCVN 41:2019 Art 4.2 |
| $\emptyset$ | $\emptyset$ | **TEMP_SPEED_40** | FIXED_SPEED_60 | **MAX 40 km/h** | Fixed Road Sign | QCVN 41:2019 Art 4.3 |
| $\emptyset$ | $\emptyset$ | **NO_LEFT_TURN** | Straight/Left Mark | **NO LEFT TURN** | Pavement Marking | QCVN 41:2019 Art 4.4 |

---

### 5.3 Jurisprudential Scope Overrides & Exception Logic

The reasoning engine applies three formal Roman/Civil Law canons of statutory interpretation:

1. **Lex Superior Derogat Legi Inferiori** (Higher norm overrides lower norm):
   $$\text{Level}(\text{Constitution}) > \text{Level}(\text{Statute/Luật}) > \text{Level}(\text{Decree/Nghị định}) > \text{Level}(\text{Circular/Thông tư})$$
   A governmental decree cannot establish criminal offenses or contradict statutory rights defined in parliamentary statutes.

2. **Lex Specialis Derogat Legi Generali** (Specific norm overrides general norm):
   When a generic behavioral prohibition and a specific operational rule conflict, the specific rule governs:
   $$\forall x \in \text{Domain}, \quad \text{Condition}_{\text{special}}(x) \implies \operatorname{ApplyNorm}(N_{\text{special}}, x) \land \operatorname{SuppressNorm}(N_{\text{general}}, x)$$
   *Example*: Generic rule prohibits crossing red lights (Art 9/10). Special rule (Law 2008 Art 22 / Law 2024 Art 20) exempts emergency vehicles (`PRIORITY_VEHICLE`).

3. **Lex Posterior Derogat Legi Priori** (Later enactment overrides earlier enactment):
   Under Law No. 80/2015/QH13 Article 156 Clause 2, when two legal acts promulgated by the same authority contain differing provisions on the same subject, the later enacted provision governs.

---

### 5.4 Temporal Active Windows & Dynamic Amendment Diff Chains

Every vertex $v \in V$ and edge $e \in E$ possesses a formal Temporal Validity Window:

$$\mathcal{I}(v) = [t_{\text{effective}}, t_{\text{expiry}}), \quad t_{\text{expiry}} \in \mathbb{R} \cup \{+\infty\}$$

#### Dynamic Amendment State Machine across 3 Distinct Historical Phases:

```
%%{init: {"flowchart": {"defaultRenderer": "elk"}}}%%
flowchart LR
    subgraph PHASE1["GIAI ĐOẠN 1: 01/01/2020 -> 31/12/2021"]
        direction TB
        L2008_P1["Luật GTĐB 2008"]
        ND100_BASE["Nghị định 100/2019/NĐ-CP<br/>(Biểu khung phạt gốc)"]
    end

    subgraph PHASE2["GIAI ĐOẠN 2: 01/01/2022 -> 31/12/2024"]
        direction TB
        L2008_P2["Luật GTĐB 2008"]
        ND123_AMEND["Nghị định 123/2021/NĐ-CP<br/>(Sửa đổi tăng nặng mức phạt)"]
        ND100_CONSOL["Nghị định 100 (Hợp nhất)<br/>(Áp dụng mức phạt sửa đổi)"]
    end

    subgraph PHASE3["GIAI ĐOẠN 3: 01/01/2025 -> HIỆN TẠI"]
        direction TB
        L2024_NEW["Luật TTATGTĐB 2024 (Luật 36)<br/>& Luật Đường bộ 2024 (Luật 35)"]
        ND168_NEW["Nghị định 168/2024/NĐ-CP<br/>(Trừ điểm GPLX 12đ + Thay thế NĐ 100/123)"]
    end

    ND100_BASE -->|"MODIFIES_AND_REPLACES (01/01/2022)"| ND123_AMEND --> ND100_CONSOL
    ND100_CONSOL -->|"REPEALS (01/01/2025)"| ND168_NEW
    L2008_P2 -->|"REPEALS (01/01/2025)"| L2024_NEW
    L2024_NEW -->|"DEFINES_SANCTION_FOR"| ND168_NEW
```

#### Temporal Validity Execution Matrix:

| Temporal Evaluation Period | Governing Traffic Safety Statute | Governing Penalty Decree | Distinctive Sanction & Procedural Mechanics |
| :--- | :--- | :--- | :--- |
| **Phase 1**: Prior to 01/01/2022 | Luật GTĐB 2008 (Luật số 23/2008/QH12) | Nghị định 100/2019/NĐ-CP | Baseline monetary fine schedules; driver's license suspension; physical vehicle impoundment. |
| **Phase 2**: 01/01/2022 to 31/12/2024 | Luật GTĐB 2008 (Luật số 23/2008/QH12) | Nghị định 100/2019/NĐ-CP (Sửa đổi bởi Nghị định 123/2021/NĐ-CP) | Heavily increased fines for racing, license plate obscuration, helmet violations (200k–300k $\to$ 400k–600k), and expressway reversing. |
| **Phase 3**: 01/01/2025 onwards | • Luật TTATGTĐB 2024 (Luật số 36/2024/QH15)<br/>• Luật Đường bộ 2024 (Luật số 35/2024/QH15) | Nghị định 168/2024/NĐ-CP (Thay thế NĐ 100 & NĐ 123) | Enactment of the **12-Point Driver's License Deduction Regime**; updated driving license categories (A1, A, B1, B, C1, C...); mandatory VNeID digital credential presentation. |

---

## 6. Downstream System Architecture Directives

To ensure total architectural cohesion and flawless execution across all downstream documents (`docs/02` through `docs/05`), this section issues mandatory structural, relational, and algorithmic contracts.

### 6.1 Directives for PostgreSQL + pgvector Schema Design (`docs/02`)
1. **Schema Partitioning Invariant**: The database DDL in `docs/02_database_schema_pgvector.md` must implement clean structural separation across five relational tables:
   - `legal_documents`: Master metadata, promulgation authority, and temporal validity intervals.
   - `legal_structural_nodes`: 6-tier hierarchy tree nodes with recursive foreign keys (`parent_id`) and GIN-indexed `lineage_path` JSONB (`{"doc": "nd100", "art": 6, "cl": 1, "pt": "a"}`).
   - `legal_chunks`: Vector storage containing CFQC text representations, dense embeddings (`vector(1536)`), HNSW indexing (`m=16`, `ef_construction=64`), and GIN-indexed `metadata_payload`.
   - `legal_norm_triads`: Structured legal triad components ($\mathcal{H}, \mathcal{P}, \mathcal{S}$) with quantitative columns (`fine_min_vnd`, `fine_max_vnd`, `points_deducted`, `suspension_min_months`).
   - `legal_graph_edges`: Directed property graph edge table storing typed relationships (`relation_type`), source/target UUIDs, and temporal constraint JSONB.
2. **Indexing Invariants**:
   - Vector Index: HNSW with Cosine Distance (`vector_cosine_ops`).
   - Relational Indexing: Multi-column B-Tree on `(effective_date, expiry_date)` to accelerate temporal filtering queries.
   - Trigram Indexing: `pg_trgm` on `canonical_text` to support hybrid search with Vietnamese diacritic robustness.

---

### 6.2 Directives for MCP Tool Ecosystem & JSON-RPC Protocols (`docs/03`)
The Model Context Protocol (MCP) server designed in `docs/03_mcp_tools_and_server.md` must expose exactly seven atomic, orthogonal tools:

1. `hybrid_legal_search`: Hybrid dense vector + sparse full-text search over `legal_chunks` with strict JSONB ontology filters (`vehicle_type`, `violation_category`, `temporal_date`).
2. `get_hierarchical_context`: AST lineage expansion tool retrieving parent Article, lead Clause, and Chapter metadata for any given node UUID.
3. `traverse_normative_graph`: Multi-hop beam-search traverser expanding outgoing/incoming graph edges (`specifies`, `penalizes`, `references_tech`, `amends`).
4. `resolve_scope_override`: Deterministic signal and scope override evaluation engine implementing the priority algebra $\mathcal{H}_{\text{CSGT}} \succ \mathcal{H}_{\text{Light}} \succ \mathcal{H}_{\text{Sign}} \succ \mathcal{H}_{\text{Marking}}$ and emergency vehicle exemptions.
5. `validate_temporal_validity`: Verifies whether a statutory node or citation is legally active at $t_{\text{query}}$ and resolves amendment diff chains.
6. `query_runtime_cache`: Retrieves pre-computed sub-goal plans and verified multi-hop citation paths from the agent runtime cache.
7. `record_runtime_insight`: Persists verified multi-hop reasoning trajectories and citation paths into runtime knowledge tables.

---

### 6.3 Directives for Symmetrical Ingestion & CPHC Chunking (`docs/04`)
1. **Context-Preserving Hierarchical Chunking (CPHC)**: The ingestion pipeline in `docs/04_ingestion_and_chunking_strategy.md` must never execute arbitrary character-length splits. Ingestion must follow an AST-guided recursive decomposition preserving the 6-tier hierarchy.
2. **Automated Lead Clause Binding**: The pipeline must identify clause lead sentences (`Lời dẫn khoản`) and programmatically prepend them to all subordinate points (`Điểm`) during CFQC synthesis.
3. **Automated Cross-Reference Extraction**: The ingestion agent must execute strict regex and LLM-guided extraction to detect statutory citations and populate `legal_graph_edges` with validated relationship types.

---

### 6.4 Directives for Multi-Hop Retrieval & Reasoning Engine (`docs/05`)
1. **Query Planning & Decomposition**: The retrieval engine in `docs/05_retrieval_and_reasoning_pipeline.md` must decompose user inputs into a Directed Acyclic Graph (DAG) of sub-goals mapping to the tripartite triad ($\mathcal{H} \to \mathcal{P} \to \mathcal{S}$).
2. **Deterministic Triad Traversal**: The query planner must enforce mandatory hops:
   - User Query $\to$ Technical Parameter ($\text{QCVN / Thông tư } \mathcal{H}$)
   - Technical Parameter $\to$ Behavioral Duty ($\text{Luật } \mathcal{P}$)
   - Behavioral Duty $\to$ Fine Bracket & License Penalty ($\text{Nghị định } \mathcal{S}$)
   - Sanction $\to$ License Point Deduction ($\text{NĐ 168/2024 } \mathcal{S}_{\text{points}}$).
3. **Verifiable Citation Output**: The generation engine must synthesize answers with formal, machine-verifiable Vietnamese legal citations formatted down to the exact sub-article:
   > *"Căn cứ Điểm a Khoản 5 và Điểm b Khoản 11 Điều 5 Nghị định 100/2019/NĐ-CP (sửa đổi bởi Nghị định 123/2021/NĐ-CP) kết hợp Điều 6 Thông tư 31/2019/TT-BGTVT và Nghị định 168/2024/NĐ-CP..."*

---

*End of Specification — Vietnamese Traffic Legal Information Structure (`SPEC-DOC-01-LEGAL-STRUCTURE`)*
