"""Adversarial stress-testing suite for Milestone R1 Legal Domain Schemas and Taxonomy Reconciliation."""

from __future__ import annotations

import unicodedata
from typing import Literal

import pytest
from pydantic import ValidationError

from rag_eval.legal.schemas import (
    AdditionalSanctions,
    AntiHallucinationAudit,
    ChainOfCustody,
    ChainOfCustodyPlanSummary,
    ChainOfCustodyStep,
    DemeritPointDeduction,
    EvidenceChunkHash,
    ExtractedEntities,
    FineBounds,
    LegalIntent,
    LegalNormExtraction,
    NormRole,
    PrecedenceResolutionAudit,
    TemporalValidationAudit,
    VehicleCategory,
    ViolationType,
    expand_vehicle_category,
    hash_evidence_node,
)

# ==============================================================================
# 1. Adversarial Vehicle Category Expansion & Unicode Diacritics
# ==============================================================================


class TestAdversarialVehicleExpansion:
    """Stress-test expand_vehicle_category across Unicode encodings, casings, and aliases."""

    @pytest.mark.parametrize(
        ("raw_input", "expected_categories"),
        [
            # Unicode Formats (NFC, NFD, NFKC, NFKD)
            (
                unicodedata.normalize("NFC", "xe ô tô"),
                [
                    VehicleCategory.CAR_PASSENGER,
                    VehicleCategory.CAR_TRUCK,
                    VehicleCategory.CAR_BUS,
                    VehicleCategory.CAR_TRACTOR,
                ],
            ),
            (
                unicodedata.normalize("NFD", "xe ô tô"),
                [
                    VehicleCategory.CAR_PASSENGER,
                    VehicleCategory.CAR_TRUCK,
                    VehicleCategory.CAR_BUS,
                    VehicleCategory.CAR_TRACTOR,
                ],
            ),
            (
                unicodedata.normalize("NFKC", "xe ô tô"),
                [
                    VehicleCategory.CAR_PASSENGER,
                    VehicleCategory.CAR_TRUCK,
                    VehicleCategory.CAR_BUS,
                    VehicleCategory.CAR_TRACTOR,
                ],
            ),
            (
                unicodedata.normalize("NFKD", "xe ô tô"),
                [
                    VehicleCategory.CAR_PASSENGER,
                    VehicleCategory.CAR_TRUCK,
                    VehicleCategory.CAR_BUS,
                    VehicleCategory.CAR_TRACTOR,
                ],
            ),
            (unicodedata.normalize("NFD", "xe máy"), [VehicleCategory.MOTORCYCLE]),
            (unicodedata.normalize("NFC", "xe máy"), [VehicleCategory.MOTORCYCLE]),
            (unicodedata.normalize("NFD", "xe tải"), [VehicleCategory.CAR_TRUCK]),
            (unicodedata.normalize("NFC", "xe tải"), [VehicleCategory.CAR_TRUCK]),
            (unicodedata.normalize("NFD", "xe buýt"), [VehicleCategory.CAR_BUS]),
            (unicodedata.normalize("NFC", "xe buýt"), [VehicleCategory.CAR_BUS]),
            (unicodedata.normalize("NFD", "mô tô"), [VehicleCategory.MOTORCYCLE]),
            (unicodedata.normalize("NFC", "mô tô"), [VehicleCategory.MOTORCYCLE]),
            (unicodedata.normalize("NFD", "xe gắn máy"), [VehicleCategory.MOPED]),
            (unicodedata.normalize("NFC", "xe gắn máy"), [VehicleCategory.MOPED]),
            (
                unicodedata.normalize("NFD", "xe đạp"),
                [VehicleCategory.BICYCLE_PRIMITIVE],
            ),
            (
                unicodedata.normalize("NFC", "xe đạp"),
                [VehicleCategory.BICYCLE_PRIMITIVE],
            ),
            (
                unicodedata.normalize("NFD", "xe đầu kéo"),
                [VehicleCategory.CAR_TRACTOR],
            ),
            (
                unicodedata.normalize("NFC", "xe đầu kéo"),
                [VehicleCategory.CAR_TRACTOR],
            ),
            (unicodedata.normalize("NFD", "xe máy điện"), [VehicleCategory.E_MOPED]),
            (unicodedata.normalize("NFC", "xe máy điện"), [VehicleCategory.E_MOPED]),
            (unicodedata.normalize("NFD", "xe đạp điện"), [VehicleCategory.E_BICYCLE]),
            (unicodedata.normalize("NFC", "xe đạp điện"), [VehicleCategory.E_BICYCLE]),
            (
                unicodedata.normalize("NFD", "xe chuyên dùng"),
                [VehicleCategory.SPECIALIZED_MACHINE],
            ),
            (
                unicodedata.normalize("NFC", "xe chuyên dùng"),
                [VehicleCategory.SPECIALIZED_MACHINE],
            ),
            (
                unicodedata.normalize("NFD", "xe máy chuyên dùng"),
                [VehicleCategory.SPECIALIZED_MACHINE],
            ),
            (
                unicodedata.normalize("NFC", "xe máy chuyên dùng"),
                [VehicleCategory.SPECIALIZED_MACHINE],
            ),
            (
                unicodedata.normalize("NFD", "xe ưu tiên"),
                [VehicleCategory.PRIORITY_VEHICLE],
            ),
            (
                unicodedata.normalize("NFC", "xe ưu tiên"),
                [VehicleCategory.PRIORITY_VEHICLE],
            ),
            # Mixed Case and Hyphenated Accented Synonyms
            ("xe ô-tô con", [VehicleCategory.CAR_PASSENGER]),
            ("Xe Ô-Tô Con", [VehicleCategory.CAR_PASSENGER]),
            ("XE Ô TÔ CON", [VehicleCategory.CAR_PASSENGER]),
            ("ô tô con", [VehicleCategory.CAR_PASSENGER]),
            ("Ô TÔ CON", [VehicleCategory.CAR_PASSENGER]),
            ("Xe Buýt", [VehicleCategory.CAR_BUS]),
            ("XE BUÝT", [VehicleCategory.CAR_BUS]),
            ("xe-buýt", [VehicleCategory.CAR_BUS]),
            ("Ô Tô Buýt", [VehicleCategory.CAR_BUS]),
            ("ô-tô-buýt", [VehicleCategory.CAR_BUS]),
            ("xe ô tô tải", [VehicleCategory.CAR_TRUCK]),
            ("xe-ô-tô-tải", [VehicleCategory.CAR_TRUCK]),
            ("ô tô tải", [VehicleCategory.CAR_TRUCK]),
            ("xe ô tô khách", [VehicleCategory.CAR_BUS]),
            ("ô tô khách", [VehicleCategory.CAR_BUS]),
            ("xe ô tô đầu kéo", [VehicleCategory.CAR_TRACTOR]),
            ("xe thô sơ", [VehicleCategory.E_BICYCLE, VehicleCategory.BICYCLE_PRIMITIVE]),
            ("XE THÔ SƠ", [VehicleCategory.E_BICYCLE, VehicleCategory.BICYCLE_PRIMITIVE]),
            ("xe-thô-sơ", [VehicleCategory.E_BICYCLE, VehicleCategory.BICYCLE_PRIMITIVE]),
            ("xe thô sơ primitive", [VehicleCategory.BICYCLE_PRIMITIVE]),
            (
                "xe hai bánh",
                [
                    VehicleCategory.MOTORCYCLE,
                    VehicleCategory.MOPED,
                    VehicleCategory.E_MOPED,
                    VehicleCategory.E_BICYCLE,
                    VehicleCategory.BICYCLE_PRIMITIVE,
                ],
            ),
            (
                "hai bánh",
                [
                    VehicleCategory.MOTORCYCLE,
                    VehicleCategory.MOPED,
                    VehicleCategory.E_MOPED,
                    VehicleCategory.E_BICYCLE,
                    VehicleCategory.BICYCLE_PRIMITIVE,
                ],
            ),
            (
                "xe cơ giới",
                [
                    VehicleCategory.CAR_PASSENGER,
                    VehicleCategory.CAR_TRUCK,
                    VehicleCategory.CAR_BUS,
                    VehicleCategory.CAR_TRACTOR,
                    VehicleCategory.MOTORCYCLE,
                    VehicleCategory.MOPED,
                    VehicleCategory.E_MOPED,
                ],
            ),
            (
                "cơ giới",
                [
                    VehicleCategory.CAR_PASSENGER,
                    VehicleCategory.CAR_TRUCK,
                    VehicleCategory.CAR_BUS,
                    VehicleCategory.CAR_TRACTOR,
                    VehicleCategory.MOTORCYCLE,
                    VehicleCategory.MOPED,
                    VehicleCategory.E_MOPED,
                ],
            ),
            ("gắn máy", [VehicleCategory.MOPED]),
            ("đầu kéo", [VehicleCategory.CAR_TRACTOR]),
            ("ĐẦU KÉO", [VehicleCategory.CAR_TRACTOR]),
            ("mô tô", [VehicleCategory.MOTORCYCLE]),
            ("MÔ TÔ", [VehicleCategory.MOTORCYCLE]),
            ("mô-tô", [VehicleCategory.MOTORCYCLE]),
            # English Codes and Enum Names
            (
                "CAR",
                [
                    VehicleCategory.CAR_PASSENGER,
                    VehicleCategory.CAR_TRUCK,
                    VehicleCategory.CAR_BUS,
                    VehicleCategory.CAR_TRACTOR,
                ],
            ),
            (
                "AUTO",
                [
                    VehicleCategory.CAR_PASSENGER,
                    VehicleCategory.CAR_TRUCK,
                    VehicleCategory.CAR_BUS,
                    VehicleCategory.CAR_TRACTOR,
                ],
            ),
            (
                "AUTOMOBILE",
                [
                    VehicleCategory.CAR_PASSENGER,
                    VehicleCategory.CAR_TRUCK,
                    VehicleCategory.CAR_BUS,
                    VehicleCategory.CAR_TRACTOR,
                ],
            ),
            (
                "MOTOR_VEHICLE",
                [
                    VehicleCategory.CAR_PASSENGER,
                    VehicleCategory.CAR_TRUCK,
                    VehicleCategory.CAR_BUS,
                    VehicleCategory.CAR_TRACTOR,
                    VehicleCategory.MOTORCYCLE,
                    VehicleCategory.MOPED,
                    VehicleCategory.E_MOPED,
                ],
            ),
            (
                "TWO_WHEELER",
                [
                    VehicleCategory.MOTORCYCLE,
                    VehicleCategory.MOPED,
                    VehicleCategory.E_MOPED,
                    VehicleCategory.E_BICYCLE,
                    VehicleCategory.BICYCLE_PRIMITIVE,
                ],
            ),
            ("MOPED_ALL", [VehicleCategory.MOPED, VehicleCategory.E_MOPED]),
            ("PRIMITIVE", [VehicleCategory.E_BICYCLE, VehicleCategory.BICYCLE_PRIMITIVE]),
            ("PASSENGER_CAR", [VehicleCategory.CAR_PASSENGER]),
            ("TRUCK", [VehicleCategory.CAR_TRUCK]),
            ("BUS", [VehicleCategory.CAR_BUS]),
            ("TRACTOR", [VehicleCategory.CAR_TRACTOR]),
            ("MOTORCYCLE", [VehicleCategory.MOTORCYCLE]),
            ("MOTO", [VehicleCategory.MOTORCYCLE]),
            ("MOPED", [VehicleCategory.MOPED]),
            ("ELECTRIC_MOPED", [VehicleCategory.E_MOPED]),
            ("ELECTRIC_BICYCLE", [VehicleCategory.E_BICYCLE]),
            ("CAR_PASSENGER", [VehicleCategory.CAR_PASSENGER]),
            ("CAR_TRUCK", [VehicleCategory.CAR_TRUCK]),
            ("CAR_BUS", [VehicleCategory.CAR_BUS]),
            ("CAR_TRACTOR", [VehicleCategory.CAR_TRACTOR]),
            ("SPECIALIZED_MACHINE", [VehicleCategory.SPECIALIZED_MACHINE]),
            ("PRIORITY_VEHICLE", [VehicleCategory.PRIORITY_VEHICLE]),
            # Enum Object Pass-through
            (VehicleCategory.CAR_PASSENGER, [VehicleCategory.CAR_PASSENGER]),
            (VehicleCategory.CAR_TRUCK, [VehicleCategory.CAR_TRUCK]),
            (VehicleCategory.CAR_BUS, [VehicleCategory.CAR_BUS]),
            (VehicleCategory.CAR_TRACTOR, [VehicleCategory.CAR_TRACTOR]),
            (VehicleCategory.MOTORCYCLE, [VehicleCategory.MOTORCYCLE]),
            (VehicleCategory.MOPED, [VehicleCategory.MOPED]),
            (VehicleCategory.E_MOPED, [VehicleCategory.E_MOPED]),
            (VehicleCategory.E_BICYCLE, [VehicleCategory.E_BICYCLE]),
            (VehicleCategory.BICYCLE_PRIMITIVE, [VehicleCategory.BICYCLE_PRIMITIVE]),
            (VehicleCategory.SPECIALIZED_MACHINE, [VehicleCategory.SPECIALIZED_MACHINE]),
            (VehicleCategory.PRIORITY_VEHICLE, [VehicleCategory.PRIORITY_VEHICLE]),
        ],
    )
    def test_expand_vehicle_category_valid_inputs(
        self, raw_input: str | VehicleCategory, expected_categories: list[VehicleCategory]
    ) -> None:
        """Verifies expand_vehicle_category correctly returns expected list without error."""
        result = expand_vehicle_category(raw_input)
        assert result == expected_categories

    @pytest.mark.parametrize(
        "invalid_input",
        [
            "",
            "   ",
            "\t",
            "\n",
            "mô-tô 2 bánh",  # specific composite unmapped phrase
            "xe ba gác",  # unmapped vernacular
            "xe xích lô ba gác",
            "tàu hỏa",
            "máy bay",
            "tàu thủy",
            "xe tên lửa",
            "phi thuyền không gian",
            "unknown_random_vehicle",
            "12345",
            "-100",
            "null",
            "None",
            "!@#$%^&*()",
            "<script>alert(1)</script>",
            "SELECT * FROM vehicle",
            "a" * 5000,
        ],
    )
    def test_expand_vehicle_category_invalid_inputs_raise_value_error(
        self, invalid_input: str
    ) -> None:
        """Verifies unmapped, non-vehicle, or adversarial inputs strictly raise ValueError."""
        with pytest.raises(
            ValueError, match="Unknown vehicle category, group alias, or code"
        ):
            expand_vehicle_category(invalid_input)


