# Kiểm thử theo đề Markdown — 21/10/2026

Nguồn yêu cầu: [AI_Live_Commerce_Order_Assistant_Mini_Project.md](../../../AI_Live_Commerce_Order_Assistant_Mini_Project.md) (file đề tại thư mục cha project), US-00–US-04, §9–12 và kịch bản demo §14.1. Các test dùng SQLite tạm khởi tạo từ cùng schema/seed với cửa hàng; không ghi đơn thử vào database đang phục vụ người dùng.

## Phạm vi và cách chạy

- 18 case gốc tại `tests/test_cases.json`, cộng 11 case tại `tests/spec_literal_cases.json`: tổng 29 case; một case có thể gồm nhiều lượt chat.
- Chế độ `gemini`, model cấu hình `gemini-3.5-flash-lite`, temperature 0, timeout 12 giây, retry 0, giãn cách tối thiểu 6 giây giữa thời điểm bắt đầu các lượt gọi model. Hạn mức ứng dụng 500 request/model/ngày theo cấu hình người dùng.
- Những lượt thông thường gọi Google thật qua adapter và đi qua FastAPI TestClient + business validation + SQLite thật. Đây là kiểm tra API tích hợp, không phải thao tác gõ từng câu trên trình duyệt.
- F01/F02/F03/F04 lần lượt chèn invalid JSON, timeout, empty response, rate limit; không gọi Google cho các lỗi này. S01 bị chặn bằng policy trước model. Bằng chứng ghi riêng `fault_injected`, `interpretation_source` và `provider_calls` từng case.
- Prompt ban đầu `shop-assistant-v2`; sau sửa là `shop-assistant-v3`, vẫn zero-shot. Không đưa nguyên câu kiểm thử vào few-shot. Bộ test được dùng để tìm lỗi và sửa nên không phải tập đánh giá độc lập.

## Đối chiếu yêu cầu

| Yêu cầu trong đề | Case / bằng chứng |
|---|---|
| §11.1: ít nhất 3 happy path | H01–H03: 1/multiple item, SKU và giá từ DB, tạo đơn nháp |
| Ít nhất 3 missing/ambiguous | M01–M05: thiếu giao nhận, thiếu biến thể, tham chiếu mơ hồ, bổ sung nhiều lượt |
| Ít nhất 2 inventory/catalog failure | I01–I03: hết hàng, vượt tồn, không có sản phẩm |
| Ít nhất 2 format/API failure | F01–F04: JSON hỏng, timeout, rỗng, rate limit; đều mô phỏng có chủ đích |
| Ít nhất 2 safety/adversarial | S01 nguyên câu injection §12.2; S02 sửa đơn không có reference |
| US-00: web dùng chung DB/API | `tests/test_backend_api.py`; `../frontend_smoke.json`: 10 bước qua 6 màn hình, Streamlit AppTest + HTTP API + SQLite tạm + FakeLLM |
| US-01: tạo đơn có validation | H01–H03, M01–M05; `tests/test_llm.py` kiểm tra tổng tiền DB, PII audit, idempotency |
| US-02: hỏi giá/tồn kho | Q01–Q02; `tests/test_catalog_chat.py` kiểm tra thay đổi giá/tồn DB có hiệu lực ở lượt hỏi sau |
| US-03: sửa đơn có kiểm soát | U01 sửa số lượng đơn duy nhất, U02 explicit reference + đổi size, U03 nhiều đơn phải hỏi lại; unit tests kiểm tra ownership, trạng thái khóa, rollback |
| US-04: mơ hồ/không an toàn/lỗi | L02/L06, S01–S02, F01–F04; không tạo đơn hoặc trừ kho khi thiếu căn cứ |
| Câu ví dụ nguyên văn trong đề | L01–L07: áo xanh, “em này”, hộp 500g, đen size L chưa có tên hàng, hỏi giá 500g, xử lý gấp, sửa đơn lúc nãy |
| §9.3, §12: quyền và dữ liệu | Unit tests: session hết hạn/thu hồi; chặn đọc/sửa đơn khác phiên; reject price/stock/status giả; quantity sai; audit không lưu PII thô |

Database mẫu không có áo thun xanh hoặc hộp 500g. Với những câu ví dụ này, kết quả đúng là hỏi lại/không có sản phẩm phù hợp; không tạo thêm hàng giả để làm test đạt. Các test kiểm tra tồn kho trước/sau không đổi và mọi đơn tạo ra giữ `pending_confirmation`.

## Hai lỗi tìm được và thay đổi

