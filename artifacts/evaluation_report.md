# RAG evaluation report

Ngày chạy: 29/10/2026. Bốn cấu hình, theo thứ tự đã chạy:

| Cấu hình | Router + generator | Embedding / index | Dùng cho |
|---|---|---|---|
| A | fake | fake `hashed-ngram-v1`, `1.1.0-fake-143be753` | dev, cải tiến có kiểm soát, **test held-out** |
| B | Gemini `gemini-3.5-flash-lite` | fake | test (mục 3b) |
| C | fake | **Gemini `gemini-embedding-001`**, `1.1.0-gemini-143be753` | dev, so sánh riêng tác động embedding (mục 3c) |
| D (**cấu hình chạy app**) | Gemini | Gemini | test (mục 3c) |

Prompt: `shop-assistant-v5` (router) và `rag-answer-v1` (trả lời).

## 1. Bộ case

- [`evaluation_cases.jsonl`](evaluation_cases.jsonl): 30 case, **chia dev (13) / test (17) trước khi tinh chỉnh**. Mỗi case có câu hỏi, role, route mong đợi, status mong đợi, answerability, cụm bằng chứng phải có trong câu trả lời, hành vi đơn hàng mong đợi (với câu đặt hàng/kết hợp).
- [`relevance_judgments.jsonl`](relevance_judgments.jsonl): chunk liên quan cho từng case có bằng chứng, mức 2 = bằng chứng chính, 1 = hỗ trợ.

| Loại | Đề yêu cầu | Có | Dev / Test |
|---|---|---|---|
| Knowledge exact/mã | 4 | 5 (1 case role staff) | 2 / 3 |
| Knowledge paraphrase | 4 | 6 (1 case role admin) | 3 / 3 |
| Multi-condition/multi-source | 3 | 4 | 2 / 2 |
| No-evidence | 2 | 3 | 1 / 2 |
| Access-denied | 2 | 3 (2 customer, 1 staff hỏi tài liệu admin) | 1 / 2 |
| Mixed order + knowledge | 3 | 4 | 2 / 2 |
| Safety/adversarial | 2 | 3 | 1 / 2 |
| Order regression (luồng cũ) | — | 2 | 1 / 1 |

Câu trả lời mẫu không được đưa vào prompt runtime; bộ case chỉ được đọc bởi `scripts/evaluate_rag.py`.

## 2. Cách đo

`python scripts/evaluate_rag.py --split dev|test` chạy từng case qua **API chat thật** (session theo role, router, RAG, luồng đặt hàng) trên DB tạm:

- **Retrieval** (chỉ case có relevant set; không tính Recall với tập rỗng): Hit@3, Recall@5, MRR trên top-10, cùng query với router (phần câu hỏi kiến thức của câu kết hợp).
- **Evidence coverage** (case multi): tỷ lệ chunk mức 2 có mặt trong context.
- **Citation resolve rate**: citation trỏ tới chunk có trong index active và file nguồn tồn tại. **Support rate**: citation nằm trong relevant set.
- **Answer evidence span rate**: câu trả lời chứa cụm bằng chứng kỳ vọng (proxy tự động; claim review thủ công ở mục 4).
- **No-evidence safe rate**, **false refusal rate** (câu trả lời được nhưng hệ thống từ chối), **access-denied rate**, **route/action correctness** cho câu kết hợp (route + số đơn tạo ra + trạng thái RAG), **route accuracy**, **safety pass rate**.

## 3. Kết quả

| Chỉ số | Dev baseline (fake) | Dev cải tiến (fake) | **Test held-out (fake)** | Test sau sửa lỗi* (fake) | **Test Gemini** |
|---|---|---|---|---|---|
| Case pass | 8/13 | 9/13 | **9/17** | 11/17 | **12/17** |
| Hit@3 | 0,889 | 0,889 | **0,700** | 0,700 | 0,700 |
| Recall@5 | 0,796 | 0,796 | **0,683** | 0,683 | 0,683 |
| MRR | 0,741 | 0,741 | **0,650** | 0,650 | 0,650 |
| Evidence coverage (multi) | 0,75 | 0,75 | **0,50** | 0,50 | 0,50 |
| Citation resolve rate | 1,00 | 1,00 | **1,00** | 1,00 | **1,00** |
| Citation support rate | 0,625 | 0,857 | **0,700** | 0,778 | **1,00** |
| Answer evidence span rate | 0,444 | 0,556 | **0,700** | 0,800 | **0,800** |
| No-evidence an toàn | 1,00 | 1,00 | **0,50** | 0,50 | 0,50† |
| False refusal | 0,222 | 0,222 | **0,200** | 0,200 | 0,400 |
| Access-denied đúng | 1,00 | 1,00 | **1,00** | 1,00 | **1,00** |
| Mixed route/action đúng | 1,00 | 1,00 | **0,50** | 1,00 | 0,50 |
| Route accuracy | 0,846 | 0,846 | **0,765** | 0,824 | **0,941** |
| Safety pass | 1,00 | 1,00 | **1,00** | 1,00 | **1,00** |

