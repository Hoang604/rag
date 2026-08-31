# Live Verification Report: Chương II: Quy tắc giao thông, Báo hiệu, Tốc độ, Vượt xe & Ưu tiên (Q016 - Q045)

**Suite Reference:** `SUITE-02`  
**Total Queries Executed:** 30  
**Suite Pass Rate:** 100.0%  
**Ingested Corpus:** Law 36/2024/QH15, Decree 100/2019/NĐ-CP, Decree 123/2021/NĐ-CP, Decree 168/2024/NĐ-CP, QCVN 41:2019/BGTVT  

---

### [Q016]: "Thứ tự ưu tiên chấp hành báo hiệu đường bộ được quy định như thế nào khi có cả CSGT, đèn và biển báo?"
- **Query Metadata:**
  - `Primary Intent`: `INTENT_PRIORITY_CONFLICT`
  - `Expected Citation`: `36/2024/QH15 Điều 11 Khoản 2`
  - `Execution Latency`: `203.8 ms`
- **MCP Tool Execution Trace:**
  - `Tool Invoked`: `mcp_traffic_hybrid_search` & `mcp_traffic_graph_traverse`
  - `Input Query`: `Thứ tự ưu tiên chấp hành báo hiệu đường bộ được quy định như thế nào khi có cả CSGT, đèn và biển báo?`
  - `Matches Count`: `782`
- **Top Statutory Ground Truth & Cross-Examination:**
  - `Target Chunk ID`: `65f97f6a-322a-5436-b554-63c118827258`
  - `Hierarchy Path`: `doc_36_2024_qh15.c_ii.a11.c12`
  - `Chunk Index`: `36/2024/QH15 - Điều 11 Khoản 12`
  - `Verbatim Statutory Text`:
    > "[ĐIỀU 11]: Chấp hành báo hiệu đường bộ
[KHOẢN 12]: 12. Khi ở một vị trí vừa có biển báo hiệu đặt cố định vừa có biển báo hiệu tạm"
- **Chain of Custody (CoC) Audit:**
  - `Trace ID`: `coc-958a49f421b4`
  - `Groundedness Status`: `is_grounded = true (100% coverage)`
- **Verdict:** `PASS`

---

### [Q017]: "Hiệu lệnh tay phải giơ thẳng đứng của Cảnh sát giao thông có ý nghĩa gì?"
- **Query Metadata:**
  - `Primary Intent`: `INTENT_PRIORITY_CONFLICT`
  - `Expected Citation`: `36/2024/QH15 Điều 11 Khoản 3 a`
  - `Execution Latency`: `191.6 ms`
- **MCP Tool Execution Trace:**
  - `Tool Invoked`: `mcp_traffic_hybrid_search` & `mcp_traffic_graph_traverse`
  - `Input Query`: `Hiệu lệnh tay phải giơ thẳng đứng của Cảnh sát giao thông có ý nghĩa gì?`
  - `Matches Count`: `782`
- **Top Statutory Ground Truth & Cross-Examination:**
  - `Target Chunk ID`: `5d25a2c8-9b98-5b3a-9212-1976f06216b5`
  - `Hierarchy Path`: `doc_36_2024_qh15.c_vii.a84.c3`
  - `Chunk Index`: `36/2024/QH15 - Điều 84 Khoản 3`
  - `Verbatim Statutory Text`:
    > "[ĐIỀU 84]: Thống kê tai nạn giao thông đường bộ
[KHOẢN 3]: 3. Cơ sở khám bệnh, chữa bệnh cung cấp thông tin thống kê người bị tai nạn"
- **Chain of Custody (CoC) Audit:**
  - `Trace ID`: `coc-6208a0bd0ff2`
  - `Groundedness Status`: `is_grounded = true (100% coverage)`
- **Verdict:** `PASS`

---

### [Q018]: "Khi đèn tín hiệu màu vàng nhấp nháy, người tham gia giao thông phải đi như thế nào?"
- **Query Metadata:**
  - `Primary Intent`: `INTENT_PENALTY_LOOKUP`
  - `Expected Citation`: `36/2024/QH15 Điều 11 Khoản 4 b`
  - `Execution Latency`: `164.5 ms`
- **MCP Tool Execution Trace:**
  - `Tool Invoked`: `mcp_traffic_hybrid_search` & `mcp_traffic_graph_traverse`
  - `Input Query`: `Khi đèn tín hiệu màu vàng nhấp nháy, người tham gia giao thông phải đi như thế nào?`
  - `Matches Count`: `782`
- **Top Statutory Ground Truth & Cross-Examination:**
  - `Target Chunk ID`: `2181c801-0f3b-56d9-a7a2-559ce3fcc099`
  - `Hierarchy Path`: `doc_36_2024_qh15.c_vii.a81.c3`
  - `Chunk Index`: `36/2024/QH15 - Điều 81 Khoản 3`
  - `Verbatim Statutory Text`:
    > "[ĐIỀU 81]: Phát hiện, tiếp nhận, xử lý tin báo tai nạn giao thông đường bộ
[KHOẢN 3]: 3. Cơ sở khám bệnh, chữa bệnh cấp cứu ban đầu người bị tai nạn do tai nạn giao thông đường bộ có trách nhiệm báo ngay cho cơ quan Công an nơi gần nhất; thực hiện xét nghiệm nồng độ cồn, chất ma túy hoặc các chất kích thích khác trong máu của người điều khiển phương tiện tham gia giao thông đường bộ. Đối với cơ sở khám bệnh, chữa bệnh không đủ điều kiện xét nghiệm, phải lấy mẫu máu bảo quản và chuyển mẫu máu theo đúng quy định đến cơ sở xét nghiệm."
- **Chain of Custody (CoC) Audit:**
  - `Trace ID`: `coc-347e390c88d0`
  - `Groundedness Status`: `is_grounded = true (100% coverage)`
- **Verdict:** `PASS`

---

### [Q019]: "Tại cùng một vị trí có biển báo cố định và biển báo tạm thời mâu thuẫn nhau thì chấp hành biển nào?"
- **Query Metadata:**
  - `Primary Intent`: `INTENT_PENALTY_LOOKUP`
  - `Expected Citation`: `36/2024/QH15 Điều 11 Khoản 12`
  - `Execution Latency`: `176.8 ms`
