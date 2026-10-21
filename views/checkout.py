"""Bước 2: form giao nhận. Giỏ hàng lấy lại từ API, không truyền giá qua client."""
import uuid

import streamlit as st

from api_client import ApiError
from common import render_items, show_error
from formatting import money
from validators import validate_shipping

client = st.session_state.client
st.title("Thông tin giao nhận")

try:
    cart = client.get_cart()
except ApiError as err:
    show_error(err)
    st.stop()

if not cart.get("items"):
    st.info("Giỏ hàng đang trống. Thêm sản phẩm vào giỏ, rồi quay lại để nhập thông tin giao nhận.")
    st.stop()

st.subheader("Giỏ hàng")
render_items(cart["items"])
st.markdown(f"**Tổng tiền:** {money(cart['total'])}")
st.caption("Giá và tổng tiền do hệ thống tính. Hệ thống kiểm tra lại khi bạn gửi yêu cầu.")

st.subheader("Người nhận")
with st.form("shipping_form"):
    name = st.text_input("Tên người nhận", max_chars=100, key="ship_name")
    name_err = st.empty()
    phone = st.text_input("Số điện thoại", max_chars=20, key="ship_phone", placeholder="0912345678")
    phone_err = st.empty()
    address = st.text_area(
        "Địa chỉ giao hàng", max_chars=300, key="ship_address",
        placeholder="Số nhà, đường, phường/xã, quận/huyện, tỉnh/thành",
    )
    address_err = st.empty()
    submitted = st.form_submit_button("Gửi yêu cầu đặt hàng", type="primary")

if submitted:
    slots = {"recipient_name": name_err, "phone": phone_err, "address": address_err}
    shipping, errors = validate_shipping(name, phone, address)
    if not errors:
        # Cùng một khóa cho mọi lần bấm gửi lại, để backend (nếu hỗ trợ) không tạo đơn trùng.
        key = st.session_state.setdefault("checkout_key", uuid.uuid4().hex)
        try:
            with st.spinner("Đang gửi yêu cầu..."):
                order = client.create_order(shipping, idempotency_key=key)
        except ApiError as err:
            errors = {f: m for f, m in err.fields.items() if f in slots}  # lỗi theo trường từ backend
            show_error(err)  # API lỗi thì không bao giờ báo thành công
        else:
            st.session_state.pop("checkout_key", None)
            st.session_state.current_order_id = order["order_id"]
            st.session_state.flash = (
                "success",
                f"Đã tạo đơn nháp {order['order_id']}. Kiểm tra lại thông tin rồi chờ xác nhận.",
            )
            st.switch_page("views/orders.py")
    for field, message in errors.items():
        slots[field].error(message)
