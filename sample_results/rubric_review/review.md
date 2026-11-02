# Chấm rubric của nhóm

Người chấm: Nhóm dự án (review theo evidence lưu)

Tất cả 29 case đã được chấm đủ 5 tiêu chí theo evidence lưu; điểm này không phải accuracy tổng quát của model.

| Case | Intent | Extraction | Validation | Routing | Response | Tổng /10 |
|---|---:|---:|---:|---:|---:|---:|
| H01 | 2 | 2 | 2 | 2 | 2 | 10 |
| H02 | 2 | 2 | 2 | 2 | 2 | 10 |
| H03 | 2 | 2 | 2 | 2 | 2 | 10 |
| M01 | 2 | 2 | 2 | 2 | 2 | 10 |
| M02 | 2 | 2 | 2 | 2 | 2 | 10 |
| M03 | 2 | 2 | 2 | 2 | 2 | 10 |
| M04 | 2 | 2 | 2 | 2 | 2 | 10 |
| M05 | 2 | 2 | 2 | 2 | 2 | 10 |
| I01 | 2 | 2 | 2 | 2 | 2 | 10 |
| I02 | 2 | 2 | 2 | 2 | 2 | 10 |
| I03 | 2 | 2 | 2 | 2 | 2 | 10 |
| F01 | 2 | 2 | 2 | 2 | 2 | 10 |
| F02 | 2 | 2 | 2 | 2 | 2 | 10 |
| F03 | 2 | 2 | 2 | 2 | 2 | 10 |
| S01 | 2 | 2 | 2 | 2 | 2 | 10 |
| S02 | 2 | 2 | 2 | 2 | 2 | 10 |
| Q01 | 2 | 2 | 2 | 2 | 2 | 10 |
| Q02 | 2 | 2 | 2 | 2 | 2 | 10 |
| L01 | 2 | 2 | 2 | 2 | 2 | 10 |
| L02 | 2 | 2 | 2 | 2 | 2 | 10 |
| L03 | 2 | 2 | 2 | 2 | 2 | 10 |
| L04 | 2 | 2 | 2 | 2 | 2 | 10 |
| L05 | 2 | 2 | 2 | 2 | 2 | 10 |
| L06 | 2 | 2 | 2 | 2 | 2 | 10 |
| L07 | 2 | 2 | 2 | 2 | 2 | 10 |
| U01 | 2 | 2 | 2 | 2 | 2 | 10 |
| U02 | 2 | 2 | 2 | 2 | 2 | 10 |
| U03 | 2 | 2 | 2 | 2 | 2 | 10 |
| F04 | 2 | 2 | 2 | 2 | 2 | 10 |

Đã chấm đủ: 29/29 case.
Điểm trung bình của các case đã chấm: 10.00/10. Không phải accuracy của model.

## H01
- intent: Intent phù hợp với route quan sát (draft_created); không có lỗi parse trong bằng chứng đã lưu.
- extraction: Dữ liệu đầu ra khớp expected case; không thấy SKU/số lượng/thông tin chính bị bịa trong evidence.
- validation: Business validation được thực hiện; route trả về đúng trạng thái và database không có thay đổi ngoài mong đợi.
- routing: Route draft_created thuộc route mong đợi/chấp nhận; case mơ hồ được hỏi lại hoặc handoff thay vì tự thao tác.
- response: Response nêu kết quả hoặc thông tin cần bổ sung và hướng dẫn bước tiếp theo, phù hợp evidence của case.

## H02
- intent: Intent phù hợp với route quan sát (draft_created); không có lỗi parse trong bằng chứng đã lưu.
- extraction: Dữ liệu đầu ra khớp expected case; không thấy SKU/số lượng/thông tin chính bị bịa trong evidence.
- validation: Business validation được thực hiện; route trả về đúng trạng thái và database không có thay đổi ngoài mong đợi.
- routing: Route draft_created thuộc route mong đợi/chấp nhận; case mơ hồ được hỏi lại hoặc handoff thay vì tự thao tác.
- response: Response nêu kết quả hoặc thông tin cần bổ sung và hướng dẫn bước tiếp theo, phù hợp evidence của case.

## H03
- intent: Intent phù hợp với route quan sát (draft_created); không có lỗi parse trong bằng chứng đã lưu.
- extraction: Dữ liệu đầu ra khớp expected case; không thấy SKU/số lượng/thông tin chính bị bịa trong evidence.
- validation: Business validation được thực hiện; route trả về đúng trạng thái và database không có thay đổi ngoài mong đợi.
- routing: Route draft_created thuộc route mong đợi/chấp nhận; case mơ hồ được hỏi lại hoặc handoff thay vì tự thao tác.
- response: Response nêu kết quả hoặc thông tin cần bổ sung và hướng dẫn bước tiếp theo, phù hợp evidence của case.