# ==============================================================================
# 2. Adversarial Fine Bounds & Currency Parsing
# ==============================================================================


class TestAdversarialFineBounds:
    """Stress-test FineBounds arithmetic, validation rules, and Vietnamese currency parsing."""

    def test_valid_fine_bounds_midpoint_calculation(self) -> None:
        fb = FineBounds(min_fine_vnd=800_000, max_fine_vnd=1_000_000)
        assert fb.min_fine_vnd == 800_000
        assert fb.max_fine_vnd == 1_000_000
        assert fb.average_fine_vnd == 900_000

    def test_single_bound_populates_average(self) -> None:
        fb_min = FineBounds(min_fine_vnd=500_000)
        assert fb_min.average_fine_vnd == 500_000

        fb_max = FineBounds(max_fine_vnd=700_000)
        assert fb_max.average_fine_vnd == 700_000

    def test_min_exceeding_max_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError, match="cannot exceed max_fine_vnd"):
            FineBounds(min_fine_vnd=2_000_000, max_fine_vnd=1_000_000)

    def test_negative_fines_raise_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            FineBounds(min_fine_vnd=-500)
        with pytest.raises(ValidationError):
            FineBounds(max_fine_vnd=-1000)

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            FineBounds.model_validate(
                {"min_fine_vnd": 100_000, "extra_illegal_field": 123}
            )

    @pytest.mark.parametrize(
        ("val_str", "unit_str", "expected_vnd"),
        [
            ("800.000", "đồng", 800_000),
            ("1.000.000", "đồng", 1_000_000),
            ("10.000.000", "đồng", 10_000_000),
            ("4", "triệu đồng", 4_000_000),
            ("6", "triệu đồng", 6_000_000),
            ("2,5", "triệu đồng", 2_500_000),
            ("2.5", "triệu", 2_500_000),
            ("500", "nghìn đồng", 500_000),
            ("500", "ngàn đồng", 500_000),
            ("500", "nghìn", 500_000),
            ("500", "k", 500_000),
            ("1,2", "tỷ đồng", 1_200_000_000),
            ("1.2", "tỷ", 1_200_000_000),
            ("100000", None, 100_000),
            ("10.000", "nghìn đồng", 10_000_000),
        ],
    )
    def test_currency_parsing_deterministic_resolution(
        self, val_str: str, unit_str: str | None, expected_vnd: int
    ) -> None:
        parsed = FineBounds.parse_currency_amount(val_str, unit_str)
        assert parsed == expected_vnd

    @pytest.mark.parametrize(
        ("val_str", "unit_str"),
        [
            ("", "đồng"),
            ("   ", "triệu"),
            ("invalid_text", "đồng"),
            ("abc", "k"),
            ("..", "triệu"),
        ],
    )
    def test_currency_parsing_malformed_returns_none(
        self, val_str: str, unit_str: str | None
    ) -> None:
        assert FineBounds.parse_currency_amount(val_str, unit_str) is None

    @pytest.mark.parametrize(
        ("statutory_text", "expected_min", "expected_max", "expected_avg"),
        [
            (
                "Phạt tiền từ 800.000 đồng đến 1.000.000 đồng đối với người điều khiển xe",
                800_000,
                1_000_000,
                900_000,
            ),
            (
                "Phạt tiền từ 4.000.000 đồng đến 6.000.000 đồng khi vi phạm tốc độ",
                4_000_000,
                6_000_000,
                5_000_000,
            ),
            (
                "phạt tiền từ 4 đến 6 triệu đồng",
                4_000_000,
                6_000_000,
                5_000_000,
            ),
            (
                "phạt tiền từ 500 nghìn đến 1 triệu đồng",
                500_000,
                1_000_000,
                750_000,
            ),
            (
                "Phạt tiền từ 100.000 đồng đến 200.000 đồng",
                100_000,
                200_000,
                150_000,
            ),
            (
                "Phạt tiền từ 30 triệu đến 40 triệu đồng đối với vi phạm cồn mức 3",
                30_000_000,
                40_000_000,
                35_000_000,
            ),
        ],
    )
    def test_from_statutory_text_extraction(
        self,
        statutory_text: str,
        expected_min: int,
        expected_max: int,
        expected_avg: int,
    ) -> None:
        fb = FineBounds.from_statutory_text(statutory_text)
        assert fb.min_fine_vnd == expected_min
        assert fb.max_fine_vnd == expected_max
        assert fb.average_fine_vnd == expected_avg

    def test_from_statutory_text_unmatched_returns_empty_model(self) -> None:
        fb = FineBounds.from_statutory_text("Không có thông tin mức phạt ở đoạn văn này")
        assert fb.min_fine_vnd is None
        assert fb.max_fine_vnd is None
        assert fb.average_fine_vnd is None


