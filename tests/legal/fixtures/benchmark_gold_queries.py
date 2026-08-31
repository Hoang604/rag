"""Authoritative Statutory Benchmark Queries Grounded on Real PostgreSQL Law 36/2024 Corpus.

Every query is authored to evaluate realistic natural-language driver/citizen inquiries
against exact statutory provisions in Law 36/2024/QH15 (Luật Trật tự, an toàn giao thông đường bộ 2024),
providing verifiable gold paths, chunk IDs, contextualized texts, and complete statutory answers.
"""

from typing import TypedDict


class StatutoryBenchmarkQuery(TypedDict):
    id: str
    query: str
    category: str
    expected_doc_code: str
    expected_article_number: int | None
    expected_clause_number: int | None
    gold_hierarchy_paths: list[str]
    gold_chunk_ids: list[str]
    gold_contextualized_text: str
    ground_truth_answer: str


LAW36_STATUTORY_BENCHMARK: list[StatutoryBenchmarkQuery] = [
    # -------------------------------------------------------------------------
    # CHAPTER I: QUY ĐỊNH CHUNG & CÁC HÀNH VI BỊ NGHIÊM CẤM (Điều 1 - Điều 9)
    # -------------------------------------------------------------------------
    {
        "id": "Q001",
        "query": "Không có giấy phép lái xe mà điều khiển xe cơ giới tham gia giao thông có bị cấm không?",
        "category": "Hành vi bị cấm - GPLX",
        "expected_doc_code": "36/2024/QH15",
        "expected_article_number": 9,
        "expected_clause_number": 1,
        "gold_hierarchy_paths": ["doc_36_2024_qh15.c_i.a9.c1"],
        "gold_chunk_ids": ["5d57c497-8b9d-5d8c-89ec-3c56408305d1"],
        "gold_contextualized_text": (
            "[ĐIỀU 9]: Các hành vi bị nghiêm cấm\n"
            "[KHOẢN 1]: 1. Điều khiển xe cơ giới tham gia giao thông đường bộ không có giấy phép lái xe theo quy định của pháp luật; "
            "điều khiển xe máy chuyên dùng tham gia giao thông đường bộ không có giấy phép lái xe hoặc chứng chỉ bồi dưỡng kiến thức "
            "pháp luật về giao thông đường bộ, bằng hoặc chứng chỉ điều khiển xe máy chuyên dùng."
        ),
        "ground_truth_answer": (
            "Bị nghiêm cấm tuyệt đối theo Khoản 1 Điều 9 Luật Trật tự, an toàn giao thông đường bộ 2024 (Luật 36/2024/QH15)."
        ),
    },
    {
        "id": "Q002",
        "query": "Lái xe ô tô hoặc xe máy mà trong máu hoặc hơi thở có nồng độ cồn thì có bị nghiêm cấm không?",
        "category": "Hành vi bị cấm - Nồng độ cồn",
        "expected_doc_code": "36/2024/QH15",
        "expected_article_number": 9,
        "expected_clause_number": 2,
        "gold_hierarchy_paths": ["doc_36_2024_qh15.c_i.a9.c2"],
        "gold_chunk_ids": ["28b433a6-dfeb-5f0e-a60a-df23aca622af"],
        "gold_contextualized_text": (
            "[ĐIỀU 9]: Các hành vi bị nghiêm cấm\n"
            "[KHOẢN 2]: 2. Điều khiển phương tiện tham gia giao thông đường bộ mà trong máu hoặc hơi thở có nồng độ cồn."
        ),
        "ground_truth_answer": (
            "Bị nghiêm cấm tuyệt đối đối với mọi nồng độ cồn theo Khoản 2 Điều 9 Luật 36/2024/QH15."
        ),
    },
    {
        "id": "Q003",
        "query": "Người điều khiển phương tiện mà trong cơ thể có ma túy có được phép lái xe không?",
        "category": "Hành vi bị cấm - Ma túy",
        "expected_doc_code": "36/2024/QH15",
        "expected_article_number": 9,
        "expected_clause_number": 3,
        "gold_hierarchy_paths": ["doc_36_2024_qh15.c_i.a9.c3"],
        "gold_chunk_ids": ["c7623b9d-b5cd-5465-9094-5877c3fa68b3"],
        "gold_contextualized_text": (
            "[ĐIỀU 9]: Các hành vi bị nghiêm cấm\n"
            "[KHOẢN 3]: 3. Điều khiển phương tiện tham gia giao thông đường bộ mà trong cơ thể có chất ma túy "
            "hoặc chất kích thích khác mà pháp luật cấm sử dụng."
        ),
        "ground_truth_answer": (
            "Bị nghiêm cấm theo Khoản 3 Điều 9 Luật 36/2024/QH15 khi trong cơ thể có chất ma túy hoặc chất kích thích bị cấm."
        ),
    },
    {
        "id": "Q004",
        "query": "Hành vi đua xe, tổ chức đua xe, lạng lách đánh võng bị cấm tại điều khoản nào của Luật Trật tự ATGT đường bộ 2024?",
        "category": "Hành vi bị cấm - Đua xe",
        "expected_doc_code": "36/2024/QH15",
        "expected_article_number": 9,
        "expected_clause_number": 5,
        "gold_hierarchy_paths": ["doc_36_2024_qh15.c_i.a9.c5"],
        "gold_chunk_ids": ["4ce901e2-e9f1-52f6-a7ee-3998fcb09e38"],
        "gold_contextualized_text": (
            "[ĐIỀU 9]: Các hành vi bị nghiêm cấm\n"
            "[KHOẢN 5]: 5. Đua xe, tổ chức đua xe, xúi giục, giúp sức, cổ vũ đua xe trái phép; "
            "điều khiển phương tiện tham gia giao thông đường bộ lạng lách, đánh võng, rú ga liên tục."
        ),
        "ground_truth_answer": (
            "Quy định cấm tại Khoản 5 Điều 9 Luật 36/2024/QH15."
        ),
    },
    {
        "id": "Q005",
        "query": "Dùng tay cầm điện thoại khi đang lái xe chạy trên đường có bị cấm không?",
        "category": "Hành vi bị cấm - Sử dụng điện thoại",
        "expected_doc_code": "36/2024/QH15",
        "expected_article_number": 9,
        "expected_clause_number": 6,
        "gold_hierarchy_paths": ["doc_36_2024_qh15.c_i.a9.c6"],
        "gold_chunk_ids": ["169136a0-a364-571d-8995-d4076fcfad34"],
        "gold_contextualized_text": (
            "[ĐIỀU 9]: Các hành vi bị nghiêm cấm\n"
            "[KHOẢN 6]: 6. Dùng tay cầm và sử dụng điện thoại hoặc thiết bị điện tử khác khi điều khiển phương tiện tham gia giao thông đang di chuyển trên đường bộ."
        ),
        "ground_truth_answer": (
            "Bị nghiêm cấm theo Khoản 6 Điều 9 Luật 36/2024/QH15 đối với hành vi dùng tay cầm và sử dụng điện thoại hoặc thiết bị điện tử khi đang di chuyển."
        ),
    },
    {
        "id": "Q006",
        "query": "Chủ xe giao xe cho người không đủ điều kiện cầm lái tham gia giao thông có bị cấm không?",
        "category": "Hành vi bị cấm - Giao xe",
        "expected_doc_code": "36/2024/QH15",
        "expected_article_number": 9,
        "expected_clause_number": 7,
        "gold_hierarchy_paths": ["doc_36_2024_qh15.c_i.a9.c7"],
        "gold_chunk_ids": ["9ba319a5-0bda-5f79-b46a-e00f1083b88b"],
        "gold_contextualized_text": (
            "[ĐIỀU 9]: Các hành vi bị nghiêm cấm\n"
            "[KHOẢN 7]: 7. Giao xe cơ giới, xe máy chuyên dùng cho người không đủ điều kiện theo quy định của pháp luật để điều khiển xe tham gia giao thông đường bộ."
        ),
        "ground_truth_answer": (
            "Bị nghiêm cấm theo Khoản 7 Điều 9 Luật 36/2024/QH15."
        ),
    },
    {
        "id": "Q007",
        "query": "Hành vi che lấp, bẻ cong hoặc làm thay đổi chữ số của biển số xe có bị nghiêm cấm không?",
        "category": "Hành vi bị cấm - Biển số",
        "expected_doc_code": "36/2024/QH15",
        "expected_article_number": 9,
        "expected_clause_number": 17,
        "gold_hierarchy_paths": ["doc_36_2024_qh15.c_i.a9.c17"],
        "gold_chunk_ids": ["f1177044-6bd2-551c-8e06-993347c65371"],
        "gold_contextualized_text": (
            "[ĐIỀU 9]: Các hành vi bị nghiêm cấm\n"
            "[KHOẢN 17]: 17. Sản xuất, sử dụng, mua, bán trái phép biển số xe; điều khiển xe cơ giới, xe máy chuyên dùng gắn biển số xe "
            "không do cơ quan nhà nước có thẩm quyền cấp, gắn biển số xe không đúng vị trí; bẻ cong, che lấp biển số xe; "
            "làm thay đổi chữ, số, màu sắc, hình dạng, kích thước của biển số xe."
        ),
        "ground_truth_answer": (
            "Bị nghiêm cấm theo Khoản 17 Điều 9 Luật 36/2024/QH15."
        ),
    },
    {
        "id": "Q008",
        "query": "Hành vi bỏ trốn sau khi gây tai nạn giao thông để trốn tránh trách nhiệm bị pháp luật quy định thế nào?",
        "category": "Hành vi bị cấm - Tai nạn",
        "expected_doc_code": "36/2024/QH15",
        "expected_article_number": 9,
        "expected_clause_number": 26,
        "gold_hierarchy_paths": ["doc_36_2024_qh15.c_i.a9.c26"],
        "gold_chunk_ids": ["5ce79c03-e74c-5cb1-a950-8f325700d631"],
        "gold_contextualized_text": (
            "[ĐIỀU 9]: Các hành vi bị nghiêm cấm\n"
            "[KHOẢN 26]: 26. Bỏ trốn sau khi gây tai nạn giao thông đường bộ để trốn tránh trách nhiệm; khi có điều kiện mà cố ý không cứu giúp người bị tai nạn; "
            "xâm phạm tính mạng, sức khỏe, tài sản của người bị nạn..."
        ),
        "ground_truth_answer": (
            "Bị nghiêm cấm tuyệt đối theo Khoản 26 Điều 9 Luật 36/2024/QH15."
        ),
    },

    # -------------------------------------------------------------------------
    # CHAPTER II: QUY TẮC GIAO THÔNG ĐƯỜNG BỘ (Điều 10 - Điều 33)
    # -------------------------------------------------------------------------
    {
        "id": "Q009",
        "query": "Người lái xe ô tô và hành khách ngồi trên ô tô có bắt buộc phải thắt dây an toàn không?",
        "category": "Quy tắc chung - Thắt dây an toàn",
        "expected_doc_code": "36/2024/QH15",
        "expected_article_number": 10,
        "expected_clause_number": 2,
        "gold_hierarchy_paths": ["doc_36_2024_qh15.c_ii.a10.c2"],
        "gold_chunk_ids": ["6e03ff25-5a03-58f1-a232-283d89cb5be7"],
        "gold_contextualized_text": (
            "[ĐIỀU 10]: Quy tắc chung\n"
            "[KHOẢN 2]: 2. Người lái xe và người được chở trên xe ô tô phải thắt dây đai an toàn tại những chỗ có trang bị dây đai an toàn khi tham gia giao thông đường bộ."
        ),
        "ground_truth_answer": (
            "Bắt buộc thắt dây an toàn tại tất cả các vị trí có trang bị dây an toàn theo Khoản 2 Điều 10 Luật 36/2024/QH15."
        ),
    },
    {
        "id": "Q010",
        "query": "Quy định về việc chở trẻ em dưới 10 tuổi và chiều cao dưới 1,35m trên xe ô tô như thế nào?",
        "category": "Quy tắc chung - Trẻ em trên ô tô",
        "expected_doc_code": "36/2024/QH15",
        "expected_article_number": 10,
        "expected_clause_number": 3,
        "gold_hierarchy_paths": ["doc_36_2024_qh15.c_ii.a10.c3"],
        "gold_chunk_ids": ["61947612-d8e5-50b3-8e71-c4f5d9b6eb33"],
        "gold_contextualized_text": (
            "[ĐIỀU 10]: Quy tắc chung\n"
            "[KHOẢN 3]: 3. Khi chở trẻ em dưới 10 tuổi và chiều cao dưới 1,35 mét trên xe ô tô không được cho trẻ em ngồi cùng hàng ghế với người lái xe, "
            "trừ loại xe ô tô chỉ có một hàng ghế; người lái xe phải sử dụng, hướng dẫn sử dụng thiết bị an toàn phù hợp cho trẻ em."
        ),
        "ground_truth_answer": (
            "Không được cho trẻ em dưới 10 tuổi và dưới 1,35m ngồi cùng hàng ghế với lái xe (trừ xe chỉ có 1 hàng ghế) và phải sử dụng thiết bị an toàn phù hợp theo Khoản 3 Điều 10 Luật 36/2024/QH15."
        ),
    },
    {
        "id": "Q011",
        "query": "Thứ tự ưu tiên chấp hành hiệu lệnh báo hiệu đường bộ được quy định như thế nào?",
        "category": "Báo hiệu đường bộ - Thứ tự ưu tiên",
        "expected_doc_code": "36/2024/QH15",
        "expected_article_number": 11,
        "expected_clause_number": 2,
        "gold_hierarchy_paths": ["doc_36_2024_qh15.c_ii.a11.c2.p_a"],
        "gold_chunk_ids": ["0f3789ad-e9ae-5d2e-a7fe-0d991bb15c0e"],
        "gold_contextualized_text": (
            "[ĐIỀU 11]: Chấp hành báo hiệu đường bộ\n"
            "[KHOẢN 2]: 2. Người tham gia giao thông đường bộ phải chấp hành báo hiệu đường bộ theo thứ tự ưu tiên từ trên xuống dưới: "
            "a) Hiệu lệnh người điều khiển GT; b) Đèn tín hiệu; c) Biển báo hiệu; d) Vạch kẻ đường..."
        ),
        "ground_truth_answer": (
            "Ưu tiên cao nhất là Hiệu lệnh của người điều khiển giao thông (CSGT) > Đèn tín hiệu > Biển báo hiệu > Vạch kẻ đường theo Khoản 2 Điều 11 Luật 36/2024/QH15."
        ),
    },
    {
        "id": "Q012",
        "query": "Khi Cảnh sát giao thông giơ tay phải thẳng đứng thì người tham gia giao thông phải làm gì?",
        "category": "Hiệu lệnh CSGT - Giơ tay thẳng đứng",
        "expected_doc_code": "36/2024/QH15",
        "expected_article_number": 11,
        "expected_clause_number": 3,
        "gold_hierarchy_paths": ["doc_36_2024_qh15.c_ii.a11.c3.p_a"],
        "gold_chunk_ids": ["594ba4b0-ae9d-5bcb-b818-9949e3919cfb"],
        "gold_contextualized_text": (
            "[ĐIỀU 11]: Chấp hành báo hiệu đường bộ\n"
            "[KHOẢN 3]: 3. Hiệu lệnh của người điều khiển giao thông:\n"
            "a) Tay bên phải giơ thẳng đứng để báo hiệu cho người tham gia giao thông đường bộ ở tất cả các hướng phải dừng lại;"
        ),
        "ground_truth_answer": (
            "Người tham gia giao thông ở tất cả các hướng phải dừng lại theo Điểm a Khoản 3 Điều 11 Luật 36/2024/QH15."
        ),
    },
    {
        "id": "Q013",
        "query": "Quy tắc chấp hành tín hiệu đèn giao thông màu vàng và màu đỏ quy định thế nào?",
        "category": "Đèn tín hiệu giao thông",
        "expected_doc_code": "36/2024/QH15",
        "expected_article_number": 11,
        "expected_clause_number": 4,
        "gold_hierarchy_paths": ["doc_36_2024_qh15.c_ii.a11.c4.p_b", "doc_36_2024_qh15.c_ii.a11.c4.p_c"],
        "gold_chunk_ids": ["d1d4f8b5-5528-5696-a865-8c5f9a7ff1a0", "68533d7b-7a93-5058-af38-53dd2ae3f20a"],
        "gold_contextualized_text": (
            "[ĐIỀU 11]: Chấp hành báo hiệu đường bộ\n"
            "[KHOẢN 4]: b) Tín hiệu đèn màu vàng phải dừng lại trước vạch dừng; c) Tín hiệu đèn màu đỏ là cấm đi."
        ),
        "ground_truth_answer": (
            "Đèn vàng phải dừng lại trước vạch dừng (trừ khi đã đi qua vạch dừng thì được đi tiếp), đèn đỏ cấm đi theo Khoản 4 Điều 11 Luật 36/2024/QH15."
        ),
    },
    {
        "id": "Q014",
        "query": "Tại vị trí vừa có biển báo hiệu cố định vừa có biển báo tạm thời trái nhau thì tuân thủ biển nào?",
        "category": "Biển báo hiệu tạm thời",
        "expected_doc_code": "36/2024/QH15",
        "expected_article_number": 11,
        "expected_clause_number": 12,
        "gold_hierarchy_paths": ["doc_36_2024_qh15.c_ii.a11.c12"],
        "gold_chunk_ids": ["65f97f6a-322a-5436-b554-63c118827258"],
        "gold_contextualized_text": (
            "[ĐIỀU 11]: Chấp hành báo hiệu đường bộ\n"
            "[KHOẢN 12]: 12. Khi ở một vị trí vừa có biển báo hiệu đặt cố định vừa có biển báo hiệu tạm thời mà hai biển có ý nghĩa khác nhau, "
            "người tham gia giao thông đường bộ phải chấp hành hiệu lệnh của biển báo hiệu tạm thời."
        ),
        "ground_truth_answer": (
            "Phải chấp hành hiệu lệnh của biển báo hiệu tạm thời theo Khoản 12 Điều 11 Luật 36/2024/QH15."
        ),
    },
    {
        "id": "Q015",
        "query": "Quy tắc di chuyển của phương tiện đi với tốc độ thấp hơn trên đường có nhiều làn xe?",
        "category": "Sử dụng làn đường",
        "expected_doc_code": "36/2024/QH15",
        "expected_article_number": 13,
        "expected_clause_number": 1,
        "gold_hierarchy_paths": ["doc_36_2024_qh15.c_ii.a13.c1"],
        "gold_chunk_ids": ["0067914a-12e3-52e2-a36b-8c16d1f8fb60"],
        "gold_contextualized_text": (
            "[ĐIỀU 13]: Sử dụng làn đường\n"
            "[KHOẢN 1]: 1. Phương tiện tham gia giao thông đường bộ di chuyển với tốc độ thấp hơn phải đi về bên phải theo chiều đi của mình."
        ),
        "ground_truth_answer": (
            "Phương tiện có tốc độ thấp hơn phải đi về bên phải theo chiều đi theo Khoản 1 Điều 13 Luật 36/2024/QH15."
        ),
    },
    {
        "id": "Q016",
        "query": "Xe thô sơ phải đi ở làn đường nào trên đường có phân chia làn đường?",
        "category": "Sử dụng làn đường - Xe thô sơ",
        "expected_doc_code": "36/2024/QH15",
        "expected_article_number": 13,
        "expected_clause_number": 3,
        "gold_hierarchy_paths": ["doc_36_2024_qh15.c_ii.a13.c3"],
        "gold_chunk_ids": ["7b5938dc-95b4-560b-99e8-860b57f33bd0"],
        "gold_contextualized_text": (
            "[ĐIỀU 13]: Sử dụng làn đường\n"
            "[KHOẢN 3]: 3. Trên một chiều đường có vạch kẻ phân làn đường, xe thô sơ phải đi trên làn đường bên phải trong cùng, "
            "xe cơ giới, xe máy chuyên dùng đi trên làn đường bên trái."
        ),
        "ground_truth_answer": (
            "Xe thô sơ phải đi trên làn đường bên phải trong cùng theo Khoản 3 Điều 13 Luật 36/2024/QH15."
        ),
    },
    {
        "id": "Q017",
        "query": "Khi vượt xe khác, các xe phải vượt về phía bên nào và có trường hợp nào được vượt bên phải?",
        "category": "Vượt xe",
        "expected_doc_code": "36/2024/QH15",
        "expected_article_number": 14,
        "expected_clause_number": 2,
        "gold_hierarchy_paths": ["doc_36_2024_qh15.c_ii.a14.c2"],
        "gold_chunk_ids": ["7c7b5b62-a361-5a84-a8eb-0432aac585bd"],
        "gold_contextualized_text": (
            "[ĐIỀU 14]: Vượt xe và nhường đường cho xe xin vượt\n"
            "[KHOẢN 2]: 2. Khi vượt các xe phải vượt bên trái; trường hợp khi xe phía trước có tín hiệu rẽ trái hoặc đang rẽ trái "
            "hoặc khi xe chuyên dùng đang làm việc trên đường mà không thể vượt bên trái thì được vượt về bên phải."
        ),
        "ground_truth_answer": (
            "Phải vượt bên trái; được vượt bên phải khi xe trước rẽ trái hoặc xe chuyên dùng đang làm việc không thể vượt trái theo Khoản 2 Điều 14 Luật 36/2024/QH15."
        ),
    },
    {
        "id": "Q018",
        "query": "Trong đô thị từ 22 giờ đến 05 giờ sáng hôm sau xe xin vượt được báo hiệu bằng phương tiện gì?",
        "category": "Báo hiệu xin vượt ban đêm",
        "expected_doc_code": "36/2024/QH15",
        "expected_article_number": 14,
        "expected_clause_number": 5,
        "gold_hierarchy_paths": ["doc_36_2024_qh15.c_ii.a14.c5"],
        "gold_chunk_ids": ["e973ccba-e360-597d-9952-b0cd1da0df0d"],
        "gold_contextualized_text": (
            "[ĐIỀU 14]: Vượt xe và nhường đường cho xe xin vượt\n"
            "[KHOẢN 5]: trong đô thị và khu đông dân cư trong thời gian từ 22 giờ ngày hôm trước đến 05 giờ ngày hôm sau chỉ được báo hiệu xin vượt bằng đèn."
        ),
        "ground_truth_answer": (
            "Chỉ được báo hiệu xin vượt bằng đèn chiếu sáng, không được dùng còi theo Khoản 5 Điều 14 Luật 36/2024/QH15."
        ),
    },
    {
        "id": "Q019",
        "query": "Những vị trí và trường hợp nào bị cấm quay đầu xe?",
        "category": "Cấm quay đầu xe",
        "expected_doc_code": "36/2024/QH15",
        "expected_article_number": 15,
        "expected_clause_number": 4,
        "gold_hierarchy_paths": ["doc_36_2024_qh15.c_ii.a15.c4"],
        "gold_chunk_ids": ["de53d556-3d8b-5bb0-b9d0-e5bfcb32f5c1"],
        "gold_contextualized_text": (
            "[ĐIỀU 15]: Chuyển hướng xe\n"
            "[KHOẢN 4]: 4. Không được quay đầu xe ở phần đường dành cho người đi bộ qua đường, trên cầu, đầu cầu, gầm cầu vượt, ngầm, "
            "tại nơi đường bộ giao nhau cùng mức với đường sắt, đường hẹp, đường dốc, đoạn đường cong tầm nhìn bị che khuất, trên đường cao tốc, trong hầm đường bộ..."
        ),
        "ground_truth_answer": (
            "Cấm quay đầu trên cầu, đầu cầu, gầm cầu vượt, trong hầm, đường cao tốc, đường dốc theo Khoản 4 Điều 15 Luật 36/2024/QH15."
        ),
    },
    {
        "id": "Q020",
        "query": "Quy định cấm lùi xe trên đường cao tốc, trong hầm và đường một chiều thế nào?",
        "category": "Cấm lùi xe",
        "expected_doc_code": "36/2024/QH15",
        "expected_article_number": 16,
        "expected_clause_number": 2,
        "gold_hierarchy_paths": ["doc_36_2024_qh15.c_ii.a16.c2"],
        "gold_chunk_ids": ["b1dc76fd-0650-5c1c-8931-1ededb7ce59a"],
        "gold_contextualized_text": (
            "[ĐIỀU 16]: Lùi xe\n"
            "[KHOẢN 2]: 2. Không được lùi xe ở đường một chiều, khu vực cấm dừng, trên phần đường dành cho người đi bộ qua đường, "
            "nơi đường bộ giao nhau, giao nhau cùng mức với đường sắt, nơi tầm nhìn bị che khuất, trong hầm đường bộ, trên đường cao tốc."
        ),
        "ground_truth_answer": (
            "Cấm lùi xe ở đường một chiều, trong hầm đường bộ, trên đường cao tốc theo Khoản 2 Điều 16 Luật 36/2024/QH15."
        ),
    },
    {
        "id": "Q021",
        "query": "Khi hai xe tránh nhau trên đường dốc hẹp thì xe nào phải nhường đường?",
        "category": "Tránh xe trên đường dốc",
        "expected_doc_code": "36/2024/QH15",
        "expected_article_number": 17,
        "expected_clause_number": 2,
        "gold_hierarchy_paths": ["doc_36_2024_qh15.c_ii.a17.c2.p_b"],
        "gold_chunk_ids": ["97ed3b47-f3b0-5ef9-8c5c-5d446702f93f"],
        "gold_contextualized_text": (
            "[ĐIỀU 17]: Tránh xe đi ngược chiều\n"
            "[KHOẢN 2]: b) Xe xuống dốc phải nhường đường cho xe lên dốc;"
        ),
        "ground_truth_answer": (
            "Xe xuống dốc phải nhường đường cho xe lên dốc theo Điểm b Khoản 2 Điều 17 Luật 36/2024/QH15."
        ),
    },
    {
        "id": "Q022",
        "query": "Khi đỗ xe trên đường phố, bánh xe gần nhất cách mép vỉa hè tối đa bao nhiêu mét?",
        "category": "Dừng xe đỗ xe trên đường phố",
        "expected_doc_code": "36/2024/QH15",
        "expected_article_number": 18,
        "expected_clause_number": 6,
        "gold_hierarchy_paths": ["doc_36_2024_qh15.c_ii.a18.c6"],
        "gold_chunk_ids": ["82f1cfd2-b8db-5389-b36d-b168f7302184"],
        "gold_contextualized_text": (
            "[ĐIỀU 18]: Dừng xe, đỗ xe\n"
            "[KHOẢN 6]: 6. Trên đường phố... bánh xe gần nhất không được cách xa lề đường, vỉa hè quá 0,25 mét và không gây cản trở, nguy hiểm..."
        ),
        "ground_truth_answer": (
            "Bánh xe gần nhất không được cách xa lề đường, vỉa hè quá 0,25 mét theo Khoản 6 Điều 18 Luật 36/2024/QH15."
        ),
    },
    {
        "id": "Q023",
        "query": "Khoảng cách cấm dừng xe, đỗ xe trước cổng trụ sở cơ quan, tổ chức là bao nhiêu mét?",
        "category": "Cấm dừng đỗ trước cổng cơ quan",
        "expected_doc_code": "36/2024/QH15",
        "expected_article_number": 18,
        "expected_clause_number": 4,
        "gold_hierarchy_paths": ["doc_36_2024_qh15.c_ii.a18.c4.p_k"],
        "gold_chunk_ids": ["e855c1eb-75a1-5344-8b1b-d91e0fc0928d"],
        "gold_contextualized_text": (
            "[ĐIỀU 18]: Dừng xe, đỗ xe\n"
            "[KHOẢN 4]: k) Trước cổng và trong phạm vi 05 mét hai bên cổng trụ sở cơ quan, tổ chức có bố trí đường cho xe ra, vào;"
        ),
        "ground_truth_answer": (
            "Cấm dừng, đỗ trước cổng và trong phạm vi 05 mét hai bên cổng trụ sở có đường xe ra vào theo Điểm k Khoản 4 Điều 18 Luật 36/2024/QH15."
        ),
    },
    {
        "id": "Q024",
        "query": "Khung giờ bắt buộc bật đèn chiếu sáng phía trước khi lái xe tham gia giao thông là từ mấy giờ?",
        "category": "Sử dụng đèn chiếu sáng",
        "expected_doc_code": "36/2024/QH15",
        "expected_article_number": 20,
        "expected_clause_number": 1,
        "gold_hierarchy_paths": ["doc_36_2024_qh15.c_ii.a20.c1"],
        "gold_chunk_ids": ["65ae47fe-51b1-5a90-8e39-5b7ef99293b3"],
        "gold_contextualized_text": (
            "[ĐIỀU 20]: Sử dụng đèn\n"
            "[KHOẢN 1]: 1. Người lái xe, người điều khiển xe máy chuyên dùng tham gia giao thông đường bộ phải bật đèn chiếu sáng phía trước "
            "trong thời gian từ 18 giờ ngày hôm trước đến 06 giờ ngày hôm sau hoặc khi có sương mù, thời tiết xấu..."
        ),
        "ground_truth_answer": (
            "Bắt buộc bật đèn chiếu sáng từ 18 giờ ngày hôm trước đến 06 giờ ngày hôm sau theo Khoản 1 Điều 20 Luật 36/2024/QH15."
        ),
    },
    {
        "id": "Q025",
        "query": "Khi đi trong khu đông dân cư có hệ thống chiếu sáng hoạt động có được bật đèn pha chiếu xa không?",
        "category": "Sử dụng đèn chiếu xa trong đô thị",
        "expected_doc_code": "36/2024/QH15",
        "expected_article_number": 20,
        "expected_clause_number": 2,
        "gold_hierarchy_paths": ["doc_36_2024_qh15.c_ii.a20.c2.p_b"],
        "gold_chunk_ids": ["837a1792-f45a-5a7d-88e2-c36f2ae1194a"],
        "gold_contextualized_text": (
            "[ĐIỀU 20]: Sử dụng đèn\n"
            "[KHOẢN 2]: b) Khi đi trên các đoạn đường qua khu đông dân cư có hệ thống chiếu sáng đang hoạt động phải tắt đèn chiếu xa, bật đèn chiếu gần;"
        ),
        "ground_truth_answer": (
            "Không được bật đèn chiếu xa, phải tắt đèn chiếu xa và bật đèn chiếu gần theo Điểm b Khoản 2 Điều 20 Luật 36/2024/QH15."
        ),
    },
    {
        "id": "Q026",
        "query": "Quy định về thời gian cấm sử dụng còi trong khu đông dân cư và gần bệnh viện?",
        "category": "Sử dụng còi",
        "expected_doc_code": "36/2024/QH15",
        "expected_article_number": 21,
        "expected_clause_number": 2,
        "gold_hierarchy_paths": ["doc_36_2024_qh15.c_ii.a21.c2"],
        "gold_chunk_ids": ["728479ed-346b-5b83-9023-17f812427c20"],
        "gold_contextualized_text": (
            "[ĐIỀU 21]: Sử dụng tín hiệu còi\n"
            "[KHOẢN 2]: 2. Không sử dụng còi liên tục; không sử dụng còi có âm lượng không đúng quy định; "
            "không sử dụng còi trong thời gian từ 22 giờ ngày hôm trước đến 05 giờ ngày hôm sau trong khu đông dân cư, bệnh viện, trừ xe ưu tiên."
        ),
        "ground_truth_answer": (
            "Cấm bấm còi từ 22 giờ hôm trước đến 05 giờ hôm sau trong khu dân cư, bệnh viện theo Khoản 2 Điều 21 Luật 36/2024/QH15."
        ),
    },
    {
        "id": "Q027",
        "query": "Tại nơi đường giao nhau không có báo hiệu đi theo vòng xuyến thì phải nhường đường cho xe nào?",
        "category": "Nhường đường tại nơi giao nhau",
        "expected_doc_code": "36/2024/QH15",
        "expected_article_number": 22,
        "expected_clause_number": 2,
        "gold_hierarchy_paths": ["doc_36_2024_qh15.c_ii.a22.c2"],
        "gold_chunk_ids": ["f1201a42-d54d-5dcf-9d7c-3a31107eb08d"],
        "gold_contextualized_text": (
            "[ĐIỀU 22]: Nhường đường tại nơi đường giao nhau\n"
            "[KHOẢN 2]: 2. Tại nơi đường giao nhau không có báo hiệu đi theo vòng xuyến, phải nhường đường cho xe đi đến từ bên phải;"
        ),
        "ground_truth_answer": (
            "Phải nhường đường cho xe đi đến từ bên phải theo Khoản 2 Điều 22 Luật 36/2024/QH15."
        ),
    },
    {
        "id": "Q028",
        "query": "Xe máy và người đi bộ có được đi vào đường cao tốc không?",
        "category": "Giao thông đường cao tốc",
        "expected_doc_code": "36/2024/QH15",
        "expected_article_number": 25,
        "expected_clause_number": 3,
        "gold_hierarchy_paths": ["doc_36_2024_qh15.c_ii.a25.c3"],
        "gold_chunk_ids": ["42093845-13db-5dfc-be62-3d1ca98ce18e"],
        "gold_contextualized_text": (
            "[ĐIỀU 25]: Giao thông trên đường cao tốc\n"
            "[KHOẢN 3]: 3. Xe mô tô, xe gắn máy, xe thô sơ, người đi bộ không được đi trên đường cao tốc, "
            "trừ người, phương tiện và thiết bị phục vụ việc quản lý, bảo trì đường cao tốc."
        ),
        "ground_truth_answer": (
            "Xe mô tô, xe gắn máy, xe thô sơ và người đi bộ không được đi trên đường cao tốc theo Khoản 3 Điều 25 Luật 36/2024/QH15."
        ),
    },
    {
        "id": "Q029",
        "query": "Khi chạy xe trong hầm đường bộ người điều khiển phương tiện có phải bật đèn chiếu gần không?",
        "category": "Giao thông trong hầm đường bộ",
        "expected_doc_code": "36/2024/QH15",
        "expected_article_number": 26,
        "expected_clause_number": 1,
        "gold_hierarchy_paths": ["doc_36_2024_qh15.c_ii.a26.c1"],
        "gold_chunk_ids": ["2c7de48f-2157-504f-95c0-5d9adb3750b1"],
        "gold_contextualized_text": (
            "[ĐIỀU 26]: Giao thông trong hầm đường bộ\n"
            "[KHOẢN 1]: 1. Xe cơ giới, xe máy chuyên dùng phải bật đèn chiếu gần; xe thô sơ phải bật đèn hoặc có vật phát sáng báo hiệu;"
        ),
        "ground_truth_answer": (
            "Bắt buộc bật đèn chiếu gần trong hầm đường bộ theo Khoản 1 Điều 26 Luật 36/2024/QH15."
        ),
    },
    {
        "id": "Q030",
        "query": "Thứ tự ưu tiên của các loại xe ưu tiên khi đi làm nhiệm vụ qua nơi đường giao nhau như thế nào?",
        "category": "Xe ưu tiên - Thứ tự quyền đi trước",
        "expected_doc_code": "36/2024/QH15",
        "expected_article_number": 27,
        "expected_clause_number": 2,
        "gold_hierarchy_paths": ["doc_36_2024_qh15.c_ii.a27.c2.p_a"],
        "gold_chunk_ids": ["81edb262-075a-5c06-810e-c930d4283e3f"],
        "gold_contextualized_text": (
            "[ĐIỀU 27]: Xe ưu tiên\n"
            "[KHOẢN 2]: 2. Thứ tự ưu tiên: a) Xe chữa cháy; b) Xe quân sự, công an, kiểm sát làm nhiệm vụ khẩn cấp, đoàn xe CSGT dẫn đường; "
            "c) Xe cứu thương cấp cứu; d) Xe hộ đê, cứu nạn, khắc phục thiên tai; đ) Đoàn xe tang."
        ),
        "ground_truth_answer": (
            "Thứ tự ưu tiên: Xe chữa cháy > Xe quân sự, công an, kiểm sát, CSGT dẫn đường > Xe cứu thương > Xe hộ đê/cứu nạn > Đoàn xe tang theo Khoản 2 Điều 27 Luật 36/2024/QH15."
        ),
    },
    {
        "id": "Q031",
        "query": "Người điều khiển xe mô tô hai bánh được chở tối đa 2 người trong những trường hợp nào?",
        "category": "Chở người trên xe mô tô",
        "expected_doc_code": "36/2024/QH15",
        "expected_article_number": 33,
        "expected_clause_number": 1,
        "gold_hierarchy_paths": ["doc_36_2024_qh15.c_ii.a33.c1.p_c"],
        "gold_chunk_ids": ["19077b2b-7081-52dc-995c-e24029e1c082"],
        "gold_contextualized_text": (
            "[ĐIỀU 33]: Người lái xe, người được chở trên xe mô tô, xe gắn máy\n"
            "[KHOẢN 1]: 1. Người lái xe mô tô chỉ được chở một người, trừ trường hợp: "
            "a) Chở người bệnh đi cấp cứu; b) Áp giải người vi phạm pháp luật; c) Trẻ em dưới 12 tuổi; d) Người già yếu hoặc người khuyết tật."
        ),
        "ground_truth_answer": (
            "Được chở 2 người khi chở bệnh nhân cấp cứu, áp giải tội phạm, chở trẻ em dưới 12 tuổi, hoặc chở người già yếu/người khuyết tật theo Khoản 1 Điều 33 Luật 36/2024/QH15."
        ),
    },
    {
        "id": "Q032",
        "query": "Người lái xe máy có được dùng ô che mưa hoặc sử dụng tai nghe khi đang lái xe không?",
        "category": "Cấm sử dụng ô, thiết bị âm thanh khi lái xe máy",
        "expected_doc_code": "36/2024/QH15",
        "expected_article_number": 33,
        "expected_clause_number": 3,
        "gold_hierarchy_paths": ["doc_36_2024_qh15.c_ii.a33.c3.p_c"],
        "gold_chunk_ids": ["515b0c30-05ee-557a-bb2f-45be9de79df9"],
        "gold_contextualized_text": (
            "[ĐIỀU 33]: Người lái xe, người được chở trên xe mô tô, xe gắn máy\n"
            "[KHOẢN 3]: c) Sử dụng ô, thiết bị âm thanh, trừ thiết bị trợ thính;"
        ),
        "ground_truth_answer": (
            "Cấm sử dụng ô và thiết bị âm thanh (trừ máy trợ thính) khi đang điều khiển xe mô tô, xe gắn máy theo Điểm c Khoản 3 Điều 33 Luật 36/2024/QH15."
        ),
    },

    # -------------------------------------------------------------------------
    # CHAPTER III: PHƯƠNG TIỆN GIAO THÔNG ĐƯỜNG BỘ (Điều 34 - Điều 55)
    # -------------------------------------------------------------------------
    {
        "id": "Q033",
        "query": "Xe gắn máy theo phân loại của Luật 36/2024 có vận tốc thiết kế và dung tích xi-lanh tối đa là bao nhiêu?",
        "category": "Phân loại phương tiện - Xe gắn máy",
        "expected_doc_code": "36/2024/QH15",
        "expected_article_number": 34,
        "expected_clause_number": 1,
        "gold_hierarchy_paths": ["doc_36_2024_qh15.c_iii.a34.c1.p_g"],
        "gold_chunk_ids": ["9c04b298-4f02-57bf-9325-f54d6ab6c134"],
        "gold_contextualized_text": (
            "[ĐIỀU 34]: Phân loại phương tiện giao thông đường bộ\n"
            "[KHOẢN 1]: g) Xe gắn máy là xe có hai hoặc ba bánh chạy bằng động cơ, có vận tốc thiết kế không lớn hơn 50 km/h; "
            "nếu động cơ nhiệt thì dung tích xi-lanh không lớn hơn 50 cm3; động cơ điện công suất không quá 04 kW."
        ),
        "ground_truth_answer": (
            "Vận tốc thiết kế không quá 50 km/h, dung tích động cơ nhiệt không quá 50 cm3 hoặc công suất động cơ điện không quá 4 kW theo Điểm g Khoản 1 Điều 34 Luật 36/2024/QH15."
        ),
    },
    {
        "id": "Q034",
        "query": "Xe mô tô và xe gắn máy tham gia giao thông có bắt buộc phải kiểm định khí thải không?",
        "category": "Đăng kiểm - Khí thải xe máy",
        "expected_doc_code": "36/2024/QH15",
        "expected_article_number": 42,
        "expected_clause_number": 2,
        "gold_hierarchy_paths": ["doc_36_2024_qh15.c_iii.a42.c2"],
        "gold_chunk_ids": ["b6dab24c-99c8-51fe-a184-fdb28f3d7908"],
        "gold_contextualized_text": (
            "[ĐIỀU 42]: Bảo đảm an toàn kỹ thuật và bảo vệ môi trường\n"
            "[KHOẢN 2]: 2. Việc kiểm định đối với xe mô tô, xe gắn máy chỉ thực hiện kiểm định khí thải. "
            "Việc kiểm định khí thải thực hiện theo quy định của pháp luật về bảo vệ môi trường..."
        ),
        "ground_truth_answer": (
            "Xe mô tô, xe gắn máy chỉ thực hiện kiểm định khí thải tại các cơ sở kiểm định đáp ứng quy chuẩn kỹ thuật theo Khoản 2 Điều 42 Luật 36/2024/QH15."
        ),
    },
    {
        "id": "Q035",
        "query": "Xe ô tô đưa đón học sinh mầm non và tiểu học có quy định niên hạn sử dụng và thiết bị cảnh báo bỏ quên thế nào?",
        "category": "Xe đưa đón học sinh",
        "expected_doc_code": "36/2024/QH15",
        "expected_article_number": 46,
        "expected_clause_number": 1,
        "gold_hierarchy_paths": ["doc_36_2024_qh15.c_iii.a46.c1.p_a"],
        "gold_chunk_ids": ["ffe1e698-c485-5ab3-95b3-f8506091273c"],
        "gold_contextualized_text": (
            "[ĐIỀU 46]: Bảo đảm an toàn đối với xe ô tô chở học sinh\n"
            "[KHOẢN 1]: a) Có thiết bị ghi nhận hình ảnh trẻ em, học sinh và thiết bị cảnh báo, chống bỏ quên trẻ em trên xe; "
            "niên hạn sử dụng không quá 20 năm; có màu sơn theo quy định của Chính phủ."
        ),
        "ground_truth_answer": (
            "Phải có thiết bị ghi hình và cảnh báo chống bỏ quên trẻ em, niên hạn sử dụng không quá 20 năm theo Điểm a Khoản 1 Điều 46 Luật 36/2024/QH15."
        ),
    },
    {
        "id": "Q036",
        "query": "Lái xe đưa đón học sinh phải có tối thiểu bao nhiêu năm kinh nghiệm lái xe vận tải hành khách?",
        "category": "Kinh nghiệm lái xe đưa đón học sinh",
        "expected_doc_code": "36/2024/QH15",
        "expected_article_number": 46,
        "expected_clause_number": 4,
        "gold_hierarchy_paths": ["doc_36_2024_qh15.c_iii.a46.c4"],
        "gold_chunk_ids": ["aae929f4-eb27-5136-acd7-1bfc1cefffc3"],
        "gold_contextualized_text": (
            "[ĐIỀU 46]: Bảo đảm an toàn đối với xe ô tô chở học sinh\n"
            "[KHOẢN 4]: 4. Người lái xe ô tô đưa đón trẻ em mầm non, học sinh phải có tối thiểu 02 năm kinh nghiệm lái xe vận tải hành khách."
        ),
        "ground_truth_answer": (
            "Phải có tối thiểu 02 năm kinh nghiệm lái xe vận tải hành khách theo Khoản 4 Điều 46 Luật 36/2024/QH15."
        ),
    },

    # -------------------------------------------------------------------------
    # CHAPTER IV: NGƯỜI ĐIỀU KHIỂN PHƯƠNG TIỆN & GPLX (Điều 56 - Điều 64)
    # -------------------------------------------------------------------------
    {
        "id": "Q037",
        "query": "Thời hạn sử dụng của giấy phép lái xe các hạng A1, A, B1 và hạng B theo Luật mới 2024?",
        "category": "Thời hạn GPLX",
        "expected_doc_code": "36/2024/QH15",
        "expected_article_number": 57,
        "expected_clause_number": 5,
        "gold_hierarchy_paths": ["doc_36_2024_qh15.c_iv.a57.c5.p_a", "doc_36_2024_qh15.c_iv.a57.c5.p_b"],
        "gold_chunk_ids": ["5530d96b-c903-5c19-8bd3-733c47f17558", "f06f8c2a-be47-57a0-bed2-c4f2e594a7b5"],
        "gold_contextualized_text": (
            "[ĐIỀU 57]: Giấy phép lái xe\n"
            "[KHOẢN 5]: a) Giấy phép lái xe các hạng A1, A, B1 không thời hạn; "
            "b) Giấy phép lái xe hạng B và hạng C1 có thời hạn 10 năm kể từ ngày cấp;"
        ),
        "ground_truth_answer": (
            "Hạng A1, A, B1 không thời hạn; Hạng B và C1 có thời hạn 10 năm theo Khoản 5 Điều 57 Luật 36/2024/QH15."
        ),
    },
    {
        "id": "Q038",
        "query": "Hệ thống điểm của giấy phép lái xe có bao nhiêu điểm và quy chế trừ điểm như thế nào?",
        "category": "Hệ thống 12 điểm GPLX",
        "expected_doc_code": "36/2024/QH15",
        "expected_article_number": 58,
        "expected_clause_number": 1,
        "gold_hierarchy_paths": ["doc_36_2024_qh15.c_iv.a58.c1"],
        "gold_chunk_ids": ["b985d7ba-2bc1-56d2-9ebf-b7d605e41dac"],
        "gold_contextualized_text": (
            "[ĐIỀU 58]: Điểm của giấy phép lái xe\n"
            "[KHOẢN 1]: 1. Điểm của giấy phép lái xe được dùng để quản lý việc chấp hành pháp luật... bao gồm 12 điểm. "
            "Số điểm trừ mỗi lần vi phạm tùy thuộc tính chất, mức độ vi phạm..."
        ),
        "ground_truth_answer": (
            "GPLX gồm 12 điểm, bị trừ điểm trên cơ sở dữ liệu khi có quyết định xử phạt vi phạm theo Khoản 1 Điều 58 Luật 36/2024/QH15."
        ),
    },
    {
        "id": "Q039",
        "query": "Giấy phép lái xe bị trừ điểm sau bao lâu không vi phạm thì được phục hồi đủ 12 điểm?",
        "category": "Phục hồi điểm GPLX",
        "expected_doc_code": "36/2024/QH15",
        "expected_article_number": 58,
        "expected_clause_number": 2,
        "gold_hierarchy_paths": ["doc_36_2024_qh15.c_iv.a58.c2"],
        "gold_chunk_ids": ["43aeecc6-c7c4-54c3-b135-ccce9ddc4737"],
        "gold_contextualized_text": (
            "[ĐIỀU 58]: Điểm của giấy phép lái xe\n"
            "[KHOẢN 2]: 2. Giấy phép lái xe chưa bị trừ hết điểm và không bị trừ điểm trong thời hạn 12 tháng từ ngày bị trừ điểm gần nhất thì được phục hồi đủ 12 điểm."
        ),
        "ground_truth_answer": (
            "Được phục hồi đủ 12 điểm nếu trong 12 tháng kể từ ngày bị trừ điểm gần nhất không bị trừ điểm tiếp theo Khoản 2 Điều 58 Luật 36/2024/QH15."
        ),
    },
    {
        "id": "Q040",
        "query": "Khi giấy phép lái xe bị trừ hết điểm thì tài xế phải làm gì để được phục hồi điểm?",
        "category": "Xử lý khi bị trừ hết 12 điểm GPLX",
        "expected_doc_code": "36/2024/QH15",
        "expected_article_number": 58,
        "expected_clause_number": 3,
        "gold_hierarchy_paths": ["doc_36_2024_qh15.c_iv.a58.c3"],
        "gold_chunk_ids": ["7aa131b6-a879-5f5b-a1f5-79030733068a"],
        "gold_contextualized_text": (
            "[ĐIỀU 58]: Điểm của giấy phép lái xe\n"
            "[KHOẢN 3]: 3. Trường hợp giấy phép lái xe bị trừ hết điểm thì người có giấy phép lái xe không được điều khiển phương tiện. "
            "Sau thời hạn ít nhất là 06 tháng kể từ ngày bị trừ hết điểm, được tham gia kiểm tra kiến thức pháp luật do CSGT tổ chức, đạt yêu cầu thì được phục hồi đủ 12 điểm."
        ),
        "ground_truth_answer": (
            "Không được lái xe; sau ít nhất 06 tháng phải tham gia kiểm tra lại kiến thức pháp luật TTATGT do CSGT tổ chức đạt kết quả để phục hồi 12 điểm theo Khoản 3 Điều 58 Luật 36/2024/QH15."
        ),
    },
    {
        "id": "Q041",
        "query": "Độ tuổi tối thiểu để được cấp giấy phép lái xe hạng A1, A, B và hạng C quy định là bao nhiêu tuổi?",
        "category": "Độ tuổi lái xe",
        "expected_doc_code": "36/2024/QH15",
        "expected_article_number": 59,
        "expected_clause_number": 1,
        "gold_hierarchy_paths": ["doc_36_2024_qh15.c_iv.a59.c1.p_b", "doc_36_2024_qh15.c_iv.a59.c1.p_c"],
        "gold_chunk_ids": ["01984004-1820-5798-8bcc-f3873d15250a", "a9f6e4fd-7986-5dc3-ac98-c3e0367be580"],
        "gold_contextualized_text": (
            "[ĐIỀU 59]: Tuổi, sức khỏe của người điều khiển phương tiện\n"
            "[KHOẢN 1]: b) Người đủ 18 tuổi trở lên được cấp GPLX hạng A1, A, B1, B, C1; "
            "c) Người đủ 21 tuổi trở lên được cấp GPLX hạng C, BE;"
        ),
        "ground_truth_answer": (
            "Đủ 18 tuổi đối với hạng A1, A, B1, B, C1; Đủ 21 tuổi đối với hạng C, BE theo Khoản 1 Điều 59 Luật 36/2024/QH15."
        ),
    },
    {
        "id": "Q042",
        "query": "Độ tuổi tối đa của người lái xe ô tô chở người trên 29 chỗ là bao nhiêu?",
        "category": "Tuổi tối đa lái xe khách trên 29 chỗ",
        "expected_doc_code": "36/2024/QH15",
        "expected_article_number": 59,
        "expected_clause_number": 1,
        "gold_hierarchy_paths": ["doc_36_2024_qh15.c_iv.a59.c1.p_e"],
        "gold_chunk_ids": ["77b2d147-d526-5b38-8e0c-716c225c8b5d"],
        "gold_contextualized_text": (
            "[ĐIỀU 59]: Tuổi, sức khỏe của người điều khiển phương tiện\n"
            "[KHOẢN 1]: e) Tuổi tối đa của người lái xe ô tô chở người (kể cả xe buýt) trên 29 chỗ, xe giường nằm "
            "là đủ 57 tuổi đối với nam, đủ 55 tuổi đối với nữ."
        ),
        "ground_truth_answer": (
            "Đủ 57 tuổi đối với nam và đủ 55 tuổi đối với nữ theo Điểm e Khoản 1 Điều 59 Luật 36/2024/QH15."
        ),
    },

    # -------------------------------------------------------------------------
    # CHAPTER V: TUẦN TRA, KIỂM SOÁT VÀ XỬ LÝ VI PHẠM (Điều 65 - Điều 77)
    # -------------------------------------------------------------------------
    {
        "id": "Q043",
        "query": "Cảnh sát giao thông được dừng phương tiện tham gia giao thông trong 4 trường hợp nào?",
        "category": "Căn cứ dừng phương tiện của CSGT",
        "expected_doc_code": "36/2024/QH15",
        "expected_article_number": 66,
        "expected_clause_number": 1,
        "gold_hierarchy_paths": ["doc_36_2024_qh15.c_v.a66.c1"],
        "gold_chunk_ids": ["7ea64511-1337-51d0-8c41-f2e229634f87"],
        "gold_contextualized_text": (
            "[ĐIỀU 66]: Căn cứ dừng phương tiện tham gia giao thông đường bộ để kiểm soát\n"
            "[KHOẢN 1]: 1. Khi phát hiện hành vi vi phạm pháp luật hoặc có căn cứ xác định có hành vi vi phạm pháp luật...; "
            "2. Thực hiện theo mệnh lệnh, kế hoạch tuần tra kiểm soát...; 3. Phục vụ an ninh trật tự, cứu nạn, dịch bệnh; 4. Có tin báo, tố giác..."
        ),
        "ground_truth_answer": (
            "CSGT dừng phương tiện theo 4 căn cứ tại Điều 66 Luật 36/2024/QH15 (Phát hiện vi phạm, theo mệnh lệnh kế hoạch, phục vụ an ninh cứu hộ, có tin báo tố giác)."
        ),
    },

    # -------------------------------------------------------------------------
    # CHAPTER IX: HIỆU LỰC & QUY ĐỊNH CHUYỂN TIẾP GPLX (Điều 88 - Điều 89)
    # -------------------------------------------------------------------------
    {
        "id": "Q044",
        "query": "Giấy phép lái xe hạng A1 cấp trước ngày Luật 36/2024 có hiệu lực được tiếp tục điều khiển xe máy đến dung tích bao nhiêu?",
        "category": "Chuyển tiếp GPLX hạng A1",
        "expected_doc_code": "36/2024/QH15",
        "expected_article_number": 89,
        "expected_clause_number": 2,
        "gold_hierarchy_paths": ["doc_36_2024_qh15.c_ix.a89.c2.p_a"],
        "gold_chunk_ids": ["2ecc907a-c411-59fb-b577-67cbd8a4095e"],
        "gold_contextualized_text": (
            "[ĐIỀU 89]: Quy định chuyển tiếp\n"
            "[KHOẢN 2]: a) Giấy phép lái xe hạng A1 được tiếp tục điều khiển xe mô tô hai bánh có dung tích xi-lanh từ 50 cm3 đến dưới 175 cm3 "
            "hoặc có công suất động cơ điện từ 04 kW đến dưới 14 kW;"
        ),
        "ground_truth_answer": (
            "Được tiếp tục điều khiển mô tô từ 50 cm3 đến dưới 175 cm3 hoặc công suất điện từ 4 kW đến dưới 14 kW theo Điểm a Khoản 2 Điều 89 Luật 36/2024/QH15."
        ),
    },
    {
        "id": "Q045",
        "query": "Giấy phép lái xe hạng B2 cấp theo luật cũ khi đổi sang luật mới 2024 được chuyển thành hạng bằng nào?",
        "category": "Quy đổi GPLX hạng B2 cũ",
        "expected_doc_code": "36/2024/QH15",
        "expected_article_number": 89,
        "expected_clause_number": 3,
        "gold_hierarchy_paths": ["doc_36_2024_qh15.c_ix.a89.c3.p_e"],
        "gold_chunk_ids": ["540734f5-7d86-5d32-a784-d6b0d886aa86"],
        "gold_contextualized_text": (
            "[ĐIỀU 89]: Quy định chuyển tiếp\n"
            "[KHOẢN 3]: e) Giấy phép lái xe hạng B1, B2 được đổi, cấp lại sang giấy phép lái xe hạng B hoặc hạng C1 "
            "và chứng chỉ điều khiển xe máy chuyên dùng cho người điều khiển máy kéo có trọng tải đến 3.500 kg;"
        ),
        "ground_truth_answer": (
            "GPLX hạng B2 được đổi sang hạng B hoặc hạng C1 theo Điểm e Khoản 3 Điều 89 Luật 36/2024/QH15."
        ),
    },
]

# Alias for backward compatibility across test runners
BENCHMARK_GOLD_QUERIES = LAW36_STATUTORY_BENCHMARK