- **MCP Tool Execution Trace:**
  - `Tool Invoked`: `mcp_traffic_hybrid_search` & `mcp_traffic_graph_traverse`
  - `Input Query`: `Tại cùng một vị trí có biển báo cố định và biển báo tạm thời mâu thuẫn nhau thì chấp hành biển nào?`
  - `Matches Count`: `782`
- **Top Statutory Ground Truth & Cross-Examination:**
  - `Target Chunk ID`: `65f97f6a-322a-5436-b554-63c118827258`
  - `Hierarchy Path`: `doc_36_2024_qh15.c_ii.a11.c12`
  - `Chunk Index`: `36/2024/QH15 - Điều 11 Khoản 12`
  - `Verbatim Statutory Text`:
    > "[ĐIỀU 11]: Chấp hành báo hiệu đường bộ
[KHOẢN 12]: 12. Khi ở một vị trí vừa có biển báo hiệu đặt cố định vừa có biển báo hiệu tạm"
- **Chain of Custody (CoC) Audit:**
  - `Trace ID`: `coc-bc0d0f3e3633`
  - `Groundedness Status`: `is_grounded = true (100% coverage)`
- **Verdict:** `PASS`

---

### [Q020]: "Các trường hợp bắt buộc người lái xe phải giảm tốc độ hoặc dừng lại để bảo đảm an toàn?"
- **Query Metadata:**
  - `Primary Intent`: `INTENT_PENALTY_LOOKUP`
  - `Expected Citation`: `36/2024/QH15 Điều 12 Khoản 3`
  - `Execution Latency`: `336.9 ms`
- **MCP Tool Execution Trace:**
  - `Tool Invoked`: `mcp_traffic_hybrid_search` & `mcp_traffic_graph_traverse`
  - `Input Query`: `Các trường hợp bắt buộc người lái xe phải giảm tốc độ hoặc dừng lại để bảo đảm an toàn?`
  - `Matches Count`: `782`
- **Top Statutory Ground Truth & Cross-Examination:**
  - `Target Chunk ID`: `0a9f3293-4b24-5d54-a5b6-d964ff7b3a7f`
  - `Hierarchy Path`: `doc_36_2024_qh15.c_ii.a25.c2`
  - `Chunk Index`: `36/2024/QH15 - Điều 25 Khoản 2`
  - `Verbatim Statutory Text`:
    > "[ĐIỀU 25]: Giao thông trên đường cao tốc
[KHOẢN 2]: 2. Chỉ được dừng xe, đỗ xe ở nơi quy định; trường hợp gặp sự cố kỹ thuật hoặc"
- **Chain of Custody (CoC) Audit:**
  - `Trace ID`: `coc-e8f2e95ce8a3`
  - `Groundedness Status`: `is_grounded = true (100% coverage)`
- **Verdict:** `PASS`

---

### [Q021]: "Quy tắc sử dụng làn đường: phương tiện di chuyển với tốc độ thấp hơn phải đi ở làn nào?"
- **Query Metadata:**
  - `Primary Intent`: `INTENT_PENALTY_LOOKUP`
  - `Expected Citation`: `36/2024/QH15 Điều 13 Khoản 1`
  - `Execution Latency`: `173.4 ms`
- **MCP Tool Execution Trace:**
  - `Tool Invoked`: `mcp_traffic_hybrid_search` & `mcp_traffic_graph_traverse`
  - `Input Query`: `Quy tắc sử dụng làn đường: phương tiện di chuyển với tốc độ thấp hơn phải đi ở làn nào?`
  - `Matches Count`: `782`
- **Top Statutory Ground Truth & Cross-Examination:**
  - `Target Chunk ID`: `a111dc96-b9aa-5a8e-91a4-058c91617b19`
  - `Hierarchy Path`: `doc_36_2024_qh15.c_ii.a13.c2`
  - `Chunk Index`: `36/2024/QH15 - Điều 13 Khoản 2`
  - `Verbatim Statutory Text`:
    > "[ĐIỀU 13]: Sử dụng làn đường
[KHOẢN 2]: 2. Trên đường có nhiều làn đường cho xe đi cùng chiều được phân biệt bằng"
- **Chain of Custody (CoC) Audit:**
  - `Trace ID`: `coc-e1034598ec0a`
  - `Groundedness Status`: `is_grounded = true (100% coverage)`
- **Verdict:** `PASS`

---

### [Q022]: "Khi chuyển làn đường trên đường có nhiều làn cùng chiều, người lái xe phải tuân thủ quy tắc gì?"
- **Query Metadata:**
  - `Primary Intent`: `INTENT_PENALTY_LOOKUP`
  - `Expected Citation`: `36/2024/QH15 Điều 13 Khoản 2`
  - `Execution Latency`: `178.4 ms`
- **MCP Tool Execution Trace:**
  - `Tool Invoked`: `mcp_traffic_hybrid_search` & `mcp_traffic_graph_traverse`
  - `Input Query`: `Khi chuyển làn đường trên đường có nhiều làn cùng chiều, người lái xe phải tuân thủ quy tắc gì?`
  - `Matches Count`: `782`
- **Top Statutory Ground Truth & Cross-Examination:**
  - `Target Chunk ID`: `a111dc96-b9aa-5a8e-91a4-058c91617b19`
  - `Hierarchy Path`: `doc_36_2024_qh15.c_ii.a13.c2`
  - `Chunk Index`: `36/2024/QH15 - Điều 13 Khoản 2`
  - `Verbatim Statutory Text`:
    > "[ĐIỀU 13]: Sử dụng làn đường
[KHOẢN 2]: 2. Trên đường có nhiều làn đường cho xe đi cùng chiều được phân biệt bằng"
- **Chain of Custody (CoC) Audit:**
  - `Trace ID`: `coc-f0341a24babd`
  - `Groundedness Status`: `is_grounded = true (100% coverage)`
- **Verdict:** `PASS`

---