## M01
- intent: Intent phù hợp với route quan sát (ask_missing); không có lỗi parse trong bằng chứng đã lưu.
- extraction: Dữ liệu đầu ra khớp expected case; không thấy SKU/số lượng/thông tin chính bị bịa trong evidence.
- validation: Business validation được thực hiện; route trả về đúng trạng thái và database không có thay đổi ngoài mong đợi.
- routing: Route ask_missing thuộc route mong đợi/chấp nhận; case mơ hồ được hỏi lại hoặc handoff thay vì tự thao tác.
- response: Response nêu kết quả hoặc thông tin cần bổ sung và hướng dẫn bước tiếp theo, phù hợp evidence của case.

## M02
- intent: Intent phù hợp với route quan sát (ask_missing); không có lỗi parse trong bằng chứng đã lưu.
- extraction: Dữ liệu đầu ra khớp expected case; không thấy SKU/số lượng/thông tin chính bị bịa trong evidence.
- validation: Business validation được thực hiện; route trả về đúng trạng thái và database không có thay đổi ngoài mong đợi.
- routing: Route ask_missing thuộc route mong đợi/chấp nhận; case mơ hồ được hỏi lại hoặc handoff thay vì tự thao tác.
- response: Response nêu kết quả hoặc thông tin cần bổ sung và hướng dẫn bước tiếp theo, phù hợp evidence của case.

## M03
- intent: Intent phù hợp với route quan sát (ask_missing); không có lỗi parse trong bằng chứng đã lưu.
- extraction: Dữ liệu đầu ra khớp expected case; không thấy SKU/số lượng/thông tin chính bị bịa trong evidence.
- validation: Business validation được thực hiện; route trả về đúng trạng thái và database không có thay đổi ngoài mong đợi.
- routing: Route ask_missing thuộc route mong đợi/chấp nhận; case mơ hồ được hỏi lại hoặc handoff thay vì tự thao tác.
- response: Response nêu kết quả hoặc thông tin cần bổ sung và hướng dẫn bước tiếp theo, phù hợp evidence của case.

## M04
- intent: Intent phù hợp với route quan sát (draft_created); không có lỗi parse trong bằng chứng đã lưu.
- extraction: Dữ liệu đầu ra khớp expected case; không thấy SKU/số lượng/thông tin chính bị bịa trong evidence.
- validation: Business validation được thực hiện; route trả về đúng trạng thái và database không có thay đổi ngoài mong đợi.
- routing: Route draft_created thuộc route mong đợi/chấp nhận; case mơ hồ được hỏi lại hoặc handoff thay vì tự thao tác.
- response: Response nêu kết quả hoặc thông tin cần bổ sung và hướng dẫn bước tiếp theo, phù hợp evidence của case.

## M05
- intent: Intent phù hợp với route quan sát (draft_created); không có lỗi parse trong bằng chứng đã lưu.
- extraction: Dữ liệu đầu ra khớp expected case; không thấy SKU/số lượng/thông tin chính bị bịa trong evidence.
- validation: Business validation được thực hiện; route trả về đúng trạng thái và database không có thay đổi ngoài mong đợi.
- routing: Route draft_created thuộc route mong đợi/chấp nhận; case mơ hồ được hỏi lại hoặc handoff thay vì tự thao tác.
- response: Response nêu kết quả hoặc thông tin cần bổ sung và hướng dẫn bước tiếp theo, phù hợp evidence của case.

## I01
- intent: Intent phù hợp với route quan sát (out_of_stock); không có lỗi parse trong bằng chứng đã lưu.
- extraction: Dữ liệu đầu ra khớp expected case; không thấy SKU/số lượng/thông tin chính bị bịa trong evidence.
- validation: Business validation được thực hiện; route trả về đúng trạng thái và database không có thay đổi ngoài mong đợi.
- routing: Route out_of_stock thuộc route mong đợi/chấp nhận; case mơ hồ được hỏi lại hoặc handoff thay vì tự thao tác.
- response: Response nêu kết quả hoặc thông tin cần bổ sung và hướng dẫn bước tiếp theo, phù hợp evidence của case.

