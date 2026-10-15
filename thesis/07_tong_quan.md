# Tổng quan các nghiên cứu liên quan

Chương này điểm lại các hướng nghiên cứu mà hệ thống dựa vào hoặc cần được so sánh với. Mỗi mục nêu công trình làm gì, rồi nêu luận văn này dùng lại điều gì và khác ở đâu. Chỉ những công trình đã kiểm tra được thông tin xuất bản (tên, tác giả, nơi công bố, mã arXiv hoặc DOI) mới được trích. Con số chỉ được nêu khi đã đọc thấy trong trang tóm tắt hoặc toàn văn. Chỗ nào chưa kiểm tra được thì ghi "cần kiểm tra". Danh mục tài liệu ở cuối chương, đánh số [1], [2]…

## 1. Tra cứu và hỏi đáp văn bản pháp luật tiếng Việt

### 1.1. Các cuộc thi và bộ dữ liệu

**Zalo AI Challenge 2021, nhánh Legal Text Retrieval** [1]. Cho một câu hỏi pháp luật bằng tiếng Việt, hệ thống phải tìm các điều luật liên quan trong một kho văn bản. Ban tổ chức không công bố bài báo mô tả bộ dữ liệu. Bản được dùng nhiều là bản đưa lên Hugging Face và vào bộ đánh giá MTEB với tên "ZacLegalTextRetrieval" [2]. Theo trang mô tả bản này, phần kho có khoảng 61 nghìn đoạn, phần câu hỏi có 818 dòng, trung bình mỗi câu hỏi có khoảng một đáp án.

**ALQAC (Automated Legal Question Answering Competition)** là cuộc thi tổ chức cùng hội nghị KSE.

- ALQAC 2021 [3] có ba nhiệm vụ: tìm điều luật, suy diễn pháp lý (entailment) và hỏi đáp, trên luật Việt Nam và Thái Lan.
- ALQAC 2022 [4] và ALQAC 2023 [5] giữ hai nhiệm vụ trên luật Việt Nam: tìm văn bản pháp luật và hỏi đáp pháp luật.

**Các bộ dữ liệu mới hơn:**

- **VLQA** [6] tự giới thiệu là bộ dữ liệu hỏi đáp pháp luật tiếng Việt lớn và chất lượng cao, dùng để đánh giá cả tìm kiếm và hỏi đáp. Trang tóm tắt không nêu kích thước, nên luận văn không dẫn con số.
- **VLegal-Bench** [7] có 10.450 mẫu, tổ chức theo các mức nhận thức. Các nhiệm vụ gồm hỏi đáp, RAG, suy luận nhiều bước và giải tình huống. Tóm tắt nêu rằng văn bản pháp luật Việt Nam được sửa đổi thường xuyên, gây khó cho việc đánh giá mô hình ngôn ngữ lớn.
- **VLSP 2025 MLQA-TSR** [8] là công trình gần lĩnh vực của luận văn nhất: hỏi đáp đa phương thức (chữ và ảnh) về quy định biển báo giao thông đường bộ Việt Nam. Có hai nhiệm vụ con: tìm điều luật đa phương thức (kết quả tốt nhất F2 = 64,55%) và trả lời câu hỏi đa phương thức (độ chính xác tốt nhất 86,30%).
- **ViBidLQA** (Nguyen Thu Ha và cộng sự, "Vietnamese Legal Question Answering: An Experimental Study", KSE 2024, tr. 440–446): bộ hỏi đáp luật đấu thầu do mô hình ngôn ngữ sinh rồi hai chuyên gia sửa lại, dùng để so sánh hai hướng trích đoạn (MRC) và sinh câu trả lời; mã và dữ liệu tại github.com/ntphuc149/ViLQA.

### 1.2. Các phương pháp

**Tìm điều luật nhiều tầng.** Pham và cộng sự [9] dùng sentence-transformers trên nền PhoBERT [10]. Họ so sánh huấn luyện ở mức âm tiết với mức từ, và so sánh nhiều cách kết hợp điểm BM25 với điểm cosine. Trên một kho luật Việt Nam khoảng 114 nghìn điều, cấu hình tốt nhất (PhoBERT-large mức từ, nhân căn bậc hai điểm BM25 với cosine) đạt F2 = 0,741.

**Mạng chú ý phân cấp.** Nguyen và cộng sự [11] đề xuất hai mô hình, Attentive CNN và Paraformer, đánh giá trên dữ liệu tìm điều luật tiếng Anh, tiếng Nhật và tiếng Việt.

**Mô hình mã hoá hai tháp cho tiếng Việt.** Nhóm BKAI [12] huấn luyện một bi-encoder trên nền PhoBERT-base-v2. Dữ liệu huấn luyện gồm MS MARCO và SQuAD v2 dịch sang tiếng Việt, cùng 80% tập huấn luyện Zalo 2021. Theo trang mô tả mô hình, trên 20% còn lại của Zalo 2021 mô hình đạt Acc@1 = 73,28 và MRR@10 = 80,73. Mô hình yêu cầu tách từ trước khi mã hoá.