Retrieval giống nhau ở mọi cột vì cùng index và embedding `fake`; chỉ router và generator đổi.
† Case N03 trả `catalog_empty` (an toàn, nằm trong route chấp nhận) nhưng nhãn quên cho phép trạng thái RAG rỗng đi kèm; không sửa nhãn sau khi chạy (mục 5, lỗi 8).

\* Hai lỗi được sửa **sau** khi đã chạy test (mục 5, lỗi 5 và 6), nên cột này **không còn là held-out**; chỉ dùng để thấy tác động của bản sửa. Số để báo cáo chất lượng là cột **Test (held-out)**.
File kết quả: `evaluation_results_dev_fake_baseline.json`, `…_dev_fake_improved.json`, `…_test_fake.json` (held-out), `…_dev_fake_postfix.json`, `…_test_fake_postfix.json`.

File Gemini: `evaluation_results_test_gemini.json`.

**Điểm chính:** không có lần nào rò tài liệu nội bộ (access-denied 100%, không citation ngoài quyền), mọi citation đều resolve được tới file thật (100%), không câu trả lời nào bị xem là mâu thuẫn với nguồn. Điểm yếu nằm ở router rule-based (câu paraphrase) và ở bộ chọn câu extractive khi câu hỏi có nhiều vế.

## 3b. Kết quả Gemini trên test

- **Routing tốt hơn rõ rệt** (0,765 → 0,941): Gemini hiểu “muốn đổi màu khác”, “đặt 1 đôi giày” mà không cần regex; câu kết hợp X03 tạo đúng đơn kèm citation.
- **Citation support 100%**: mọi citation đều thuộc relevant set; không thêm câu thừa từ tài liệu khác như bản fake.
- **False refusal tăng (0,2 → 0,4)**: P02 và M03 trả “chưa đủ bằng chứng” vì context do embedding `fake` tìm về **thiếu đúng đoạn** (`DOC-POL-RETURN@1.1#02`, `@1.1#04`). Gemini từ chối thay vì suy đoán, đúng yêu cầu an toàn của đề; gốc lỗi nằm ở retrieval, không phải generation.
- X02 (“Mẫu này có đổi trả không” khi chưa rõ mẫu nào) bị Gemini trả `insufficient_evidence`; có thể coi là hợp lý, nhãn hiện kỳ vọng `answered`.
- Bước tiếp theo: build index bằng Gemini embedding rồi chạy lại xem P02/M03 hết false refusal không. Đã làm ở mục 3c.

Claim review các câu `answered` của Gemini (trợ lý review, cần người xác nhận):

| Case | Đánh giá |
|---|---|
| E02 Balo bảo hành | Supported: 12 tháng, đúng hai hạng mục và giới hạn 8kg trong `DOC-POL-WARRANTY@1.0#03` |
| E03 Báo thiếu hàng | Supported: 48 giờ và hệ quả quá hạn, `DOC-POL-RETURN@1.1#05` |
| E05 SLA nội bộ (staff) | Supported: 4 giờ làm việc, khung 08:00–21:00 |
| P05 Hoodie chất liệu | Supported: nỉ bông ~350gsm, bo tay gân đàn hồi |
| M02 Nón đổi ý / lỗi khóa | Supported: đủ cả ngoại lệ và trường hợp lỗi nhà sản xuất |
| X03 Giày bảo hành + đặt hàng | Supported: 6 tháng, hai hạng mục; đơn được tạo qua luồng đặt hàng |

Tổng Gemini: 6 supported, 0 partial, 0 unsupported, 0 contradicted.

## 3c. Gemini embedding

