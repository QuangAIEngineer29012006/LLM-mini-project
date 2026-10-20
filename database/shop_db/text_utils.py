import re
import unicodedata


def normalize(text) -> str:
    if not text:
        return ""
    t = unicodedata.normalize("NFD", str(text).lower().replace("đ", "d"))
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", t).strip()
