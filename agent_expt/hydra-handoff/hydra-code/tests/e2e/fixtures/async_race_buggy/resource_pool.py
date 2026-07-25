"""Async resource pool with cleanup.

BUGGY VERSION: cleanup uses fire-and-forget asyncio.create_task
instead of awaiting completion. Cleanup returns before resources
are actually closed, causing race conditions.
"""

import asyncio


class Resource:
    """A simple resource that needs cleanup."""

    _instances = []

    def __init__(self, name):
        self.name = name
        self.closed = False
        Resource._instances.append(self)

    async def close(self):
        """Close the resource asynchronously."""
        await asyncio.sleep(0.01)
        self.closed = True

    @classmethod
    def pending(cls):
        """Return resources that are not yet closed."""
        return [r for r in cls._instances if not r.closed]

    @classmethod
    def reset(cls):
        """Reset all instances (for testing)."""
        cls._instances.clear()


class ResourcePool:
    """Pool that manages async resources."""

    def __init__(self):
        self._resources = []

    async def acquire(self, name):
        """Acquire a new resource."""
        res = Resource(name)
        self._resources.append(res)
        return res

    def get_resources(self):
        """Return all acquired resources."""
        return list(self._resources)

    async def cleanup(self):
        """Close all resources.

        BUG: Fire-and-forget via create_task. The tasks are not awaited,
        so cleanup returns before resources are actually closed.
        FIX: await asyncio.gather(*[r.close() for r in self._resources])
        """
        for res in self._resources:
            asyncio.create_task(res.close())
        self._resources.clear()

    async def cleanup_correct(self):
        """Correct version for reference."""
        tasks = [res.close() for res in self._resources]
        await asyncio.gather(*tasks)
        self._resources.clear()
