from database.shop_db.text_utils import normalize


def attribute_value(value, field):
    text = normalize(value)
    prefixes = {"color": ("mau", "color"), "size": ("kich co", "size", "co")}
    for prefix in prefixes.get(field, ()):
        if text.startswith(prefix + " "):
            return text[len(prefix) + 1:]
    return text