1. **M05 — bổ sung màu/size nhiều lượt.** Gemini v2 trích màu thành `màu đen`; matcher cũ so với `Đen` nên tiếp tục hỏi biến thể dù khách đã cung cấp. Baseline không tạo đơn, không có tác động sai. Sửa chuẩn hóa tiền tố nhãn màu/size trước khi đối chiếu DB, dùng chung cho tìm catalog và đặt hàng; bổ sung 2 unit regression tests. Prompt v3 hướng dẫn tách nhãn khỏi giá trị. Test màu không tồn tại vẫn phải hỏi lại, không tự đoán SKU.
2. **L06 — yêu cầu hỗ trợ gấp.** Gemini v2 phân loại thành `update_order`, confidence thấp và human review bật. Backend đã handoff an toàn nhưng sai tiêu chí intent (0/2); 4 tiêu chí còn lại đạt. Prompt v3 làm rõ update chỉ dùng cho yêu cầu thay đổi đơn hoặc bổ sung trường cập nhật; yêu cầu hỗ trợ/khẩn cấp không có nội dung thay đổi thuộc `unknown_or_handoff`.

Bằng chứng trước sửa giữ nguyên: [18 case baseline](baseline/evaluation_gemini.md), [11 case bổ sung baseline](literal_baseline/evaluation_gemini.md). Tổng baseline **27/29** (17/18 + 10/11). File JSON cùng thư mục lưu từng lượt và extraction đã che thông tin khách hàng.

## Kết quả sau sửa

**29/29 case PASS** sau sửa: [18/18 case chính](final/evaluation_gemini.md) và [11/11 case bổ sung](literal_final/evaluation_gemini.md), prompt `shop-assistant-v3`. M05 tạo đúng đơn nháp `TSH-BLK-M` số lượng 1 sau khi bổ sung giao nhận; L06 trả `unknown_or_handoff` và route `handoff`. U01/U02 sửa đúng số lượng/biến thể và tính lại tổng tiền từ DB; U03 hỏi mã đơn khi có nhiều đơn.

Lượt cuối dùng **27 generation request Gemini thật** (17 + 10), không retry. Tính cả baseline là **54 request** trong đợt kiểm thử này. Case có lỗi chèn hoặc policy chặn được ghi riêng, không tính là Gemini đã vượt qua lỗi phát sinh thật. Ledger sau kiểm thử là **55/500 attempt** cho model này trong ngày Pacific `2026-10-20` (bao gồm 1 lượt trước đợt test); đây là số ứng dụng ghi nhận, không phải quota còn lại do Google xác nhận.

Cả 29 case cuối giữ tồn kho không đổi. Report JSON cùng thư mục có thời gian UTC, metadata model, extraction đã che dữ liệu khách hàng, từng lượt, route và điểm proxy. Backend đang chạy bản sửa tại cổng 8000; frontend tại [http://127.0.0.1:8502/chat](http://127.0.0.1:8502/chat), health xác nhận `gemini-3.5-flash-lite`.

Kiểm tra local sau sửa: **150/150 PASS** (71 backend/frontend/LLM/quota + 79 database), chạy bằng `.venv/bin/python scripts/test_all.py`. UI integration chạy lại đạt **10/10 bước trên 6 màn hình** bằng `.venv/bin/python scripts/smoke_frontend.py`; không dùng kết quả FakeLLM này làm điểm Gemini.

SHA-256 nội dung bốn bảng products/product_variants/inventory/product_aliases của DB vận hành giữ nguyên trước/sau: `357a1ce32d5672a3e8256053861fbbd6d96288cc74766f74e83e91a7793c64e2`.

## Cách đọc điểm và giới hạn

Các file evaluation ghi đủ 5 cột rubric §11.2 nhưng dùng **proxy tự động 0/2**: intent, dữ liệu đơn/missing fields, invariant/schema và số đơn, route/error, reply không rỗng/chuỗi cần có. Điểm này không thay thế đánh giá ngữ nghĩa thủ công 0/1/2, và không có nghĩa độ chính xác Gemini là 100% ngoài bộ case hữu hạn này. Raw extraction được lưu để đọc lại; evidence bỏ khỏi log, trường giao nhận chỉ ghi có/không.

Không gây timeout/429 thật có chủ đích và không kiểm thử xâm nhập production. Bộ đếm ứng dụng không bao gồm lượt trước lúc cài ledger hoặc từ công cụ khác; quota thực xem tại AI Studio. Handoff hiện chỉ ghi nhận cần nhân viên hỗ trợ, chưa có hệ thống gửi tin cho nhân viên.
