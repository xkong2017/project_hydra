"""Tests for content hasher."""
from hasher import compute_hash, clear_cache, cache_size


def test_same_data_returns_same_hash():
    """Same data should always return the same hash."""
    clear_cache()
    h1 = compute_hash(b"hello world")
    h2 = compute_hash(b"hello world")
    assert h1 == h2


def test_different_data_returns_different_hash():
    """Different data should return different hashes."""
    clear_cache()
    h1 = compute_hash(b"hello world")
    h2 = compute_hash(b"HELLO WORLD")
    assert h1 != h2, "Different data should have different hashes!"


def test_cache_returns_fresh_hash_for_new_data():
    """Cache should not return stale results when data changes."""
    clear_cache()
    compute_hash(b"aaaa")

    compute_hash(b"bbbb")
    h_bbbb = compute_hash(b"bbbb")

    result = compute_hash(b"aaaa")
    assert result != h_bbbb, (
        "Cache returned hash of 'bbbb' for 'aaaa' because they have the same size!"
    )


def test_cache_speed_up():
    """Repeated calls should use cache."""
    clear_cache()
    data = b"x" * 1000
    compute_hash(data)
    size_before = cache_size()
    compute_hash(data)
    assert cache_size() == size_before


def test_three_different_same_size():
    """Three different inputs of same size should have different hashes."""
    clear_cache()
    h1 = compute_hash(b"abc")
    h2 = compute_hash(b"xyz")
    h3 = compute_hash(b"123")
    assert len({h1, h2, h3}) == 3, "Same-size different content should produce different hashes!"
