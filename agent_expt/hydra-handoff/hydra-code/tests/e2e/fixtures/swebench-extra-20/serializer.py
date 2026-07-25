def serialize(obj):
    if obj is None:
        return "null"
    if isinstance(obj, bool):
        return "true" if obj else "false"
    if isinstance(obj, (int, float)):
        return str(obj)
    if isinstance(obj, str):
        return '"' + obj + '"'
    if isinstance(obj, (list, tuple)):
        items = ", ".join(serialize(item) for item in obj)
        return "[" + items + "]"
    if isinstance(obj, dict):
        items = ", ".join(
            serialize(k) + ": " + serialize(v) for k, v in obj.items()
        )
        return "{" + items + "}"
    return str(obj)
