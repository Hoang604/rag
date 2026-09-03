"""Vietnamese Traffic Law Model Context Protocol (MCP) Server.

Implements the official MCP Python SDK v2 MCPServer exposing the 10 canonical
Agent-First legal tools (6 runtime sensors + 4 staging lifecycle tools)
with constructive contracts, comprehensive Vietnamese affirmative descriptions, and dynamic corpus topology instructions.
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.shared.exceptions import MCPError
from mcp.types import CallToolResult, TextContent
from pydantic import Field

from rag_eval.legal.mcp.tools import (
    CorpusValidateResult,
    GraphEdgeWriteResult,
    GraphTraverseResult,
    HierarchicalNavigateResult,
    HybridSearchResult,
    LegalMCPTools,
    SentenceTransformerQueryEmbedder,
    StgAddEdgesResult,
    StgCommitResult,
    StgGetChunkResult,
    StgGetRawResult,
    StgGrepResult,
    StgPatchResult,
    StgPreviewResult,
    StgReparentResult,
    VerbatimGrepResult,
)
from rag_eval.legal.schemas import LegalDomainError, get_vietnam_today

logger = logging.getLogger("rag_eval.legal.mcp.server")

SERVER_NAME = "vietnamese-traffic-law-mcp"
SERVER_VERSION = "3.0.0"

STATIC_SERVER_INSTRUCTIONS = """# VIETNAMESE TRAFFIC LAW REASONING PROTOCOL

## 1. MÔ HÌNH DỮ LIỆU (Data Topology)
- CẤU TRÚC CÂY PHÂN CẤP: Văn bản được phân rã theo 7 cấp: `Document -> Chapter -> Section -> Article -> Clause -> Point -> Appendix`.
- NGUYÊN TẮC LƯU TRỮ NÚT LÁ (Leaf Nodes): Cơ sở dữ liệu chỉ lưu trữ các nút lá trên cây cú pháp. Nút cha (Điều/Khoản không có điểm con) được lưu trực tiếp; nút cha có các điểm con được phân rã thành các nút lá tương ứng.
- NGỮ CẢNH TỔNG HỢP: Mỗi nút lá chứa văn bản nguyên văn (`verbatim_text`) và văn bản đã tổng hợp toàn bộ chuỗi ngữ cảnh phả hệ cha (`contextualized_text`).

