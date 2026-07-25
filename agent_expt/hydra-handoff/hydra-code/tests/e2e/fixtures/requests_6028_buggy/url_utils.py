"""URL utilities — mirrors the bug from psf/requests#6028.

BUGGY VERSION: auth info (user:pass@) is dropped when reconstructing URL.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse, urlunparse


def parse_url(url: str) -> dict:
    """Parse a URL into components (mimics urllib3's parse_url behavior).

    Returns a dict with scheme, auth, host, port, path, query, fragment, netloc.
    Note: auth is returned SEPARATELY from netloc (not included in netloc).
    """
    scheme = ""
    netloc = ""
    path = ""
    query = ""
    fragment = ""
    username = ""
    password = ""

    if "://" in url:
        parsed = urlparse(url)
        scheme = parsed.scheme
        netloc = parsed.netloc
        path = parsed.path
        query = parsed.query
        fragment = parsed.fragment
        username = parsed.username or ""
        password = parsed.password or ""
    elif url.startswith("//"):
        parsed = urlparse("http:" + url)
        netloc = parsed.netloc
        path = parsed.path
        query = parsed.query
        fragment = parsed.fragment
        username = parsed.username or ""
        password = parsed.password or ""
    else:
        parsed = urlparse("http://" + url)
        netloc = parsed.netloc
        path = parsed.path
        query = parsed.query
        fragment = parsed.fragment
        username = parsed.username or ""
        password = parsed.password or ""

    host = ""
    port = None
    if netloc:
        host_part = netloc.split("@")[-1]
        if ":" in host_part:
            parts = host_part.rsplit(":", 1)
            host = parts[0]
            try:
                port = int(parts[1])
            except ValueError:
                host = host_part
        else:
            host = host_part

    auth = None
    if username:
        if password:
            auth = f"{username}:{password}"
        else:
            auth = username

    return {
        "scheme": scheme,
        "auth": auth,
        "host": host,
        "port": port,
        "path": path,
        "query": query,
        "fragment": fragment,
        "netloc": netloc.split("@")[-1] if "@" in netloc else netloc,
    }


def prepend_scheme_if_needed(url: str, new_scheme: str) -> str:
    """Given a URL that may or may not have a scheme, prepend the given scheme.

    BUG: auth info (user:pass@) is parsed correctly but NOT re-included in the
    reconstructed netloc. The fix is to add auth back to netloc when present.

    :param url: URL that may lack a scheme
    :param new_scheme: Scheme to prepend if missing
    :rtype: str
    """
    parsed = parse_url(url)
    scheme = parsed["scheme"]
    path = parsed.get("path", "")
    query = parsed.get("query")
    fragment = parsed.get("fragment")

    netloc = parsed["netloc"]
    if not netloc:
        netloc, path = path, netloc

    if not scheme:
        scheme = new_scheme
    if not path:
        path = ""

    # BUG: auth is parsed and available via parsed["auth"] but never
    # re-attached to netloc before urlunparse.
    return urlunparse((scheme, netloc, path, "", query or "", fragment or ""))
