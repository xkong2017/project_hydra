"""Tests for connection pool isolation."""
from connection_pool import ConnectionPool


def test_pool_acquire_release():
    """Basic acquire and release should work."""
    pool = ConnectionPool("db-main", max_size=3)
    c = pool.acquire("conn-1")
    assert c == "conn-1"
    assert pool.active_count == 1
    assert pool.release("conn-1") is True
    assert pool.active_count == 0


def test_pool_max_size():
    """Pool should not exceed max_size connections."""
    pool = ConnectionPool("db-limited", max_size=2)
    assert pool.acquire("c1") == "c1"
    assert pool.acquire("c2") == "c2"
    assert pool.acquire("c3") is None  # pool is full
    assert pool.active_count == 2


def test_pools_are_independent():
    """Different pools should NOT share connections."""
    pool_a = ConnectionPool("db-users", max_size=3)
    pool_b = ConnectionPool("db-orders", max_size=3)

    pool_a.acquire("user-conn-1")
    pool_a.acquire("user-conn-2")

    assert pool_a.active_count == 2, "Pool A should have 2 active connections"
    assert pool_b.active_count == 0, (
        f"Pool B should have 0 connections, but has {pool_b.active_count}. "
        "Pools are sharing state!"
    )


def test_pool_isolation_fill_one_only():
    """Filling pool A should not affect pool B."""
    pool_a = ConnectionPool("a", max_size=2)
    pool_b = ConnectionPool("b", max_size=2)

    pool_a.acquire("a1")
    pool_a.acquire("a2")

    # Pool A should be full
    assert pool_a.acquire("a3") is None

    # Pool B should still be able to acquire
    assert pool_b.acquire("b1") == "b1", "Pool B should allow connections even when A is full!"
    assert pool_b.active_count == 1


def test_release_only_affects_own_pool():
    """Releasing in one pool should not affect the other."""
    pool_a = ConnectionPool("a", max_size=5)
    pool_b = ConnectionPool("b", max_size=5)

    pool_a.acquire("shared-id")
    pool_b.acquire("shared-id")

    pool_a.release("shared-id")

    assert pool_a.active_count == 0
    assert pool_b.active_count == 1, (
        "Releasing in pool A should NOT release in pool B!"
    )
