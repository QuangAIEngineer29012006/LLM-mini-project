# Automatic RAG error analysis

Báo cáo này được sinh từ kết quả evaluation; không thay đổi nhãn expected và không loại bỏ case thất bại.

- Cases: 17
- Cases có lỗi/near-miss: 7
- Pass: 11/17
- Hit@3: 1.0
- Recall@5: 0.95
- MRR: 0.95

## Phân loại

| Loại | Số case |
|---|---:|
| routing | 1 |
| retrieval | 1 |
| context | 1 |
| grounding | 1 |
| citation | 3 |
| status_safety | 3 |
| action_validation | 0 |

## Chi tiết

| Case | Loại | Categories | Phân tích |
|---|---|---|---|
| E02 | exact | citation | citation: resolved=2, supported=1, total=2 |
| P03 | paraphrase | routing, status_safety | routing: route='catalog_shown', expected='knowledge'<br>status_safety: status=None, expected='answered' |
| M02 | multi | retrieval | retrieval: Hit@3=True, Recall@5=0.5, MRR=1.0 |
| M03 | multi | context, grounding, citation | context: evidence coverage=0.5 for multi-condition query<br>grounding: answer does not contain all expected evidence spans<br>citation: resolved=2, supported=1, total=2 |
| N03 | no_evidence | status_safety | status_safety: status=None, expected='insufficient_evidence' |
| X02 | mixed | status_safety | status_safety: status='insufficient_evidence', expected='answered' |
| X03 | mixed | citation | citation: resolved=2, supported=1, total=2 |

## Cách sử dụng

Báo cáo thủ công vẫn cần xem xét nguyên nhân nghiệp vụ và xác nhận claim; báo cáo tự động chỉ phân loại theo các tín hiệu đo được.