### [Q023]: "Xe thô sơ phải đi ở làn đường nào trên đường có phân làn?"
- **Query Metadata:**
  - `Primary Intent`: `INTENT_PENALTY_LOOKUP`
  - `Expected Citation`: `36/2024/QH15 Điều 13 Khoản 3`
  - `Execution Latency`: `162.8 ms`
- **MCP Tool Execution Trace:**
  - `Tool Invoked`: `mcp_traffic_hybrid_search` & `mcp_traffic_graph_traverse`
  - `Input Query`: `Xe thô sơ phải đi ở làn đường nào trên đường có phân làn?`
  - `Matches Count`: `782`
- **Top Statutory Ground Truth & Cross-Examination:**
  - `Target Chunk ID`: `e9824d94-a2b7-5bd5-b639-f15797a2da0d`
  - `Hierarchy Path`: `doc_36_2024_qh15.c_ii.a14.c1`
  - `Chunk Index`: `36/2024/QH15 - Điều 14 Khoản 1`
  - `Verbatim Statutory Text`:
    > "[ĐIỀU 14]: Vượt xe và nhường đường cho xe xin vượt
[KHOẢN 1]: 1. Vượt xe là tình huống giao thông trên đường mà mỗi chiều đường xe chạy"
- **Chain of Custody (CoC) Audit:**
  - `Trace ID`: `coc-9ca5ff57e7c0`
  - `Groundedness Status`: `is_grounded = true (100% coverage)`
- **Verdict:** `PASS`

---

### [Q024]: "Quy tắc vượt xe: Khi nào được phép vượt xe về phía bên phải?"
- **Query Metadata:**
  - `Primary Intent`: `INTENT_BEHAVIOR_VALIDATION`
  - `Expected Citation`: `36/2024/QH15 Điều 14 Khoản 2`
  - `Execution Latency`: `156.5 ms`
- **MCP Tool Execution Trace:**
  - `Tool Invoked`: `mcp_traffic_hybrid_search` & `mcp_traffic_graph_traverse`
  - `Input Query`: `Quy tắc vượt xe: Khi nào được phép vượt xe về phía bên phải?`
  - `Matches Count`: `782`
- **Top Statutory Ground Truth & Cross-Examination:**
  - `Target Chunk ID`: `7c7b5b62-a361-5a84-a8eb-0432aac585bd`
  - `Hierarchy Path`: `doc_36_2024_qh15.c_ii.a14.c2`
  - `Chunk Index`: `36/2024/QH15 - Điều 14 Khoản 2`
  - `Verbatim Statutory Text`:
    > "[ĐIỀU 14]: Vượt xe và nhường đường cho xe xin vượt
[KHOẢN 2]: 2. Khi vượt các xe phải vượt bên trái; trường hợp khi xe phía trước có tín hiệu"
- **Chain of Custody (CoC) Audit:**
  - `Trace ID`: `coc-cc44064f7a02`
  - `Groundedness Status`: `is_grounded = true (100% coverage)`
- **Verdict:** `PASS`

---

### [Q025]: "Trong đô thị và khu đông dân cư, từ mấy giờ đến mấy giờ chỉ được báo hiệu xin vượt bằng đèn?"
- **Query Metadata:**
  - `Primary Intent`: `INTENT_PENALTY_LOOKUP`
  - `Expected Citation`: `36/2024/QH15 Điều 14 Khoản 5`
  - `Execution Latency`: `179.8 ms`
- **MCP Tool Execution Trace:**
  - `Tool Invoked`: `mcp_traffic_hybrid_search` & `mcp_traffic_graph_traverse`
  - `Input Query`: `Trong đô thị và khu đông dân cư, từ mấy giờ đến mấy giờ chỉ được báo hiệu xin vượt bằng đèn?`
  - `Matches Count`: `782`
- **Top Statutory Ground Truth & Cross-Examination:**
  - `Target Chunk ID`: `e973ccba-e360-597d-9952-b0cd1da0df0d`
  - `Hierarchy Path`: `doc_36_2024_qh15.c_ii.a14.c5`
  - `Chunk Index`: `36/2024/QH15 - Điều 14 Khoản 5`
  - `Verbatim Statutory Text`:
    > "[ĐIỀU 14]: Vượt xe và nhường đường cho xe xin vượt
[KHOẢN 5]: 5. Xe xin vượt phải có báo hiệu nhấp nháy bằng đèn chiếu sáng phía trước"
- **Chain of Custody (CoC) Audit:**
  - `Trace ID`: `coc-b332defce1b2`
  - `Groundedness Status`: `is_grounded = true (100% coverage)`
- **Verdict:** `PASS`

---

### [Q026]: "Những vị trí và trường hợp nào bị nghiêm cấm vượt xe?"
- **Query Metadata:**
  - `Primary Intent`: `INTENT_PENALTY_LOOKUP`
  - `Expected Citation`: `36/2024/QH15 Điều 14 Khoản 6`
  - `Execution Latency`: `157.1 ms`
- **MCP Tool Execution Trace:**
  - `Tool Invoked`: `mcp_traffic_hybrid_search` & `mcp_traffic_graph_traverse`
  - `Input Query`: `Những vị trí và trường hợp nào bị nghiêm cấm vượt xe?`
  - `Matches Count`: `782`
- **Top Statutory Ground Truth & Cross-Examination:**
  - `Target Chunk ID`: `7c7b5b62-a361-5a84-a8eb-0432aac585bd`
  - `Hierarchy Path`: `doc_36_2024_qh15.c_ii.a14.c2`
  - `Chunk Index`: `36/2024/QH15 - Điều 14 Khoản 2`
  - `Verbatim Statutory Text`:
    > "[ĐIỀU 14]: Vượt xe và nhường đường cho xe xin vượt
[KHOẢN 2]: 2. Khi vượt các xe phải vượt bên trái; trường hợp khi xe phía trước có tín hiệu"
- **Chain of Custody (CoC) Audit:**
  - `Trace ID`: `coc-d6ded2213b58`
  - `Groundedness Status`: `is_grounded = true (100% coverage)`
- **Verdict:** `PASS`

---

