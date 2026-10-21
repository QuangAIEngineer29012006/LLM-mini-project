from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


Sku = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[A-Z0-9][A-Z0-9_-]{0,39}$")]
Quantity = Annotated[int, Field(ge=1, le=99)]


class CartItem(StrictModel):
    sku: Sku
    quantity: Quantity


class QuantityChange(StrictModel):
    quantity: Quantity


class Shipping(StrictModel):
    recipient_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)]
    phone: Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=20)]
    address: Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=200)]


class Checkout(StrictModel):
    shipping: Shipping


class ItemChange(StrictModel):
    sku: Sku | None = None
    quantity: Quantity | None = None

    @model_validator(mode="after")
    def require_change(self):
        if not self.model_fields_set or any(getattr(self, f) is None for f in self.model_fields_set):
            raise ValueError("Cần sku hoặc quantity có giá trị hợp lệ")
        return self


class ChatRequest(StrictModel):
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
