from fib import fibonacci, factorial, memoize


def test_fib_0():
    assert fibonacci(0) == 0


def test_fib_1():
    assert fibonacci(1) == 1


def test_fib_10():
    assert fibonacci(10) == 55


def test_fib_20():
    # Without memoization, this would be very slow
    # We're testing correctness, not speed here
    result = fibonacci(20)
    assert result == 6765


def test_factorial():
    assert factorial(5) == 120
