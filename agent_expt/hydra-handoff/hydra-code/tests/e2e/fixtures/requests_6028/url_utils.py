"""URL utilities — mirrors the bug from psf/requests#6028.

The real bug: parse_url() from urllib3 returns netloc without auth components
(user:pass@), so the reconstructed URL drops credentials.

This fixture replicates the same bug pattern in a self-contained module.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse, urlunparse


def parse_url(url: str) -> dict:
    """Parse a URL into components (mimics urllib3's parse_url behavior).

    Returns a dict with scheme, auth, host, port, path, query, fragment, netloc.
    Note: auth is returned SEPARATELY from netloc (not included in netloc).
    """
    # Handle schemeless URLs like "example.com/path" or "example.com:80"
    # urlparse treats these incorrectly, so we need special handling
    scheme = ""
    netloc = ""
    path = ""
    query = ""
    fragment = ""
    username = ""
    password = ""

    if "://" in url:
        # Has scheme — urlparse handles it correctly
        parsed = urlparse(url)
        scheme = parsed.scheme
        netloc = parsed.netloc
        path = parsed.path
        query = parsed.query
        fragment = parsed.fragment
        username = parsed.username or ""
        password = parsed.password or ""
    elif url.startswith("//"):
        # Protocol-relative URL
        parsed = urlparse("http:" + url)
        netloc = parsed.netloc
        path = parsed.path
        query = parsed.query
        fragment = parsed.fragment
        username = parsed.username or ""
        password = parsed.password or ""
    else:
        # No scheme, no // — urlparse treats it as a path
        # Parse as if it has http:// scheme
        parsed = urlparse("http://" + url)
        netloc = parsed.netloc
        path = parsed.path
        query = parsed.query
        fragment = parsed.fragment
        username = parsed.username or ""
        password = parsed.password or ""

    # Extract host and port from netloc
    host = ""
    port = None
    if netloc:
        # Strip auth from netloc for host extraction
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

    # Build auth string (like urllib3)
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
        # urllib3's parse_url returns netloc WITHOUT auth info
        "netloc": netloc.split("@")[-1] if "@" in netloc else netloc,
    }


def prepend_scheme_if_needed(url: str, new_scheme: str) -> str:
    """Given a URL that may or may not have a scheme, prepend the given scheme.

    :param url: URL that may lack a scheme
    :param new_scheme: Scheme to prepend if missing
    :rtype: str
    """
    parsed = parse_url(url)
    scheme = parsed["scheme"]
    auth = parsed.get("auth")
    path = parsed.get("path", "")
    query = parsed.get("query")
    fragment = parsed.get("fragment")

    # A defect in urlparse determines that there isn't a netloc present in some
    # urls. We previously assumed parsing was overly cautious, and swapped the
    # netloc and path. Due to a lack of tests on the original defect, this is
    # maintained with parse_url for backwards compatibility.
    netloc = parsed["netloc"]
    if not netloc:
        netloc, path = path, netloc

    if not scheme:
        scheme = new_scheme
    if not path:
        path = ""

    if auth:
        netloc = f"{auth}@{netloc}"

    return urlunparse((scheme, netloc, path, "", query or "", fragment or ""))