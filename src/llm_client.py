import json
import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import requests

from database.shop_db.text_utils import normalize

from .parser import Extraction, NUMBER_WORDS, money_amounts, plain_text
from .prompts import build_prompt
from .quota import DailyBudget, DailyLimitReached


@dataclass
class LLMResult:
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    retry_count: int = 0


class LLMError(Exception):
    def __init__(self, code, retry_count=0):
        self.code = code
        self.retry_count = retry_count


def _retry_delay(header, attempt):
    try:
        seconds = float(header)
    except (ValueError, TypeError):
        try:
            seconds = (parsedate_to_datetime(header) - datetime.now(timezone.utc)).total_seconds()
        except (ValueError, TypeError, OverflowError):
            seconds = 0
    return max(0.25 * 2 ** attempt, seconds)


class GeminiLLMClient:
    def __init__(self, settings):
        self.settings = settings
        self.model_id = settings.model_id
        self.budget = DailyBudget(settings.llm_usage_path, settings.llm_daily_limit) if settings.llm_usage_path else None

    def generate(self, message, catalog, context):
        system, prompt = build_prompt(message, catalog, context)
        return self.complete(system, prompt, Extraction.model_json_schema())

    def complete(self, system, prompt, schema):
        url = "https://generativelanguage.googleapis.com/v1beta/models/" + quote(self.model_id, safe="-") + ":generateContent"
        payload = {"systemInstruction": {"parts": [{"text": system}]},
                   "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                   "generationConfig": {"temperature": 0, "maxOutputTokens": 2048,
                                        "responseFormat": {"text": {"mimeType": "APPLICATION_JSON",
                                                                    "schema": schema}}}}
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


def _span(text, pattern):
    match = re.search(pattern, plain_text(text), flags=re.I)
    return text[match.start(1):match.end(1)].strip() if match else None


KNOWLEDGE_CUES = re.compile(r"\b(bao hanh|doi tra|doi y|hoan tien|chat lieu|bao quan|giat|chinh sach|phi van chuyen|"
                            r"phi ship|van chuyen|giao hang|thanh toan|tra gop|huy don|thieu hang|hu hong|ngap nuoc|"
                            r"bang size|phu hop|tien luong|muc luong|bang luong|luong nhan vien|phu cap|ca truc|ca dem|sla|noi bo|han muc|uu dai|khuyen mai|"
                            r"ma giam gia|quoc te|hoa toc|tich diem|vat|hoa don|sop|quy trinh)\b")
ACTION_CUES = re.compile(r"\b(chot|mua|lay|dat|them|gia|con hang)\b")


def _short_span(text):
    text = text.strip()
    return text if len(text) <= 200 else text[:200].rsplit(" ", 1)[0]


class FakeLLMClient:
    """Small rule-based extractor for offline demos; it does not measure Gemini quality."""
    model_id = "fake-rules-v1"

    def generate(self, message, catalog, context):
        if KNOWLEDGE_CUES.search(plain_text(message)):
            clauses = [c.strip() for c in re.split(r"[,;.?!]|\s+(?:rồi|và)\s+", message) if c.strip()]
            asks = [c for c in clauses if KNOWLEDGE_CUES.search(plain_text(c))]
            acts = [c for c in clauses if c not in asks and ACTION_CUES.search(plain_text(c))]
            question = _short_span(asks[0]) if asks else _short_span(message)
            if acts:
                result = json.loads(self._extract(message[message.index(acts[0]):], catalog, context).text)
            else:
                result = {"intent": "knowledge_query", "confidence": "high", "items": [],
                          "customer": {"name": None, "phone": None, "address": None}, "order_reference": None,
                          "missing_information": [], "requires_human_review": False,
                          "evidence": [_short_span(message)]}
            result["knowledge_question"] = question
            return LLMResult(json.dumps(result, ensure_ascii=False))
        return self._extract(message, catalog, context)

    def _extract(self, message, catalog, context):
        text = plain_text(message)
        pending = context.get("pending_intent")
        lowered = unicodedata.normalize("NFC", message.lower())
        # "đôi" (a pair of shoes) and "đổi" (change) both strip to "doi"; only the accented "đôi" is unambiguous.
        if re.search(r"\b(sua|cap nhat)\b", text) or (re.search(r"\bdoi\b", text) and "đôi" not in lowered):
            intent = "update_order"
        elif re.search(r"\b(ban (?:nhung )?gi|tham khao|catalog|cho.*xem|tim|tu van|gioi thieu)\b", text):
            intent = "browse_catalog"
        elif re.search(r"\b(gia|bao nhieu tien)\b", text):
            intent = "check_price"
        elif re.search(r"\b(con|ton kho|het hang)\b", text):
            intent = "check_stock"
        elif re.search(r"\b(chot|mua|lay|dat|them)\b|\bcho\s+(?:em|anh|chi|toi|minh)\s+(?:\d+|mot|hai|ba|bon|nam|sau|bay|tam|chin|muoi)\b", text):
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
            plain = plain_text(chunk)
            aliases = [alias for p in catalog for alias in [p["name"], *p.get("aliases", [])]
                       if re.search(r"(?<!\w)" + re.escape(plain_text(alias)) + r"(?!\w)", plain)]
            alias = max(aliases, key=len) if aliases else None
            if not alias and intent == "browse_catalog":
                categories = {p.get("category", "") for p in catalog} - {""}
                alias = next((c for c in sorted(categories) if re.search(r"\b" + re.escape(plain_text(c)) + r"\b", plain)), None)
            sku = _span(chunk, r"\b([A-Z][A-Z0-9]*-[A-Z0-9]+-[A-Z0-9]+)\b")
            color = next((_span(chunk, r"\b(" + re.escape(plain_text(c)) + r")\b") for c in colors
                          if re.search(r"\b" + re.escape(plain_text(c)) + r"\b", plain)), None)
            size = _span(chunk, r"\bsize\s+([a-z0-9]+)\b")
            if re.search(r"\b\d+(?:[.,]\d+)?\s*(?:inch|inches)\b", plain):
                size = _span(chunk, r"\b(\d+(?:[.,]\d+)?\s*(?:inches|inch))\b")
            qty_text = _span(chunk, r"(?:\bchot|\bmua|\blay|\bdat|\bthem|\bthanh|\bcon|\bso luong|\bcho\s+(?:em|anh|chi|toi|minh))\s*[:=]?\s+(-?\d+(?:[.,]\d+)?|mot|hai|ba|bon|nam|sau|bay|tam|chin|muoi)\b")
            if qty_text is None:
                qty_text = _span(chunk, r"^\s*(\d+)\s+")
            qty = NUMBER_WORDS.get(plain_text(qty_text or ""))
            if qty_text and qty is None:
                try:
                    qty = int(qty_text)
                except ValueError:
                    qty = 0
            requested = _span(chunk, "(" + re.escape(plain_text(alias)) + ")") if alias else None
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


def make_client(settings):
    return GeminiLLMClient(settings) if settings.llm_provider == "gemini" else FakeLLMClient()
