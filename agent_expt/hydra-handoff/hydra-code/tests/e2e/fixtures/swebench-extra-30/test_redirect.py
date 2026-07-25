from redirect import handle_redirect, HttpResponse


def test_no_redirect():
    response = HttpResponse(200, {"Content-Type": "text/html"})
    result = handle_redirect(response, "Bearer token123")
    assert result.status == 200


def test_redirect_preserves_auth():
    response = HttpResponse(302, {"Location": "/new-path"})
    result = handle_redirect(response, "Bearer mytoken")
    assert result.headers.get("Authorization") == "Bearer mytoken",         "Auth header should be preserved on redirect!"


def test_redirect_without_auth():
    response = HttpResponse(302, {"Location": "/new-path"})
    result = handle_redirect(response, None)
    assert "Authorization" not in result.headers
