"""Trang chi tiết sản phẩm: chọn biến thể + số lượng, thêm vào giỏ (chỉ gửi sku và quantity)."""
import streamlit as st

from api_client import ApiError
from common import show_error
from formatting import money, safe_md
from shop_logic import (
    category_label, max_selectable, pick_default_variant, stock_label, variant_option_label,
)

client = st.session_state.client
pid = st.session_state.get("selected_product")

st.page_link("views/catalog.py", label="← Quay lại danh sách")
if not pid:
    st.info("Hãy chọn một sản phẩm ở trang Sản phẩm.")
    st.stop()

try:
    with st.spinner("Đang tải sản phẩm..."):
        product = client.get_product(pid)
except ApiError as err:
    show_error(err)
    st.stop()

variants = product.get("variants") or []
st.title(safe_md(product["name"]))
st.caption(category_label(product["category"]))
if product.get("description"):
    st.write(safe_md(product["description"]))
if not variants:
    st.warning("Sản phẩm này hiện chưa có phân loại để bán.")
    st.stop()

by_sku = {v["sku"]: v for v in variants}
skus = list(by_sku)
sku = st.radio(
    "Phân loại", skus, index=skus.index(pick_default_variant(variants)),
    format_func=lambda s: variant_option_label(by_sku[s], money), key=f"variant_{pid}",
)
v = by_sku[sku]
sold_out = v["stock"] <= 0

st.markdown(f"### {money(v['unit_price'])}")
if sold_out:
    st.error(stock_label(v["stock"]))
else:
    st.caption(stock_label(v["stock"]))

qty = st.number_input(
    "Số lượng", min_value=1, max_value=max_selectable(v["stock"]), value=1, step=1,
    key=f"qty_{sku}", disabled=sold_out,
)
if st.button("Thêm vào giỏ", type="primary", disabled=sold_out):
    try:
        with st.spinner("Đang thêm vào giỏ..."):
            cart = client.add_to_cart(sku, int(qty))  # chỉ gửi sku + số lượng
    except ApiError as err:
        show_error(err)  # hết hàng / số lượng sai / lỗi mạng: không báo thành công
    else:
        st.success(f"Đã thêm {int(qty)} × {safe_md(v['label'])} vào giỏ. Giỏ hiện có {len(cart['items'])} dòng sản phẩm.")
        st.page_link("views/cart.py", label="Xem giỏ hàng →")
