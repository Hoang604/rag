# Iteration 006: Failure Triage & Error Analysis

Analysis of Iteration 006 (BGE Query Prefix):

---

## 1. Diagnostic Summary

- Adding the 8-word instruction prefix shifted the query representation away from compact scientific and legal entity names.
- Dense representations perform best with direct tokenization on `bge-small-en-v1.5`.

---

## 2. Target for Iteration 007

- **Chunk Window Optimization**: Current 512 character chunking (~80 words) splits paragraphs and sentences arbitrarily. Expanding to 1000 characters (`chunk_overlap=150`) allows complete paragraphs to be represented in single dense vectors (~200 tokens) without exceeding the model's 512-token limit.
