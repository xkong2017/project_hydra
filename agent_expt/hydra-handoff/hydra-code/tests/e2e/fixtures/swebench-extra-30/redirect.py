class HttpResponse:
    def __init__(self, status, headers, body=""):
        self.status = status
        self.headers = headers
        self.body = body


def handle_redirect(response, auth_header):
    if 300 <= response.status < 400:
        return HttpResponse(response.status, dict(response.headers), response.body)
    return response


def follow_redirects(client, url, auth_header, max_redirects=5):
    for _ in range(max_redirects):
        response = client.get(url, headers={"Authorization": auth_header})
        if 300 <= response.status < 400:
            url = response.headers.get("Location")
            if not url:
                return response
        else:
            return response
    return response
