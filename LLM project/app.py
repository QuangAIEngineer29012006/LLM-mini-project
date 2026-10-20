"""Điểm vào của frontend. Chạy: streamlit run app.py"""
import os

import streamlit as st

from api_client import ApiError
from common import get_client, show_error

st.set_page_config(page_title="Live Commerce", page_icon="🛍️", layout="wide")

try:
    get_client()  # tạo phiên dùng chung cho mọi màn hình
except ApiError as err:
    show_error(err)
    st.stop()

if os.getenv("FRONTEND_MOCK") == "1":
    st.sidebar.warning("Đang chạy với dữ liệu giả (mock), chưa nối backend.")

pages = [
    st.Page("views/catalog.py", title="Sản phẩm", icon="🛍️", default=True),
    st.Page("views/product.py", title="Chi tiết sản phẩm", icon="🔎"),
    st.Page("views/cart.py", title="Giỏ hàng", icon="🛒"),
    st.Page("views/checkout.py", title="Giao nhận", icon="🚚"),
    st.Page("views/orders.py", title="Đơn hàng", icon="🧾"),
    st.Page("views/chat.py", title="Chat đặt hàng", icon="💬"),
]
st.navigation(pages).run()
