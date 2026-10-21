# Evaluation: gemini-3.5-flash-lite

Prompt: `shop-assistant-v3`. UTC: 2026-10-21T02:20:32.201211+00:00.

Kết quả: 11/11 case đạt các kiểm tra tự động.

Đây là kiểm tra workflow bằng rule/fixture khi provider=fake, không phải benchmark Gemini. Các case F dùng lỗi chèn chủ động, kể cả khi chọn Gemini.

Điểm 0/2 là proxy tự động cho rubric: intent, extraction, validation, routing, response. Cần người đọc chấm lại 0/1/2 để đánh giá chất lượng ngôn ngữ và groundedness đầy đủ.

| Case | Nhóm | Route thực tế | Intent | Extract | Validate | Route | Reply | Pass |
|---|---|---|---:|---:|---:|---:|---:|---|
| L01 | literal_spec | ask_missing | 2 | 2 | 2 | 2 | 2 | PASS |
| L02 | literal_spec | ask_missing | 2 | 2 | 2 | 2 | 2 | PASS |
| L03 | literal_spec | ask_missing | 2 | 2 | 2 | 2 | 2 | PASS |
| L04 | literal_spec | ask_missing | 2 | 2 | 2 | 2 | 2 | PASS |
| L05 | literal_spec | catalog_empty | 2 | 2 | 2 | 2 | 2 | PASS |
| L06 | literal_spec | handoff | 2 | 2 | 2 | 2 | 2 | PASS |
| L07 | literal_spec | ask_missing | 2 | 2 | 2 | 2 | 2 | PASS |
| U01 | update | order_updated | 2 | 2 | 2 | 2 | 2 | PASS |
| U02 | update | order_updated | 2 | 2 | 2 | 2 | 2 | PASS |
| U03 | update | ask_missing | 2 | 2 | 2 | 2 | 2 | PASS |
| F04 | format_api | failed_validation | 2 | 2 | 2 | 2 | 2 | PASS |