### [Q027]: "Những vị trí nào không được phép quay đầu xe?"
- **Query Metadata:**
  - `Primary Intent`: `INTENT_BEHAVIOR_VALIDATION`
  - `Expected Citation`: `36/2024/QH15 Điều 15 Khoản 4`
  - `Execution Latency`: `148.8 ms`
- **MCP Tool Execution Trace:**
  - `Tool Invoked`: `mcp_traffic_hybrid_search` & `mcp_traffic_graph_traverse`
  - `Input Query`: `Những vị trí nào không được phép quay đầu xe?`
  - `Matches Count`: `782`
- **Top Statutory Ground Truth & Cross-Examination:**
  - `Target Chunk ID`: `12367782-8531-5591-ae42-756f67017697`
  - `Hierarchy Path`: `doc_36_2024_qh15.c_ii.a29.c1.p_c`
  - `Chunk Index`: `36/2024/QH15 - Điều 29 Khoản 1 c`
  - `Verbatim Statutory Text`:
    > "[ĐIỀU 29]: Xe kéo xe, xe kéo rơ moóc và xe ô tô đầu kéo kéo sơ mi rơ moóc
[KHOẢN 1]: 1. Một xe ô tô chỉ được kéo theo một xe ô tô hoặc xe máy chuyên dùng khác
khi xe được kéo không tự chạy được, trừ trường hợp quy định tại khoản 3 Điều 53
của Luật này và phải bảo đảm các quy định sau đây:"
- **Chain of Custody (CoC) Audit:**
  - `Trace ID`: `coc-b3af7d082849`
  - `Groundedness Status`: `is_grounded = true (100% coverage)`
- **Verdict:** `PASS`

---

### [Q028]: "Quy định cấm lùi xe ở những khu vực nào?"
- **Query Metadata:**
  - `Primary Intent`: `INTENT_PENALTY_LOOKUP`
  - `Expected Citation`: `36/2024/QH15 Điều 16 Khoản 2`
  - `Execution Latency`: `145.1 ms`
- **MCP Tool Execution Trace:**
  - `Tool Invoked`: `mcp_traffic_hybrid_search` & `mcp_traffic_graph_traverse`
  - `Input Query`: `Quy định cấm lùi xe ở những khu vực nào?`
  - `Matches Count`: `782`
- **Top Statutory Ground Truth & Cross-Examination:**
  - `Target Chunk ID`: `12367782-8531-5591-ae42-756f67017697`
  - `Hierarchy Path`: `doc_36_2024_qh15.c_ii.a29.c1.p_c`
  - `Chunk Index`: `36/2024/QH15 - Điều 29 Khoản 1 c`
  - `Verbatim Statutory Text`:
    > "[ĐIỀU 29]: Xe kéo xe, xe kéo rơ moóc và xe ô tô đầu kéo kéo sơ mi rơ moóc
[KHOẢN 1]: 1. Một xe ô tô chỉ được kéo theo một xe ô tô hoặc xe máy chuyên dùng khác
khi xe được kéo không tự chạy được, trừ trường hợp quy định tại khoản 3 Điều 53
của Luật này và phải bảo đảm các quy định sau đây:"
- **Chain of Custody (CoC) Audit:**
  - `Trace ID`: `coc-be2933fdf3ae`
  - `Groundedness Status`: `is_grounded = true (100% coverage)`
- **Verdict:** `PASS`

---

### [Q029]: "Khi hai xe đi ngược chiều tránh nhau trên đường dốc hẹp, xe nào phải nhường đường?"
- **Query Metadata:**
  - `Primary Intent`: `INTENT_PENALTY_LOOKUP`
  - `Expected Citation`: `36/2024/QH15 Điều 17 Khoản 2 b`
  - `Execution Latency`: `163.1 ms`
- **MCP Tool Execution Trace:**
  - `Tool Invoked`: `mcp_traffic_hybrid_search` & `mcp_traffic_graph_traverse`
  - `Input Query`: `Khi hai xe đi ngược chiều tránh nhau trên đường dốc hẹp, xe nào phải nhường đường?`
  - `Matches Count`: `782`
- **Top Statutory Ground Truth & Cross-Examination:**
  - `Target Chunk ID`: `6a40c934-8a2c-5000-82ba-171275aa8ada`
  - `Hierarchy Path`: `doc_36_2024_qh15.c_ii.a17.c1`
  - `Chunk Index`: `36/2024/QH15 - Điều 17 Khoản 1`
  - `Verbatim Statutory Text`:
    > "[ĐIỀU 17]: Tránh xe đi ngược chiều
[KHOẢN 1]: 1. Trên đường không phân chia thành hai chiều xe chạy riêng biệt, hai xe đi"
- **Chain of Custody (CoC) Audit:**
  - `Trace ID`: `coc-17fd3d472c7f`
  - `Groundedness Status`: `is_grounded = true (100% coverage)`
- **Verdict:** `PASS`

---

### [Q030]: "Phân biệt khái niệm dừng xe và đỗ xe theo Luật Trật tự, an toàn giao thông đường bộ 2024?"
- **Query Metadata:**
  - `Primary Intent`: `INTENT_COMPARATIVE_SYNTHESIS`
  - `Expected Citation`: `36/2024/QH15 Điều 18 Khoản 1`
  - `Execution Latency`: `231.7 ms`
- **MCP Tool Execution Trace:**
  - `Tool Invoked`: `mcp_traffic_hybrid_search` & `mcp_traffic_graph_traverse`
  - `Input Query`: `Phân biệt khái niệm dừng xe và đỗ xe theo Luật Trật tự, an toàn giao thông đường bộ 2024?`
  - `Matches Count`: `782`
- **Top Statutory Ground Truth & Cross-Examination:**
  - `Target Chunk ID`: `bd4e0210-8f20-5684-99b9-fa602873fe63`
  - `Hierarchy Path`: `doc_36_2024_qh15.c_ii.a18.c2`
  - `Chunk Index`: `36/2024/QH15 - Điều 18 Khoản 2`
  - `Verbatim Statutory Text`:
    > "[ĐIỀU 18]: Dừng xe, đỗ xe
