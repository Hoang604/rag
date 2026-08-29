"""Vietnamese Traffic Law Legal Domain Schemas and Taxonomy Models.

Strict Pydantic v2 domain models for normative triad traversal, CPHC chunks,
scope override algebra, DAG planning, and cryptographic chain-of-custody tracking.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from enum import Enum, IntEnum
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

LTREE_PATH_PATTERN: str = r"^doc_[a-z0-9_]+(?:\.[a-z0-9_]+)*$"

# ==============================================================================
# Domain Taxonomy Enums
# ==============================================================================


class VehicleCategory(str, Enum):
    """11 controlled vehicle categories under Vietnamese Road Traffic Law and QCVN 41:2019."""

    CAR_PASSENGER = "CAR_PASSENGER"  # Xe ô tô con (<= 9 chỗ, pickup < 950kg)
    CAR_TRUCK = "CAR_TRUCK"  # Xe ô tô tải (>= 950kg)
    CAR_BUS = "CAR_BUS"  # Xe ô tô khách (>= 10 chỗ)
    CAR_TRACTOR = "CAR_TRACTOR"  # Xe ô tô đầu kéo, sơ mi rơ moóc
    MOTORCYCLE = "MOTORCYCLE"  # Xe mô tô (dung tích >= 50cc hoặc điện > 4kW)
    MOPED = "MOPED"  # Xe gắn máy (< 50cc, vận tốc <= 50km/h)
    E_MOPED = "E_MOPED"  # Xe máy điện (<= 4kW, <= 50km/h)
    E_BICYCLE = "E_BICYCLE"  # Xe đạp điện (<= 250W, có bàn đạp)
    BICYCLE_PRIMITIVE = (
        "BICYCLE_PRIMITIVE"  # Xe đạp, xe thô sơ, xích lô, xe súc vật kéo
    )
    SPECIALIZED_MACHINE = (
        "SPECIALIZED_MACHINE"  # Xe máy chuyên dùng (thi công, nông nghiệp)
    )
    PRIORITY_VEHICLE = (
        "PRIORITY_VEHICLE"  # Xe ưu tiên (Cứu thương, Chữa cháy, Công an, Quân sự)
    )


class ViolationCategory(str, Enum):
    """8 core statutory violation categories."""

    ALCOHOL_DRUGS = "ALCOHOL_DRUGS"
    SPEED_DISTANCE = "SPEED_DISTANCE"
    LANE_DIRECTION = "LANE_DIRECTION"
    SIGNAL_COMPLIANCE = "SIGNAL_COMPLIANCE"
    STOP_PARK = "STOP_PARK"
    EQUIPMENT_SAFETY = "EQUIPMENT_SAFETY"
    LOAD_PASSENGER = "LOAD_PASSENGER"
    DOCUMENTATION_VNEID = "DOCUMENTATION_VNEID"


class ViolationType(str, Enum):
    """38 granular statutory violation types under Vietnamese traffic decrees."""

    # ALCOHOL_DRUGS
    ALC_BRACKET_1 = "ALC_BRACKET_1"
    ALC_BRACKET_2 = "ALC_BRACKET_2"
    ALC_BRACKET_3 = "ALC_BRACKET_3"
    DRUG_POSITIVE = "DRUG_POSITIVE"

    # SPEED_DISTANCE
    SPEED_OVER_5_10 = "SPEED_OVER_5_10"
    SPEED_OVER_10_20 = "SPEED_OVER_10_20"
    SPEED_OVER_20_35 = "SPEED_OVER_20_35"
    SPEED_OVER_35_PLUS = "SPEED_OVER_35_PLUS"
    SPEED_UNDER_MIN = "SPEED_UNDER_MIN"
    DISTANCE_UNSAFE = "DISTANCE_UNSAFE"

    # LANE_DIRECTION
    WRONG_LANE = "WRONG_LANE"
    WRONG_ROAD_PORTION = "WRONG_ROAD_PORTION"
    OPPOSITE_DIRECTION = "OPPOSITE_DIRECTION"
    HIGHWAY_REVERSE = "HIGHWAY_REVERSE"
    TURN_NO_SIGNAL = "TURN_NO_SIGNAL"
    LANE_CHANGE_NO_SIGNAL = "LANE_CHANGE_NO_SIGNAL"

    # SIGNAL_COMPLIANCE
    RED_LIGHT = "RED_LIGHT"
    AMBER_LIGHT = "AMBER_LIGHT"
    POLICE_COMMAND = "POLICE_COMMAND"
    SIGN_MARKING = "SIGN_MARKING"
    PROHIBITED_ZONE = "PROHIBITED_ZONE"

    # STOP_PARK
    ILLEGAL_STOP_PARK = "ILLEGAL_STOP_PARK"
    HIGHWAY_STOP_PARK = "HIGHWAY_STOP_PARK"
    BRIDGE_TUNNEL_STOP = "BRIDGE_TUNNEL_STOP"

    # EQUIPMENT_SAFETY
    HELMET_VIOLATION = "HELMET_VIOLATION"
    SEATBELT_VIOLATION = "SEATBELT_VIOLATION"
    PHONE_HANDHELD = "PHONE_HANDHELD"
    HEADLIGHT_NIGHT = "HEADLIGHT_NIGHT"
    HIGHBEAM_URBAN = "HIGHBEAM_URBAN"

    # LOAD_PASSENGER
    OVERLOAD_VEHICLE = "OVERLOAD_VEHICLE"
    OVERLOAD_INFRA = "OVERLOAD_INFRA"
    OVER_PASSENGER = "OVER_PASSENGER"

    # DOCUMENTATION_VNEID
    NO_LICENSE = "NO_LICENSE"
    EXPIRED_LICENSE = "EXPIRED_LICENSE"
    NO_REGISTRATION = "NO_REGISTRATION"
    NO_INSPECTION = "NO_INSPECTION"
    NO_CIVIL_INSURANCE = "NO_CIVIL_INSURANCE"
    VNEID_INTEGRATION = "VNEID_INTEGRATION"


class NormRole(str, Enum):
    """8 functional normative roles under formal jurisprudential triad theory."""

    HYPOTHESIS_CONDITION = "HYPOTHESIS_CONDITION"
    PRESCRIPTION_DUTY = "PRESCRIPTION_DUTY"
    PRESCRIPTION_PROHIBITION = "PRESCRIPTION_PROHIBITION"
    PRESCRIPTION_PERMISSION = "PRESCRIPTION_PERMISSION"
    SANCTION_PRINCIPAL = "SANCTION_PRINCIPAL"
    SANCTION_SUPPLEMENTARY = "SANCTION_SUPPLEMENTARY"
    SANCTION_POINT_DEDUCTION = "SANCTION_POINT_DEDUCTION"
    REMEDIAL_MEASURE = "REMEDIAL_MEASURE"


class ActorCategory(str, Enum):
    """7 controlled subject actors in traffic administrative relationships."""

    DRIVER = "DRIVER"
    PASSENGER = "PASSENGER"
    PEDESTRIAN = "PEDESTRIAN"
    VEHICLE_OWNER = "VEHICLE_OWNER"
    TRANSPORT_BUSINESS = "TRANSPORT_BUSINESS"
    ROAD_AUTHORITY = "ROAD_AUTHORITY"
    OTHER = "OTHER"


class GraphRelationType(str, Enum):
    """9 typed directed relations governing statutory interaction across normative triad."""

    DEFINES_SANCTION_FOR = "DEFINES_SANCTION_FOR"
    HAS_ADDITIONAL_SANCTION = "HAS_ADDITIONAL_SANCTION"
    REFERENCES_TECHNICAL_STANDARD = "REFERENCES_TECHNICAL_STANDARD"
    MODIFIES_AND_REPLACES = "MODIFIES_AND_REPLACES"
    REPEALS = "REPEALS"
    OVERRIDES_PRIORITY = "OVERRIDES_PRIORITY"
    EXEMPTS_CONDITION = "EXEMPTS_CONDITION"
    GUIDES = "GUIDES"
    DEFINES_TERM = "DEFINES_TERM"


class SignCategoryEnum(str, Enum):
    """8 signaling categories under QCVN 41:2019 and police command regulations."""

    PROHIBITORY = "PROHIBITORY"  # Biển báo cấm (P)
    WARNING = "WARNING"  # Biển cảnh báo / Nguy hiểm (W)
    MANDATORY = "MANDATORY"  # Biển hiệu lệnh (R)
    GUIDE = "GUIDE"  # Biển chỉ dẫn (I)
    AUXILIARY = "AUXILIARY"  # Biển phụ (S)
    ROAD_MARKING = "ROAD_MARKING"  # Vạch kẻ đường
    TRAFFIC_LIGHT = "TRAFFIC_LIGHT"  # Đèn tín hiệu giao thông
    POLICE_SIGNAL = "POLICE_SIGNAL"  # Hiệu lệnh CSGT / Người ĐKGT


class CacheValidationStatus(str, Enum):
    """4 verification statuses for runtime knowledge cache entries."""

    CANDIDATE = "CANDIDATE"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


class LegalIntent(str, Enum):
    """6 primary legal intent classes for query planning and decomposition."""

    INTENT_PENALTY_LOOKUP = "INTENT_PENALTY_LOOKUP"
    INTENT_BEHAVIOR_VALIDATION = "INTENT_BEHAVIOR_VALIDATION"
    INTENT_TECHNICAL_STANDARD = "INTENT_TECHNICAL_STANDARD"
    INTENT_PRIORITY_CONFLICT = "INTENT_PRIORITY_CONFLICT"
    INTENT_PROCEDURAL_TIMELINE = "INTENT_PROCEDURAL_TIMELINE"
    INTENT_COMPARATIVE_SYNTHESIS = "INTENT_COMPARATIVE_SYNTHESIS"


class SignalTier(IntEnum):
    """4-tier hierarchical precedence of traffic signaling authorities under QCVN 41:2019 Art 4."""

    POLICE_OFFICER = 1
    TRAFFIC_LIGHT = 2
    TRAFFIC_SIGN = 3
    ROAD_MARKING = 4


class Temporality(IntEnum):
    """Temporal status of road signaling."""

    TEMPORARY = 1  # Biển tạm thời / Công trường
    PERMANENT = 2  # Biển cố định


class SubGoalType(str, Enum):
    """Sub-goal types in query decomposition execution DAG."""

    LOOKUP_TECHNICAL_SPEC = "LOOKUP_TECHNICAL_SPEC"
    SEARCH_PRIMARY_SANCTION = "SEARCH_PRIMARY_SANCTION"
    EXPAND_ADDITIONAL_SANCTION = "EXPAND_ADDITIONAL_SANCTION"
    EVALUATE_PRIORITY_CASCADE = "EVALUATE_PRIORITY_CASCADE"
    CHECK_EXEMPTION_CLAUSES = "CHECK_EXEMPTION_CLAUSES"
    VERIFY_TEMPORAL_AMENDMENT = "VERIFY_TEMPORAL_AMENDMENT"


# ==============================================================================
# Helper Functions
# ==============================================================================


def remove_vietnamese_diacritics(text: str) -> str:
    """Normalizes Vietnamese text to uppercase unaccented ASCII snake_case.

    Decomposes Unicode combining characters (e.g., 'ô' -> 'o', 'á' -> 'a'),
    explicitly maps Vietnamese stroked letters ('đ'/'Đ' -> 'd'/'D'),
    and collapses consecutive whitespace and punctuation into single underscores.
    """
    nfkd_form = unicodedata.normalize("NFKD", text)
    unaccented = "".join(c for c in nfkd_form if not unicodedata.combining(c))
    unaccented = unaccented.replace("đ", "d").replace("Đ", "D")
    cleaned = re.sub(r"[\s\-_]+", "_", unaccented.strip().upper())
    return cleaned.strip("_")


def canonical_doc_slug(doc_code: str) -> str:
    """Returns the canonical dot-separated ltree document slug.

    Guarantees deterministic slug format 'doc_qcvn_41_2019' for QCVN 41:2019,
    'doc_luat_gtdb_2008' for Law 2008, 'doc_luat_ttatgtdb_2024' for Law 2024,
    and standard 'doc_<sanitized>' for decrees and other statutes.
    """
    if not doc_code or not doc_code.strip():
        return "doc_root"

    code = doc_code.strip()
    code_upper = code.upper()

    if "QCVN" in code_upper and "41" in code_upper:
        return "doc_qcvn_41_2019"
    if ("LUẬT" in code_upper or "LUAT" in code_upper) and "2008" in code_upper:
        return "doc_luat_gtdb_2008"
    if ("LUẬT" in code_upper or "LUAT" in code_upper) and "2024" in code_upper:
        return "doc_luat_ttatgtdb_2024"

    # Strip leading "doc_" if already present
    if code.lower().startswith("doc_"):
        code = code[4:]

    # Pre-transliterate Vietnamese Đ/đ into ASCII D/d before NFKD normalization
    transliterated = code.replace("đ", "d").replace("Đ", "D")
    normalized = unicodedata.normalize("NFKD", transliterated)
    ascii_text = "".join(c for c in normalized if not unicodedata.combining(c))
    clean = re.sub(r"[^a-zA-Z0-9_]+", "_", ascii_text.lower()).strip("_")
    clean = re.sub(r"_+", "_", clean)
    return f"doc_{clean or 'root'}"


def expand_vehicle_category(category: str | VehicleCategory) -> list[VehicleCategory]:
    """Expands a vehicle category or umbrella group alias into its constituent VehicleCategory classes.

    Supports hierarchical expansion for broad categories (e.g., 'CAR', 'MOTOR_VEHICLE', 'XE_MAY')
    and natural accented Vietnamese inputs (e.g., 'xe ô tô', 'xe máy', 'xe tải', 'xe buýt', 'mô tô', 'xe gắn máy', 'xe đạp').
    """
    if isinstance(category, VehicleCategory):
        clean_key = category.value
    else:
        clean_key = remove_vietnamese_diacritics(str(category))

    car_group = [
        VehicleCategory.CAR_PASSENGER,
        VehicleCategory.CAR_TRUCK,
        VehicleCategory.CAR_BUS,
        VehicleCategory.CAR_TRACTOR,
    ]
    motor_group = [
        VehicleCategory.CAR_PASSENGER,
        VehicleCategory.CAR_TRUCK,
        VehicleCategory.CAR_BUS,
        VehicleCategory.CAR_TRACTOR,
        VehicleCategory.MOTORCYCLE,
        VehicleCategory.MOPED,
        VehicleCategory.E_MOPED,
    ]
    two_wheeler_group = [
        VehicleCategory.MOTORCYCLE,
        VehicleCategory.MOPED,
        VehicleCategory.E_MOPED,
        VehicleCategory.E_BICYCLE,
        VehicleCategory.BICYCLE_PRIMITIVE,
    ]
    moped_group = [
        VehicleCategory.MOPED,
        VehicleCategory.E_MOPED,
    ]
    primitive_group = [
        VehicleCategory.E_BICYCLE,
        VehicleCategory.BICYCLE_PRIMITIVE,
    ]

    expansion_map: dict[str, list[VehicleCategory]] = {
        # Group Aliases
        "CAR": car_group,
        "AUTO": car_group,
        "AUTOMOBILE": car_group,
        "XE_O_TO": car_group,
        "O_TO": car_group,
        "OTO": car_group,
        "MOTOR_VEHICLE": motor_group,
        "XE_CO_GIOI": motor_group,
        "CO_GIOI": motor_group,
        "ALL_MOTOR": motor_group,
        "TWO_WHEELER": two_wheeler_group,
        "XE_HAI_BANH": two_wheeler_group,
        "HAI_BANH": two_wheeler_group,
        "MOPED_ALL": moped_group,
        "XE_GAN_MAY_ALL": moped_group,
        "PRIMITIVE": primitive_group,
        "XE_THO_SO": primitive_group,
        # Exact Member Aliases
        "CAR_PASSENGER": [VehicleCategory.CAR_PASSENGER],
        "XE_CON": [VehicleCategory.CAR_PASSENGER],
        "XE_O_TO_CON": [VehicleCategory.CAR_PASSENGER],
        "O_TO_CON": [VehicleCategory.CAR_PASSENGER],
        "PASSENGER_CAR": [VehicleCategory.CAR_PASSENGER],
        "CAR_TRUCK": [VehicleCategory.CAR_TRUCK],
        "XE_TAI": [VehicleCategory.CAR_TRUCK],
        "XE_O_TO_TAI": [VehicleCategory.CAR_TRUCK],
        "O_TO_TAI": [VehicleCategory.CAR_TRUCK],
        "TRUCK": [VehicleCategory.CAR_TRUCK],
        "CAR_BUS": [VehicleCategory.CAR_BUS],
        "XE_KHACH": [VehicleCategory.CAR_BUS],
        "XE_O_TO_KHACH": [VehicleCategory.CAR_BUS],
        "O_TO_KHACH": [VehicleCategory.CAR_BUS],
        "XE_BUYT": [VehicleCategory.CAR_BUS],
        "O_TO_BUYT": [VehicleCategory.CAR_BUS],
        "BUS": [VehicleCategory.CAR_BUS],
        "CAR_TRACTOR": [VehicleCategory.CAR_TRACTOR],
        "XE_DAU_KEO": [VehicleCategory.CAR_TRACTOR],
        "XE_O_TO_DAU_KEO": [VehicleCategory.CAR_TRACTOR],
        "DAU_KEO": [VehicleCategory.CAR_TRACTOR],
        "TRACTOR": [VehicleCategory.CAR_TRACTOR],
        "MOTORCYCLE": [VehicleCategory.MOTORCYCLE],
        "XE_MO_TO": [VehicleCategory.MOTORCYCLE],
        "MO_TO": [VehicleCategory.MOTORCYCLE],
        "XE_MAY": [VehicleCategory.MOTORCYCLE],
        "MOTO": [VehicleCategory.MOTORCYCLE],
        "MOPED": [VehicleCategory.MOPED],
        "XE_GAN_MAY": [VehicleCategory.MOPED],
        "GAN_MAY": [VehicleCategory.MOPED],
        "E_MOPED": [VehicleCategory.E_MOPED],
        "XE_MAY_DIEN": [VehicleCategory.E_MOPED],
        "ELECTRIC_MOPED": [VehicleCategory.E_MOPED],
        "E_BICYCLE": [VehicleCategory.E_BICYCLE],
        "XE_DAP_DIEN": [VehicleCategory.E_BICYCLE],
        "ELECTRIC_BICYCLE": [VehicleCategory.E_BICYCLE],
        "BICYCLE_PRIMITIVE": [VehicleCategory.BICYCLE_PRIMITIVE],
        "XE_DAP": [VehicleCategory.BICYCLE_PRIMITIVE],
        "XE_THO_SO_PRIMITIVE": [VehicleCategory.BICYCLE_PRIMITIVE],
        "SPECIALIZED_MACHINE": [VehicleCategory.SPECIALIZED_MACHINE],
        "XE_MAY_CHUYEN_DUNG": [VehicleCategory.SPECIALIZED_MACHINE],
        "XE_CHUYEN_DUNG": [VehicleCategory.SPECIALIZED_MACHINE],
        "PRIORITY_VEHICLE": [VehicleCategory.PRIORITY_VEHICLE],
        "XE_UU_TIEN": [VehicleCategory.PRIORITY_VEHICLE],
    }

    if clean_key in expansion_map:
        return list(expansion_map[clean_key])

    # Direct Enum matching attempt
    for cat in VehicleCategory:
        if cat.value == clean_key:
            return [cat]

    raise ValueError(f"Unknown vehicle category, group alias, or code: '{category}'")


def hash_evidence_node(text: str) -> str:
    """Calculates deterministic SHA-256 digest of textual legal node for provenance tracking."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ==============================================================================
