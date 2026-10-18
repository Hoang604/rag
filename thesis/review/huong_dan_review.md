# Hướng dẫn review bộ câu hỏi đánh giá (answers.jsonl)

Cảm ơn bạn đã giúp kiểm tra bộ đáp án. Bộ này gồm 81 câu hỏi về xử phạt và quy tắc giao thông đường bộ (71 câu trong phạm vi, 10 câu ngoài phạm vi). Hệ thống hỏi đáp được chấm theo các đáp án này, nên đáp án sai thì điểm của hệ thống cũng sai. Việc của bạn là xác nhận từng đáp án có đúng theo văn bản pháp luật hiện hành hay không.

File cần điền: `review_sheet.csv` (mở bằng Excel, tiếng Việt hiển thị đúng). Mỗi dòng là một câu hỏi.

## Các cột có sẵn

| Cột | Nội dung |
| :--- | :--- |
| `id` | mã câu (u… trong phạm vi, o… ngoài phạm vi) |
| `cau_hoi` | câu hỏi gốc của người dùng (có câu viết không dấu, sai chính tả, văn nói: giữ nguyên, đó là chủ đích) |
| `trong_pham_vi` | "Có" = hệ thống phải trả lời; "Không" = hệ thống phải từ chối |
| `dieu_khoan_ky_vong` | điều khoản được coi là căn cứ đúng, ví dụ "Điểm c Khoản 7 Điều 7 Nghị định 168/2024/NĐ-CP". Có nhiều dòng thì trích một trong số đó là đạt |
| `noi_dung_dieu_khoan` | toàn văn các điều khoản trên, lấy từ cơ sở dữ liệu. Với một Điểm, phần mở đầu của Khoản (nơi ghi mức phạt) được đặt trước, sau đó là "[...]" rồi đến Điểm |
| `ghi_chu_sua_doi` | điều khoản bị Nghị định 238/2026/NĐ-CP (hiệu lực 15/8/2026) hoặc văn bản khác sửa đổi, bổ sung, bỏ cụm từ; kèm lời văn của điều khoản sửa đổi |
| `so_tien_ky_vong` | các mốc tiền câu trả lời bắt buộc phải nêu |
| `du_kien_ky_vong` | các dữ kiện bắt buộc phải nêu (số điểm bị trừ, tốc độ, khoảng cách...); "A / B" nghĩa là viết A hoặc B đều được |
| `ghi_chu_nhan` | ghi chú của người soạn về nhãn đặc biệt |
| `nguon_cau_hoi` | trang gốc của câu hỏi, hoặc `paraphrase` nếu là câu diễn đạt lại |

## Cần kiểm tra gì

Với câu **trong phạm vi**:

1. **Đúng điều khoản không?** Hành vi trong câu hỏi có đúng là hành vi được mô tả ở điều khoản kỳ vọng không (đúng loại xe, đúng hành vi, đúng tình tiết như "gây tai nạn")? Có điều khoản nào khác phù hợp hơn hoặc cũng phải được chấp nhận không?
2. **Đúng số tiền không?** Mốc tiền trong `so_tien_ky_vong` có khớp với Khoản trong `noi_dung_dieu_khoan` không? Có thiếu mốc nào không (ví dụ câu hỏi cả ô tô và xe máy mà chỉ có mức của một loại xe)?
3. **Đúng dữ kiện không?** Số điểm trừ, tốc độ, thời hạn... có đúng không?
4. **Còn hiệu lực không?** Đọc `ghi_chu_sua_doi`: nếu điều khoản đã bị sửa, đáp án phải theo lời văn mới.
5. **Câu hỏi có trả lời được không?** Nếu câu hỏi mơ hồ đến mức có nhiều đáp án, hãy ghi rõ.

Với câu **ngoài phạm vi**: xác nhận câu đó thật sự không thể trả lời bằng các văn bản về xử phạt hành chính và quy tắc giao thông đường bộ (ví dụ: án tù hình sự, bồi thường dân sự, giá xe, luật nước ngoài). Nếu thực ra trả lời được bằng văn bản giao thông thì đánh "Sai".

Không cần kiểm tra cách trình bày, chính tả hay câu chữ của câu hỏi.

## Cách điền

| Cột | Điền gì |
| :--- | :--- |
| `dung_khong` | đúng một trong ba giá trị: **Đúng**, **Sai**, **Không chắc** |
| `dap_an_dung_neu_sai` | chỉ điền khi chọn Sai: điều khoản đúng (viết như "Điểm b Khoản 9 Điều 6 Nghị định 168/2024/NĐ-CP") và/hoặc số tiền, dữ kiện đúng |
| `ghi_chu` | lý do ngắn gọn, nhất là khi chọn Sai hoặc Không chắc; điều khoản nên chấp nhận thêm; nguồn bạn đã tra |

Ví dụ: câu hỏi về xe máy vượt đèn đỏ, kỳ vọng "Điểm c Khoản 7 Điều 7", số tiền 4.000.000 và 6.000.000 đồng → khớp lời văn → `dung_khong` = Đúng, hai cột còn lại để trống.

Chỉ sửa ba cột cuối, không sửa các cột khác. Khi lưu, chọn lại định dạng **CSV UTF-8** để giữ tiếng Việt.

## Thời gian

Khoảng **20 phút cho 10 câu**; cả bộ 81 câu mất khoảng 2,5–3 giờ, có thể chia nhiều lần. Câu ngoài phạm vi (o001–o010) nhanh hơn, chừng 1 phút mỗi câu. Ba câu u007, u008, u012 có điều khoản kỳ vọng là cả một Điều dài; chỉ cần tìm đúng Khoản trong Điều đó có mức phạt khớp với `so_tien_ky_vong`.
