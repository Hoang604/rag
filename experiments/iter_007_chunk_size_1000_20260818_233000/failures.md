# Iteration 007: Failure Triage & Error Analysis

Analysis of Iteration 007:

---

## 1. Domain Resolution Differences

- **FiQA**: Financial question answering requires full multi-sentence contexts; 1000 chars provided the complete explanatory reasoning, increasing Hit@10 to 64%.
- **CUAD & SciFact**: Specific clause contracts and abstracts are concise (~300-500 chars); 1000 chars bundled extra clauses, introducing cross-clause term noise.

---

## 2. Target for Iteration 008

- **Balanced Window Size**: Intermediate chunk size of 750 characters (`chunk_overlap=100`) to capture multi-sentence explanations while keeping clause boundary dilution low.