# ==============================================================================
# 3. Adversarial Additional Sanctions & Demerit Points
# ==============================================================================


class TestAdversarialSanctionsAndDemerit:
    """Stress-test AdditionalSanctions and DemeritPointDeduction bounds and constraints."""

    def test_valid_additional_sanctions(self) -> None:
        sanctions = AdditionalSanctions(
            license_suspension_months_min=1,
            license_suspension_months_max=3,
            vehicle_impoundment_days=7,
            demerit_points=2,
        )
        assert sanctions.license_suspension_months_min == 1
        assert sanctions.license_suspension_months_max == 3
        assert sanctions.vehicle_impoundment_days == 7
        assert sanctions.demerit_points == 2

    @pytest.mark.parametrize(
        "invalid_kwargs",
        [
            {"license_suspension_months_min": 0},  # ge=1 violation
            {"license_suspension_months_min": 37},  # le=36 violation
            {"license_suspension_months_max": 0},  # ge=1 violation
            {"license_suspension_months_max": 37},  # le=36 violation
            {
                "license_suspension_months_min": 10,
                "license_suspension_months_max": 5,
            },  # min > max
            {"vehicle_impoundment_days": -1},  # ge=0 violation
            {"vehicle_impoundment_days": 31},  # le=30 violation
            {"demerit_points": -1},  # ge=0 violation
            {"demerit_points": 13},  # le=12 violation
            {"unrecognized_property": "test"},  # extra=forbid
        ],
    )
    def test_invalid_additional_sanctions_raise_validation_error(
        self, invalid_kwargs: dict[str, int | str]
    ) -> None:
        with pytest.raises(ValidationError):
            AdditionalSanctions.model_validate(invalid_kwargs)

    @pytest.mark.parametrize("valid_points", [0, 2, 3, 4, 6, 8, 10, 12])
    def test_demerit_points_valid_steps(
        self, valid_points: Literal[0, 2, 3, 4, 6, 8, 10, 12]
    ) -> None:
        d = DemeritPointDeduction(is_demerit_applicable=True, points_deducted=valid_points)
        assert d.points_deducted == valid_points

    @pytest.mark.parametrize("invalid_points", [-1, 1, 5, 7, 9, 11, 13, 100])
    def test_demerit_points_invalid_steps_raise_validation_error(
        self, invalid_points: int
    ) -> None:
        with pytest.raises(ValidationError):
            DemeritPointDeduction.model_validate(
                {"is_demerit_applicable": True, "points_deducted": invalid_points}
            )


