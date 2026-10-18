# Phân tích lỗi

## 1. Câu trả lời cuối: 5 câu bị chấm sai

Mỗi câu được đọc tay và xếp vào một trong ba loại: lỗi hệ thống, lỗi bộ chấm, hoặc lỗi đáp án.

| Câu | Bộ chấm báo | Câu trả lời thực tế | Phân loại |
| :-- | :-- | :-- | :-- |
| u017 "bảng tốc độ tối đa ô tô trong và ngoài khu dân cư" | thiếu dữ kiện "90km" | Đúng và đủ: "60 km/h … 50 km/h", ngoài khu dân cư "90/80 km/h", "80/70", "70/60", "60/50", cao tốc 120 km/h | **Lỗi bộ chấm:** cách viết "90/80 km/h" không khớp mẫu "90km" |
| u045 "quên mang bằng lái nhưng có trên VNeID" | sai Điều | Trích Điều 48 NĐ 168: xuất trình qua tài khoản định danh điện tử trong thời hạn hẹn thì không bị phạt | **Lỗi đáp án:** đáp án chỉ ghi Điều 56 Luật TTATGT. Câu trả lời trích đúng căn cứ xử phạt, trả lời sát câu hỏi hơn |
| u070 "NĐ 100/2019 còn hiệu lực không" | sai Điều, số liệu không bám nguồn | Trích Điều 52 NĐ 168, điều sửa đổi và bãi bỏ NĐ 100; nêu đúng các Điều 5–11, 25–27… bị bãi bỏ | **Lỗi đáp án và bộ chấm:** đáp án ghi Điều 53/54. Bộ kiểm tra số liệu tưởng "Điều 5, 11…" là điều khoản không được trích, trong khi đó là số Điều của NĐ 100 xuất hiện ngay trong văn bản được trích |
| o002 "tai nạn chết người bồi thường bao nhiêu" | không từ chối | "Văn bản không nêu con số cụ thể … bồi thường theo pháp luật dân sự", có trích 2 điều | **Ranh giới định nghĩa:** trung thực và có ích, nhưng không phải từ chối trống |
| o004 "va quẹt trầy sơn đền bao nhiêu" | không từ chối | Tương tự o002 | Như trên |

Agent kiểm tra độc lập đọc lại cùng các câu này và đồng ý với cách phân loại, kèm ba chi tiết:
- **u045** thiếu một ý: theo Khoản 3 Điều 56 Luật TTATGT, có thể xuất trình qua VNeID ngay lúc bị kiểm tra.
- **u070** có một chỗ thật sự vượt nguồn: "Điều 25" nằm ở điểm i khoản 8 Điều 52, nhưng agent không trích điểm này.
- **o003** (đã bồi thường có bị xử lý hình sự không) được tính "từ chối đúng" chỉ vì câu trả lời tình cờ có cụm "không quy định". Thực ra agent trả lời có căn cứ từ Điểm b Khoản 1 Điều 83 Luật TTATGT, nên câu này nên được gán lại nhãn.

**Lỗi thật trong sản phẩm, không chỉ trong bộ chấm:** hàm kiểm tra số liệu (`check_grounding`) chỉ chấp nhận "Điều N" khi N là số Điều của điều khoản được trích. Nó bỏ qua các số Điều xuất hiện ngay trong văn bản được trích, như danh sách bãi bỏ hay tham chiếu. Trong khi đó, lời nhắc gửi agent khi bắt trả lời lại lại bảo "dùng số Điều có nguyên văn trong điều khoản trích". Hai bên mâu thuẫn nhau, nên câu trả lời đúng bị đánh dấu không bám nguồn và agent phải trả lời lại vô ích. 6/81 câu phải trả lời lại.

Nếu chấm tay, tỉ lệ đúng trong phạm vi là khoảng 70/71.

**Kết luận:**
- Không có câu nào trong phạm vi trích sai điều khoản, sai mức tiền hay bịa số liệu.
- Bộ chấm cần ba sửa đổi:
  1. hiểu cách viết gộp "90/80 km/h";
  2. không coi số Điều được nhắc trong chính văn bản đã trích là bịa;
  3. định nghĩa lại "từ chối đúng" cho câu ngoài phạm vi.
- Đáp án u045 và u070 cần mở rộng, chờ người học luật duyệt.

## 2. Tìm kiếm: các câu trượt trên tập dev

Trước khi sửa, có 54 câu trượt. Nguyên nhân gốc, phân tích trên tập dev:

| Nhóm nguyên nhân | Số câu | Ví dụ | Đã sửa bằng |
| :-- | --: | :-- | :-- |
| Tìm nguyên văn trả 10 kết quả đầu theo thứ tự văn bản | ~17 | "phục hồi điểm" khớp 1.413 đoạn vì có trong tên NĐ 168 | xếp theo vector câu hỏi |
| Gộp hai nhánh làm mất kết quả hạng 1–3 của một nhánh | ~15 | e308: hạng 2 theo vector, hạng 12 sau khi gộp | RRF k = 20 |
| Model embedding yếu, tiêu đề dài lặp ở mọi đoạn | ~9 | Điều 32 khoản 10 NĐ 168 ở hạng 742–880 theo vector | chưa sửa |
| Nhánh từ khoá không có IDF | ~6 | e075: hạng 1 theo vector, hạng 226 theo từ khoá | BM25 |
| Lời gọi tìm kiếm sai hoặc khoanh phạm vi sai | 3 | "đường nhánh" bị viết thành "đường cao tốc" | không thuộc tầng tìm kiếm |
| Nghi đáp án gán sai | 3 | e165, e537, e186 | chờ người duyệt |

Sau khi sửa còn 39 câu trượt. Đa số thuộc nhóm "model embedding yếu", với đáp án ở hạng 11–40. Có 7 câu trước đúng nay trượt, đáp án rơi xuống hạng 11–37. Hướng tiếp theo:
- giảm tiêu đề văn bản lặp lại trong ngữ cảnh của mỗi đoạn;
- thử model embedding lớn hơn;
- thêm bước xếp hạng lại (rerank).

## 3. Lỗi trong quá trình phát triển

Xem chương 4: bộ đề làm điểm cao giả tạo, cải tiến bị mất khi merge, ghi chú sửa đổi sai cả hai chiều, và ba lỗi của bộ chấm.