**Dữ liệu tổng hợp.** Pham Tien và cộng sự [13] tiền huấn luyện bi-encoder và ColBERT trên câu hỏi do mô hình ngôn ngữ lớn sinh ra, rồi tinh chỉnh với mẫu âm khó.

**Hệ thống RAG pháp luật tiếng Việt.** Nguyen Ba và cộng sự [14] mô tả một hệ thống hỏi đáp gồm: xử lý văn bản tiếng Việt cho mô hình embedding, một biến thể của RRF có chuẩn hoá thứ tự để gộp tìm theo từ khoá và theo vector, và xếp hạng lại bằng mô hình ngôn ngữ lớn. Về cách làm, đây là công trình gần thiết kế tìm lai của luận văn nhất. Trang tóm tắt không có số liệu.

**Công cụ xử lý tiếng Việt.** Phần lớn các công trình trên tách từ trước khi mã hoá, bằng VnCoreNLP [15] hoặc pyvi [16]. pyvi còn có chức năng bỏ dấu và khôi phục dấu.

### 1.3. Quan hệ với luận văn

Luận văn khác các công trình trên ở bốn điểm:

1. **Đơn vị tìm kiếm.** Zalo 2021 và ALQAC lấy đơn vị là một điều luật. Luận văn tìm đến Điểm, vì mức phạt và hành vi nằm ở hai cấp khác nhau trong nghị định xử phạt (chương 6, mục 2.4).
2. **Hiệu lực theo thời gian.** Các bộ dữ liệu trên coi kho là tĩnh. Luận văn lọc theo ngày vi phạm và gắn ghi chú văn bản sửa đổi. Nhận xét của VLegal-Bench [7] về việc văn bản pháp luật được sửa đổi thường xuyên cho thấy đây là vấn đề chung, không riêng luật giao thông.
3. **Câu hỏi kiểu người dùng.** Bộ đánh giá câu trả lời của luận văn soạn theo lời hỏi thật, có câu không dấu và viết tắt. Ở đây không tách từ: nhánh BM25 dùng âm tiết và cặp âm tiết sau khi bỏ dấu (chương 6, mục 4.1). Đây là một lựa chọn đơn giản hơn tách từ. Luận văn chưa so trực tiếp hai cách.
4. **Chưa đo trên bộ chuẩn chung.** Hệ thống chưa được chạy trên Zalo 2021 hay ALQAC, và chưa so với bi-encoder BKAI [12]. Kết quả ở chương 2 vì vậy không so trực tiếp được với các con số trên. Đây là một hạn chế cần nêu rõ.

## 2. Sinh câu trả lời có tăng cường truy xuất (RAG)

Lewis và cộng sự [17] đặt tên cho mô hình **RAG (Retrieval-Augmented Generation)**. Mô hình sinh câu trả lời được ghép với một bộ tìm kiếm vector trên Wikipedia (dùng DPR [18]): tri thức nằm một phần trong tham số của mô hình, một phần trong chỉ mục ngoài có thể thay thế. Mô hình đạt kết quả tốt nhất thời điểm đó trên ba bài hỏi đáp miền mở.

Gao và cộng sự [19] tổng hợp các hướng RAG cho mô hình ngôn ngữ lớn thành ba dạng:

- **Naive RAG:** tìm một lần rồi sinh;
- **Advanced RAG:** thêm xử lý trước và sau khi tìm, như viết lại câu hỏi và xếp hạng lại;
- **Modular RAG:** các thành phần ghép linh hoạt, có thể lặp.

**Quan hệ với luận văn.** Chế độ tìm một lần (chương 6, mục 5.2) là dạng Naive RAG, thêm một bước kiểm tra bám nguồn. Chế độ agent gần với dạng Modular: mô hình tự quyết định viết lại câu hỏi, tìm lại, đọc rộng ra hay đi theo trích dẫn. Khác với RAG gốc [17], luận văn không huấn luyện mô hình nào. Bộ tìm kiếm và mô hình sinh tách rời, giao tiếp qua công cụ.

## 3. Tìm theo từ khoá, tìm theo vector và BM25

**BM25.** Robertson và Zaragoza [20] trình bày khung xác suất về mức liên quan, trong đó BM25 là hàm xếp hạng kết hợp ba yếu tố:

- IDF: từ hiếm có trọng số cao hơn từ phổ biến;
- tần suất từ trong văn bản, có bão hoà (tham số k1);
- chuẩn hoá theo độ dài văn bản (tham số b).

**Tìm theo vector.** DPR [18] dùng hai bộ mã hoá BERT cho câu hỏi và đoạn văn, huấn luyện bằng học tương phản. Trên các bộ hỏi đáp miền mở, DPR hơn BM25 (Lucene) từ 9 đến 19 điểm phần trăm về độ chính xác top-20.

