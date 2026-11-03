# Backend và xử lý LLM: tài liệu thuyết trình

Bản chụp code ngày 22/10/2026. 88 slide, 34 slide phần chính, 100 hàm được tra cứu đầy đủ.

## Pipeline chung

1. React gửi JSON và token tới FastAPI.
2. Middleware giới hạn request, body và gắn request ID.
3. Pydantic kiểm tra body, session_db xác thực phiên và gắn owner.
4. Luồng web gọi service trực tiếp. Luồng chat chọn policy, rule catalog hoặc Gemini.
5. Kết quả model qua parse_output, bỏ lượng tự đoán, validate_grounding rồi mới ghép context.
6. Workflow đọc catalog hoặc hỏi thêm, tạo/sửa đơn qua business service và transaction.
7. Server cập nhật context/audit/receipt và trả JSON về UI.

## Lộ trình trình bày

### Slide 1. Backend và xử lý LLM

Pipeline xử lý request, code chứng minh và tra cứu 100 hàm

Mở đầu bằng câu hỏi: khi khách yêu cầu đặt một balo, đoạn code nào nhận request và đoạn code nào thực sự ghi đơn? Các slide trích đúng code của bản chụp ngày 22/10/2026, sau khi thêm comment. Phần chính tập trung vào đường chạy. Phụ lục giải thích từng hàm trong backend/ và src/.

### Slide 2. Bản đồ phần backend



Phạm vi “tất cả hàm” trong bộ slide là 80 def/async def của backend/ và 20 của src/, bao gồm hàm lồng và phương thức lớp. database/shop_db là lớp dữ liệu được gọi tới, trình bày phần liên quan pipeline, không trộn vào danh mục 100 hàm. Hai file shop_api/shop_logic nằm trong thư mục backend nhưng phục vụ UI Python cũ. Frontend React gọi HTTP trực tiếp.

### Slide 3. Pipeline chung của backend



Đọc từ trái sang phải ở hàng trên, sau đó theo đường nối xuống hàng dưới. Mọi đường ghi đơn đều qua server và DB. Route catalog công khai không cần phiên, còn giỏ/đơn/chat phải có token. Web đi thẳng business service; chat có thêm nhánh hiểu ngôn ngữ.

### Slide 4. Pipeline riêng của chat



Gemini chỉ nằm ở một nhánh, không phải mọi câu đều tốn quota. Request trùng có receipt trả kết quả trước đó. Sau lời gọi provider, workflow kiểm tra lại phiên và revision trong transaction trước khi ghi dữ liệu.

### Slide 5. Pipeline xử lý LLM



Theo dõi nhánh Gemini của workflow. generate chỉ trả LLMResult. parse_output tạo Extraction. discard_implicit_quantities và validate_grounding kiểm tra dữ liệu trước khi ghép vào context. Sau đó chat dispatch hành động và chỉ ghi trong transaction sau khi kiểm tra lại phiên/revision. Lỗi provider hoặc output chặn đường ghi và trả failed_validation.

### Slide 6. Nơi nhận request chat

Endpoint POST /api/chat chuyển body.message sang workflow sau khi xác thực phiên.

Giải thích decorator khai báo route, ChatRequest là Pydantic model của body, Request chứa headers/IP. request_key đọc Idempotency-Key. session_db trả kết nối, phiên và Ctx. limiter.check áp giới hạn chat theo owner. Chưa có thao tác tạo đơn ở route này.

**Code chứng minh: `backend/main.py:237-244`**

```python
237      @app.post("/api/chat")
238      # Nhận tin nhắn, kiểm tra phiên/giới hạn gọi chat rồi chuyển sang luồng xử lý bot.
239      def chat_message(body: ChatRequest, request: Request):
240          key = request_key(request.headers.get("Idempotency-Key"))
241          with session_db(request) as (conn, session, ctx):
242              limiter.check("chat", session["owner_id"], settings.chat_limit)
243              return chat(conn, ctx, session, body.message, app.state.llm_client, key)
244  
```

### Slide 7. Hợp đồng đầu vào

Schema từ chối trường thừa và kiểm tra kiểu dữ liệu trước khi endpoint chạy.

strict=True không tự đổi chuỗi số thành số nguyên. extra=forbid chặn client gửi thêm price/stock/status/owner. Shipping kiểm tra độ dài, còn quy tắc số điện thoại tiếp tục ở lớp validation database.

**Code chứng minh: `backend/models.py:6-15`**

```python
  6  class StrictModel(BaseModel):
  7      model_config = ConfigDict(extra="forbid", strict=True)
  8  
  9  
 10  Sku = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[A-Z0-9][A-Z0-9_-]{0,39}$")]
 11  Quantity = Annotated[int, Field(ge=1, le=99)]
 12  
 13  
 14  class CartItem(StrictModel):
 15      sku: Sku
```

**Code chứng minh: `backend/models.py:45-46`**

```python
 45  class ChatRequest(StrictModel):
 46      message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
```

### Slide 8. Middleware và lỗi API

Một lớp chung gắn request ID và kiểm soát request trước khi vào route.

RateLimiter giữ deque và khóa trong RAM, phạm vi một process. Các exception handlers chuyển ApiProblem, DataServiceError, lỗi Pydantic, HTTPException và OperationalError sang JSON thống nhất. Không đưa stack trace hoặc body provider vào phản hồi.

**Code chứng minh: `backend/main.py:74-85`**

```python
 74      async def request_context(request, call_next):
 75          request.state.request_id = uuid.uuid4().hex
 76          try:
 77              limiter.check("http", request.client.host if request.client else "local", settings.request_limit)
 78              body = bytearray()
 79              async for chunk in request.stream():
 80                  body.extend(chunk)
 81                  if len(body) > 16384:
 82                      raise ApiProblem(413, "request_too_large", "Nội dung request vượt giới hạn 16 KB.")
 83              # Starlette reuses the cached body when dispatching to the route.
 84              request._body = bytes(body)
 85              response = await call_next(request)
```

### Slide 9. Phiên mua sắm và quyền dữ liệu

Token nhận từ POST /api/session được lưu dưới dạng hash trong database.

authenticate kiểm tra scheme Bearer, độ dài token, hash và expires_at. owned_order tiếp tục so owner_id trước khi đọc/sửa một đơn. Hết hạn hoặc bị thu hồi trả 401. Đây là phiên demo, chưa phải tài khoản đăng nhập.

**Code chứng minh: `backend/storage.py:62-70`**

```python
 62  def authenticate(conn, authorization):
 63      scheme, _, token = (authorization or "").partition(" ")
 64      if scheme.lower() != "bearer" or not 20 <= len(token) <= 200:
 65          raise ApiProblem(401, "auth", "Cần phiên khách hàng hợp lệ.")
 66      row = conn.execute("SELECT * FROM api_sessions WHERE token_hash = ? AND expires_at > ?",
 67                         (hashlib.sha256(token.encode()).hexdigest(), int(time.time()))).fetchone()
 68      if row is None:
 69          raise ApiProblem(401, "auth", "Phiên đã hết hạn hoặc không hợp lệ. Hãy mở phiên mới.")
 70      return dict(row)
```

**Code chứng minh: `backend/services.py:30-35`**

```python
 30  def owned_order(conn, owner, order_id):
 31      order = orders.get_order(conn, order_id)
 32      if order["owner_id"] != owner:
 33          raise ApiProblem(404, "not_found", "Không tìm thấy đơn hàng trong phiên của bạn.")
 34      return order
 35  
```

### Slide 10. Ba nhánh hiểu một câu chat

Workflow ưu tiên chặn yêu cầu nguy hiểm và nhận câu catalog rõ nghĩa trước Gemini.

Regex UNSAFE chỉ là một lớp phòng vệ, không bảo đảm chống mọi injection. Những câu khác đi vào client.generate. Các thao tác cuối vẫn bị giới hạn bởi schema, quyền phiên, SKU, tồn và transaction.

**Code chứng minh: `backend/chat_service.py:226-235`**

```python
226      if UNSAFE.search(normalize(message)):
227          result = response("Yêu cầu này cần nhân viên xem lại. Hệ thống chưa thay đổi đơn hàng.", "handoff")
228          meta.update(intent="unknown_or_handoff", model_id="local-policy", interpretation_source="local_policy")
229      elif (local := local_catalog_request(message)) is not None:
230          data = local
231          meta.update(intent=data.intent, model_id="local-catalog", interpretation_source="local_catalog")
232      else:
233          try:
234              context = {**conv["context"], "pending_intent": conv["pending_intent"]}
235              context["recent_products"] = [{"name": p["name"], "category": p["category"]}
```

### Slide 11. Ngữ cảnh gửi cho model

Prompt gồm dữ liệu câu hiện tại, catalog rút gọn và các trường hội thoại cần tiếp tục.

_catalog_context tìm theo câu hiện tại và sản phẩm đang hỏi, giới hạn 6 sản phẩm và 10 alias mỗi sản phẩm. Context catalog gồm tên, category, description, alias, sku/color/size. Hàm không gửi giá/tồn cho model để model quyết định nghiệp vụ. Không gửi toàn bộ lịch sử chat thô.

**Code chứng minh: `src/prompts.py:48-54`**

```python
 48  def build_prompt(message, catalog, context):
 49      safe_context = {"pending_intent": context.get("pending_intent"),
 50                      "pending_items": context.get("items", []),
 51                      "recent_products": context.get("recent_products", [])}
 52      payload = {"CUSTOMER_MESSAGE": message, "CATALOG_CONTEXT": catalog,
 53                 "CONVERSATION_CONTEXT": safe_context, "OUTPUT_SCHEMA": Extraction.model_json_schema()}
 54      return SYSTEM_PROMPT, json.dumps(payload, ensure_ascii=False)
```

### Slide 12. Prompt shop-assistant-v4

Hướng dẫn model trả một JSON và tách ý định mua khỏi ý định chỉ xem hàng.

Bản v4 nhấn mạnh chỉ trích dữ liệu mới từ câu hiện tại, giữ null nếu chưa có, không tự điền 1 và không lấy 15inch làm số lượng. Prompt là hướng dẫn xác suất. Parser và quy tắc server mới quyết định dữ liệu có được dùng.

**Code chứng minh: `src/prompts.py:10-20`**

```python
 10  Return only one JSON object following OUTPUT_SCHEMA. No markdown or extra properties.
 11  Allowed intents: browse_catalog, create_order, check_stock, check_price, update_order, unknown_or_handoff.
 12  browse_catalog covers browsing, product search, recommendations, categories, descriptions,
 13  colors and sizes. Questions like 'cửa hàng bán những gì', 'tôi muốn tham khảo sản phẩm',
 14  'shop có những loại áo nào', 'cho xem giày dưới 800k' are normal shopping, never handoff.
 15  For broad catalog questions emit items=[]; do not invent product names from the catalog.
 16  For specific product/category searches put the literal phrase in requested_product.
 17  Use catalog_filters only for explicitly stated category, min/max price in VND, or 'còn hàng'.
 18  Convert 200k/200 nghìn to 200000 and 1 triệu to 1000000; absent price bounds are null.
 19  Do not treat browsing, asking prices, or asking availability as an instruction to buy.
 20  Only explicit purchase instructions can have create_order intent.
```

**Code chứng minh: `src/prompts.py:28-30`**

```python
 28  An instruction to order a product without a count must have quantity=null, never default 1.
 29  Measurements such as 15inch/15 inch describe size, never quantity. Keep their literal spelling.
 30  Repeated product names still describe one item unless the customer requests distinct items.
```

### Slide 13. JSON mà LLM phải trả

Extraction quy định cấu trúc để backend có thể xử lý thay vì đọc một đoạn văn tự do.

Giải thích item có requested_product, sku, variant và quantity. Confidence thấp hoặc requires_human_review bật sẽ đi handoff. missing_information của model không trực tiếp là quyết định cuối. Workflow tự xác định phần thiếu bằng dữ liệu đã ghép và DB.

**Code chứng minh: `src/parser.py:41-51`**

```python
 41  class Extraction(StrictModel):
 42      intent: INTENTS
 43      confidence: Literal["low", "medium", "high"]
 44      items: Annotated[list[ExtractedItem], Field(max_length=10)]
 45      customer: Customer
 46      order_reference: Text | None
 47      missing_information: Annotated[list[Text], Field(max_length=10)]
 48      requires_human_review: bool
 49      evidence: Annotated[list[Text], Field(max_length=10)]
 50      catalog_filters: CatalogFilters = Field(default_factory=CatalogFilters)
 51  
```

### Slide 14. Gọi Gemini qua REST

GeminiLLMClient.generate() ghép payload rồi gọi endpoint generateContent.

Đây là implementation REST bằng requests, không dùng SDK agent/tool-calling. API key lấy từ settings và nằm trong header x-goog-api-key. Deck chỉ trích tên biến, không chứa giá trị key. requests.post dùng timeout cấu hình và không tự đi theo redirect.

**Code chứng minh: `src/llm_client.py:51-57`**

```python
 51          system, prompt = build_prompt(message, catalog, context)
 52          url = "https://generativelanguage.googleapis.com/v1beta/models/" + quote(self.model_id, safe="-") + ":generateContent"
 53          payload = {"systemInstruction": {"parts": [{"text": system}]},
 54                     "contents": [{"role": "user", "parts": [{"text": prompt}]}],
 55                     "generationConfig": {"temperature": 0, "maxOutputTokens": 2048,
 56                                          "responseFormat": {"text": {"mimeType": "APPLICATION_JSON",
 57                                                                      "schema": Extraction.model_json_schema()}}}}
```

**Code chứng minh: `src/llm_client.py:66-67`**

```python
 66                  response = requests.post(url, headers={"x-goog-api-key": self.settings.api_key}, json=payload,
 67                                           timeout=self.settings.llm_timeout, allow_redirects=False)
```

### Slide 15. Đọc kết quả Gemini

Client chỉ nhận candidate kết thúc STOP, ghép phần text và lấy token usage.

Nếu prompt bị chặn, finishReason không phải STOP hoặc cấu trúc provider thiếu trường, client báo LLMError. thought parts không ghép vào text. Không tin rằng JSON nhìn hợp lệ là đủ an toàn để ghi DB.

**Code chứng minh: `src/llm_client.py:84-91`**

```python
 84                          candidate = body["candidates"][0]
 85                          if candidate.get("finishReason") != "STOP":
 86                              raise LLMError("llm_refusal", attempt)
 87                          parts = candidate["content"]["parts"]
 88                          text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
 89                          usage = body.get("usageMetadata", {})
 90                          return LLMResult(text, usage.get("promptTokenCount"), usage.get("candidatesTokenCount"), attempt)
 91                      except (AttributeError, KeyError, IndexError, TypeError, ValueError):
```

### Slide 16. Ngân sách gọi model theo ngày

Mỗi HTTP attempt phải được giữ một lượt trong ledger trước khi gửi mạng.

Ngày quota theo America/Los_Angeles. Hạn mức là cấu hình ứng dụng, không phải cam kết quota Google. Nếu request timeout vẫn đã tính một attempt vì có thể provider đã nhận. Bộ đếm không biết traffic của ứng dụng khác hay trước lúc tính ledger.

**Code chứng minh: `src/quota.py:22-32`**

```python
 22      def reserve(self, model_id, now=None):
 23          day = (now or datetime.now(ZoneInfo("America/Los_Angeles"))).astimezone(ZoneInfo("America/Los_Angeles")).date().isoformat()
 24          with closing(sqlite3.connect(self.path, timeout=10)) as conn, conn:
 25              conn.execute("BEGIN IMMEDIATE")
 26              row = conn.execute("SELECT attempts FROM llm_daily_usage WHERE model_id=? AND quota_day=?", (model_id, day)).fetchone()
 27              used = row[0] if row else 0
 28              if used >= self.limit:
 29                  raise DailyLimitReached()
 30              conn.execute("INSERT INTO llm_daily_usage VALUES (?,?,1) ON CONFLICT(model_id,quota_day)"
 31                           " DO UPDATE SET attempts=attempts+1", (model_id, day))
 32              return used + 1
```

### Slide 17. Timeout, lỗi provider và retry

Client phân loại 429, 5xx, lỗi xác thực và lỗi transport.

_retry_delay đọc Retry-After giây hoặc HTTP-date và dùng backoff. Nếu thời gian phải chờ trên 3 giây thì trả lỗi để khách thử sau, không gửi sớm. Mỗi retry vẫn tiêu một lượt ngân sách. Không tự động retry vô hạn.

**Code chứng minh: `src/llm_client.py:73-79`**

```python
 73                  if response.status_code == 429 or 500 <= response.status_code <= 599:
 74                      error = "llm_rate_limit" if response.status_code == 429 else "llm_unavailable"
 75                      header = response.headers.get("Retry-After")
 76                  elif response.status_code != 200:
 77                      code = "llm_auth" if response.status_code in {401, 403} else "llm_request"
 78                      raise LLMError(code, attempt)
 79                  else:
```

**Code chứng minh: `src/llm_client.py:93-100`**

```python
 93              if attempt >= self.settings.llm_max_retries:
 94                  raise LLMError(error, attempt)
 95              delay = _retry_delay(header, attempt)
 96              if delay > 3:
 97                  # Return a recoverable error rather than retrying before the provider permits it.
 98                  raise LLMError(error, attempt)
 99              time.sleep(delay)
100  
```

### Slide 18. Parse JSON và kiểm tra schema

parse_output() từ chối JSON rỗng/quá lớn, khóa trùng, NaN và dữ liệu sai schema.

Giới hạn output là 16.000 ký tự. object_pairs_hook=_unique_object giúp phát hiện khóa trùng. parse_constant từ chối giá trị không hữu hạn. Pydantic kiểm tra enum intent, số lượng 1–99, độ dài text, extra fields và kiểu strict.

**Code chứng minh: `src/parser.py:67-78`**

