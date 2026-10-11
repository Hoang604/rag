# Báo cáo đóng repo (2026-10-11)

## Tóm tắt một đoạn

Luồng nạp văn bản (file Word → text chuẩn → cây điều khoản → chunk → edge trích dẫn → PostgreSQL) đã được viết lại theo quy tắc soạn thảo chung, không theo từng văn bản. Nó chạy từ đầu đến cuối được, và khi gặp thứ không hiểu thì báo lỗi to chứ không làm mất chữ. Cả 14 văn bản đã ở trong DB. Bộ eval đã được chuyển sang path mới, mọi đáp án đều có thật trong DB. Kết quả: dev **90,5%**, holdout **94,3%**. Ba công cụ cho agent (`search`, `hierarchical_navigate`, `graph_traverse`) cho kết quả đúng khi kiểm tay.

## Trạng thái hiện tại

- **Corpus** (`data/sources`): 14 văn bản: 105, 108, 13/2025, 144, 151, 168, 171, 184, 236, 238, 38, 55, 65, QCVN 41. Các văn bản đã hết hiệu lực hoặc bị thay thế (100/2019, 12/2025, 49/VBHN, 90/VBHN) đã được xoá khỏi corpus và DB.
- **DB:** 14/14 văn bản, 6.775 chunk, 10.570 edge, tất cả có embedding (Qwen3-Embedding-0.6B, 512 chiều). Mọi edge đều do bộ giải trên cây parse sinh ra, vì DB đã được truncate trước khi nạp lại. Bảng dưới là 13 văn bản nạp trong đêm; QCVN 41 được nạp sau, bằng `finish.sh`.

  | Văn bản | Chunk | Edge | Dòng biểu mẫu không chunk |
  |---|---|---|---|
  | 105/2026/TT-BCA | 18 | 3 | |
  | 108/2026/TT-BCA | 936 | 1.984 | 879 |
  | 13/2025/TT-BCA | 124 | 0 | |
  | 144/2026/VBHN | 783 | 908 | |
  | 151/2024/NĐ-CP | 346 | 331 | 326 |
  | 168/2024/NĐ-CP | 1.253 | 3.588 | |
  | 171/2026/VBHN | 742 | 1.006 | |
  | 184/2025/NĐ-CP | 268 | 14 | |
  | 236/2026/NĐ-CP | 61 | 16 | 254 |
  | 238/2026/NĐ-CP | 68 | 0 | |
  | 38/2024/TT-BGTVT | 50 | 30 | |
  | 55/VBHN | 894 | 824 | |
  | 65/2024/TT-BCA | 69 | 24 | 56 |
  | QCVN 41 | 1.163 | 1.842 | |

- **Kiểm tra tĩnh:** `uv run ruff check --fix && uv run ty check` cho kết quả "All checks passed!" ở cả hai.

## Tốt ở đâu

1. **Không mất chữ trong im lặng.**
   - Chữ trong file Word mà extractor không đọc được làm `legal-convert` dừng, nêu tên file, cấu trúc và mẫu chữ. File gõ bằng font TCVN3/VNI cũng bị từ chối thẳng.
   - Khi chunk, dòng nào không thuộc chunk nào hoặc thuộc hai chunk thì ingest văn bản đó dừng.
   - Cả 13 văn bản đã nạp đều đạt kiểm tra này.
2. **Chữ trong ngoặc kép không bao giờ thành cấu trúc.** Văn bản sửa đổi không còn sinh ra "Điều 4" giả từ đoạn trích. Đã kiểm trên 13/2025: điều được trích vẫn nằm trong chữ của khoản sửa đổi.
3. **Câu dẫn mức phạt nằm trong chunk** (`…c_N.body`), nên "Phạt tiền từ … đến …" tìm và trích dẫn được.
4. **Edge trích dẫn tra trên cây parse**, không ghép path từ nhãn. Giải được Phụ lục, Chương, Mục, khoản thập phân kiểu QCVN, điểm chèn `a1` và range theo thứ tự thật. Trường hợp mơ hồ thì không tạo edge, chứ không đoán. Kiểm tay 45 hint ngẫu nhiên: cả 45 đều đúng.
5. **Không có luật nào gọi tên một văn bản cụ thể.** Mọi luật dựa trên quy ước soạn thảo (Luật Ban hành VBQPPL, NĐ 30, NĐ 34). Các luật viết ra sau khi nhìn corpus đã được gỡ: đóng khối chữ ký khi gặp một câu, đoán tiêu đề văn bản đính kèm từ dòng in hoa, bỏ ngoặc đơn cuối dòng khi xét tiêu đề phụ lục.
6. **Công cụ agent chạy đúng** (kiểm tay hôm nay):
   - `search` "vượt đèn xe mô tô" trả đúng Điều 7 khoản 7 điểm c của 168/2024, có câu dẫn mức phạt trong context.
   - `graph_traverse` từ "điểm a khoản 9 Điều này" trỏ đúng Điều 7 khoản 9 điểm a.
   - Hai path ví dụ trong mô tả tool (`registry.py`, `server.py`) đều có thật trong DB.

## Kém ở đâu (biết rõ, chấp nhận hoặc để lại)