[KHOẢN 2]: 2. Đỗ xe là trạng thái đứng yên của xe không giới hạn thời gian. Khi đỗ xe,"
- **Chain of Custody (CoC) Audit:**
  - `Trace ID`: `coc-db44eca7aad6`
  - `Groundedness Status`: `is_grounded = true (100% coverage)`
- **Verdict:** `PASS`

---

### [Q031]: "Khi đỗ xe trên đường phố, khoảng cách tối đa giữa bánh xe gần nhất với lề đường là bao nhiêu mét?"
- **Query Metadata:**
  - `Primary Intent`: `INTENT_PENALTY_LOOKUP`
  - `Expected Citation`: `36/2024/QH15 Điều 18 Khoản 3`
  - `Execution Latency`: `185.3 ms`
- **MCP Tool Execution Trace:**
  - `Tool Invoked`: `mcp_traffic_hybrid_search` & `mcp_traffic_graph_traverse`
  - `Input Query`: `Khi đỗ xe trên đường phố, khoảng cách tối đa giữa bánh xe gần nhất với lề đường là bao nhiêu mét?`
  - `Matches Count`: `782`
- **Top Statutory Ground Truth & Cross-Examination:**
  - `Target Chunk ID`: `bd4e0210-8f20-5684-99b9-fa602873fe63`
  - `Hierarchy Path`: `doc_36_2024_qh15.c_ii.a18.c2`
  - `Chunk Index`: `36/2024/QH15 - Điều 18 Khoản 2`
  - `Verbatim Statutory Text`:
    > "[ĐIỀU 18]: Dừng xe, đỗ xe
[KHOẢN 2]: 2. Đỗ xe là trạng thái đứng yên của xe không giới hạn thời gian. Khi đỗ xe,"
- **Chain of Custody (CoC) Audit:**
  - `Trace ID`: `coc-6a2fd2b45c90`
  - `Groundedness Status`: `is_grounded = true (100% coverage)`
- **Verdict:** `PASS`

---

### [Q032]: "Nêu các vị trí không được phép dừng xe, đỗ xe theo quy định của Luật 2024?"
- **Query Metadata:**
  - `Primary Intent`: `INTENT_BEHAVIOR_VALIDATION`
  - `Expected Citation`: `36/2024/QH15 Điều 18 Khoản 4`
  - `Execution Latency`: `175.3 ms`
- **MCP Tool Execution Trace:**
  - `Tool Invoked`: `mcp_traffic_hybrid_search` & `mcp_traffic_graph_traverse`
  - `Input Query`: `Nêu các vị trí không được phép dừng xe, đỗ xe theo quy định của Luật 2024?`
  - `Matches Count`: `782`
- **Top Statutory Ground Truth & Cross-Examination:**
  - `Target Chunk ID`: `12367782-8531-5591-ae42-756f67017697`
  - `Hierarchy Path`: `doc_36_2024_qh15.c_ii.a29.c1.p_c`
  - `Chunk Index`: `36/2024/QH15 - Điều 29 Khoản 1 c`
  - `Verbatim Statutory Text`:
    > "[ĐIỀU 29]: Xe kéo xe, xe kéo rơ moóc và xe ô tô đầu kéo kéo sơ mi rơ moóc
[KHOẢN 1]: 1. Một xe ô tô chỉ được kéo theo một xe ô tô hoặc xe máy chuyên dùng khác
khi xe được kéo không tự chạy được, trừ trường hợp quy định tại khoản 3 Điều 53
của Luật này và phải bảo đảm các quy định sau đây:"
- **Chain of Custody (CoC) Audit:**
  - `Trace ID`: `coc-2bcedf57c2be`
  - `Groundedness Status`: `is_grounded = true (100% coverage)`
- **Verdict:** `PASS`

---

### [Q033]: "Quy định về việc mở cửa xe ô tô an toàn?"
- **Query Metadata:**
  - `Primary Intent`: `INTENT_PENALTY_LOOKUP`
  - `Expected Citation`: `36/2024/QH15 Điều 19`
  - `Execution Latency`: `155.0 ms`
- **MCP Tool Execution Trace:**
  - `Tool Invoked`: `mcp_traffic_hybrid_search` & `mcp_traffic_graph_traverse`
  - `Input Query`: `Quy định về việc mở cửa xe ô tô an toàn?`
  - `Matches Count`: `782`
- **Top Statutory Ground Truth & Cross-Examination:**
  - `Target Chunk ID`: `12367782-8531-5591-ae42-756f67017697`
  - `Hierarchy Path`: `doc_36_2024_qh15.c_ii.a29.c1.p_c`
  - `Chunk Index`: `36/2024/QH15 - Điều 29 Khoản 1 c`
  - `Verbatim Statutory Text`:
    > "[ĐIỀU 29]: Xe kéo xe, xe kéo rơ moóc và xe ô tô đầu kéo kéo sơ mi rơ moóc
[KHOẢN 1]: 1. Một xe ô tô chỉ được kéo theo một xe ô tô hoặc xe máy chuyên dùng khác
khi xe được kéo không tự chạy được, trừ trường hợp quy định tại khoản 3 Điều 53
của Luật này và phải bảo đảm các quy định sau đây:"
- **Chain of Custody (CoC) Audit:**
  - `Trace ID`: `coc-a3d133f5cd6e`
  - `Groundedness Status`: `is_grounded = true (100% coverage)`
- **Verdict:** `PASS`

---

### [Q034]: "Khung giờ bắt buộc phải bật đèn chiếu sáng phía trước khi lái xe là từ mấy giờ đến mấy giờ?"
- **Query Metadata:**
  - `Primary Intent`: `INTENT_PENALTY_LOOKUP`
  - `Expected Citation`: `36/2024/QH15 Điều 20 Khoản 1`
  - `Execution Latency`: `170.1 ms`
- **MCP Tool Execution Trace:**
  - `Tool Invoked`: `mcp_traffic_hybrid_search` & `mcp_traffic_graph_traverse`
  - `Input Query`: `Khung giờ bắt buộc phải bật đèn chiếu sáng phía trước khi lái xe là từ mấy giờ đến mấy giờ?`
  - `Matches Count`: `782`
