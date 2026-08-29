"""Authoritative statutory test data derived directly from docs/ specifications.

Includes Law 2008 & Law 36/2024, Decrees 100/2019, 123/2021, 168/2024, Circular 31/2019.
"""

from __future__ import annotations

from rag_eval.legal.schemas import (
    ActorCategory,
    AdditionalSanctions,
    CanonicalFullyQualifiedChunk,
    ExceptionMetadata,
    FineBounds,
    NormRole,
    VehicleCategory,
    ViolationCategory,
    ViolationType,
)

# 1. Decree 100/2019 Article 5 (Automobiles)
DECREE_100_ART5_CL3_PTA = CanonicalFullyQualifiedChunk(
    chunk_id="chk_nd100_art5_cl3_pta",
    document_id="doc_nd100",
    document_code="100/2019/ND-CP",
    hierarchy_path="doc_nd100_2019.c2.s1.a5.c3.p_a",
    article_number=5,
    article_index="Điều 5",
    clause_number=3,
    point_letter="a",
    synthesized_prefix="Nghị định 100/2019/NĐ-CP > Điều 5 (Xe ô tô) > Khoản 3 > Điểm a",
    lead_sentence="Phạt tiền từ 800.000 đồng đến 1.000.000 đồng đối với người điều khiển xe thực hiện một trong các hành vi vi phạm sau đây:",
    verbatim_text="a) Không chấp hành hiệu lệnh của đèn tín hiệu giao thông;",
    contextualized_text=(
        "Nghị định 100/2019/NĐ-CP > Điều 5 (Xe ô tô) > Khoản 3 (Phạt tiền từ 800.000đ đến 1.000.000đ) "
        "> Điểm a: Không chấp hành hiệu lệnh của đèn tín hiệu giao thông"
    ),
    norm_role=NormRole.SANCTION_PRINCIPAL,
    primary_actor=ActorCategory.DRIVER,
    vehicle_types=[
        VehicleCategory.CAR_PASSENGER,
        VehicleCategory.CAR_TRUCK,
        VehicleCategory.CAR_BUS,
        VehicleCategory.CAR_TRACTOR,
    ],
    violation_categories=[ViolationCategory.SIGNAL_COMPLIANCE],
    violation_types=[ViolationType.RED_LIGHT],
    fine_bounds=FineBounds(
        min_fine_vnd=800000, max_fine_vnd=1000000, average_fine_vnd=900000
    ),
    additional_sanctions=AdditionalSanctions(
        license_suspension_months_min=1,
        license_suspension_months_max=3,
        vehicle_impoundment_days=0,
        demerit_points=2,
    ),
    exceptions_and_overrides=ExceptionMetadata(
        has_exception=True,
        exception_type="EMERGENCY_VEHICLE",
        exception_clause_text="Trừ các xe ưu tiên đang đi làm nhiệm vụ khẩn cấp",
        overridden_by=["POLICE_COMMAND", "EMERGENCY_MISSION"],
        exempt_vehicle_categories=[VehicleCategory.PRIORITY_VEHICLE],
    ),
    effective_date="2020-01-15",
    expiry_date=None,
    is_active=True,
)

# 2. Decree 100/2019 Article 6 (Motorcycles)
DECREE_100_ART6_CL4_PTE = CanonicalFullyQualifiedChunk(
    chunk_id="chk_nd100_art6_cl4_pte",
    document_id="doc_nd100",
    document_code="100/2019/ND-CP",
    hierarchy_path="doc_nd100_2019.c2.s1.a6.c4.p_e",
    article_number=6,
    article_index="Điều 6",
    clause_number=4,
    point_letter="e",
    synthesized_prefix="Nghị định 100/2019/NĐ-CP > Điều 6 (Xe mô tô, xe gắn máy) > Khoản 4 > Điểm e",
    lead_sentence="Phạt tiền từ 800.000 đồng đến 1.000.000 đồng đối với người điều khiển xe thực hiện một trong các hành vi vi phạm sau đây:",
    verbatim_text="e) Không chấp hành hiệu lệnh của đèn tín hiệu giao thông;",
    contextualized_text=(
        "Nghị định 100/2019/NĐ-CP > Điều 6 (Xe mô tô, xe gắn máy) > Khoản 4 (Phạt 800.000đ - 1.000.000đ) "
        "> Điểm e: Không chấp hành hiệu lệnh của đèn tín hiệu giao thông"
    ),
    norm_role=NormRole.SANCTION_PRINCIPAL,
    primary_actor=ActorCategory.DRIVER,
    vehicle_types=[
        VehicleCategory.MOTORCYCLE,
        VehicleCategory.MOPED,
        VehicleCategory.E_MOPED,
    ],
    violation_categories=[ViolationCategory.SIGNAL_COMPLIANCE],
    violation_types=[ViolationType.RED_LIGHT],
    fine_bounds=FineBounds(
        min_fine_vnd=800000, max_fine_vnd=1000000, average_fine_vnd=900000
    ),
    additional_sanctions=AdditionalSanctions(
        license_suspension_months_min=1,
        license_suspension_months_max=3,
        vehicle_impoundment_days=0,
        demerit_points=2,
    ),
    exceptions_and_overrides=ExceptionMetadata(
        has_exception=True,
        exception_type="EMERGENCY_VEHICLE",
        exception_clause_text="Trừ trường hợp xe ưu tiên",
        overridden_by=["POLICE_COMMAND"],
        exempt_vehicle_categories=[VehicleCategory.PRIORITY_VEHICLE],
    ),
    effective_date="2020-01-15",
    expiry_date=None,
    is_active=True,
)

