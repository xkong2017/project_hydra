from range_util import generate_range, generate_range_step, sum_range


def test_range_1_to_3():
    assert generate_range(1, 3) == [1, 2, 3], f"Got {generate_range(1, 3)}"


def test_range_1_to_1():
    assert generate_range(1, 1) == [1], f"Got {generate_range(1, 1)}"


def test_range_0_to_0():
    assert generate_range(0, 0) == [0]


def test_range_step():
    assert generate_range_step(0, 5, 2) == [0, 2, 4]
