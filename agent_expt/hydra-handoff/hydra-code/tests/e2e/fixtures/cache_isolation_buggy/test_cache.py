"""Tests for cache tenant isolation."""

from cache import TenantCache


def test_tenant_isolation():
    """Different tenants should not see each other's data."""
    cache = TenantCache()

    cache.set("tenant-a", "user:1", {"name": "Alice"})
    cache.set("tenant-b", "user:1", {"name": "Bob"})

    assert cache.get("tenant-a", "user:1") == {"name": "Alice"}
    assert cache.get("tenant-b", "user:1") == {"name": "Bob"}


def test_same_tenant_same_key():
    """Same tenant with same key should return same value."""
    cache = TenantCache()

    cache.set("tenant-a", "user:1", {"name": "Alice"})
    assert cache.get("tenant-a", "user:1") == {"name": "Alice"}


def test_delete_one_tenant():
    """Deleting one tenant's data should not affect others."""
    cache = TenantCache()

    cache.set("tenant-a", "user:1", {"name": "Alice"})
    cache.set("tenant-b", "user:1", {"name": "Bob"})

    cache.delete("tenant-a", "user:1")
    assert cache.get("tenant-a", "user:1") is None
    assert cache.get("tenant-b", "user:1") == {"name": "Bob"}


def test_overwrite_same_tenant():
    """Overwriting a key should update the value."""
    cache = TenantCache()

    cache.set("tenant-a", "user:1", {"name": "Alice"})
    cache.set("tenant-a", "user:1", {"name": "Alice Updated"})

    assert cache.get("tenant-a", "user:1") == {"name": "Alice Updated"}


def test_cache_miss():
    """Missing key should return None."""
    cache = TenantCache()
    assert cache.get("tenant-a", "nonexistent") is None


def test_clear_removes_all():
    """Clear should remove all entries."""
    cache = TenantCache()

    cache.set("tenant-a", "user:1", {"name": "Alice"})
    cache.set("tenant-b", "user:1", {"name": "Bob"})
    cache.clear()

    assert cache.get("tenant-a", "user:1") is None
    assert cache.get("tenant-b", "user:1") is None


def test_size_counts_entries():
    """Size should reflect number of cached entries."""
    cache = TenantCache()

    cache.set("tenant-a", "user:1", {"name": "Alice"})
    cache.set("tenant-b", "user:1", {"name": "Bob"})

    # With proper isolation, these should be 2 separate entries
    # Without isolation, they collide and size is 1
    assert cache.size() == 2
