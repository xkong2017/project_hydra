from serializer import serialize

def test_null():
    assert serialize(None) == "null"

def test_int():
    assert serialize(42) == "42"

def test_string():
    assert serialize("hello") == '"hello"'

def test_string_with_quotes():
    result = serialize('say "hello"')
    assert '\\"' in result, f"Quotes should be escaped in {result}"

def test_list():
    assert serialize([1, 2, 3]) == "[1, 2, 3]"

def test_dict_with_null():
    result = serialize({"a": None, "b": 1})
    assert '"a": null' in result
    assert '"b": 1' in result

def test_nested():
    result = serialize({"x": {"y": [1, None]}})
    assert "null" in result
