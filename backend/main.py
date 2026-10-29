import json
import logging
import sqlite3
import threading
import time
import uuid
from collections import deque
from contextlib import asynccontextmanager, contextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from database.shop_db import catalog_service as catalog, order_service as orders
from database.shop_db.audit_service import Ctx
from database.shop_db.db import connect, transaction
from database.shop_db.errors import DataServiceError
from src.llm_client import make_client

from .chat_service import chat
from .config import Settings
from .errors import ApiProblem, database_problem
from .models import CartItem, ChatRequest, Checkout, ItemChange, QuantityChange
from .services import (cart_order, cart_view, checkout, item_row, order_number,
                       order_view, owned_order, product_view, update_item)
from .storage import authenticate, initialize, new_session, request_key


class RateLimiter:
    # Khởi tạo bộ đếm request và khóa để nhiều luồng cập nhật an toàn.
    def __init__(self):
        self.entries = {}
        self.lock = threading.Lock()

    # Chặn khi số request của một IP hoặc phiên vượt giới hạn trong 60 giây.
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


def _client_ip(request):
    return request.client.host if request.client else "local"


# Đóng gói lỗi thành JSON thống nhất, kèm request ID và thời gian chờ nếu bị giới hạn.
def _error(problem, request_id=None):
    headers = {"Retry-After": "60"} if problem.status == 429 else {}
    return JSONResponse(status_code=problem.status, headers=headers,
                        content={"error": {"code": problem.code, "message": problem.message,
                                           "fields": problem.fields}, "request_id": request_id})


# Tạo ứng dụng FastAPI, gắn cấu hình, LLM, middleware và các endpoint.
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
            limiter.check("http", _client_ip(request), settings.request_limit)
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
        limiter.check("session", _client_ip(request), settings.session_limit)
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


app = create_app()
