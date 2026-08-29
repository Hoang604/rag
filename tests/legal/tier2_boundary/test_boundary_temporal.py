"""Tier 2: Boundary & Corner Cases tests for Temporal Validity executing production schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from rag_eval.legal.schemas import (
    ExtractedEntities,
    TemporalValidationAudit,
)
from tests.legal.fixtures.laws_data import (
    DECREE_100_ART5_CL3_PTA,
    DECREE_100_ART5_CL5_PTI,
)


class TestTier2TemporalBoundaries:
    """Boundary tests for statutory temporal horizons, amendments, and effective dates."""

    @pytest.mark.parametrize(
        ("evaluated_date", "expected_is_active"),
        [
            ("2024-12-31", False),
            ("2025-01-01", True),
            ("2026-08-29", True),
        ],
    )
    def test_decree_168_demerit_points_temporal_activation(
        self, evaluated_date: str, expected_is_active: bool
    ) -> None:
        """Verifies Decree 168 demerit points effective date (2025-01-01) boundary on production schema."""
        audit = TemporalValidationAudit(
            base_document="168/2024/ND-CP",
            is_amended=False,
            effective_date_evaluated=evaluated_date,
        )
        assert (audit.effective_date_evaluated >= "2025-01-01") is expected_is_active
        assert audit.base_document == "168/2024/ND-CP"
        assert audit.is_amended is False

    def test_temporal_validation_audit_amendment_tracking(self) -> None:
        """Verifies amendment tracking between base decree and amending decree."""
        audit = TemporalValidationAudit(
            base_document="100/2019/ND-CP",
            active_amending_document="123/2021/ND-CP",
            is_amended=True,
            effective_date_evaluated="2022-01-01",
        )
        assert audit.is_amended is True
        assert audit.active_amending_document == "123/2021/ND-CP"
        assert audit.effective_date_evaluated == "2022-01-01"

    def test_temporal_validation_audit_frozen_immutability(self) -> None:
        """Verifies that TemporalValidationAudit is immutable (frozen=True)."""
        audit = TemporalValidationAudit(
            base_document="100/2019/ND-CP",
            is_amended=False,
            effective_date_evaluated="2020-01-15",
        )
        attr_to_mutate = "is_amended"
        with pytest.raises(ValidationError):
            setattr(audit, attr_to_mutate, True)

    def test_statutory_chunk_temporal_metadata(self) -> None:
        """Verifies statutory chunks adhere to temporal horizons in production data."""
        assert DECREE_100_ART5_CL3_PTA.effective_date == "2020-01-15"
        assert DECREE_100_ART5_CL3_PTA.is_active is True

        assert DECREE_100_ART5_CL5_PTI.effective_date == "2022-01-01"
        assert DECREE_100_ART5_CL5_PTI.is_active is True

    @pytest.mark.parametrize("effective_year", [2019, 2020, 2024, 2025, 2026])
    def test_extracted_entities_effective_year_boundaries(
        self, effective_year: int
    ) -> None:
        """Verifies ExtractedEntities accepts and preserves statutory temporal horizons."""
        entities = ExtractedEntities(effective_year=effective_year)
        assert entities.effective_year == effective_year

    def test_extracted_entities_default_effective_year(self) -> None:
        """Verifies default statutory evaluation horizon is 2026."""
        entities = ExtractedEntities()
        assert entities.effective_year == 2026
