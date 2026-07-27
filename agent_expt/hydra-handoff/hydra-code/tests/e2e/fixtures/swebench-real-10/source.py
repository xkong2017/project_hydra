def build_request(method, url, body=None):
    headers = {}
    headers["Content-Length"] = str(len(body or ""))
    return {"method": method, "url": url, "headers": headers, "body": body}
