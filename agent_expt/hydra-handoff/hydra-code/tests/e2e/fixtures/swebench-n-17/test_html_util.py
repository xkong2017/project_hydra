from html_util import escape_html, escape_attribute, strip_tags


def test_escape_lt():
    assert escape_html("<hello>") == "&lt;hello&gt;"


def test_escape_ampersand():
    assert escape_html("a & b") == "a &amp; b"


def test_escape_quotes_in_attribute():
    result = escape_attribute('say "hello"')
    assert "&quot;" in result, f"Expected &quot; in {result}"


def test_escape_single_quote():
    result = escape_attribute("it's")
    assert "&#x27;" in result or "&apos;" in result or "'" not in result.split("&quot;")[0],         f"Single quote not escaped in {result}"


def test_strip_tags():
    assert strip_tags("<b>bold</b>") == "bold"


def test_escape_twice_is_idempotent():
    once = escape_html("<>&")
    twice = escape_html(once)
    assert once == twice, f"Escaping twice changed output: {once} -> {twice}"
