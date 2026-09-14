"""Disk-based Staging Store and Manager for Two-Phase Statutory Ingestion.

Re-exports public models, domain entities, and manager class for 100% backward compatibility.
"""

from rag_eval.legal.ingestion.staging.manager import StagingManager
from rag_eval.legal.ingestion.staging.models import (
    DEFAULT_STAGING_DIR,
    RawTextWindow,
    ReparentPathMapping,
    StagingChunk,
    StagingChunkDelta,
    StagingDeltaReport,
    StagingEdge,
    StagingGrepHit,
    StagingMutationRecord,
    StagingSessionSummary,
    StagingStatus,
    StgReparentResult,
    deep_merge_dict,
)
from rag_eval.legal.ingestion.staging.session import StagingDocumentSession

__all__ = [
    "DEFAULT_STAGING_DIR",
    "RawTextWindow",
    "ReparentPathMapping",
    "StagingChunk",
    "StagingChunkDelta",
    "StagingDeltaReport",
    "StagingDocumentSession",
    "StagingEdge",
    "StagingGrepHit",
    "StagingManager",
    "StagingMutationRecord",
    "StagingSessionSummary",
    "StagingStatus",
    "StgReparentResult",
    "deep_merge_dict",
]