# Pydantic v2 Extraction & Sanction Models
# ==============================================================================


class FineBounds(BaseModel):
    """Statutory administrative fine interval in Vietnamese Đồng (VND)."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    min_fine_vnd: int | None = Field(
        default=None, ge=0, description="Minimum fine in VND"
    )
    max_fine_vnd: int | None = Field(
        default=None, ge=0, description="Maximum fine in VND"
    )
    average_fine_vnd: int | None = Field(
        default=None, ge=0, description="Midpoint average fine in VND"
    )

    @model_validator(mode="after")
    def validate_fine_bounds(self) -> FineBounds:
        """Ensures min_fine <= max_fine and computes average_fine if omitted."""
        if self.min_fine_vnd is not None and self.max_fine_vnd is not None:
            if self.min_fine_vnd > self.max_fine_vnd:
                raise ValueError(
                    f"min_fine_vnd ({self.min_fine_vnd}) cannot exceed max_fine_vnd ({self.max_fine_vnd})"
                )
            if self.average_fine_vnd is None:
                self.average_fine_vnd = (self.min_fine_vnd + self.max_fine_vnd) // 2
        elif self.min_fine_vnd is not None and self.average_fine_vnd is None:
            self.average_fine_vnd = self.min_fine_vnd
        elif self.max_fine_vnd is not None and self.average_fine_vnd is None:
            self.average_fine_vnd = self.max_fine_vnd
        return self

    @staticmethod
    def parse_currency_amount(val_str: str, unit_str: str | None = None) -> int | None:
        """Deterministically converts Vietnamese numerical amounts and units into integer VND."""
        clean_val = val_str.strip().replace(" ", "")
        if not clean_val:
            return None

        # Handle Vietnamese thousand and decimal separators
        if "." in clean_val and "," in clean_val:
            clean_val = clean_val.replace(".", "").replace(",", ".")
        elif "," in clean_val:
            clean_val = clean_val.replace(",", ".")
        elif "." in clean_val:
            parts = clean_val.split(".")
            # If 3-digit groups (e.g. 800.000 or 1.000.000), strip dots
            if all(len(p) == 3 for p in parts[1:]):
                clean_val = clean_val.replace(".", "")

        try:
            base_val = float(clean_val)
        except (ValueError, TypeError):
            return None

        unit = (unit_str or "đồng").lower().strip()
        if "tỷ" in unit:
            multiplier = 1_000_000_000
        elif "triệu" in unit or "tr" in unit:
            multiplier = 1_000_000
        elif "nghìn" in unit or "ngàn" in unit or "k" in unit:
            multiplier = 1_000
        else:
            multiplier = 1

        return round(base_val * multiplier)

    @classmethod
    def from_statutory_text(cls, text: str) -> FineBounds:
        """Extracts FineBounds from statutory or conversational Vietnamese text."""
        fine_pattern = re.compile(
            r"phạt\s+tiền\s+từ\s+"
            r"(?P<min_val>[0-9\.\,]+)\s*(?P<min_unit>đồng|triệu\s+đồng|nghìn\s+đồng|ngàn\s+đồng|tỷ\s+đồng|triệu|nghìn|ngàn|tỷ)?\s*"
            r"đến\s+"
            r"(?P<max_val>[0-9\.\,]+)\s*(?P<max_unit>đồng|triệu\s+đồng|nghìn\s+đồng|ngàn\s+đồng|tỷ\s+đồng|triệu|nghìn|ngàn|tỷ)?",
            re.IGNORECASE,
        )
        match = fine_pattern.search(text)
        if not match:
            return cls()

        max_unit = match.group("max_unit") or "đồng"
        min_unit = match.group("min_unit") or max_unit

        min_vnd = cls.parse_currency_amount(match.group("min_val"), min_unit)
        max_vnd = cls.parse_currency_amount(match.group("max_val"), max_unit)

        return cls(min_fine_vnd=min_vnd, max_fine_vnd=max_vnd)


class AdditionalSanctions(BaseModel):
    """Supplementary administrative sanctions including driving license suspensions and impoundment."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    license_suspension_months_min: int | None = Field(
        default=None,
        ge=1,
        le=36,
        description="Min months of driving license suspension",
    )
    license_suspension_months_max: int | None = Field(
        default=None,
        ge=1,
        le=36,
        description="Max months of driving license suspension",
    )
    vehicle_impoundment_days: int | None = Field(
        default=None, ge=0, le=30, description="Days of temporary vehicle impoundment"
    )
    demerit_points: Literal[0, 2, 3, 4, 6, 8, 10, 12] | None = Field(
        default=None,
        description="Driving license demerit points (Luật 2024 / NĐ 168/2024)",
    )

    @model_validator(mode="after")
    def validate_suspension_range(self) -> AdditionalSanctions:
        """Validates that license suspension min does not exceed max."""
        if (
            self.license_suspension_months_min is not None
            and self.license_suspension_months_max is not None
            and self.license_suspension_months_min > self.license_suspension_months_max
        ):
            raise ValueError(
                f"license_suspension_months_min ({self.license_suspension_months_min}) "
                f"cannot exceed max ({self.license_suspension_months_max})"
            )
        return self