**BEIR.** Thakur và cộng sự [21] đánh giá 10 hệ thống tìm kiếm trên 18 bộ dữ liệu, trong điều kiện không huấn luyện lại cho miền mới (zero-shot). Kết luận đáng chú ý: BM25 là một mốc so sánh vững, và nhiều mô hình vector huấn luyện trên một miền tụt điểm khi sang miền khác.

**Quan hệ với luận văn.** Kết quả ở chương 2 khớp với nhận định của BEIR. Trên tập dev, BM25 riêng đạt Hit@1 57,8%, cao hơn nhánh vector riêng (50,0%). Luận văn tự cài BM25 trong SQL với k1 = 1,2 và b = 0,75, theo công thức của [20]. Thay đổi lớn nhất về chất lượng tìm kiếm là thay `ts_rank` (không có IDF) bằng BM25. Đây không phải đóng góp mới về phương pháp, mà là bằng chứng rằng chọn sai hàm xếp hạng từ khoá có thể làm hỏng cả một hệ thống tìm lai.

## 4. Tìm lai và Reciprocal Rank Fusion

**RRF.** Cormack, Clarke và Büttcher [22] đề xuất gộp nhiều danh sách xếp hạng bằng công thức điểm(d) = Σ_r 1/(k + r(d)), trong đó r(d) là hạng của d trong danh sách r. RRF chỉ dùng thứ hạng, nên không cần chuẩn hoá điểm của các hệ thống khác nhau. Trên dữ liệu TREC, RRF tốt hơn phương pháp Condorcet và tốt hơn từng hệ thống riêng lẻ. Bài báo ghi rõ hằng số k = 60 "được cố định trong một khảo sát thử nghiệm ban đầu", tức là chọn bằng thực nghiệm chứ không suy ra từ lý thuyết.

**Phân tích các hàm gộp.** Bruch, Gai và Ingber [23] so sánh RRF với tổ hợp lồi (convex combination) của điểm từ khoá và điểm vector đã chuẩn hoá. Họ thấy tổ hợp lồi tốt hơn RRF cả trong miền và ngoài miền, và chỉ cần ít mẫu để chỉnh. Họ cũng thấy RRF nhạy với tham số của nó, trái với nhận định của các nghiên cứu trước.

**Quan hệ với luận văn.**

- Hệ thống dùng RRF với k = 20 thay vì 60. Lý do: với k = 60, một kết quả hạng 1–3 của một nhánh có thể bị đẩy ra khỏi top 10 sau khi gộp (chương 5). Điều này phù hợp với nhận xét của [23] rằng RRF nhạy với k.
- Khác biệt giữa k = 20 và k = 60 trên tập dev chỉ là 4 câu (p = 0,125; chương 2). Hằng số này được chọn bằng cách nhìn tập dev (chương 4).
- Luận văn chưa thử tổ hợp lồi [23] hay phép nhân điểm của [9]. Đây là một hướng so sánh nên làm.
- Nhánh thứ ba của luận văn (tìm theo cụm từ nguyên văn do agent đặt) không nằm trong RRF. Nó được gắn nhãn riêng (`found_in`) để agent tự cân nhắc. Trong các công trình đã đọc, chưa thấy cách làm tương tự.

## 5. Mô hình embedding

**Qwen3 Embedding.** Zhang và cộng sự [24] giới thiệu họ mô hình embedding và xếp hạng lại dựng trên mô hình nền Qwen3, gồm ba cỡ. Số liệu dưới đây lấy từ báo cáo kỹ thuật:

| Mô hình | Số chiều | Độ dài tối đa | MMTEB (trung bình theo nhiệm vụ) |
| :-- | --: | --: | --: |
| Qwen3-Embedding-0.6B | 1024 | 32K token | 64,33 |
| Qwen3-Embedding-4B | 2560 | 32K token | 69,45 |
| Qwen3-Embedding-8B | 4096 | 32K token | 70,58 |

Các mô hình hỗ trợ chọn số chiều đầu ra linh hoạt (theo kiểu Matryoshka) và nhận chỉ dẫn (instruction) cho câu hỏi; văn bản thì mã hoá không kèm chỉ dẫn. Cùng bảng so sánh, multilingual-e5-large-instruct đạt 63,22 và BGE-M3 đạt 59,56 trên MMTEB.

**Các mô hình đa ngôn ngữ khác.**

- **multilingual-E5** [25]: các cỡ small, base, large, tiền huấn luyện tương phản trên khoảng một tỉ cặp văn bản đa ngôn ngữ, có thêm bản nhận chỉ dẫn.
- **BGE-M3** [26]: hỗ trợ hơn 100 ngôn ngữ, đầu vào đến 8.192 token. Một mô hình cho ba kiểu tìm kiếm: vector đặc, vector thưa và nhiều vector.

**Matryoshka Representation Learning (MRL).** Kusupati và cộng sự [27] huấn luyện để các tiền tố của vector embedding cũng là biểu diễn dùng được. Nhờ vậy có thể cắt bớt chiều mà mất ít chất lượng.

