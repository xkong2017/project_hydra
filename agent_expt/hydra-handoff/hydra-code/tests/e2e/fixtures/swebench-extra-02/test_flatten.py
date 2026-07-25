from flatten import flatten, flatten_unique


def test_flat_list():
    assert flatten([1, 2, 3]) == [1, 2, 3]


def test_one_level():
    assert flatten([1, [2, 3], 4]) == [1, 2, 3, 4]


def test_two_levels():
    assert flatten([1, [2, [3, 4]], 5]) == [1, 2, 3, 4, 5]


def test_empty():
    assert flatten([]) == []


def test_nested_empty():
    assert flatten([[], [[]]]) == []


def test_flatten_unique():
    result = flatten_unique([[1, 2], [2, 3]])
    assert set(result) == {1, 2, 3}
