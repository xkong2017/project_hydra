"""Tests for config merge utility.

4 of 5 tests fail. A naive fix (adding deep-merge for dicts) passes tests 1-3
but still fails tests 4 and 5. The correct fix must handle all three bugs.
"""

from config import merge_config


def test_merge_simple():
    """Simple key-value merge."""
    result = merge_config({"a": 1}, {"b": 2})
    assert result == {"a": 1, "b": 2}
    assert result is not {"a": 1}  # must be a new dict


def test_merge_overwrite():
    """User values override defaults."""
    result = merge_config({"a": 1, "b": 2}, {"a": 99})
    assert result == {"a": 99, "b": 2}


def test_merge_nested():
    """Nested dicts should be deep-merged, not overwritten."""
    result = merge_config(
        {"db": {"host": "localhost", "port": 5432}},
        {"db": {"pool": 10}},
    )
    assert result == {"db": {"host": "localhost", "port": 5432, "pool": 10}}


def test_defaults_unchanged():
    """Defaults dict must NOT be mutated by merge."""
    original = {"nested": {"x": 1}}
    defaults = {"nested": {"x": 1}}
    merge_config(defaults, {"nested": {"y": 2}})
    assert defaults == original, f"Defaults mutated: {defaults}"


def test_merge_lists():
    """List values should be concatenated, not overwritten."""
    result = merge_config(
        {"tags": ["a", "b"]},
        {"tags": ["c"]},
    )
    assert result == {"tags": ["a", "b", "c"]}
    assert len(result["tags"]) == 3
