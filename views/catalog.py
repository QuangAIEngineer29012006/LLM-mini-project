"""Trang catalog: danh sách sản phẩm do API trả về (giá, tồn kho không lấy từ client)."""
import streamlit as st

from api_client import ApiError
from common import show_error, show_flash
from formatting import money, safe_md
from shop_logic import category_label, chunk, filter_products, price_text

COLUMNS = 3
client = st.session_state.client

st.title("Sản phẩm")
show_flash()

try:
    with st.spinner("Đang tải sản phẩm..."):
        products = client.list_products()
except ApiError as err:
    show_error(err)
    if st.button("Thử lại"):
        st.rerun()
    st.stop()

if not products:
    st.info("Hiện chưa có sản phẩm nào. Vui lòng quay lại sau.")
    st.stop()

f1, f2 = st.columns([3, 2])
query = f1.text_input("Tìm sản phẩm", placeholder="Ví dụ: áo thun, cà phê")
categories = sorted({p["category"] for p in products})
choice = f2.selectbox(
    "Nhóm sản phẩm", ["all"] + categories,
    format_func=lambda c: "Tất cả" if c == "all" else category_label(c),
)
shown = filter_products(products, None if choice == "all" else choice, query)

if not shown:
    st.info("Không có sản phẩm phù hợp. Thử từ khóa khác hoặc chọn nhóm khác.")
    st.stop()

for row in chunk(shown, COLUMNS):
    cols = st.columns(COLUMNS)
    for col, p in zip(cols, row):
        with col, st.container(border=True):
            st.markdown(f"**{safe_md(p['name'])}**")
            st.caption(category_label(p["category"]))
            st.markdown(price_text(p, money))
            st.caption("✅ Còn hàng" if p["in_stock"] else "❌ Hết hàng")
            if st.button("Xem chi tiết", key=f"view_{p['product_id']}"):
                st.session_state.selected_product = p["product_id"]
                st.switch_page("views/product.py")
