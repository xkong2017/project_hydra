"""Tests for URL utilities — SWE-bench task psf__requests-6028."""

import pytest
from url_utils import prepend_scheme_if_needed


@pytest.mark.parametrize(
    "value, expected",
    [
        ("example.com/path", "http://example.com/path"),
        ("//example.com/path", "http://example.com/path"),
        ("example.com:80", "http://example.com:80"),
        # These FAIL on buggy code: auth is dropped
        (
            "http://user:pass@example.com/path?query",
            "http://user:pass@example.com/path?query",
        ),
        (
            "http://user@example.com/path?query",
            "http://user@example.com/path?query",
        ),
    ],
)
def test_prepend_scheme_if_needed(value, expected):
    assert prepend_scheme_if_needed(value, "http") == expected