**Bộ đánh giá.** MTEB [28] gồm 8 loại nhiệm vụ trên 58 bộ dữ liệu, với kết luận rằng không phương pháp nào thắng ở mọi nhiệm vụ. MMTEB [29] mở rộng ra hơn 500 nhiệm vụ trên hơn 250 ngôn ngữ.

**Quan hệ với luận văn.**

- Hệ thống dùng Qwen3-Embedding-0.6B, cắt từ 1024 xuống 512 chiều nhờ tính chất MRL. Câu hỏi được mã hoá kèm prompt truy vấn, đúng cách dùng mà [24] mô tả.
- Lý do chọn là thực dụng (chương 6, mục 7.9): đa ngôn ngữ, nhận chuỗi dài, chạy được trên GPU 4 GB.
- Bảng trên cho thấy bản 4B hơn bản 0.6B khoảng 5 điểm trên MMTEB. Nhưng luận văn chưa đo được bản 4B trên kho hiện tại (chương 2).
- Luận văn chưa so với các mô hình chuyên cho tiếng Việt như bi-encoder BKAI [12]. Mô hình đó cần tách từ và giới hạn 256 token, ngắn hơn nhiều đoạn ngữ cảnh hoá của hệ thống.

## 6. Cắt đoạn theo cấu trúc văn bản

**Cắt theo loại phần tử.** Jimeno Yepes và cộng sự [30] cắt báo cáo tài chính theo loại phần tử của văn bản (tiêu đề, đoạn văn, bảng) thay vì theo độ dài cố định. Họ báo cáo rằng cách này cải thiện đáng kể RAG trên báo cáo tài chính.

**Độ mịn của đơn vị tìm kiếm.** Chen và cộng sự [31] so sánh ba mức đơn vị lập chỉ mục: đoạn văn, câu, và mệnh đề (proposition, một sự kiện tối giản). Mức mệnh đề cho kết quả tìm kiếm và hỏi đáp tốt hơn mức đoạn văn.

**Contextual Retrieval.** Anthropic [32] đề xuất ghép trước mỗi đoạn khoảng 50–100 token ngữ cảnh do một mô hình ngôn ngữ sinh ra, rồi mới mã hoá vector và lập chỉ mục BM25. Theo bài viết, tỉ lệ trượt (1 − recall@20) giảm:

| Cấu hình | Tỉ lệ trượt |
| :-- | --: |
| Gốc | 5,7% |
| Thêm ngữ cảnh khi mã hoá vector | 3,7% |
| Thêm ngữ cảnh cho cả vector và BM25 | 2,9% |
| Thêm xếp hạng lại | 1,9% |

**Benchmark pháp lý.** LegalBench-RAG [33] là bộ đánh giá riêng cho bước tìm kiếm của RAG trong miền pháp lý tiếng Anh, gồm 6.858 cặp câu hỏi–đáp án do chuyên gia pháp lý gán nhãn, trên một kho hơn 79 triệu ký tự.

**Quan hệ với luận văn.**

- Hệ thống theo cùng ý tưởng với [30] và [31]: đơn vị tìm kiếm phải theo cấu trúc tự nhiên của văn bản và đủ mịn. Với văn bản quy phạm pháp luật, cấu trúc đó được quy ước soạn thảo xác định sẵn (Điều, Khoản, Điểm), nên có thể phân tích tất định thay vì đoán.
- Văn bản ngữ cảnh hoá (chương 6, mục 2.4) cùng mục đích với Contextual Retrieval [32]: một đoạn đứng riêng phải mang đủ ngữ cảnh để được tìm thấy. Khác ở chỗ ngữ cảnh của luận văn lấy từ chính cây văn bản (tên văn bản, Chương, Điều, câu dẫn của Khoản cha), không do mô hình sinh. Vì vậy không tốn chi phí gọi mô hình, không có nguy cơ bịa, và ngữ cảnh vẫn là nguyên văn luật.
- Ngữ cảnh cũng được dùng cho cả vector và BM25 như [32]. Chương 5 cho thấy mặt trái của cách này: tên văn bản dài lặp ở mọi đoạn làm yếu tín hiệu phân biệt.
- Luận văn không tìm thấy công trình đã bình duyệt nào về cắt đoạn văn bản pháp luật tiếng Việt theo Điều–Khoản–Điểm. Nhận định này giới hạn trong phạm vi đã tìm.

## 7. Tìm kiếm có dùng công cụ và agent

**Kết hợp suy luận và hành động.** ReAct [34] cho mô hình ngôn ngữ xen kẽ bước suy luận bằng lời với bước hành động, ví dụ gọi API tìm kiếm Wikipedia, rồi đọc kết quả để quyết định bước sau. Trên ALFWorld và WebShop, ReAct tăng tỉ lệ thành công tuyệt đối 34 và 10 điểm phần trăm.

