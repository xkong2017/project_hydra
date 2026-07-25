from math_util import round_half_up, calculate_tax


def test_round_half_up_basic():
    assert round_half_up(2.5) == 3.0


def test_round_half_up_negative():
    assert round_half_up(-2.5) == -2.0, f"Got {round_half_up(-2.5)}"


def test_round_half_up_two_decimals():
    assert round_half_up(3.141, 2) == 3.14


def test_round_half_up_2dp():
    assert round_half_up(2.675, 2) == 2.68


def test_calculate_tax():
    result = calculate_tax(10.00)
    assert result == 0.70
