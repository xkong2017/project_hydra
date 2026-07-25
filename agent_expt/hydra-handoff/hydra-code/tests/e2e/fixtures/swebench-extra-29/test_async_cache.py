from async_cache import AsyncCache


def test_get_set():
    c = AsyncCache()
    c.set("key", 42)
    assert c.get("key") == 42


def test_get_or_compute():
    c = AsyncCache()
    called = []
    def compute():
        called.append(1)
        return 99
    result = c.get_or_compute("x", compute)
    assert result == 99
    assert len(called) == 1
    result2 = c.get_or_compute("x", compute)
    assert result2 == 99
    assert len(called) == 1, "compute should not be called again"


def test_invalidate():
    c = AsyncCache()
    c.set("k", 1)
    c.invalidate("k")
    assert c.get("k") is None
