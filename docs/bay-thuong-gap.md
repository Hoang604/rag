# Những cái bẫy đã sập, và cách không sập lại

Mọi mục dưới đây là **lỗi có thật đã xảy ra trong dự án này**, không phải danh
sách mẹo chung chung. Mỗi mục ghi ba phần: **lỗi gì**, **vì sao không ai thấy**,
và **làm gì để lần sau nó tự lộ ra**.

Sắp theo mức nguy hiểm giảm dần. Nhóm 1 nguy hiểm nhất không phải vì khó sửa,
mà vì **nó làm mình tin vào một con số sai** — và mọi quyết định sau đó đều lệch.

---

## 1. Bẫy đo lường — nguy hiểm nhất

> Đặc điểm chung: chương trình **chạy thành công**, in ra một con số **đẹp**, và
> con số đó **sai**. Không có gì đỏ, không có gì báo lỗi.

### 1.1 Đo hai pha bằng cùng một bộ dữ liệu

**Lỗi.** Bộ đo độ trễ chạy pha đo tốc độ rồi pha đo thông lượng, nhưng **phát
lại đúng những truy vấn của pha trước**. Vô hại cho tới khi thêm bộ nhớ đệm —
sau đó nó báo **11,76 request/giây trong khi trần lý thuyết chỉ 7,5**.

**Vì sao không ai thấy.** Kết quả vẫn "hợp lý", chỉ là cao hơn. Không ai kiểm
tra một con số tốt.

**Cách tránh.** Chia dữ liệu thành **các lát cắt rời nhau** cho từng pha:
khởi động / đo độ trễ / đo thông lượng. Và **tính trần lý thuyết trước khi đo** —
nếu kết quả vượt trần thì phép đo sai, không phải hệ thống nhanh.

### 1.2 Đo một đường chạy với chính nó

**Lỗi.** Đo chi phí của vòng chấm lại, kết quả ra **0 mili giây**. Nguyên nhân:
lát cắt truy vấn dùng để gỡ lỗi rơi trúng cụm **câu không dấu**, mà hệ thống
**cố ý tắt chấm lại cho câu không dấu**. Tức là đang so một đường chạy với chính
nó.

**Vì sao không ai thấy.** "Tính năng này miễn phí" là một kết luận ai cũng muốn
tin.

**Cách tránh.** Bắt phép đo **tự chứng minh nó đang đo cái gì**. Cụ thể là thêm
một cột đếm số phản hồi **thật sự** đi qua nhánh đang đo:

```
chế độ          p50    req/s   đã chấm lại
không rerank    82      16,35        0/40
có rerank       87      15,33       40/40
```

Không có cột cuối thì hai dòng trên có thể là cùng một thứ.

### 1.3 Đo ở cấu hình không phải cấu hình sẽ chạy

**Lỗi.** Đánh giá một tính năng mới, baseline ra 46,3% trong khi số công bố là
63,9%. Nguyên nhân: **quên bật chấm lại**, mà hệ thống thật thì bật mặc định. Ở
cấu hình sai đó, tính năng **có vẻ giúp +1,8 điểm**. Đo lại đúng cấu hình: lợi
ích **bằng không**.

**Cách tránh.** Trước khi tin một phép so sánh, **đối chiếu baseline với con số
đã công bố**. Lệch là dấu hiệu đang đo nhầm cấu hình, không phải phát hiện mới.

### 1.4 Số cũ sống sót sau khi nguyên nhân đã biến mất

**Lỗi.** Mọi báo cáo ghi vòng chấm lại tốn **913 ms và mất 7 lần thông lượng**.
Một commit tối ưu inference làm con số thật rơi xuống **+5 ms và −6%**. Các báo
cáo vẫn giữ số cũ suốt nhiều ngày.

**Cách tránh.** Mỗi con số phải **truy được về một file bằng chứng hoặc một lệnh
chạy lại được**. Sau bất kỳ commit tối ưu nào, chạy lại **toàn bộ** số đo liên
quan, không chỉ số mình đang quan tâm.

### 1.5 Đo thời gian mô hình trong tiến trình nạp nhiều mô hình

**Lỗi.** Đo riêng thời gian của cross-encoder ra 780–1236 ms. Con số đó bị nhiễm
vì **hai mô hình cùng được nạp trong một tiến trình**.

