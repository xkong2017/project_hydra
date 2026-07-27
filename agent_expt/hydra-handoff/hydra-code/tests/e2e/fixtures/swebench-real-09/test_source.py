from source import extract_type_hints

class MyClass:
    x: int = 5
    y: str = "hello"

def test_extract_hints():
    hints = extract_type_hints(MyClass)
    assert hints["x"] == "int"
    assert hints["y"] == "str"
