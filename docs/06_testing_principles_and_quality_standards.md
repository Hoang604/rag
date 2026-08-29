# Vietnamese Traffic Law Platform: Testing Principles & Quality Standards Reference

**Document Reference:** `SPEC-TESTING-PRINCIPLES-2026`  
**Purpose:** Authoritative testing philosophy, seam discipline, mock banning rules, and adversarial test design standards for audit agents and software engineers.  
**Target Codebase:** [`src/rag_eval/legal/`](file:///home/hoang/python/rag/src/rag_eval/legal/), [`tests/legal/`](file:///home/hoang/python/rag/tests/legal/), and [`audits/`](file:///home/hoang/python/rag/audits/)

---

## 1. Core Testing Directive & Philosophy

Every test suite in this platform exists to discover and verify **actual system invariants, boundary contracts, and failure seams**.

```
%%{init: {"flowchart": {"defaultRenderer": "elk"}}}%%
flowchart TD
    subgraph DIRECTIVE["Core Testing Directives"]
        D1["<b>1. Catch Real Bugs (Breaks-If)</b><br/>Every test must fail if a specific mutation or logic bug is introduced."]
        D2["<b>2. Zero Tautology & Zero Logic Mirroring</b><br/>Never copy-paste source logic into test functions or assert on local if/elif variables."]
        D3["<b>3. The Interface is the Test Surface</b><br/>Assert exclusively on observable outcomes crossing public external seams."]
        D4["<b>4. Strict Dependency Discipline</b><br/>Forbid mocks for in-process compute and local-substitutable infrastructure."]
    end
```

### The "Breaks-If" Criterion
A test is only valid if you can answer:
> **"What specific, plausible defect in production code will cause this test to fail?"**

If a test only asserts on mock return values, checks trivial enum membership (`assert cat in VehicleCategory`), or tests local variables inside the test body, it is a **Tautological Test (Test Rác)** and must be rejected during audit.

---

## 2. Seam Discipline: "The Interface is the Test Surface"

An interface is **everything a caller must know to use the module**:
- Public type signatures and parameters.
- Behavioral invariants and ordering constraints.
- Error modes, exception classes, and boundary rejections.

```
                    ┌─────────────────────────────────────────────────────────┐
                    │                   EXTERNAL SEAM                         │
                    │        (Public Function / Class / Tool Call)            │
                    └─────────────────────────────────────────────────────────┘
                                                ▲
                                                │ Calls & Asserts
                        ┌───────────────────────┴───────────────────────┐
                        │                                               │
               ┌─────────────────┐                             ┌─────────────────┐
               │ Production Code │                             │   Test Suite    │
               └─────────────────┘                             └─────────────────┘
                        │                                               │
                        ▼                                               ▼
          [Private Helpers & Methods]                      [❌ FORBIDDEN: NEVER]
          [Internal State & Variables]                     [Assert on internals]
          [Intermediate Call Graphs]                       [Mock internal calls]
```

### Anti-Brittle Defense Rules:
1. **Zero Interface Leakage**: Never expose private methods, internal helper functions, or intermediate variables solely to make something testable.
2. **Refactor-Proof Invariance**: If the internal implementation is refactored (e.g., switching from a regex loop to a state machine) but the public interface behavior remains identical, **the test MUST continue to pass**. If it breaks solely due to refactoring, it is brittle implementation-coupled code.

---

## 3. Dependency Categorization & Mocking Ban (`DEPENDING` Discipline)

All system dependencies must be categorized into one of 4 strict tiers. Mocks are forbidden in tiers 1 and 2:

```
%%{init: {"flowchart": {"defaultRenderer": "elk"}}}%%
flowchart LR
    subgraph DEPENDENCY_TIERS["4-Tier Dependency Discipline"]
        direction TB
        T1["<b>Tier 1: In-Process Compute</b><br/>(Schemas, Parsers, CPHC, Overrides)<br/>👉 <b>STRICTLY FORBID MOCKS</b> (Direct calls)"]
        T2["<b>Tier 2: Local-Substitutable</b><br/>(PostgreSQL 16, pgvector, Filesystem)<br/>👉 <b>STRICTLY FORBID MOCKS</b> (Real Docker / tmp_path)"]
        T3["<b>Tier 3: Remote-Owned Services</b><br/>(Internal microservices, Message Queues)<br/>👉 <b>Port Seams with In-Memory FakePorts</b>"]
        T4["<b>Tier 4: True-External APIs</b><br/>(OpenAI Cloud Embedding API, LLM Gateway)<br/>👉 <b>Mock / Stub Adapters Permitted</b>"]
    end
```

| Dependency Category | System Components | Stand-In / Adapter Rule | Mocking Policy |
|:---|:---|:---|:---:|
| **1. In-Process** | `schemas.py`, `grammar.py`, `parser.py`, `cphc.py`, `overrides.py`, `chain_of_custody.py` | Call production functions directly crossing public interface. | 🚫 **STRICTLY BANNED** |
| **2. Local-Substitutable** | PostgreSQL 16 (`db/connection.py`, `001_initial_schema.sql`, `002_stored_procs.sql`), `loader.py`, Filesystem | Use containerized PostgreSQL (`compose.yaml`) or isolated test DB (`tmp_path`). | 🚫 **STRICTLY BANNED** |
| **3. Remote-Owned** | MCP JSON-RPC Server Transport, Stdio Dispatcher | Use in-memory Stdio/AsyncIO transport pipes (`FakePort`). | ⚠️ **FakePort Only** |
| **4. True-External** | OpenAI Embedding API, Third-Party LLM Endpoints | Use deterministic static vector stubs with exact target dimensions (e.g. 384d / 1536d). | ✅ **Permitted** |

---

## 4. Legwork & Oracle Declaration Standards

### 4.1. Zero-Hallucination Legwork Requirement
Before writing or auditing a test, the auditor/engineer must explicitly cite the exact ground-truth source:
- **Code Line Citation**: `CODE [src/rag_eval/legal/schemas.py#L110-L125]`
- **Statutory Specification Citation**: `SPEC [docs/01_legal_information_structure.md#L45]` or `LEGAL [Nghị định 100/2019/NĐ-CP Điều 5 Khoản 8 Điểm a]`

### 4.2. Oracle & Causal Independence
- **Ground Truth Claim**: Declare what the invariant is (e.g., *"Fine midpoint must equal (min + max) / 2"*).
- **Causal Independence**: Declare variables that must NOT affect the outcome (e.g., *"Input casing or extra whitespace must not alter extracted legal citations"*).
- **Unverified Assumptions**: If a requirement is ambiguous, explicitly flag it with `⚠️ ASSUMPTION — needs confirmation`.

---

## 5. Adversarial Test Matrix Specification

When auditing existing tests or designing new tests, every test case must conform to this structured matrix schema:

| Test Category | Target Seam / Function | Verification Target (`Observable Outcome / Invariant`) | Test Stand-in / Adapter (`No In-Process Mocks`) | Breaks-If Mutation (`Specific Code Bug That Fails This`) |
|:---|:---|:---|:---|:---|
| **Unit / Logic** | `[expand_vehicle_category](file:///src/rag_eval/legal/schemas.py)` | Expands `"xe ô tô"` into `CAR_PASSENGER`, `CAR_TRUCK`, `CAR_BUS` | In-process direct call | Diacritic stripping failure or missing alias mapping |
| **Database / SQL** | `[hybrid_legal_search](file:///src/rag_eval/legal/db/sql/002_stored_procs.sql)` | Returns valid RRF ranks with zero NULL values for sparse-only matches | Real PostgreSQL 16 Container (`compose.yaml`) | Swallowing sparse ranks or outer join NULL propagation |
| **Ingestion / CPHC** | `[synthesize_cphc_prefix](file:///src/rag_eval/legal/ingestion/cphc.py)` | Point chunk inherits Clause lead sentence and Article title | In-process direct call | Dropping parent context or leaking neighbor penalties |
| **Reasoning / Overrides** | `[resolve_scope_overrides](file:///src/rag_eval/legal/reasoning/overrides.py)` | CSGT command overrides Red Light signal with zero fine | In-process direct call | Incorrect priority tuple ordering (e.g. Light > CSGT) |
| **Security / CoC** | `[validate_citations](file:///src/rag_eval/legal/reasoning/chain_of_custody.py)` | Rejects fabricated citation `"Điều 999 NĐ 999"` with `is_grounded=False` | In-process direct call | Hardcoding `is_grounded = len(retrieved) > 0` |

---

## 6. Checklist for Audit Agents (`audits/08_test_fidelity_and_verification_audit.md`)

When auditing tests, auditors must check and flag the following **6 Deadly Test Smells**:
1. **Split-Brain Test Schemas**: Test suite maintains duplicate schema definitions instead of importing production models.
2. **Tautological In-Test Branching**: Test implements local `if/elif` logic and asserts on local variables without invoking production code.
3. **Artificial Keyword Bonuses**: Mock fixtures add fake scores (`+50.0`) to force benchmark test passes.
4. **Mocking In-Process Code**: Tests instantiate mock classes (`MockQueryPlanner`, `MockMCPServer`) instead of testing production classes.
5. **Vacuous Assertions**: Tests that only check `assert x is not None` or `assert enum_val in EnumClass` without testing behavior.
6. **Implementation-Coupled Fragility**: Tests asserting on internal private attributes (`obj._internal_cache`) instead of public interface outcomes.
