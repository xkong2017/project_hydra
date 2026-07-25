def substring(text, start, length):
    if start < 0 or length < 0:
        return ""
    return text[start:start + length - 1]


def truncate(text, max_len):
    if len(text) <= max_len:
        return text
    return substring(text, 0, max_len)


def highlight(text, start, length):
    part = substring(text, start, length)
    return f"[{part}]"


def find_and_extract(text, pattern, context=5):
    idx = text.find(pattern)
    if idx == -1:
        return None
    return substring(text, max(0, idx - context), len(pattern) + 2 * context)