```python
 67  def parse_output(raw):
 68      if not isinstance(raw, str) or not raw.strip() or len(raw) > 16000:
 69          raise OutputError("invalid_json")
 70      try:
 71          value = json.loads(raw, object_pairs_hook=_unique_object,
 72                             parse_constant=lambda _: (_ for _ in ()).throw(ValueError("non-finite")))
 73      except (ValueError, RecursionError):
 74          raise OutputError("invalid_json") from None
 75      try:
 76          return Extraction.model_validate(value)
 77      except ValidationError:
 78          raise OutputError("invalid_schema") from None
```

### Slide 19. Kiểm tra evidence của dữ liệu

validate_grounding() so các giá trị model trích với chính câu khách đang gửi.

Kiểm tra requested_product, sku, màu, size, quantity, customer, order reference, evidence và bộ lọc giá/tồn. money_amounts hỗ trợ 800k hay 1 triệu. Đây là kiểm tra từ vựng/chuỗi và allowlist, không chứng minh đầy đủ ngữ nghĩa hoặc chống mọi cách diễn đạt mơ hồ.

**Code chứng minh: `src/parser.py:127-134`**

```python
127  def validate_grounding(data, message):
128      """Reject invented fields before merging them into server-owned conversation state."""
129      text = " " + normalize(message) + " "
130      def present(value):
131          return value is None or (normalize(value) and " " + normalize(value) + " " in text)
132      for item in data.items:
133          if not all(present(v) for v in (item.requested_product, item.sku, item.variant.color)):
134              raise OutputError("ungrounded_output")
```

**Code chứng minh: `src/parser.py:138-141`**

```python
138          if item.quantity is not None:
139              words = [w for w, n in NUMBER_WORDS.items() if n == item.quantity]
140              if not any(" " + q + " " in quantity_source(message, data.customer) for q in [str(item.quantity), *words]):
141                  raise OutputError("ungrounded_output")
```

### Slide 20. Số đo và số lượng

Server loại số đo, phần SKU và giao nhận khỏi nguồn dùng để kiểm tra quantity.

discard_implicit_quantities bỏ giá trị do model tự mặc định nếu không có lượng rõ ràng. Số lượng trái với lượng khách đã nêu vẫn bị từ chối bởi grounding. Trong form UI, số 1 là lựa chọn hiển thị để khách xem/sửa trước khi chủ động bấm gửi, không phải đơn tự tạo.

**Code chứng minh: `src/parser.py:104-116`**

```python
104  def quantity_source(message, customer=None):
105      text = normalize_money(message)
106      text = re.split(r"\b(?:ten|nguoi nhan|sdt|so dien thoai|giao ve|giao den|dia chi)\b", text)[0]
107      if customer:
108          for value in customer.model_dump().values():
109              if value:
110                  text = text.replace(normalize_money(value), " ")
111      text = re.sub(r"\b[a-z][a-z0-9]*(?:-[a-z0-9]+){2,}\b", " ", text)
112      text = re.sub(r"\b\d+(?:[.,]\d+)?\s*(?:inches|inch|cm|mm|kg|g|ml)\b", " ", text)
113      text = re.sub(r"\bsize\s+[a-z0-9]+\b", " ", text)
114      text = re.sub(r"(?<!\w)-\d+(?:[.,]\d+)?|\b\d+[.,]\d+\b", " invalidquantity ", text)
115      return " " + normalize(text) + " "
116  
```

### Slide 21. Ghép hội thoại nhiều lượt

_merge_items() bổ sung trường còn thiếu khi xác định đang nói về cùng một sản phẩm.

Trong chat(), continuing kiểm tra intent mới có khớp pending_intent không. Customer chỉ ghép các trường khác null từ câu mới. Khi đổi biến thể mà chưa nêu SKU, helper xóa SKU cũ để resolve lại. Nếu sản phẩm thực sự khác, không tự mượn số lượng/giao nhận của ý định khác.

**Code chứng minh: `backend/chat_service.py:61-73`**

```python
 61  def _merge_items(previous, incoming):
 62      if not incoming:
 63          return previous
 64      if len(previous) == len(incoming) == 1:
 65          old, new = previous[0], incoming[0]
 66          same = not new.get("requested_product") or normalize(new["requested_product"]) == normalize(old.get("requested_product"))
 67          if same and not (new.get("sku") and old.get("sku") and new["sku"] != old["sku"]):
 68              variant = {**old["variant"], **{k: v for k, v in new["variant"].items() if v is not None}}
 69              result = {**old, **{k: v for k, v in new.items() if v is not None}, "variant": variant}
 70              if any(new["variant"].values()) and not new.get("sku"):
 71                  result["sku"] = None
 72              return [result]
 73      return incoming
```

### Slide 22. Chọn nhánh nghiệp vụ

Workflow quyết định action từ intent đã qua kiểm tra và dữ liệu đã ghép.

browse_catalog đọc hàng, create_order gọi _draft, update_order gọi _update, các câu price/stock qua _query. Nếu requires_human_review hoặc confidence thấp hoặc unknown_or_handoff thì handoff trước dispatch. Không có API confirm payment/order cho khách.

**Code chứng minh: `backend/chat_service.py:283-292`**

```python
283                  if data.intent == "browse_catalog":
284                      result = catalog_reply(conn, incoming, data.catalog_filters, data.intent)
285                  elif data.intent == "create_order":
286                      result = _draft(conn, ctx, session, slots, key)
287                  elif data.intent == "update_order":
288                      result = _update(conn, ctx, session, slots)
289                  else:
290                      result = _query(conn, slots["items"], data.intent, data.catalog_filters)
291                  if data.intent in READ_INTENTS:
292                      saved = browsing_context(result) if "products" in result else {}
```

### Slide 23. Đối chiếu biến thể trong catalog

resolve_item() cần tìm được đúng một biến thể đang bán, không chọn đại SKU gần giống.

Nếu có SKU thì đọc variant, nếu có tên thì search rồi lấy nhóm score gần đầu. Lọc màu/size sau đó. Nhiều hoặc không có ứng viên đều hỏi variant. Màu chung có thể khớp màu chi tiết theo prefix, nên luôn cần giới hạn cuối cùng đúng một SKU.

**Code chứng minh: `backend/chat_service.py:88-99`**

```python
 88      for key in ("color", "size"):
 89          value = item["variant"].get(key)
 90          if value:
 91              requested = attribute_value(value, key)
 92              candidates = [v for v in candidates if requested == attribute_value(v[key], key)
 93                            or (key == "color" and attribute_value(v[key], key).startswith(requested + " "))]
 94      if len(candidates) != 1:
 95          options = "; ".join(f"{v['sku']} ({v['variant_name']})" for v in candidates[:8])
 96          detail = "Có nhiều biến thể phù hợp: " + options if candidates else "Không có biến thể khớp màu/size đã yêu cầu."
 97          return None, ask(["variant"], detail)
 98      return candidates[0], None
 99  
```

**Code chứng minh: `backend/variant_utils.py:7-8`**

```python
  7  def size_value(value):
  8      return re.sub(r"(?<=\d)\s*(?:inches|inch)\b", " inch", normalize(value))
```

### Slide 24. Thiếu thông tin: bot hỏi tiếp

_draft() trả ask_missing cùng purchase.items để frontend vẽ form đặt hàng ngay trong chat.

_shipping kiểm tra tên/phone/address rồi dùng validate_delivery ở lớp DB. Client không gửi price/stock để server tin. ChatPurchaseForm tạo một message có SKU, số lượng và giao nhận khách nhập, gửi tiếp POST /api/chat với khóa riêng. Không phải một route bỏ qua LLM/validation.

**Code chứng minh: `backend/chat_service.py:144-148`**

```python
144          if stock["ok"]:
145              detail = "Đã chọn: " + "; ".join(f"{i['name']} — {i['variant_label']} ({i['unit_price']:,} VND/sản phẩm)" for i in selected) + "."
146              result = ask(missing, detail)
147              result["purchase"] = {"items": selected}
148              return result
```

### Slide 25. Đủ thông tin: tạo đơn nháp

Sau khi chuẩn hóa số lượng và kiểm tra tồn, workflow gọi lớp order service.

orders.create_draft_order ở database/shop_db/order_service.py kiểm tra owner/key/items/delivery, tạo cart trong transaction rồi chuyển trạng thái. Giá từng item đọc từ catalog bởi _upsert_item. Lỗi nào cũng rollback. _draft không có nhánh tự xác nhận thanh toán.

**Code chứng minh: `backend/chat_service.py:149-158`**

```python
149      resolved = [{"sku": s, "quantity": q} for s, q in normalize_items(resolved)]
150      stock = catalog.check_items(conn, resolved)
151      if not stock["ok"]:
152          details = "; ".join(f"{r['sku']} còn {r['available']}, bạn yêu cầu {r['requested']}" for r in stock["results"] if not r["ok"])
153          return response("Không đủ hàng: " + details + ". Vui lòng chọn lại số lượng hoặc biến thể.", "out_of_stock")
154      order = orders.create_draft_order(conn, ctx, session["owner_id"], resolved, delivery, source="chat", idempotency_key=key)
155      return response("Đã tạo đơn nháp. Bạn có thể xem và sửa ở trang Đơn hàng; đơn đang chờ xác nhận.",
156                      "draft_created", order=order_view(conn, order))
157  
158  
```

### Slide 26. Lời gọi LLM và transaction

Gemini chạy trước transaction ghi dữ liệu để tránh giữ khóa SQLite trong lúc đợi mạng.

Hai lượt chat chạy song song có thể đều tiêu quota, nhưng request theo revision cũ bị 409 conversation_busy trước khi ghi. Bảo vệ phiên bị thu hồi trong lúc model xử lý. Receipt được kiểm tra cả trước lẫn trong transaction để chặn request lặp cạnh tranh.

**Code chứng minh: `backend/chat_service.py:255-267`**

```python
255      with transaction(conn):
256          active = conn.execute("SELECT 1 FROM api_sessions WHERE token_hash=? AND expires_at>?",
257                                (session["token_hash"], int(time.time()))).fetchone()
258          if active is None:
259              raise ApiProblem(401, "auth", "Phiên đã hết hạn hoặc bị thu hồi trong lúc xử lý. Vui lòng mở phiên mới.")
260          cached = replay(conn, owner, "chat", key, message)
261          if cached:
262              return cached
263          latest = conn.execute("SELECT COALESCE(MAX(id),0) FROM conversation_messages WHERE conversation_id=?", (cid,)).fetchone()[0]
264          if revision != latest:
265              raise ApiProblem(409, "conversation_busy", "Hội thoại vừa thay đổi. Vui lòng gửi lại sau khi tin trước xử lý xong.")
266          slots = conv["context"]
267          if data:
```

### Slide 27. Giá tiền và trạng thái đơn trong DB

Lớp dữ liệu kiểm tra hàng/giao nhận và chuyển đơn sang pending_confirmation trong transaction.

Tiếp tục đọc order_common.reprice_and_check_stock và recalc_total nếu được hỏi. change_status khi chuyển confirmed mới có logic trừ kho nhưng API khách hàng hiện tại không cung cấp đường confirm. Kiểm tra tổng của ví dụ balo: 2 × 520000 = 1040000.

**Code chứng minh: `database/shop_db/order_service.py:128-128`**

```python
128      with transaction(conn):
```

**Code chứng minh: `database/shop_db/order_service.py:132-132`**

```python
132          order = create_cart(conn, ctx, owner, items, source)
```

**Code chứng minh: `database/shop_db/order_service.py:138-140`**

```python
138          order = change_status(conn, ctx, order["id"], "pending_confirmation")
139          order["replayed"] = False
140          return order
```

**Code chứng minh: `database/shop_db/order_common.py:36-40`**

```python
 36  def recalc_total(conn, order_id) -> int:
 37      total = conn.execute("SELECT COALESCE(SUM(line_total), 0) FROM order_items WHERE order_id = ?",
 38                           (order_id,)).fetchone()[0]
 39      conn.execute(f"UPDATE orders SET total_amount = ?, updated_at = {NOW_SQL} WHERE id = ?", (total, order_id))
 40      return total
```

### Slide 28. Checkout từ website

Luồng web gửi giao nhận và chuyển giỏ của phiên thành đơn chờ xác nhận, không cần LLM.

Giải thích replay bảo vệ thao tác checkout gửi lại. Sau submit_order, api_sessions.cart_id về NULL để lần mua sau mở giỏ mới. Nếu giỏ rỗng trả 409. Khách không được xác nhận đơn hoặc gửi owner/giá tùy ý.

**Code chứng minh: `backend/services.py:103-117`**

```python
103  def checkout(conn, ctx, session, shipping, key):
104      owner = session["owner_id"]
105      with transaction(conn):
106          existing = replay(conn, owner, "checkout", key, shipping)
107          if existing:
108              return existing
109          cart = cart_order(conn, session, ctx)
110          if not cart or not cart["items"]:
111              raise ApiProblem(409, "empty_cart", "Giỏ hàng đang trống.")
112          delivery = {"customer_name": shipping["recipient_name"], "phone": shipping["phone"], "address": shipping["address"]}
113          order = orders.submit_order(conn, ctx, cart["id"], delivery)
114          conn.execute("UPDATE api_sessions SET cart_id=NULL WHERE owner_id=?", (owner,))
115          result = order_view(conn, order)
116          save_receipt(conn, owner, "checkout", key, shipping, result)
117          return result
```

### Slide 29. Sửa đơn có kiểm soát

_update() nhận mã đơn rõ ràng hoặc yêu cầu trong phiên chỉ có duy nhất một đơn chờ xác nhận.

Nếu nhiều đơn thì hỏi order_reference. Nếu nhiều dòng chưa xác định đích thì hỏi product hoặc hướng dẫn sửa trên web. Toàn bộ đổi biến thể là một transaction: bỏ dòng cũ và thêm biến thể mới, rollback nếu hết hàng hoặc sai sản phẩm.

**Code chứng minh: `backend/chat_service.py:169-175`**

```python
169      if reference:
170          order = owned_order(conn, session["owner_id"], order_number(reference))
171      else:
172          candidates = orders.list_orders(conn, session["owner_id"], statuses=["pending_confirmation"], limit=2)
173          if len(candidates) != 1:
174              return ask(["order_reference"], "Chưa xác định được duy nhất một đơn nháp trong phiên.")
175          order = candidates[0]
```

**Code chứng minh: `backend/services.py:89-90`**

```python
 89          if order["status"] not in {"cart", "pending_confirmation"}:
 90              raise OrderNotEditable("Đơn không còn cho phép chỉnh sửa.")
```

**Code chứng minh: `backend/services.py:96-97`**

```python
 96          if before["product_id"] != after["product_id"]:
 97              raise ValidationError("Chỉ được đổi biến thể thuộc cùng sản phẩm.", field="sku")
```

### Slide 30. Context, audit và chống gửi trùng

Mỗi route cập nhật state hội thoại, lưu metadata và ghi receipt khi có kết quả có thể replay.

Tin user trong conversation_messages được thay bằng placeholder. Logger chỉ ghi meta chứ không log prompt đầy đủ. Tuy nhiên orders, conversation.context khi đang thu thập và receipts có thể chứa giao nhận, nên không tuyên bố hệ thống không lưu PII. failed_validation không lưu receipt để có thể thử lại.

**Code chứng minh: `backend/chat_service.py:309-319`**

```python
309          conversations.add_message(conn, cid, "user", "[Nội dung không lưu; intent=" + str(meta["intent"]) + "]")
310          conversations.add_message(conn, cid, "assistant", result["reply"])
311          meta.update(route=route, latency_ms=round((time.monotonic() - start) * 1000, 2))
312          result["request_id"] = ctx.request_id
313          result["intent"] = meta["intent"]
314          result["interpretation_source"] = meta["interpretation_source"]
315          audit.log_event(conn, ctx, "chat_processed", details=meta)
316          if route != "failed_validation":
317              save_receipt(conn, owner, "chat", key, message, result)
318      import json
319      logger.info(json.dumps(meta, ensure_ascii=False))
```

### Slide 31. Ví dụ balo đã chạy bằng Gemini thật



Bằng chứng là log đã lưu ngày 22/10 trên SQLite thử riêng. Hai lượt model thật có prompt v4, retry 0. Không sử dụng FakeLLM cho con số live này. Đơn thử không nằm trong DB vận hành. Khi demo trên lớp có thể gõ lại câu đầu, sau đó điền form; phụ thuộc quota và mạng ở thời điểm demo.

### Slide 32. Bằng chứng kiểm thử và giới hạn



Các số là kết quả đã lưu trong sample_results/chat_purchase_2026-10-22, không gọi thêm Google để tạo deck. Không dùng 29/29 offline làm độ chính xác Gemini. Rate limiter trong RAM không đồng bộ giữa nhiều process, ledger quota dùng SQLite riêng. Regex/evidence chưa bảo đảm hiểu mọi câu, handoff chưa có hàng đợi nhân viên. Giá/tồn vẫn phải kiểm tra lại khi xác nhận đơn.

### Slide 33. Câu hỏi khi bảo vệ



Khi trả lời, chỉ vào code: client.generate và validate_grounding ở chat_service.py, session kiểm tra lại ở transaction, storage.replay/digest và parser.quantity_source. Không mô tả model có quyền tool tự do hay hệ thống RAG vector vì code hiện tại không triển khai các cơ chế đó.

### Slide 34. Tra cứu toàn bộ 100 hàm



Phần này dùng để tra cứu và giải thích từng hàm, không cần đọc liên tục khi thuyết trình phần chính. Mỗi trang có tối đa hai hàm. Số dòng áp dụng cho snapshot ngày 22/10/2026. Nếu sau này code sửa, tìm theo tên hàm và xem snapshot để đối chiếu.

## Danh mục 100 hàm

