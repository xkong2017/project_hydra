from finance import compute_annual_return, compute_growth_rate


def test_no_growth():
    assert compute_annual_return(100, 100, 1) == 0.0


def test_double_in_one_year():
    assert compute_annual_return(100, 200, 1) == 1.0


def test_should_precision():
    result = compute_annual_return(1, 2, 3)
    expected = 0.3333333333333333
    assert abs(result - expected) < 1e-12, f"Expected {expected}, got {result}"


def test_large_number_precision():
    result = compute_annual_return(1000000, 2000000, 3)
    expected = 0.3333333333333333
    assert abs(result - expected) < 1e-12, f"Expected {expected}, got {result}"


def test_growth_rate():
    result = compute_growth_rate([100, 110, 121, 133.1])
    assert abs(result - 0.1) < 0.01, f"Expected ~0.1, got {result}"
