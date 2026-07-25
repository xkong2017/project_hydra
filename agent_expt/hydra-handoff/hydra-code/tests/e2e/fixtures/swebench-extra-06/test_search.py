from search import find_first, find_all, find_last, count_until


def test_find_first():
    items = [1, 2, 3, 4, 5]
    result = find_first(items, lambda x: x > 3)
    assert result == 4


def test_find_first_none():
    assert find_first([1, 2], lambda x: x > 10) is None


def test_find_all():
    assert find_all([1, 2, 3, 4], lambda x: x % 2 == 0) == [2, 4]


def test_count_until():
    result = count_until([1, 2, 3, 4, 5], lambda x: x > 2, 2)
    assert result == 2
