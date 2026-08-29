"""Tier 2: Boundary & Corner Cases tests for Vehicle Gross Weights and Overloading."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from rag_eval.legal.schemas import (
    ExtractedEntities,
    VehicleCategory,
    ViolationCategory,
    ViolationType,
    expand_vehicle_category,
)


class TestTier2VehicleWeights:
    """Boundary tests for payload limits, pickup truck definitions, and overloading brackets."""

    def test_pickup_truck_payload_boundary_under_950kg_is_passenger_car(self) -> None:
        """QCVN 41:2019 Art 3.20: Pickup with permissible payload < 950kg is categorized as CAR_PASSENGER."""
        expanded = expand_vehicle_category("xe ô tô con")
        assert VehicleCategory.CAR_PASSENGER in expanded
        assert len(expanded) == 1

        entities = ExtractedEntities(
            vehicle_category=VehicleCategory.CAR_PASSENGER,
            vehicle_weight_tons=0.949,
        )
        assert entities.vehicle_category == VehicleCategory.CAR_PASSENGER
        assert entities.vehicle_weight_tons == 0.949

    def test_truck_payload_boundary_exact_950kg_is_truck(self) -> None:
        """QCVN 41:2019 Art 3.25: Commercial vehicle with payload >= 950kg is categorized as CAR_TRUCK."""
        expanded = expand_vehicle_category("xe tải")
        assert VehicleCategory.CAR_TRUCK in expanded
        assert len(expanded) == 1

        entities = ExtractedEntities(
            vehicle_category=VehicleCategory.CAR_TRUCK,
            vehicle_weight_tons=0.950,
        )
        assert entities.vehicle_category == VehicleCategory.CAR_TRUCK
        assert entities.vehicle_weight_tons == 0.950

    @pytest.mark.parametrize(
        ("weight_tons", "is_valid"),
        [
            (0.0, True),
            (0.5, True),
            (3.5, True),
            (10.0, True),
            (45.0, True),
        ],
    )
    def test_extracted_entities_valid_vehicle_weights(
        self, weight_tons: float, is_valid: bool
    ) -> None:
        """Verifies ExtractedEntities correctly processes non-negative metric ton weights."""
        entities = ExtractedEntities(
            vehicle_category=VehicleCategory.CAR_TRUCK,
            vehicle_weight_tons=weight_tons,
        )
        assert (entities.vehicle_weight_tons == weight_tons) is is_valid

    def test_extracted_entities_negative_weight_raises_validation_error(self) -> None:
        """Verifies ExtractedEntities rejects negative gross weights via ge=0.0 constraint."""
        with pytest.raises(ValidationError):
            ExtractedEntities(
                vehicle_category=VehicleCategory.CAR_TRUCK,
                vehicle_weight_tons=-0.01,
            )

    @pytest.mark.parametrize(
        ("alias", "expected_category"),
        [
            ("xe tải", VehicleCategory.CAR_TRUCK),
            ("xe ô tô tải", VehicleCategory.CAR_TRUCK),
            ("TRUCK", VehicleCategory.CAR_TRUCK),
            ("xe đầu kéo", VehicleCategory.CAR_TRACTOR),
            ("xe ô tô đầu kéo", VehicleCategory.CAR_TRACTOR),
            ("TRACTOR", VehicleCategory.CAR_TRACTOR),
            ("xe khách", VehicleCategory.CAR_BUS),
            ("xe buýt", VehicleCategory.CAR_BUS),
            ("BUS", VehicleCategory.CAR_BUS),
        ],
    )
    def test_commercial_heavy_vehicle_alias_expansion(
        self, alias: str, expected_category: VehicleCategory
    ) -> None:
        """Verifies expand_vehicle_category resolves all commercial weight category aliases."""
        expanded = expand_vehicle_category(alias)
        assert expected_category in expanded

    def test_overload_violation_types_exist_in_taxonomy(self) -> None:
        """Verifies violation taxonomy contains vehicle and infrastructure overload categories."""
        assert ViolationType.OVERLOAD_VEHICLE.value == "OVERLOAD_VEHICLE"
        assert ViolationType.OVERLOAD_INFRA.value == "OVERLOAD_INFRA"
        assert ViolationCategory.LOAD_PASSENGER.value == "LOAD_PASSENGER"