| Hàm | Nguồn | Slide |
|---|---|---:|
| `RateLimiter.__init__` | `backend/main.py:32` | 35 |
| `RateLimiter.check` | `backend/main.py:37` | 35 |
| `_error` | `backend/main.py:50` | 36 |
| `create_app` | `backend/main.py:58` | 36 |
| `create_app.lifespan` | `backend/main.py:63` | 37 |
| `create_app.request_context` | `backend/main.py:74` | 37 |
| `create_app.api_error` | `backend/main.py:98` | 38 |
| `create_app.db_error` | `backend/main.py:103` | 38 |
| `create_app.validation_error` | `backend/main.py:108` | 39 |
| `create_app.http_error` | `backend/main.py:117` | 39 |
| `create_app.busy_error` | `backend/main.py:123` | 40 |
| `create_app.db` | `backend/main.py:128` | 40 |
| `create_app.session_db` | `backend/main.py:137` | 41 |
| `create_app.health` | `backend/main.py:145` | 41 |
| `create_app.start_session` | `backend/main.py:152` | 42 |
| `create_app.end_session` | `backend/main.py:159` | 42 |
| `create_app.products` | `backend/main.py:166` | 43 |
| `create_app.product` | `backend/main.py:172` | 43 |
| `create_app.get_cart` | `backend/main.py:178` | 44 |
| `create_app.add_cart_item` | `backend/main.py:184` | 44 |
| `create_app.edit_cart_item` | `backend/main.py:191` | 45 |
| `create_app.delete_cart_item` | `backend/main.py:201` | 45 |
| `create_app.create_order` | `backend/main.py:211` | 46 |
| `create_app.list_orders` | `backend/main.py:218` | 46 |
| `create_app.get_order` | `backend/main.py:225` | 47 |
| `create_app.edit_order_item` | `backend/main.py:231` | 47 |
| `create_app.chat_message` | `backend/main.py:239` | 48 |
| `response` | `backend/chat_service.py:33` | 49 |
| `ask` | `backend/chat_service.py:38` | 49 |
| `_catalog_context` | `backend/chat_service.py:45` | 50 |
| `_merge_items` | `backend/chat_service.py:61` | 50 |
| `resolve_item` | `backend/chat_service.py:77` | 51 |
| `_shipping` | `backend/chat_service.py:102` | 51 |
| `_draft` | `backend/chat_service.py:121` | 52 |
| `_query` | `backend/chat_service.py:160` | 52 |
| `_update` | `backend/chat_service.py:167` | 53 |
| `chat` | `backend/chat_service.py:210` | 53 |
| `LLMError.__init__` | `src/llm_client.py:28` | 54 |
| `_retry_delay` | `src/llm_client.py:33` | 54 |
| `GeminiLLMClient.__init__` | `src/llm_client.py:45` | 55 |
| `GeminiLLMClient.generate` | `src/llm_client.py:50` | 55 |
| `_plain` | `src/llm_client.py:102` | 56 |
| `_span` | `src/llm_client.py:107` | 56 |
| `FakeLLMClient.generate` | `src/llm_client.py:116` | 57 |
| `make_client` | `src/llm_client.py:190` | 57 |
| `build_prompt` | `src/prompts.py:48` | 58 |
| `OutputError.__init__` | `src/parser.py:54` | 59 |
| `_unique_object` | `src/parser.py:58` | 59 |
| `parse_output` | `src/parser.py:67` | 60 |
| `money_amounts` | `src/parser.py:84` | 60 |
| `normalize_money` | `src/parser.py:99` | 61 |
| `quantity_source` | `src/parser.py:104` | 61 |
| `discard_implicit_quantities` | `src/parser.py:118` | 62 |
| `validate_grounding` | `src/parser.py:127` | 62 |
| `validate_grounding.present` | `src/parser.py:130` | 63 |
| `DailyBudget.__init__` | `src/quota.py:13` | 64 |
| `DailyBudget.reserve` | `src/quota.py:22` | 64 |
| `product_view` | `backend/services.py:12` | 65 |
| `order_number` | `backend/services.py:23` | 65 |
| `owned_order` | `backend/services.py:30` | 66 |
| `order_view` | `backend/services.py:38` | 66 |
| `cart_order` | `backend/services.py:57` | 67 |
| `cart_view` | `backend/services.py:69` | 67 |
| `item_row` | `backend/services.py:77` | 68 |
| `update_item` | `backend/services.py:86` | 68 |
| `checkout` | `backend/services.py:103` | 69 |
| `initialize` | `backend/storage.py:35` | 70 |
| `new_session` | `backend/storage.py:48` | 70 |
| `authenticate` | `backend/storage.py:62` | 71 |
| `request_key` | `backend/storage.py:74` | 71 |
| `digest` | `backend/storage.py:81` | 72 |
| `replay` | `backend/storage.py:86` | 72 |
| `save_receipt` | `backend/storage.py:99` | 73 |
| `local_catalog_request` | `backend/catalog_chat.py:10` | 74 |
| `_matches` | `backend/catalog_chat.py:29` | 74 |
| `find_products` | `backend/catalog_chat.py:35` | 75 |
| `catalog_reply` | `backend/catalog_chat.py:71` | 75 |
| `browsing_context` | `backend/catalog_chat.py:102` | 76 |
| `resolve_reference` | `backend/catalog_chat.py:109` | 76 |
| `size_value` | `backend/variant_utils.py:7` | 77 |
| `attribute_value` | `backend/variant_utils.py:12` | 77 |
| `ItemChange.require_change` | `backend/models.py:39` | 78 |
| `Settings.from_env` | `backend/config.py:27` | 79 |
| `ApiProblem.__init__` | `backend/errors.py:6` | 80 |
| `database_problem` | `backend/errors.py:14` | 80 |
| `_seg` | `backend/shop_api.py:11` | 81 |
| `ShopApiMixin.list_products` | `backend/shop_api.py:18` | 81 |
| `ShopApiMixin.get_product` | `backend/shop_api.py:22` | 82 |
| `ShopApiMixin.add_to_cart` | `backend/shop_api.py:27` | 82 |
| `ShopApiMixin.update_cart_item` | `backend/shop_api.py:31` | 83 |
| `ShopApiMixin.remove_cart_item` | `backend/shop_api.py:35` | 83 |
| `category_label` | `backend/shop_logic.py:10` | 84 |
| `normalize` | `backend/shop_logic.py:15` | 84 |
| `filter_products` | `backend/shop_logic.py:22` | 85 |
| `stock_label` | `backend/shop_logic.py:32` | 85 |
| `max_selectable` | `backend/shop_logic.py:41` | 86 |
| `price_text` | `backend/shop_logic.py:47` | 86 |
| `variant_option_label` | `backend/shop_logic.py:54` | 87 |
| `pick_default_variant` | `backend/shop_logic.py:60` | 87 |
| `chunk` | `backend/shop_logic.py:69` | 88 |

## RateLimiter.__init__

**Nguồn:** `backend/main.py:32-34`. **Slide:** 35

**Chức năng:** Khởi tạo bộ đếm request và khóa để nhiều luồng cập nhật an toàn.

**Đầu vào:** `không có tham số ngoài đối tượng`

**Đầu ra/tác động:** Khởi tạo entries và lock trên đối tượng.

```python
    def __init__(self):
        self.entries = {}
        self.lock = threading.Lock()
```

## RateLimiter.check

**Nguồn:** `backend/main.py:37-46`. **Slide:** 35

**Chức năng:** Chặn khi số request của một IP hoặc phiên vượt giới hạn trong 60 giây.

**Đầu vào:** `bucket, identity, limit`

**Đầu ra/tác động:** Không trả dữ liệu, hoặc ném ApiProblem 429.

```python
    def check(self, bucket, identity, limit):
        now = time.monotonic()
        with self.lock:
            self.entries = {k: q for k, q in self.entries.items() if q and q[-1] > now - 60}
            queue = self.entries.setdefault((bucket, identity), deque())
            while queue and queue[0] <= now - 60:
                queue.popleft()
            if len(queue) >= limit:
                raise ApiProblem(429, "rate_limit", "Bạn gửi yêu cầu quá nhanh. Vui lòng thử lại sau một phút.")
            queue.append(now)
```

## _error

**Nguồn:** `backend/main.py:50-54`. **Slide:** 36

**Chức năng:** Đóng gói lỗi thành JSON thống nhất, kèm request ID và thời gian chờ nếu bị giới hạn.

**Đầu vào:** `problem, request_id`

**Đầu ra/tác động:** JSONResponse chứa error, fields và request_id.

```python
def _error(problem, request_id=None):
    headers = {"Retry-After": "60"} if problem.status == 429 else {}
    return JSONResponse(status_code=problem.status, headers=headers,
                        content={"error": {"code": problem.code, "message": problem.message,
                                           "fields": problem.fields}, "request_id": request_id})
```

## create_app

**Nguồn:** `backend/main.py:58-245`. **Slide:** 36

**Chức năng:** Tạo ứng dụng FastAPI, gắn cấu hình, LLM, middleware và các endpoint.

**Đầu vào:** `settings, llm_client`

**Đầu ra/tác động:** Đối tượng FastAPI đã gắn route và middleware.

```python
def create_app(settings=None, llm_client=None):
    settings = settings or Settings.from_env()

    @asynccontextmanager
    # Chuẩn bị database và catalog mẫu trước khi ứng dụng bắt đầu nhận request.
    async def lifespan(app):
        initialize(settings.db_path)
        yield

    app = FastAPI(title="Live Commerce Order Assistant", version="1.0.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.llm_client = llm_client or make_client(settings)
    limiter = RateLimiter()

    @app.middleware("http")
    # Gắn mã theo dõi, giới hạn request/kích thước body và xử lý lỗi chung cho mỗi lượt gọi.
    async def request_context(request, call_next):
        request.state.request_id = uuid.uuid4().hex
        try:
            limiter.check("http", request.client.host if request.client else "local", settings.request_limit)
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 16384:
                    raise ApiProblem(413, "request_too_large", "Nội dung request vượt giới hạn 16 KB.")
            # Starlette reuses the cached body when dispatching to the route.
            request._body = bytes(body)
            response = await call_next(request)
        except ApiProblem as err:
            response = _error(err, request.state.request_id)
        except Exception as err:
            logging.getLogger("shop.api").error(json.dumps({"request_id": request.state.request_id,
                                                           "error_type": type(err).__name__}))
            response = _error(ApiProblem(500, "server", "Máy chủ chưa xử lý được yêu cầu. Vui lòng thử lại."), request.state.request_id)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ApiProblem)
    # Chuyển lỗi nghiệp vụ API thành phản hồi JSON có mã HTTP tương ứng.
    async def api_error(request, err):
        return _error(err, request.state.request_id)

    @app.exception_handler(DataServiceError)
    # Chuyển lỗi từ lớp database thành lỗi API dễ hiểu cho frontend.
    async def db_error(request, err):
        return _error(database_problem(err), request.state.request_id)

    @app.exception_handler(RequestValidationError)
    # Báo các trường đầu vào thiếu, sai kiểu hoặc không được phép gửi.
    async def validation_error(request, err):
        fields = {}
        for error in err.errors():
            name = str(error["loc"][-1])
            fields[name] = "Trường không được phép." if error["type"] == "extra_forbidden" else "Giá trị không hợp lệ hoặc còn thiếu."
        return _error(ApiProblem(422, "validation", "Dữ liệu gửi lên chưa hợp lệ.", fields), request.state.request_id)

    @app.exception_handler(HTTPException)
    # Trả thông báo thống nhất khi endpoint không tồn tại hoặc request không được hỗ trợ.
    async def http_error(request, err):
        return _error(ApiProblem(err.status_code, "not_found" if err.status_code == 404 else "request_error",
                                 "Không tìm thấy endpoint." if err.status_code == 404 else "Yêu cầu không được hỗ trợ."), request.state.request_id)

    @app.exception_handler(sqlite3.OperationalError)
    # Trả lỗi 503 khi SQLite tạm thời không truy cập được để khách có thể thử lại.
    async def busy_error(request, err):
        return _error(ApiProblem(503, "database_unavailable", "Dữ liệu tạm thời chưa truy cập được. Vui lòng thử lại."), request.state.request_id)

    @contextmanager
    # Mở kết nối database cho một khối xử lý và luôn đóng kết nối khi khối kết thúc.
    def db():
        conn = connect(settings.db_path)
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    # Xác thực Bearer token và cung cấp database, phiên cùng thông tin ghi audit.
    def session_db(request):
        with db() as conn:
            session = authenticate(conn, request.headers.get("Authorization"))
            ctx = Ctx("customer", session["owner_id"], request.state.request_id)
            yield conn, session, ctx

    @app.get("/api/health")
    # Kiểm tra database và trả provider/model hiện tại mà không gọi Gemini.
    def health():
        with db() as conn:
            conn.execute("SELECT 1 FROM products LIMIT 1").fetchone()
        return {"status": "ok", "llm_provider": settings.llm_provider, "model_id": app.state.llm_client.model_id}

    @app.post("/api/session", status_code=201)
    # Tạo phiên mua sắm mới sau khi kiểm tra giới hạn tạo phiên theo IP.
    def start_session(request: Request):
        limiter.check("session", request.client.host if request.client else "local", settings.session_limit)
        with db() as conn:
            return new_session(conn, settings.session_ttl)

    @app.delete("/api/session")
    # Thu hồi token của phiên hiện tại để token đó không truy cập tiếp được.
    def end_session(request: Request):
        with session_db(request) as (conn, session, ctx):
            conn.execute("DELETE FROM api_sessions WHERE token_hash=?", (session["token_hash"],))
        return {"revoked": True}

    @app.get("/api/products")
    # Trả danh sách sản phẩm đang bán theo định dạng mà frontend sử dụng.
    def products():
        with db() as conn:
            return {"products": [product_view(p) for p in catalog.list_products(conn)]}

    @app.get("/api/products/{product_id}")
    # Trả chi tiết một sản phẩm cùng giá, biến thể và tồn kho trong database.
    def product(product_id: int):
        with db() as conn:
            return product_view(catalog.get_product(conn, product_id))

    @app.get("/api/cart")
    # Đọc giỏ hàng thuộc phiên đã xác thực; chưa có giỏ thì trả giỏ trống.
    def get_cart(request: Request):
        with session_db(request) as (conn, session, ctx):
            return cart_view(conn, session, ctx)

    @app.post("/api/cart/items")
    # Thêm hoặc gộp sản phẩm vào giỏ của phiên và kiểm tra số lượng, tồn kho.
    def add_cart_item(body: CartItem, request: Request):
        with session_db(request) as (conn, session, ctx), transaction(conn):
            cart = cart_order(conn, session, ctx, create=True)
            return order_view(conn, orders.add_item(conn, ctx, cart["id"], body.sku, body.quantity))

    @app.patch("/api/cart/items/{item_id}")
    # Đổi số lượng của một dòng trong giỏ hiện tại và trả giỏ đã tính lại tiền.
    def edit_cart_item(item_id: str, body: QuantityChange, request: Request):
        with session_db(request) as (conn, session, ctx), transaction(conn):
            cart = cart_order(conn, session, ctx)
            if cart is None:
                raise ApiProblem(404, "not_found", "Giỏ hàng đang trống.")
            row = item_row(conn, cart["id"], item_id)
            return order_view(conn, orders.set_item_quantity(conn, ctx, cart["id"], row["sku"], body.quantity))

    @app.delete("/api/cart/items/{item_id}")
    # Xóa một dòng khỏi giỏ hiện tại và trả trạng thái giỏ sau khi xóa.
    def delete_cart_item(item_id: str, request: Request):
        with session_db(request) as (conn, session, ctx), transaction(conn):
            cart = cart_order(conn, session, ctx)
            if cart is None:
                raise ApiProblem(404, "not_found", "Giỏ hàng đang trống.")
            row = item_row(conn, cart["id"], item_id)
            return order_view(conn, orders.remove_item(conn, ctx, cart["id"], row["sku"]))

    @app.post("/api/orders")
    # Gửi giỏ hàng thành đơn chờ xác nhận, dùng khóa chống tạo trùng nếu được cung cấp.
    def create_order(body: Checkout, request: Request):
        key = request_key(request.headers.get("Idempotency-Key"))
        with session_db(request) as (conn, session, ctx):
            return checkout(conn, ctx, session, body.shipping.model_dump(), key)

    @app.get("/api/orders")
    # Liệt kê tối đa 100 đơn đã gửi của chính phiên hiện tại, không gồm giỏ chưa gửi.
    def list_orders(request: Request):
        with session_db(request) as (conn, session, ctx):
            found = orders.list_orders(conn, session["owner_id"], statuses=["pending_confirmation", "confirmed", "cancelled"], limit=100)
            return {"orders": [order_view(conn, o) for o in found]}

    @app.get("/api/orders/{order_id}")
    # Lấy chi tiết đơn sau khi kiểm tra mã đơn và quyền sở hữu của phiên.
    def get_order(order_id: str, request: Request):
        with session_db(request) as (conn, session, ctx):
            return order_view(conn, owned_order(conn, session["owner_id"], order_number(order_id)))

    @app.patch("/api/orders/{order_id}/items/{item_id}")
    # Cập nhật số lượng hoặc biến thể của một dòng đơn mà phiên được phép sửa.
    def edit_order_item(order_id: str, item_id: str, body: ItemChange, request: Request):
        with session_db(request) as (conn, session, ctx):
            order = update_item(conn, ctx, session["owner_id"], order_number(order_id), item_id,
                                body.model_dump(exclude_unset=True))
            return order_view(conn, order)

    @app.post("/api/chat")
    # Nhận tin nhắn, kiểm tra phiên/giới hạn gọi chat rồi chuyển sang luồng xử lý bot.
    def chat_message(body: ChatRequest, request: Request):
        key = request_key(request.headers.get("Idempotency-Key"))
        with session_db(request) as (conn, session, ctx):
            limiter.check("chat", session["owner_id"], settings.chat_limit)
            return chat(conn, ctx, session, body.message, app.state.llm_client, key)

    return app
```

## create_app.lifespan

**Nguồn:** `backend/main.py:63-65`. **Slide:** 37

**Chức năng:** Chuẩn bị database và catalog mẫu trước khi ứng dụng bắt đầu nhận request.

**Đầu vào:** `app`

**Đầu ra/tác động:** Async context manager khởi tạo DB trước yield.

```python
    async def lifespan(app):
        initialize(settings.db_path)
        yield
```

## create_app.request_context

**Nguồn:** `backend/main.py:74-94`. **Slide:** 37

**Chức năng:** Gắn mã theo dõi, giới hạn request/kích thước body và xử lý lỗi chung cho mỗi lượt gọi.

**Đầu vào:** `request, call_next`

