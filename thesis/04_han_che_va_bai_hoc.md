# Hạn chế và bài học từ quá trình phát triển

Chương này ghi lại những chỗ hệ thống và cách đánh giá đã sai, cách phát hiện ra và cách sửa. Phần phân tích lỗi theo số liệu cuối nằm ở `05_phan_tich_loi.md`, viết sau khi có kết quả chạy đầy đủ.

## 1. Bộ đề sinh từ văn bản luật làm điểm cao hơn thực tế

- **Sai ở đâu:** các bộ đề ban đầu được sinh từ chính câu chữ của văn bản luật. Trên các bộ này, tìm kiếm đúng ở hạng 1 tới 79,5%.
- **Phát hiện thế nào:** soạn bộ 81 câu theo lời hỏi thật trên các trang hỏi đáp pháp luật, báo và diễn đàn. Cùng hệ thống chỉ đạt 49,3% ở hạng 1, và 27,3% với câu gõ không dấu.
- **Bài học:** đo bằng câu hỏi có từ ngữ giống văn bản là đo một việc người dùng không làm. Từ đó mọi kết luận đều phải kiểm trên bộ câu hỏi kiểu người dùng.

## 2. Mã "vá" theo bộ đề

- **Sai ở đâu:** giai đoạn đầu có các quy tắc định tuyến, danh sách từ khoá và ngưỡng được chỉnh để kéo điểm trên bộ đề.
- **Cách sửa:** gỡ hết. Đặt nguyên tắc: mọi thay đổi phải là cải tiến chung (tách từ, biểu diễn, cách gộp kết quả, truy vấn SQL), không viết luật cho câu hỏi cụ thể.
- **Cách kiểm soát:** tách tập dev và holdout, chỉ nhìn holdout khi kiểm tra cuối. Mỗi thay đổi có một agent độc lập review xem có chỉnh theo bộ đề không.
- **Phần còn lại cần nói thẳng:** hằng số RRF k = 20 được chọn bằng cách nhìn điểm trên tập dev. Điểm holdout không đổi khi đổi hằng số này.

## 3. Cải tiến bị mất khi gộp code

- **Sai ở đâu:** BM25 thay `ts_rank` (PR #8) đã được merge, nhưng một migration sau đó định nghĩa lại hàm tìm kiếm bằng `ts_rank`. Cải tiến mất mà không ai báo.
- **Phát hiện thế nào:** đọc trực tiếp hàm SQL đang chạy khi kết quả không khớp kỳ vọng.
- **Cách sửa:** PR #15 đưa BM25 trở lại.
- **Bài học:** cần một phép đo tự động chạy sau mỗi lần merge, để biết ngay khi chất lượng tụt.

## 4. Ghi chú văn bản sửa đổi sai cả hai chiều

- **Sai ở đâu:** bản đầu (PR #14) đọc tiêu đề điều sửa đổi. Tiêu đề kiểu "sửa đổi một số điểm, khoản của Điều 6" khiến mọi điểm của Điều 6 bị gắn ghi chú. Kết quả là khoảng 395/686 đoạn bị gắn sai, trong khi các lệnh bãi bỏ, thay thế cụm từ và sửa phụ lục lại bị bỏ sót.
- **Phát hiện thế nào:** kiểm lại sau khi luồng nạp được viết lại.
- **Cách sửa:** đọc từng câu lệnh sửa đổi ở cấp Khoản và Điểm bằng bộ phân tích trích dẫn (PR #16).
- **Bài học:** kiểm "có ghi chú hay không" là chưa đủ. Phải đếm cả ghi chú sai lẫn ghi chú thiếu.

## 5. Lỗi của chính bộ chấm

Ba lỗi đã gặp, đều làm sai kết quả mà không báo lỗi:

1. **Khớp đường dẫn theo tiền tố chuỗi.** Biển P.102 (`app_b.i_2`) bị tính là khớp với P.123 (`app_b.i_23`). Sửa thành khớp theo từng đoạn đường dẫn.
2. **Thông báo hết hạn mức bị tính là "từ chối đúng".** Khi tài khoản Claude hết hạn mức, câu trả lời là thông báo lỗi, và bộ chấm coi đó là từ chối đúng với câu ngoài phạm vi. Sửa thành ghi nhận là lỗi, không tính điểm.
3. **Máy chủ công cụ không kết nối bị tính là câu trả lời.** Agent khi đó trả lời "không tìm thấy căn cứ". Bộ chấm tính là sai với câu trong phạm vi, và là đúng với câu ngoài phạm vi. Sửa thành ghi nhận là lỗi.

**Bài học:** mọi bộ chấm phải được kiểm bằng cách đọc tay một mẫu câu trả lời, đối chiếu với từng phán quyết của nó.

## 6. Số liệu tự báo khác số liệu kiểm chứng

- Agent sửa tìm kiếm báo dev 545/592 cho một bước trung gian. Kiểm độc lập trên DB nạp mới cho 549/592. Agent đã đo bằng một script khác với đường chạy thật.
- Con số cuối (553/592) thì khớp.
- **Bài học:** chỉ báo con số đo bằng đúng lệnh đánh giá chính thức, trên DB nạp mới từ snapshot.

## 7. Hạn chế còn lại

- **Đáp án do một người soạn,** chưa được người có chuyên môn pháp lý duyệt. Có 3 câu nghi gán sai đáp án (e165, e537, e186) trong bộ tìm kiếm.
- **Kho văn bản nhỏ:** 14 văn bản. Biểu mẫu không được tách thành đoạn. Một số lỗi gõ trong văn bản nguồn làm mất cấu trúc 1–3 dòng.
- **Phụ thuộc mô hình thương mại:** câu trả lời cuối dùng Claude, mỗi câu tốn khoảng 0,15–0,29 USD và 35–45 giây. Chưa thử mô hình mở.
- **Chưa đánh giá với người dùng thật.**
- **Ghi chú sửa đổi chưa xử lý:** đích không đánh số ("bãi bỏ Phụ lục"), các cấp trên Điều, và trường hợp chính điều sửa đổi bị bãi bỏ về sau.
- **Tìm kiếm chưa từ chối câu ngoài phạm vi:** độ tin cậy gần như không bao giờ hạ, vì tiêu đề văn bản lặp lại trong mọi đoạn.