# ==============================================================================
# 4. Adversarial Ltree Regex & AST Node Validation
# ==============================================================================


class TestAdversarialLtreePathValidation:
    """Stress-test LTREE_PATH_PATTERN and LegalNormExtraction schema validation."""

    @pytest.mark.parametrize(
        "valid_path",
        [
            "doc_nd100_2019",
            "doc_nd100_2019.art_5",
            "doc_nd100_2019.c2.s1.a5.c3.p_a",
            "doc_luat_gtdb_2008.d10.k3",
            "doc_qcvn41_2019.app_b.p102",
            "doc_tt31_2019.art_6.cl_1",
            "doc_123_2021.a2.c10.p_b",
        ],
    )
    def test_ltree_path_valid_patterns(self, valid_path: str) -> None:
        norm = LegalNormExtraction(
            chunk_id="chk_test_001",
            hierarchy_path=valid_path,
            document_code="100/2019/NĐ-CP",
            document_type="NGHI_DINH",
            article_number=5,
            norm_role=NormRole.SANCTION_PRINCIPAL,
        )
        assert norm.hierarchy_path == valid_path

    @pytest.mark.parametrize(
        "invalid_path",
        [
            "",
            "   ",
            "nd100_2019.a5",  # missing doc_ prefix
            "doc_",  # no identifier after doc_
            "doc_nd100_2019..a5",  # consecutive dots
            "doc_nd100_2019.a5.",  # trailing dot
            ".doc_nd100_2019.a5",  # leading dot
            "doc_nd100-2019.a5",  # hyphen instead of underscore
            "doc_nd100/2019.a5",  # slash
            "doc_ND100_2019.a5",  # uppercase
            "doc_nd100_2019.A5",  # uppercase node
            "doc_nd100_2019.art 5",  # space
            "doc_nd100_2019.art_5;DROP TABLE legal_chunks;",  # injection attempt
            "doc_nd100_2019.a5.<script>",  # XSS attempt
            "doc_nd100_2019.a5.\x00",  # null byte
        ],
    )
    def test_ltree_path_invalid_patterns_raise_validation_error(
        self, invalid_path: str
    ) -> None:
        with pytest.raises(ValidationError):
            LegalNormExtraction(
                chunk_id="chk_test_invalid",
                hierarchy_path=invalid_path,
                document_code="100/2019/NĐ-CP",
                document_type="NGHI_DINH",
                article_number=5,
                norm_role=NormRole.SANCTION_PRINCIPAL,
            )