1. **Embedding được tính bên trong transaction của DB.** Khi tính trên GPU 4 GB, một văn bản lớn giữ transaction mở nhiều phút. Nếu tiến trình chết giữa chừng thì văn bản đó rollback và phải nạp lại từ đầu. Đó chính là chuyện đã xảy ra với QCVN 41.
2. **Ingest không tự xoá văn bản đã rời khỏi `data/sources`.** Nó chỉ in cảnh báo. Lớp quyền của Claude Code đã chặn việc tự xoá, nên việc xoá do anh làm bằng tay.
3. **Khi re-ingest, edge cũ không được giải lại.** Hệ thống chỉ kiểm cụm trích dẫn còn nằm trong chunk hay không. Lần này không ảnh hưởng vì DB đã truncate. Nạp lại từng phần thì vẫn có thể còn edge cũ trỏ sai.
4. **Fan-out lớn.** Ví dụ "Chương II Nghị định này" ở 168/2024 sinh khoảng 930 edge, nên `graph_traverse` từ chunk đó trả rất nhiều kết quả. Về ngữ nghĩa thì đúng, chỉ nặng.
5. **Độ chính xác của edge chưa được đo lại** sau khi bộ giải chuyển lên cây parse (con số 99,5% cũ đã bị xoá). Ngoài 45 mẫu kiểm tay, chưa có phép đo nào.
6. **Văn bản sửa đổi** (13/2025, 238, 184, 236) gần như không có edge, vì "này" của chúng nằm trong đoạn trích. Đây là chủ ý.
7. **Biểu mẫu không được chunk** (đây là quyết định của anh). Số dòng bị bỏ được in trong báo cáo ingest.
8. **Dữ liệu "xấu" nhưng không sai:** nhãn `app_u1`, tiêu đề rỗng, chunk postamble lẫn rác, vài chỗ nguồn gõ sai làm mất cấu trúc 1–3 dòng (QCVN 41 "B3", "G1.1.").
9. **Chưa có audit độc lập** của lượt sửa này. Auditor bị dừng theo yêu cầu của anh trước khi có báo cáo.

## Kết quả eval

`uv run rag-eval legal-eval` trên bộ `data/eval/retrieval.jsonl` mới (715 câu):

| split | both | chỉ ngữ nghĩa | chỉ nguyên văn | trượt | tìm thấy |
|---|---|---|---|---|---|
| dev | 413 | 104 | 19 | 56 | **536/592 (90,5%)** |
| holdout | 96 | 16 | 4 | 7 | **116/123 (94,3%)** |

**Bộ eval đã được chuyển sang path mới như thế nào.** Sau khi viết lại parser, path của nhiều điều khoản thay đổi. Mỗi path đáp án không còn trong DB được thay bằng bước đầu tiên khớp, theo thứ tự:
1. **Nguyên văn** (82 path): chunk mới có lời văn trùng với chunk cũ.
2. **Số điều khoản** (77 path): node mới có cùng địa chỉ Điều/Khoản/Điểm, trong cùng văn bản hoặc trong văn bản hợp nhất thay thế (49/VBHN → 144, 90/VBHN → 171; văn bản hợp nhất giữ nguyên số điều của luật gốc).
3. Không khớp cách nào thì bỏ path đó. Câu không còn đáp án nào thì bỏ cả câu.

Không bước nào xem điểm số, và không lời gọi `search` nào bị sửa. Có 563 path vẫn còn nguyên. **41 câu bị bỏ** (756 → 715):
- 26 câu của 12/2025, văn bản đã hết hiệu lực và đã xoá;
- 8 câu của QCVN 41 Phụ lục G (nguồn gõ "G1.1." thiếu dấu chấm nên mục con không còn path riêng);
- 7 câu của 49/90 không tìm được điều cùng số duy nhất trong 144/171.

Bản gốc 756 câu được giữ ngoài repo.

**So với trước khi viết lại** (93,0% dev và 95,4% holdout, trên corpus và path cũ): dev giảm khoảng 2,5 điểm, holdout giảm khoảng 1 điểm. Hai lần đo không cùng tập câu nên không so trực tiếp được. Tôi không chỉnh gì để kéo số lên. 63 câu trượt là trượt thật, chưa ai phân tích nguyên nhân.

## Việc còn lại (không bắt buộc)

1. **Dọn `embedding_cache`**, bỏ vector của những text không còn chunk nào dùng:
   ```bash
   docker exec rag_legal_postgres psql -U postgres -d rag_legal -c "DELETE FROM embedding_cache e WHERE NOT EXISTS (SELECT 1 FROM chunks c WHERE encode(sha256(convert_to(c.contextualized_text,'UTF8')),'hex') = e.text_sha256);"
   ```
2. Đo độ chính xác edge, chạy một audit độc lập, xem 63 câu trượt.

## Đêm 2026-10-11 đã chạy thế nào

- 04:02: GPU rảnh, không có tiến trình nào giữ GPU. **Không kill tiến trình nào.**
- Ingest chạy **trên GPU**. Có 15 lần OOM, và embedder tự hạ batch rồi chạy tiếp như thiết kế. Không chuyển sang CPU, không dùng `--no-embed`.
- Khoảng 04:50, đang nạp QCVN 41 thì Claude Code dừng lệnh vì RAM hệ thống cạn (swap đầy do pyright, docling-serve và trình duyệt). Transaction của QCVN rollback sạch. Sau đó anh nạp lại văn bản này bằng `finish.sh`.

## Ước lượng tổng thể

Xét theo mục tiêu "chạy được, đúng, không gian lận" thì repo đạt khoảng **85%**. Luồng nạp, công cụ tra cứu và bộ eval đều dùng được. Phần thiếu là đo độ chính xác edge, audit độc lập, và vài giới hạn kiến trúc đã nêu ở trên.