class DemeritPointDeduction(BaseModel):
    """Demerit point deduction mechanics under Law No. 36/2024/QH15 and Decree No. 168/2024/NĐ-CP."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    is_demerit_applicable: bool = Field(
        default=False, description="Whether points deduction applies"
    )
    points_deducted: Literal[0, 2, 3, 4, 6, 8, 10, 12] = Field(
        default=0, description="Exact points deducted from 12-point license bank"
    )
    legal_basis: str = Field(
        default="Nghị định 168/2024/NĐ-CP",
        description="Statutory provision establishing point deduction",
    )


class ExceptionMetadata(BaseModel):
    """Statutory exemption clauses, emergency vehicle privileges, and scope overrides."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    has_exception: bool = Field(
        default=False,
        description="Whether unit contains an exemption or override clause",
    )
    exception_type: str | None = Field(
        default=None,
        description="Category: EMERGENCY_VEHICLE, POLICE_COMMAND, TECHNICAL_MALFUNCTION",
    )
    exception_clause_text: str | None = Field(
        default=None, description="Verbatim text of the exception clause"
    )
    overridden_by: list[str] = Field(
        default_factory=lambda: list[str](),
        description="Authorities overriding this rule (e.g. POLICE_COMMAND)",
    )
    exempt_vehicle_categories: list[VehicleCategory] = Field(
        default_factory=lambda: list[VehicleCategory](),
        description="Vehicles exempt from this sanction",
    )