**Đầu ra/tác động:** HTTP response có X-Request-ID và Cache-Control.

```python
    async def request_context(request, call_next):
        request.state.request_id = uuid.uuid4().hex
        try:
            limiter.check("http", request.client.host if request.client else "local", settings.request_limit)
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 16384:
                    raise ApiProblem(413, "request_too_large", "Nội dung request vượt giới hạn 16 KB.")
            # Starlette reuses the cached body when dispatching to the route.
            request._body = bytes(body)
            response = await call_next(request)
        except ApiProblem as err:
            response = _error(err, request.state.request_id)
        except Exception as err:
            logging.getLogger("shop.api").error(json.dumps({"request_id": request.state.request_id,
                                                           "error_type": type(err).__name__}))
            response = _error(ApiProblem(500, "server", "Máy chủ chưa xử lý được yêu cầu. Vui lòng thử lại."), request.state.request_id)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        return response
```

## create_app.api_error

**Nguồn:** `backend/main.py:98-99`. **Slide:** 38

**Chức năng:** Chuyển lỗi nghiệp vụ API thành phản hồi JSON có mã HTTP tương ứng.

**Đầu vào:** `request, err`

**Đầu ra/tác động:** JSON lỗi nghiệp vụ API.

```python
    async def api_error(request, err):
        return _error(err, request.state.request_id)
```

## create_app.db_error

**Nguồn:** `backend/main.py:103-104`. **Slide:** 38

**Chức năng:** Chuyển lỗi từ lớp database thành lỗi API dễ hiểu cho frontend.

**Đầu vào:** `request, err`

**Đầu ra/tác động:** JSON lỗi đã ánh xạ từ database.

```python
    async def db_error(request, err):
        return _error(database_problem(err), request.state.request_id)
```

## create_app.validation_error

**Nguồn:** `backend/main.py:108-113`. **Slide:** 39

**Chức năng:** Báo các trường đầu vào thiếu, sai kiểu hoặc không được phép gửi.

**Đầu vào:** `request, err`

**Đầu ra/tác động:** JSON 422 với lỗi theo tên trường.

```python
    async def validation_error(request, err):
        fields = {}
        for error in err.errors():
            name = str(error["loc"][-1])
            fields[name] = "Trường không được phép." if error["type"] == "extra_forbidden" else "Giá trị không hợp lệ hoặc còn thiếu."
        return _error(ApiProblem(422, "validation", "Dữ liệu gửi lên chưa hợp lệ.", fields), request.state.request_id)
```

## create_app.http_error

**Nguồn:** `backend/main.py:117-119`. **Slide:** 39

**Chức năng:** Trả thông báo thống nhất khi endpoint không tồn tại hoặc request không được hỗ trợ.

**Đầu vào:** `request, err`

**Đầu ra/tác động:** JSON lỗi endpoint hoặc method.

```python
    async def http_error(request, err):
        return _error(ApiProblem(err.status_code, "not_found" if err.status_code == 404 else "request_error",
                                 "Không tìm thấy endpoint." if err.status_code == 404 else "Yêu cầu không được hỗ trợ."), request.state.request_id)
```

## create_app.busy_error

**Nguồn:** `backend/main.py:123-124`. **Slide:** 40

**Chức năng:** Trả lỗi 503 khi SQLite tạm thời không truy cập được để khách có thể thử lại.

**Đầu vào:** `request, err`

**Đầu ra/tác động:** JSON 503 khi SQLite gặp OperationalError.

```python
    async def busy_error(request, err):
        return _error(ApiProblem(503, "database_unavailable", "Dữ liệu tạm thời chưa truy cập được. Vui lòng thử lại."), request.state.request_id)
```

## create_app.db

**Nguồn:** `backend/main.py:128-133`. **Slide:** 40

**Chức năng:** Mở kết nối database cho một khối xử lý và luôn đóng kết nối khi khối kết thúc.

**Đầu vào:** `không có tham số ngoài đối tượng`

**Đầu ra/tác động:** Yield kết nối rồi đóng trong finally.

```python
    def db():
        conn = connect(settings.db_path)
        try:
            yield conn
        finally:
            conn.close()
```

## create_app.session_db

**Nguồn:** `backend/main.py:137-141`. **Slide:** 41

**Chức năng:** Xác thực Bearer token và cung cấp database, phiên cùng thông tin ghi audit.

**Đầu vào:** `request`

**Đầu ra/tác động:** Yield (conn, session, ctx) sau xác thực.

```python
    def session_db(request):
        with db() as conn:
            session = authenticate(conn, request.headers.get("Authorization"))
            ctx = Ctx("customer", session["owner_id"], request.state.request_id)
            yield conn, session, ctx
```

## create_app.health

**Nguồn:** `backend/main.py:145-148`. **Slide:** 41

**Chức năng:** Kiểm tra database và trả provider/model hiện tại mà không gọi Gemini.

**Đầu vào:** `không có tham số ngoài đối tượng`

**Đầu ra/tác động:** status, llm_provider, model_id.

```python
    def health():
        with db() as conn:
            conn.execute("SELECT 1 FROM products LIMIT 1").fetchone()
        return {"status": "ok", "llm_provider": settings.llm_provider, "model_id": app.state.llm_client.model_id}
```

## create_app.start_session

**Nguồn:** `backend/main.py:152-155`. **Slide:** 42

**Chức năng:** Tạo phiên mua sắm mới sau khi kiểm tra giới hạn tạo phiên theo IP.

**Đầu vào:** `request`

**Đầu ra/tác động:** token mới và expires_at.

```python
    def start_session(request: Request):
        limiter.check("session", request.client.host if request.client else "local", settings.session_limit)
        with db() as conn:
            return new_session(conn, settings.session_ttl)
```

## create_app.end_session

**Nguồn:** `backend/main.py:159-162`. **Slide:** 42

**Chức năng:** Thu hồi token của phiên hiện tại để token đó không truy cập tiếp được.

**Đầu vào:** `request`

**Đầu ra/tác động:** {revoked: True}, token không còn dùng được.

```python
    def end_session(request: Request):
        with session_db(request) as (conn, session, ctx):
            conn.execute("DELETE FROM api_sessions WHERE token_hash=?", (session["token_hash"],))
        return {"revoked": True}
```

## create_app.products

**Nguồn:** `backend/main.py:166-168`. **Slide:** 43

**Chức năng:** Trả danh sách sản phẩm đang bán theo định dạng mà frontend sử dụng.

**Đầu vào:** `không có tham số ngoài đối tượng`

**Đầu ra/tác động:** {products: [...]}.

```python
    def products():
        with db() as conn:
            return {"products": [product_view(p) for p in catalog.list_products(conn)]}
```

## create_app.product

**Nguồn:** `backend/main.py:172-174`. **Slide:** 43

**Chức năng:** Trả chi tiết một sản phẩm cùng giá, biến thể và tồn kho trong database.

**Đầu vào:** `product_id`

**Đầu ra/tác động:** Một product_view.

```python
    def product(product_id: int):
        with db() as conn:
            return product_view(catalog.get_product(conn, product_id))
```

## create_app.get_cart

**Nguồn:** `backend/main.py:178-180`. **Slide:** 44

**Chức năng:** Đọc giỏ hàng thuộc phiên đã xác thực; chưa có giỏ thì trả giỏ trống.

**Đầu vào:** `request`

**Đầu ra/tác động:** Giỏ của phiên hoặc giỏ trống.

```python
    def get_cart(request: Request):
        with session_db(request) as (conn, session, ctx):
            return cart_view(conn, session, ctx)
```

## create_app.add_cart_item

**Nguồn:** `backend/main.py:184-187`. **Slide:** 44

**Chức năng:** Thêm hoặc gộp sản phẩm vào giỏ của phiên và kiểm tra số lượng, tồn kho.

**Đầu vào:** `body, request`

**Đầu ra/tác động:** Giỏ đã thêm/gộp hàng.

```python
    def add_cart_item(body: CartItem, request: Request):
        with session_db(request) as (conn, session, ctx), transaction(conn):
            cart = cart_order(conn, session, ctx, create=True)
            return order_view(conn, orders.add_item(conn, ctx, cart["id"], body.sku, body.quantity))
```

## create_app.edit_cart_item

**Nguồn:** `backend/main.py:191-197`. **Slide:** 45

**Chức năng:** Đổi số lượng của một dòng trong giỏ hiện tại và trả giỏ đã tính lại tiền.

**Đầu vào:** `item_id, body, request`

**Đầu ra/tác động:** Giỏ với số lượng và tiền đã tính lại.

```python
    def edit_cart_item(item_id: str, body: QuantityChange, request: Request):
        with session_db(request) as (conn, session, ctx), transaction(conn):
            cart = cart_order(conn, session, ctx)
            if cart is None:
                raise ApiProblem(404, "not_found", "Giỏ hàng đang trống.")
            row = item_row(conn, cart["id"], item_id)
            return order_view(conn, orders.set_item_quantity(conn, ctx, cart["id"], row["sku"], body.quantity))
```

## create_app.delete_cart_item

**Nguồn:** `backend/main.py:201-207`. **Slide:** 45

**Chức năng:** Xóa một dòng khỏi giỏ hiện tại và trả trạng thái giỏ sau khi xóa.

**Đầu vào:** `item_id, request`

**Đầu ra/tác động:** Giỏ sau khi xóa dòng.

```python
    def delete_cart_item(item_id: str, request: Request):
        with session_db(request) as (conn, session, ctx), transaction(conn):
            cart = cart_order(conn, session, ctx)
            if cart is None:
                raise ApiProblem(404, "not_found", "Giỏ hàng đang trống.")
            row = item_row(conn, cart["id"], item_id)
            return order_view(conn, orders.remove_item(conn, ctx, cart["id"], row["sku"]))
```

## create_app.create_order

**Nguồn:** `backend/main.py:211-214`. **Slide:** 46

**Chức năng:** Gửi giỏ hàng thành đơn chờ xác nhận, dùng khóa chống tạo trùng nếu được cung cấp.

**Đầu vào:** `body, request`

**Đầu ra/tác động:** Đơn pending_confirmation hoặc kết quả replay.

```python
    def create_order(body: Checkout, request: Request):
        key = request_key(request.headers.get("Idempotency-Key"))
        with session_db(request) as (conn, session, ctx):
            return checkout(conn, ctx, session, body.shipping.model_dump(), key)
```

## create_app.list_orders

**Nguồn:** `backend/main.py:218-221`. **Slide:** 46

**Chức năng:** Liệt kê tối đa 100 đơn đã gửi của chính phiên hiện tại, không gồm giỏ chưa gửi.

**Đầu vào:** `request`

**Đầu ra/tác động:** {orders: [...]}, tối đa 100 đơn của phiên.

```python
    def list_orders(request: Request):
        with session_db(request) as (conn, session, ctx):
            found = orders.list_orders(conn, session["owner_id"], statuses=["pending_confirmation", "confirmed", "cancelled"], limit=100)
            return {"orders": [order_view(conn, o) for o in found]}
```

## create_app.get_order

**Nguồn:** `backend/main.py:225-227`. **Slide:** 47

**Chức năng:** Lấy chi tiết đơn sau khi kiểm tra mã đơn và quyền sở hữu của phiên.

**Đầu vào:** `order_id, request`

**Đầu ra/tác động:** Đơn đã kiểm tra quyền sở hữu.

```python
    def get_order(order_id: str, request: Request):
        with session_db(request) as (conn, session, ctx):
            return order_view(conn, owned_order(conn, session["owner_id"], order_number(order_id)))
```

## create_app.edit_order_item

**Nguồn:** `backend/main.py:231-235`. **Slide:** 47

**Chức năng:** Cập nhật số lượng hoặc biến thể của một dòng đơn mà phiên được phép sửa.

**Đầu vào:** `order_id, item_id, body, request`

**Đầu ra/tác động:** Đơn sau sửa quantity/SKU.

```python
    def edit_order_item(order_id: str, item_id: str, body: ItemChange, request: Request):
        with session_db(request) as (conn, session, ctx):
            order = update_item(conn, ctx, session["owner_id"], order_number(order_id), item_id,
                                body.model_dump(exclude_unset=True))
            return order_view(conn, order)
```

## create_app.chat_message

**Nguồn:** `backend/main.py:239-243`. **Slide:** 48

**Chức năng:** Nhận tin nhắn, kiểm tra phiên/giới hạn gọi chat rồi chuyển sang luồng xử lý bot.

**Đầu vào:** `body, request`

**Đầu ra/tác động:** Kết quả workflow chat với route và reply.

```python
    def chat_message(body: ChatRequest, request: Request):
        key = request_key(request.headers.get("Idempotency-Key"))
        with session_db(request) as (conn, session, ctx):
            limiter.check("chat", session["owner_id"], settings.chat_limit)
            return chat(conn, ctx, session, body.message, app.state.llm_client, key)
```

## response

**Nguồn:** `backend/chat_service.py:33-34`. **Slide:** 49

**Chức năng:** Tạo cấu trúc phản hồi chat chung gồm lời nhắn, nhánh xử lý, trường thiếu và đơn nếu có.

**Đầu vào:** `reply, route, missing, order`

**Đầu ra/tác động:** Dictionary reply, route, missing_fields, order và phần bổ sung.

```python
def response(reply, route, missing=(), order=None, **extra):
    return {"reply": reply, "route": route, "missing_fields": list(missing), "order": order, **extra}
```

## ask

**Nguồn:** `backend/chat_service.py:38-41`. **Slide:** 49

**Chức năng:** Đổi tên các trường còn thiếu sang tiếng Việt và tạo câu hỏi bổ sung thông tin.

**Đầu vào:** `fields, detail`

**Đầu ra/tác động:** Response ask_missing với nhãn trường bằng tiếng Việt.

```python
def ask(fields, detail=""):
    fields = list(dict.fromkeys(fields))
    text = ", ".join(FIELD_NAMES.get(f, f) for f in fields)
    return response((detail + " Vui lòng bổ sung: " + text + ".").strip(), "ask_missing", fields)
```

## _catalog_context

**Nguồn:** `backend/chat_service.py:45-57`. **Slide:** 50

**Chức năng:** Chọn sản phẩm liên quan từ database làm ngữ cảnh để LLM nhận diện yêu cầu.

**Đầu vào:** `conn, message, context`

**Đầu ra/tác động:** Tối đa 6 sản phẩm, alias và định danh biến thể cho prompt.

```python
def _catalog_context(conn, message, context):
    found = catalog.search_products(conn, message, limit=3)
    for item in context.get("items", []):
        found += catalog.search_products(conn, item.get("requested_product") or item.get("sku"), limit=2)
    if not found:
        found = catalog.list_products(conn, limit=6)
    unique = {p["product_id"]: p for p in found}
    result = []
    for p in list(unique.values())[:6]:
        aliases = [r[0] for r in conn.execute("SELECT alias FROM product_aliases WHERE product_id=? LIMIT 10", (p["product_id"],))]
        result.append({"name": p["name"], "category": p["category"], "description": p["description"], "aliases": aliases,
                       "variants": [{k: v[k] for k in ("sku", "color", "size")} for v in p["variants"]]})
    return result
```

## _merge_items

**Nguồn:** `backend/chat_service.py:61-73`. **Slide:** 50

**Chức năng:** Gộp thông tin bổ sung của cùng một sản phẩm với dữ liệu đã thu thập ở lượt trước.

**Đầu vào:** `previous, incoming`

**Đầu ra/tác động:** Danh sách item đã ghép hoặc danh sách mới.

```python
def _merge_items(previous, incoming):
    if not incoming:
        return previous
    if len(previous) == len(incoming) == 1:
        old, new = previous[0], incoming[0]
        same = not new.get("requested_product") or normalize(new["requested_product"]) == normalize(old.get("requested_product"))
        if same and not (new.get("sku") and old.get("sku") and new["sku"] != old["sku"]):
            variant = {**old["variant"], **{k: v for k, v in new["variant"].items() if v is not None}}
            result = {**old, **{k: v for k, v in new.items() if v is not None}, "variant": variant}
            if any(new["variant"].values()) and not new.get("sku"):
                result["sku"] = None
            return [result]
    return incoming
```

## resolve_item

**Nguồn:** `backend/chat_service.py:77-98`. **Slide:** 51

**Chức năng:** Đối chiếu tên/SKU, màu và size với catalog; hỏi lại khi chưa xác định duy nhất biến thể.

**Đầu vào:** `conn, item`

**Đầu ra/tác động:** (variant, None) hoặc (None, câu hỏi bổ sung).

```python
def resolve_item(conn, item):
    if item.get("sku"):
        candidates = [catalog.get_variant(conn, item["sku"])]
    elif item.get("requested_product"):
        found = catalog.search_products(conn, item["requested_product"], limit=5)
        if not found:
            return None, ask(["product"], "Không tìm thấy sản phẩm trong catalog.")
        close = [p for p in found if found[0]["score"] - p["score"] < 10]
        candidates = [v for p in close for v in p["variants"]]
    else:
        return None, ask(["product"])
    for key in ("color", "size"):
        value = item["variant"].get(key)
        if value:
            requested = attribute_value(value, key)
            candidates = [v for v in candidates if requested == attribute_value(v[key], key)
                          or (key == "color" and attribute_value(v[key], key).startswith(requested + " "))]
    if len(candidates) != 1:
        options = "; ".join(f"{v['sku']} ({v['variant_name']})" for v in candidates[:8])
        detail = "Có nhiều biến thể phù hợp: " + options if candidates else "Không có biến thể khớp màu/size đã yêu cầu."
        return None, ask(["variant"], detail)
    return candidates[0], None
```

## _shipping

**Nguồn:** `backend/chat_service.py:102-117`. **Slide:** 51

**Chức năng:** Kiểm tra tên, điện thoại, địa chỉ và trả giao nhận đã chuẩn hóa hoặc danh sách trường lỗi.

**Đầu vào:** `customer`

**Đầu ra/tác động:** (giao nhận sạch, []) hoặc (None, các trường thiếu/sai).

