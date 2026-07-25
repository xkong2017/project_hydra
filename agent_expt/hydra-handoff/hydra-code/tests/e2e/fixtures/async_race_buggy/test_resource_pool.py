"""Tests for async resource pool cleanup."""

import pytest
from resource_pool import Resource, ResourcePool


@pytest.fixture(autouse=True)
def reset_resources():
    """Reset resource instances before each test."""
    Resource.reset()
    yield
    Resource.reset()


@pytest.mark.asyncio
async def test_cleanup_closes_all_resources():
    """Cleanup should close all resources."""
    pool = ResourcePool()

    await pool.acquire("res-1")
    await pool.acquire("res-2")
    await pool.acquire("res-3")

    await pool.cleanup()

    assert len(Resource.pending()) == 0


@pytest.mark.asyncio
async def test_cleanup_marks_resources_closed():
    """Each resource should have closed=True after cleanup."""
    pool = ResourcePool()

    r1 = await pool.acquire("res-1")
    r2 = await pool.acquire("res-2")

    await pool.cleanup()

    assert r1.closed is True
    assert r2.closed is True


@pytest.mark.asyncio
async def test_cleanup_empty_pool():
    """Cleanup of empty pool should not error."""
    pool = ResourcePool()
    await pool.cleanup()  # should not raise


@pytest.mark.asyncio
async def test_resources_available_before_cleanup():
    """Resources should be accessible before cleanup."""
    pool = ResourcePool()

    await pool.acquire("res-1")
    await pool.acquire("res-2")

    resources = pool.get_resources()
    assert len(resources) == 2


@pytest.mark.asyncio
async def test_multiple_acquires():
    """Multiple acquires should create separate resources."""
    pool = ResourcePool()

    r1 = await pool.acquire("a")
    r2 = await pool.acquire("b")

    assert r1 is not r2
    assert r1.name == "a"
    assert r2.name == "b"
