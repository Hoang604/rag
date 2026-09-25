"""Tool registration module for Vietnamese Traffic Law Model Context Protocol (MCP) Server."""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from rag_eval.legal.mcp.tools import (
    AddMetadataResult,
    ChunkBacklogResult,
    CorpusValidateResult,
    GraphEdgeWriteResult,
    GraphTraverseResult,
    HierarchicalNavigateResult,
    HybridSearchResult,
    LegalMCPTools,
    StgAddEdgesResult,
    StgCommitResult,
    StgFinalizeResult,
    StgGetChunkResult,
    StgGetRawResult,
    StgGrepResult,
    StgListSessionsResult,
    StgPatchResult,
    StgPollPendingResult,
    StgPreviewResult,
    StgReparentResult,
    VerbatimGrepResult,
)

_EMPTY_STR_LIST: list[str] = []
_EMPTY_DICT_LIST: list[dict[str, Any]] = []
_EMPTY_DICT: dict[str, Any] = {}


def register_legal_mcp_tools(server: MCPServer, tool_impl: LegalMCPTools) -> None:
    """Registers all 16 canonical Agent-First legal tools onto the MCPServer instance."""

    # 1. Hybrid Search
    @server.tool(
        name="hybrid_search",
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
                examples=[["ND_168_2024"], ["ND_168_2024", "LUAT_TTATGTDB_2024"]],
            ),
        ] = _EMPTY_STR_LIST,
        rerank: Annotated[
            bool,
            Field(
                default=False,
                description="Bật hoặc tắt bước xếp hạng lại bằng cross-encoder. Mặc định tắt. Bước này bị tự động tắt với truy vấn gõ không dấu.",
            ),
        ] = False,
    ) -> HybridSearchResult:
        return await tool_impl.hybrid_search(
            query=query,
            temporal_violation_date=temporal_violation_date or None,
            limit=limit,
            doc_codes=doc_codes or None,
            rerank=rerank or None,
        )

    # 2. Verbatim Grep
    @server.tool(
        name="verbatim_grep",
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
    ) -> VerbatimGrepResult:
        return await tool_impl.verbatim_grep(
            pattern=pattern,
            is_regex=is_regex,
            case_sensitive=case_sensitive,
            temporal_violation_date=temporal_violation_date or None,
            limit=limit,
        )

    # 3. Hierarchical Navigate
    @server.tool(
        name="hierarchical_navigate",
        description="Điều hướng cấu trúc cây phân cấp văn bản pháp luật (Văn bản -> Chương -> Mục -> Điều -> Khoản -> Điểm -> Phụ lục) xoay quanh một nút quy phạm được chỉ định thông qua toán tử ltree.",
    )
    async def hierarchical_navigate(
        path: Annotated[
            str,
            Field(
                default="",
                description="Đường dẫn cây phân cấp ltree của nút quy phạm mục tiêu. Cung cấp 'path' hoặc 'chunk_id'.",
                examples=["100_2019_nd_cp.c_ii.a_5.c_3.p_a", "100_2019_nd_cp.a_5"],
            ),
        ] = "",
        chunk_id: Annotated[
            str,
            Field(
                default="",
                description="Mã định danh UUID của đoạn quy phạm cần điều hướng mở rộng. Cung cấp 'path' hoặc 'chunk_id'.",
            ),
        ] = "",
        direction: Annotated[
            str,
            Field(
                default="FULL_ARTICLE",
                description="Phạm vi điều hướng: 'FULL_ARTICLE' (toàn bộ các Khoản/Điểm thuộc cùng Điều cha), 'CHILDREN' (tất cả các phân vị con trực tiếp), 'PARENT_CHAIN' (chuỗi phả hệ tổ tiên từ Văn bản đến nút hiện tại), 'SIBLINGS' (các nút cùng cấp dưới cùng một nút cha).",
            ),
        ] = "FULL_ARTICLE",
    ) -> HierarchicalNavigateResult:
        return await tool_impl.hierarchical_navigate(
            path=path or None,
            chunk_id=chunk_id or None,
            direction=direction,
        )

    # 4. Graph Traverse
    @server.tool(
        name="graph_traverse",
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
            str,
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
        name="graph_edge_write",
        description="Ghi nhận và lưu trữ một liên kết quan hệ pháp lý có hướng đã được xác thực giữa hai nút quy phạm vào nhật ký WAL staging.",
    )
    async def graph_edge_write(
        source_chunk_id: Annotated[
            str,
            Field(
                description="Mã định danh UUID hoặc ltree path của nút quy phạm nguồn.",
            ),
        ],
        relation_type: Annotated[
            str,
            Field(
                default="REFERENCES",
                description="Loại quan hệ pháp lý: 'SANCTIONS' (chế tài áp dụng), 'REFERENCES' (dẫn chiếu điều khoản), 'OVERRIDES' (bãi bỏ/thay thế), 'EXEMPTS' (ngoại lệ miễn trừ), 'MODIFIES_AND_REPLACES' (sửa đổi bổ sung), 'GUIDES' (quy chuẩn hướng dẫn), 'DEFINES_TERM' (định nghĩa thuật ngữ).",
            ),
        ] = "REFERENCES",
        target_chunk_id: Annotated[
            str,
            Field(
                default="",
                description="Mã định danh UUID của nút quy phạm đích nếu đã tồn tại trong cơ sở dữ liệu.",
            ),
        ] = "",
        target_external_ref: Annotated[
            str,
            Field(
                default="",
                description="Chuỗi trích dẫn điều khoản đích nếu văn bản đích chưa được nạp vào cơ sở dữ liệu.",
                examples=["Khoản 1 Điều 12 Luật Giao thông đường bộ"],
            ),
        ] = "",
        citation_text: Annotated[
            str,
            Field(
                default="",
                description="Đoạn văn bản nguyên văn thể hiện mối quan hệ dẫn chiếu này.",
                examples=["theo quy định tại Điều 12"],
            ),
        ] = "",
        metadata: Annotated[
            dict[str, Any],
            Field(
                description="Dữ liệu siêu thông tin bổ sung về điều kiện hoặc ngữ cảnh liên kết.",
            ),
        ] = _EMPTY_DICT,
    ) -> GraphEdgeWriteResult:
        return await tool_impl.graph_edge_write(
            source_chunk_id=source_chunk_id,
            relation_type=relation_type,
            target_chunk_id=target_chunk_id or None,
            target_external_ref=target_external_ref or None,
            citation_text=citation_text or None,
            metadata=metadata or None,
        )

    # 6. Corpus Validate
    @server.tool(
        name="corpus_validate",
        description="Kiểm tra và thẩm định tính toàn vẹn cấu trúc cơ sở dữ liệu, số lượng văn bản, đoạn quy phạm, tính liên tục của quan hệ cha-con và tính hợp lệ của các cạnh đồ thị.",
    )
    async def corpus_validate() -> CorpusValidateResult:
        return await tool_impl.corpus_validate()

    # 7. Add Metadata
    @server.tool(
        name="add_metadata",
        description="Ghi nhận rằng một đoạn quy phạm đã trả lời được một câu hỏi cụ thể, sau khi đã tra cứu và xác nhận nội dung. Đây là phản hồi độ liên quan dùng cho nghiên cứu xếp hạng về sau; nó KHÔNG thay đổi kết quả truy xuất hiện tại.",
    )
    async def add_metadata(
        chunk_id: Annotated[
            str,
            Field(
                description="Định danh của đoạn quy phạm đã trả lời được câu hỏi.",
            ),
        ],
        query: Annotated[
            str,
            Field(
                description="Câu hỏi mà đoạn quy phạm này trả lời được, ghi nguyên văn như người dùng đã hỏi.",
                examples=["vượt đèn đỏ xe máy phạt bao nhiêu"],
            ),
        ],
        note: Annotated[
            str,
            Field(
                default="",
                description="Ghi chú tuỳ chọn về lý do đoạn này trả lời được câu hỏi.",
            ),
        ] = "",
    ) -> AddMetadataResult:
        return await tool_impl.add_metadata(
            chunk_id=chunk_id,
            query=query,
            note=note or None,
        )

    # 8. Staging Preview
    @server.tool(
        name="stg_preview",
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
            str,
            Field(
                default="",
                description="Tiền tố đường dẫn ltree tùy chọn để lọc danh sách xem trước.",
                examples=["100_2019_nd_cp.a_5"],
            ),
        ] = "",
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
            path_prefix=path_prefix or None,
            limit=limit,
            offset=offset,
        )

    # 9. Staging Get Chunk
    @server.tool(
        name="stg_get_chunk",
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

    # 10. Staging Get Raw
    @server.tool(
        name="stg_get_raw",
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

    # 11. Staging Grep
    @server.tool(
        name="stg_grep",
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

    # 12. Staging Patch
    @server.tool(
        name="stg_patch",
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
            list[dict[str, Any]],
            Field(
                description="Danh sách các bản vá đoạn quy phạm (có thể gửi một phần các trường: path, verbatim_text, contextualized_text, lead_sentence, metadata).",
            ),
        ] = _EMPTY_DICT_LIST,
        removed_paths: Annotated[
            list[str],
            Field(
                description="Danh sách các đường dẫn ltree của các đoạn quy phạm cần xóa khỏi phiên làm việc.",
            ),
        ] = _EMPTY_STR_LIST,
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
            updated_chunks=updated_chunks or None,
            removed_paths=removed_paths or None,
            cascade_breadcrumbs=cascade_breadcrumbs,
        )

    # 13. Staging Add Edges
    @server.tool(
        name="stg_add_edges",
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

    # 14. Staging Subtree Re-parenting
    @server.tool(
        name="stg_reparent",
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

    # 15. Staging Commit
    @server.tool(
        name="stg_commit",
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

    # 16. Staging Poll Pending Chunks
    @server.tool(
        name="stg_poll_pending",
        description="Lấy danh sách các đoạn quy phạm (chunks) chưa chốt (PENDING) kèm thống kê tiến độ rà soát tổng thể để xử lý theo từng đợt (batch) trong vùng đệm staging.",
    )
    async def stg_poll_pending_chunks(
        doc_code: Annotated[
            str,
            Field(
                description="Số hiệu văn bản của phiên làm việc trong vùng đệm staging.",
                examples=["100/2019/NĐ-CP"],
            ),
        ],
        limit: Annotated[
            int,
            Field(
                default=10,
                ge=1,
                le=50,
                description="Số lượng đoạn quy phạm tối đa cần lấy ra trong đợt này.",
            ),
        ] = 10,
        path_prefix: Annotated[
            str,
            Field(
                default="",
                description="Tiền tố đường dẫn ltree tùy chọn để giới hạn phạm vi quét (ví dụ: '100_2019_nd_cp.a_5').",
            ),
        ] = "",
    ) -> StgPollPendingResult:
        return await tool_impl.stg_poll_pending_chunks(
            doc_code=doc_code,
            limit=limit,
            path_prefix=path_prefix or None,
        )

    # 17. Staging Finalize Chunks
    @server.tool(
        name="stg_finalize_chunks",
        description="Đánh dấu danh sách các đoạn quy phạm (chunks) đã hoàn tất rà soát và gắn đủ quan hệ liên quan sang trạng thái ĐÃ CHỐT (FINALIZED) trong vùng đệm staging.",
    )
    async def stg_finalize_chunks(
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
                description="Danh sách đường dẫn ltree của các đoạn quy phạm cần chốt hoàn tất.",
                examples=[["100_2019_nd_cp.c_ii.a_5.c_3.p_a"]],
            ),
        ],
    ) -> StgFinalizeResult:
        return await tool_impl.stg_finalize_chunks(
            doc_code=doc_code,
            paths=paths,
        )

    # 18. Staging List Sessions
    @server.tool(
        name="stg_list_sessions",
        description="Liệt kê danh sách tóm tắt toàn bộ các phiên làm việc và tài liệu pháp lý đang có trong vùng đệm staging (.cache/stg), hỗ trợ lọc theo trạng thái.",
    )
    async def stg_list_sessions(
        status: Annotated[
            str,
            Field(
                default="",
                description="Lọc danh sách theo trạng thái phiên làm việc (ví dụ: 'PENDING', 'AGENT_COMMITTED', 'PROMOTED'). Để trống để lấy tất cả.",
                examples=["PENDING", "AGENT_COMMITTED"],
            ),
        ] = "",
    ) -> StgListSessionsResult:
        return await tool_impl.stg_list_sessions(status=status or None)

    # 19. Chunk Backlog Poll
    @server.tool(
        name="chunk_backlog_poll",
        description="Truy vấn danh sách các đoạn quy phạm chưa hoàn tất liên kết (UNFINALIZED) hoặc chứa các viện dẫn/ngoại lệ mở ('theo quy định khác của pháp luật') để phục vụ thu nạp văn bản bổ sung hoặc liên kết tri thức.",
    )
    async def chunk_backlog_poll(
        finalization_state: Annotated[
            str,
            Field(
                default="",
                description="Lọc theo trạng thái hoàn tất pháp lý cụ thể: 'UNFINALIZED_PENDING_EXTERNAL' (chờ văn bản ngoài) hoặc 'UNFINALIZED_OPEN_ENDED' (viện dẫn mở). Để trống để lấy tất cả.",
                examples=["UNFINALIZED_PENDING_EXTERNAL", "UNFINALIZED_OPEN_ENDED"],
            ),
        ] = "",
        doc_code: Annotated[
            str,
            Field(
                default="",
                description="Lọc theo số hiệu văn bản (ví dụ: '100/2019/NĐ-CP'). Để trống để quét toàn bộ kho.",
                examples=["100/2019/NĐ-CP"],
            ),
        ] = "",
        limit: Annotated[
            int,
            Field(
                default=50,
                ge=1,
                le=100,
                description="Số lượng đoạn quy phạm tối đa cần trả về.",
            ),
        ] = 50,
    ) -> ChunkBacklogResult:
        return await tool_impl.chunk_backlog_poll(
            finalization_state=finalization_state or None,
            doc_code=doc_code or None,
            limit=limit,
        )