# 3. Decree 100/2019 Art 6 Cl 8 Pt a (Motorcycle opposite direction on one-way road)
DECREE_100_ART6_CL8_PTA = CanonicalFullyQualifiedChunk(
    chunk_id="chk_nd100_art6_cl8_pta",
    document_id="doc_nd100",
    document_code="100/2019/ND-CP",
    hierarchy_path="doc_nd100_2019.c2.s1.a6.c8.p_a",
    article_number=6,
    article_index="Điều 6",
    clause_number=8,
    point_letter="a",
    synthesized_prefix="Nghị định 100/2019/NĐ-CP > Điều 6 (Xe mô tô, xe gắn máy) > Khoản 8 > Điểm a",
    lead_sentence="Phạt tiền từ 1.000.000 đồng đến 2.000.000 đồng đối với người điều khiển xe thực hiện một trong các hành vi vi phạm sau đây:",
    verbatim_text="a) Đi ngược chiều của đường một chiều, đi ngược chiều trên đường có biển 'Cấm đi ngược chiều';",
    contextualized_text=(
        "Nghị định 100/2019/NĐ-CP > Điều 6 (Xe mô tô, xe gắn máy) > Khoản 8 (Phạt 1.000.000đ - 2.000.000đ) "
        "> Điểm a: Đi ngược chiều của đường một chiều, đi ngược chiều trên đường có biển Cấm đi ngược chiều"
    ),
    norm_role=NormRole.SANCTION_PRINCIPAL,
    primary_actor=ActorCategory.DRIVER,
    vehicle_types=[
        VehicleCategory.MOTORCYCLE,
        VehicleCategory.MOPED,
        VehicleCategory.E_MOPED,
    ],
    violation_categories=[ViolationCategory.LANE_DIRECTION],
    violation_types=[ViolationType.OPPOSITE_DIRECTION],
    fine_bounds=FineBounds(
        min_fine_vnd=1000000, max_fine_vnd=2000000, average_fine_vnd=1500000
    ),
    additional_sanctions=AdditionalSanctions(
        license_suspension_months_min=2,
        license_suspension_months_max=4,
        vehicle_impoundment_days=0,
        demerit_points=3,
    ),
    exceptions_and_overrides=ExceptionMetadata(
        has_exception=True,
        exception_type="EMERGENCY_VEHICLE",
        exception_clause_text="Trừ các xe ưu tiên đang đi làm nhiệm vụ",
        overridden_by=["POLICE_COMMAND"],
        exempt_vehicle_categories=[VehicleCategory.PRIORITY_VEHICLE],
    ),
    effective_date="2020-01-15",
    expiry_date=None,
    is_active=True,
)

