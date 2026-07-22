"""Tests for URL utilities — SWE-bench task psf__requests-6028.

These tests verify that prepend_scheme_if_needed preserves auth info
(user:pass@) in URLs, which was the real bug in requests#6028.
"""

import pytest

from url_utils import prepend_scheme_if_needed


@pytest.mark.parametrize(
    "value, expected",
    [
        ("example.com/path", "http://example.com/path"),
        ("//example.com/path", "http://example.com/path"),
        ("example.com:80", "http://example.com:80"),
        # These are the FAIL_TO_PASS cases from the real SWE-bench task
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