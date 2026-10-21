import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Đảm bảo các thư mục con trong dự án có trong sys.path
ROOT_DIR = Path(__file__).resolve().parent
for folder in ["frontend", "backend", "mocks"]:
    folder_path = str(ROOT_DIR / folder)
    if folder_path not in sys.path:
        sys.path.insert(0, folder_path)

import streamlit as st

from api_client import ApiError
from common import get_client, show_error

# Mặc định dùng backend API; FRONTEND_MOCK=1 để chạy riêng giao diện.
if "FRONTEND_MOCK" not in os.environ:
    os.environ["FRONTEND_MOCK"] = "0"


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
