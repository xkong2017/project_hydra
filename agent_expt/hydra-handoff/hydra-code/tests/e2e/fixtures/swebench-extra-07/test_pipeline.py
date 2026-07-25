from pipeline import process_items, process_with_skip


def test_process_items():
    assert process_items([1, 2, 3]) == [2, 4, 6]


def test_skip_none():
    result = process_items([1, None, 2, None, 3])
    assert result == [2, 4, 6], f"Got {result}"


def test_skip_value():
    result = process_with_skip([1, 2, 3, 2, 4], 2)
    assert result == [1, 3, 4]


def test_all_skip():
    assert process_with_skip([1, 1, 1], 1) == []
