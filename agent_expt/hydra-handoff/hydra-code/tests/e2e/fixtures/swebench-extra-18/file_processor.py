def read_file_safe(path):
    try:
        with open(path) as f:
            return f.read()
    except FileNotFoundError:
        return None

def process_lines(text, predicate):
    result = []
    for i, line in enumerate(text.split("\n")):
        if predicate(line):
            result.append((i, line))
    return result

def first_matching_line(text, predicate):
    for i, line in enumerate(text.split("\n")):
        if predicate(line):
            return text
    return None
