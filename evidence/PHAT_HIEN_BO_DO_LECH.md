# Bộ đo cũ nói cao hơn thực tế 16 điểm

Đo lần đầu ngày 08/09/2026 trên `qrels_colloquial.jsonl` — 118 câu hỏi viết
theo cách người ta thật sự hỏi, **không sinh từ path corpus**.

Số liệu thô: [`colloquial118.txt`](colloquial118.txt) ·
[`lexicon_by_style.txt`](lexicon_by_style.txt)
Lệnh: `uv run python scripts/qa_bench.py tests/fixtures/qrels_colloquial.jsonl --rerank 10`

## Con số

| Tập | n | Hit@1 | Hit@3 | Hit@5 |
| :--- | ---: | ---: | ---: | ---: |
| Mẫu 2.000 câu sinh máy, có rerank | 1.980 | 86,4% | 94,0% | 95,1% |
| Tập niêm phong (sinh từ corpus) | 80 | 80,0% | 92,5% | 92,5% |
| **Câu khẩu ngữ** | **108** | **63,9%** | 85,2% | 90,7% |

Mức Điều, cấu hình đang chạy. Chênh **16,1 điểm** so với tập niêm phong và
**22,5 điểm** so với mẫu 2.000 câu.

Khoảng cách Hit@1 → Hit@5 rộng (63,9 → 90,7) nói rằng phần lớn cái sai là
**xếp hạng**, không phải không tìm được. Trên tập sinh từ corpus khoảng cách này
hẹp — tức hai tập đang bộc lộ hai loại lỗi khác nhau.

## Vì sao bộ đo cũ nói cao hơn

`qa_generate.py` viết câu hỏi **từ** chunk được lấy mẫu, nên câu hỏi thừa hưởng
từ vựng của chính văn bản luật. Điều đó gây ra hai điểm mù đã đo được:

**Một — lexicon gần như không được kiểm.** Trên 1.099 câu thuộc 20 phong cách,
phép mở rộng truy vấn chỉ **viết lại 7,2%** câu hỏi: 0,0% ở `gen_definition`,
1,7% ở `gen_rule`. Trong khi đó nó viết lại **5 trên 7** câu khẩu ngữ viết tay.
Các phong cách "khẩu ngữ" của bộ sinh (`p_typo`, `p_no_diacritics`,
`p_chat_abbrev`) là **ngụy trang máy móc** của từ vựng văn luật — sai chính tả,
bỏ dấu, viết tắt — chứ không phải cách gọi khác cho cùng một việc. Không có
khoảng cách từ vựng nào trong toàn bộ bộ đo để lexicon bắc cầu.

Hệ quả: con số **−2,0 điểm** mà `ablation.py` gán cho lexicon trên `qrels200`
**không đọc được thành "lexicon có hại"**. Nó là hình phạt dồn vào vài phần trăm
câu mà lexicon thực sự nổ, còn tác dụng thật của lexicon thì bộ đo chưa từng đo.

**Hai — facet loại xe cũng không được kiểm**, cùng một lý do. Câu hỏi sinh ra từ
một điều khoản hiếm khi nêu loại xe **xung đột** với nhãn của điều khoản đó. Đó
là vì sao 12.241 truy vấn bỏ qua lỗi nhãn `works_vehicle` trên điều khoản tốc độ
đường cao tốc, còn một câu hỏi bình thường bắt được ngay.

## Điều còn tệ hơn con số Hit@1

**Truy hồi bỏ sót ở độ sâu 10 nhiều hơn tưởng.** Trong 118 câu, gán nhãn ở độ
sâu 10 tìm được đáp án cho 98 câu. Gán lại ở **độ sâu 30** tìm thêm **10 câu**,
ở các hạng **1, 4, 5, 13, 14, 14, 16, 18, 24, 28** — tức phần lớn nằm ngoài
top-10 mà giao diện hiển thị.

Và những điều khoản đó **có thật, tìm được bằng grep nguyên văn**. Triage cả 20
câu ban đầu bị coi là "không có đáp án": **16/20 có điều khoản trong corpus**.
Ví dụ:

| Câu hỏi | Điều khoản có thật | Hạng khi tìm lại |
| :--- | :--- | ---: |
| từ chối kiểm tra nồng độ cồn | `168/2024` Điều 6 Khoản 11 Điểm b | 14 |
| không gạt chân chống | `168/2024` Điều 7 Khoản 9 Điểm a | 13 |
| dùng ma tuý khi lái xe | `168/2024` Điều 7 Khoản 9 Điểm e | 28 |
| đường đôi khác đường hai chiều thế nào | `QCVN41` Điều 3 Khoản 10 | 24 |

**Lớp từ chối trả lời im lặng 0/10 lần.** Với 10 câu mà ngay ở độ sâu 30 vẫn
không tìm được đáp án, hệ thống vẫn trả về kết quả trông tự tin. Ngưỡng −1,0
được chọn trên 25 câu **ngoài phạm vi** (hình sự, dân sự) — một loại câu dễ, vì
từ vựng của nó xa corpus. Câu **trong phạm vi nhưng corpus không có** là loại
khó hơn và thực tế hơn, và lớp từ chối chưa từng được hiệu chỉnh cho nó.

## Bộ này đo được gì và không đo được gì

**Được:** xếp hạng trên câu hỏi khẩu ngữ, trong độ sâu đã gán nhãn.

**Không được:**

- **Recall ngoài độ sâu gán nhãn.** Nhãn được chọn trong số ứng viên do chính hệ
  thống đề xuất, nên 10 câu còn lại có thể là corpus thiếu, mà cũng có thể là
  đáp án nằm sâu hơn 30.
- **Từ vựng của người lái xe thật.** Câu hỏi do agent viết nên mang từ vựng của
  agent. Yếu hơn một bộ do người viết, mạnh hơn một bộ sinh từ corpus.

## Chất lượng nhãn

Nhãn do CLI agent trên máy chọn trong số ứng viên được in ra, không phải "lấy
cái hệ thống xếp đầu". Judge không bao giờ được hỏi luật nói gì — nó được hỏi
điều khoản nào **trong số đã in** trả lời được câu hỏi, hoặc không có.

Soát tay mẫu ngẫu nhiên 10 nhãn (seed 20260908): **10/10 đúng**, mỗi điều khoản
trả lời trực tiếp câu hỏi của nó.

## Hệ quả với báo cáo

Con số nên trích khi cần một số duy nhất **vẫn là 80,0% trên tập niêm phong**,
nhưng phải kèm câu này: tập đó sinh từ corpus, và trên câu hỏi khẩu ngữ cùng
cấu hình chỉ đạt **63,9%**. Trích 80,0% mà không kèm là nói cao hơn thực tế.