class ReferencedEntity(BaseModel):
    """Explicit cross-references to statutory laws, technical standards, and amending decrees."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    law_articles: list[str] = Field(
        default_factory=lambda: list[str](),
        description="Referenced Law Articles (e.g. 'Luật GTĐB Điều 10')",
    )
    qcvn_signs: list[str] = Field(
        default_factory=lambda: list[str](),
        description="Referenced Sign codes (e.g. 'P.102', 'W.201')",
    )
    qcvn_markings: list[str] = Field(
        default_factory=lambda: list[str](),
        description="Referenced Road Marking codes (e.g. '1.1', '2.2')",
    )
    amending_decrees: list[str] = Field(
        default_factory=lambda: list[str](),
        description="Amending decree references (e.g. '123/2021/NĐ-CP')",
    )


class LegalNormExtraction(BaseModel):
    """Master production extraction schema matching PostgreSQL legal_chunks."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    chunk_id: str = Field(description="Deterministic chunk identifier")
    hierarchy_path: str = Field(
        pattern=LTREE_PATH_PATTERN,
        description="ltree dot-separated path (e.g., 'doc_nd100_2019.a5.c3.p_a')",
    )
    document_code: str = Field(
        description="Official document number/code (e.g., '100/2019/NĐ-CP')"
    )
    document_type: (
        Literal["LUAT", "NGHI_DINH", "THONG_TU", "QUY_CHUAN_KY_THUAT", "QUYET_DINH"]
        | str
    ) = Field(description="Statutory instrument type")

    article_number: int | None = Field(
        default=None, ge=1, description="Numerical article index if pure integer"
    )
    article_index: str = Field(
        default="", description="Full statutory article code, e.g. 'Điều 5', 'Điều 7a'"
    )
    clause_number: int | None = Field(
        default=None, ge=1, description="Clause number (Khoản)"
    )
    point_letter: str | None = Field(
        default=None, description="Point letter (Điểm)"
    )

    norm_role: NormRole = Field(description="Functional normative role")
    primary_actor: ActorCategory = Field(
        default=ActorCategory.DRIVER, description="Target legal subject actor"
    )
    vehicle_types: list[VehicleCategory] = Field(
        default_factory=lambda: list[VehicleCategory](),
        description="Target vehicle classes",
    )
    violation_categories: list[ViolationCategory] = Field(
        default_factory=lambda: list[ViolationCategory](),
        description="Violation categories",
    )
    violation_types: list[ViolationType] = Field(
        default_factory=lambda: list[ViolationType](),
        description="Granular violation types",
    )

    behavior_summary: str = Field(
        default="", description="Concise Vietnamese summary of regulated behavior"
    )
    fine_bounds: FineBounds = Field(default_factory=FineBounds)
    additional_sanctions: AdditionalSanctions = Field(
        default_factory=AdditionalSanctions
    )
    remedial_measures: list[str] = Field(default_factory=lambda: list[str]())

    exceptions_and_overrides: ExceptionMetadata = Field(
        default_factory=ExceptionMetadata
    )
    referenced_entities: ReferencedEntity = Field(default_factory=ReferencedEntity)

    contextualized_text: str = Field(
        default="", description="Full CPHC synthesized text for vector embedding"
    )
    verbatim_text: str = Field(default="", description="Raw statutory text")
    effective_date: str | None = None
    expiry_date: str | None = None
    expiration_date: str | None = None
    is_active: bool = True
    is_amended: bool = False
    amended_by: str | None = None