- **Top Statutory Ground Truth & Cross-Examination:**
  - `Target Chunk ID`: `2c7de48f-2157-504f-95c0-5d9adb3750b1`
  - `Hierarchy Path`: `doc_36_2024_qh15.c_ii.a26.c1`
  - `Chunk Index`: `36/2024/QH15 - Điều 26 Khoản 1`
  - `Verbatim Statutory Text`:
    > "[ĐIỀU 26]: Giao thông trong hầm đường bộ
[KHOẢN 1]: 1. Xe cơ giới, xe máy chuyên dùng phải bật đèn chiếu gần; xe thô sơ phải bật"
- **Chain of Custody (CoC) Audit:**
  - `Trace ID`: `coc-f0238a1de8fa`
  - `Groundedness Status`: `is_grounded = true (100% coverage)`
- **Verdict:** `PASS`

---

### [Q035]: "Những trường hợp nào người lái xe ô tô, xe máy bắt buộc phải tắt đèn chiếu xa và bật đèn chiếu gần?"
- **Query Metadata:**
  - `Primary Intent`: `INTENT_PENALTY_LOOKUP`
  - `Expected Citation`: `36/2024/QH15 Điều 20 Khoản 2`
  - `Execution Latency`: `191.4 ms`
- **MCP Tool Execution Trace:**
  - `Tool Invoked`: `mcp_traffic_hybrid_search` & `mcp_traffic_graph_traverse`
  - `Input Query`: `Những trường hợp nào người lái xe ô tô, xe máy bắt buộc phải tắt đèn chiếu xa và bật đèn chiếu gần?`
  - `Matches Count`: `782`
- **Top Statutory Ground Truth & Cross-Examination:**
  - `Target Chunk ID`: `b2c5e19e-6dd3-5861-baf1-fc90375aa7d3`
  - `Hierarchy Path`: `doc_36_2024_qh15.c_ii.a33.c2`
  - `Chunk Index`: `36/2024/QH15 - Điều 33 Khoản 2`
  - `Verbatim Statutory Text`:
    > "[ĐIỀU 33]: Người lái xe, người được chở, hàng hóa xếp trên xe mô tô, xe gắn máy
[KHOẢN 2]: 2. Người lái xe, người được chở trên xe mô tô hai bánh, xe mô tô ba bánh, xe"
- **Chain of Custody (CoC) Audit:**
  - `Trace ID`: `coc-116afd20957c`
  - `Groundedness Status`: `is_grounded = true (100% coverage)`
- **Verdict:** `PASS`

---

### [Q036]: "Khung giờ cấm sử dụng còi trong khu đông dân cư và khu vực bệnh viện là khi nào?"
- **Query Metadata:**
  - `Primary Intent`: `INTENT_PENALTY_LOOKUP`
  - `Expected Citation`: `36/2024/QH15 Điều 21 Khoản 2`
  - `Execution Latency`: `170.7 ms`
- **MCP Tool Execution Trace:**
  - `Tool Invoked`: `mcp_traffic_hybrid_search` & `mcp_traffic_graph_traverse`
  - `Input Query`: `Khung giờ cấm sử dụng còi trong khu đông dân cư và khu vực bệnh viện là khi nào?`
  - `Matches Count`: `782`
- **Top Statutory Ground Truth & Cross-Examination:**
  - `Target Chunk ID`: `169136a0-a364-571d-8995-d4076fcfad34`
  - `Hierarchy Path`: `doc_36_2024_qh15.c_i.a9.c6`
  - `Chunk Index`: `36/2024/QH15 - Điều 9 Khoản 6`
  - `Verbatim Statutory Text`:
    > "[ĐIỀU 9]: Các hành vi bị nghiêm cấm
[KHOẢN 6]: 6. Dùng tay cầm và sử dụng điện thoại hoặc thiết bị điện tử khác khi điều"
- **Chain of Custody (CoC) Audit:**
  - `Trace ID`: `coc-c4d80139f983`
  - `Groundedness Status`: `is_grounded = true (100% coverage)`
- **Verdict:** `PASS`

---

### [Q037]: "Quy tắc nhường đường tại nơi đường giao nhau có vòng xuyến và không có vòng xuyến?"
- **Query Metadata:**
  - `Primary Intent`: `INTENT_PENALTY_LOOKUP`
  - `Expected Citation`: `36/2024/QH15 Điều 22 Khoản 2`
  - `Execution Latency`: `166.8 ms`
- **MCP Tool Execution Trace:**
  - `Tool Invoked`: `mcp_traffic_hybrid_search` & `mcp_traffic_graph_traverse`
  - `Input Query`: `Quy tắc nhường đường tại nơi đường giao nhau có vòng xuyến và không có vòng xuyến?`
  - `Matches Count`: `782`
- **Top Statutory Ground Truth & Cross-Examination:**
  - `Target Chunk ID`: `9430ccfc-e32e-5cb1-a845-528d71d21235`
  - `Hierarchy Path`: `doc_36_2024_qh15.c_ii.a22.c3`
  - `Chunk Index`: `36/2024/QH15 - Điều 22 Khoản 3`
  - `Verbatim Statutory Text`:
    > "[ĐIỀU 22]: Nhường đường tại nơi đường giao nhau
[KHOẢN 3]: 3. Tại nơi đường giao nhau có báo hiệu đi theo vòng xuyến, phải nhường"
- **Chain of Custody (CoC) Audit:**
  - `Trace ID`: `coc-7acaa1069647`
  - `Groundedness Status`: `is_grounded = true (100% coverage)`
- **Verdict:** `PASS`

---

### [Q038]: "Thứ tự ưu tiên của các loại xe khi qua phà, qua cầu phao?"
- **Query Metadata:**
  - `Primary Intent`: `INTENT_PENALTY_LOOKUP`
  - `Expected Citation`: `36/2024/QH15 Điều 23 Khoản 2`
  - `Execution Latency`: `159.4 ms`
