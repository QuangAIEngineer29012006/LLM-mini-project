import logging
import re
import time
from datetime import datetime, timezone

from database.shop_db import audit_service as audit, catalog_service as catalog
from database.shop_db import conversation_service as conversations, order_service as orders
from database.shop_db.db import transaction
from database.shop_db.errors import DataServiceError
from database.shop_db.text_utils import normalize
from database.shop_db.validation import normalize_items
from src.llm_client import LLMError
from src.parser import OutputError, parse_output, validate_grounding
from src.prompts import PROMPT_VERSION

from .errors import ApiProblem
from .catalog_chat import browsing_context, catalog_reply, local_catalog_request, resolve_reference
from .models import Shipping
from .services import order_number, order_view, owned_order, update_item
from .storage import replay, save_receipt
from .variant_utils import attribute_value


logger = logging.getLogger("shop.workflow")
FIELD_NAMES = {"recipient_name": "tên người nhận", "phone": "số điện thoại", "address": "địa chỉ đầy đủ",
               "product": "sản phẩm hoặc SKU", "quantity": "số lượng", "variant": "màu/size", "order_reference": "mã đơn"}
UNSAFE = re.compile(r"bo qua.*huong dan|ignore.*instructions?|api[ _-]?key|system prompt|"
                    r"xoa.*(?:don|du lieu)|delete.*orders?|drop\s+table|(?:xac nhan|danh dau).*(?:thanh toan|da tra)")
READ_INTENTS = {"browse_catalog", "check_price", "check_stock"}


def response(reply, route, missing=(), order=None, **extra):
    return {"reply": reply, "route": route, "missing_fields": list(missing), "order": order, **extra}


def ask(fields, detail=""):
    fields = list(dict.fromkeys(fields))
    text = ", ".join(FIELD_NAMES.get(f, f) for f in fields)
    return response((detail + " Vui lòng bổ sung: " + text + ".").strip(), "ask_missing", fields)


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


def _draft(conn, ctx, session, slots, key):
    items = slots.get("items", [])
    if not items:
        return ask(["product", "quantity"])
    resolved = []
    for item in items:
        variant, problem = resolve_item(conn, item)
        if problem:
            return problem
        if item.get("quantity") is None:
            return ask(["quantity"])
        resolved.append({"sku": variant["sku"], "quantity": item["quantity"]})
    resolved = [{"sku": s, "quantity": q} for s, q in normalize_items(resolved)]
    stock = catalog.check_items(conn, resolved)
    if not stock["ok"]:
        details = "; ".join(f"{r['sku']} còn {r['available']}, bạn yêu cầu {r['requested']}" for r in stock["results"] if not r["ok"])
        return response("Không đủ hàng: " + details + ". Vui lòng chọn lại số lượng hoặc biến thể.", "out_of_stock")
    delivery, missing = _shipping(slots.get("customer", {}))
    if missing:
        return ask(missing)
    order = orders.create_draft_order(conn, ctx, session["owner_id"], resolved, delivery, source="chat", idempotency_key=key)
    return response("Đã tạo đơn nháp. Bạn có thể xem và sửa ở trang Đơn hàng; đơn đang chờ xác nhận.",
                    "draft_created", order=order_view(conn, order))


def _query(conn, items, intent, filters):
    if not items or any(not i.get("requested_product") and not i.get("sku") for i in items):
        return ask(["product"])
    return catalog_reply(conn, items, filters, intent)


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
            data = validate_grounding(parse_output(llm.text), message)
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
