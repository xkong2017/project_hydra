import pytest
from http_client import build_request, send_request


def test_get_without_body():
    r = build_request("GET", "http://example.com")
    assert send_request(r) == "GET http://example.com"


def test_get_with_params():
    r = build_request("GET", "http://example.com", params={"q": "test"})
    result = send_request(r)
    assert "q=test" in result


def test_get_with_body_raises():
    r = build_request("GET", "http://example.com", data="payload")
    with pytest.raises(ValueError, match="body"):
        send_request(r)


def test_post_with_body():
    r = build_request("POST", "http://example.com", data="payload")
    assert send_request(r) == "POST http://example.com"