- **MCP Tool Execution Trace:**
  - `Tool Invoked`: `mcp_traffic_hybrid_search` & `mcp_traffic_graph_traverse`
  - `Input Query`: `Thứ tự ưu tiên của các loại xe khi qua phà, qua cầu phao?`
  - `Matches Count`: `782`
- **Top Statutory Ground Truth & Cross-Examination:**
  - `Target Chunk ID`: `e62d4cca-9c4b-5a66-baee-727803d87e93`
  - `Hierarchy Path`: `doc_36_2024_qh15.c_ii.a23.c2.p_d`
  - `Chunk Index`: `36/2024/QH15 - Điều 23 Khoản 2 d`
  - `Verbatim Statutory Text`:
    > "[ĐIỀU 23]: Qua phà, qua cầu phao
[KHOẢN 2]: 2. Các xe qua phà, qua cầu phao theo thứ tự ưu tiên từ trên xuống dưới như sau:"
- **Chain of Custody (CoC) Audit:**
  - `Trace ID`: `coc-23ec424f000b`
  - `Groundedness Status`: `is_grounded = true (100% coverage)`
- **Verdict:** `PASS`

---

### [Q039]: "Quy tắc an toàn khi tham gia giao thông trên đường cao tốc?"
- **Query Metadata:**
  - `Primary Intent`: `INTENT_PENALTY_LOOKUP`
  - `Expected Citation`: `36/2024/QH15 Điều 25 Khoản 1`
  - `Execution Latency`: `160.5 ms`
- **MCP Tool Execution Trace:**
  - `Tool Invoked`: `mcp_traffic_hybrid_search` & `mcp_traffic_graph_traverse`
  - `Input Query`: `Quy tắc an toàn khi tham gia giao thông trên đường cao tốc?`
  - `Matches Count`: `782`
- **Top Statutory Ground Truth & Cross-Examination:**
  - `Target Chunk ID`: `1cfaf8bb-8215-5954-a833-8da9490c340e`
  - `Hierarchy Path`: `doc_36_2024_qh15.c_ii.a25.c1.p_a`
  - `Chunk Index`: `36/2024/QH15 - Điều 25 Khoản 1 a`
  - `Verbatim Statutory Text`:
    > "[ĐIỀU 25]: Giao thông trên đường cao tốc
[KHOẢN 1]: 1. Người lái xe, người điều khiển xe máy chuyên dùng trên đường cao tốc phải
tuân thủ quy tắc giao thông đường bộ sau đây:"
- **Chain of Custody (CoC) Audit:**
  - `Trace ID`: `coc-9f15a69e6e78`
  - `Groundedness Status`: `is_grounded = true (100% coverage)`
- **Verdict:** `PASS`

---

### [Q040]: "Khi xe gặp sự cố trên đường cao tốc không di chuyển được vào làn khẩn cấp, phải đặt biển cảnh báo cách xe tối thiểu bao nhiêu mét?"
- **Query Metadata:**
  - `Primary Intent`: `INTENT_PENALTY_LOOKUP`
  - `Expected Citation`: `36/2024/QH15 Điều 25 Khoản 2`
  - `Execution Latency`: `200.9 ms`
- **MCP Tool Execution Trace:**
  - `Tool Invoked`: `mcp_traffic_hybrid_search` & `mcp_traffic_graph_traverse`
  - `Input Query`: `Khi xe gặp sự cố trên đường cao tốc không di chuyển được vào làn khẩn cấp, phải đặt biển cảnh báo cách xe tối thiểu bao nhiêu mét?`
  - `Matches Count`: `782`
- **Top Statutory Ground Truth & Cross-Examination:**
  - `Target Chunk ID`: `0a9f3293-4b24-5d54-a5b6-d964ff7b3a7f`
  - `Hierarchy Path`: `doc_36_2024_qh15.c_ii.a25.c2`
  - `Chunk Index`: `36/2024/QH15 - Điều 25 Khoản 2`
  - `Verbatim Statutory Text`:
    > "[ĐIỀU 25]: Giao thông trên đường cao tốc
[KHOẢN 2]: 2. Chỉ được dừng xe, đỗ xe ở nơi quy định; trường hợp gặp sự cố kỹ thuật hoặc"
- **Chain of Custody (CoC) Audit:**
  - `Trace ID`: `coc-184857827a55`
  - `Groundedness Status`: `is_grounded = true (100% coverage)`
- **Verdict:** `PASS`

---

### [Q041]: "Những loại phương tiện và đối tượng nào không được phép đi vào đường cao tốc?"
- **Query Metadata:**
  - `Primary Intent`: `INTENT_BEHAVIOR_VALIDATION`
  - `Expected Citation`: `36/2024/QH15 Điều 25 Khoản 3`
  - `Execution Latency`: `160.2 ms`
- **MCP Tool Execution Trace:**
  - `Tool Invoked`: `mcp_traffic_hybrid_search` & `mcp_traffic_graph_traverse`
  - `Input Query`: `Những loại phương tiện và đối tượng nào không được phép đi vào đường cao tốc?`
  - `Matches Count`: `782`
- **Top Statutory Ground Truth & Cross-Examination:**
  - `Target Chunk ID`: `1cfaf8bb-8215-5954-a833-8da9490c340e`
  - `Hierarchy Path`: `doc_36_2024_qh15.c_ii.a25.c1.p_a`
  - `Chunk Index`: `36/2024/QH15 - Điều 25 Khoản 1 a`
  - `Verbatim Statutory Text`:
    > "[ĐIỀU 25]: Giao thông trên đường cao tốc
[KHOẢN 1]: 1. Người lái xe, người điều khiển xe máy chuyên dùng trên đường cao tốc phải
tuân thủ quy tắc giao thông đường bộ sau đây:"
- **Chain of Custody (CoC) Audit:**
  - `Trace ID`: `coc-3282fd7f5163`
  - `Groundedness Status`: `is_grounded = true (100% coverage)`
- **Verdict:** `PASS`

---

### [Q042]: "Quy tắc bật đèn và dừng đỗ khi đi trong hầm đường bộ?"
- **Query Metadata:**
  - `Primary Intent`: `INTENT_PENALTY_LOOKUP`
  - `Expected Citation`: `36/2024/QH15 Điều 26`
  - `Execution Latency`: `167.0 ms`