# ==============================================================================
# 5. Adversarial Extracted Entities & Classifiers
# ==============================================================================


class TestAdversarialExtractedEntities:
    """Stress-test speed delta calculations and statutory violation bracket classifications."""

    @pytest.mark.parametrize(
        ("recorded_speed", "speed_limit", "expected_delta", "expected_violation"),
        [
            # Below limit or exact limit
            (50.0, 50.0, 0.0, None),
            (45.0, 50.0, 0.0, None),
            (54.9, 50.0, 4.9, None),  # Under 5 km/h tolerance
            # SPEED_OVER_5_10: 5 km/h <= delta < 10 km/h
            (55.0, 50.0, 5.0, ViolationType.SPEED_OVER_5_10),
            (59.9, 50.0, 9.9, ViolationType.SPEED_OVER_5_10),
            # SPEED_OVER_10_20: 10 km/h <= delta <= 20 km/h
            (60.0, 50.0, 10.0, ViolationType.SPEED_OVER_10_20),
            (68.0, 50.0, 18.0, ViolationType.SPEED_OVER_10_20),
            (70.0, 50.0, 20.0, ViolationType.SPEED_OVER_20_35),
            # SPEED_OVER_20_35: 20 km/h < delta <= 35 km/h
            (75.0, 50.0, 25.0, ViolationType.SPEED_OVER_20_35),
            (84.9, 50.0, 34.9, ViolationType.SPEED_OVER_20_35),
            # SPEED_OVER_35_PLUS: delta >= 35 km/h
            (85.0, 50.0, 35.0, ViolationType.SPEED_OVER_35_PLUS),
            (120.0, 50.0, 70.0, ViolationType.SPEED_OVER_35_PLUS),
        ],
    )
    def test_speed_violation_classification_boundaries(
        self,
        recorded_speed: float,
        speed_limit: float,
        expected_delta: float,
        expected_violation: ViolationType | None,
    ) -> None:
        entities = ExtractedEntities(
            recorded_speed_kmh=recorded_speed, speed_limit_kmh=speed_limit
        )
        delta = entities.calculate_speed_delta()
        assert delta is not None
        assert round(delta, 1) == round(expected_delta, 1)
        assert entities.classify_speed_violation() == expected_violation

    @pytest.mark.parametrize(
        ("breath_mg_l", "blood_mg_100ml", "expected_violation"),
        [
            # Zero / Clean
            (0.0, 0.0, None),
            (None, None, None),
            # ALC_BRACKET_1: breath <= 0.25 or blood <= 50.0 (but > 0)
            (0.05, None, ViolationType.ALC_BRACKET_1),
            (0.25, None, ViolationType.ALC_BRACKET_1),
            (None, 20.0, ViolationType.ALC_BRACKET_1),
            (None, 50.0, ViolationType.ALC_BRACKET_1),
            # ALC_BRACKET_2: 0.25 < breath <= 0.40 or 50.0 < blood <= 80.0
            (0.2501, None, ViolationType.ALC_BRACKET_2),
            (0.35, None, ViolationType.ALC_BRACKET_2),
            (0.40, None, ViolationType.ALC_BRACKET_2),
            (None, 50.01, ViolationType.ALC_BRACKET_2),
            (None, 70.0, ViolationType.ALC_BRACKET_2),
            (None, 80.0, ViolationType.ALC_BRACKET_2),
            # ALC_BRACKET_3: breath > 0.40 or blood > 80.0
            (0.4001, None, ViolationType.ALC_BRACKET_3),
            (0.85, None, ViolationType.ALC_BRACKET_3),
            (None, 80.01, ViolationType.ALC_BRACKET_3),
            (None, 150.0, ViolationType.ALC_BRACKET_3),
        ],
    )
    def test_alcohol_violation_classification_boundaries(
        self,
        breath_mg_l: float | None,
        blood_mg_100ml: float | None,
        expected_violation: ViolationType | None,
    ) -> None:
        entities = ExtractedEntities(
            alcohol_breath_mg_l=breath_mg_l, alcohol_blood_mg_100ml=blood_mg_100ml
        )
        assert entities.classify_alcohol_violation() == expected_violation


