from database.shop_db.errors import DataServiceError


class ApiProblem(Exception):
    # Lưu mã HTTP, mã lỗi, thông báo và lỗi từng trường để API phản hồi thống nhất.
    def __init__(self, status, code, message, fields=None):
        self.status = status
        self.code = code
        self.message = message
        self.fields = fields or {}


# Ánh xạ lỗi database sang mã HTTP và đổi tên trường cho khớp dữ liệu frontend.
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
