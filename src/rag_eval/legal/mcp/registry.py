from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from rag_eval.legal.mcp.tools import (
    AddEdgesResult,
    EdgeKey,
    EdgeProposal,
    LegalMCPTools,
    RemoveEdgesResult,
)
from rag_eval.legal.schemas.domain import (
    GraphDirection,
    StatutoryRelationType,
)
from rag_eval.legal.schemas.retrieval import (
    GraphTraverseResult,
    HierarchicalNavigateResult,
    LegalSearchResult,
)

_EMPTY_STR_LIST: list[str] = []

def register_legal_mcp_tools(server: MCPServer, tool_impl: LegalMCPTools) -> None:
    """Registers the 3 runtime sensors and the 2 graph curation tools onto the MCPServer instance."""

    @server.tool(
        name="search",
        description=(
            "Tìm các đoạn quy phạm pháp luật giao thông đường bộ bằng hai cách cùng lúc trên cùng phạm vi: "
            "theo nghĩa (query, kết hợp vector ngữ nghĩa và từ khóa) và theo nguyên văn (pattern, chuỗi con không phân biệt hoa thường hoặc regex POSIX). "
            "Mỗi đoạn xuất hiện đúng một lần, trong một trong ba nhóm: "
            "'both' (liên quan về nghĩa và chứa pattern, đáng tin nhất), 'semantic_only' (liên quan về nghĩa nhưng không chứa pattern), "
            "'verbatim_only' (chứa pattern nhưng không nằm trong top ngữ nghĩa, xếp theo thứ tự văn bản). "
            "Mỗi đoạn có 'context' (Văn bản > Chương > Điều > Khoản, gồm cả mức phạt và chủ thể của Khoản cha) và 'text' (nguyên văn của chính đoạn đó); "
            "'documents' cho tên và hiệu lực của từng văn bản xuất hiện trong kết quả."
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
                    "khớp không phân biệt hoa thường trên context và text. Không truyền cả câu hỏi. "
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
        name="hierarchical_navigate",
        description=(
            "Đọc toàn văn mọi đoạn quy phạm tại hoặc dưới một nút của cây phân cấp (Văn bản > Chương > Mục > Điều > Khoản > Điểm), theo thứ tự đọc văn bản. "
            "Cắt path của một kết quả để chọn phạm vi: đến 'a_N' để đọc cả Điều, đến 'c_N' để đọc cả Khoản cùng các Điểm của nó. "
            "Các đoạn liên tiếp có cùng ngữ cảnh cha được gom vào một nhóm: 'context' (Văn bản > Chương > Điều > Khoản, gồm mức phạt và chủ thể) viết một lần, "
            "'provisions' liệt kê nguyên văn từng đoạn."
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
        name="graph_traverse",
        description=(
            "Đi theo các cạnh quan hệ (dẫn chiếu) từ một đoạn quy phạm. Mỗi bước cho cạnh đã đi (from_path, relation_type, "
            "citation_text là cụm viện dẫn nguyên văn trong đoạn chứa viện dẫn, depth) và đoạn đến được ('to', cùng dạng kết quả của search)."
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
        name="graph_add_edges",
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
        name="graph_remove_edges",
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