class CanonicalFullyQualifiedChunk(BaseModel):
    """Canonical Fully Qualified Chunk (CFQC) generated by CPHC engine."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    chunk_id: str
    document_id: str
    document_code: str
    hierarchy_path: str = Field(
        pattern=LTREE_PATH_PATTERN,
        description="ltree dot-separated path (e.g., 'doc_nd100_2019.a5.c3.p_a')",
    )
    article_number: int | None = None
    article_index: str = ""
    clause_number: int | None = None
    point_letter: str | None = None

    synthesized_prefix: str
    lead_sentence: str | None = None
    verbatim_text: str
    contextualized_text: str

    norm_role: NormRole
    primary_actor: ActorCategory
    vehicle_types: list[VehicleCategory] = Field(
        default_factory=lambda: list[VehicleCategory]()
    )
    violation_categories: list[ViolationCategory] = Field(
        default_factory=lambda: list[ViolationCategory]()
    )
    violation_types: list[ViolationType] = Field(
        default_factory=lambda: list[ViolationType]()
    )

    fine_bounds: FineBounds = Field(default_factory=FineBounds)
    additional_sanctions: AdditionalSanctions = Field(
        default_factory=AdditionalSanctions
    )
    exceptions_and_overrides: ExceptionMetadata = Field(
        default_factory=ExceptionMetadata
    )
    referenced_entities: ReferencedEntity = Field(default_factory=ReferencedEntity)

    embedding_vector: list[float] | None = Field(
        default=None,
        description="Normalized dense embedding vector (e.g. 384 or 1536 dim)",
    )
    effective_date: str | None = None
    expiry_date: str | None = None
    expiration_date: str | None = None
    is_active: bool = True
    is_amended: bool = False
    amended_by: str | None = None

    @property
    def clause_index(self) -> str | None:
        return f"Khoản {self.clause_number}" if self.clause_number is not None else None

    @property
    def point_index(self) -> str | None:
        return f"Điểm {self.point_letter}" if self.point_letter is not None else None

    @property
    def doc_title(self) -> str:
        return self.document_code

    @property
    def doc_code(self) -> str:
        return self.document_code

    @property
    def full_citation_label(self) -> str:
        """Constructs full hierarchical Vietnamese statutory citation label.

        Combines point_index, clause_index, article_index (or article_number), and document_code.
        Example: 'Điểm a Khoản 3 Điều 5 100/2019/NĐ-CP' or 'Điều 5 100/2019/NĐ-CP'.
        """
        parts: list[str] = []
        if self.point_index:
            parts.append(self.point_index)
        if self.clause_index:
            parts.append(self.clause_index)
        if self.article_index:
            parts.append(self.article_index)
        elif self.article_number is not None:
            parts.append(f"Điều {self.article_number}")
        if self.document_code:
            parts.append(self.document_code)
        return " ".join(parts).strip()


# ==============================================================================
# Reasoning, DAG Planning & Scope Override Models
# ==============================================================================


class ExtractedEntities(BaseModel):
    """Structured query entity slots extracted by the query planner."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    vehicle_category: VehicleCategory | None = Field(
        default=None, description="Primary vehicle type"
    )
    vehicle_weight_tons: float | None = Field(
        default=None, ge=0.0, description="Gross vehicle weight in metric tons"
    )
    recorded_speed_kmh: float | None = Field(
        default=None, ge=0.0, description="Actual driving speed recorded"
    )
    speed_limit_kmh: float | None = Field(
        default=None, ge=0.0, description="Applicable speed limit on roadway"
    )
    alcohol_breath_mg_l: float | None = Field(
        default=None, ge=0.0, le=5.0, description="Breath alcohol concentration mg/1L"
    )
    alcohol_blood_mg_100ml: float | None = Field(
        default=None, ge=0.0, le=500.0, description="Blood alcohol concentration mg/100mL"
    )
    traffic_sign_codes: list[str] = Field(
        default_factory=lambda: list[str](),
        description="Referenced sign codes (e.g. ['P.102', 'P.106a'])",
    )
    road_marking_codes: list[str] = Field(
        default_factory=lambda: list[str](),
        description="Referenced marking codes (e.g. ['1.1', '2.2'])",
    )
    location_context: Literal[
        "urban_residential", "rural_non_residential", "expressway", "unknown"
    ] = Field(default="unknown", description="Roadway classification and environment")
    is_emergency_mission: bool = Field(
        default=False,
        description="Whether vehicle was operating under statutory emergency duty",
    )
    has_conflicting_authority: bool = Field(
        default=False,
        description="Whether query involves multiple contradictory signals",
    )
    effective_year: int = Field(
        default=2026, description="Statutory temporal horizon for legal validity"
    )

    def classify_alcohol_violation(self) -> ViolationType | None:
        """Deterministically classifies breath/blood alcohol readings into statutory violation types."""
        brac = self.alcohol_breath_mg_l
        bac = self.alcohol_blood_mg_100ml

        if (brac is not None and brac > 0.40) or (bac is not None and bac > 80.0):
            return ViolationType.ALC_BRACKET_3
        if (brac is not None and brac > 0.25) or (bac is not None and bac > 50.0):
            return ViolationType.ALC_BRACKET_2
        if (brac is not None and brac > 0.0) or (bac is not None and bac > 0.0):
            return ViolationType.ALC_BRACKET_1
        return None

    def calculate_speed_delta(self) -> float | None:
        """Calculates over-speed delta Δv in km/h."""
        if self.recorded_speed_kmh is not None and self.speed_limit_kmh is not None:
            return max(0.0, self.recorded_speed_kmh - self.speed_limit_kmh)
        return None

    def classify_speed_violation(self) -> ViolationType | None:
        """Deterministically classifies speed delta into statutory violation types."""
        delta = self.calculate_speed_delta()
        if delta is None or delta < 5.0:
            return None
        if delta >= 35.0:
            return ViolationType.SPEED_OVER_35_PLUS
        if delta >= 20.0:
            return ViolationType.SPEED_OVER_20_35
        if delta >= 10.0:
            return ViolationType.SPEED_OVER_10_20
        return ViolationType.SPEED_OVER_5_10