**Cách tránh.** Đo qua **giao diện thật** (HTTP) trên tiến trình đã khởi động
xong, không đo bằng cách gọi hàm trong script vừa import mọi thứ.

---

## 2. Bẫy bộ đề chấm điểm

### 2.1 Bộ chấm âm thầm bỏ câu thay vì báo lỗi

**Lỗi.** `qa_bench.py` **bỏ qua** dòng có địa chỉ không còn tồn tại trong kho.
Cắt lại văn bản làm địa chỉ đổi → bộ 100 câu lặng lẽ còn 90 câu, mà tiêu đề vẫn
ghi 100.

**Cách tránh.** Một bài kiểm thử khẳng định **mọi địa chỉ trong mọi bộ đề vẫn
phân giải được** (`test_fixture_paths.py`). Nó đỏ ngay sau khi đổi bộ cắt, và
nêu tên từng địa chỉ đã dịch chuyển.

### 2.2 Nhãn tự viết cũng sai

**Lỗi.** Trong 28 câu hỏi mức Khoản/Điểm em tự viết, **6 nhãn sai**: 3 trỏ vào
đường dẫn không tồn tại, và 3 **sai về nghĩa** —
`a_6.c_4.p_d` là *không nhường đường cho xe xin vượt*, không phải xe cứu thương;
`a_26.c_2.p_b` là *chỗ ưu tiên cho người khuyết tật*, không phải làn xe buýt;
`a_7.c_9.p_a` là *kéo lê chân chống*, không phải lạng lách.

**Vì sao không ai thấy.** Ba cái sai về nghĩa **không có cách nào phát hiện tự
động** — đường dẫn tồn tại, hệ thống trả về đúng nó, mọi thứ xanh.

**Cách tránh.** **Đọc nguyên văn điều khoản mà mỗi đường dẫn trỏ tới.** Không có
đường tắt. Nhãn tự tin nhất là nhãn sai nguy hiểm nhất.

### 2.3 Câu hỏi sinh từ chính văn bản thì quá dễ

**Lỗi.** Bộ đề máy sinh cho **80%**, bộ câu hỏi viết theo lối người dân hỏi cho
**64%**. Chênh **16 điểm**, và toàn bộ báo cáo trước đó dùng con số 80%.

**Nguyên nhân.** Chương trình sinh câu hỏi lấy đề **từ chính đoạn văn bản**, nên
câu hỏi thừa hưởng từ vựng của luật. Bằng chứng: bộ mở rộng truy vấn chỉ kích
hoạt trên **7,2%** câu máy sinh nhưng **5/7** câu viết tay.

**Cách tránh.** Luôn có **ít nhất một bộ đề do người viết**, không nhìn vào văn
bản khi viết. Và khi trích số, **luôn trích kèm cả hai**.

### 2.4 Chấm ở sai đơn vị

**Lỗi.** Chấm "đúng Điều" cho câu hỏi mức phạt. Nhưng một Điều có hơn mười Khoản
với hơn mười mức phạt khác nhau. Cùng một bộ 27 câu: **88,9% đúng Điều nhưng chỉ
59,3% đúng Khoản**.

**Cách tránh.** Hỏi: **người dùng cần đến cấp nào mới trả lời được?** Chấm ở cấp
đó. Có cờ `--strict` để chấm mức Khoản/Điểm.

### 2.5 Đo sai đường đi — đo thứ người dùng không nhận

**Lỗi.** Bộ đo bảng chấm **kết quả thô** của khâu truy hồi. Nhưng lúc trả lời, hệ
thống còn **ghép các mảnh bảng** rồi mới đưa cho mô hình. Tức là đang chấm một
đường đi **không người dùng nào đi qua**.

Thêm cột đo đúng đường đi thì lộ ra: **việc ghép đang làm kết quả xấu đi** (60,0%
so với 63,3% thô) — một "cải tiến" làm hỏng 3 câu.

**Cách tránh.** Vẽ ra đường đi thật từ câu hỏi tới câu trả lời, rồi hỏi **bộ đo
đang cắt vào đoạn nào**. Báo cáo cả hai cột nếu cả hai đều có ý nghĩa.

---

## 3. Bẫy kiến trúc và giao diện