**Tự học cách dùng công cụ.** Toolformer [35] huấn luyện mô hình tự quyết định khi nào gọi API (máy tính, hỏi đáp, tìm kiếm, dịch, lịch), theo cách tự giám sát.

**Tìm kiếm xen kẽ chuỗi suy luận.** IRCoT [36] dùng từng bước của chuỗi suy luận làm câu truy vấn cho bước tìm tiếp theo. Trên bốn bộ câu hỏi nhiều bước (HotpotQA, 2WikiMultihopQA, MuSiQue, IIRC), phương pháp tăng tới 21 điểm về tìm kiếm và 15 điểm về hỏi đáp.

**Tự phản tỉnh.** Self-RAG [37] huấn luyện mô hình tự quyết định khi nào cần tìm, và tự chấm câu trả lời của mình bằng các token phản tỉnh. Tác giả báo cáo độ chính xác trích dẫn tốt hơn.

**Tổng quan Agentic RAG.** Singh và cộng sự [38] phân loại các hệ thống RAG dạng agent theo số agent, cấu trúc điều khiển, mức tự chủ và cách biểu diễn tri thức.

**Model Context Protocol (MCP).** MCP [39] là giao thức mở do Anthropic công bố tháng 11/2024, chuẩn hoá cách ứng dụng mô hình ngôn ngữ (client) kết nối với nguồn dữ liệu và công cụ (server).

**Quan hệ với luận văn.**

- Chế độ agent của luận văn là một vòng lặp kiểu ReAct [34]. Mô hình không được huấn luyện thêm như Toolformer [35] hay Self-RAG [37]; chỉ có prompt và mô tả công cụ.
- Agent dùng một mô hình thương mại sẵn có (Claude Code) qua MCP [39]. Luận văn không đóng góp gì cho cơ chế agent.
- Đóng góp nằm ở **thiết kế công cụ cho miền pháp luật**:
  - công cụ trả về đường dẫn để agent đi tiếp;
  - nhánh nguyên văn có nhãn `found_in`;
  - `hierarchical_navigate` để đọc cả Điều;
  - `graph_traverse` để đi theo trích dẫn đã giải trên cây;
  - ghi chú sửa đổi gắn sẵn trong kết quả;
  - danh sách công cụ chỉ đọc.
- Ở chương 3, so với lời gọi tìm kiếm đầu tiên do agent viết, các bước tra cứu thêm không làm tăng tỉ lệ tìm thấy (95,0% so với 92,5% trên 40 câu holdout); lợi ích của chúng là đọc toàn văn, mở điều sửa đổi và tự kiểm tra số liệu. Điều này khác với các báo cáo của [34] và [36], vốn so tìm kiếm nhiều bước với tìm một lần trên câu hỏi gốc; đây là so sánh trên một bộ dữ liệu nhỏ, với một mô hình.

## 8. Đánh giá RAG: bám nguồn và trích dẫn

**Đánh giá không cần đáp án.** RAGAS [40] đề xuất các thước đo không cần đáp án chuẩn:

- độ liên quan của ngữ cảnh tìm được;
- độ trung thành (faithfulness): câu trả lời có được ngữ cảnh hỗ trợ không;
- độ liên quan của câu trả lời.

Các thước đo này đều do một mô hình ngôn ngữ chấm.

**Bộ chấm huấn luyện riêng.** ARES [41] huấn luyện các mô hình chấm nhỏ trên dữ liệu tổng hợp, rồi hiệu chỉnh bằng vài trăm nhãn người qua phương pháp prediction-powered inference.

**Đánh giá trích dẫn.** ALCE [42] đo khả năng sinh câu trả lời kèm trích dẫn theo ba mặt: độ trôi chảy, độ đúng và chất lượng trích dẫn. Trên bộ ELI5, ngay cả mô hình tốt nhất cũng thiếu hỗ trợ trích dẫn đầy đủ khoảng 50% số lần.

**Ảo giác trong công cụ pháp lý thương mại.** Magesh và cộng sự [43] đánh giá các công cụ nghiên cứu pháp luật có dùng AI của Mỹ: Lexis+ AI, Westlaw AI-Assisted Research, Ask Practical Law AI. Các công cụ này vẫn tạo ra thông tin sai (ảo giác) trong khoảng 17% đến 33% số câu hỏi. Tỉ lệ này thấp hơn GPT-4 dùng riêng, nhưng cao hơn nhiều so với tuyên bố của các nhà cung cấp rằng công cụ của họ tránh được ảo giác.

**Kiểm định ghép cặp.** Kiểm định McNemar [44] dùng để so hai tỉ lệ trên cùng một tập mẫu. Chương 2 dùng kiểm định này để so các cấu hình tìm kiếm trên cùng 715 câu.

**Quan hệ với luận văn.**

- Luận văn không dùng mô hình làm bộ chấm như [40] hay [41]. Câu trả lời được chấm bằng quy tắc, dựa trên đáp án tra tay:
  - trích đúng Điều và đúng Khoản/Điểm;
  - đủ mức tiền và dữ kiện;
  - số Điều và số tiền trong câu trả lời phải có trong nguồn được trích.
