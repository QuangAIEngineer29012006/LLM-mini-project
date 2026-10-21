"""Trang giỏ hàng: sửa / xóa item, tổng tiền do server trả về, rồi chuyển sang giao nhận (Huy)."""
import os

import streamlit as st

from api_client import ApiError
from common import show_error, show_flash
from formatting import money, safe_md
from shop_logic import MAX_QTY

CHECKOUT_PAGE = os.getenv("CHECKOUT_PAGE", "views/checkout.py")
client = st.session_state.client

st.title("Giỏ hàng")
show_flash()

try:
    cart = client.get_cart()
except ApiError as err:
    show_error(err)
    st.stop()

items = cart.get("items") or []
if not items:
    st.info("Giỏ hàng đang trống.")
    st.page_link("views/catalog.py", label="Đi xem sản phẩm →")
    st.stop()

for item in items:
    iid = item["item_id"]
    with st.container(border=True):
        c1, c2, c3 = st.columns([4, 2, 2])
        c1.markdown(
            f"**{safe_md(item['name'])}**  \n"
            f"{safe_md(item.get('variant_label', ''))} · {money(item['unit_price'])}"
        )
        # key chứa số lượng từ server: server đổi thì ô nhập tự về giá trị đúng
        qty = c2.number_input(
            "Số lượng", min_value=1, max_value=MAX_QTY, value=int(item["quantity"]), step=1,
            key=f"cart_qty_{iid}_{item['quantity']}",
        )
        c3.markdown(f"Thành tiền  \n**{money(item['line_total'])}**")

        b1, b2, _ = st.columns([1, 1, 3])
        if b1.button("Cập nhật", key=f"upd_{iid}", disabled=int(qty) == int(item["quantity"])):
            try:
                client.update_cart_item(iid, int(qty))
            except ApiError as err:
                show_error(err)  # ví dụ vượt tồn kho: giỏ giữ nguyên
            else:
                st.session_state.flash = ("success", "Đã cập nhật giỏ hàng.")
                st.rerun()
        if b2.button("Xóa", key=f"del_{iid}"):
            try:
                client.remove_cart_item(iid)
            except ApiError as err:
                show_error(err)
            else:
                st.session_state.flash = ("success", "Đã xóa sản phẩm khỏi giỏ.")
                st.rerun()

st.markdown(f"### Tổng tiền: {money(cart['total'])}")
st.caption("Giá và tổng tiền do hệ thống tính. Hệ thống kiểm tra lại khi bạn gửi yêu cầu đặt hàng.")
n1, n2 = st.columns(2)
n1.page_link("views/catalog.py", label="← Tiếp tục mua sắm")
if n2.button("Tiếp tục: thông tin giao nhận", type="primary"):
    st.switch_page(CHECKOUT_PAGE)
