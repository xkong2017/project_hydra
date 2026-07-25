def process_items(items):
    result = []
    for item in items:
        result.append(item * 2)
    return result


def filter_and_process(items):
    result = []
    for item in items:
        if item is not None:
            result.append(process_items([item])[0])
    return result


def process_with_skip(items, skip_value):
    result = []
    for item in items:
        if item != skip_value:
            result.append(item)
    return result
