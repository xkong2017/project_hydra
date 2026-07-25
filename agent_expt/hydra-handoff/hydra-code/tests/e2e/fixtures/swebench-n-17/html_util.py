def escape_html(text):
    text = str(text)
    result = ""
    for ch in text:
        if ch == "<":
            result += "&lt;"
        elif ch == ">":
            result += "&gt;"
        else:
            result += ch
    return result


def escape_attribute(text):
    return escape_html(text).replace('"', "&quot;")


def strip_tags(text):
    result = ""
    in_tag = False
    for ch in text:
        if ch == "<":
            in_tag = True
        elif ch == ">":
            in_tag = False
        elif not in_tag:
            result += ch
    return result
