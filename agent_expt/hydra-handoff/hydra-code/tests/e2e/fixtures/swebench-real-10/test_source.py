from source import build_request

def test_get_no_body():
    req = build_request("GET", "http://example.com")
    assert req["method"] == "GET"

def test_get_no_content_length():
    req = build_request("GET", "http://example.com")
    assert "Content-Length" not in req["headers"],         "GET requests should not have Content-Length!"

def test_post_has_content_length():
    req = build_request("POST", "http://example.com", body="data")
    assert "Content-Length" in req["headers"]
