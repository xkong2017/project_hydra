def normalize_header(value):
    return value.strip().lower()


def match_header(expected, actual):
    return normalize_header(expected) == normalize_header(actual)


def has_header(headers, target):
    for key in headers:
        if match_header(key, target):
            return True
    return False