type ToolArgumentValue = str | int | float | bool | list[str] | None


class SubGoalNode(BaseModel):
    """Sub-goal node in execution DAG."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    goal_id: str = Field(description="Unique identifier for the sub-goal, e.g. 'G1'")
    goal_type: SubGoalType
    mcp_tool_name: str
    tool_arguments: dict[str, ToolArgumentValue] = Field(
        default_factory=lambda: dict[str, ToolArgumentValue]()
    )
    dependencies: list[str] = Field(
        default_factory=lambda: list[str](),
        description="List of goal_ids that must complete before this node",
    )
    can_execute_parallel: bool = Field(
        default=False,
        description="Whether this goal can execute concurrently with siblings",
    )


class ExecutionPlanDAG(BaseModel):
    """Complete query decomposition and execution DAG plan."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    query_id: str
    original_query: str
    primary_intent: LegalIntent
    extracted_entities: ExtractedEntities = Field(default_factory=ExtractedEntities)
    sub_goals: list[SubGoalNode] = Field(default_factory=lambda: list[SubGoalNode]())
    execution_order: list[list[str]] = Field(
        default_factory=lambda: list[list[str]](),
        description="Topologically sorted execution stages with parallel goal IDs",
    )
    fallback_clarification_prompt: str | None = Field(
        default=None,
        description="Interactive dialog prompt if query is fatally underspecified",
    )