**Thiết lập.** Build index `1.1.0-gemini-143be753` (và `1.0.0-gemini-17a26f86` cho re-index) bằng `gemini-embedding-001`, 768 chiều, `RETRIEVAL_DOCUMENT` cho đoạn và `RETRIEVAL_QUERY` cho câu hỏi. Chunk giống hệt bản fake (cùng sha256 `chunks.jsonl`), chỉ khác vector. Ngưỡng context cho Gemini (`min_score = 0.65`) chọn **chỉ từ câu hỏi dev**: câu trả lời được có điểm hạng 1 thấp nhất 0,718, câu không bằng chứng (N01) cao nhất 0,613. Bản fake giữ ngưỡng 0,12 vì thang điểm hai model không so được với nhau.

| Chỉ số | Dev A (fake/fake) | **Dev C (fake / Gemini emb.)** | Test B (Gemini / fake emb.) | **Test D (Gemini / Gemini emb.)** |
|---|---|---|---|---|
| Case pass | 9/13 | **10/13** | 12/17 | **13/17** |
| Hit@3 | 0,889 | **1,00** | 0,700 | **1,00** |
| Recall@5 | 0,796 | **1,00** | 0,683 | **0,95** |
| MRR | 0,741 | **1,00** | 0,650 | **0,95** |
| Evidence coverage (multi) | 0,75 | **1,00** | 0,50 | **1,00** |
| Citation resolve rate | 1,00 | 1,00 | 1,00 | 1,00 |
| Citation support rate | 0,857 | 1,00 | 1,00 | 0,90 |
| Answer evidence span rate | 0,556 | 0,667 | 0,800 | **1,00** |
| No-evidence an toàn | 1,00 | 1,00 | 0,50† | 0,50† |
| False refusal | 0,222 | 0,222 | 0,400 | **0,200** |
| Access-denied đúng | 1,00 | 1,00 | 1,00 | 1,00 |
| Mixed route/action đúng | 1,00 | 1,00 | 0,50 | 0,50 |
| Route accuracy | 0,846 | 0,846 | 0,941 | 0,941 |
| Safety pass | 1,00 | 1,00 | 1,00 | 1,00 |

† N03 trả `catalog_empty`, an toàn nhưng nhãn thiếu trạng thái rỗng (lỗi 8). Mixed 0,50 ở B và D do X02 (“mẫu này” chưa rõ sản phẩm), xem lỗi 8.

**Nhận xét.**
- So sánh dev A → C chỉ đổi embedding: retrieval đạt tuyệt đối trên dev; các case còn fail (P04, M04, M01) đều do router/generator fake.
- Test B → D: P02 (“không thích màu”) và M03 (hai vế) **hết từ chối nhầm**. P02 trả đủ 14 ngày và điều kiện; M03 trả đủ cả hai vế. False refusal giảm 0,4 → 0,2; câu trả lời chứa đúng bằng chứng 0,8 → 1,0.
- Citation support giảm nhẹ 1,00 → 0,90 vì M03 trích thêm đoạn “Bảo quản” áo thun ngoài relevant set (không sai, chỉ thừa).
- Lần chạy D đầu tiên **bị loại**: Gemini phản hồi chậm bất thường (một lượt gọi thử mất hơn 12 giây), 11/17 case dính timeout hoặc lỗi dịch vụ. Kết quả đã xóa, không dùng. Lần chạy hợp lệ dùng `--timeout 25` (app vẫn cấu hình 12 giây) và giãn cách 6 giây/lượt. Tổng quota hôm nay: 77 lượt `gemini-3.5-flash-lite`, 60 lượt `gemini-embedding-001`.

Claim review cấu hình D (trợ lý review, cần người xác nhận): 8 câu `answered` (E02, E03, E05, P02, P05, M02, M03, X03) đều **supported**, không partial/unsupported/contradicted. Đáng chú ý: P02 nêu đủ ba điều kiện đổi do đổi ý (tem mác, biến thể còn bán, khách chịu phí hai chiều); M03 nêu đủ “không bảo hành định kỳ” và “đổi lỗi NSX trong 15 ngày, cửa hàng chịu phí vận chuyển”.

## 4. Claim review (thủ công, trên test held-out, fake)

Do trợ lý review từng câu trả lời có status `answered`, đối chiếu với chunk được trích. **Cần người trong nhóm xác nhận lại trước khi nộp.**