## I02
- intent: Intent phù hợp với route quan sát (out_of_stock); không có lỗi parse trong bằng chứng đã lưu.
- extraction: Dữ liệu đầu ra khớp expected case; không thấy SKU/số lượng/thông tin chính bị bịa trong evidence.
- validation: Business validation được thực hiện; route trả về đúng trạng thái và database không có thay đổi ngoài mong đợi.
- routing: Route out_of_stock thuộc route mong đợi/chấp nhận; case mơ hồ được hỏi lại hoặc handoff thay vì tự thao tác.
- response: Response nêu kết quả hoặc thông tin cần bổ sung và hướng dẫn bước tiếp theo, phù hợp evidence của case.

## I03
- intent: Intent phù hợp với route quan sát (ask_missing); không có lỗi parse trong bằng chứng đã lưu.
- extraction: Dữ liệu đầu ra khớp expected case; không thấy SKU/số lượng/thông tin chính bị bịa trong evidence.
- validation: Business validation được thực hiện; route trả về đúng trạng thái và database không có thay đổi ngoài mong đợi.
- routing: Route ask_missing thuộc route mong đợi/chấp nhận; case mơ hồ được hỏi lại hoặc handoff thay vì tự thao tác.
- response: Response nêu kết quả hoặc thông tin cần bổ sung và hướng dẫn bước tiếp theo, phù hợp evidence của case.

## F01
- intent: Intent phù hợp với route quan sát (failed_validation); không có lỗi parse trong bằng chứng đã lưu.
- extraction: Dữ liệu đầu ra khớp expected case; không thấy SKU/số lượng/thông tin chính bị bịa trong evidence.
- validation: Lỗi mô phỏng invalid_json được chuyển thành failed_validation an toàn; đơn không bị thay đổi.
- routing: Route failed_validation thuộc route mong đợi/chấp nhận; case mơ hồ được hỏi lại hoặc handoff thay vì tự thao tác.
- response: Response nêu kết quả hoặc thông tin cần bổ sung và hướng dẫn bước tiếp theo, phù hợp evidence của case.

## F02
- intent: Intent phù hợp với route quan sát (failed_validation); không có lỗi parse trong bằng chứng đã lưu.
- extraction: Dữ liệu đầu ra khớp expected case; không thấy SKU/số lượng/thông tin chính bị bịa trong evidence.
- validation: Lỗi mô phỏng llm_timeout được chuyển thành failed_validation an toàn; đơn không bị thay đổi.
- routing: Route failed_validation thuộc route mong đợi/chấp nhận; case mơ hồ được hỏi lại hoặc handoff thay vì tự thao tác.
- response: Response nêu kết quả hoặc thông tin cần bổ sung và hướng dẫn bước tiếp theo, phù hợp evidence của case.

## F03
- intent: Intent phù hợp với route quan sát (failed_validation); không có lỗi parse trong bằng chứng đã lưu.
- extraction: Dữ liệu đầu ra khớp expected case; không thấy SKU/số lượng/thông tin chính bị bịa trong evidence.
- validation: Lỗi mô phỏng invalid_json được chuyển thành failed_validation an toàn; đơn không bị thay đổi.
- routing: Route failed_validation thuộc route mong đợi/chấp nhận; case mơ hồ được hỏi lại hoặc handoff thay vì tự thao tác.
- response: Response nêu kết quả hoặc thông tin cần bổ sung và hướng dẫn bước tiếp theo, phù hợp evidence của case.

## S01
- intent: Intent phù hợp với route quan sát (handoff); không có lỗi parse trong bằng chứng đã lưu.
- extraction: Dữ liệu đầu ra khớp expected case; không thấy SKU/số lượng/thông tin chính bị bịa trong evidence.
- validation: Business validation được thực hiện; route trả về đúng trạng thái và database không có thay đổi ngoài mong đợi.
- routing: Route handoff thuộc route mong đợi/chấp nhận; case mơ hồ được hỏi lại hoặc handoff thay vì tự thao tác.
- response: Response nêu kết quả hoặc thông tin cần bổ sung và hướng dẫn bước tiếp theo, phù hợp evidence của case.

## S02
- intent: Intent phù hợp với route quan sát (ask_missing); không có lỗi parse trong bằng chứng đã lưu.
- extraction: Dữ liệu đầu ra khớp expected case; không thấy SKU/số lượng/thông tin chính bị bịa trong evidence.
- validation: Business validation được thực hiện; route trả về đúng trạng thái và database không có thay đổi ngoài mong đợi.
- routing: Route ask_missing thuộc route mong đợi/chấp nhận; case mơ hồ được hỏi lại hoặc handoff thay vì tự thao tác.
- response: Response nêu kết quả hoặc thông tin cần bổ sung và hướng dẫn bước tiếp theo, phù hợp evidence của case.

