from encoder import match_header, has_header


def test_match_str_str():
    assert match_header("Content-Type", "content-type")


def test_match_bytes_str():
    assert match_header(b"Content-Type", "content-type")


def test_match_str_bytes():
    assert match_header("Content-Type", b"content-type")


def test_match_bytes_bytes():
    assert match_header(b"Content-Type", b"content-type")


def test_has_header_mixed():
    headers = {b"Content-Type": "application/json"}
    assert has_header(headers, "Content-Type")


def test_has_header_missing():
    headers = {"Accept": "text/html"}
    assert not has_header(headers, "Content-Type")


def test_normalize_strips_whitespace():
    from encoder import normalize_header
    assert normalize_header("  Content-Type  ") == "content-type"
