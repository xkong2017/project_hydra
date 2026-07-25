def find_first(items, predicate):
    for item in items:
        if predicate(item):
            return item
    return None


def find_all(items, predicate):
    return [item for item in items if predicate(item)]


def find_last(items, predicate):
    result = None
    for item in items:
        if predicate(item):
            result = item
    return result


def count_until(items, predicate, limit):
    count = 0
    for item in items:
        if predicate(item):
            count += 1
    return count
