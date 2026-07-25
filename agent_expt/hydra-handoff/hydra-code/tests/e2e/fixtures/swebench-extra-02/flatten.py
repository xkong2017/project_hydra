def flatten(items):
    result = []
    for item in items:
        if isinstance(item, list):
            result.extend(item)
        else:
            result.append(item)
    return result


def flatten_unique(items):
    return list(set(flatten(items)))


def flatten_to_dict(items):
    flat = flatten(items)
    return {str(i): v for i, v in enumerate(flat)}
