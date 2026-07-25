from file_processor import process_lines, first_matching_line


def test_process_lines():
    text = "a\nb\nc"
    result = process_lines(text, lambda x: x in ("a", "c"))
    assert result == [(0, "a"), (2, "c")]


def test_first_matching():
    text = "x\ny\nz"
    result = first_matching_line(text, lambda x: x > "x")
    assert result == "y"


def test_first_matching_none():
    text = "a\nb"
    assert first_matching_line(text, lambda x: x == "z") is None