## 2. NGUYÊN TẮC BẢO CHỨNG & TỪ CHỐI (Grounding & Abstention)
- Trích dẫn căn cứ pháp lý bắt buộc theo định danh phân cấp: `[Tên Văn bản > Điều > Khoản > Điểm]` lấy trực tiếp từ kết quả truy xuất của công cụ.
- Khi không tìm thấy kết quả trong cơ sở dữ liệu (`total_hits == 0` hoặc không có quy định liên quan): Thông báo rõ ràng hệ thống chưa có dữ liệu và dừng lại; không suy đoán hay bổ sung thông tin ngoài kết quả công cụ."""


def render_server_instructions(
    manifest_block: str | None = None,
    as_of_date: datetime.date | None = None,
) -> str:
    """Renders full server instructions combining static topology rules and dynamic corpus manifest in Vietnam timezone."""
    target_date = as_of_date or get_vietnam_today()
    date_str = target_date.strftime("%d/%m/%Y")
    manifest = (
        manifest_block
        if manifest_block
        else f"## DANH MỤC VĂN BẢN TRONG CƠ SỞ DỮ LIỆU (TÍNH ĐẾN: {date_str})\n- (Cơ sở dữ liệu đang ngoại tuyến hoặc chưa kết nối)"
    )
    return f"{STATIC_SERVER_INSTRUCTIONS}\n\n{manifest}".strip()


LEGAL_SERVER_INSTRUCTIONS = render_server_instructions()

NavigateDirection = Literal["FULL_ARTICLE", "CHILDREN", "PARENT_CHAIN", "SIBLINGS"]
GraphTraverseDirection = Literal["OUTGOING", "INCOMING", "BOTH"]
RelationTypeLiteral = Literal[
    "MODIFIES_AND_REPLACES",
    "REFERENCES",
    "SANCTIONS",
    "OVERRIDES",
    "EXEMPTS",
    "GUIDES",
    "DEFINES_TERM",
]


def create_legal_mcp_server(
    tools: LegalMCPTools | None = None,
    manifest_block: str | None = None,
    as_of_date: datetime.date | None = None,
) -> MCPServer:
    """Builds and configures the official MCP v2 MCPServer instance with all 10 legal tools in comprehensive Vietnamese."""
    tool_impl = tools or LegalMCPTools(
        embedding_engine=SentenceTransformerQueryEmbedder()
    )
    instructions_text = render_server_instructions(manifest_block=manifest_block, as_of_date=as_of_date)
    server = MCPServer(
        SERVER_NAME,
        version=SERVER_VERSION,
        description="Máy chủ Giao thức Ngữ cảnh Mô hình (MCP) Pháp luật Giao thông Đường bộ Việt Nam",
        instructions=instructions_text,
    )

    # 1. Hybrid Search
    @server.tool(
        name="mcp_traffic_hybrid_search",
        description="Truy xuất các điều khoản quy định mức xử phạt và quy tắc giao thông đường bộ khớp với câu hỏi ngôn ngữ tự nhiên hoặc mô tả tình huống hành vi thông qua kết hợp xếp hạng ngữ nghĩa (Dense Vector) và từ khóa (Sparse Full-Text Search RRF).",
    )
    async def hybrid_search(
        query: Annotated[
            str,
            Field(
                description="Câu hỏi bằng ngôn ngữ tự nhiên, tình huống giao thông thực tế hoặc mô tả hành vi vi phạm bằng tiếng Việt.",
                examples=["vượt đèn đỏ xe máy", "người lái xe ô tô không thắt dây an toàn", "chạy quá tốc độ quy định từ 10 đến 20 km/h"],
            ),
        ],
        temporal_violation_date: Annotated[
            str | None,
            Field(
                default=None,
                description="Ngày xảy ra hành vi vi phạm (định dạng YYYY-MM-DD hoặc 'ngày DD tháng MM năm YYYY') để đánh giá hiệu lực văn bản pháp luật tại đúng thời điểm đó. Mặc định là ngày hiện tại theo giờ Việt Nam.",
                examples=["2020-01-15", "2024-06-01", "ngày 15 tháng 01 năm 2020"],
            ),
        ] = None,
        limit: Annotated[
            int,
            Field(
                default=10,
                ge=1,
                le=50,
                description="Số lượng điều khoản quy phạm tối đa cần trả về, được sắp xếp theo điểm hòa trộn tương đồng giảm dần.",
            ),
        ] = 10,
    ) -> HybridSearchResult:
        return await tool_impl.hybrid_search(
            query=query,
            temporal_violation_date=temporal_violation_date,
            limit=limit,
        )

    # 2. Verbatim Grep
    @server.tool(
        name="mcp_traffic_verbatim_grep",
        description="Thực hiện tìm kiếm chuỗi văn bản nguyên văn hoặc biểu thức chính quy POSIX trên toàn bộ dữ liệu quy phạm pháp luật, mã số văn bản, số hiệu điều khoản, mã hiệu biển báo và thông số kỹ thuật (được tăng tốc bởi chỉ mục Trigram GIN).",
    )
    async def verbatim_grep(
        pattern: Annotated[
            str,
            Field(
                description="Cụm từ nguyên văn chính xác, số hiệu văn bản, số hiệu Điều/Khoản, mã định danh biển báo hoặc biểu thức chính quy POSIX.",
                examples=["100/2019/NĐ-CP", "Điều 5", "P.102", "W.205", "^[0-9]+ km/h"],
            ),
        ],
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
            str | None,
            Field(
                default=None,
                description="Ngày xảy ra vi phạm (định dạng YYYY-MM-DD hoặc tiếng Việt) để lọc hiệu lực văn bản tại thời điểm đó.",
            ),
        ] = None,
        limit: Annotated[
            int,
            Field(
                default=20,
                ge=1,
                le=100,
                description="Số lượng kết quả khớp tối đa cần trả về.",
            ),
        ] = 20,
    ) -> VerbatimGrepResult:
        return await tool_impl.verbatim_grep(
            pattern=pattern,
            is_regex=is_regex,
            case_sensitive=case_sensitive,
            temporal_violation_date=temporal_violation_date,
            limit=limit,
        )

    # 3. Hierarchical Navigate
    @server.tool(
        name="mcp_traffic_hierarchical_navigate",
        description="Điều hướng cấu trúc cây phân cấp văn bản pháp luật (Văn bản -> Chương -> Mục -> Điều -> Khoản -> Điểm -> Phụ lục) xoay quanh một nút quy phạm được chỉ định thông qua toán tử ltree.",
    )
    async def hierarchical_navigate(
        path: Annotated[
            str | None,
            Field(
                default=None,
                description="Đường dẫn cây phân cấp ltree của nút quy phạm mục tiêu.",
                examples=["100_2019_nd_cp.c_ii.a_5.c_3.p_a", "100_2019_nd_cp.a_5"],
            ),
        ] = None,
        chunk_id: Annotated[
            str | None,
            Field(
                default=None,
                description="Mã định danh UUID của đoạn quy phạm cần điều hướng mở rộng.",
            ),
        ] = None,
        direction: Annotated[
            NavigateDirection,
            Field(
                default="FULL_ARTICLE",
                description="Phạm vi điều hướng: 'FULL_ARTICLE' (toàn bộ các Khoản/Điểm thuộc cùng Điều cha), 'CHILDREN' (tất cả các phân vị con trực tiếp), 'PARENT_CHAIN' (chuỗi phả hệ tổ tiên từ Văn bản đến nút hiện tại), 'SIBLINGS' (các nút cùng cấp dưới cùng một nút cha).",
            ),
        ] = "FULL_ARTICLE",
    ) -> HierarchicalNavigateResult:
        return await tool_impl.hierarchical_navigate(
            path=path,
            chunk_id=chunk_id,
            direction=direction,
        )

    # 4. Graph Traverse
    @server.tool(
        name="mcp_traffic_graph_traverse",
        description="Duyệt đồ thị tri thức pháp lý đệ quy qua các liên kết quan hệ giữa các quy định pháp luật (dẫn chiếu văn bản, hình thức xử phạt bổ sung, quy chuẩn kỹ thuật).",
    )
    async def graph_traverse(
        source_chunk_id: Annotated[
            str,
            Field(
                description="Mã định danh UUID của nút quy phạm gốc bắt đầu duyệt.",
            ),
        ],
        direction: Annotated[
            GraphTraverseDirection,
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
    ) -> GraphTraverseResult:
        return await tool_impl.graph_traverse(
            source_chunk_id=source_chunk_id,
            direction=direction,
            max_depth=max_depth,
        )

    # 5. Graph Edge Write
    @server.tool(
        name="mcp_traffic_graph_edge_write",
        description="Ghi nhận và lưu trữ một liên kết quan hệ pháp lý có hướng đã được xác thực giữa hai nút quy phạm vào bảng graph_edges.",
    )
    async def graph_edge_write(
        source_chunk_id: Annotated[
            str,
            Field(
                description="Mã định danh UUID của nút quy phạm nguồn.",
            ),
        ],
        relation_type: Annotated[
            RelationTypeLiteral,
            Field(
                description="Loại quan hệ pháp lý: 'SANCTIONS' (chế tài áp dụng), 'REFERENCES' (dẫn chiếu điều khoản), 'OVERRIDES' (bãi bỏ/thay thế), 'EXEMPTS' (ngoại lệ miễn trừ), 'MODIFIES_AND_REPLACES' (sửa đổi bổ sung), 'GUIDES' (quy chuẩn hướng dẫn), 'DEFINES_TERM' (định nghĩa thuật ngữ).",
            ),
        ],
        target_chunk_id: Annotated[
            str | None,
            Field(
                default=None,
                description="Mã định danh UUID của nút quy phạm đích nếu đã tồn tại trong cơ sở dữ liệu.",
            ),
        ] = None,
        target_external_ref: Annotated[
            str | None,
            Field(
                default=None,
                description="Chuỗi trích dẫn điều khoản đích nếu văn bản đích chưa được nạp vào cơ sở dữ liệu.",
                examples=["Khoản 1 Điều 12 Luật Giao thông đường bộ"],
            ),
        ] = None,
        citation_text: Annotated[
            str | None,
            Field(
                default=None,
                description="Đoạn văn bản nguyên văn thể hiện mối quan hệ dẫn chiếu này.",
                examples=["theo quy định tại Điều 12"],
            ),
        ] = None,
        metadata: Annotated[
            dict[str, Any] | None,
            Field(
                default=None,
                description="Dữ liệu siêu thông tin bổ sung về điều kiện hoặc ngữ cảnh liên kết.",
            ),
        ] = None,
    ) -> GraphEdgeWriteResult:
        return await tool_impl.graph_edge_write(
            source_chunk_id=source_chunk_id,
            relation_type=relation_type,
            target_chunk_id=target_chunk_id,
            target_external_ref=target_external_ref,
            citation_text=citation_text,
            metadata=metadata,
        )

    # 6. Corpus Validate
    @server.tool(
        name="mcp_traffic_corpus_validate",
        description="Kiểm tra và thẩm định tính toàn vẹn cấu trúc cơ sở dữ liệu, số lượng văn bản, đoạn quy phạm, tính liên tục của quan hệ cha-con và tính hợp lệ của các cạnh đồ thị.",
    )
    async def corpus_validate() -> CorpusValidateResult:
        return await tool_impl.corpus_validate()

    # 7. Staging Preview
    @server.tool(
        name="mcp_traffic_stg_preview",
        description="Xem trước tóm tắt cấu trúc, nội dung nguyên văn và ngữ cảnh tổng hợp của các đoạn quy phạm trong vùng đệm (.cache/stg) có hỗ trợ phân trang trước khi commit vào cơ sở dữ liệu.",
    )
    async def stg_preview(
        doc_code: Annotated[
            str,
            Field(
                description="Số hiệu văn bản của phiên làm việc trong vùng đệm.",
                examples=["100/2019/NĐ-CP"],
            ),
        ],
        path_prefix: Annotated[
            str | None,
            Field(
                default=None,
                description="Tiền tố đường dẫn ltree tùy chọn để lọc danh sách xem trước.",
                examples=["100_2019_nd_cp.a_5"],
            ),
        ] = None,
        limit: Annotated[
            int,
            Field(
                default=50,
                ge=1,
                le=200,
                description="Số lượng đoạn quy phạm tối đa cần xem trước trên mỗi trang.",
            ),
        ] = 50,
        offset: Annotated[
            int,
            Field(
                default=0,
                ge=0,
                description="Vị trí bắt đầu phân trang danh sách xem trước.",
            ),
        ] = 0,
    ) -> StgPreviewResult:
        return await tool_impl.stg_preview(
            doc_code=doc_code,
            path_prefix=path_prefix,
            limit=limit,
            offset=offset,
        )

    # 7.1 Staging Get Chunk
    @server.tool(
        name="mcp_traffic_stg_get_chunk",
        description="Đọc toàn bộ nội dung nguyên văn, ngữ cảnh tổng hợp, câu dẫn đề và siêu dữ liệu của một đoạn quy phạm (không bị cắt cụt) từ vùng đệm staging theo đường dẫn ltree.",
    )
    async def stg_get_chunk(
        doc_code: Annotated[
            str,
            Field(
                description="Số hiệu văn bản của phiên làm việc trong vùng đệm staging.",
                examples=["100/2019/NĐ-CP"],
            ),
        ],
        path: Annotated[
            str,
            Field(
                description="Đường dẫn phân cấp ltree chính xác của đoạn quy phạm cần đọc toàn văn.",
                examples=["100_2019_nd_cp.c_ii.a_5.c_3.p_a"],
            ),
        ],
    ) -> StgGetChunkResult:
        return await tool_impl.stg_get_chunk(doc_code=doc_code, path=path)

    # 7.2 Staging Get Raw
    @server.tool(
        name="mcp_traffic_stg_get_raw",
        description="Đọc văn bản quy phạm nguồn ban đầu được lưu trong phiên staging theo cửa sổ dòng (line window) để đối chiếu, kiểm tra và phát hiện câu chữ bị bỏ sót.",
    )
    async def stg_get_raw(
        doc_code: Annotated[
            str,
            Field(
                description="Số hiệu văn bản của phiên làm việc trong vùng đệm staging.",
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
    ) -> StgGetRawResult:
        return await tool_impl.stg_get_raw(
            doc_code=doc_code, start_line=start_line, end_line=end_line
        )

    # 7.3 Staging Grep
    @server.tool(
        name="mcp_traffic_stg_grep",
        description="Tìm kiếm nhanh chuỗi ký tự hoặc biểu thức chính quy (Regex) quét qua toàn bộ các đoạn quy phạm trong vùng đệm staging mà không cần phân trang.",
    )
    async def stg_grep(
        doc_code: Annotated[
            str,
            Field(
                description="Số hiệu văn bản của phiên làm việc trong vùng đệm staging.",
                examples=["100/2019/NĐ-CP"],
            ),
        ],
        pattern: Annotated[
            str,
            Field(
                description="Cụm từ tìm kiếm, số hiệu điều khoản hoặc biểu thức chính quy (Regex).",
                examples=["tước quyền sử dụng", "Điều 5", r"từ [0-9]+ đến [0-9]+ triệu"],
            ),
        ],
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
        search_in: Annotated[
            str,
            Field(
                default="ALL",
                description="Phạm vi tìm kiếm: 'ALL' (tất cả), 'VERBATIM' (nguyên văn), 'CONTEXT' (ngữ cảnh), 'PATH' (đường dẫn), 'METADATA' (siêu dữ liệu).",
            ),
        ] = "ALL",
        limit: Annotated[
            int,
            Field(
                default=50,
                ge=1,
                le=200,
                description="Số lượng kết quả khớp tối đa cần trả về.",
            ),
        ] = 50,
    ) -> StgGrepResult:
        return await tool_impl.stg_grep(
            doc_code=doc_code,
            pattern=pattern,
            is_regex=is_regex,
            case_sensitive=case_sensitive,
            search_in=search_in,
            limit=limit,
        )

    # 8. Staging Patch
    @server.tool(
        name="mcp_traffic_stg_patch",
        description="Thực hiện vá lỗi vi phẫu (delta patch) hoặc xóa các đoạn quy phạm trong vùng đệm staging. Hỗ trợ gửi delta fields (chỉ gửi các trường cần sửa mà không làm mất văn bản gốc) và tự động đồng bộ ngữ cảnh xuống các điểm con cháu.",
    )
    async def stg_patch(
        doc_code: Annotated[
            str,
            Field(
                description="Số hiệu văn bản của phiên làm việc trong vùng đệm.",
            ),
        ],
        updated_chunks: Annotated[
            list[dict[str, Any]] | None,
            Field(
                default=None,
                description="Danh sách các bản vá đoạn quy phạm (có thể gửi một phần các trường: path, verbatim_text, contextualized_text, lead_sentence, metadata).",
            ),
        ] = None,
        removed_paths: Annotated[
            list[str] | None,
            Field(
                default=None,
                description="Danh sách các đường dẫn ltree của các đoạn quy phạm cần xóa khỏi phiên làm việc.",
            ),
        ] = None,
        cascade_breadcrumbs: Annotated[
            bool,
            Field(
                default=True,
                description="Tự động cập nhật ngữ cảnh contextualized_text cho các điểm con khi câu dẫn đề lead_sentence của khoản cha thay đổi.",
            ),
        ] = True,
    ) -> StgPatchResult:
        return await tool_impl.stg_patch(
            doc_code=doc_code,
            updated_chunks=updated_chunks,
            removed_paths=removed_paths,
            cascade_breadcrumbs=cascade_breadcrumbs,
        )

    # 9. Staging Add Edges
    @server.tool(
        name="mcp_traffic_stg_add_edges",
        description="Gắn kết và kiểm toán trước (pre-commit linting) các cạnh quan hệ đồ thị pháp lý trong vùng đệm staging. Tự động kiểm tra tính hợp lệ của source_path và target_path nội bộ trước khi lưu.",
    )
    async def stg_add_edges(
        doc_code: Annotated[
            str,
            Field(
                description="Số hiệu văn bản của phiên làm việc trong vùng đệm.",
            ),
        ],
        edges: Annotated[
            list[dict[str, Any]],
            Field(
                description="Danh sách các cạnh quan hệ (source_path, target_path/target_external_ref, relation_type, citation_text, metadata).",
            ),
        ],
    ) -> StgAddEdgesResult:
        return await tool_impl.stg_add_edges(
            doc_code=doc_code,
            edges=edges,
        )

    # 10. Staging Subtree Re-parenting
    @server.tool(
        name="mcp_traffic_stg_reparent",
        description="Tái cấu trúc và di chuyển cả một nhánh cây quy phạm (Chương, Mục, Điều) sang vị trí cha mới trong vùng đệm staging. Tự động cascade đổi đường dẫn ltree của toàn bộ các khoản/điểm con cháu và di dời các cạnh quan hệ đồ thị tương ứng. Hỗ trợ cờ dry_run để xem trước kết quả.",
    )
    async def stg_reparent(
        doc_code: Annotated[
            str,
            Field(
                description="Số hiệu văn bản của phiên làm việc trong vùng đệm.",
                examples=["100/2019/NĐ-CP"],
            ),
        ],
        old_path_prefix: Annotated[
            str,
            Field(
                description="Đường dẫn ltree cũ cần di chuyển (ví dụ: '100_2019_nd_cp.c_i.a_5').",
            ),
        ],
        new_path_prefix: Annotated[
            str,
            Field(
                description="Đường dẫn ltree đích mới (ví dụ: '100_2019_nd_cp.c_ii.a_5').",
            ),
        ],
        dry_run: Annotated[
            bool,
            Field(
                default=False,
                description="Nếu True, chỉ tính toán và mô phỏng số lượng node sẽ thay đổi mà không ghi xuống đĩa.",
            ),
        ] = False,
    ) -> StgReparentResult:
        return await tool_impl.stg_reparent(
            doc_code=doc_code,
            old_path_prefix=old_path_prefix,
            new_path_prefix=new_path_prefix,
            dry_run=dry_run,
        )

    # 11. Staging Commit
    @server.tool(
        name="mcp_traffic_stg_commit",
        description="Xác nhận hoàn tất phiên xử lý và lập chỉ mục văn bản trong vùng đệm staging, chuyển trạng thái phiên làm việc sang AGENT_COMMITTED để sẵn sàng cho chuyên viên pháp lý thẩm định và phê duyệt (không ghi trực tiếp vào CSDL sản xuất).",
    )
    async def stg_commit(
        doc_code: Annotated[
            str,
            Field(
                description="Số hiệu văn bản cần xác nhận hoàn tất trong vùng đệm staging.",
                examples=["100/2019/NĐ-CP"],
            ),
        ],
    ) -> StgCommitResult:
        return await tool_impl.stg_commit(
            doc_code=doc_code,
        )

    return server


class LegalMCPServer:
    """Wrapper providing direct execution, JSON-RPC bridge, and SDK lifecycle management."""

    def __init__(self, tools: LegalMCPTools | None = None) -> None:
        self.tools = tools or LegalMCPTools(
            embedding_engine=SentenceTransformerQueryEmbedder()
        )
        self.mcp_server = create_legal_mcp_server(self.tools)

    async def get_instructions(self, as_of_date: datetime.date | None = None) -> str:
        """Dynamically generates server instructions containing live corpus manifest and dynamic date in Vietnam timezone."""
        manifest = await self.tools.build_dynamic_corpus_manifest(as_of_date=as_of_date)
        return render_server_instructions(manifest_block=manifest, as_of_date=as_of_date)

    async def get_tool_definitions(self) -> list[dict[str, Any]]:
        """Returns registered tool definitions formatted for inspection."""
        tool_objs = await self.mcp_server.list_tools()
        return [
            {
                "name": t.name,
                "description": t.description or "",
                "inputSchema": t.input_schema,
            }
            for t in tool_objs
        ]

    async def execute_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Dispatches tool execution through the official MCPServer tool manager."""
        tool_name = name if name.startswith("mcp_traffic_") else f"mcp_traffic_{name}"
        res = await self.mcp_server.call_tool(tool_name, args)
        if isinstance(res, CallToolResult) and res.is_error:
            err_msg = "\n".join(
                c.text for c in res.content if isinstance(c, TextContent)
            )
            raise LegalDomainError(
                error_code=-32603,
                message=err_msg or f"Lỗi khi thực thi công cụ '{name}'",
            )
        if isinstance(res, CallToolResult):
            for item in res.content:
                if isinstance(item, TextContent):
                    try:
                        parsed = json.loads(item.text)
                        if isinstance(parsed, dict):
                            return parsed
                        return {"result": parsed}
                    except (json.JSONDecodeError, ValueError):
                        return {"result": item.text}
        return {}

    async def handle_request_dict(self, req: dict[str, Any]) -> dict[str, Any] | None:
        """Processes JSON-RPC 2.0 requests with standardized envelope for headless CLI & tests."""
        if not isinstance(req, dict) or req.get("jsonrpc") != "2.0":
            return {
                "jsonrpc": "2.0",
                "id": req.get("id") if isinstance(req, dict) else None,
                "error": {"code": -32600, "message": "Yêu cầu JSON-RPC 2.0 không hợp lệ"},
            }

        req_id = req.get("id")
        method = req.get("method", "")
        params = req.get("params") or {}

        try:
            if method == "initialize":
                dyn_instructions = await self.get_instructions()
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {
                            "name": SERVER_NAME,
                            "version": SERVER_VERSION,
                        },
                        "instructions": dyn_instructions,
                    },
                }
            if method == "notifications/initialized":
                return None
            if method == "ping":
                return {"jsonrpc": "2.0", "id": req_id, "result": {}}
            if method == "tools/list":
                defs = await self.get_tool_definitions()
                return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": defs}}
            if method == "tools/call":
                if not isinstance(params, dict):
                    return {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {
                            "code": -32602,
                            "message": "params bắt buộc phải là một đối tượng JSON",
                        },
                    }
                t_name = str(params.get("name", ""))
                t_args = params.get("arguments", {})
                if not isinstance(t_args, dict):
                    return {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {
                            "code": -32602,
                            "message": "arguments bắt buộc phải là một đối tượng JSON",
                        },
                    }
                out = await self.execute_tool(t_name, t_args)
                return {"jsonrpc": "2.0", "id": req_id, "result": out}

            if method.startswith("mcp_traffic_"):
                args = params if isinstance(params, dict) else {}
                out = await self.execute_tool(method, args)
                return {"jsonrpc": "2.0", "id": req_id, "result": out}

            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Không tìm thấy phương thức: {method}"},
            }

        except (LegalDomainError, MCPError) as err:
            code = err.error_code if isinstance(err, LegalDomainError) else err.code
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": code,
                    "message": err.message,
                    "data": err.data,
                },
            }
        except (RuntimeError, ValueError, TypeError, KeyError, OSError) as exc:
            logger.exception("Error handling request")
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32603, "message": str(exc)},
            }

    def run(self, transport: str = "stdio") -> None:
        """Runs the official MCPServer transport."""
        self.mcp_server.run(transport=transport)  # type: ignore


def run_mcp_server(log_file: str | None = None) -> None:
    """Entry point to run the official MCP Server over Stdio."""
    if log_file:
        from pathlib import Path

        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            filename=log_file,
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )
    server = LegalMCPServer()
    server.run(transport="stdio")
