from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from rag_eval.legal.mcp.tools import (
    AddEdgesResult,
    EdgeKey,
    EdgeProposal,
    LegalMCPTools,
    RawTextResult,
    RemoveEdgesResult,
)
from rag_eval.legal.schemas.domain import (
    CITATION_DIRECTION_DESCRIPTIONS,
    CitationDirection,
    GraphDirection,
    LegalToolName,
    StatutoryRelationType,
    format_graph_direction_docs,
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
    """Registers the 4 runtime sensors and the 2 graph curation tools onto the MCPServer instance."""

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
            "Cắt path của một kết quả để chọn phạm vi: đến 'a_N' để đọc cả Điều, đến 'c_N' để đọc cả Khoản cùng các Điểm của nó. "
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
        limit: Annotated[
            int,
            Field(ge=1, le=300, description="Số đoạn tối đa trả về; 'total' và 'truncated' cho biết phạm vi có bị cắt bớt không."),
        ] = 100,
    ) -> HierarchicalNavigateResult:
        return await tool_impl.hierarchical_navigate(path=path, limit=limit)

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
            "Đọc nguyên văn các dòng liên tiếp của văn bản gốc, đúng bản text mà mọi đoạn quy phạm được cắt ra. "
            f"Dùng khi một đoạn có vẻ bị cắt lệch hoặc thiếu chữ: lấy doc_code (của nhóm chứa đoạn) cùng start_line, end_line của đoạn trong kết quả search, hierarchical_navigate hoặc graph_traverse, mở rộng vài dòng trước và sau rồi đọc. "
            f"Mỗi lần tối đa {RAW_MAX_LINES} dòng; 'total_lines' cho biết văn bản dài bao nhiêu dòng để đọc tiếp."
        ),
    )
    async def get_raw(
        doc_code: Annotated[
            str,
            Field(min_length=1, description="Mã văn bản, chép nguyên văn trường doc_code của kết quả.", examples=["168/2024/ND-CP"]),
        ],
        start_line: Annotated[int, Field(ge=1, description="Dòng đầu tiên cần đọc (đánh số từ 1).")],
        end_line: Annotated[
            int,
            Field(ge=1, description=f"Dòng cuối cùng cần đọc (tính cả dòng này); không quá start_line + {RAW_MAX_LINES - 1}. Vượt cuối văn bản thì dừng ở dòng cuối."),
        ],
    ) -> RawTextResult:
        return await tool_impl.get_raw(doc_code=doc_code, start_line=start_line, end_line=end_line)

    @server.tool(
        name=LegalToolName.GRAPH_ADD_EDGES.value,
        description=(
            "Thêm cạnh quan hệ giữa các đoạn quy phạm khi trả lời câu hỏi cần đi theo một viện dẫn mà đồ thị chưa có.\n"
            "- Mỗi cạnh phải có citation_text là cụm viện dẫn chép nguyên văn từ verbatim_text của đoạn nguồn; nếu không tìm thấy, công cụ từ chối (UNGROUNDED_CITATION_TEXT).\n"
            "- target_path có thể là đoạn lá hoặc một nút cha (Điều, Khoản); nút cha được tự động nối tới mọi đoạn lá bên dưới.\n"
            "- Kiểm tra cả lô trước khi ghi: một cạnh không hợp lệ thì không cạnh nào được ghi. Cạnh đã có được báo trong 'existing' và giữ nguyên."
        ),
    )
    async def graph_add_edges(
        edges: Annotated[
            list[EdgeProposal],
            Field(
                min_length=1,
                description="Danh sách cạnh: source_path, target_path, relation_type, citation_text (cụm viện dẫn nguyên văn trong đoạn nguồn).",
            ),
        ],
        reason: Annotated[
            str,
            Field(min_length=1, description="Lý do thêm cạnh, thường là câu hỏi đang trả lời; được ghi vào nhật ký."),
        ],
    ) -> AddEdgesResult:
        return await tool_impl.graph_add_edges(edges=edges, reason=reason)

    @server.tool(
        name=LegalToolName.GRAPH_REMOVE_EDGES.value,
        description=(
            "Gỡ cạnh quan hệ sai, bất kể cạnh do hệ thống hay agent tạo; mỗi cạnh gỡ được ghi nhật ký kèm lý do.\n"
            "- Mỗi cạnh xác định bằng source_path, target_path, relation_type.\n"
            "- Cạnh do hệ thống tạo từ viện dẫn sẽ được tạo lại ở lần nạp sau; nếu cạnh sai cứ lặp lại, đó là lỗi quy tắc viện dẫn cần báo lại."
        ),
    )
    async def graph_remove_edges(
        edges: Annotated[
            list[EdgeKey],
            Field(min_length=1, description="Danh sách cạnh cần gỡ: source_path, target_path, relation_type."),
        ],
        reason: Annotated[
            str,
            Field(min_length=1, description="Lý do gỡ cạnh; được ghi vào nhật ký."),
        ],
    ) -> RemoveEdgesResult:
        return await tool_impl.graph_remove_edges(edges=edges, reason=reason)