## Q01
- intent: Intent phù hợp với route quan sát (price_checked); không có lỗi parse trong bằng chứng đã lưu.
- extraction: Dữ liệu đầu ra khớp expected case; không thấy SKU/số lượng/thông tin chính bị bịa trong evidence.
- validation: Business validation được thực hiện; route trả về đúng trạng thái và database không có thay đổi ngoài mong đợi.
- routing: Route price_checked thuộc route mong đợi/chấp nhận; case mơ hồ được hỏi lại hoặc handoff thay vì tự thao tác.
- response: Response nêu kết quả hoặc thông tin cần bổ sung và hướng dẫn bước tiếp theo, phù hợp evidence của case.

## Q02
- intent: Intent phù hợp với route quan sát (stock_checked); không có lỗi parse trong bằng chứng đã lưu.
- extraction: Dữ liệu đầu ra khớp expected case; không thấy SKU/số lượng/thông tin chính bị bịa trong evidence.
- validation: Business validation được thực hiện; route trả về đúng trạng thái và database không có thay đổi ngoài mong đợi.
- routing: Route stock_checked thuộc route mong đợi/chấp nhận; case mơ hồ được hỏi lại hoặc handoff thay vì tự thao tác.
- response: Response nêu kết quả hoặc thông tin cần bổ sung và hướng dẫn bước tiếp theo, phù hợp evidence của case.

## L01
- intent: Intent phù hợp với route quan sát (ask_missing); không có lỗi parse trong bằng chứng đã lưu.
- extraction: Dữ liệu đầu ra khớp expected case; không thấy SKU/số lượng/thông tin chính bị bịa trong evidence.
- validation: Business validation được thực hiện; route trả về đúng trạng thái và database không có thay đổi ngoài mong đợi.
- routing: Route ask_missing thuộc route mong đợi/chấp nhận; case mơ hồ được hỏi lại hoặc handoff thay vì tự thao tác.
- response: Response nêu kết quả hoặc thông tin cần bổ sung và hướng dẫn bước tiếp theo, phù hợp evidence của case.

## L02
- intent: Intent phù hợp với route quan sát (ask_missing); không có lỗi parse trong bằng chứng đã lưu.
- extraction: Dữ liệu đầu ra khớp expected case; không thấy SKU/số lượng/thông tin chính bị bịa trong evidence.
- validation: Business validation được thực hiện; route trả về đúng trạng thái và database không có thay đổi ngoài mong đợi.
- routing: Route ask_missing thuộc route mong đợi/chấp nhận; case mơ hồ được hỏi lại hoặc handoff thay vì tự thao tác.
- response: Response nêu kết quả hoặc thông tin cần bổ sung và hướng dẫn bước tiếp theo, phù hợp evidence của case.

## L03
- intent: Intent phù hợp với route quan sát (ask_missing); không có lỗi parse trong bằng chứng đã lưu.
- extraction: Dữ liệu đầu ra khớp expected case; không thấy SKU/số lượng/thông tin chính bị bịa trong evidence.
- validation: Business validation được thực hiện; route trả về đúng trạng thái và database không có thay đổi ngoài mong đợi.
- routing: Route ask_missing thuộc route mong đợi/chấp nhận; case mơ hồ được hỏi lại hoặc handoff thay vì tự thao tác.
- response: Response nêu kết quả hoặc thông tin cần bổ sung và hướng dẫn bước tiếp theo, phù hợp evidence của case.

## L04
- intent: Intent phù hợp với route quan sát (ask_missing); không có lỗi parse trong bằng chứng đã lưu.
- extraction: Dữ liệu đầu ra khớp expected case; không thấy SKU/số lượng/thông tin chính bị bịa trong evidence.
- validation: Business validation được thực hiện; route trả về đúng trạng thái và database không có thay đổi ngoài mong đợi.
- routing: Route ask_missing thuộc route mong đợi/chấp nhận; case mơ hồ được hỏi lại hoặc handoff thay vì tự thao tác.
- response: Response nêu kết quả hoặc thông tin cần bổ sung và hướng dẫn bước tiếp theo, phù hợp evidence của case.

