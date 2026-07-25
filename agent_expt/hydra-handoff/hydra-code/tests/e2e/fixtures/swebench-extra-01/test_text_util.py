from text_util import substring, truncate, highlight


def test_substring_normal():
    assert substring("hello", 0, 3) == "hel"


def test_substring_full():
    assert substring("hello", 0, 5) == "hello"


def test_substring_middle():
    assert substring("hello world", 6, 5) == "world"


def test_substring_negative_start():
    assert substring("hello", -1, 3) == ""


def test_truncate():
    assert truncate("hello world", 5) == "hello"


def test_truncate_shorter():
    assert truncate("hi", 5) == "hi"


def test_highlight():
    assert highlight("hello world", 0, 5) == "[hello]"
