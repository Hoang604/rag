# Kết quả thực nghiệm: agent và câu trả lời cuối (trả lời CH3)

## Thiết lập

- **Bộ đánh giá:** `data/eval/answers.jsonl`, gồm 81 câu soạn theo lời hỏi thật trên các trang hỏi đáp pháp luật, báo và diễn đàn.
  - 71 câu trong phạm vi: 36 khẩu ngữ, 15 trang trọng, 11 không dấu, 5 viết tắt, 4 nhiều bước.
  - 10 câu ngoài phạm vi: án tù, bồi thường dân sự, bảo hiểm, luật nước ngoài, giá xăng…
- **Đáp án:** gồm điều khoản đúng (đến Điểm), mức tiền và dữ kiện chính, tra tay trong văn bản. Đáp án chưa được người có chuyên môn pháp lý duyệt; bảng cho người duyệt nằm ở `review/`.
- **Hệ thống:** bản tích hợp (`main` + PR #15, #16, #17). Agent là Claude Code, chỉ được gọi các công cụ tra cứu qua MCP. Nếu câu trả lời chứa số liệu không có trong nguồn, agent được hỏi lại một lần.
- **Tiêu chí "đúng toàn phần"** cho câu trong phạm vi, phải đạt cả 5:
  1. có trích nguồn;
  2. trích đúng Điều;
  3. đủ mọi mức tiền yêu cầu;
  4. đủ mọi dữ kiện yêu cầu;
  5. mọi số tiền và số Điều trong câu trả lời đều có trong nguồn đã trích.
- **Câu ngoài phạm vi** được tính đúng khi agent không trích nguồn nào, hoặc nói rõ là không có căn cứ.

## Kết quả

Đã chấm đủ 81/81 câu (o009, o010 chạy bổ sung sau khi hạn mức được đặt lại).

| Chỉ số | Kết quả |
| :-- | --: |
| Đúng toàn phần (71 câu trong phạm vi) | 97,2% (69/71), 95,8% trước khi sửa bộ chấm |
| Trích đúng Điều | 97,2% |
| Trích đúng Khoản/Điểm | 97,2% |
| Đủ mức tiền và dữ kiện (69 câu có đáp án định lượng) | 100% sau khi sửa bộ chấm (98,6% trước) |
| Số liệu bám nguồn | 98,7% |
| Từ chối nhầm câu trong phạm vi | 0% |
| Từ chối đúng câu ngoài phạm vi | 80% (8/10) |
| Thời gian trung vị / chậm nhất | 36 giây / 105 giây |
| Chi phí | 12,84 USD, trung bình 0,159 USD/câu |

Theo kiểu câu hỏi:

| Kiểu | n | Đúng toàn phần |
| :-- | --: | --: |
| Khẩu ngữ | 36 | 100% |
| Không dấu | 11 | 100% |
| Trang trọng | 15 | 100% |
| Viết tắt | 5 | 80% |
| Nhiều bước | 4 | 75% |

## Lời gọi đầu tiên và agent nhiều bước

Câu hỏi của người dùng không bao giờ được đưa thẳng vào `search`: agent đọc câu hỏi rồi tự viết lời gọi (query bằng thuật ngữ luật, pattern nguyên văn) theo mô tả công cụ. Vì vậy phép so có ý nghĩa là giữa lời gọi đầu tiên agent viết và kết quả sau khi agent tra cứu nhiều bước, ghép cặp trên 40 câu holdout (`scripts/agent_eval.py`, `main`, 14/10):

| | Lời gọi đầu tiên | Agent nhiều bước |
| :-- | --: | --: |
| Điều khoản đáp án được tìm thấy hoặc trích | 95,0% | 92,5% |
| Câu sửa được / làm hỏng | -- | 1 / 2 |

Tra cứu thêm không làm tăng tỉ lệ tìm thấy. Lợi ích của các bước sau là đọc toàn văn Điều để lấy câu dẫn mức phạt, mở điều sửa đổi và tự kiểm tra số liệu, những thứ bộ đánh giá câu trả lời ở trên đo được.

## Nhận xét

- **Gần như mọi câu "sai" trong phạm vi đều do bộ chấm hoặc đáp án** (phân tích ở chương 5). Đọc lại, cả ba câu đều là câu trả lời đúng về nội dung. Bộ chấm đã được sửa để đọc đúng cách viết "90/80 km/h" (u017) và chấm lại bằng `--regrade`, không gọi lại agent: 97,2%. Hai câu còn lại (u045, u070) nhiều khả năng do đáp án quá hẹp, chờ người duyệt. Con số 97,2% vì vậy vẫn là cận dưới.
- **Điểm yếu thật nằm ở câu ngoài phạm vi về bồi thường dân sự.** Agent trả lời trung thực rằng văn bản không có con số và việc bồi thường theo pháp luật dân sự, nhưng vẫn trích điều khoản liên quan. Đây là chỗ cần định nghĩa rõ thế nào là "từ chối": trả lời "không có trong phạm vi, nhưng luật nói bồi thường theo pháp luật dân sự" có thể còn hữu ích hơn một lời từ chối trống.
- **Mẫu nhỏ:** 71 câu trong phạm vi, mỗi câu chạy một lần, một mô hình. Khoảng tin cậy của 97,2% còn rộng (khoảng 90–99% theo khoảng Wilson).