- Tiêu chí cuối là một dạng hẹp của "độ trung thành" [40] và "chất lượng trích dẫn" [42]. Nó chỉ áp dụng cho hai loại khẳng định kiểm tra được chắc chắn: số Điều và số tiền.
- Lựa chọn này phù hợp với miền pháp luật. Như [43] cho thấy, lỗi nguy hiểm nhất là trích dẫn hoặc con số nghe hợp lý nhưng sai, và đó đúng là hai thứ bộ kiểm tra bắt được.
- Mặt trái: bộ chấm quy tắc có lỗi riêng. Chương 4 và 5 ghi lại ba lỗi của bộ chấm, cùng một mâu thuẫn giữa bộ kiểm tra bám nguồn và lời nhắc gửi agent.
- Luận văn cũng chưa có đánh giá của người có chuyên môn pháp lý. Bước đó đang chờ (thư mục `review/`).

## 9. Tóm tắt vị trí của luận văn

| Hướng nghiên cứu | Luận văn dùng lại | Luận văn khác hoặc thêm |
| :-- | :-- | :-- |
| Tìm và hỏi đáp pháp luật tiếng Việt [1]–[14] | Bài toán tìm điều luật cho câu hỏi tiếng Việt | Đơn vị đến Điểm; lọc theo ngày vi phạm; ghi chú sửa đổi; câu hỏi kiểu người dùng; chưa đo trên Zalo/ALQAC |
| RAG [17], [19] | Tách bộ tìm kiếm khỏi bộ sinh | Không huấn luyện mô hình; có kiểm tra bám nguồn và trả lời lại |
| BM25, tìm theo vector [18], [20], [21] | Công thức BM25 chuẩn; tìm vector với HNSW | BM25 trên âm tiết và cặp âm tiết không dấu, không tách từ |
| Tìm lai, RRF [22], [23] | RRF | k = 20 chọn trên dev; thêm nhánh nguyên văn ngoài RRF; chưa thử tổ hợp lồi |
| Embedding [24]–[29] | Qwen3-Embedding-0.6B, MRL 512 chiều, prompt truy vấn | Chưa đo bản 4B và mô hình chuyên tiếng Việt |
| Cắt đoạn theo cấu trúc [30]–[33] | Đơn vị theo cấu trúc, ngữ cảnh ghép vào đoạn | Ngữ cảnh lấy tất định từ cây văn bản, không do mô hình sinh; kiểm tra phủ dòng |
| Agent, công cụ, MCP [34]–[39] | Vòng lặp kiểu ReAct qua MCP | Bộ công cụ chỉ đọc thiết kế cho văn bản pháp luật |
| Đánh giá RAG [40]–[44] | Bám nguồn, chất lượng trích dẫn, McNemar | Chấm bằng quy tắc với đáp án tra tay; tách dev/holdout |

## Tài liệu tham khảo

[1] Zalo AI Challenge 2021, nhánh Legal Text Retrieval. https://challenge.zalo.ai/ (ban tổ chức không công bố bài báo mô tả dữ liệu).

[2] GreenNode. *zalo-ai-legal-text-retrieval-vn* (bộ dữ liệu trên Hugging Face, nhiệm vụ MTEB "ZacLegalTextRetrieval"). https://huggingface.co/datasets/GreenNode/zalo-ai-legal-text-retrieval-vn

[3] Nguyen Ha Thanh, Bui Minh Quan, Chau Nguyen, và cộng sự. A Summary of the ALQAC 2021 Competition. *13th International Conference on Knowledge and Systems Engineering (KSE)*, 2021, tr. 1–5. DOI: 10.1109/KSE53942.2021.9648724. arXiv:2204.10717.

[4] Chau Nguyen, Minh-Quan Bui, Dinh-Truong Do, và cộng sự. ALQAC 2022: A Summary of the Competition. *14th International Conference on Knowledge and Systems Engineering (KSE)*, 2022, tr. 1–5. DOI: 10.1109/KSE56063.2022.9953764.

[5] Chau Nguyen, Son T. Luu, Thanh Tran, và cộng sự. A Summary of the ALQAC 2023 Competition. *15th International Conference on Knowledge and Systems Engineering (KSE)*, 2023, tr. 1–6. DOI: 10.1109/KSE59128.2023.10299527.

[6] Tan-Minh Nguyen, Hoang-Trung Nguyen, Trong-Khoi Dao, Xuan-Hieu Phan, Ha-Thanh Nguyen, Thi-Hai-Yen Vuong. VLQA: The First Comprehensive, Large, and High-Quality Vietnamese Dataset for Legal Question Answering. arXiv:2507.19995, 2025.

[7] Nguyen Tien Dong, Minh-Anh Nguyen, Thanh Dat Hoang, và cộng sự. VLegal-Bench: Cognitively Grounded Benchmark for Vietnamese Legal Reasoning of Large Language Models. arXiv:2512.14554, 2025.

