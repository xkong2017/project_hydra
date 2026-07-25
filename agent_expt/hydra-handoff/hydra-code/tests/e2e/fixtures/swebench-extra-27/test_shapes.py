from shapes import ColoredSizedShape


def test_mro():
    obj = ColoredSizedShape("red", 10)
    assert obj.color == "red"
    assert obj.size == 10


def test_describe_includes_color():
    obj = ColoredSizedShape("blue", 20)
    result = obj.describe()
    assert "blue" in result, f"describe() should mention color: {result}"
    assert "20" in result, f"describe() should mention size: {result}"
