"""Bước 3-4: đơn nháp (mã đơn, item, tổng tiền, trạng thái) và sửa đơn theo quyền backend cho phép."""
import streamlit as st

from api_client import ApiError
from common import render_order, show_error, show_flash
from formatting import EDITABLE_STATUSES, STATUS_LABEL, safe_md

client = st.session_state.client
st.title("Đơn hàng")
show_flash()

try:
    orders = client.list_orders()
except ApiError as err:
    show_error(err)
    st.stop()

if not orders:
    st.info("Bạn chưa có đơn nào. Đặt hàng ở trang Giao nhận hoặc nhắn tin ở trang Chat đặt hàng.")
    st.stop()

labels = {o["order_id"]: f"{o['order_id']} - {STATUS_LABEL.get(o['status'], o['status'])}" for o in orders}
ids = list(labels)
current = st.session_state.get("current_order_id")
order_id = st.selectbox(
    "Chọn đơn", ids, index=ids.index(current) if current in ids else 0, format_func=labels.get
)
st.session_state.current_order_id = order_id

try:
    order = client.get_order(order_id)
except ApiError as err:
    show_error(err)  # gồm cả 403/404 khi đơn không thuộc phiên này
    st.stop()

render_order(order)
if st.button("Tải lại đơn"):
    st.rerun()

st.subheader("Chỉnh sửa đơn")
if not order.get("editable", order["status"] in EDITABLE_STATUSES):
    st.info("Đơn ở trạng thái này không thể sửa. Liên hệ nhân viên nếu cần thay đổi.")
    st.stop()

for item in order["items"]:
    item_id = item["item_id"]
    with st.form(f"edit_{order_id}_{item_id}"):
        st.markdown(f"**{safe_md(item['name'])}**")
        col_variant, col_qty = st.columns(2)
        variants = item.get("available_variants") or []
        skus = [v["sku"] for v in variants] or [item["sku"]]
        names = {v["sku"]: v["label"] for v in variants}
        sku = col_variant.selectbox(
            "Phân loại", skus, key=f"sku_{order_id}_{item_id}",
            index=skus.index(item["sku"]) if item["sku"] in skus else 0,
            format_func=lambda s: names.get(s, item.get("variant_label", s)),
        )
        qty = col_qty.number_input(
            "Số lượng", min_value=1, step=1, value=int(item["quantity"]), key=f"qty_{order_id}_{item_id}"
        )
        saved = st.form_submit_button("Lưu thay đổi")
    if not saved:
        continue
    changes = {}
    if int(qty) != item["quantity"]:
        changes["quantity"] = int(qty)
    if sku != item["sku"]:
        changes["sku"] = sku
    if not changes:
        st.info("Chưa có thay đổi nào để lưu.")
        continue
    try:
        with st.spinner("Đang cập nhật..."):
            client.update_item(order_id, item_id, changes)
    except ApiError as err:
        show_error(err)  # quyền, trạng thái hoặc tồn kho: hiển thị đúng lý do backend trả về
    else:
        st.session_state.flash = ("success", "Đã cập nhật đơn. Giá và tồn kho đã được hệ thống kiểm tra lại.")
        st.rerun()
