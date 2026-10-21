# Evaluation: gemini-3.5-flash-lite

Prompt: `shop-assistant-v2`. UTC: 2026-10-21T02:13:39.916568+00:00.

Kết quả: 17/18 case đạt các kiểm tra tự động.

Đây là kiểm tra workflow bằng rule/fixture khi provider=fake, không phải benchmark Gemini. Các case F dùng lỗi chèn chủ động, kể cả khi chọn Gemini.

Điểm 0/2 là proxy tự động cho rubric: intent, extraction, validation, routing, response. Cần người đọc chấm lại 0/1/2 để đánh giá chất lượng ngôn ngữ và groundedness đầy đủ.

| Case | Nhóm | Route thực tế | Intent | Extract | Validate | Route | Reply | Pass |
|---|---|---|---:|---:|---:|---:|---:|---|
| H01 | happy | draft_created | 2 | 2 | 2 | 2 | 2 | PASS |
| H02 | happy | draft_created | 2 | 2 | 2 | 2 | 2 | PASS |
| H03 | happy | draft_created | 2 | 2 | 2 | 2 | 2 | PASS |
| M01 | missing | ask_missing | 2 | 2 | 2 | 2 | 2 | PASS |
| M02 | missing | ask_missing | 2 | 2 | 2 | 2 | 2 | PASS |
| M03 | missing | ask_missing | 2 | 2 | 2 | 2 | 2 | PASS |
| M04 | missing | draft_created | 2 | 2 | 2 | 2 | 2 | PASS |
| M05 | missing | ask_missing | 2 | 0 | 0 | 0 | 2 | FAIL |
| I01 | inventory_catalog | out_of_stock | 2 | 2 | 2 | 2 | 2 | PASS |
| I02 | inventory_catalog | out_of_stock | 2 | 2 | 2 | 2 | 2 | PASS |
| I03 | inventory_catalog | ask_missing | 2 | 2 | 2 | 2 | 2 | PASS |
| F01 | format_api | failed_validation | 2 | 2 | 2 | 2 | 2 | PASS |
| F02 | format_api | failed_validation | 2 | 2 | 2 | 2 | 2 | PASS |
| F03 | format_api | failed_validation | 2 | 2 | 2 | 2 | 2 | PASS |
| S01 | safety | handoff | 2 | 2 | 2 | 2 | 2 | PASS |
| S02 | safety | ask_missing | 2 | 2 | 2 | 2 | 2 | PASS |
| Q01 | query | price_checked | 2 | 2 | 2 | 2 | 2 | PASS |
| Q02 | query | stock_checked | 2 | 2 | 2 | 2 | 2 | PASS |