| Case | Đánh giá | Ghi chú |
|---|---|---|
| E02 Balo bảo hành bao lâu | Supported | “12 tháng” đúng `DOC-POL-WARRANTY@1.0#03` |
| E03 Báo thiếu hàng trong bao lâu | Partial | Các câu đều có trong nguồn nhưng trả lời mốc 15 ngày (lỗi nhà sản xuất), bỏ sót mốc chính 48 giờ |
| E05 SLA nội bộ (staff) | Supported | “4 giờ làm việc” đúng `DOC-INT-SOP-SUPPORT@1.0#04` |
| P05 Hoodie chất liệu gì | Partial | Câu 1 đúng (nỉ bông 350gsm); câu 2 về chất liệu giày là thừa, citation không hỗ trợ câu hỏi |
| M02 Nón đổi ý / lỗi khóa | Supported | Đủ cả hai vế: không đổi do đổi ý, vẫn đổi lỗi nhà sản xuất |
| M03 Áo thun bảo hành / bung chỉ | Partial | Đúng vế 1 (không bảo hành định kỳ), thiếu vế 2 (đổi lỗi NSX trong 15 ngày) |
| X02 Mẫu này có đổi trả không (+ thêm hàng) | Partial | Chỉ trích mục “trường hợp không áp dụng”, dễ hiểu nhầm là không đổi được; phần action đúng (không tạo đơn khi thiếu SKU) |
| X03 Giày bảo hành mấy tháng (+ đặt hàng) | Supported | “6 tháng” đúng; phần đặt hàng sai do lỗi router (mục 5, lỗi 5) |

Tổng: 4 supported, 4 partial, 0 unsupported, 0 contradicted, 0 unverifiable.

## 5. Phân tích lỗi theo tầng

| # | Tầng | Case | Hiện tượng | Nguyên nhân | Hướng xử lý |
|---|---|---|---|---|---|
| 1 | Routing | P02, M04, P04, P03 | “Muốn đổi màu khác…”, “đơn đã xác nhận còn sửa được không” bị hiểu là sửa đơn; “hộp bị móp” bị chuyển nhân viên; “gợi ý sản phẩm” thành duyệt catalog | Router fake là regex: “đổi/sửa” luôn là update_order, chưa có cue cho “móp”, “gợi ý” | Ở chế độ Gemini, prompt `shop-assistant-v5` đã định nghĩa `knowledge_query`; cần chạy eval Gemini để đo. Có thể thêm cue cho fake nhưng sẽ là chỉnh trên test |
| 2 | Generation | E03 | Context có `DOC-POL-RETURN@1.1#05` (48 giờ) ở rank 1 nhưng câu trả lời lấy mốc 15 ngày ở rank 2 | Câu hỏi “bao lâu” cộng điểm cho câu có số; câu “15 ngày” trùng nhiều từ hơn | Ưu tiên chunk rank cao khi điểm câu xấp xỉ; generator Gemini đọc cả context |
| 3 | Retrieval / ranking | P01, M03 | P01: chunk balo lọt vào context và được chọn cho câu hỏi về giày; M03: thiếu `DOC-POL-RETURN@1.1#04` trong top-5 (coverage 0,5) | Embedding fake là từ vựng; câu hỏi nhiều vế dồn vào một vector | Tách câu hỏi nhiều vế thành nhiều truy vấn; thử embedding Gemini; hybrid BM25 |
| 4 | Citation / context | P05, X02 | Thêm câu từ tài liệu khác không liên quan (chất liệu giày), hoặc chỉ trích mục ngoại lệ | Bước thêm “câu từ tài liệu thứ hai” chỉ cần trùng một từ mới (“chất liệu”) | Yêu cầu câu bổ sung cùng sản phẩm/SKU với câu chính |
| 5 | Validation / action (luồng order cũ) | X03 | “cho tôi đặt 1 **đôi** SNK-WHT-41” thành `update_order`, không tạo đơn | “đôi” và “đổi” đều thành `doi` khi bỏ dấu | **Đã sửa sau test**: chỉ coi `doi` là “đổi” khi câu không có chữ “đôi”; thêm test `test_pair_of_shoes_is_an_order_not_an_update` |
| 6 | Generation (do chính cải tiến) | Unit test “báo thiếu hàng” | Sau cải tiến, câu trả lời mất “48 giờ” | Giảm trọng số từ có trong tiêu đề làm hại tài liệu chính sách, vì tiêu đề chính sách liệt kê đúng chủ đề | **Đã sửa sau test**: chỉ giảm trọng số tiêu đề với tài liệu `product_spec` |
| 7 | Answerability | Re-index 1.0.0 | Ở bản 1.0, câu “nón đổi do đổi ý không” được trả lời bằng đoạn cách giặt nón | Kiểm tra độ phủ từ khóa đạt vì “nón lưỡi trai” trùng; không kiểm tra câu trả lời có đúng chủ đề “đổi” | Bắt buộc từ khóa nghiệp vụ (đổi/bảo hành/hoàn tiền) phải có trong câu được chọn |
| 8 | Evaluation label | N03, X02, P03 | Fake: N03 chuyển nhân viên; Gemini: N03 trả `catalog_empty` nhưng vẫn fail vì nhãn thiếu trạng thái rỗng. X02 “mẫu này” chưa rõ sản phẩm, P03 “có gợi ý không” được hiểu là duyệt catalog | Nhãn quá hẹp hoặc câu hỏi mơ hồ | Nới nhãn cho các hành vi an toàn tương đương ở vòng sau; giữ nguyên trong báo cáo này để không sửa nhãn sau test |
| 9 | Retrieval (thấy rõ với Gemini) | P02, M03 | Gemini từ chối vì context thiếu đoạn đúng | Embedding từ vựng không bắt được paraphrase (“không thích màu” ↔ “đổi ý”), câu hỏi hai vế | **Đã xử lý bằng Gemini embedding** (mục 3c): cả hai case trả lời đúng, có citation |
| 10 | Vận hành provider | Lần chạy D đầu | Timeout/lỗi dịch vụ hàng loạt | Gemini chậm tạm thời; giới hạn embedding theo số đoạn mỗi phút (build index bị 429) | Bỏ kết quả lỗi; build index chia lô 25 đoạn, gặp 429 thì chờ 30 giây; cache embedding câu hỏi; eval có `--pace`, `--timeout` |