[8] Son T. Luu, Trung Vo, Hiep Nguyen, Khanh Quoc Tran, Kiet Van Nguyen, Vu Tran, Ngan Luu-Thuy Nguyen, Le-Minh Nguyen. VLSP 2025 MLQA-TSR Challenge: Vietnamese Multimodal Legal Question Answering on Traffic Sign Regulation. *VLSP 2025*. arXiv:2510.20381.

[9] Nhat-Minh Pham, Ha-Thanh Nguyen, Trong-Hop Do. Multi-stage Information Retrieval for Vietnamese Legal Texts. *PKAW 2022*. arXiv:2209.14494.

[10] Dat Quoc Nguyen, Anh Tuan Nguyen. PhoBERT: Pre-trained language models for Vietnamese. *Findings of EMNLP 2020*, tr. 1037–1042. DOI: 10.18653/v1/2020.findings-emnlp.92.

[11] Ha-Thanh Nguyen, Manh-Kien Phi, Xuan-Bach Ngo, Vu Tran, Le-Minh Nguyen, Minh-Phuong Tu. Attentive Deep Neural Networks for Legal Document Retrieval. *Artificial Intelligence and Law* 32 (2024), tr. 57–86. DOI: 10.1007/s10506-022-09341-8. arXiv:2212.13899.

[12] Nguyen Quang Duc, Le Hai Son, Nguyen Duc Nhan, Nguyen Dich Nhat Minh, Le Thanh Huong, Dinh Viet Sang. Towards Comprehensive Vietnamese Retrieval-Augmented Generation and Large Language Models. arXiv:2403.01616, 2024. Mô hình: https://huggingface.co/bkai-foundation-models/vietnamese-bi-encoder

[13] Son Pham Tien, Hieu Nguyen Doan, An Nguyen Dai, Sang Dinh Viet. Improving Vietnamese Legal Document Retrieval using Synthetic Data. arXiv:2412.00657, 2024.

[14] Thiem Nguyen Ba, Vinh Doan The, Tung Pham Quang, Toan Tran Van. Vietnamese Legal Information Retrieval in Question-Answering System. arXiv:2409.13699, 2024.

[15] Thanh Vu, Dat Quoc Nguyen, Dai Quoc Nguyen, Mark Dras, Mark Johnson. VnCoreNLP: A Vietnamese Natural Language Processing Toolkit. *NAACL 2018 Demonstrations*, tr. 56–60. DOI: 10.18653/v1/N18-5012.

[16] Viet-Trung Tran. pyvi: Python Vietnamese Core NLP Toolkit. https://pypi.org/project/pyvi/

[17] Patrick Lewis, Ethan Perez, Aleksandra Piktus, và cộng sự. Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. *NeurIPS 2020*. arXiv:2005.11401.

[18] Vladimir Karpukhin, Barlas Oğuz, Sewon Min, và cộng sự. Dense Passage Retrieval for Open-Domain Question Answering. *EMNLP 2020*. arXiv:2004.04906.

[19] Yunfan Gao, Yun Xiong, Xinyu Gao, và cộng sự. Retrieval-Augmented Generation for Large Language Models: A Survey. arXiv:2312.10997, 2023.

[20] Stephen Robertson, Hugo Zaragoza. The Probabilistic Relevance Framework: BM25 and Beyond. *Foundations and Trends in Information Retrieval* 3(4), 2009, tr. 333–389. DOI: 10.1561/1500000019.

[21] Nandan Thakur, Nils Reimers, Andreas Rücklé, Abhishek Srivastava, Iryna Gurevych. BEIR: A Heterogenous Benchmark for Zero-shot Evaluation of Information Retrieval Models. *NeurIPS 2021 Datasets and Benchmarks Track*. arXiv:2104.08663.

[22] Gordon V. Cormack, Charles L. A. Clarke, Stefan Büttcher. Reciprocal Rank Fusion outperforms Condorcet and Individual Rank Learning Methods. *SIGIR 2009*, tr. 758–759. DOI: 10.1145/1571941.1572114.

[23] Sebastian Bruch, Siyu Gai, Amir Ingber. An Analysis of Fusion Functions for Hybrid Retrieval. *ACM Transactions on Information Systems* 42(1), 2023, tr. 1–35. DOI: 10.1145/3596512. arXiv:2210.11934.

[24] Yanzhao Zhang, Mingxin Li, Dingkun Long, Xin Zhang, Huan Lin, Baosong Yang, Pengjun Xie, An Yang, Dayiheng Liu, Junyang Lin, Fei Huang, Jingren Zhou. Qwen3 Embedding: Advancing Text Embedding and Reranking Through Foundation Models. arXiv:2506.05176, 2025.

[25] Liang Wang, Nan Yang, Xiaolong Huang, Linjun Yang, Rangan Majumder, Furu Wei. Multilingual E5 Text Embeddings: A Technical Report. arXiv:2402.05672, 2024.

