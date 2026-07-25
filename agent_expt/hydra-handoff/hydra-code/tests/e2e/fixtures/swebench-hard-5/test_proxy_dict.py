"""Tests for read-only dict wrapper."""
import pytest
from proxy_dict import ReadOnlyDict


@pytest.fixture
def data():
    return {"a": 1, "b": 2, "c": 3}


@pytest.fixture
def proxy(data):
    return ReadOnlyDict(data)


def test_getitem(proxy):
    """__getitem__ should return values from the wrapped dict."""
    assert proxy["a"] == 1
    assert proxy["c"] == 3


def test_contains(proxy):
    """__contains__ should work on wrapped dict keys."""
    assert "a" in proxy
    assert "z" not in proxy


def test_keys(proxy):
    """keys() should return wrapped dict keys."""
    assert set(proxy.keys()) == {"a", "b", "c"}


def test_len(proxy):
    """__len__ should reflect wrapped dict size."""
    assert len(proxy) == 3


def test_get_method(proxy):
    """get() should return values from the wrapped dict."""
    assert proxy.get("a") == 1
    assert proxy.get("z", "default") == "default"


def test_values_method(proxy):
    """values() should return wrapped dict values."""
    vals = list(proxy.values())
    assert sorted(vals) == [1, 2, 3]


def test_items_method(proxy):
    """items() should return wrapped dict items."""
    items = dict(proxy.items())
    assert items == {"a": 1, "b": 2, "c": 3}


def test_readonly_enforced(proxy):
    """Wrapper should not allow mutation."""
    with pytest.raises(TypeError):
        proxy["a"] = 99


def test_get_returns_default_for_missing(proxy):
    """get() with missing key should return default."""
    assert proxy.get("nonexistent", 42) == 42


def test_all_methods_consistent(proxy):
    """All read methods should see the same data."""
    assert len(proxy) == len(list(proxy.keys()))
    assert len(proxy) == len(list(proxy.values()))
    assert len(proxy) == len(list(proxy.items()))
