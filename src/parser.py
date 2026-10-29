import json
import re
import unicodedata
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, ValidationError

from backend.models import StrictModel
from backend.variant_utils import size_value
from database.shop_db.text_utils import normalize


Text = Annotated[str, StringConstraints(min_length=1, max_length=200)]
INTENTS = Literal["browse_catalog", "create_order", "check_stock", "check_price", "update_order", "unknown_or_handoff"]


class Variant(StrictModel):
    color: Text | None
    size: Text | None


class ExtractedItem(StrictModel):
    requested_product: Text | None
    sku: Text | None
    variant: Variant
    quantity: Annotated[int, Field(ge=1, le=99)] | None


class Customer(StrictModel):
    name: Text | None
    phone: Text | None
    address: Text | None


class CatalogFilters(StrictModel):
    category: Text | None = None
    min_price: Annotated[int, Field(ge=0, le=1_000_000_000)] | None = None
    max_price: Annotated[int, Field(ge=0, le=1_000_000_000)] | None = None
    in_stock_only: bool = False


class Extraction(StrictModel):
    intent: INTENTS
    confidence: Literal["low", "medium", "high"]
    items: Annotated[list[ExtractedItem], Field(max_length=10)]
    customer: Customer
    order_reference: Text | None
    missing_information: Annotated[list[Text], Field(max_length=10)]
    requires_human_review: bool
    evidence: Annotated[list[Text], Field(max_length=10)]
    catalog_filters: CatalogFilters = Field(default_factory=CatalogFilters)


class OutputError(Exception):
    def __init__(self, code):
        self.code = code


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


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


NUMBER_WORDS = {"mot": 1, "hai": 2, "ba": 3, "bon": 4, "nam": 5, "sau": 6, "bay": 7, "tam": 8, "chin": 9, "muoi": 10}


def money_amounts(text):
    matches = re.findall(r"(?<![a-z0-9])(\d+(?:[.,]\d+)*)\s*(trieu|tr|nghin|ngan|k)?\b", plain_text(text))
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


def plain_text(text):
    """Lowercase and strip Vietnamese accents but keep punctuation, unlike text_utils.normalize."""
    return "".join(c for c in unicodedata.normalize("NFD", text.lower().replace("đ", "d")) if unicodedata.category(c) != "Mn")


def quantity_source(message, customer=None):
    text = plain_text(message)
    text = re.split(r"\b(?:ten|nguoi nhan|sdt|so dien thoai|giao ve|giao den|dia chi)\b", text)[0]
    if customer:
        for value in customer.model_dump().values():
            if value:
                text = text.replace(plain_text(value), " ")
    text = re.sub(r"\b[a-z][a-z0-9]*(?:-[a-z0-9]+){2,}\b", " ", text)
    text = re.sub(r"\b\d+(?:[.,]\d+)?\s*(?:inches|inch|cm|mm|kg|g|ml)\b", " ", text)
    text = re.sub(r"\bsize\s+[a-z0-9]+\b", " ", text)
    text = re.sub(r"(?<!\w)-\d+(?:[.,]\d+)?|\b\d+[.,]\d+\b", " invalidquantity ", text)
    return " " + normalize(text) + " "


def discard_implicit_quantities(data, message):
    source = quantity_source(message, data.customer)
    explicit = " invalidquantity " in source or re.search(r"\b\d+\b", source) or any(" " + word + " " in source for word in NUMBER_WORDS)
    if data.intent in {"create_order", "update_order"} and not explicit:
        for item in data.items:
            item.quantity = None
    return data


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
