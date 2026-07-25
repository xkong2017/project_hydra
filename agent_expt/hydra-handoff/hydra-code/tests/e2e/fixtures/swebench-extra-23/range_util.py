def generate_range(start, end):
    result = []
    current = start
    while current < end:
        result.append(current)
        current += 1
    return result


def generate_range_step(start, end, step=1):
    result = []
    current = start
    while current < end:
        result.append(current)
        current += step
    return result


def sum_range(start, end):
    return sum(generate_range(start, end))


def contains_duplicates(items):
    return len(items) != len(set(items))