# 4. Speeding Bracket 10-20 km/h for Passenger Car (Decree 100 Art 5 Cl 5 Pt i amended by NĐ 123)
DECREE_100_ART5_CL5_PTI = CanonicalFullyQualifiedChunk(
    chunk_id="chk_nd100_art5_cl5_pti",
    document_id="doc_nd100",
    document_code="100/2019/ND-CP",
    hierarchy_path="doc_nd100_2019.c2.s1.a5.c5.p_i",
    article_number=5,
    article_index="Điều 5",
    clause_number=5,
    point_letter="i",
    synthesized_prefix="Nghị định 100/2019/NĐ-CP (Sửa đổi bởi NĐ 123/2021) > Điều 5 (Xe ô tô) > Khoản 5 > Điểm i",
    lead_sentence="Phạt tiền từ 4.000.000 đồng đến 6.000.000 đồng đối với người điều khiển xe thực hiện một trong các hành vi vi phạm sau đây:",
    verbatim_text="i) Điều khiển xe chạy quá tốc độ quy định từ 10 km/h đến 20 km/h;",
    contextualized_text=(
        "Nghị định 100/2019/NĐ-CP (Sửa đổi bởi NĐ 123/2021) > Điều 5 (Xe ô tô) > Khoản 5 "
        "(Phạt tiền từ 4.000.000đ đến 6.000.000đ) > Điểm i: Điều khiển xe chạy quá tốc độ quy định từ 10 km/h đến 20 km/h"
    ),
    norm_role=NormRole.SANCTION_PRINCIPAL,
    primary_actor=ActorCategory.DRIVER,
    vehicle_types=[
        VehicleCategory.CAR_PASSENGER,
        VehicleCategory.CAR_TRUCK,
        VehicleCategory.CAR_BUS,
        VehicleCategory.CAR_TRACTOR,
    ],
    violation_categories=[ViolationCategory.SPEED_DISTANCE],
    violation_types=[ViolationType.SPEED_OVER_10_20],
    fine_bounds=FineBounds(
        min_fine_vnd=4000000, max_fine_vnd=6000000, average_fine_vnd=5000000
    ),
    additional_sanctions=AdditionalSanctions(
        license_suspension_months_min=1,
        license_suspension_months_max=3,
        vehicle_impoundment_days=0,
        demerit_points=2,
    ),
    exceptions_and_overrides=ExceptionMetadata(
        has_exception=True,
        exception_type="EMERGENCY_VEHICLE",
        exception_clause_text="Trừ trường hợp xe ưu tiên đang đi làm nhiệm vụ",
        overridden_by=["POLICE_COMMAND"],
        exempt_vehicle_categories=[VehicleCategory.PRIORITY_VEHICLE],
    ),
    effective_date="2022-01-01",
    expiry_date=None,
    is_active=True,
)

# 5. Alcohol Bracket 3 (> 80 mg/100ml or > 0.40 mg/L) for Automobile (Decree 100 Art 5 Cl 10 Pt a)
DECREE_100_ART5_CL10_PTA = CanonicalFullyQualifiedChunk(
    chunk_id="chk_nd100_art5_cl10_pta",
    document_id="doc_nd100",
    document_code="100/2019/ND-CP",
    hierarchy_path="doc_nd100_2019.c2.s1.a5.c10.p_a",
    article_number=5,
    article_index="Điều 5",
    clause_number=10,
    point_letter="a",
    synthesized_prefix="Nghị định 100/2019/NĐ-CP > Điều 5 (Xe ô tô) > Khoản 10 > Điểm a",
    lead_sentence="Phạt tiền từ 30.000.000 đồng đến 40.000.000 đồng đối với người điều khiển xe thực hiện một trong các hành vi vi phạm sau đây:",
    verbatim_text="a) Điều khiển xe trên đường mà trong máu hoặc hơi thở có nồng độ cồn vượt quá 80 miligam/100 mililít máu hoặc vượt quá 0,4 miligam/1 lít khí thở;",
    contextualized_text=(
        "Nghị định 100/2019/NĐ-CP > Điều 5 (Xe ô tô) > Khoản 10 (Phạt tiền từ 30.000.000đ đến 40.000.000đ) "
        "> Điểm a: Điều khiển xe mà nồng độ cồn vượt quá 80 mg/100 ml máu hoặc vượt quá 0.4 mg/1 l khí thở"
    ),
    norm_role=NormRole.SANCTION_PRINCIPAL,
    primary_actor=ActorCategory.DRIVER,
    vehicle_types=[
        VehicleCategory.CAR_PASSENGER,
        VehicleCategory.CAR_TRUCK,
        VehicleCategory.CAR_BUS,
        VehicleCategory.CAR_TRACTOR,
    ],
    violation_categories=[ViolationCategory.ALCOHOL_DRUGS],
    violation_types=[ViolationType.ALC_BRACKET_3],
    fine_bounds=FineBounds(
        min_fine_vnd=30000000, max_fine_vnd=40000000, average_fine_vnd=35000000
    ),
    additional_sanctions=AdditionalSanctions(
        license_suspension_months_min=22,
        license_suspension_months_max=24,
        vehicle_impoundment_days=7,
        demerit_points=12,
    ),
    exceptions_and_overrides=ExceptionMetadata(has_exception=False),
    effective_date="2020-01-15",
    expiry_date=None,
    is_active=True,
)