```python
def _shipping(customer):
    mapped = {"recipient_name": customer.get("name"), "phone": customer.get("phone"), "address": customer.get("address")}
    missing = [k for k, v in mapped.items() if not v]
    if missing:
        return None, missing
    try:
        shipping = Shipping.model_validate(mapped)
    except ValueError:
        return None, [k for k, v in mapped.items() if not v or (k == "address" and len(v) < 10)] or ["recipient_name"]
    from database.shop_db.validation import validate_delivery
    try:
        clean = validate_delivery({"customer_name": shipping.recipient_name, "phone": shipping.phone,
                                   "address": shipping.address}, require_all=True)
    except DataServiceError as err:
        return None, ["recipient_name" if f == "customer_name" else f for f in err.details.get("errors", {})]
    return clean, []
```

## _draft

**Nguồn:** `backend/chat_service.py:121-156`. **Slide:** 52

**Chức năng:** Kiểm tra hàng, số lượng, giao nhận; hỏi phần còn thiếu hoặc tạo đơn nháp từ hội thoại.

**Đầu vào:** `conn, ctx, session, slots, key`

**Đầu ra/tác động:** ask_missing/purchase, out_of_stock hoặc draft_created/order.

```python
def _draft(conn, ctx, session, slots, key):
    items = slots.get("items", [])
    if not items:
        return ask(["product", "quantity"])
    resolved, selected, missing = [], [], []
    for item in items:
        variant, problem = resolve_item(conn, item)
        if problem:
            return problem
        selected.append({"sku": variant["sku"], "name": variant["product_name"],
                         "variant_label": variant["variant_name"], "unit_price": variant["price"],
                         "stock": variant["stock"], "quantity": item.get("quantity")})
        if variant["stock"] <= 0:
            return response(f"Không đủ hàng: {variant['sku']} còn 0. Vui lòng chọn biến thể khác.", "out_of_stock")
        if item.get("quantity") is None:
            missing.append("quantity")
            continue
        resolved.append({"sku": variant["sku"], "quantity": item["quantity"]})
    delivery, delivery_missing = _shipping(slots.get("customer", {}))
    missing.extend(delivery_missing)
    if missing:
        # Validate any explicit quantities even when another line is incomplete.
        stock = catalog.check_items(conn, resolved) if resolved else {"ok": True}
        if stock["ok"]:
            detail = "Đã chọn: " + "; ".join(f"{i['name']} — {i['variant_label']} ({i['unit_price']:,} VND/sản phẩm)" for i in selected) + "."
            result = ask(missing, detail)
            result["purchase"] = {"items": selected}
            return result
    resolved = [{"sku": s, "quantity": q} for s, q in normalize_items(resolved)]
    stock = catalog.check_items(conn, resolved)
    if not stock["ok"]:
        details = "; ".join(f"{r['sku']} còn {r['available']}, bạn yêu cầu {r['requested']}" for r in stock["results"] if not r["ok"])
        return response("Không đủ hàng: " + details + ". Vui lòng chọn lại số lượng hoặc biến thể.", "out_of_stock")
    order = orders.create_draft_order(conn, ctx, session["owner_id"], resolved, delivery, source="chat", idempotency_key=key)
    return response("Đã tạo đơn nháp. Bạn có thể xem và sửa ở trang Đơn hàng; đơn đang chờ xác nhận.",
                    "draft_created", order=order_view(conn, order))
```

## _query

**Nguồn:** `backend/chat_service.py:160-163`. **Slide:** 52

**Chức năng:** Yêu cầu tên sản phẩm nếu chưa rõ, rồi trả thông tin catalog, giá hoặc tồn kho từ database.

**Đầu vào:** `conn, items, intent, filters`

**Đầu ra/tác động:** Câu hỏi tên hàng hoặc kết quả giá/tồn/catalog từ DB.

```python
def _query(conn, items, intent, filters):
    if not items or any(not i.get("requested_product") and not i.get("sku") for i in items):
        return ask(["product"])
    return catalog_reply(conn, items, filters, intent)
```

## _update

**Nguồn:** `backend/chat_service.py:167-206`. **Slide:** 53

**Chức năng:** Xác định đúng đơn/dòng hàng được phép sửa và cập nhật số lượng hoặc biến thể theo yêu cầu.

**Đầu vào:** `conn, ctx, session, slots`

**Đầu ra/tác động:** order_updated hoặc câu hỏi làm rõ đích sửa.

```python
def _update(conn, ctx, session, slots):
    reference = slots.get("order_reference")
    if reference:
        order = owned_order(conn, session["owner_id"], order_number(reference))
    else:
        candidates = orders.list_orders(conn, session["owner_id"], statuses=["pending_confirmation"], limit=2)
        if len(candidates) != 1:
            return ask(["order_reference"], "Chưa xác định được duy nhất một đơn nháp trong phiên.")
        order = candidates[0]
    changes = slots.get("items", [])
    if len(changes) != 1:
        return ask(["product", "quantity"], "Mỗi lượt sửa một dòng sản phẩm để tránh nhầm đơn.")
    item = changes[0]
    if item.get("quantity") is None and not any(item["variant"].values()) and not item.get("sku"):
        return ask(["quantity", "variant"])
    lines = order_view(conn, order)["items"]
    target_variant = None
    if item.get("sku") or item.get("requested_product"):
        target_variant, problem = resolve_item(conn, item)
        if problem:
            return problem
        lines = [line for line in lines if catalog.get_variant(conn, line["sku"])["product_id"] == target_variant["product_id"]]
    if len(lines) != 1:
        return ask(["product"], "Đơn có nhiều dòng hoặc chưa xác định được dòng cần sửa. Hãy nêu SKU hiện tại hoặc sửa trên web.")
    line = lines[0]
    updates = {}
    if target_variant:
        updates["sku"] = target_variant["sku"]
    elif any(item["variant"].values()):
        current = catalog.get_variant(conn, line["sku"])
        desired = {"requested_product": current["product_name"], "sku": None,
                   "variant": {k: item["variant"].get(k) or current[k] for k in ("color", "size")}}
        target_variant, problem = resolve_item(conn, desired)
        if problem:
            return problem
        updates["sku"] = target_variant["sku"]
    if item.get("quantity") is not None:
        updates["quantity"] = item["quantity"]
    updated = update_item(conn, ctx, session["owner_id"], order["id"], line["item_id"], updates)
    return response("Đã cập nhật đơn nháp và kiểm tra lại tồn kho.", "order_updated", order=order_view(conn, updated))
```

## chat

**Nguồn:** `backend/chat_service.py:210-320`. **Slide:** 53

**Chức năng:** Điều phối toàn bộ lượt chat: chống gửi trùng, gọi LLM, kiểm tra dữ liệu, xử lý đơn và ghi audit.

**Đầu vào:** `conn, ctx, session, message, client, key`

**Đầu ra/tác động:** Response chat, cập nhật context, receipt và audit trong DB.

```python
def chat(conn, ctx, session, message, client, key):
    start = time.monotonic()
    owner, cid = session["owner_id"], session["conversation_id"]
    cached = replay(conn, owner, "chat", key, message)
    if cached:
        return cached
    conv = conversations.get_conversation(conn, cid)
    if conv["owner_id"] != owner:
        raise ApiProblem(404, "not_found", "Không tìm thấy hội thoại trong phiên.")
    revision = conn.execute("SELECT COALESCE(MAX(id),0) FROM conversation_messages WHERE conversation_id=?", (cid,)).fetchone()[0]
    result, data, llm = None, None, None
    meta = {"timestamp": datetime.now(timezone.utc).isoformat(), "request_id": ctx.request_id,
            "model_id": client.model_id, "prompt_template_version": PROMPT_VERSION,
            "intent": None, "validation_status": "passed", "input_tokens": None,
            "output_tokens": None, "retry_count": 0, "error_type": None,
            "interpretation_source": "gemini" if client.model_id.startswith("gemini-") else "fake"}
    if UNSAFE.search(normalize(message)):
        result = response("Yêu cầu này cần nhân viên xem lại. Hệ thống chưa thay đổi đơn hàng.", "handoff")
        meta.update(intent="unknown_or_handoff", model_id="local-policy", interpretation_source="local_policy")
    elif (local := local_catalog_request(message)) is not None:
        data = local
        meta.update(intent=data.intent, model_id="local-catalog", interpretation_source="local_catalog")
    else:
        try:
            context = {**conv["context"], "pending_intent": conv["pending_intent"]}
            context["recent_products"] = [{"name": p["name"], "category": p["category"]}
                                          for p in (catalog.get_product(conn, pid) for pid in context.get("catalog_product_ids", [])[:8])]
            llm = client.generate(message, _catalog_context(conn, message, context), context)
            meta.update(input_tokens=llm.input_tokens, output_tokens=llm.output_tokens, retry_count=llm.retry_count)
            parsed = parse_output(llm.text)
            quantities = [item.quantity for item in parsed.items]
            data = validate_grounding(discard_implicit_quantities(parsed, message), message)
            meta["discarded_implicit_quantity"] = quantities != [item.quantity for item in data.items]
            meta["intent"] = data.intent
        except (OutputError, LLMError) as err:
            meta.update(validation_status="failed", error_type=err.code, retry_count=getattr(err, "retry_count", 0))
            if err.code == "llm_daily_limit":
                explanation = "Đã chạm giới hạn gọi AI theo ngày của ứng dụng. Bạn vẫn có thể xem sản phẩm trên web hoặc hỏi cửa hàng bán những gì."
            elif err.code == "llm_rate_limit":
                explanation = "Dịch vụ AI đang giới hạn lượt yêu cầu. Vui lòng đợi khoảng một phút rồi gửi lại."
            elif err.code == "llm_timeout":
                explanation = "Dịch vụ AI phản hồi quá chậm. Vui lòng thử lại sau ít phút."
            else:
                explanation = "Chưa xử lý được tin nhắn do lỗi dịch vụ AI hoặc dữ liệu trả về không hợp lệ. Vui lòng thử lại."
            result = response(explanation + " Đơn hàng chưa thay đổi.", "failed_validation", error_type=err.code)
    with transaction(conn):
        active = conn.execute("SELECT 1 FROM api_sessions WHERE token_hash=? AND expires_at>?",
                              (session["token_hash"], int(time.time()))).fetchone()
        if active is None:
            raise ApiProblem(401, "auth", "Phiên đã hết hạn hoặc bị thu hồi trong lúc xử lý. Vui lòng mở phiên mới.")
        cached = replay(conn, owner, "chat", key, message)
        if cached:
            return cached
        latest = conn.execute("SELECT COALESCE(MAX(id),0) FROM conversation_messages WHERE conversation_id=?", (cid,)).fetchone()[0]
        if revision != latest:
            raise ApiProblem(409, "conversation_busy", "Hội thoại vừa thay đổi. Vui lòng gửi lại sau khi tin trước xử lý xong.")
        slots = conv["context"]
        if data:
            if data.requires_human_review or data.confidence == "low" or data.intent == "unknown_or_handoff":
                result = response("Chưa đủ căn cứ xử lý tự động. Vui lòng nêu sản phẩm và yêu cầu cụ thể hoặc nhờ nhân viên hỗ trợ.", "handoff")
            else:
                continuing = data.intent == conv["pending_intent"]
                previous = slots if continuing else {}
                incoming = [i.model_dump() for i in data.items]
                if data.intent in {"create_order", "browse_catalog", "check_price", "check_stock"}:
                    if not incoming and data.intent in {"check_price", "check_stock"}:
                        incoming = [{"requested_product": None, "sku": None, "variant": {"color": None, "size": None}, "quantity": None}]
                    incoming = resolve_reference(conn, incoming, conv["context"], message)
                slots = {"items": _merge_items(previous.get("items", []), incoming),
                         "customer": {**previous.get("customer", {}), **{k: v for k, v in data.customer.model_dump().items() if v is not None}},
                         "order_reference": data.order_reference or previous.get("order_reference")}
                if data.intent in {"check_price", "check_stock"} and not any(i.get("requested_product") or i.get("sku") for i in incoming):
                    slots["items"] = _merge_items(conv["context"].get("items", []), incoming)
                if data.intent == "browse_catalog":
                    result = catalog_reply(conn, incoming, data.catalog_filters, data.intent)
                elif data.intent == "create_order":
                    result = _draft(conn, ctx, session, slots, key)
                elif data.intent == "update_order":
                    result = _update(conn, ctx, session, slots)
                else:
                    result = _query(conn, slots["items"], data.intent, data.catalog_filters)
                if data.intent in READ_INTENTS:
                    saved = browsing_context(result) if "products" in result else {}
                    if conv["pending_intent"] in {"create_order", "update_order"}:
                        slots = {**conv["context"], **saved}
                    else:
                        slots = {**conv["context"], **slots, **saved}
        route = result["route"]
        if route == "handoff":
            conversations.update_conversation(conn, cid, context={}, state="handoff", pending_intent=None)
        elif route in {"draft_created", "order_updated"}:
            conversations.update_conversation(conn, cid, context={}, state="awaiting_confirmation", pending_intent=None,
                                              last_order_id=order_number(result["order"]["order_id"]))
        elif data and route != "failed_validation":
            if data.intent in READ_INTENTS:
                pending = conv["pending_intent"] if conv["pending_intent"] in {"create_order", "update_order"} else None
            else:
                pending = data.intent
            conversations.update_conversation(conn, cid, context=slots, state="collecting_info" if pending else "idle", pending_intent=pending)
        conversations.add_message(conn, cid, "user", "[Nội dung không lưu; intent=" + str(meta["intent"]) + "]")
        conversations.add_message(conn, cid, "assistant", result["reply"])
        meta.update(route=route, latency_ms=round((time.monotonic() - start) * 1000, 2))
        result["request_id"] = ctx.request_id
        result["intent"] = meta["intent"]
        result["interpretation_source"] = meta["interpretation_source"]
        audit.log_event(conn, ctx, "chat_processed", details=meta)
        if route != "failed_validation":
            save_receipt(conn, owner, "chat", key, message, result)
    import json
    logger.info(json.dumps(meta, ensure_ascii=False))
    return result
```

## LLMError.__init__

**Nguồn:** `src/llm_client.py:28-30`. **Slide:** 54

**Chức năng:** Đóng gói mã lỗi provider và số lần retry để workflow trả thông báo phù hợp.

**Đầu vào:** `code, retry_count`

**Đầu ra/tác động:** Đối tượng lỗi có code và retry_count.

```python
    def __init__(self, code, retry_count=0):
        self.code = code
        self.retry_count = retry_count
```

## _retry_delay

**Nguồn:** `src/llm_client.py:33-41`. **Slide:** 54

**Chức năng:** Tính thời gian chờ từ Retry-After dạng giây hoặc ngày giờ, kết hợp backoff theo lượt.

**Đầu vào:** `header, attempt`

**Đầu ra/tác động:** Số giây cần chờ trước retry.

```python
def _retry_delay(header, attempt):
    try:
        seconds = float(header)
    except (ValueError, TypeError):
        try:
            seconds = (parsedate_to_datetime(header) - datetime.now(timezone.utc)).total_seconds()
        except (ValueError, TypeError, OverflowError):
            seconds = 0
    return max(0.25 * 2 ** attempt, seconds)
```

## GeminiLLMClient.__init__

**Nguồn:** `src/llm_client.py:45-48`. **Slide:** 55

**Chức năng:** Gắn cấu hình/model và khởi tạo bộ đếm ngân sách ngày nếu có đường dẫn ledger.

**Đầu vào:** `settings`

**Đầu ra/tác động:** Client giữ settings, model_id và DailyBudget/None.

```python
    def __init__(self, settings):
        self.settings = settings
        self.model_id = settings.model_id
        self.budget = DailyBudget(settings.llm_usage_path, settings.llm_daily_limit) if settings.llm_usage_path else None
```

## GeminiLLMClient.generate

**Nguồn:** `src/llm_client.py:50-99`. **Slide:** 55

**Chức năng:** Ghép prompt, giữ ngân sách, gọi Gemini REST, kiểm tra response và trả văn bản JSON cùng usage.

**Đầu vào:** `message, catalog, context`

**Đầu ra/tác động:** LLMResult(text, input_tokens, output_tokens, retry_count).

```python
    def generate(self, message, catalog, context):
        system, prompt = build_prompt(message, catalog, context)
        url = "https://generativelanguage.googleapis.com/v1beta/models/" + quote(self.model_id, safe="-") + ":generateContent"
        payload = {"systemInstruction": {"parts": [{"text": system}]},
                   "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                   "generationConfig": {"temperature": 0, "maxOutputTokens": 2048,
                                        "responseFormat": {"text": {"mimeType": "APPLICATION_JSON",
                                                                    "schema": Extraction.model_json_schema()}}}}
        for attempt in range(self.settings.llm_max_retries + 1):
            if self.budget:
                try:
                    self.budget.reserve(self.model_id)
                except DailyLimitReached:
                    raise LLMError("llm_daily_limit", attempt) from None
            header = None
            try:
                response = requests.post(url, headers={"x-goog-api-key": self.settings.api_key}, json=payload,
                                         timeout=self.settings.llm_timeout, allow_redirects=False)
            except (requests.Timeout, requests.ConnectionError):
                error = "llm_timeout"
            except requests.RequestException:
                raise LLMError("llm_transport", attempt) from None
            else:
                if response.status_code == 429 or 500 <= response.status_code <= 599:
                    error = "llm_rate_limit" if response.status_code == 429 else "llm_unavailable"
                    header = response.headers.get("Retry-After")
                elif response.status_code != 200:
                    code = "llm_auth" if response.status_code in {401, 403} else "llm_request"
                    raise LLMError(code, attempt)
                else:
                    try:
                        body = response.json()
                        if body.get("promptFeedback", {}).get("blockReason"):
                            raise LLMError("llm_refusal", attempt)
                        candidate = body["candidates"][0]
                        if candidate.get("finishReason") != "STOP":
                            raise LLMError("llm_refusal", attempt)
                        parts = candidate["content"]["parts"]
                        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
                        usage = body.get("usageMetadata", {})
                        return LLMResult(text, usage.get("promptTokenCount"), usage.get("candidatesTokenCount"), attempt)
                    except (AttributeError, KeyError, IndexError, TypeError, ValueError):
                        raise LLMError("llm_response", attempt) from None
            if attempt >= self.settings.llm_max_retries:
                raise LLMError(error, attempt)
            delay = _retry_delay(header, attempt)
            if delay > 3:
                # Return a recoverable error rather than retrying before the provider permits it.
                raise LLMError(error, attempt)
            time.sleep(delay)
```

