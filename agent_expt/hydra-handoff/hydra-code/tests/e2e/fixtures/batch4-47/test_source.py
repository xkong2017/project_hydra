from source import add


def test_basic():
    assert add(2, 3) == 5, f"Expected 5, got {add(2, 3)}"


def test_negative():
    assert add(-1, 1) == 0, f"Expected 0, got {add(-1, 1)}"


def test_zero():
    assert add(0, 5) == 5


def test_large():
    assert add(100, 200) == 300


def test_decimals():
    assert add(1.5, 2.5) == 4.0