### 3.1 `@property` của Pydantic không được tuần tự hoá

**Lỗi.** `confidence` là `@property`, nên `model_dump()` **bỏ qua nó**. Ba tín
hiệu từ chối trả lời chạy trên mọi truy vấn và **chưa từng tới tay agent**.

**Cách tránh.** Dùng `@computed_field`. Và kiểm bằng cách **in `model_dump()`
ra xem**, đừng tin là trường có ở đó chỉ vì gọi `result.confidence` chạy được.

### 3.2 Phần cài đặt nhận tham số mà giao diện không lộ ra

**Lỗi.** `hybrid_search` nhận `doc_codes` và `rerank`; schema MCP **không lộ cái
nào**, trong khi giao diện web lộ cả hai. Agent có **ít quyền hơn con người**.

**Cách tránh.** Một bài kiểm thử đối chiếu **chữ ký hàm cài đặt** với **schema
giao diện**. Thêm tham số mà quên lộ ra thì đỏ.

### 3.3 Cùng một danh sách chép ba lần rồi lệch nhau

**Lỗi.** Danh sách loại văn bản (`Nghị định|Luật|Thông tư|…`) nằm ở **ba chỗ**
trong `xref.py`. Ba bản đã lệch: bản nhận "… này" **thiếu `Pháp lệnh`**, cả ba
**thiếu `Nghị quyết`** — khiến 4 trích dẫn có thật trong kho không phân giải
được mà **không báo lỗi**.

**Cách tránh.** Một nguồn duy nhất. Nếu là danh sách miền, đưa vào **file dữ
liệu**, không phải hằng số trong mã.

### 3.4 Danh mục tĩnh trong mã nguồn

**Lỗi.** Sáu loại xe, mười lăm cặp từ đồng nghĩa nằm thẳng trong `.py`. Nghị định
mới có loại xe mới → **phải sửa mã và triển khai lại**.

**Cách tránh.** Phân biệt **ngữ pháp văn bản** với **từ vựng lĩnh vực**:

| | Ví dụ | Ở đâu |
| :--- | :--- | :--- |
| **Ngữ pháp** — mọi văn bản đều dùng | `\[Điều\s+…\]`, `Khoản`, `Bảng` | Trong mã, hợp lệ |
| **Từ vựng** — sự thật về lĩnh vực lúc này | `xe tay ga`, `kẹp ba` | Phải là dữ liệu |

Bài kiểm thử `test_vocabulary_is_data.py` chốt ranh giới này.

### 3.5 Gộp dữ liệu bắt đầu từ đầu danh sách thay vì từ chỗ tìm được

**Lỗi.** Hàm ghép các mảnh của một điều khoản dài **nối từ mảnh thứ nhất** cho
tới khi đầy chỗ rồi cắt. Với một phụ lục mười mảnh mà bảng nằm ở mảnh thứ mười,
nó **đổ đầy bằng văn xuôi rồi cắt mất đúng mảnh đã được truy hồi**.

**Cách tránh.** Khi phải cắt bớt vì giới hạn kích thước, **lấy phần đã được chọn
làm tâm** rồi mở rộng ra hai bên, và **ghi rõ chỗ nào bị lược**.

### 3.6 `bool("false")` là `True`

**Lỗi.** Ép cờ jsonb bằng `bool(value)`. Đúng với mọi giá trị **trừ đúng cái
nguy hiểm**: chuỗi `"false"` là truthy.

**Cách tránh.** Viết hàm ép kiểu riêng và **có bài kiểm thử cho đúng chuỗi
`"false"`**.

### 3.7 Đường dẫn bắt-tất-cả của SPA nuốt luôn `/api/*`

**Lỗi.** Gõ sai một endpoint API thì nhận **HTTP 200 kèm trang HTML** thay vì
404. Chỉ xảy ra **khi đã build `frontend/dist`**, tức là chỉ ở môi trường thật.

**Cách tránh.** Cho đường dẫn bắt-tất-cả **trả 404 tường minh** cho tiền tố
`api/`. Và chạy kiểm thử đầu-cuối trên **bản đã build**, không chỉ bản dev.

---

## 4. Bẫy Windows / PowerShell