## _plain

**Nguồn:** `src/llm_client.py:102-104`. **Slide:** 56

**Chức năng:** Bỏ dấu và chuyển chữ thường để FakeLLM nhận diện các mẫu câu bằng regex.

**Đầu vào:** `text`

**Đầu ra/tác động:** Chuỗi không dấu để chạy regex.

```python
def _plain(text):
    text = unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
    return "".join(c for c in text if unicodedata.category(c) != "Mn")
```

## _span

**Nguồn:** `src/llm_client.py:107-109`. **Slide:** 56

**Chức năng:** Tìm nhóm regex trên bản không dấu rồi lấy lại đoạn nguyên văn tương ứng trong tin nhắn.

**Đầu vào:** `text, pattern`

**Đầu ra/tác động:** Đoạn chữ nguyên văn hoặc None.

```python
def _span(text, pattern):
    match = re.search(pattern, _plain(text), flags=re.I)
    return text[match.start(1):match.end(1)].strip() if match else None
```

## FakeLLMClient.generate

**Nguồn:** `src/llm_client.py:116-187`. **Slide:** 57

**Chức năng:** Trích xuất theo rule cho demo và test offline, tạo JSON cùng schema với Gemini.

**Đầu vào:** `message, catalog, context`

**Đầu ra/tác động:** LLMResult chứa JSON rule-based, không gọi mạng.

```python
    def generate(self, message, catalog, context):
        text = _plain(message)
        pending = context.get("pending_intent")
        if re.search(r"\b(doi|sua|cap nhat)\b", text):
            intent = "update_order"
        elif re.search(r"\b(ban (?:nhung )?gi|tham khao|catalog|cho.*xem|tim|tu van|gioi thieu)\b", text):
            intent = "browse_catalog"
        elif re.search(r"\b(gia|bao nhieu tien)\b", text):
            intent = "check_price"
        elif re.search(r"\b(con|ton kho|het hang)\b", text):
            intent = "check_stock"
        elif re.search(r"\b(chot|mua|lay|dat)\b|\bcho\s+(?:em|anh|chi|toi|minh)\s+(?:\d+|mot|hai|ba|bon|nam|sau|bay|tam|chin|muoi)\b", text):
            intent = "create_order"
        elif re.search(r"\b(ban (?:nhung )?gi|tham khao|san pham|catalog|cho.*xem|tim|tu van|gioi thieu|mau nao|size nao|mau gi|thong tin)\b", text):
            intent = "browse_catalog"
        else:
            intent = pending or "unknown_or_handoff"
        name = _span(message, r"(?:ten(?: la)?|nguoi nhan)\s*[:=]?\s*([^,;\d]+)")
        phone = _span(message, r"(?<!\d)((?:\+84|0)[\d .-]{8,16}\d)(?!\d)")
        address = _span(message, r"(?:giao (?:ve|den)|dia chi)\s*[:=]?\s*([^;]+)")
        reference = _span(message, r"\b(DH\d{6,10})\b")
        items = []
        item_text = re.split(r"(?:,\s*)?(?:ten|nguoi nhan|sdt|so dien thoai|giao ve|giao den|dia chi)\b", text)[0]
        original_items = message[:len(item_text)]
        chunks = re.split(r"\s+và\s+|;|,\s*(?=\d+\s+(?:áo|giày|dép|nón|balo))", original_items, flags=re.I)
        colors = ["xanh navy", "trắng", "đen", "xám", "xanh", "đỏ", "vàng"]
        for chunk in chunks:
            plain = _plain(chunk)
            aliases = [alias for p in catalog for alias in [p["name"], *p.get("aliases", [])]
                       if re.search(r"(?<!\w)" + re.escape(_plain(alias)) + r"(?!\w)", plain)]
            alias = max(aliases, key=len) if aliases else None
            if not alias and intent == "browse_catalog":
                categories = {p.get("category", "") for p in catalog} - {""}
                alias = next((c for c in sorted(categories) if re.search(r"\b" + re.escape(_plain(c)) + r"\b", plain)), None)
            sku = _span(chunk, r"\b([A-Z][A-Z0-9]*-[A-Z0-9]+-[A-Z0-9]+)\b")
            color = next((_span(chunk, r"\b(" + re.escape(_plain(c)) + r")\b") for c in colors
                          if re.search(r"\b" + re.escape(_plain(c)) + r"\b", plain)), None)
            size = _span(chunk, r"\bsize\s+([a-z0-9]+)\b")
            if re.search(r"\b\d+(?:[.,]\d+)?\s*(?:inch|inches)\b", plain):
                size = _span(chunk, r"\b(\d+(?:[.,]\d+)?\s*(?:inches|inch))\b")
            qty_text = _span(chunk, r"(?:\bchot|\bmua|\blay|\bdat|\bthanh|\bcon|\bso luong|\bcho\s+(?:em|anh|chi|toi|minh))\s*[:=]?\s+(-?\d+(?:[.,]\d+)?|mot|hai|ba|bon|nam|sau|bay|tam|chin|muoi)\b")
            if qty_text is None:
                qty_text = _span(chunk, r"^\s*(\d+)\s+")
            qty = NUMBER_WORDS.get(_plain(qty_text or ""))
            if qty_text and qty is None:
                try:
                    qty = int(qty_text)
                except ValueError:
                    qty = 0
            requested = _span(chunk, "(" + re.escape(_plain(alias)) + ")") if alias else None
            if intent == "browse_catalog" and not requested:
                candidate = _span(chunk, r"(?:tim|xem|thong tin ve)\s+(.+?)(?=\s+(?:duoi|tren|tu|con hang)\b|[,;?]|$)")
                if candidate and normalize(candidate) not in {"san pham", "catalog", "danh muc san pham", "hang"}:
                    requested = candidate
            if requested or sku or color or size or qty is not None:
                items.append({"requested_product": requested, "sku": sku.upper() if sku else None,
                              "variant": {"color": color, "size": size}, "quantity": qty})
            elif intent in {"create_order", "check_stock", "check_price"} and plain.strip():
                generic = normalize(chunk) in {"gia bao nhieu", "con hang khong", "con khong"}
                items.append({"requested_product": None if generic else chunk.strip()[:180], "sku": None,
                              "variant": {"color": None, "size": None}, "quantity": None})
        minimum = _span(message, r"(?:tu|tren|it nhat)\s+(\d+(?:[.,]\d+)*\s*(?:k|nghin|ngan|trieu|tr)?)\b")
        maximum = _span(message, r"(?:duoi|toi da|khong qua)\s+(\d+(?:[.,]\d+)*\s*(?:k|nghin|ngan|trieu|tr)?)\b")
        result = {"intent": intent, "confidence": "low" if intent == "unknown_or_handoff" else "high",
                  "items": items, "customer": {"name": name, "phone": phone, "address": address},
                  "order_reference": reference.upper() if reference else None,
                  "missing_information": [], "requires_human_review": intent == "unknown_or_handoff",
                  "evidence": [message if len(message) <= 200 else message[:200].rsplit(" ", 1)[0]],
                  "catalog_filters": {"category": None, "min_price": next(iter(money_amounts(minimum)), None) if minimum else None,
                                      "max_price": next(iter(money_amounts(maximum)), None) if maximum else None,
                                      "in_stock_only": "con hang" in text or "co san" in text}}
        return LLMResult(json.dumps(result, ensure_ascii=False))
```

## make_client

**Nguồn:** `src/llm_client.py:190-191`. **Slide:** 57

**Chức năng:** Chọn GeminiLLMClient hoặc FakeLLMClient theo cấu hình provider.

**Đầu vào:** `settings`

**Đầu ra/tác động:** Client Gemini hoặc FakeLLM theo settings.

```python
def make_client(settings):
    return GeminiLLMClient(settings) if settings.llm_provider == "gemini" else FakeLLMClient()
```

## build_prompt

**Nguồn:** `src/prompts.py:48-54`. **Slide:** 58

**Chức năng:** Ghép message, catalog và context có giới hạn thành JSON, trả riêng system prompt và user payload.

**Đầu vào:** `message, catalog, context`

**Đầu ra/tác động:** Tuple (SYSTEM_PROMPT, JSON payload).

```python
def build_prompt(message, catalog, context):
    safe_context = {"pending_intent": context.get("pending_intent"),
                    "pending_items": context.get("items", []),
                    "recent_products": context.get("recent_products", [])}
    payload = {"CUSTOMER_MESSAGE": message, "CATALOG_CONTEXT": catalog,
               "CONVERSATION_CONTEXT": safe_context, "OUTPUT_SCHEMA": Extraction.model_json_schema()}
    return SYSTEM_PROMPT, json.dumps(payload, ensure_ascii=False)
```

## OutputError.__init__

**Nguồn:** `src/parser.py:54-55`. **Slide:** 59

**Chức năng:** Gắn mã lỗi kiểm tra output để workflow phân biệt lỗi JSON, schema và evidence.

**Đầu vào:** `code`

**Đầu ra/tác động:** Đối tượng lỗi output có code.

```python
    def __init__(self, code):
        self.code = code
```

## _unique_object

**Nguồn:** `src/parser.py:58-64`. **Slide:** 59

**Chức năng:** Phát hiện khóa JSON lặp trong cùng một object và từ chối kết quả đó.

**Đầu vào:** `pairs`

**Đầu ra/tác động:** Dictionary không có khóa trùng hoặc ValueError.

```python
def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result
```

## parse_output

**Nguồn:** `src/parser.py:67-78`. **Slide:** 60

**Chức năng:** Giới hạn kích thước, parse JSON nghiêm ngặt và kiểm tra đối tượng Extraction bằng Pydantic.

**Đầu vào:** `raw`

**Đầu ra/tác động:** Extraction hợp schema hoặc OutputError.

```python
def parse_output(raw):
    if not isinstance(raw, str) or not raw.strip() or len(raw) > 16000:
        raise OutputError("invalid_json")
    try:
        value = json.loads(raw, object_pairs_hook=_unique_object,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError("non-finite")))
    except (ValueError, RecursionError):
        raise OutputError("invalid_json") from None
    try:
        return Extraction.model_validate(value)
    except ValidationError:
        raise OutputError("invalid_schema") from None
```

## money_amounts

**Nguồn:** `src/parser.py:84-96`. **Slide:** 60

**Chức năng:** Trích các mức tiền khách thực sự nêu, đổi k/nghìn/triệu thành số nguyên VND.

**Đầu vào:** `text`

**Đầu ra/tác động:** Tập các số tiền nguyên VND có trong câu.

```python
def money_amounts(text):
    matches = re.findall(r"(?<![a-z0-9])(\d+(?:[.,]\d+)*)\s*(trieu|tr|nghin|ngan|k)?\b", normalize_money(text))
    amounts = set()
    for number, unit in matches:
        if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", number):
            number = number.replace(",", "").replace(".", "")
        try:
            value = float(number.replace(",", ".")) * ({"trieu": 1000000, "tr": 1000000, "nghin": 1000, "ngan": 1000, "k": 1000}.get(unit, 1))
            if value.is_integer():
                amounts.add(int(value))
        except ValueError:
            continue
    return amounts
```

## normalize_money

**Nguồn:** `src/parser.py:99-101`. **Slide:** 61

**Chức năng:** Bỏ dấu và chuyển chữ thường nhưng giữ dấu thập phân để đọc các biểu thức tiền.

**Đầu vào:** `text`

**Đầu ra/tác động:** Chuỗi không dấu vẫn giữ ký hiệu tiền/số.

```python
def normalize_money(text):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", text.lower().replace("đ", "d")) if unicodedata.category(c) != "Mn")
```

## quantity_source

**Nguồn:** `src/parser.py:104-115`. **Slide:** 61

**Chức năng:** Loại phần giao nhận, SKU và số đo khỏi nguồn kiểm tra số lượng, đánh dấu lượng âm/lẻ.

**Đầu vào:** `message, customer`

**Đầu ra/tác động:** Chuỗi chỉ phục vụ kiểm tra evidence số lượng.

```python
def quantity_source(message, customer=None):
    text = normalize_money(message)
    text = re.split(r"\b(?:ten|nguoi nhan|sdt|so dien thoai|giao ve|giao den|dia chi)\b", text)[0]
    if customer:
        for value in customer.model_dump().values():
            if value:
                text = text.replace(normalize_money(value), " ")
    text = re.sub(r"\b[a-z][a-z0-9]*(?:-[a-z0-9]+){2,}\b", " ", text)
    text = re.sub(r"\b\d+(?:[.,]\d+)?\s*(?:inches|inch|cm|mm|kg|g|ml)\b", " ", text)
    text = re.sub(r"\bsize\s+[a-z0-9]+\b", " ", text)
    text = re.sub(r"(?<!\w)-\d+(?:[.,]\d+)?|\b\d+[.,]\d+\b", " invalidquantity ", text)
    return " " + normalize(text) + " "
```

## discard_implicit_quantities

**Nguồn:** `src/parser.py:118-124`. **Slide:** 62

**Chức năng:** Bỏ số lượng do model tự điền khi khách không nêu lượng, để workflow hỏi lại.

**Đầu vào:** `data, message`

**Đầu ra/tác động:** Extraction với quantity chưa nêu đã về None.

```python
def discard_implicit_quantities(data, message):
    source = quantity_source(message, data.customer)
    explicit = " invalidquantity " in source or re.search(r"\b\d+\b", source) or any(" " + word + " " in source for word in NUMBER_WORDS)
    if data.intent in {"create_order", "update_order"} and not explicit:
        for item in data.items:
            item.quantity = None
    return data
```

## validate_grounding

**Nguồn:** `src/parser.py:127-163`. **Slide:** 62

**Chức năng:** Kiểm tra các trường và bộ lọc bám câu hiện tại trước khi gộp vào context phía server.

**Đầu vào:** `data, message`

**Đầu ra/tác động:** Extraction đã kiểm tra hoặc OutputError.

```python
def validate_grounding(data, message):
    """Reject invented fields before merging them into server-owned conversation state."""
    text = " " + normalize(message) + " "
    def present(value):
        return value is None or (normalize(value) and " " + normalize(value) + " " in text)
    for item in data.items:
        if not all(present(v) for v in (item.requested_product, item.sku, item.variant.color)):
            raise OutputError("ungrounded_output")
        if item.variant.size and not present(item.variant.size):
            if " " + size_value(item.variant.size) + " " not in " " + size_value(message) + " ":
                raise OutputError("ungrounded_output")
        if item.quantity is not None:
            words = [w for w, n in NUMBER_WORDS.items() if n == item.quantity]
            if not any(" " + q + " " in quantity_source(message, data.customer) for q in [str(item.quantity), *words]):
                raise OutputError("ungrounded_output")
    if not all(present(v) for v in (data.customer.name, data.customer.address, data.order_reference)):
        raise OutputError("ungrounded_output")
    if data.customer.phone:
        phone = re.sub(r"\D", "", data.customer.phone)
        source = re.sub(r"[ .+\-]", "", message)
        if not phone or phone not in source:
            raise OutputError("ungrounded_output")
    if any(not present(e) for e in data.evidence):
        raise OutputError("ungrounded_output")
    filters = data.catalog_filters
    if not present(filters.category):
        raise OutputError("ungrounded_output")
    amounts = money_amounts(message)
    if any(p is not None and p not in amounts for p in (filters.min_price, filters.max_price)):
        raise OutputError("ungrounded_output")
    if filters.min_price is not None and filters.max_price is not None and filters.min_price > filters.max_price:
        raise OutputError("invalid_price_range")
    if filters.in_stock_only and not any(p in text for p in (" con hang ", " co san ", " dang co hang ")):
        raise OutputError("ungrounded_output")
    if (data.items or any(data.customer.model_dump().values()) or data.order_reference) and not data.evidence:
        raise OutputError("missing_evidence")
    return data
```

## validate_grounding.present

**Nguồn:** `src/parser.py:130-131`. **Slide:** 63

**Chức năng:** Kiểm tra giá trị null hoặc chuỗi đã chuẩn hóa có xuất hiện thành đoạn trong câu khách.

**Đầu vào:** `value`

**Đầu ra/tác động:** Boolean trường null hoặc có đoạn văn bản tương ứng.

```python
    def present(value):
        return value is None or (normalize(value) and " " + normalize(value) + " " in text)
```

## DailyBudget.__init__

**Nguồn:** `src/quota.py:13-20`. **Slide:** 64

**Chức năng:** Chuẩn bị ledger SQLite riêng và bảng lưu số HTTP attempt theo model/ngày.

**Đầu vào:** `path, limit`

**Đầu ra/tác động:** Ledger có bảng llm_daily_usage.

```python
    def __init__(self, path, limit):
        self.path = str(path)
        self.limit = limit
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("CREATE TABLE IF NOT EXISTS llm_daily_usage ("
                         "model_id TEXT NOT NULL, quota_day TEXT NOT NULL, attempts INTEGER NOT NULL,"
                         "PRIMARY KEY(model_id,quota_day))")
```

## DailyBudget.reserve

**Nguồn:** `src/quota.py:22-32`. **Slide:** 64

**Chức năng:** Giữ một lượt gọi trước khi gửi HTTP, chặn vượt ngân sách trong transaction theo ngày Pacific.

**Đầu vào:** `model_id, now`

**Đầu ra/tác động:** Số lượt đã dùng sau tăng, hoặc DailyLimitReached.

```python
    def reserve(self, model_id, now=None):
        day = (now or datetime.now(ZoneInfo("America/Los_Angeles"))).astimezone(ZoneInfo("America/Los_Angeles")).date().isoformat()
        with closing(sqlite3.connect(self.path, timeout=10)) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT attempts FROM llm_daily_usage WHERE model_id=? AND quota_day=?", (model_id, day)).fetchone()
            used = row[0] if row else 0
            if used >= self.limit:
                raise DailyLimitReached()
            conn.execute("INSERT INTO llm_daily_usage VALUES (?,?,1) ON CONFLICT(model_id,quota_day)"
                         " DO UPDATE SET attempts=attempts+1", (model_id, day))
            return used + 1
```

