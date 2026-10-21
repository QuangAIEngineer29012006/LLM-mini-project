"""Exercise all six Streamlit pages against a temporary HTTP backend."""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]


def run():
    with tempfile.TemporaryDirectory() as folder:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        os.environ.update(API_BASE_URL=base, FRONTEND_MOCK="0")
        env = {**os.environ, "SHOP_DB_PATH": folder + "/shop.db", "LLM_PROVIDER": "fake"}
        server = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", str(port), "--no-access-log"],
                                  cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(100):
                try:
                    if requests.get(base + "/api/health", timeout=0.2).ok:
                        break
                except requests.RequestException:
                    pass
                time.sleep(0.1)
            else:
                raise RuntimeError("Backend did not start")
            from streamlit.testing.v1 import AppTest
            steps = []
            app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=15).run()

            def checked(label):
                if app.exception:
                    raise AssertionError([error.message for error in app.exception])
                if app.error:
                    raise AssertionError([error.value for error in app.error])
                steps.append(label)

            def button(label):
                return next(b for b in app.button if b.label == label)

            checked("Catalog reads six active products through HTTP")
            assert len(app.button) == 6
            app.text_input[0].set_value("ao thun").run()
            assert len(app.button) == 1
            app.button(key="view_1").click().run()
            checked("Catalog search and product navigation")
            app.radio[0].set_value("TSH-WHT-M").run()
            assert button("Thêm vào giỏ").disabled
            app.radio[0].set_value("TSH-BLK-M").run()
            app.number_input[0].set_value(2).run()
            button("Thêm vào giỏ").click().run()
            checked("Sold-out variant disabled; two available items added")
            app.switch_page("views/cart.py").run()
            app.number_input[0].set_value(3).run()
            button("Cập nhật").click().run()
            checked("Cart quantity updated through API")
            button("Xóa").click().run()
            assert "trống" in app.info[0].value
            checked("Cart removal and empty state")
            client = app.session_state.client
            client.add_to_cart("TSH-BLK-M", 2)
            app.switch_page("views/cart.py").run()
            button("Tiếp tục: thông tin giao nhận").click().run()
            assert app.title[0].value == "Thông tin giao nhận"
            app.switch_page("views/checkout.py").run()
            app.text_input(key="ship_name").set_value("Khách Demo")
            app.text_input(key="ship_phone").set_value("0912345678")
            app.text_area(key="ship_address").set_value("12 Đường Mẫu, Phường Mẫu, Quận 7")
            button("Gửi yêu cầu đặt hàng").click().run()
            checked("Checkout creates a pending order and opens Orders")
            assert len(client.list_orders()) == 1, {"titles": [v.value for v in app.title], "info": [v.value for v in app.info],
                                                   "success": [v.value for v in app.success], "cart": client.get_cart()}
            app.switch_page("views/orders.py").run()
            app.number_input[0].set_value(3)
            button("Lưu thay đổi").click().run()
            assert client.list_orders()[0]["total"] == 450000
            checked("Orders edits quantity and recomputes database total")
            app.switch_page("views/chat.py").run()
            app.chat_input[0].set_value("Chốt 1 nón đen").run()
            checked("Chat asks for missing shipping fields")
            app.chat_input[0].set_value("Tên Khách Demo, SĐT 0912345678, giao về 12 Đường Mẫu, Quận 7").run()
            assert len(client.list_orders()) == 2
            checked("Chat draft appears in the same session's order list")
            button("Xem và sửa đơn").click().run()
            app.switch_page("views/orders.py").run()
            button("Tải lại đơn").click().run()
            checked("Chat order navigation and refresh")
            report = {"backend": "real HTTP + temporary SQLite", "llm": "FakeLLMClient", "pages": 6,
                      "passed": True, "steps": steps,
                      "limits": "Streamlit AppTest interactions; browser rendering and Gemini network call are not covered."}
            target = ROOT / "sample_results/frontend_smoke.json"
            target.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"PASS: {len(steps)} UI integration steps across 6 pages; {target}")
        finally:
            server.terminate()
            server.wait(timeout=10)


if __name__ == "__main__":
    run()