# ==============================================================================
# 6. Adversarial Cryptographic Provenance & Chain of Custody
# ==============================================================================


class TestAdversarialChainOfCustody:
    """Stress-test EvidenceChunkHash SHA-256 hashing, immutability, and ChainOfCustody serialization."""

    def test_evidence_chunk_hash_from_text(self) -> None:
        text = "Điều 5 Khoản 3 Điểm a Nghị định 100/2019/NĐ-CP"
        ev = EvidenceChunkHash.from_text(
            chunk_id="chk_nd100_a5_c3_pa",
            hierarchy_path="doc_nd100_2019.a5.c3.p_a",
            document_code="100/2019/NĐ-CP",
            text=text,
        )
        assert ev.sha256_digest == hash_evidence_node(text)
        assert ev.byte_length == len(text.encode("utf-8"))

        # Verify frozen immutability dynamically
        target_field = "chunk_id"
        with pytest.raises(ValidationError):
            setattr(ev, target_field, "mutated_chunk_id")

    def test_invalid_sha256_digest_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            EvidenceChunkHash(
                chunk_id="chk_001",
                hierarchy_path="doc_nd100_2019.a5",
                document_code="100/2019/ND-CP",
                sha256_digest="INVALID_NON_HEX_OR_TOO_SHORT",
                byte_length=100,
            )

    def test_chain_of_custody_full_lifecycle_and_immutability(self) -> None:
        step = ChainOfCustodyStep(
            step_index=0,
            action="HYBRID_SEARCH",
            tool_invoked="mcp_traffic_hybrid_search",
            target_node_id="chk_001",
            node_sha256=hash_evidence_node("Statutory clause text"),
            document_code="100/2019/NĐ-CP",
            hierarchy_path="doc_nd100_2019.a5.c3.p_a",
            exact_statutory_text="Statutory clause text",
            relevance_score=0.99,
        )

        coc = ChainOfCustody(
            trace_id="trace-adversarial-2026",
            session_id="session-001",
            query_fingerprint_sha256=hash_evidence_node(
                "Vượt đèn đỏ ô tô phạt bao nhiêu?"
            ),
            execution_timestamp="2026-08-29T17:45:00Z",
            plan_summary=ChainOfCustodyPlanSummary(
                primary_intent=LegalIntent.INTENT_PENALTY_LOOKUP,
                total_subgoals=1,
                execution_path=["G1"],
            ),
            retrieval_steps=[step],
            precedence_resolutions=[
                PrecedenceResolutionAudit(
                    conflict_type="POLICE_VS_LIGHT",
                    dominant_authority="POLICE_OFFICER",
                    overridden_authorities=["TRAFFIC_LIGHT"],
                    statutory_rule_applied="QCVN 41:2019/BGTVT Điều 4.1",
                )
            ],
            temporal_validation=TemporalValidationAudit(
                base_document="100/2019/NĐ-CP",
                active_amending_document="123/2021/NĐ-CP",
                is_amended=True,
                effective_date_evaluated="2026-01-01",
            ),
            anti_hallucination_audit=AntiHallucinationAudit(
                is_grounded=True,
                unmatched_citations=[],
                citation_coverage_pct=100.0,
                hallucination_score=0.0,
            ),
        )

        # Immutability
        target_field_coc = "trace_id"
        target_field_step = "exact_statutory_text"
        with pytest.raises(ValidationError):
            setattr(coc, target_field_coc, "tampered_trace_id")
        with pytest.raises(ValidationError):
            setattr(step, target_field_step, "tampered_text")

        # Full roundtrip JSON serialization
        json_data = coc.model_dump_json()
        recovered = ChainOfCustody.model_validate_json(json_data)
        assert recovered.trace_id == "trace-adversarial-2026"
        assert (
            recovered.retrieval_steps[0].exact_statutory_text == "Statutory clause text"
        )
        assert recovered.anti_hallucination_audit.is_grounded is True
