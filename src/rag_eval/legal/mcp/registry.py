from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from rag_eval.legal.mcp.tools import (
    CurateEdgesResult,
    EdgeKey,
    EdgeProposal,
    LegalMCPTools,
    RawTextResult,
)
from rag_eval.legal.schemas.domain import (
    CITATION_DIRECTION_DESCRIPTIONS,
    CitationDirection,
    GraphDirection,
    LegalToolName,
    NavigationScope,
    StatutoryRelationType,
    format_graph_direction_docs,
    format_navigation_scope_docs,
    format_statutory_relation_docs,
)
from rag_eval.legal.schemas.retrieval import (
    RAW_MAX_LINES,
    GraphTraverseResult,
    HierarchicalNavigateResult,
    LegalSearchResult,
    format_search_found_in_docs,
)

_EMPTY_STR_LIST: list[str] = []

def register_legal_mcp_tools(server: MCPServer, tool_impl: LegalMCPTools) -> None:
    """Registers the 4 runtime sensors and the 1 graph curation tool onto the MCPServer instance."""

    @server.tool(
        name=LegalToolName.SEARCH.value,
        description=(
            "Tìm các đoạn quy phạm pháp luật giao thông đường bộ bằng hai cách cùng lúc trên cùng phạm vi: "
            "theo nghĩa (query, kết hợp vector ngữ nghĩa và từ khóa) và theo nguyên văn (pattern, chuỗi con không phân biệt hoa thường hoặc regex POSIX). "
            f"Mỗi đoạn xuất hiện đúng một lần, với 'found_in' là một trong các giá trị: {format_search_found_in_docs()}. "
            "'rank' là thứ hạng 1.. của đoạn trong cả kết quả: mọi 'both' trước, rồi 'semantic_only', rồi 'verbatim_only'. "
            "Các đoạn cùng văn bản và cùng ngữ cảnh cha được gom thành một nhóm trong 'groups': 'doc_code' và 'context' (Chương > Điều > Khoản, gồm cả mức phạt và chủ thể của Khoản cha; rỗng nếu đoạn nằm ngay dưới văn bản) ghi một lần, "
            "'provisions' liệt kê từng đoạn với 'text' (nguyên văn của chính đoạn đó). Nhóm xếp theo đoạn có rank tốt nhất trong nhóm; các đoạn trong nhóm xếp theo thứ tự văn bản. "
            "'documents' cho tên và hiệu lực của từng văn bản theo doc_code."
        ),
    )
    async def search(
        query: Annotated[
            str,
            Field(
                min_length=1,
                description=(
                    "Truy vấn ngữ nghĩa theo thuật ngữ văn bản luật: [chủ thể, phương tiện] + [hành vi, quy tắc, tiêu chuẩn, thẩm quyền]. "
                    "Thay khẩu ngữ bằng thuật ngữ luật nhưng giữ từ khóa hành vi cốt lõi; bỏ từ xưng hô, cảm xúc; "
                    "không đưa mốc thời gian vào query (dùng temporal_violation_date)."
                ),
                examples=[
                    "không chấp hành hiệu lệnh của đèn tín hiệu giao thông xe mô tô xe gắn máy",
                    "người điều khiển xe ô tô chạy quá tốc độ quy định từ 10 km/h đến 20 km/h",
                ],
            ),
        ],
        pattern: Annotated[
            str,
            Field(
                min_length=1,
                description=(
                    "Cụm từ ngắn chắc chắn xuất hiện nguyên văn trong đoạn cần tìm (thuật ngữ quy phạm, số hiệu văn bản, số Điều, mã biển báo), "
                    "khớp không phân biệt hoa thường trên tên văn bản, context và text. Không truyền cả câu hỏi. "
                    "Bật is_regex để quét biến thể (khung tiền, tốc độ, thời hạn)."
                ),
                examples=["đèn tín hiệu giao thông", "P.123a", "tước quyền sử dụng giấy phép lái xe từ [0-9]+ tháng đến [0-9]+ tháng"],
            ),
        ],
        is_regex: Annotated[
            bool,
            Field(description="Hiểu pattern là biểu thức chính quy POSIX thay vì chuỗi con."),
        ] = False,
        temporal_violation_date: Annotated[
            str,
            Field(
                description="Ngày xảy ra hành vi vi phạm (YYYY-MM-DD hoặc 'ngày DD tháng MM năm YYYY'); chỉ trả các đoạn có hiệu lực vào ngày đó. Để trống để dùng ngày hiện tại theo giờ Việt Nam.",
                examples=["2020-01-15", "ngày 15 tháng 01 năm 2020"],
            ),
        ] = "",
        doc_codes: Annotated[
            list[str],
            Field(
                description="Giới hạn trong các văn bản có mã này. Để rỗng để tìm trên toàn bộ kho.",
                examples=[["168/2024/ND-CP"]],
            ),
        ] = _EMPTY_STR_LIST,
        path_prefix: Annotated[
            str,
            Field(
                description="Giới hạn trong một nhánh của cây phân cấp (ví dụ '168_2024_nd_cp.c_ii'). Để trống để không giới hạn.",
                examples=["168_2024_nd_cp.c_ii"],
            ),
        ] = "",
        limit: Annotated[
            int,
            Field(ge=1, le=50, description="Số kết quả tối đa của từng cách tìm (ngữ nghĩa và nguyên văn)."),
        ] = 10,
        rerank: Annotated[
            bool,
            Field(description="Xếp hạng lại kết quả ngữ nghĩa bằng mô hình cross-encoder. Bị bỏ qua với truy vấn gõ không dấu."),
        ] = False,
    ) -> LegalSearchResult:
        return await tool_impl.search(
            query=query,
            pattern=pattern,
            is_regex=is_regex,
            temporal_violation_date=temporal_violation_date or None,
            doc_codes=doc_codes or None,
            path_prefix=path_prefix or None,
            limit=limit,
            rerank=rerank,
        )

    @server.tool(
        name=LegalToolName.HIERARCHICAL_NAVIGATE.value,
        description=(
            "Đọc toàn văn mọi đoạn quy phạm tại hoặc dưới một nút của cây phân cấp (Văn bản > Chương > Mục > Điều > Khoản > Điểm), theo thứ tự đọc văn bản. "
            "Dùng scope='parent_context' khi đứng ở một Điểm lá để tự động mở rộng lên Khoản cha, lấy cả đoạn mở đầu chứa khung phạt lẫn các Điểm anh em. "
            "Các đoạn liên tiếp có cùng ngữ cảnh cha được gom vào một nhóm trong 'groups': 'doc_code' và 'context' (Chương > Điều > Khoản, gồm mức phạt và chủ thể; rỗng nếu đoạn nằm ngay dưới văn bản) viết một lần, "
            "'provisions' liệt kê nguyên văn từng đoạn. 'documents' cho tên và hiệu lực của văn bản theo doc_code."
        ),
    )
    async def hierarchical_navigate(
        path: Annotated[
            str,
            Field(
                description="Đường dẫn của nút cần đọc: Điều, Khoản, Điểm, Chương hoặc cả văn bản.",
                examples=["168_2024_nd_cp.c_ii.s_1.a_6", "168_2024_nd_cp.c_ii.s_1.a_6.c_9"],
            ),
        ],
        scope: Annotated[
            NavigationScope,
            Field(
                default=NavigationScope.SUBTREE,
                description=f"Phạm vi duyệt: {format_navigation_scope_docs()}.",
            ),
        ] = NavigationScope.SUBTREE,
        limit: Annotated[
            int,
            Field(ge=1, le=100, description="Số đoạn tối đa trả về; 'total' và 'truncated' cho biết phạm vi có bị cắt bớt không."),
        ] = 50,
    ) -> HierarchicalNavigateResult:
        return await tool_impl.hierarchical_navigate(path=path, scope=scope, limit=limit)

    @server.tool(
        name=LegalToolName.GRAPH_TRAVERSE.value,
        description=(
            "Đi theo các cạnh quan hệ (dẫn chiếu) từ một đoạn quy phạm. Mỗi mục trong 'links' là một viện dẫn đã đi: from_path (đoạn đang đứng), "
            "relation_type, depth, citation_text (cụm viện dẫn nguyên văn) và 'direction': "
            f"OUTGOING ({CITATION_DIRECTION_DESCRIPTIONS[CitationDirection.OUTGOING]}), "
            f"INCOMING ({CITATION_DIRECTION_DESCRIPTIONS[CitationDirection.INCOMING]}). "
            "Các đoạn đến được gom trong 'groups' theo văn bản và ngữ cảnh cha, cùng dạng với hierarchical_navigate. 'total' là số đoạn viện dẫn đó dẫn tới; 'truncated' là true khi 'groups' chỉ có phần đầu, khi đó đọc tiếp bằng hierarchical_navigate trên đường dẫn cần xem. 'documents' cho tên và hiệu lực văn bản theo doc_code."
        ),
    )
    async def graph_traverse(
        source_path: Annotated[
            str,
            Field(
                description="Đường dẫn cây phân cấp của nút quy phạm gốc bắt đầu duyệt.",
                examples=["168_2024_nd_cp.c_ii.s_1.a_7.c_11.p_b", "168_2024_nd_cp.c_ii.s_1.a_6"],
            ),
        ],
        direction: Annotated[
            GraphDirection,
            Field(
                default=GraphDirection.OUTGOING,
                description=f"Hướng duyệt đồ thị: {format_graph_direction_docs()}.",
            ),
        ] = GraphDirection.OUTGOING,
        max_depth: Annotated[
            int,
            Field(
                default=1,
                ge=1,
                le=4,
                description="Độ sâu bước nhảy tối đa trên đồ thị quan hệ. Mặc định 1 (chỉ các viện dẫn trực tiếp); tăng khi cần đi tiếp qua các đoạn đến được.",
            ),
        ] = 1,
        filter_relations: Annotated[
            list[StatutoryRelationType] | None,
            Field(
                default=None,
                description=f"Lọc danh sách các loại quan hệ cần duyệt: {format_statutory_relation_docs()}. Để trống để duyệt tất cả.",
                examples=[[StatutoryRelationType.REFERENCES.value, StatutoryRelationType.SANCTIONS.value]],
            ),
        ] = None,
        limit_per_link: Annotated[
            int,
            Field(
                default=20,
                ge=1,
                le=100,
                description="Số đoạn đến được tối đa trả về cho mỗi viện dẫn, theo thứ tự đọc. Viện dẫn tới một chương hay điều dẫn tới mọi đoạn bên dưới nó.",
            ),
        ] = 20,
    ) -> GraphTraverseResult:
        return await tool_impl.graph_traverse(
            source_path=source_path,
            direction=direction,
            max_depth=max_depth,
            filter_relations=filter_relations,
            limit_per_link=limit_per_link,
        )

    @server.tool(
        name=LegalToolName.GET_RAW.value,
        description=(
            "Đọc nguyên văn các dòng liên tiếp của văn bản gốc dưới dạng chuỗi text thuần. "
            f"Dùng khi một đoạn có vẻ bị cắt lệch hoặc thiếu chữ: lấy doc_code (hoặc path của đoạn) cùng start_line, end_line trong kết quả search, hierarchical_navigate hoặc graph_traverse, mở rộng vài dòng trước và sau rồi đọc. "
            f"Mỗi lần tối đa {RAW_MAX_LINES} dòng; 'end_line' là tùy chọn (mặc định lấy tối đa {RAW_MAX_LINES} dòng từ start_line); 'total_lines' cho biết văn bản dài bao nhiêu dòng."
        ),
    )
    async def get_raw(
        doc_code: Annotated[
            str,
            Field(min_length=1, description="Mã văn bản (ví dụ '168/2024/ND-CP') hoặc đường dẫn phân cấp chunk path.", examples=["168/2024/ND-CP", "168_2024_nd_cp.c_ii.s_1.a_6"]),
        ],
        start_line: Annotated[int, Field(ge=1, description="Dòng đầu tiên cần đọc (đánh số từ 1, mặc định 1).")] = 1,
        end_line: Annotated[
            int | None,
            Field(default=None, ge=1, description=f"Dòng cuối cùng cần đọc (tính cả dòng này, tối đa start_line + {RAW_MAX_LINES - 1}). Để trống sẽ tự động lấy tối đa {RAW_MAX_LINES} dòng."),
        ] = None,
    ) -> RawTextResult:
        return await tool_impl.get_raw(doc_code=doc_code, start_line=start_line, end_line=end_line)

    @server.tool(
        name=LegalToolName.GRAPH_CURATE_EDGES.value,
        description=(
            "Hiệu chỉnh đồ thị quan hệ giữa các đoạn quy phạm trong một giao dịch nguyên tử: thêm cạnh mới (add_edges) hoặc gỡ cạnh sai (remove_edges).\n"
            "- add_edges: mỗi cạnh cần source_path, target_path, relation_type, và citation_text (cụm viện dẫn nguyên văn từ verbatim_text của đoạn nguồn). target_path có thể là một nút cha (Điều, Khoản) và sẽ được mở rộng tới mọi đoạn lá bên dưới.\n"
            "- remove_edges: mỗi cạnh gồm source_path, target_path, relation_type. target_path có thể là một nút cha để gỡ toàn bộ các cạnh lá liên quan.\n"
            "- reason: bắt buộc, ghi câu hỏi đang trả lời hoặc căn cứ hiệu chỉnh để lưu nhật ký.\n"
            "- Phải truyền ít nhất một cạnh trong add_edges hoặc remove_edges."
        ),
    )
    async def graph_curate_edges(
        reason: Annotated[
            str,
            Field(min_length=1, description="Lý do hiệu chỉnh đồ thị (câu hỏi đang giải quyết hoặc lý do gỡ/thêm cạnh)."),
        ],
        add_edges: Annotated[
            list[EdgeProposal] | None,
            Field(
                default=None,
                description="Danh sách cạnh cần thêm: source_path, target_path, relation_type, citation_text (nguyên văn cụm viện dẫn).",
            ),
        ] = None,
        remove_edges: Annotated[
            list[EdgeKey] | None,
            Field(
                default=None,
                description="Danh sách cạnh cần gỡ: source_path, target_path, relation_type.",
            ),
        ] = None,
    ) -> CurateEdgesResult:
        return await tool_impl.graph_curate_edges(
            reason=reason,
            add_edges=add_edges or None,
            remove_edges=remove_edges or None,
        )