## product_view

**Nguồn:** `backend/services.py:12-19`. **Slide:** 65

**Chức năng:** Đổi dữ liệu catalog nội bộ thành cấu trúc sản phẩm/biến thể cho frontend.

**Đầu vào:** `product`

**Đầu ra/tác động:** Dictionary product/variants theo hợp đồng frontend.

```python
def product_view(product):
    return {
        **{k: product[k] for k in ("product_id", "name", "category", "description", "in_stock")},
        "price_from": product["price_min"], "price_to": product["price_max"],
        "variants": [{"sku": v["sku"], "label": v["variant_name"], "unit_price": v["price"],
                      "stock": v["stock"], "color": v["color"], "size": v["size"]}
                     for v in product["variants"]],
    }
```

## order_number

**Nguồn:** `backend/services.py:23-26`. **Slide:** 65

**Chức năng:** Kiểm tra mã đơn dạng DH000001 rồi lấy phần ID số để truy vấn database.

**Đầu vào:** `value`

**Đầu ra/tác động:** ID đơn kiểu int hoặc lỗi 404.

```python
def order_number(value):
    if not isinstance(value, str) or not re.fullmatch(r"DH\d{6,10}", value):
        raise ApiProblem(404, "not_found", "Không tìm thấy đơn hàng trong phiên của bạn.")
    return int(value[2:])
```

## owned_order

**Nguồn:** `backend/services.py:30-34`. **Slide:** 66

**Chức năng:** Lấy đơn và từ chối truy cập nếu đơn không thuộc chủ phiên đang yêu cầu.

**Đầu vào:** `conn, owner, order_id`

**Đầu ra/tác động:** Đơn nội bộ của owner hoặc lỗi 404.

```python
def owned_order(conn, owner, order_id):
    order = orders.get_order(conn, order_id)
    if order["owner_id"] != owner:
        raise ApiProblem(404, "not_found", "Không tìm thấy đơn hàng trong phiên của bạn.")
    return order
```

## order_view

**Nguồn:** `backend/services.py:38-53`. **Slide:** 66

**Chức năng:** Ghép dòng hàng, biến thể có thể đổi và giao nhận thành dữ liệu đơn cho frontend.

**Đầu vào:** `conn, order`

**Đầu ra/tác động:** Dictionary đơn, dòng hàng, tổng, giao nhận và editable.

```python
def order_view(conn, order):
    rows = conn.execute("SELECT * FROM order_items WHERE order_id=? ORDER BY id", (order["id"],)).fetchall()
    items = []
    for row in rows:
        variants = conn.execute(
            "SELECT v.sku, v.variant_name FROM product_variants v JOIN products p ON p.id=v.product_id"
            " WHERE v.product_id=(SELECT product_id FROM product_variants WHERE sku=?)"
            " AND v.is_active=1 AND p.is_active=1 ORDER BY v.sku", (row["sku"],)).fetchall()
        items.append({"item_id": str(row["id"]), "sku": row["sku"], "name": row["product_name"],
                      "variant_label": row["variant_name"], "quantity": row["quantity"],
                      "unit_price": row["unit_price"], "line_total": row["line_total"],
                      "available_variants": [{"sku": v["sku"], "label": v["variant_name"]} for v in variants]})
    return {"order_id": f"DH{order['id']:06d}", "status": order["status"],
            "editable": order["status"] in {"cart", "pending_confirmation"},
            "shipping": {"recipient_name": order["customer_name"], "phone": order["phone"], "address": order["address"]},
            "items": items, "total": order["total_amount"], "source": order["source"]}
```

## cart_order

**Nguồn:** `backend/services.py:57-65`. **Slide:** 67

**Chức năng:** Tìm giỏ gắn với phiên; chỉ tạo giỏ mới khi tham số create được bật.

**Đầu vào:** `conn, session, ctx, create`

**Đầu ra/tác động:** Đơn cart của phiên, giỏ mới hoặc None.

```python
def cart_order(conn, session, ctx, create=False):
    row = conn.execute("SELECT cart_id FROM api_sessions WHERE owner_id=?", (session["owner_id"],)).fetchone()
    if row and row["cart_id"]:
        return owned_order(conn, session["owner_id"], row["cart_id"])
    if create:
        order = orders.create_cart(conn, ctx, session["owner_id"], [])
        conn.execute("UPDATE api_sessions SET cart_id=? WHERE owner_id=?", (order["id"], session["owner_id"]))
        return order
    return None
```

## cart_view

**Nguồn:** `backend/services.py:69-73`. **Slide:** 67

**Chức năng:** Trả giỏ theo định dạng frontend hoặc cấu trúc giỏ trống nếu chưa có giỏ.

**Đầu vào:** `conn, session, ctx`

**Đầu ra/tác động:** order_view hoặc {items: [], total: 0}.

```python
def cart_view(conn, session, ctx):
    order = cart_order(conn, session, ctx)
    if order is None:
        return {"items": [], "total": 0}
    return order_view(conn, order)
```

## item_row

**Nguồn:** `backend/services.py:77-82`. **Slide:** 68

**Chức năng:** Lấy dòng hàng theo cả mã đơn và item ID để tránh thao tác nhầm đơn.

**Đầu vào:** `conn, order_id, item_id`

**Đầu ra/tác động:** Row order_items hoặc ItemNotFound.

```python
def item_row(conn, order_id, item_id):
    row = conn.execute("SELECT * FROM order_items WHERE order_id=? AND CAST(id AS TEXT)=?",
                       (order_id, item_id)).fetchone()
    if row is None:
        raise ItemNotFound("Không tìm thấy sản phẩm trong đơn.")
    return row
```

## update_item

**Nguồn:** `backend/services.py:86-99`. **Slide:** 68

**Chức năng:** Sửa số lượng/biến thể trong transaction, kiểm tra quyền và trạng thái cho phép sửa.

**Đầu vào:** `conn, ctx, owner, order_id, item_id, changes`

**Đầu ra/tác động:** Đơn sau thay đổi, rollback nếu có lỗi.

```python
def update_item(conn, ctx, owner, order_id, item_id, changes):
    with transaction(conn):
        order = owned_order(conn, owner, order_id)
        if order["status"] not in {"cart", "pending_confirmation"}:
            raise OrderNotEditable("Đơn không còn cho phép chỉnh sửa.")
        old = item_row(conn, order_id, item_id)
        sku, qty = changes.get("sku", old["sku"]), changes.get("quantity", old["quantity"])
        if sku == old["sku"]:
            return orders.set_item_quantity(conn, ctx, order_id, sku, qty)
        before, after = catalog.get_variant(conn, old["sku"]), catalog.get_variant(conn, sku)
        if before["product_id"] != after["product_id"]:
            raise ValidationError("Chỉ được đổi biến thể thuộc cùng sản phẩm.", field="sku")
        orders.remove_item(conn, ctx, order_id, old["sku"])
        return orders.add_item(conn, ctx, order_id, sku, qty)
```

## checkout

**Nguồn:** `backend/services.py:103-117`. **Slide:** 69

**Chức năng:** Chuyển giỏ thành đơn chờ xác nhận, tách giỏ khỏi phiên và lưu kết quả chống gửi trùng.

**Đầu vào:** `conn, ctx, session, shipping, key`

**Đầu ra/tác động:** Đơn đã gửi, xóa liên kết cart_id và lưu receipt.

```python
def checkout(conn, ctx, session, shipping, key):
    owner = session["owner_id"]
    with transaction(conn):
        existing = replay(conn, owner, "checkout", key, shipping)
        if existing:
            return existing
        cart = cart_order(conn, session, ctx)
        if not cart or not cart["items"]:
            raise ApiProblem(409, "empty_cart", "Giỏ hàng đang trống.")
        delivery = {"customer_name": shipping["recipient_name"], "phone": shipping["phone"], "address": shipping["address"]}
        order = orders.submit_order(conn, ctx, cart["id"], delivery)
        conn.execute("UPDATE api_sessions SET cart_id=NULL WHERE owner_id=?", (owner,))
        result = order_view(conn, order)
        save_receipt(conn, owner, "checkout", key, shipping, result)
        return result
```

## initialize

**Nguồn:** `backend/storage.py:35-44`. **Slide:** 70

**Chức năng:** Chạy migration, seed catalog nếu chưa có sản phẩm và tạo bảng phiên/chống gửi trùng.

**Đầu vào:** `path`

**Đầu ra/tác động:** Chuẩn bị schema/seed/bảng phụ, không trả dữ liệu.

```python
def initialize(path):
    conn = connect(path)
    try:
        migrate(conn)
        with transaction(conn):
            if not conn.execute("SELECT 1 FROM products LIMIT 1").fetchone():
                seed_catalog(conn)
        conn.executescript(SCHEMA)
    finally:
        conn.close()
```

## new_session

**Nguồn:** `backend/storage.py:48-58`. **Slide:** 70

**Chức năng:** Tạo token, chủ phiên và hội thoại mới; database chỉ lưu hash của token cùng hạn dùng.

**Đầu vào:** `conn, ttl`

**Đầu ra/tác động:** Token thô cho client và thời điểm hết hạn.

```python
def new_session(conn, ttl):
    token = secrets.token_urlsafe(32)
    owner = uuid.uuid4().hex
    expiry = int(time.time()) + ttl
    with transaction(conn):
        conv = conversations.create_conversation(conn, owner)
        conn.execute(
            "INSERT INTO api_sessions(token_hash, owner_id, conversation_id, expires_at) VALUES (?,?,?,?)",
            (hashlib.sha256(token.encode()).hexdigest(), owner, conv["id"], expiry),
        )
    return {"token": token, "expires_at": expiry}
```

## authenticate

**Nguồn:** `backend/storage.py:62-70`. **Slide:** 71

**Chức năng:** Kiểm tra Bearer token và trả phiên tương ứng nếu token hợp lệ, chưa hết hạn.

**Đầu vào:** `conn, authorization`

**Đầu ra/tác động:** Dictionary phiên đã xác thực hoặc lỗi 401.

```python
def authenticate(conn, authorization):
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not 20 <= len(token) <= 200:
        raise ApiProblem(401, "auth", "Cần phiên khách hàng hợp lệ.")
    row = conn.execute("SELECT * FROM api_sessions WHERE token_hash = ? AND expires_at > ?",
                       (hashlib.sha256(token.encode()).hexdigest(), int(time.time()))).fetchone()
    if row is None:
        raise ApiProblem(401, "auth", "Phiên đã hết hạn hoặc không hợp lệ. Hãy mở phiên mới.")
    return dict(row)
```

## request_key

**Nguồn:** `backend/storage.py:74-77`. **Slide:** 71

**Chức năng:** Kiểm tra định dạng khóa Idempotency-Key dùng để nhận biết các request gửi lại.

**Đầu vào:** `value`

**Đầu ra/tác động:** Khóa hợp lệ/None hoặc lỗi 422.

```python
def request_key(value):
    if value is not None and not re.fullmatch(r"[A-Za-z0-9_.:-]{8,100}", value):
        raise ApiProblem(422, "validation", "Idempotency-Key phải dài 8-100 ký tự gồm chữ, số và _-:.")
    return value
```

## digest

**Nguồn:** `backend/storage.py:81-82`. **Slide:** 72

**Chức năng:** Tạo hash SHA-256 từ nội dung JSON đã sắp xếp khóa để so sánh các request.

**Đầu vào:** `payload`

**Đầu ra/tác động:** Chuỗi hash SHA-256 của payload JSON.

```python
def digest(payload):
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
```

## replay

**Nguồn:** `backend/storage.py:86-95`. **Slide:** 72

**Chức năng:** Trả kết quả đã lưu cho request lặp; báo xung đột nếu cùng khóa nhưng khác nội dung.

**Đầu vào:** `conn, owner, scope, key, payload`

**Đầu ra/tác động:** Response đã lưu/None hoặc xung đột 409.

```python
def replay(conn, owner, scope, key, payload):
    if not key:
        return None
    row = conn.execute("SELECT * FROM api_receipts WHERE owner_id=? AND scope=? AND request_key=?",
                       (owner, scope, key)).fetchone()
    if row is None:
        return None
    if row["request_hash"] != digest(payload):
        raise ApiProblem(409, "idempotency_conflict", "Khóa này đã được dùng cho nội dung khác.")
    return json.loads(row["response"])
```

## save_receipt

**Nguồn:** `backend/storage.py:99-102`. **Slide:** 73

**Chức năng:** Lưu hash nội dung và kết quả theo phiên/phạm vi/khóa để xử lý request lặp sau này.

**Đầu vào:** `conn, owner, scope, key, payload, response`

**Đầu ra/tác động:** Lưu response khi có key, không trả dữ liệu.

```python
def save_receipt(conn, owner, scope, key, payload, response):
    if key:
        conn.execute("INSERT INTO api_receipts VALUES (?,?,?,?,?)",
                     (owner, scope, key, digest(payload), json.dumps(response, ensure_ascii=False)))
```

## local_catalog_request

**Nguồn:** `backend/catalog_chat.py:10-25`. **Slide:** 74

**Chức năng:** Nhận diện một số câu hỏi catalog/giá/tồn rõ nghĩa bằng rule để không cần gọi LLM.

**Đầu vào:** `message`

**Đầu ra/tác động:** Extraction theo rule hoặc None để chuyển sang LLM.

```python
def local_catalog_request(message):
    text = normalize(message)
    browse = {"cua hang ban gi", "cua hang ban nhung gi", "cua hang ban ban nhung gi", "shop ban gi", "shop ban nhung gi",
              "toi muon tham khao san pham", "toi muon tham khao san pham cua hang ban ban nhung gi",
              "cho toi xem san pham", "cho xem san pham", "xem catalog", "xem danh muc san pham"}
    price = {"gia bao nhieu", "mau nay gia bao nhieu", "gia mau nay bao nhieu"}
    stock = {"con hang khong", "mau nay con hang khong", "mau nay con khong"}
    intent = "browse_catalog" if text in browse else "check_price" if text in price else "check_stock" if text in stock else None
    if intent is None:
        return None
    items = [] if intent == "browse_catalog" else [{"requested_product": None, "sku": None, "quantity": None,
                                                  "variant": {"color": None, "size": None}}]
    return Extraction.model_validate({"intent": intent, "confidence": "high", "items": items,
                                      "customer": {"name": None, "phone": None, "address": None},
                                      "order_reference": None, "missing_information": [], "requires_human_review": False,
                                      "evidence": [message]})
```

## _matches

**Nguồn:** `backend/catalog_chat.py:29-31`. **Slide:** 74

**Chức năng:** So khớp thuộc tính đã chuẩn hóa; cho phép màu chung khớp tên màu chi tiết trong catalog.

**Đầu vào:** `value, actual, field`

**Đầu ra/tác động:** Boolean thuộc tính yêu cầu khớp catalog.

```python
def _matches(value, actual, field=None):
    requested, known = attribute_value(value, field), attribute_value(actual, field)
    return not value or requested == known or (field == "color" and known.startswith(requested + " "))
```

## find_products

**Nguồn:** `backend/catalog_chat.py:35-67`. **Slide:** 75

**Chức năng:** Tìm sản phẩm theo tên/SKU và lọc biến thể theo danh mục, màu, size, giá, tồn kho.

**Đầu vào:** `conn, items, filters`

**Đầu ra/tác động:** Danh sách sản phẩm và biến thể qua các bộ lọc.

```python
def find_products(conn, items, filters):
    found = {}
    for item in items or [{"requested_product": None, "sku": None, "variant": {}}]:
        query, sku = item.get("requested_product"), item.get("sku")
        if sku:
            variant = catalog.get_variant(conn, sku)
            products = [catalog.get_product(conn, variant["product_id"])]
        elif query:
            categories = [c for c in catalog.list_categories(conn) if normalize(c) == normalize(query)]
            products = catalog.list_products(conn, category=categories[0], limit=100) if categories else catalog.search_products(conn, query, limit=20)
        else:
            products = catalog.list_products(conn, limit=100)
        for p in products:
            if filters.category and not _matches(filters.category, p["category"]):
                continue
            requested = item.get("variant", {})
            variants = [v for v in p["variants"]
                        if (not sku or v["sku"] == sku)
                        and _matches(requested.get("color"), v["color"], field="color")
                        and _matches(requested.get("size"), v["size"], field="size")
                        and (filters.min_price is None or v["price"] >= filters.min_price)
                        and (filters.max_price is None or v["price"] <= filters.max_price)
                        and (not filters.in_stock_only or v["stock"] > 0)]
            if not variants:
                continue
            if p["product_id"] in found:
                previous = found[p["product_id"]]["variants"]
                variants = list({v["sku"]: v for v in [*previous, *variants]}.values())
            found[p["product_id"]] = {**p, "variants": variants,
                                      "price_min": min(v["price"] for v in variants),
                                      "price_max": max(v["price"] for v in variants),
                                      "in_stock": any(v["stock"] > 0 for v in variants)}
    return list(found.values())
```

## catalog_reply

**Nguồn:** `backend/catalog_chat.py:71-98`. **Slide:** 75

**Chức năng:** Tạo câu trả lời và danh sách sản phẩm bằng giá/tồn thực tế lấy từ database.

**Đầu vào:** `conn, items, filters, intent`

**Đầu ra/tác động:** Response đọc catalog/giá/tồn cùng products.

