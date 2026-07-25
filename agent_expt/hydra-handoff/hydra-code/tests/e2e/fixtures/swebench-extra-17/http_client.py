class Request:
    def __init__(self, method, url, body=None):
        self.method = method.upper()
        self.url = url
        self.body = body


def build_request(method, url, data=None, params=None):
    if params:
        import urllib.parse
        url = url + "?" + urllib.parse.urlencode(params)
    return Request(method, url, body=data)


def send_request(request):
    return f"{request.method} {request.url}"
