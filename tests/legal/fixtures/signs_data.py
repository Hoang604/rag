"""Authoritative QCVN 41:2019 sign catalog test data."""

from __future__ import annotations

from dataclasses import dataclass, field

from rag_eval.legal.schemas import SignCategoryEnum


@dataclass(frozen=True)
class SignDefinition:
    sign_code: str
    sign_name: str
    category: SignCategoryEnum
    shape: str
    primary_color: str
    meaning: str
    placement_rules: str
    penalty_references: list[str] = field(default_factory=list)


SIGN_P102 = SignDefinition(
    sign_code="P.102",
    sign_name="Cấm đi ngược chiều",
    category=SignCategoryEnum.PROHIBITORY,
    shape="TRÒN",
    primary_color="ĐỎ_TRẮNG",
    meaning="Báo đường cấm tất cả các loại xe (cơ giới và thô sơ) đi vào theo chiều đặt biển, trừ các xe được ưu tiên theo quy định.",
    placement_rules="Đặt ở đầu đường một chiều hoặc nhánh vào theo chiều ngược dòng giao thông.",
    penalty_references=[
        "doc_nd100_2019.c2.s1.a5.c5.p_c",
        "doc_nd100_2019.c2.s1.a6.c8.p_a",
    ],
)

SIGN_P106A = SignDefinition(
    sign_code="P.106a",
    sign_name="Cấm xe ô tô tải",
    category=SignCategoryEnum.PROHIBITORY,
    shape="TRÒN",
    primary_color="ĐỎ_TRẮNG_ĐEN",
    meaning="Báo đường cấm các loại xe ô tô tải trừ các xe được ưu tiên theo quy định. Biển có hiệu lực cấm đối với cả máy kéo và xe máy chuyên dùng.",
    placement_rules="Đặt ở đầu đường cấm xe tải.",
    penalty_references=["doc_nd100_2019.c2.s1.a5.c4.p_b"],
)

SIGN_P130 = SignDefinition(
    sign_code="P.130",
    sign_name="Cấm dừng xe và đỗ xe",
    category=SignCategoryEnum.PROHIBITORY,
    shape="TRÒN",
    primary_color="XANH_ĐỎ",
    meaning="Báo nơi cấm dừng xe và đỗ xe. Biển có hiệu lực cấm các loại xe cơ giới dừng và đỗ ở phía đường có đặt biển.",
    placement_rules="Đặt dọc theo chiều đi của đoạn đường cần cấm dừng và đỗ.",
    penalty_references=[
        "doc_nd100_2019.c2.s1.a5.c3.p_h",
        "doc_nd100_2019.c2.s1.a6.c2.p_h",
    ],
)

SIGN_P131A = SignDefinition(
    sign_code="P.131a",
    sign_name="Cấm đỗ xe",
    category=SignCategoryEnum.PROHIBITORY,
    shape="TRÒN",
    primary_color="XANH_ĐỎ",
    meaning="Báo nơi cấm đỗ xe cơ giới, được phép dừng xe trong khoảng thời gian nhất định.",
    placement_rules="Đặt dọc theo chiều đi của đoạn đường cần cấm đỗ.",
    penalty_references=["doc_nd100_2019.c2.s1.a5.c2.p_h"],
)

SIGN_R412A = SignDefinition(
    sign_code="R.412a",
    sign_name="Làn đường dành riêng cho xe ô tô khách",
    category=SignCategoryEnum.MANDATORY,
    shape="CHỮ_NHẬT",
    primary_color="XANH_TRẮNG",
    meaning="Báo hiệu làn đường dành riêng cho ô tô khách. Các loại phương tiện khác không được đi vào làn đường này.",
    placement_rules="Đặt ở đầu làn đường hoặc treo trên giá long môn.",
    penalty_references=["doc_nd100_2019.c2.s1.a5.c5.p_g"],
)

SIGN_R420 = SignDefinition(
    sign_code="R.420",
    sign_name="Bắt đầu khu đông dân cư",
    category=SignCategoryEnum.MANDATORY,
    shape="CHỮ_NHẬT",
    primary_color="XANH_TRẮNG",
    meaning="Báo hiệu bắt đầu đoạn đường qua khu đông dân cư, áp dụng tốc độ tối đa theo Thông tư 31/2019.",
    placement_rules="Đặt ở vị trí bắt đầu vào khu đông dân cư.",
    penalty_references=["doc_tt31_2019.a6"],
)

SIGN_W207A = SignDefinition(
    sign_code="W.207a",
    sign_name="Giao nhau với đường không ưu tiên",
    category=SignCategoryEnum.WARNING,
    shape="TAM_GIÁC_ĐỀU",
    primary_color="VÀNG_ĐEN_ĐỎ",
    meaning="Báo trước sắp đến nơi giao nhau với đường không ưu tiên, xe chạy trên đường này được quyền ưu tiên qua nơi giao nhau.",
    placement_rules="Đặt trước nơi giao nhau ở cự ly theo quy chuẩn ngoài hoặc trong đô thị.",
    penalty_references=[],
)

MARKING_1_1 = SignDefinition(
    sign_code="M.1.1",
    sign_name="Vạch đơn nét liền màu trắng",
    category=SignCategoryEnum.ROAD_MARKING,
    shape="VẠCH_SƠN",
    primary_color="TRẮNG",
    meaning="Dùng để phân chia các làn xe cùng chiều; xe không được lấn làn hoặc đè lên vạch.",
    placement_rules="Kẻ trên mặt đường bê tông hoặc nhựa đường.",
    penalty_references=["doc_nd100_2019.c2.s1.a5.c1.p_a"],
)

ALL_SIGN_CATALOG: list[SignDefinition] = [
    SIGN_P102,
    SIGN_P106A,
    SIGN_P130,
    SIGN_P131A,
    SIGN_R412A,
    SIGN_R420,
    SIGN_W207A,
    MARKING_1_1,
]