```python
def catalog_reply(conn, items, filters, intent):
    products = find_products(conn, items, filters)
    if not products:
        return {"reply": "Hiện cửa hàng chưa có sản phẩm khớp yêu cầu trong catalog. Bạn có thể đổi từ khóa, màu/size hoặc mức giá để mình tìm lại.",
                "route": "catalog_empty", "missing_fields": [], "order": None, "products": []}
    shown = products[:8]
    if intent == "browse_catalog":
        lines = ["Mình tìm được các sản phẩm sau trong cửa hàng:"]
    else:
        lines = ["Thông tin hiện tại từ cửa hàng:"]
    for index, p in enumerate(shown, 1):
        lines.append(f"\n{index}. {p['name']} ({p['category']})")
        if intent == "browse_catalog" and p.get("description"):
            lines.append(p["description"])
        if intent == "browse_catalog" and len(shown) > 1:
            price = f"{p['price_min']:,} VND" if p["price_min"] == p["price_max"] else f"{p['price_min']:,}–{p['price_max']:,} VND"
            lines.append(f"Giá {price}; " + ("còn hàng." if p["in_stock"] else "hiện hết hàng."))
            continue
        for v in p["variants"]:
            stock = f"còn {v['stock']} sản phẩm" if v["stock"] else "hết hàng (còn 0 sản phẩm)"
            facts = f"giá {v['price']:,} VND; {stock}"
            lines.append(f"- {v['variant_name']} ({v['sku']}): {facts}.")
    if len(products) > len(shown):
        lines.append(f"\nĐang hiển thị {len(shown)}/{len(products)} sản phẩm phù hợp. Bạn muốn xem nhóm nào cụ thể?")
    else:
        lines.append("\nBạn muốn xem kỹ sản phẩm, màu hoặc size nào?")
    return {"reply": "\n".join(lines), "route": {"browse_catalog": "catalog_shown", "check_price": "price_checked", "check_stock": "stock_checked"}[intent],
            "missing_fields": [], "order": None, "products": [product_view(p) for p in shown]}
```

## browsing_context

**Nguồn:** `backend/catalog_chat.py:102-105`. **Slide:** 76

**Chức năng:** Lưu ID sản phẩm và SKU vừa hiển thị để hiểu các câu hỏi tiếp theo của khách.

**Đầu vào:** `result`

**Đầu ra/tác động:** catalog_product_ids và tối đa 40 catalog_skus.

```python
def browsing_context(result):
    products = result.get("products", [])
    return {"catalog_product_ids": [p["product_id"] for p in products],
            "catalog_skus": [v["sku"] for p in products for v in p["variants"]][:40]}
```

## resolve_reference

**Nguồn:** `backend/catalog_chat.py:109-132`. **Slide:** 76

**Chức năng:** Hiểu “mẫu này”, “mẫu đầu tiên” từ lịch sử xem hàng, chỉ chọn khi tham chiếu đủ rõ.

**Đầu vào:** `conn, items, context, message`

**Đầu ra/tác động:** Item gắn sản phẩm/SKU rõ nghĩa hoặc giữ nguyên để hỏi lại.

```python
def resolve_reference(conn, items, context, message):
    ids = context.get("catalog_product_ids", [])
    if not ids or not items or len(items) != 1:
        return items
    item = items[0]
    query = normalize(item.get("requested_product"))
    references = {"mau nay", "mau do", "cai nay", "cai do", "ao nay", "ao do", "san pham nay", "san pham do", "mau dau tien", "mau cuoi"}
    if item.get("sku") or (query and query not in references):
        return items
    text = normalize(message)
    if "mau dau tien" in text or "san pham dau tien" in text:
        target = ids[0]
    elif "mau cuoi" in text or "san pham cuoi" in text:
        target = ids[-1]
    elif len(ids) == 1:
        target = ids[0]
    else:
        return items
    product = catalog.get_product(conn, target)
    result = {**item, "requested_product": product["name"]}
    skus = [v["sku"] for v in product["variants"] if v["sku"] in context.get("catalog_skus", [])]
    if len(skus) == 1 and not any(item["variant"].values()):
        result["sku"] = skus[0]
    return [result]
```

## size_value

**Nguồn:** `backend/variant_utils.py:7-8`. **Slide:** 77

**Chức năng:** Chuẩn hóa cách viết size để “15inch” và “15 inch” được đối chiếu như nhau.

**Đầu vào:** `value`

**Đầu ra/tác động:** Chuỗi size đã chuẩn hóa cách viết inch.

```python
def size_value(value):
    return re.sub(r"(?<=\d)\s*(?:inches|inch)\b", " inch", normalize(value))
```

## attribute_value

**Nguồn:** `backend/variant_utils.py:12-19`. **Slide:** 77

**Chức năng:** Bỏ nhãn “màu”, “size”, “cỡ” và chuẩn hóa giá trị trước khi so với biến thể.

**Đầu vào:** `value, field`

**Đầu ra/tác động:** Chuỗi màu/size đã bỏ nhãn để so khớp.

```python
def attribute_value(value, field):
    text = normalize(value)
    prefixes = {"color": ("mau", "color"), "size": ("kich co", "size", "co")}
    for prefix in prefixes.get(field, ()):
        if text.startswith(prefix + " "):
            text = text[len(prefix) + 1:]
            break
    return size_value(text) if field == "size" else text
```

## ItemChange.require_change

**Nguồn:** `backend/models.py:39-42`. **Slide:** 78

**Chức năng:** Bắt buộc yêu cầu sửa dòng hàng có ít nhất một trường sku hoặc quantity khác null.

**Đầu vào:** `không có tham số ngoài đối tượng`

**Đầu ra/tác động:** self hợp lệ hoặc ValueError nếu không có trường sửa.

```python
    def require_change(self):
        if not self.model_fields_set or any(getattr(self, f) is None for f in self.model_fields_set):
            raise ValueError("Cần sku hoặc quantity có giá trị hợp lệ")
        return self
```

## Settings.from_env

**Nguồn:** `backend/config.py:27-54`. **Slide:** 79

**Chức năng:** Đọc cấu hình từ .env/biến môi trường và kiểm tra key, timeout, retry cùng các giới hạn.

**Đầu vào:** `không có tham số ngoài đối tượng`

**Đầu ra/tác động:** Settings bất biến hoặc ValueError nếu cấu hình sai.

```python
    def from_env(cls):
        load_dotenv()
        settings = cls(
            db_path=get_db_path(),
            llm_provider=os.getenv("LLM_PROVIDER", "fake"),
            model_id=os.getenv("LLM_MODEL_ID", "gemini-3.5-flash-lite"),
            api_key=os.getenv("GEMINI_API_KEY", ""),
            llm_timeout=float(os.getenv("LLM_TIMEOUT_SECONDS", "12")),
            llm_max_retries=int(os.getenv("LLM_MAX_RETRIES", "0")),
            llm_daily_limit=int(os.getenv("LLM_DAILY_REQUEST_LIMIT", "500")),
            llm_usage_path=os.getenv("LLM_USAGE_DB_PATH", str(Path(__file__).resolve().parents[1] / "database/data/llm_usage.db")),
            session_ttl=int(os.getenv("SESSION_TTL_SECONDS", "86400")),
            request_limit=int(os.getenv("API_REQUESTS_PER_MINUTE", "120")),
            chat_limit=int(os.getenv("CHAT_REQUESTS_PER_MINUTE", "10")),
            session_limit=int(os.getenv("SESSION_REQUESTS_PER_MINUTE", "20")),
        )
        if settings.llm_provider not in {"fake", "gemini"}:
            raise ValueError("LLM_PROVIDER phải là fake hoặc gemini")
        if settings.llm_provider == "gemini" and not settings.api_key:
            raise ValueError("Chưa cấu hình GEMINI_API_KEY trong .env")
        if not 1 <= settings.llm_timeout <= 30 or not 0 <= settings.llm_max_retries <= 2:
            raise ValueError("Timeout phải từ 1-30 giây, retry từ 0-2")
        maximum = 500 if settings.model_id == "gemini-3.5-flash-lite" else 20
        if not 0 <= settings.llm_daily_limit <= maximum:
            raise ValueError(f"Giới hạn gọi {settings.model_id} mỗi ngày phải từ 0-{maximum}")
        if min(settings.session_ttl, settings.request_limit, settings.chat_limit, settings.session_limit) < 1:
            raise ValueError("TTL và giới hạn request phải lớn hơn 0")
        return settings
```

## ApiProblem.__init__

**Nguồn:** `backend/errors.py:6-10`. **Slide:** 80

**Chức năng:** Lưu mã HTTP, mã lỗi, thông báo và lỗi từng trường để API phản hồi thống nhất.

**Đầu vào:** `status, code, message, fields`

**Đầu ra/tác động:** Đối tượng lỗi có status, code, message, fields.

```python
    def __init__(self, status, code, message, fields=None):
        self.status = status
        self.code = code
        self.message = message
        self.fields = fields or {}
```

## database_problem

**Nguồn:** `backend/errors.py:14-23`. **Slide:** 80

**Chức năng:** Ánh xạ lỗi database sang mã HTTP và đổi tên trường cho khớp dữ liệu frontend.

**Đầu vào:** `err`

**Đầu ra/tác động:** ApiProblem tương ứng lỗi database.

```python
def database_problem(err: DataServiceError):
    code = err.code
    status = 409
    if code in {"sku_not_found", "product_not_found", "order_not_found", "item_not_found", "conversation_not_found"}:
        status = 404
    if code == "validation_error":
        status, code = 422, "validation"
    fields = err.details.get("errors", {})
    fields = {"recipient_name" if k == "customer_name" else k: v for k, v in fields.items()}
    return ApiProblem(status, code, err.message, fields)
```

## _seg

**Nguồn:** `backend/shop_api.py:11-12`. **Slide:** 81

**Chức năng:** Mã hóa ID hoặc SKU để chèn an toàn vào một đoạn đường dẫn URL.

**Đầu vào:** `value`

**Đầu ra/tác động:** Chuỗi URL-encoded cho một đoạn path.

Hàm tương thích giao diện Streamlit. Đây không phải endpoint nhận request của frontend React.

```python
def _seg(value):
    return quote(str(value), safe="")
```

## ShopApiMixin.list_products

**Nguồn:** `backend/shop_api.py:18-19`. **Slide:** 81

**Chức năng:** Gọi API lấy danh sách sản phẩm và trả riêng mảng products.

**Đầu vào:** `không có tham số ngoài đối tượng`

**Đầu ra/tác động:** Mảng products từ API.

Hàm tương thích giao diện Streamlit. Đây không phải endpoint nhận request của frontend React.

```python
    def list_products(self):
        return self._request("GET", "/api/products")["products"]
```

## ShopApiMixin.get_product

**Nguồn:** `backend/shop_api.py:22-23`. **Slide:** 82

**Chức năng:** Gọi API lấy thông tin chi tiết sản phẩm theo ID.

**Đầu vào:** `product_id`

**Đầu ra/tác động:** JSON chi tiết sản phẩm từ API.

Hàm tương thích giao diện Streamlit. Đây không phải endpoint nhận request của frontend React.

```python
    def get_product(self, product_id):
        return self._request("GET", f"/api/products/{_seg(product_id)}")
```

## ShopApiMixin.add_to_cart

**Nguồn:** `backend/shop_api.py:27-28`. **Slide:** 82

**Chức năng:** Gửi SKU và số lượng để API thêm hàng; không gửi giá hay tổng tiền từ client.

**Đầu vào:** `sku, quantity`

**Đầu ra/tác động:** JSON giỏ sau thêm hàng qua API.

Hàm tương thích giao diện Streamlit. Đây không phải endpoint nhận request của frontend React.

```python
    def add_to_cart(self, sku, quantity):
        return self._request("POST", "/api/cart/items", json={"sku": sku, "quantity": quantity})
```

## ShopApiMixin.update_cart_item

**Nguồn:** `backend/shop_api.py:31-32`. **Slide:** 83

**Chức năng:** Gửi số lượng mới cho một dòng giỏ hàng và nhận lại giỏ đã cập nhật.

**Đầu vào:** `item_id, quantity`

**Đầu ra/tác động:** JSON giỏ sau sửa số lượng qua API.

Hàm tương thích giao diện Streamlit. Đây không phải endpoint nhận request của frontend React.

```python
    def update_cart_item(self, item_id, quantity):
        return self._request("PATCH", f"/api/cart/items/{_seg(item_id)}", json={"quantity": quantity})
```

## ShopApiMixin.remove_cart_item

**Nguồn:** `backend/shop_api.py:35-36`. **Slide:** 83

**Chức năng:** Gọi API xóa một dòng giỏ hàng theo item ID.

**Đầu vào:** `item_id`

**Đầu ra/tác động:** JSON giỏ sau xóa dòng qua API.

Hàm tương thích giao diện Streamlit. Đây không phải endpoint nhận request của frontend React.

```python
    def remove_cart_item(self, item_id):
        return self._request("DELETE", f"/api/cart/items/{_seg(item_id)}")
```

## category_label

**Nguồn:** `backend/shop_logic.py:10-11`. **Slide:** 84

**Chức năng:** Đổi mã danh mục thành nhãn tiếng Việt; mã lạ được viết hoa chữ đầu.

**Đầu vào:** `code`

**Đầu ra/tác động:** Tên danh mục hiển thị.

Hàm tương thích giao diện Streamlit. Đây không phải endpoint nhận request của frontend React.

```python
def category_label(code):
    return CATEGORY_LABEL.get(code, str(code).capitalize())
```

## normalize

**Nguồn:** `backend/shop_logic.py:15-18`. **Slide:** 84

**Chức năng:** Bỏ dấu và chuyển chữ thường để tìm kiếm tên sản phẩm không phụ thuộc dấu tiếng Việt.

**Đầu vào:** `text`

**Đầu ra/tác động:** Chuỗi không dấu, chữ thường để tìm kiếm.

Hàm tương thích giao diện Streamlit. Đây không phải endpoint nhận request của frontend React.

```python
def normalize(text):
    """Bỏ dấu + chữ thường để tìm 'ao thun' ra 'Áo thun'."""
    text = unicodedata.normalize("NFD", str(text or "").lower().replace("đ", "d"))
    return "".join(c for c in text if unicodedata.category(c) != "Mn").strip()
```

## filter_products

**Nguồn:** `backend/shop_logic.py:22-28`. **Slide:** 85

**Chức năng:** Lọc danh sách sản phẩm theo danh mục và từ khóa tên đã chuẩn hóa.

**Đầu vào:** `products, category, query`

**Đầu ra/tác động:** Danh sách sau lọc category/query.

Hàm tương thích giao diện Streamlit. Đây không phải endpoint nhận request của frontend React.

```python
def filter_products(products, category=None, query=""):
    q = normalize(query)
    return [
        p for p in products
        if (not category or p.get("category") == category)
        and (not q or q in normalize(p.get("name", "")))
    ]
```

## stock_label

**Nguồn:** `backend/shop_logic.py:32-37`. **Slide:** 85

**Chức năng:** Tạo nhãn hết hàng, sắp hết hoặc còn hàng từ số lượng tồn kho.

**Đầu vào:** `stock`

**Đầu ra/tác động:** Nhãn hết hàng/sắp hết/còn hàng.

Hàm tương thích giao diện Streamlit. Đây không phải endpoint nhận request của frontend React.

```python
def stock_label(stock):
    if stock <= 0:
        return "Hết hàng"
    if stock <= LOW_STOCK:
        return f"Sắp hết (còn {stock})"
    return f"Còn hàng ({stock})"
```

## max_selectable

**Nguồn:** `backend/shop_logic.py:41-43`. **Slide:** 86

**Chức năng:** Giới hạn số lượng trên giao diện theo tồn kho và trần 99; server vẫn kiểm tra lại.

**Đầu vào:** `stock`

**Đầu ra/tác động:** Số từ 1 đến 99 cho control UI, còn kiểm tra server.

Hàm tương thích giao diện Streamlit. Đây không phải endpoint nhận request của frontend React.

```python
def max_selectable(stock):
    """Số lượng tối đa cho ô nhập (chỉ để UX; server mới là bên quyết định)."""
    return max(1, min(int(stock), MAX_QTY))
```

## price_text

**Nguồn:** `backend/shop_logic.py:47-50`. **Slide:** 86

**Chức năng:** Định dạng giá sản phẩm, thêm chữ “Từ” nếu các biến thể có giá khác nhau.

**Đầu vào:** `product, fmt`

**Đầu ra/tác động:** Chuỗi giá hoặc “Từ ...”.

Hàm tương thích giao diện Streamlit. Đây không phải endpoint nhận request của frontend React.

```python
def price_text(product, fmt):
    low = product["price_from"]
    high = product.get("price_to", low)
    return fmt(low) if low == high else f"Từ {fmt(low)}"
```

## variant_option_label

**Nguồn:** `backend/shop_logic.py:54-56`. **Slide:** 87

**Chức năng:** Ghép tên biến thể, giá và trạng thái hết hàng thành nhãn lựa chọn.

**Đầu vào:** `variant, fmt`

**Đầu ra/tác động:** Nhãn gồm biến thể, giá và tình trạng hết hàng.

Hàm tương thích giao diện Streamlit. Đây không phải endpoint nhận request của frontend React.

```python
def variant_option_label(variant, fmt):
    text = f"{variant['label']} · {fmt(variant['unit_price'])}"
    return text + (" · Hết hàng" if variant["stock"] <= 0 else "")
```

## pick_default_variant

**Nguồn:** `backend/shop_logic.py:60-65`. **Slide:** 87

**Chức năng:** Ưu tiên SKU đầu tiên còn hàng, hoặc SKU đầu danh sách nếu tất cả đều hết.

**Đầu vào:** `variants`

**Đầu ra/tác động:** SKU mặc định hoặc None nếu danh sách rỗng.

Hàm tương thích giao diện Streamlit. Đây không phải endpoint nhận request của frontend React.

```python
def pick_default_variant(variants):
    """Ưu tiên biến thể còn hàng đầu tiên."""
    for v in variants:
        if v["stock"] > 0:
            return v["sku"]
    return variants[0]["sku"] if variants else None
```

## chunk

**Nguồn:** `backend/shop_logic.py:69-70`. **Slide:** 88

**Chức năng:** Chia danh sách thành các nhóm nhỏ có kích thước cho trước để bố trí giao diện.

**Đầu vào:** `seq, size`

**Đầu ra/tác động:** Danh sách các nhóm con.

Hàm tương thích giao diện Streamlit. Đây không phải endpoint nhận request của frontend React.

```python
def chunk(seq, size):
    return [seq[i:i + size] for i in range(0, len(seq), size)]
```
