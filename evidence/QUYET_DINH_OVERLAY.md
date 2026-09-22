# Quyết định cổng Sprint 3 về overlay: REVERT

Cổng Sprint 3 đòi một quyết định PROMOTE hoặc REVERT **kèm số liệu**, và kế
hoạch ghi rõ REVERT kèm số liệu là đạt cổng. Đây là quyết định đó.

**Kết luận: REVERT.** Overlay đã cài đủ năm cơ chế, giữ nguyên trong code, và
**mặc định tắt**. Không xoá, vì bản thân nó không sai — nó chỉ chưa chạm được
tới xếp hạng ở lượng annotation hiện có.

Số liệu thô: [`overlay_eval.txt`](overlay_eval.txt).
Lệnh sinh lại: `uv run python scripts/overlay_eval.py --max-weights 0.05 0.10 0.25 --error-rates 0.0 0.6`

## Vì sao không phải "chưa đủ thời gian"

Lần đo đầu cho hai con số mà đọc riêng thì thành ra tốt: benefit **+2,5 điểm**
Hit@1 và damage **bằng 0** — bơm 60% annotation sai chấm điểm y như bơm 0% sai.
Hai số đó dễ bị đọc thành "overlay có lợi và an toàn".

Đọc như vậy là sai, và cách phân biệt là quét **trần trọng số** thay vì cố định
nó ở 0,10. Nên `OverlayBuilder.build()` được thêm tham số `max_weight`, và
`_score()` được thêm việc trả về danh sách hạng 1 để đếm số câu overlay **thực
sự đổi thứ hạng**.

| trần trọng số | 0% sai | 60% sai | đổi hạng 1 |
| ---: | ---: | ---: | ---: |
| tắt | 65,0 | — | — |
| 0,05 | 67,5 | 67,5 | **3/80** |
| 0,10 *(đang cài)* | 67,5 | 67,5 | **3/80** |
| 0,25 *(trần SQL cho phép)* | 68,8 | 67,5 | **4/80** |

Hit@1 mức Điều, n=80.

**Ở mọi trần, overlay chỉ đổi hạng 1 của 3–4 câu trên 80.** Kể cả ở 0,25 — tức
**2,5 lần** giá trị đang cài, và là trần cao nhất mà ràng buộc SQL
`chk_overlay_weight_bounds` cho phép.

Đó là lời giải thích cho cả hai con số: benefit +2,5 điểm **là 2 câu**, và damage
bằng 0 không phải vì overlay an toàn mà vì **cùng 3 câu đó đổi dù annotation
đúng hay sai**. Annotation sai trỏ vào những chunk không cạnh tranh được, nên
chúng không gây hại — và cũng không chứng minh được cơ chế bảo vệ nào hoạt động.

## Vì sao độ với là ràng buộc, không phải độ mạnh

Trọng số được áp theo **phép nhân**: `* (1.0 + overlay_boost(...))` trong
`019_search_doc_scope.sql`. Nên trần 0,25 nghĩa là ×1,25 — **mạnh hơn** hệ số
thưởng của facet loại xe (×1,12), thứ đã chứng minh được là đủ đảo thứ hạng.

Ràng buộc thật nằm ở chỗ khác: từ 40 annotation, build ra được **28 cặp trên 28
chủ đề** (6 bị guard chặn). Tập đánh giá có 80 câu, và `lookup_tokens` đòi tối
thiểu 2 token chủ đề cùng mức chồng lấn tối thiểu. Nên phần lớn câu hỏi **không
có chủ đề nào khớp để tra**, và trong số có khớp thì ×1,25 chỉ đủ vượt một đối
thủ đang dẫn dưới 25% điểm RRF.

Tức muốn overlay có ý nghĩa đo được thì cần **nhiều annotation hơn**, không phải
trọng số lớn hơn. Kế hoạch đã tính đúng điều này khi sizing Sprint 3 trên "~3
tháng annotation log từ Sprint 1"; log mới bắt đầu chạy.

## Hệ quả với hạng mục "learned relatedness" (8 ngày)

Kế hoạch gắn hạng mục này với điều kiện *"nếu overlay PROMOTE"*. Điều kiện đó
**không đạt**, và nay không đạt vì một phép đo chứ vì một phỏng đoán. Dựng
learned relatedness trên một cơ chế đã đo được là chạm tới 4% xếp hạng sẽ là xây
tầng hai trên một tầng một chưa đứng.

Đây là chỗ cần thầy quyết: giữ điều kiện của kế hoạch (không dựng), hay bỏ điều
kiện để dựng cho đủ phạm vi. Em nghiêng về giữ, và ghi rõ lý do trong báo cáo.

## Điều kiện để xem lại quyết định này

Ba điều kiện, mỗi điều kiện đo được:

1. **Annotation log thật đạt ~1.000 bản ghi** trên các chủ đề khác nhau, đủ để
   `build` sinh ra số cặp cùng cỡ với số câu hỏi thật.
2. **Số "đổi hạng 1" vượt 15%** tập đánh giá ở trần 0,10. Dưới mức đó, mọi
   chênh lệch Hit@1 đều nằm trong nhiễu của vài câu và không kết luận được.
3. **Damage khác 0** ở cấu hình 60% sai. Một cơ chế không gây hại được khi bị
   bơm annotation sai cũng chưa chứng minh được là nó có tác dụng khi đúng.

Điều kiện 3 quan trọng nhất và dễ bị bỏ qua: nó nói rằng **damage bằng 0 chưa
phải tin tốt** cho tới khi cơ chế chứng minh được là nó chạm tới xếp hạng.
