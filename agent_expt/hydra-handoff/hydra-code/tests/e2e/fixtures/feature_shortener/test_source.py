import pytest
from source import URLShortener

def test_shorten_and_resolve():
    shortener = URLShortener()
    code = shortener.shorten("https://example.com/very/long/url")
    assert len(code) > 0 and len(code) < 10
    assert shortener.resolve(code) == "https://example.com/very/long/url"

def test_custom_alias():
    shortener = URLShortener()
    code = shortener.shorten("https://example.com", alias="my-link")
    assert code == "my-link"
    assert shortener.resolve("my-link") == "https://example.com"

def test_invalid_url():
    shortener = URLShortener()
    with pytest.raises(ValueError):
        shortener.shorten("not-a-url")

def test_nonexistent_code():
    shortener = URLShortener()
    assert shortener.resolve("nonexistent") is None

def test_expiry():
    import time
    shortener = URLShortener()
    code = shortener.shorten("https://example.com", expiry_days=0)
    assert shortener.resolve(code) is None, "Expired URL should return None"

def test_multiple_urls():
    shortener = URLShortener()
    c1 = shortener.shorten("https://a.com")
    c2 = shortener.shorten("https://b.com")
    assert c1 != c2
    assert shortener.resolve(c1) == "https://a.com"
    assert shortener.resolve(c2) == "https://b.com"

def test_alias_conflict():
    shortener = URLShortener()
    shortener.shorten("https://example.com", alias="my-link")
    with pytest.raises(ValueError):
        shortener.shorten("https://other.com", alias="my-link")