| Bẫy | Triệu chứng | Cách làm đúng |
| :--- | :--- | :--- |
| PowerShell 5.1 **không có `&&`** | `The token '&&' is not a valid statement separator` | Tách từng dòng lệnh |
| JSON trên dòng lệnh PS | Tham số rỗng, tool nhận `{}` | Nhân đôi nháy kép: `'{""query"":""…""}'` |
| In tiếng Việt ra pipe | `UnicodeEncodeError` | `$env:PYTHONIOENCODING="utf-8"`, và gọi `use_utf8_stdout()` trong script |
| `localhost` phân giải IPv6 trước | Trình duyệt báo không kết nối được, `curl` thì được | Dùng `127.0.0.1`, hoặc bind cả hai họ địa chỉ |
| Mở `http://0.0.0.0:8000` | `ERR_ADDRESS_INVALID` | `0.0.0.0` là địa chỉ **để bind**, không phải để gõ |
| Cổng trong dải 49152+ | `An attempt was made to access a socket in a way forbidden…` | Windows giữ chỗ cho Hyper-V và **đổi khối sau mỗi lần khởi động**. Dùng cổng dưới dải động (dự án này: `15432`) |
| Docker Desktop tắt giữa các phiên | Bài kiểm thử **bỏ qua thay vì đỏ**, thời gian chạy nhảy vọt | Kiểm `docker info` trước khi tin kết quả xanh |

### Bẫy heredoc — mất nhiều thời gian nhất

Viết mã Python **có ký tự thoát** qua heredoc của bash thì `\n` và dấu huyền bị
biến dạng. Đã dựng ra file `.py` hỏng cú pháp **ba lần** vì lỗi này:

```python
# Ý định:   split("\n")
# Thực tế:  split("
#           ")
```

**Cách tránh.** Bất cứ khi nào nội dung có ký tự thoát, **viết ra file bằng công
cụ ghi file rồi chạy file đó**, đừng nhồi qua heredoc.

---

## 5. Bẫy môi trường kiểm thử

### 5.1 Kiểm thử chạy trên cơ sở dữ liệu rỗng mà tưởng là kho thật

**Lỗi.** Bài kiểm thử địa chỉ bộ đề dùng `real_pg_pool` — vốn là **cơ sở dữ liệu
tạm, rỗng, dành cho kiểm thử migration**. Toàn bộ 15 assertion đỏ cùng lúc. Nhìn
như 15 bộ đề hỏng, thực ra là **một lựa chọn fixture sai**.

**Cách tránh.** Bài kiểm thử về **nội dung kho** phải nối vào **kho đã nạp**, và
**bỏ qua có kèm lý do** nếu không nối được — đừng bao giờ thay bằng bản giả.

### 5.2 Hai tên biến môi trường cho cùng một thứ

**Lỗi.** Bài kiểm thử đọc `LEGAL_DB_DSN`, cả hệ thống dùng `DATABASE_URL`. Trỏ
bộ kiểm thử sang cơ sở dữ liệu khác thì **riêng bài đó vẫn im lặng chạy trên
mặc định**.

**Cách tránh.** Một biến, một tên, dùng lại tên mà ứng dụng đã dùng.

### 5.3 Fixture do mình bịa ra không giống dữ liệu thật

**Lỗi.** Fixture kiểm thử bộ lọc rác website đặt phần rác chiếm **49%** văn bản,
trong khi thực tế là **1,6%–18,2%**. Hai bài kiểm thử đỏ **hoàn toàn đúng**, còn
fixture mới là cái sai.

**Cách tránh.** **Đo tỉ lệ thật trên dữ liệu thật rồi mới dựng fixture**, và
thêm một bài kiểm thử **ghim chính tỉ lệ của fixture**.

---

## 6. Ba câu hỏi nên tự hỏi trước khi tin một kết quả

1. **Phép đo này có tự chứng minh được nó đang đo cái gì không?**
   Nếu tắt tính năng đi mà con số không đổi, phép đo có nói cho mình biết không?

2. **Đây có phải cấu hình sẽ thực sự chạy không?**
   Baseline có khớp với con số đã công bố không?

3. **Con số này tốt hơn mình mong đợi bao nhiêu?**
   Càng đẹp càng phải nghi. Trong dự án này, **mọi con số đẹp bất ngờ đều hoá
   ra là lỗi đo lường**, không có ngoại lệ nào.