class TrafficSignalCommand(BaseModel):
    """Traffic signaling directive with authority tier and temporality ranking."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    source_type: SignalTier
    temporality: Temporality
    command_directive: (
        Literal["PROCEED", "STOP", "TURN_LEFT", "TURN_RIGHT", "SPEED_LIMIT"] | str
    )
    speed_cap_kmh: float | None = None
    legal_citation: str = ""


class ConflictEvaluationResult(BaseModel):
    """Evaluated signal resolution ruling under statutory precedence algebra."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    dominant_signal: TrafficSignalCommand
    suppressed_signals: list[TrafficSignalCommand] = Field(
        default_factory=lambda: list[TrafficSignalCommand]()
    )
    is_driver_action_legal: bool
    ruling_rationale: str
    legal_basis: list[str] = Field(default_factory=lambda: list[str]())


# ==============================================================================
# Cryptographic Chain of Custody (CoC) & Provenance Models
# ==============================================================================


class EvidenceChunkHash(BaseModel):
    """Cryptographic evidence digest binding an exact statutory text payload to a SHA-256 hash."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    chunk_id: str = Field(description="Deterministic chunk identifier")
    hierarchy_path: str = Field(
        pattern=LTREE_PATH_PATTERN,
        description="ltree hierarchy path",
    )
    document_code: str = Field(description="Statutory document code")
    sha256_digest: str = Field(
        pattern=r"^[a-f0-9]{64}$",
        description="SHA-256 hex digest of the raw verbatim text",
    )
    byte_length: int = Field(ge=0, description="Payload length in UTF-8 bytes")

    @classmethod
    def from_text(
        cls, chunk_id: str, hierarchy_path: str, document_code: str, text: str
    ) -> EvidenceChunkHash:
        encoded = text.encode("utf-8")
        return cls(
            chunk_id=chunk_id,
            hierarchy_path=hierarchy_path,
            document_code=document_code,
            sha256_digest=hashlib.sha256(encoded).hexdigest(),
            byte_length=len(encoded),
        )


class ChainOfCustodyStep(BaseModel):
    """Individual retrieval step with cryptographic evidence hashing."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    step_index: int = Field(ge=0)
    action: str
    tool_invoked: str
    target_node_id: str
    node_sha256: str = Field(
        description="SHA-256 cryptographic hash of the retrieved node payload"
    )
    document_code: str
    hierarchy_path: str
    exact_statutory_text: str
    relevance_score: float = Field(default=1.0, ge=0.0, le=1.0)


