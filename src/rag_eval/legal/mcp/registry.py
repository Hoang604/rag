from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from rag_eval.legal.mcp.tools import (
    LegalMCPTools,
)
from rag_eval.legal.schemas.domain import (
    HIERARCHICAL_DIRECTION_DESCRIPTION,
    GraphDirection,
    HierarchicalDirection,
    RelationEdge,
    RelationEdgeFilter,
    StagingChunkDelta,
    StagingStatus,
    StatutoryRelationType,
)
from rag_eval.legal.schemas.retrieval import (
    GraphTraverseResult,
    GrepResult,
    HierarchicalNavigateResult,
    RawTextResult,
    SearchResult,
)
from rag_eval.legal.schemas.staging import (
    BatchPatchResult,
    FinalizeChunksResult,
    MutationResult,
    PendingChunksResult,
    PreFlightValidationResponse,
    ReparentSubtreeResult,
    SessionStatusResult,
    StagedChunkDetail,
    StgGrepResponse,
    StgListSessionsResponse,
    UnfinalizeChunksResult,
)

_EMPTY_STR_LIST: list[str] = []
_EMPTY_CHUNK_DELTAS: list[StagingChunkDelta] = []
_EMPTY_METADATA_DICT: dict[str, object] = {}


def register_legal_mcp_tools(server: MCPServer, tool_impl: LegalMCPTools) -> None:
    """Registers all 19 canonical legal tools (4 runtime sensors and 15 staging tools) onto the MCPServer instance."""

    @server.tool(
        name="hybrid_search",
        description=(
            "Truy xuất các đoạn quy phạm pháp luật giao thông đường bộ (quy tắc hành vi, điều kiện an toàn, "
            "tiêu chuẩn phương tiện, người điều khiển, thẩm quyền kiểm soát, tổ chức hạ tầng, định nghĩa và chế tài) "
            "thông qua kết hợp xếp hạng ngữ nghĩa (Dense Vector) và đối sánh từ khóa quy phạm (Sparse Full-Text Search RRF)."
        ),
    )
    async def hybrid_search(
        query: Annotated[
            str,
            Field(
                description=(
                    "Truy vấn quy phạm chuẩn hóa: Chuyển hóa câu hỏi hoặc tình huống thành tổ hợp "
                    "[Thực thể pháp lý] (chủ thể, loại phương tiện, đối tượng quản lý) + [Mệnh đề quy phạm] (quy tắc, "
                    "tiêu chuẩn, thẩm quyền, điều kiện, hoặc hành vi vi phạm) theo thuật ngữ văn bản luật. "
                    "Quy tắc bắt buộc: "
                    "(1) Thay thế khẩu ngữ bằng thuật ngữ luật tương đương nhưng giữ lại từ khóa hành vi cốt lõi để kích hoạt đồng thời Dense và Sparse search; "
                    "(2) Quy đổi số liệu đo lường cụ thể thành khung định lượng luật định; "
                    "(3) Loại bỏ toàn bộ từ đệm xưng hô, cảm xúc và giao tiếp; "
                    "(4) KHÔNG đưa mốc thời gian vào query (bắt buộc dùng temporal_violation_date)."
                ),
                examples=[
                    "không chấp hành hiệu lệnh của đèn tín hiệu giao thông xe máy vượt đèn vàng",
                    "người điều khiển xe ô tô chạy quá tốc độ quy định từ 10 km/h đến 20 km/h",
                    "quy tắc nhường đường tại nơi đường giao nhau không có báo hiệu đi theo vòng xuyến",
                ],
            ),
        ],
        temporal_violation_date: Annotated[
            str,
            Field(
                default="",
                description="Ngày xảy ra hành vi vi phạm (định dạng YYYY-MM-DD hoặc 'ngày DD tháng MM năm YYYY') để đánh giá hiệu lực văn bản pháp luật tại đúng thời điểm đó. Để trống để dùng ngày hiện tại theo giờ Việt Nam.",
                examples=["2020-01-15", "2024-06-01", "ngày 15 tháng 01 năm 2020"],
            ),
        ] = "",
        limit: Annotated[
            int,
            Field(
                default=10,
                ge=1,
                le=50,
                description="Số lượng điều khoản quy phạm tối đa cần trả về, được sắp xếp theo điểm hòa trộn tương đồng giảm dần.",
            ),
        ] = 10,
        doc_codes: Annotated[
            list[str],
            Field(
                description="Giới hạn phạm vi tìm kiếm trong một số văn bản nhất định, dùng mã văn bản. Để danh sách rỗng để tìm trên toàn bộ kho.",
                examples=[["168/2024/ND-CP"], ["168/2024/ND-CP", "100/2019/ND-CP"]],
            ),
        ] = _EMPTY_STR_LIST,
        path_prefix: Annotated[
            str,
            Field(
                default="",
                description="Tiền tố đường dẫn phân cấp tùy chọn để giới hạn phạm vi tìm kiếm theo phân cấp (ví dụ: '100_2019_nd_cp.c_ii').",
                examples=["100_2019_nd_cp.c_ii", "100_2019_nd_cp.a_5"],
            ),
        ] = "",
        rerank: Annotated[
            bool,
            Field(
                default=False,
                description="Bật hoặc tắt bước xếp hạng lại bằng mô hình ngôn ngữ sâu. Mặc định tắt. Bước này bị tự động tắt với truy vấn gõ không dấu.",
            ),
        ] = False,
    ) -> SearchResult:
        return await tool_impl.hybrid_search(
            query=query,
            temporal_violation_date=temporal_violation_date or None,
            limit=limit,
            doc_codes=doc_codes or None,
            path_prefix=path_prefix or None,
            rerank=rerank or None,
        )

    @server.tool(
        name="verbatim_grep",
        description=(
            "Tìm kiếm chính xác tuyệt đối theo chuỗi nguyên văn hoặc biểu thức chính quy POSIX "
            "trên kho quy phạm pháp luật giao thông. Dùng làm điểm neo chuẩn xác cao để từ đó phối hợp "
            "với hierarchical_navigate (mở rộng toàn văn Điều) hoặc graph_traverse (duyệt dẫn chiếu). "
            "Ưu tiên sử dụng thay cho hybrid_search khi đã xác định được thuật ngữ quy phạm đặc thù, số hiệu văn bản, "
            "số hiệu Điều/Khoản, mã hiệu biển báo/quy chuẩn hoặc cần quét cấu trúc cú pháp lập pháp."
        ),
    )
    async def verbatim_grep(
        pattern: Annotated[
            str,
            Field(
                description=(
                    "Điểm neo tìm kiếm chính xác: Chuỗi ký tự nguyên văn đặc trưng hoặc biểu thức chính quy POSIX "
                    "(số hiệu văn bản, số Điều/Khoản, mã hiệu biển báo, cụm từ quy phạm đặc thù, hoặc mẫu cú pháp luật). "
                    "Quy tắc bắt buộc: "
                    "(1) Chỉ truyền cụm từ khóa ngắn mang tính nhận diện độc bản; "
                    "(2) TUYỆT ĐỐI KHÔNG truyền cả câu hỏi đàm thoại tự nhiên (sẽ gây 0 kết quả); "
                    "(3) Bật is_regex=True khi cần quét các biến thể định lượng (khung tiền, tốc độ) hoặc cấu trúc mẫu; "
                    "(4) Tách riêng mốc thời gian sang temporal_violation_date."
                ),
                examples=[
                    "không chấp hành hiệu lệnh của đèn tín hiệu giao thông",
                    "100/2019/NĐ-CP",
                    "P.123a",
                    "tước quyền sử dụng giấy phép lái xe từ [0-9]+ đến [0-9]+ tháng",
                ],
            ),
        ],
        doc_codes: Annotated[
            list[str],
            Field(
                description="Giới hạn phạm vi tìm kiếm trong một số văn bản nhất định, dùng mã văn bản. Để danh sách rỗng để tìm trên toàn bộ kho.",
                examples=[["100/2019/NĐ-CP"]],
            ),
        ] = _EMPTY_STR_LIST,
        path_prefix: Annotated[
            str,
            Field(
                default="",
                description="Tiền tố đường dẫn phân cấp tùy chọn để giới hạn phạm vi tìm kiếm theo phân cấp (ví dụ: '100_2019_nd_cp.c_ii').",
                examples=["100_2019_nd_cp.c_ii"],
            ),
        ] = "",
        is_regex: Annotated[
            bool,
            Field(
                default=False,
                description="Bật chế độ đánh giá biểu thức chính quy POSIX đối với chuỗi tìm kiếm.",
            ),
        ] = False,
        case_sensitive: Annotated[
            bool,
            Field(
                default=False,
                description="Bắt buộc phân biệt chữ hoa chữ thường khi so khớp chuỗi.",
            ),
        ] = False,
        temporal_violation_date: Annotated[
            str,
            Field(
                default="",
                description="Ngày xảy ra vi phạm (định dạng YYYY-MM-DD hoặc tiếng Việt) để lọc hiệu lực văn bản tại thời điểm đó. Để trống để dùng ngày hiện tại.",
            ),
        ] = "",
        limit: Annotated[
            int,
            Field(
                default=20,
                ge=1,
                le=100,
                description="Số lượng kết quả khớp tối đa cần trả về.",
            ),
        ] = 20,
    ) -> GrepResult:
        return await tool_impl.verbatim_grep(
            pattern=pattern,
            doc_codes=doc_codes or None,
            path_prefix=path_prefix or None,
            is_regex=is_regex,
            case_sensitive=case_sensitive,
            temporal_violation_date=temporal_violation_date or None,
            limit=limit,
        )

    @server.tool(
        name="hierarchical_navigate",
        description=(
            "Điều hướng cấu trúc cây phân cấp văn bản pháp luật (Văn bản -> Chương -> Mục -> Điều -> Khoản -> Điểm -> Phụ lục) "
            "xoay quanh một nút quy phạm được chỉ định. "
            "Dùng để mở rộng ngữ cảnh trọn vẹn một Điều luật (FULL_ARTICLE) hoặc duyệt con trỏ cú pháp (CHILDREN, PARENT_CHAIN, SIBLINGS). "
            "Kết quả trả về danh sách phẳng các đoạn quy phạm được sắp xếp theo đúng thứ tự đọc văn bản kèm relative_depth."
        ),
    )
    async def hierarchical_navigate(
        path: Annotated[
            str,
            Field(
                description="Đường dẫn cây phân cấp của nút quy phạm mục tiêu (ví dụ '100_2019_nd_cp.c_ii.a_5.c_3.p_a' hoặc '100_2019_nd_cp.a_5').",
                examples=["100_2019_nd_cp.c_ii.a_5.c_3.p_a", "100_2019_nd_cp.a_5"],
            ),
        ],
        direction: Annotated[
            HierarchicalDirection,
            Field(
                default=HierarchicalDirection.FULL_ARTICLE,
                description=HIERARCHICAL_DIRECTION_DESCRIPTION,
            ),
        ] = HierarchicalDirection.FULL_ARTICLE,
    ) -> HierarchicalNavigateResult:
        return await tool_impl.hierarchical_navigate(
            path=path,
            direction=direction,
        )

    @server.tool(
        name="graph_traverse",
        description="Duyệt đồ thị tri thức pháp lý đệ quy qua các liên kết quan hệ giữa các quy định pháp luật (dẫn chiếu văn bản, hình thức xử phạt bổ sung, quy chuẩn kỹ thuật).",
    )
    async def graph_traverse(
        source_path: Annotated[
            str,
            Field(
                description="Đường dẫn cây phân cấp của nút quy phạm gốc bắt đầu duyệt.",
                examples=["100_2019_nd_cp.c_ii.a_5.c_3.p_a", "100_2019_nd_cp.a_5"],
            ),
        ],
        direction: Annotated[
            GraphDirection,
            Field(
                default="OUTGOING",
                description="Hướng duyệt đồ thị: 'OUTGOING' (các liên kết do nút này trỏ tới), 'INCOMING' (các quy định khác trỏ tới nút này), 'BOTH' (duyệt cả hai hướng).",
            ),
        ] = "OUTGOING",
        max_depth: Annotated[
            int,
            Field(
                default=2,
                ge=1,
                le=4,
                description="Độ sâu bước nhảy tối đa trên đồ thị quan hệ.",
            ),
        ] = 2,
        filter_relations: Annotated[
            list[StatutoryRelationType] | None,
            Field(
                default=None,
                description="Lọc danh sách các loại quan hệ cần duyệt (ví dụ: ['REFERENCES', 'SANCTIONS']). Để trống để duyệt tất cả.",
                examples=[["REFERENCES", "SANCTIONS"]],
            ),
        ] = None,
    ) -> GraphTraverseResult:
        return await tool_impl.graph_traverse(
            source_path=source_path,
            direction=direction,
            max_depth=max_depth,
            filter_relations=filter_relations,
        )

    @server.tool(
        name="stg_get_chunk",
        description=(
            "Đọc nội dung nguyên văn (verbatim_text), ngữ cảnh phân cấp cha mẹ (parent_context breadcrumbs), "
            "siêu dữ liệu, ngày hiệu lực và danh sách cạnh quan hệ đồ thị (edges) của một đoạn quy phạm từ phiên làm việc staging theo đường dẫn phân cấp."
        ),
    )
    async def stg_get_chunk(
        doc_code: Annotated[
            str,
            Field(
                description="Số hiệu văn bản của phiên làm việc trong phiên làm việc staging.",
                examples=["100/2019/NĐ-CP"],
            ),
        ],
        path: Annotated[
            str,
            Field(
                description="Đường dẫn phân cấp chính xác của đoạn quy phạm cần đọc toàn văn.",
                examples=["100_2019_nd_cp.c_ii.a_5.c_3.p_a"],
            ),
        ],
    ) -> StagedChunkDetail:
        return await tool_impl.stg_get_chunk(doc_code=doc_code, path=path)

    @server.tool(
        name="stg_get_raw",
        description="Đọc văn bản quy phạm nguồn ban đầu được lưu trong phiên staging theo cửa sổ dòng (line window) để đối chiếu, kiểm tra và phát hiện câu chữ bị bỏ sót.",
    )
    async def stg_get_raw(
        doc_code: Annotated[
            str,
            Field(
                description="Số hiệu văn bản của phiên làm việc trong phiên làm việc staging.",
                examples=["100/2019/NĐ-CP"],
            ),
        ],
        start_line: Annotated[
            int,
            Field(
                default=1,
                ge=1,
                description="Số thứ tự dòng bắt đầu (đánh số từ 1).",
            ),
        ] = 1,
        end_line: Annotated[
            int,
            Field(
                default=100,
                ge=1,
                description="Số thứ tự dòng kết thúc (bao gồm cả dòng này).",
            ),
        ] = 100,
    ) -> RawTextResult:
        return await tool_impl.stg_get_raw(
            doc_code=doc_code, start_line=start_line, end_line=end_line
        )

    @server.tool(
        name="stg_grep",
        description="Tìm kiếm nhanh chuỗi ký tự hoặc biểu thức chính quy (Regex) xếp hạng phân tầng có trích đoạn văn cảnh highlight từ khóa.",
    )
    async def stg_grep(
        pattern: Annotated[
            str,
            Field(
                description="Cụm từ tìm kiếm, số hiệu điều khoản hoặc biểu thức chính quy (Regex).",
                examples=["khoảng cách an toàn", "vượt đèn đỏ"],
            ),
        ],
        doc_code: Annotated[
            str | None,
            Field(
                default=None,
                description="Số hiệu văn bản pháp lý. Nếu bỏ qua (None), hệ thống sẽ quét toàn bộ kho staging.",
                examples=["100/2019/NĐ-CP"],
            ),
        ] = None,
        heading_hint: Annotated[
            str | None,
            Field(
                default=None,
                description="Gợi ý tiêu đề Điều/Mục/Chương (ví dụ: 'ô tô') để cộng điểm xếp hạng.",
            ),
        ] = None,
        body_hint: Annotated[
            str | None,
            Field(
                default=None,
                description="Gợi ý nội dung Khoản/Điểm để cộng điểm xếp hạng.",
            ),
        ] = None,
        is_regex: Annotated[
            bool,
            Field(
                default=False,
                description="Bật chế độ đánh giá biểu thức chính quy Regex.",
            ),
        ] = False,
        case_sensitive: Annotated[
            bool,
            Field(
                default=False,
                description="Bắt buộc phân biệt chữ hoa chữ thường.",
            ),
        ] = False,
        limit: Annotated[
            int,
            Field(
                default=15,
                ge=1,
                le=30,
                description="Số lượng kết quả khớp tối đa cần trả về.",
            ),
        ] = 15,
    ) -> StgGrepResponse:
        return await tool_impl.stg_grep(
            pattern=pattern,
            doc_code=doc_code,
            heading_hint=heading_hint,
            body_hint=body_hint,
            is_regex=is_regex,
            case_sensitive=case_sensitive,
            limit=limit,
        )

    @server.tool(
        name="stg_patch",
        description="Thực hiện vá lỗi vi phẫu, tạo mới (upsert) hoặc xóa các đoạn quy phạm trong phiên làm việc staging. Khi đường dẫn path chưa từng tồn tại trong phiên làm việc, hệ thống sẽ tự động tạo mới chunk nếu được cung cấp verbatim_text (bắt buộc). Hỗ trợ gửi delta fields và tự động đồng bộ ngữ cảnh xuống các điểm con cháu.",
    )
    async def stg_patch(
        doc_code: Annotated[
            str,
            Field(
                description="Số hiệu văn bản của phiên làm việc trong phiên làm việc staging.",
            ),
        ],
        updated_chunks: Annotated[
            list[StagingChunkDelta],
            Field(
                description=(
                    "Danh sách các bản vá hoặc tạo mới đoạn quy phạm chi tiết theo StagingChunkDelta (có thể gửi một phần các trường: "
                    "path, verbatim_text, contextualized_text, metadata, context_type, justification, dangling_dependencies; bắt buộc verbatim_text nếu tạo mới). "
                    "Trong đó context_type bắt buộc phải là 'SELF_CONTAINED' hoặc 'REQUIRES_EXTERNAL_CONTEXT' trước khi finalize; "
                    "đối với dangling_dependencies, chỉ cần cung cấp dependency_text, dependency_type, reason; "
                    "hệ thống tự động neo tọa độ ký tự vào văn bản nguyên văn."
                ),
            ),
        ] = _EMPTY_CHUNK_DELTAS,
        removed_paths: Annotated[
            list[str],
            Field(
                description="Danh sách các đường dẫn phân cấp của các đoạn quy phạm cần xóa khỏi phiên làm việc.",
            ),
        ] = _EMPTY_STR_LIST,
        cascade_breadcrumbs: Annotated[
            bool,
            Field(
                default=True,
                description="Tự động cập nhật ngữ cảnh contextualized_text cho các điểm con khi nội dung của khoản cha thay đổi.",
            ),
        ] = True,
    ) -> BatchPatchResult:
        return await tool_impl.stg_patch(
            doc_code=doc_code,
            updated_chunks=updated_chunks or None,
            removed_paths=removed_paths or None,
            cascade_breadcrumbs=cascade_breadcrumbs,
        )

    @server.tool(
        name="stg_add_edges",
        description=(
            "Gắn kết và kiểm toán trước (pre-commit linting) các cạnh quan hệ đồ thị pháp lý trong phiên làm việc staging.\n"
            "- Cưỡng chế đích đến có thực: Bắt buộc target_path phải là một phân đoạn (chunk) thực sự tồn tại trong phiên hiện tại (nội bộ văn bản) "
            "hoặc trong một phiên tài liệu đã nạp trong corpus (liên tài liệu). Cấm tạo cạnh ảo trỏ tới văn bản ngoài corpus (nếu viện dẫn văn bản ngoài chưa nạp, "
            "bắt buộc phải khai báo vào dangling_dependencies dạng EXTERNAL_CITATION qua stg_patch).\n"
            "- Tự động kiểm tra tính hợp lệ của cả source_path và target_path trước khi lưu."
        ),
    )
    async def stg_add_edges(
        doc_code: Annotated[
            str,
            Field(
                description="Số hiệu văn bản của phiên làm việc trong phiên làm việc staging.",
            ),
        ],
        edges: Annotated[
            list[RelationEdge],
            Field(
                description="Danh sách các cạnh quan hệ đồ thị pháp lý tuân thủ RelationEdge (source_path, target_path, relation_type, citation_text). Bắt buộc phải có target_path xác định.",
            ),
        ],
    ) -> MutationResult:
        return await tool_impl.stg_add_edges(
            doc_code=doc_code,
            edges=edges,
        )

    @server.tool(
        name="stg_reparent",
        description="Tái cấu trúc và di chuyển cả một nhánh cây quy phạm (Chương, Mục, Điều) sang vị trí cha mới trong phiên làm việc staging. Tự động cascade đổi đường dẫn phân cấp của toàn bộ các khoản/điểm con cháu và di dời các cạnh quan hệ đồ thị tương ứng. Hỗ trợ cờ dry_run để xem trước kết quả.",
    )
    async def stg_reparent(
        doc_code: Annotated[
            str,
            Field(
                description="Số hiệu văn bản của phiên làm việc trong phiên làm việc staging.",
                examples=["100/2019/NĐ-CP"],
            ),
        ],
        old_path_prefix: Annotated[
            str,
            Field(
                description="Đường dẫn phân cấp cũ cần di chuyển (ví dụ: '100_2019_nd_cp.c_i.a_5').",
            ),
        ],
        new_path_prefix: Annotated[
            str,
            Field(
                description="Đường dẫn phân cấp đích mới (ví dụ: '100_2019_nd_cp.c_ii.a_5').",
            ),
        ],
        dry_run: Annotated[
            bool,
            Field(
                default=False,
                description="Nếu True, chỉ tính toán và mô phỏng số lượng node sẽ thay đổi mà không ghi xuống đĩa.",
            ),
        ] = False,
    ) -> ReparentSubtreeResult:
        return await tool_impl.stg_reparent(
            doc_code=doc_code,
            old_path_prefix=old_path_prefix,
            new_path_prefix=new_path_prefix,
            dry_run=dry_run,
        )

    @server.tool(
        name="stg_commit",
        description="Xác nhận hoàn tất phiên xử lý của Agent trong phiên làm việc staging, chuyển trạng thái phiên sang AGENT_COMMITTED. Yêu cầu bắt buộc: 100% các đoạn quy phạm trong phiên làm việc phải đạt trạng thái review_status == 'REVIEWED' (không còn chunk PENDING).",
    )
    async def stg_commit(
        doc_code: Annotated[
            str,
            Field(
                description="Số hiệu văn bản cần xác nhận hoàn tất trong phiên làm việc staging.",
                examples=["100/2019/NĐ-CP"],
            ),
        ],
    ) -> SessionStatusResult:
        return await tool_impl.stg_commit(
            doc_code=doc_code,
        )

    @server.tool(
        name="stg_uncommit",
        description="Mở lại phiên làm việc đã cam kết (AGENT_COMMITTED) về trạng thái chỉnh sửa (DRAFT hoặc AMENDMENT) để Agent hoặc Chuyên viên tiếp tục vi phẫu, chỉnh sửa quan hệ hoặc tái thẩm định phân đoạn.",
    )
    async def stg_uncommit(
        doc_code: Annotated[
            str,
            Field(
                description="Số hiệu văn bản cần mở lại (uncommit) trong phiên làm việc staging.",
                examples=["100/2019/NĐ-CP"],
            ),
        ],
        reason: Annotated[
            str,
            Field(
                default="",
                description="Lý do mở lại phiên làm việc để phục vụ kiểm toán và truy vết lịch sử WAL.",
                examples=["Bổ sung quan hệ viện dẫn cho Điều 5", "Điều chỉnh toạ độ phân đoạn"],
            ),
        ] = "",
    ) -> SessionStatusResult:
        return await tool_impl.stg_uncommit(
            doc_code=doc_code,
            reason=reason,
        )

    @server.tool(
        name="stg_poll_pending",
        description="Lấy danh sách các đoạn quy phạm chưa thẩm định (PENDING) gom nhóm theo ngữ cảnh cấp cha từ hàng đợi công việc để Agent xử lý theo từng đợt (tối đa 10 chunk).",
    )
    async def stg_poll_pending(
        doc_code: Annotated[
            str,
            Field(
                description="Số hiệu văn bản của phiên làm việc trong phiên làm việc staging.",
                examples=["100/2019/NĐ-CP"],
            ),
        ],
        limit: Annotated[
            int,
            Field(
                default=10,
                ge=1,
                le=10,
                description="Số lượng đoạn quy phạm tối đa cần lấy ra trong đợt này (tối đa 10).",
            ),
        ] = 10,
        path_prefix: Annotated[
            str,
            Field(
                default="",
                description="Tiền tố đường dẫn phân cấp tùy chọn để giới hạn phạm vi quét (ví dụ: '100_2019_nd_cp.a_5').",
            ),
        ] = "",
    ) -> PendingChunksResult:
        return await tool_impl.stg_poll_pending(
            doc_code=doc_code,
            limit=limit,
            path_prefix=path_prefix or None,
        )

    @server.tool(
        name="stg_finalize_chunks",
        description=(
            "Đánh dấu danh sách các đoạn quy phạm sang trạng thái đã thẩm định (review_status = 'REVIEWED') "
            "sau khi đã đối soát và bắt buộc phân loại context_type qua stg_patch ('SELF_CONTAINED' hoặc 'REQUIRES_EXTERNAL_CONTEXT').\n"
            "- Bắt buộc phân loại trước: Nếu chunk chưa có context_type, công cụ sẽ chặn ngay lập tức với lỗi UNCLASSIFIED_CHUNK.\n"
            "- Cưỡng chế luật quan hệ (Relational Parity):\n"
            "  + Chunk SELF_CONTAINED bắt buộc có 0 cạnh đồ thị và 0 dangling_dependencies (nếu vi phạm sẽ ném INVALID_RELATION_ON_SELF_CONTAINED hoặc DANGLING_ON_SELF_CONTAINED);\n"
            "  + Chunk REQUIRES_EXTERNAL_CONTEXT bắt buộc phải có bằng chứng phụ thuộc: hoặc có cạnh đồ thị có thực (nội bộ/liên tài liệu trong corpus), "
            "hoặc có viện dẫn ngoài/mở trong dangling_dependencies (nếu không có cả hai sẽ ném MISSING_DEPENDENCY_SPECIFICATION).\n"
            "Kết quả trả về danh sách chi tiết (results) ghi nhận trạng thái pháp lý và context_type của từng chunk."
        ),
    )
    async def stg_finalize_chunks(
        doc_code: Annotated[
            str,
            Field(
                description="Số hiệu văn bản của phiên làm việc trong phiên làm việc staging.",
                examples=["100/2019/NĐ-CP"],
            ),
        ],
        paths: Annotated[
            list[str],
            Field(
                description="Danh sách đường dẫn phân cấp của các đoạn quy phạm cần chốt hoàn tất.",
                examples=[["100_2019_nd_cp.c_ii.a_5.c_3.p_a"]],
            ),
        ],
    ) -> FinalizeChunksResult:
        return await tool_impl.stg_finalize_chunks(
            doc_code=doc_code,
            paths=paths,
        )

    @server.tool(
        name="stg_unfinalize_chunks",
        description="Mở lại các đoạn quy phạm đã thẩm định chuyển về trạng thái PENDING để tiến hành chỉnh sửa hoặc bổ sung liên kết.",
    )
    async def stg_unfinalize_chunks(
        doc_code: Annotated[
            str,
            Field(
                description="Số hiệu văn bản của phiên làm việc trong vùng đệm staging.",
                examples=["100/2019/NĐ-CP"],
            ),
        ],
        paths: Annotated[
            list[str],
            Field(
                description="Danh sách đường dẫn phân cấp của các đoạn quy phạm cần mở lại trạng thái PENDING.",
                examples=[["100_2019_nd_cp.c_ii.a_5.c_3.p_a"]],
            ),
        ],
    ) -> UnfinalizeChunksResult:
        return await tool_impl.stg_unfinalize_chunks(
            doc_code=doc_code,
            paths=paths,
        )

    @server.tool(
        name="stg_list_sessions",
        description="Liệt kê danh sách tóm tắt toàn bộ các phiên làm việc và tài liệu pháp lý đang có trong hệ thống staging, hỗ trợ lọc theo trạng thái.",
    )
    async def stg_list_sessions(
        status: Annotated[
            StagingStatus | None,
            Field(
                default=None,
                description="Lọc danh sách theo trạng thái phiên làm việc. Để trống để lấy tất cả.",
            ),
        ] = None,
    ) -> StgListSessionsResponse:
        return await tool_impl.stg_list_sessions(status=status)


    @server.tool(
        name="stg_reopen_session",
        description="Mở lại phiên làm việc của một văn bản pháp luật đã promote vào PostgreSQL sang trạng thái AMENDMENT để tiến hành vá lỗi quy phạm (errata), hoàn tất các điều khoản chưa hoàn thiện (unfinalized) hoặc bổ sung liên kết quan hệ đồ thị.",
    )
    async def stg_reopen_session(
        doc_code: Annotated[
            str,
            Field(
                description="Số hiệu văn bản cần mở lại phiên làm việc (ví dụ: '100/2019/NĐ-CP').",
                examples=["100/2019/NĐ-CP"],
            ),
        ],
        reason: Annotated[
            str,
            Field(
                default="",
                description="Lý do hoặc ghi chú mở lại phiên làm việc để phục vụ nhật ký kiểm toán.",
            ),
        ] = "",
    ) -> SessionStatusResult:
        return await tool_impl.stg_reopen_session(
            doc_code=doc_code,
            reason=reason,
        )

    @server.tool(
        name="stg_remove_edges",
        description="Xóa bỏ một hoặc nhiều cạnh quan hệ đồ thị pháp lý khỏi phiên làm việc staging theo danh sách bộ lọc edges (mỗi phần tử tuân thủ RelationEdgeFilter: source_path, target_path, relation_type, clear_all_targets).",
    )
    async def stg_remove_edges(
        doc_code: Annotated[
            str,
            Field(
                description="Số hiệu văn bản của phiên làm việc trong vùng đệm staging.",
                examples=["100/2019/NĐ-CP"],
            ),
        ],
        edges: Annotated[
            list[RelationEdgeFilter],
            Field(
                description="Danh sách các bộ lọc cạnh quan hệ cần xóa.",
            ),
        ],
    ) -> MutationResult:
        return await tool_impl.stg_remove_edges(
            doc_code=doc_code,
            edges=edges,
        )

    @server.tool(
        name="stg_validate",
        description="Kiểm tra toàn diện 9 quy tắc kiểm định an toàn (Pre-Flight Integrity Gate) của phiên làm việc staging trước khi thực hiện cam kết (commit) hoặc nạp chính thức (promote) vào cơ sở dữ liệu.",
    )
    async def stg_validate(
        doc_code: Annotated[
            str,
            Field(
                description="Số hiệu văn bản pháp luật cần kiểm tra tiền kiểm định (ví dụ: '100/2019/NĐ-CP').",
                examples=["100/2019/NĐ-CP"],
            ),
        ],
    ) -> PreFlightValidationResponse:
        return await tool_impl.stg_validate(doc_code=doc_code)