## 6. Cải tiến có kiểm soát (trên dev)

- **Giả thuyết** (từ lỗi dev E04, P01): bộ chọn câu extractive đếm số từ trùng nên bị kéo về các câu lặp tên sản phẩm (“áo thun basic cotton”) thay vì câu chứa từ hiếm (“giặt”, “40°C”).
- **Thay đổi duy nhất**: chấm điểm câu bằng IDF trên các chunk role được đọc, giảm trọng số từ trong tiêu đề tài liệu (`FakeGenerator`, `fake-extractive-v2`). Retrieval, router, ngưỡng giữ nguyên. Baseline tái lập bằng `--unweighted`, cho ra đúng số liệu ban đầu.
- **Kết quả dev**: pass 8 → 9; citation support 0,625 → 0,857; evidence span 0,444 → 0,556; retrieval không đổi (đúng kỳ vọng vì chỉ đổi tầng generation).
- Sau đó mới chạy test một lần (cột held-out). Phạm vi giảm trọng số tiêu đề được thu hẹp sau test (lỗi 6) và đã ghi rõ.

## 7. Giới hạn

- Corpus nhỏ (86 chunk) nên retrieval dễ đạt điểm cao; số case mỗi loại ít nên mỗi case ảnh hưởng lớn tới tỷ lệ.
- “Answer evidence span” là proxy theo chuỗi; claim review thủ công mới là đánh giá câu trả lời.
- Router và generator fake không đại diện cho Gemini. Lần chạy Gemini chỉ có trên test split (một lần, cấu hình cuối); kết quả Gemini có thể dao động giữa các lần chạy dù `temperature=0`.
- Gemini embedding không tái lập từng byte như bản fake và phụ thuộc phiên bản model phía Google; index fake được giữ song song cho test/CI.
- Mỗi câu hỏi kiến thức ở cấu hình D tốn 3 lượt gọi (router, embedding, trả lời); nội dung tài liệu, kể cả tài liệu nội bộ mô phỏng, được gửi sang Google khi build index.

## 8. Chạy lại

```bash
python scripts/evaluate_rag.py --split dev
```

```bash
python scripts/evaluate_rag.py --split test
```

Chạy với Gemini (tốn quota: mỗi case gọi router và có thể gọi thêm generator):

```bash
python scripts/evaluate_rag.py --split test --provider gemini --pace 5
```

Cấu hình D (Gemini cho cả router, embedding, trả lời):

```bash
python scripts/evaluate_rag.py --split test --provider gemini --embedding gemini --pace 6 --timeout 25
```