# 6. Commercial Truck Overloading 20-50% (Decree 100 Art 24 Cl 5 Pt a amended by NĐ 123)
DECREE_100_ART24_CL5_PTA = CanonicalFullyQualifiedChunk(
    chunk_id="chk_nd100_art24_cl5_pta",
    document_id="doc_nd100",
    document_code="100/2019/ND-CP",
    hierarchy_path="doc_nd100_2019.c2.s2.a24.c5.p_a",
    article_number=24,
    article_index="Điều 24",
    clause_number=5,
    point_letter="a",
    synthesized_prefix="Nghị định 100/2019/NĐ-CP (Sửa đổi bởi NĐ 123/2021) > Điều 24 (Xử phạt xe ô tô tải) > Khoản 5 > Điểm a",
    lead_sentence="Phạt tiền từ 6.000.000 đồng đến 8.000.000 đồng đối với người điều khiển xe thực hiện một trong các hành vi vi phạm sau đây:",
    verbatim_text="a) Chở hàng vượt trọng tải (khối lượng hàng chuyên chở cho phép tham gia giao thông) được ghi trong Giấy chứng nhận kiểm định an toàn kỹ thuật và bảo vệ môi trường của xe trên 20% đến 50%;",
    contextualized_text=(
        "Nghị định 100/2019/NĐ-CP > Điều 24 (Xử phạt xe ô tô tải) > Khoản 5 (Phạt tiền từ 6.000.000đ đến 8.000.000đ) "
        "> Điểm a: Chở hàng vượt trọng tải trên 20% đến 50%"
    ),
    norm_role=NormRole.SANCTION_PRINCIPAL,
    primary_actor=ActorCategory.DRIVER,
    vehicle_types=[VehicleCategory.CAR_TRUCK, VehicleCategory.CAR_TRACTOR],
    violation_categories=[ViolationCategory.LOAD_PASSENGER],
    violation_types=[ViolationType.OVERLOAD_VEHICLE],
    fine_bounds=FineBounds(
        min_fine_vnd=6000000, max_fine_vnd=8000000, average_fine_vnd=7000000
    ),
    additional_sanctions=AdditionalSanctions(
        license_suspension_months_min=1,
        license_suspension_months_max=3,
        vehicle_impoundment_days=0,
        demerit_points=3,
    ),
    exceptions_and_overrides=ExceptionMetadata(has_exception=False),
    effective_date="2022-01-01",
    expiry_date=None,
    is_active=True,
)

# 7. Circular 31/2019/TT-BGTVT Speed limits in populated areas
CIRCULAR_31_ART6 = CanonicalFullyQualifiedChunk(
    chunk_id="chk_tt31_art6",
    document_id="doc_tt31",
    document_code="31/2019/TT-BGTVT",
    hierarchy_path="doc_tt31_2019.a6",
    article_number=6,
    article_index="Điều 6",
    clause_number=1,
    point_letter=None,
    synthesized_prefix="Thông tư 31/2019/TT-BGTVT > Điều 6",
    lead_sentence="Tốc độ tối đa cho phép xe cơ giới tham gia giao thông trong khu vực đông dân cư (trừ đường cao tốc):",
    verbatim_text="1. Tại đường đôi; đường một chiều có từ hai làn xe cơ giới trở lên: tối đa 60 km/h.\n2. Tại đường hai chiều; đường một chiều có một làn xe cơ giới: tối đa 50 km/h.",
    contextualized_text=(
        "Thông tư 31/2019/TT-BGTVT > Điều 6: Tốc độ tối đa trong khu vực đông dân cư: "
        "Đường đôi/đường một chiều >=2 làn: 60 km/h; Đường hai chiều không có dải phân cách/đường 1 làn: 50 km/h"
    ),
    norm_role=NormRole.PRESCRIPTION_DUTY,
    primary_actor=ActorCategory.DRIVER,
    vehicle_types=[
        VehicleCategory.CAR_PASSENGER,
        VehicleCategory.CAR_TRUCK,
        VehicleCategory.CAR_BUS,
        VehicleCategory.CAR_TRACTOR,
        VehicleCategory.MOTORCYCLE,
        VehicleCategory.MOPED,
    ],
    violation_categories=[ViolationCategory.SPEED_DISTANCE],
    violation_types=[],
    fine_bounds=FineBounds(),
    additional_sanctions=AdditionalSanctions(),
    exceptions_and_overrides=ExceptionMetadata(has_exception=False),
    effective_date="2019-10-15",
    expiry_date=None,
    is_active=True,
)

# Authoritative collection
ALL_STATUTORY_CHUNKS: list[CanonicalFullyQualifiedChunk] = [
    DECREE_100_ART5_CL3_PTA,
    DECREE_100_ART6_CL4_PTE,
    DECREE_100_ART6_CL8_PTA,
    DECREE_100_ART5_CL5_PTI,
    DECREE_100_ART5_CL10_PTA,
    DECREE_100_ART24_CL5_PTA,
    CIRCULAR_31_ART6,
]
