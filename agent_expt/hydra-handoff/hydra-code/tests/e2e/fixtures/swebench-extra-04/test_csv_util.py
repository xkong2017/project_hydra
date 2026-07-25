from csv_util import parse_csv_line, parse_csv, to_csv_row


def test_simple():
    assert parse_csv_line("a,b,c") == ["a", "b", "c"]


def test_quoted():
    assert parse_csv_line('a,"b,c",d') == ["a", "b,c", "d"]


def test_quoted_with_escaped_quote():
    assert parse_csv_line('a,"b""c",d') == ["a", 'b"c', "d"]


def test_empty_field():
    assert parse_csv_line("a,,c") == ["a", "", "c"]


def test_roundtrip():
    original = ["hello", "world"]
    assert parse_csv_line(to_csv_row(original)) == original


def test_roundtrip_with_comma():
    original = ["a", "b,c", "d"]
    assert parse_csv_line(to_csv_row(original)) == original