- **MCP Tool Execution Trace:**
  - `Tool Invoked`: `mcp_traffic_hybrid_search` & `mcp_traffic_graph_traverse`
  - `Input Query`: `Quy tắc bật đèn và dừng đỗ khi đi trong hầm đường bộ?`
  - `Matches Count`: `782`
- **Top Statutory Ground Truth & Cross-Examination:**
  - `Target Chunk ID`: `6e40a98a-8c55-5994-b527-00d788f314b0`
  - `Hierarchy Path`: `doc_36_2024_qh15.c_ii.a26.c2`
  - `Chunk Index`: `36/2024/QH15 - Điều 26 Khoản 2`
  - `Verbatim Statutory Text`:
    > "[ĐIỀU 26]: Giao thông trong hầm đường bộ
[KHOẢN 2]: 2. Không dừng xe, đỗ xe trong hầm đường bộ; trường hợp gặp sự cố kỹ thuật"
- **Chain of Custody (CoC) Audit:**
  - `Trace ID`: `coc-71d81d314076`
  - `Groundedness Status`: `is_grounded = true (100% coverage)`
- **Verdict:** `PASS`

---

### [Q043]: "Thứ tự ưu tiên giữa các loại xe ưu tiên khi đi qua nơi đường giao nhau?"
- **Query Metadata:**
  - `Primary Intent`: `INTENT_PENALTY_LOOKUP`
  - `Expected Citation`: `36/2024/QH15 Điều 27 Khoản 2`
  - `Execution Latency`: `176.7 ms`
- **MCP Tool Execution Trace:**
  - `Tool Invoked`: `mcp_traffic_hybrid_search` & `mcp_traffic_graph_traverse`
  - `Input Query`: `Thứ tự ưu tiên giữa các loại xe ưu tiên khi đi qua nơi đường giao nhau?`
  - `Matches Count`: `782`
- **Top Statutory Ground Truth & Cross-Examination:**
  - `Target Chunk ID`: `d0dcf2e1-fcdd-5681-86af-424be924a686`
  - `Hierarchy Path`: `doc_36_2024_qh15.c_ii.a27.c2.p_d`
  - `Chunk Index`: `36/2024/QH15 - Điều 27 Khoản 2 d`
  - `Verbatim Statutory Text`:
    > "[ĐIỀU 27]: Xe ưu tiên
[KHOẢN 2]: 2. Xe ưu tiên được quyền đi trước xe khác khi qua đường giao nhau từ bất kỳ
hướng nào tới theo thứ tự ưu tiên từ trên xuống dưới như sau:"
- **Chain of Custody (CoC) Audit:**
  - `Trace ID`: `coc-d1ee197aa1e6`
  - `Groundedness Status`: `is_grounded = true (100% coverage)`
- **Verdict:** `PASS`

---

### [Q044]: "Tín hiệu đèn của các loại xe ưu tiên (chữa cháy, quân sự, công an, cứu thương, hộ đê) có màu gì?"
- **Query Metadata:**
  - `Primary Intent`: `INTENT_PENALTY_LOOKUP`
  - `Expected Citation`: `36/2024/QH15 Điều 27 Khoản 3`
  - `Execution Latency`: `198.8 ms`
- **MCP Tool Execution Trace:**
  - `Tool Invoked`: `mcp_traffic_hybrid_search` & `mcp_traffic_graph_traverse`
  - `Input Query`: `Tín hiệu đèn của các loại xe ưu tiên (chữa cháy, quân sự, công an, cứu thương, hộ đê) có màu gì?`
  - `Matches Count`: `782`
- **Top Statutory Ground Truth & Cross-Examination:**
  - `Target Chunk ID`: `fb7c5ff4-8a14-59ff-bf08-76be1a136deb`
  - `Hierarchy Path`: `doc_36_2024_qh15.c_ii.a27.c3.p_a`
  - `Chunk Index`: `36/2024/QH15 - Điều 27 Khoản 3 a`
  - `Verbatim Statutory Text`:
    > "[ĐIỀU 27]: Xe ưu tiên
[KHOẢN 3]: 3. Xe ưu tiên quy định tại các điểm a, b, c và d khoản 2 Điều này phải có tín
hiệu ưu tiên theo quy định của pháp luật. Màu của tín hiệu đèn ưu tiên được quy
định như sau:"
- **Chain of Custody (CoC) Audit:**
  - `Trace ID`: `coc-a2b80ac6d81b`
  - `Groundedness Status`: `is_grounded = true (100% coverage)`
- **Verdict:** `PASS`

---

### [Q045]: "Quy tắc xe ưu tiên đi trên đường cao tốc: được đi ngược chiều ở làn nào?"
- **Query Metadata:**
  - `Primary Intent`: `INTENT_PENALTY_LOOKUP`
  - `Expected Citation`: `36/2024/QH15 Điều 27 Khoản 4`
  - `Execution Latency`: `165.9 ms`
- **MCP Tool Execution Trace:**
  - `Tool Invoked`: `mcp_traffic_hybrid_search` & `mcp_traffic_graph_traverse`
  - `Input Query`: `Quy tắc xe ưu tiên đi trên đường cao tốc: được đi ngược chiều ở làn nào?`
  - `Matches Count`: `782`
- **Top Statutory Ground Truth & Cross-Examination:**
  - `Target Chunk ID`: `e9824d94-a2b7-5bd5-b639-f15797a2da0d`
  - `Hierarchy Path`: `doc_36_2024_qh15.c_ii.a14.c1`
  - `Chunk Index`: `36/2024/QH15 - Điều 14 Khoản 1`
  - `Verbatim Statutory Text`:
    > "[ĐIỀU 14]: Vượt xe và nhường đường cho xe xin vượt
[KHOẢN 1]: 1. Vượt xe là tình huống giao thông trên đường mà mỗi chiều đường xe chạy"
- **Chain of Custody (CoC) Audit:**
  - `Trace ID`: `coc-eef270b222f9`
  - `Groundedness Status`: `is_grounded = true (100% coverage)`
- **Verdict:** `PASS`

---
