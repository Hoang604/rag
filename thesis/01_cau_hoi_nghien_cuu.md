# Câu hỏi nghiên cứu và đóng góp

## Bài toán

Người dân hỏi về luật giao thông bằng lời thường: "xe máy vượt đèn đỏ phạt bao nhiêu", "uong 1 lon bia roi chay xe may co bi phat ko". Câu trả lời đúng nằm rải rác trong nhiều văn bản. Một nghị định xử phạt có hàng nghìn điểm, khoản. Thông tư và quy chuẩn quy định chi tiết. Nhiều văn bản sửa đổi có hiệu lực từ những ngày khác nhau.

Một hệ thống RAG thông thường (cắt văn bản thành đoạn cố định, tìm theo vector, đưa cho mô hình ngôn ngữ viết câu trả lời) sai ở ba chỗ quen thuộc:

- **Cắt mất cấu trúc pháp lý.** Đoạn cắt ra không biết mình là Điểm nào của Khoản nào. Câu dẫn mức phạt ("Phạt tiền từ … đến …") nằm ở Khoản cha, tách khỏi hành vi vi phạm ở Điểm con.
- **Tìm kiếm lệch chủ đề.** "Vượt đèn đỏ" kéo về các điều về vượt xe. Câu gõ không dấu và từ lóng làm tìm theo vector kém hẳn.
- **Không biết hiệu lực và sửa đổi.** Điều khoản đã bị sửa vẫn được trích nguyên văn bản cũ, và không xét ngày xảy ra vi phạm.

## Câu hỏi nghiên cứu

- **CH1.** Biểu diễn văn bản quy phạm pháp luật tiếng Việt thành cây Điều–Khoản–Điểm, dựa trên quy ước soạn thảo văn bản thay vì quy tắc riêng cho từng văn bản, có giữ được đủ nội dung và quan hệ trích dẫn để phục vụ tra cứu không?
- **CH2.** Trên biểu diễn đó, cách tìm kiếm nào (theo vector, theo từ khoá BM25, kết hợp hai cách, thêm tìm theo cụm từ nguyên văn) tìm đúng điều khoản tốt nhất cho câu hỏi của người dùng, kể cả câu không dấu và câu khẩu ngữ?
- **CH3.** Để agent tự gọi công cụ tra cứu nhiều bước, thay vì tìm một lần rồi trả lời, có làm câu trả lời cuối đúng hơn không (đúng điều khoản, đúng mức phạt, từ chối đúng khi ngoài phạm vi)? Phải trả bao nhiêu thời gian và chi phí?

## Đóng góp chính

1. **Luồng nạp văn bản luật theo quy ước soạn thảo.**
   - Chuyển Word/PDF thành cây Điều–Khoản–Điểm.
   - Mọi dòng thuộc đúng một đoạn (chunk). Chữ trong ngoặc kép không bao giờ thành cấu trúc. Câu dẫn mức phạt đi kèm Điểm.
   - Liên kết trích dẫn ("điểm a khoản 9 Điều này") được giải trên cây phân tích, không đoán từ nhãn.
   - Không có quy tắc nào gọi tên một văn bản cụ thể.
2. **Tìm kiếm lai có xét hiệu lực và văn bản sửa đổi.**
   - Kết hợp tìm theo vector (Qwen3-Embedding) với BM25 trên âm tiết và cặp âm tiết không dấu, cộng thêm tìm theo cụm từ nguyên văn được xếp hạng theo câu hỏi.
   - Lọc theo ngày vi phạm.
   - Điều khoản đã bị sửa được gắn ghi chú: văn bản nào, câu lệnh nào sửa, từ ngày nào. Thông tin này đọc từ chính câu lệnh sửa đổi ở cấp Khoản và Điểm.
3. **Agent tra cứu nhiều bước và cách đánh giá hai tầng.**
   - Agent gọi công cụ qua giao thức MCP.
   - Bộ đánh giá tìm kiếm có 715 câu, tách tập dev (dùng khi phát triển) và holdout (chỉ dùng để kiểm tra cuối).
   - Bộ đánh giá câu trả lời có 81 câu theo lời hỏi của người dùng thật, chấm đúng điều khoản, đúng mức phạt và dữ kiện, số liệu bám nguồn, và từ chối đúng.
   - Quy trình chống "học tủ": không vá theo từng câu hỏi, có kiểm chứng độc lập.

## Phạm vi

- 14 văn bản về trật tự, an toàn giao thông đường bộ còn hiệu lực đến 10/2026: Luật, Nghị định 168/2024 và các văn bản sửa đổi, các Thông tư, QCVN 41:2024.
- Chỉ tra cứu và trả lời. Không tư vấn pháp lý, không xử lý trách nhiệm hình sự hay bồi thường dân sự.
