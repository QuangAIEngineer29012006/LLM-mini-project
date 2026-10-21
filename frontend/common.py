"""Thành phần UI dùng chung giữa các màn hình."""
import os

import streamlit as st

from api_client import ApiClient
from formatting import ERROR_TITLE, STATUS_LABEL, money, safe_md
from mock_backend import MockClient


def get_client():
    """Một client (một phiên) cho cả đặt hàng trên web và chat."""
    if "client" not in st.session_state:
        client = MockClient() if os.getenv("FRONTEND_MOCK") == "1" else ApiClient()
        client.start_session()  # lỗi thì ApiError nổi lên; lần chạy lại sẽ thử lại
        st.session_state.client = client
    return st.session_state.client


def show_error(err):
    title = ERROR_TITLE.get(err.code) or ERROR_TITLE.get(err.kind) or "Có lỗi xảy ra"
    st.error(f"**{title}.** {safe_md(err.message)}")


def show_flash():
    """Hiện thông báo một lần, được đặt trước khi chuyển màn hình."""
    kind, text = st.session_state.pop("flash", (None, None))
    if kind:
        getattr(st, kind)(text)


def render_items(items):
    st.dataframe(
        [
            {
                "Sản phẩm": i["name"],
                "Phân loại": i.get("variant_label", ""),
                "Số lượng": i["quantity"],
                "Đơn giá": money(i["unit_price"]),
                "Thành tiền": money(i["line_total"]),
            }
            for i in items
        ],
        hide_index=True,
    )


def render_order(order):
    """Mã đơn, trạng thái, tổng tiền, item và thông tin giao nhận (toàn bộ do backend trả về)."""
    c1, c2, c3 = st.columns(3)
    c1.metric("Mã đơn", order["order_id"])
    c2.metric("Trạng thái", STATUS_LABEL.get(order["status"], order["status"]))
    c3.metric("Tổng tiền", money(order["total"]))
    render_items(order["items"])
    ship = order.get("shipping") or {}
    if ship:
        st.caption(
            "Giao đến: "
            + safe_md(f"{ship.get('recipient_name', '')}, {ship.get('phone', '')}, {ship.get('address', '')}")
        )
