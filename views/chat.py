"""Bước 5: giao diện chat. Chỉ hiển thị hội thoại; hiểu tin nhắn và quyết định hành động là việc của backend."""
import streamlit as st

from api_client import ApiError
from common import render_order, show_error
from formatting import FIELD_LABEL, safe_md

client = st.session_state.client  # cùng phiên với luồng đặt hàng trên web
history = st.session_state.setdefault("chat_history", [])


def render_message(msg, idx):
    with st.chat_message(msg["role"]):
        if msg.get("error"):
            show_error(msg["error"])
            return
        st.markdown(safe_md(msg["text"]))  # luôn escape: tin nhắn là dữ liệu không tin cậy
        route = msg.get("route")
        missing = msg.get("missing_fields") or []
        if route == "ask_missing" and missing:
            st.info("Cần bổ sung: " + ", ".join(FIELD_LABEL.get(f) or safe_md(f) for f in missing))
        elif route == "handoff":
            st.warning("Yêu cầu cần nhân viên xem lại. Vui lòng liên hệ shop để được hỗ trợ.")
        order = msg.get("order")
        if order:
            render_order(order)
            if st.button("Xem và sửa đơn", key=f"open_order_{idx}"):
                st.session_state.current_order_id = order["order_id"]
                st.switch_page("views/orders.py")


st.title("Chat đặt hàng")
st.caption("Hỏi sản phẩm, giá, tồn kho hoặc đặt hàng. Ví dụ: “Cửa hàng bán những gì?”")

for idx, msg in enumerate(history):
    render_message(msg, idx)

prompt = st.chat_input("Nhập tin nhắn", max_chars=500)
if prompt:
    user_msg = {"role": "user", "text": prompt}
    history.append(user_msg)
    render_message(user_msg, len(history) - 1)
    with st.chat_message("assistant"):
        with st.spinner("Đang xử lý..."):
            try:
                data = client.chat(prompt)
                reply = {
                    "role": "assistant",
                    "text": data.get("reply", ""),
                    "route": data.get("route"),
                    "missing_fields": data.get("missing_fields"),
                    "order": data.get("order"),
                }
            except ApiError as err:
                reply = {"role": "assistant", "error": err}
    history.append(reply)
    if reply.get("order"):
        st.session_state.current_order_id = reply["order"]["order_id"]
    st.rerun()
