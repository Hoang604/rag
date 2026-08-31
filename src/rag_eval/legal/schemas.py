"""Domain Taxonomy, Enums, and Pydantic v2 Schemas for Vietnamese Traffic Law RAG."""

from __future__ import annotations

import functools
import re
import unicodedata
from enum import Enum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Strict LTREE path regex conforming to PostgreSQL ltree extension
LTREE_PATH_PATTERN = r"^doc_[a-z0-9_]+(?:\.[a-z0-9_]+)*$"


# ==============================================================================
# Domain Exceptions (Matching JSON-RPC 2.0 error specifications)
# ==============================================================================


class LegalDomainError(Exception):
    """Base domain exception with standardized error code and metadata payload."""

    error_code: int = -32000

    def __init__(self, message: str, data: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.data = data or {}


class StorageConnectionError(LegalDomainError):
    error_code = -32001


class UnitNotFoundError(LegalDomainError):
    error_code = -32004


class InvalidLTREEPathError(LegalDomainError):
    error_code = -32602


class InvalidParamsError(LegalDomainError):
    error_code = -32602


class ASTGroundingValidationError(LegalDomainError):
    error_code = -32002


class CitationIntegrityViolationError(LegalDomainError):
    error_code = -32002


class CorpusNotFoundError(LegalDomainError):
    error_code = -32004


class VectorDimensionMismatchError(LegalDomainError):
    error_code = -32003


class HierarchyNavigationError(LegalDomainError):
    error_code = -32005


class KnowledgeCacheMissError(LegalDomainError):
    error_code = -32006


class PrecedenceConflictError(LegalDomainError):
    error_code = -32007


class StatementTimeoutError(LegalDomainError):
    error_code = -32008


# ==============================================================================
# Canonical Taxonomies & Enumerations (Mirroring PostgreSQL DDL Enums)
# ==============================================================================


class NormRole(str, Enum):
    """8 canonical norm roles under Vietnamese Administrative Jurisprudence."""

    HYPOTHESIS_CONDITION = "HYPOTHESIS_CONDITION"
    PRESCRIPTION_DUTY = "PRESCRIPTION_DUTY"
    PRESCRIPTION_PROHIBITION = "PRESCRIPTION_PROHIBITION"
    PRESCRIPTION_PERMISSION = "PRESCRIPTION_PERMISSION"
    SANCTION_PRINCIPAL = "SANCTION_PRINCIPAL"
    SANCTION_SUPPLEMENTARY = "SANCTION_SUPPLEMENTARY"
    SANCTION_POINT_DEDUCTION = "SANCTION_POINT_DEDUCTION"
    REMEDIAL_MEASURE = "REMEDIAL_MEASURE"


class GraphRelationType(str, Enum):
    """9 statutory property graph relation types."""

    DEFINES_SANCTION_FOR = "DEFINES_SANCTION_FOR"
    HAS_ADDITIONAL_SANCTION = "HAS_ADDITIONAL_SANCTION"
    REFERENCES_TECHNICAL_STANDARD = "REFERENCES_TECHNICAL_STANDARD"
    MODIFIES_AND_REPLACES = "MODIFIES_AND_REPLACES"
    REPEALS = "REPEALS"
    OVERRIDES_PRIORITY = "OVERRIDES_PRIORITY"
    EXEMPTS_CONDITION = "EXEMPTS_CONDITION"
    GUIDES = "GUIDES"
    DEFINES_TERM = "DEFINES_TERM"


class CacheValidationStatus(str, Enum):
    """4 verification statuses for runtime knowledge cache entries."""

    CANDIDATE = "CANDIDATE"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


# ==============================================================================
# Helper Functions
# ==============================================================================


@functools.lru_cache(maxsize=8192)
def remove_vietnamese_diacritics(text: str) -> str:
    """Normalizes Vietnamese text to uppercase unaccented ASCII snake_case."""
    nfkd_form = unicodedata.normalize("NFKD", text)
    unaccented = "".join(c for c in nfkd_form if not unicodedata.combining(c))
    unaccented = unaccented.replace("đ", "d").replace("Đ", "D")
    cleaned = re.sub(r"[\s\-_]+", "_", unaccented.strip().upper())
    return cleaned.strip("_")


@functools.lru_cache(maxsize=4096)
def canonical_doc_slug(doc_code: str) -> str:
    """Returns the canonical dot-separated ltree document slug dynamically."""
    if not doc_code or not doc_code.strip():
        return "doc_root"

    raw = doc_code.strip()
    if raw.lower().startswith("doc_"):
        raw = raw[4:]

    transliterated = raw.replace("đ", "d").replace("Đ", "D")
    normalized = unicodedata.normalize("NFKD", transliterated)
    ascii_text = "".join(c for c in normalized if not unicodedata.combining(c)).strip()
    ascii_upper = ascii_text.upper()

    qcvn_match = re.search(r"\b(QCVN|TCVN)\s*([0-9]+)\s*:\s*([0-9]{4})", ascii_upper)
    if qcvn_match:
        std_type = qcvn_match.group(1).lower()
        std_num = qcvn_match.group(2)
        std_year = qcvn_match.group(3)
        return f"doc_{std_type}_{std_num}_{std_year}"

    law_match = re.search(r"\bLUAT\s+([A-Z0-9_]+)\s*([0-9]{4})\b", ascii_upper)
    if law_match:
        law_abbr = re.sub(r"[^a-zA-Z0-9]+", "_", law_match.group(1).lower()).strip("_")
        law_year = law_match.group(2)
        return f"doc_luat_{law_abbr}_{law_year}"

    num_match = re.search(r"([0-9]+)/([0-9]{4})/([A-Z0-9\-]+)", ascii_upper)
    if num_match:
        num = num_match.group(1)
        year = num_match.group(2)
        auth = re.sub(r"[^A-Z0-9]+", "_", num_match.group(3)).strip("_").lower()
        return f"doc_{num}_{year}_{auth}"

    clean = re.sub(r"[^a-zA-Z0-9_]+", "_", ascii_text.lower()).strip("_")
    clean = re.sub(r"_+", "_", clean)
    return f"doc_{clean or 'root'}"


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

        if "." in clean_val and "," in clean_val:
            clean_val = clean_val.replace(".", "").replace(",", ".")
        elif "," in clean_val:
            clean_val = clean_val.replace(",", ".")
        elif "." in clean_val:
            parts = clean_val.split(".")
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
    demerit_points: int | None = Field(
        default=None,
        ge=0,
        le=12,
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
    points_deducted: int = Field(
        default=0, ge=0, le=12, description="Exact points deducted from 12-point license bank"
    )
    legal_basis: str = Field(
        default="",
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
    document_type: str = Field(
        default="NGHI_DINH", description="Statutory instrument type (e.g. LUAT, NGHI_DINH, THONG_TU, QUY_CHUAN_KY_THUAT)"
    )

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
        """Constructs full hierarchical Vietnamese statutory citation label."""
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
