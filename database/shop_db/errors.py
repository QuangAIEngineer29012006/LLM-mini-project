class DataServiceError(Exception):
    code = "data_error"

    def __init__(self, message: str, **details):
        super().__init__(message)
        self.message = message
        self.details = details

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "details": self.details}


class ValidationError(DataServiceError):
    code = "validation_error"


class SkuNotFound(DataServiceError):
    code = "sku_not_found"


class ProductNotFound(DataServiceError):
    code = "product_not_found"


class InsufficientStock(DataServiceError):
    code = "insufficient_stock"


class OutOfStock(InsufficientStock):
    code = "out_of_stock"


class PriceChanged(DataServiceError):
    code = "price_changed"


class OrderNotFound(DataServiceError):
    code = "order_not_found"


class ItemNotFound(DataServiceError):
    code = "item_not_found"


class OrderNotEditable(DataServiceError):
    code = "order_not_editable"


class InvalidStatusTransition(DataServiceError):
    code = "invalid_status_transition"


class IdempotencyConflict(DataServiceError):
    code = "idempotency_conflict"


class ConversationNotFound(DataServiceError):
    code = "conversation_not_found"