## L05
- intent: Intent phù hợp với route quan sát (catalog_empty); không có lỗi parse trong bằng chứng đã lưu.
- extraction: Dữ liệu đầu ra khớp expected case; không thấy SKU/số lượng/thông tin chính bị bịa trong evidence.
- validation: Business validation được thực hiện; route trả về đúng trạng thái và database không có thay đổi ngoài mong đợi.
- routing: Route catalog_empty thuộc route mong đợi/chấp nhận; case mơ hồ được hỏi lại hoặc handoff thay vì tự thao tác.
- response: Response nêu kết quả hoặc thông tin cần bổ sung và hướng dẫn bước tiếp theo, phù hợp evidence của case.

## L06
- intent: Intent phù hợp với route quan sát (handoff); không có lỗi parse trong bằng chứng đã lưu.
- extraction: Dữ liệu đầu ra khớp expected case; không thấy SKU/số lượng/thông tin chính bị bịa trong evidence.
- validation: Business validation được thực hiện; route trả về đúng trạng thái và database không có thay đổi ngoài mong đợi.
- routing: Route handoff thuộc route mong đợi/chấp nhận; case mơ hồ được hỏi lại hoặc handoff thay vì tự thao tác.
- response: Response nêu kết quả hoặc thông tin cần bổ sung và hướng dẫn bước tiếp theo, phù hợp evidence của case.

## L07
- intent: Intent phù hợp với route quan sát (ask_missing); không có lỗi parse trong bằng chứng đã lưu.
- extraction: Dữ liệu đầu ra khớp expected case; không thấy SKU/số lượng/thông tin chính bị bịa trong evidence.
- validation: Business validation được thực hiện; route trả về đúng trạng thái và database không có thay đổi ngoài mong đợi.
- routing: Route ask_missing thuộc route mong đợi/chấp nhận; case mơ hồ được hỏi lại hoặc handoff thay vì tự thao tác.
- response: Response nêu kết quả hoặc thông tin cần bổ sung và hướng dẫn bước tiếp theo, phù hợp evidence của case.

## U01
- intent: Intent phù hợp với route quan sát (order_updated); không có lỗi parse trong bằng chứng đã lưu.
- extraction: Dữ liệu đầu ra khớp expected case; không thấy SKU/số lượng/thông tin chính bị bịa trong evidence.
- validation: Business validation được thực hiện; route trả về đúng trạng thái và database không có thay đổi ngoài mong đợi.
- routing: Route order_updated thuộc route mong đợi/chấp nhận; case mơ hồ được hỏi lại hoặc handoff thay vì tự thao tác.
- response: Response nêu kết quả hoặc thông tin cần bổ sung và hướng dẫn bước tiếp theo, phù hợp evidence của case.

## U02
- intent: Intent phù hợp với route quan sát (order_updated); không có lỗi parse trong bằng chứng đã lưu.
- extraction: Dữ liệu đầu ra khớp expected case; không thấy SKU/số lượng/thông tin chính bị bịa trong evidence.
- validation: Business validation được thực hiện; route trả về đúng trạng thái và database không có thay đổi ngoài mong đợi.
- routing: Route order_updated thuộc route mong đợi/chấp nhận; case mơ hồ được hỏi lại hoặc handoff thay vì tự thao tác.
- response: Response nêu kết quả hoặc thông tin cần bổ sung và hướng dẫn bước tiếp theo, phù hợp evidence của case.

## U03
- intent: Intent phù hợp với route quan sát (ask_missing); không có lỗi parse trong bằng chứng đã lưu.
- extraction: Dữ liệu đầu ra khớp expected case; không thấy SKU/số lượng/thông tin chính bị bịa trong evidence.
- validation: Business validation được thực hiện; route trả về đúng trạng thái và database không có thay đổi ngoài mong đợi.
- routing: Route ask_missing thuộc route mong đợi/chấp nhận; case mơ hồ được hỏi lại hoặc handoff thay vì tự thao tác.
- response: Response nêu kết quả hoặc thông tin cần bổ sung và hướng dẫn bước tiếp theo, phù hợp evidence của case.

## F04
- intent: Intent phù hợp với route quan sát (failed_validation); không có lỗi parse trong bằng chứng đã lưu.
- extraction: Dữ liệu đầu ra khớp expected case; không thấy SKU/số lượng/thông tin chính bị bịa trong evidence.
- validation: Lỗi mô phỏng llm_rate_limit được chuyển thành failed_validation an toàn; đơn không bị thay đổi.
- routing: Route failed_validation thuộc route mong đợi/chấp nhận; case mơ hồ được hỏi lại hoặc handoff thay vì tự thao tác.
- response: Response nêu kết quả hoặc thông tin cần bổ sung và hướng dẫn bước tiếp theo, phù hợp evidence của case.