class ChainOfCustodyPlanSummary(BaseModel):
    """Summary of DAG execution plan inside Chain of Custody."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    primary_intent: LegalIntent
    total_subgoals: int = Field(ge=0)
    execution_path: list[str] = Field(default_factory=lambda: list[str]())


class PrecedenceResolutionAudit(BaseModel):
    """Audit log entry for signal conflict or scope override resolution."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    conflict_type: str
    dominant_authority: str
    overridden_authorities: list[str] = Field(default_factory=lambda: list[str]())
    statutory_rule_applied: str


class TemporalValidationAudit(BaseModel):
    """Audit log entry for temporal amendment resolution."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    base_document: str
    active_amending_document: str | None = None
    is_amended: bool = False
    effective_date_evaluated: str


class AntiHallucinationAudit(BaseModel):
    """Verification metrics for legal citation grounding."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    is_grounded: bool = True
    unmatched_citations: list[str] = Field(default_factory=lambda: list[str]())
    citation_coverage_pct: float = Field(default=100.0, ge=0.0, le=100.0)
    hallucination_score: float = Field(default=0.0, ge=0.0, le=1.0)


class ChainOfCustody(BaseModel):
    """Cryptographic provenance and anti-hallucination audit package."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    trace_id: str
    session_id: str | None = None
    query_fingerprint_sha256: str
    execution_timestamp: str
    plan_summary: ChainOfCustodyPlanSummary | None = None
    retrieval_steps: list[ChainOfCustodyStep] = Field(
        default_factory=lambda: list[ChainOfCustodyStep]()
    )
    evidence_hashes: list[EvidenceChunkHash] = Field(
        default_factory=lambda: list[EvidenceChunkHash]()
    )
    precedence_resolutions: list[PrecedenceResolutionAudit] = Field(
        default_factory=lambda: list[PrecedenceResolutionAudit]()
    )
    temporal_validation: TemporalValidationAudit | None = None
    anti_hallucination_audit: AntiHallucinationAudit = Field(
        default_factory=AntiHallucinationAudit
    )


# ==============================================================================
# Synthetic Benchmark Evaluation Models
# ==============================================================================


class SyntheticQAPair(BaseModel):
    """Synthetic multi-hop benchmark QA pair with verified gold citation paths."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    test_id: str = Field(
        description="Unique synthetic test identifier, e.g. 'SYN_T1_a5c3pa_001'"
    )
    tier: Literal[1, 2, 3] = Field(
        description="Benchmark tier: 1=Single-hop factual, 2=Boundary/parametric, 3=Multi-hop override/precedence"
    )
    intent: LegalIntent = Field(
        default=LegalIntent.INTENT_PENALTY_LOOKUP,
        description="Statutory query intent classification",
    )
    query: str = Field(
        description="Natural language Vietnamese question or operational query"
    )
    context_scenario: str | None = Field(
        default=None, description="Operational scenario or background condition"
    )
    gold_citation_paths: list[str] = Field(
        min_length=1,
        description="Ordered list of gold citation ltree paths forming verifiable Chain of Custody",
    )
    primary_vehicle: VehicleCategory | None = Field(
        default=None, description="Target vehicle category"
    )
    violation_categories: list[ViolationCategory] = Field(
        default_factory=lambda: list[ViolationCategory]()
    )
    violation_types: list[ViolationType] = Field(
        default_factory=lambda: list[ViolationType]()
    )
    expected_fine_bounds: FineBounds = Field(default_factory=FineBounds)
    expected_additional_sanctions: AdditionalSanctions = Field(
        default_factory=AdditionalSanctions
    )
    is_exempt: bool = Field(
        default=False,
        description="Whether the driver action is legally exempt from sanctions",
    )
    dominant_authority: str | None = Field(
        default=None,
        description="Dominant signaling or legal authority in conflict resolution",
    )
    metadata: dict[str, str | int | float | bool | list[str]] = Field(
        default_factory=lambda: dict[str, str | int | float | bool | list[str]]()
    )
