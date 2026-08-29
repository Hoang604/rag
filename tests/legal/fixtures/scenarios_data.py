"""Authoritative scenario test vectors for 4-tier E2E testing."""

from __future__ import annotations

from dataclasses import dataclass

from rag_eval.legal.schemas import VehicleCategory


@dataclass(frozen=True)
class SpeedingScenarioVector:
    vehicle_type: VehicleCategory
    is_divided_road: bool
    is_urban_area: bool
    speed_limit_kmh: float
    recorded_speed_kmh: float
    expected_delta_kmh: float
    expected_fine_min_vnd: int
    expected_fine_max_vnd: int
    expected_suspension_months_min: int | None
    expected_suspension_months_max: int | None
    expected_demerit_points: int


SPEEDING_SCENARIOS = [
    # 1. Car in urban undivided road at 68 km/h (Limit 50, delta = 18 -> Bracket 10-20)
    SpeedingScenarioVector(
        vehicle_type=VehicleCategory.CAR_PASSENGER,
        is_divided_road=False,
        is_urban_area=True,
        speed_limit_kmh=50.0,
        recorded_speed_kmh=68.0,
        expected_delta_kmh=18.0,
        expected_fine_min_vnd=4000000,
        expected_fine_max_vnd=6000000,
        expected_suspension_months_min=1,
        expected_suspension_months_max=3,
        expected_demerit_points=2,
    ),
    # 2. Car in urban divided road at 64 km/h (Limit 60, delta = 4 -> Under 5 km/h tolerance: No fine)
    SpeedingScenarioVector(
        vehicle_type=VehicleCategory.CAR_PASSENGER,
        is_divided_road=True,
        is_urban_area=True,
        speed_limit_kmh=60.0,
        recorded_speed_kmh=64.0,
        expected_delta_kmh=4.0,
        expected_fine_min_vnd=0,
        expected_fine_max_vnd=0,
        expected_suspension_months_min=None,
        expected_suspension_months_max=None,
        expected_demerit_points=0,
    ),
]


@dataclass(frozen=True)
class AlcoholScenarioVector:
    vehicle_type: VehicleCategory
    breath_mg_l: float | None
    blood_mg_100ml: float | None
    expected_tier: int  # 1, 2, 3
    expected_fine_min_vnd: int
    expected_fine_max_vnd: int
    expected_suspension_months_min: int
    expected_suspension_months_max: int
    expected_impound_days: int
    expected_demerit_points: int


ALCOHOL_SCENARIOS = [
    # Tier 1 Car: breath <= 0.25 mg/L
    AlcoholScenarioVector(
        vehicle_type=VehicleCategory.CAR_PASSENGER,
        breath_mg_l=0.15,
        blood_mg_100ml=None,
        expected_tier=1,
        expected_fine_min_vnd=6000000,
        expected_fine_max_vnd=8000000,
        expected_suspension_months_min=10,
        expected_suspension_months_max=12,
        expected_impound_days=7,
        expected_demerit_points=3,
    ),
    # Tier 2 Car: 0.25 < breath <= 0.40 mg/L
    AlcoholScenarioVector(
        vehicle_type=VehicleCategory.CAR_PASSENGER,
        breath_mg_l=0.35,
        blood_mg_100ml=None,
        expected_tier=2,
        expected_fine_min_vnd=16000000,
        expected_fine_max_vnd=18000000,
        expected_suspension_months_min=16,
        expected_suspension_months_max=18,
        expected_impound_days=7,
        expected_demerit_points=6,
    ),
    # Tier 3 Car: breath > 0.40 mg/L
    AlcoholScenarioVector(
        vehicle_type=VehicleCategory.CAR_PASSENGER,
        breath_mg_l=0.55,
        blood_mg_100ml=None,
        expected_tier=3,
        expected_fine_min_vnd=30000000,
        expected_fine_max_vnd=40000000,
        expected_suspension_months_min=22,
        expected_suspension_months_max=24,
        expected_impound_days=7,
        expected_demerit_points=12,
    ),
]