[26] Jianlyu Chen, Shitao Xiao, Peitian Zhang, Kun Luo, Defu Lian, Zheng Liu. M3-Embedding: Multi-Linguality, Multi-Functionality, Multi-Granularity Text Embeddings Through Self-Knowledge Distillation. Findings of the Association for Computational Linguistics: ACL 2024, tr. 2318–2335. doi:10.18653/v1/2024.findings-acl.137. arXiv:2402.03216.

[27] Aditya Kusupati, Gantavya Bhatt, Aniket Rege, và cộng sự. Matryoshka Representation Learning. Advances in Neural Information Processing Systems 35 (NeurIPS 2022). arXiv:2205.13147.

[28] Niklas Muennighoff, Nouamane Tazi, Loïc Magne, Nils Reimers. MTEB: Massive Text Embedding Benchmark. Proceedings of the 17th Conference of the European Chapter of the ACL (EACL 2023), tr. 2014–2037. doi:10.18653/v1/2023.eacl-main.148. arXiv:2210.07316.

[29] Kenneth Enevoldsen, Isaac Chung, Imene Kerboua, và cộng sự. MMTEB: Massive Multilingual Text Embedding Benchmark. The Thirteenth International Conference on Learning Representations (ICLR 2025). arXiv:2502.13595.

[30] Antonio Jimeno Yepes, Yao You, Jan Milczek, Sebastian Laverde, Renyu Li. Financial Report Chunking for Effective Retrieval Augmented Generation. arXiv:2402.05131, 2024.

[31] Tong Chen, Hongwei Wang, Sihao Chen, và cộng sự. Dense X Retrieval: What Retrieval Granularity Should We Use? arXiv:2312.06648, 2023.

[32] Anthropic. Introducing Contextual Retrieval. Bài viết ngày 19/9/2024. https://www.anthropic.com/news/contextual-retrieval

[33] Nicholas Pipitone, Ghita Houir Alami. LegalBench-RAG: A Benchmark for Retrieval-Augmented Generation in the Legal Domain. arXiv:2408.10343, 2024.

[34] Shunyu Yao, Jeffrey Zhao, Dian Yu, Nan Du, Izhak Shafran, Karthik Narasimhan, Yuan Cao. ReAct: Synergizing Reasoning and Acting in Language Models. *ICLR 2023*. arXiv:2210.03629.

[35] Timo Schick, Jane Dwivedi-Yu, Roberto Dessì, và cộng sự. Toolformer: Language Models Can Teach Themselves to Use Tools. Advances in Neural Information Processing Systems 36 (NeurIPS 2023). arXiv:2302.04761.

[36] Harsh Trivedi, Niranjan Balasubramanian, Tushar Khot, Ashish Sabharwal. Interleaving Retrieval with Chain-of-Thought Reasoning for Knowledge-Intensive Multi-Step Questions. *ACL 2023*. arXiv:2212.10509.

[37] Akari Asai, Zeqiu Wu, Yizhong Wang, Avirup Sil, Hannaneh Hajishirzi. Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection. The Twelfth International Conference on Learning Representations (ICLR 2024). arXiv:2310.11511.

[38] Aditi Singh, Abul Ehtesham, Saket Kumar, Tala Talaei Khoei, Athanasios V. Vasilakos. Agentic Retrieval-Augmented Generation: A Survey on Agentic RAG. arXiv:2501.09136, 2025.

[39] Anthropic. Introducing the Model Context Protocol. Bài viết ngày 25/11/2024. https://www.anthropic.com/news/model-context-protocol. Đặc tả: https://modelcontextprotocol.io

[40] Shahul Es, Jithin James, Luis Espinosa-Anke, Steven Schockaert. RAGAs: Automated Evaluation of Retrieval Augmented Generation. *EACL 2024 System Demonstrations*, tr. 150–158. DOI: 10.18653/v1/2024.eacl-demo.16. arXiv:2309.15217.

[41] Jon Saad-Falcon, Omar Khattab, Christopher Potts, Matei Zaharia. ARES: An Automated Evaluation Framework for Retrieval-Augmented Generation Systems. *NAACL 2024*. arXiv:2311.09476.

[42] Tianyu Gao, Howard Yen, Jiatong Yu, Danqi Chen. Enabling Large Language Models to Generate Text with Citations. *EMNLP 2023*. arXiv:2305.14627.

[43] Varun Magesh, Faiz Surani, Matthew Dahl, Mirac Suzgun, Christopher D. Manning, Daniel E. Ho. Hallucination-Free? Assessing the Reliability of Leading AI Legal Research Tools. *Journal of Empirical Legal Studies* 22(2), 2025, tr. 216–242. DOI: 10.1111/jels.12413. arXiv:2405.20362.

[44] Quinn McNemar. Note on the Sampling Error of the Difference Between Correlated Proportions or Percentages. *Psychometrika* 12(2), 1947, tr. 153–157. DOI: 10.1007/BF02295996.
