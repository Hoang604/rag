"""Deprecated mock reasoning module - purged in compliance with F-23 (FLAG-05).

All test suites must invoke real production reasoning components directly from
`rag_eval.legal.reasoning.*` (QueryPlanner, ScopeOverrideEngine, DeterministicTriadTraverser,
ChainOfCustodyGenerator, LegalReasoningPipeline).
"""

from __future__ import annotations

__all__: list[str] = []
