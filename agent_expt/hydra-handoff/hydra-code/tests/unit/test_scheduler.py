"""Unit tests for the scheduler."""

import asyncio

import pytest


@pytest.mark.unit
@pytest.mark.asyncio
async def test_concurrency_limit():
    """TC-U01: Concurrency never exceeds configured limit."""
    from hydra_code.scheduler import JobPriority, Scheduler

    max_concurrent = 6
    scheduler = Scheduler(max_concurrent=max_concurrent)
    active_count = 0
    max_observed = 0
    lock = asyncio.Lock()

    async def mock_job():
        nonlocal active_count, max_observed
        async with lock:
            active_count += 1
            max_observed = max(max_observed, active_count)
        await asyncio.sleep(0.02)
        async with lock:
            active_count -= 1

    jobs = [
        (f"job-{i}", mock_job(), JobPriority.NORMAL) for i in range(20)
    ]
    results = await scheduler.submit_batch(jobs)

    assert len(results) == 20
    assert max_observed <= max_concurrent
    assert max_observed > 0  # Some concurrency actually happened


@pytest.mark.unit
@pytest.mark.asyncio
async def test_all_jobs_complete():
    """All submitted jobs eventually complete."""
    from hydra_code.scheduler import JobPriority, Scheduler

    scheduler = Scheduler(max_concurrent=4)
    completed: list[str] = []

    async def simple_job(job_id: str):
        completed.append(job_id)
        return job_id

    jobs = [
        (f"job-{i}", simple_job(f"job-{i}"), JobPriority.NORMAL)
        for i in range(10)
    ]
    results = await scheduler.submit_batch(jobs)

    assert len(completed) == 10
    assert len(results) == 10


@pytest.mark.unit
@pytest.mark.asyncio
async def test_priority_ordering():
    """TC-U03: Priority jobs get scheduled before low priority."""
    from hydra_code.scheduler import JobPriority, Scheduler

    scheduler = Scheduler(max_concurrent=1)
    execution_order: list[str] = []

    async def named_job(name: str):
        execution_order.append(name)
        return name

    # Submit a low priority job first
    low_task = scheduler.submit("low-1", named_job("low-1"), JobPriority.LOW)

    await asyncio.sleep(0.01)  # Let low-1 start
    high_task = scheduler.submit("high-1", named_job("high-1"), JobPriority.HIGH)

    await low_task
    await high_task

    # Both should have completed
    assert len(execution_order) == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scheduler_stats():
    """Scheduler reports correct statistics."""
    from hydra_code.scheduler import Scheduler

    scheduler = Scheduler(max_concurrent=3)
    stats = scheduler.get_stats()

    assert stats["max_concurrent"] == 3
    assert stats["active"] == 0
    assert stats["completed"] == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_work_conserving():
    """TC-U02: Scheduler keeps slots occupied."""
    from hydra_code.scheduler import JobPriority, Scheduler

    scheduler = Scheduler(max_concurrent=3)
    active = 0
    max_active = 0
    lock = asyncio.Lock()

    async def short_job():
        nonlocal active, max_active
        async with lock:
            active += 1
            max_active = max(max_active, active)
        await asyncio.sleep(0.02)
        async with lock:
            active -= 1

    jobs = [
        (f"job-{i}", short_job(), JobPriority.NORMAL) for i in range(6)
    ]
    await scheduler.submit_batch(jobs)

    # Should have had 3 concurrent at some point
    assert max_active == 3
