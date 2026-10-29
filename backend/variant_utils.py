import re

from database.shop_db.text_utils import normalize


# Chuẩn hóa cách viết size để “15inch” và “15 inch” được đối chiếu như nhau.
def size_value(value):
    return re.sub(r"(?<=\d)\s*(?:inches|inch)\b", " inch", normalize(value))


# Bỏ nhãn “màu”, “size”, “cỡ” và chuẩn hóa giá trị trước khi so với biến thể.
def attribute_value(value, field):
    text = normalize(value)
    prefixes = {"color": ("mau", "color"), "size": ("kich co", "size", "co")}
    for prefix in prefixes.get(field, ()):
        if text.startswith(prefix + " "):
            text = text[len(prefix) + 1:]
            break
    return size_value(text) if field == "size" else text
