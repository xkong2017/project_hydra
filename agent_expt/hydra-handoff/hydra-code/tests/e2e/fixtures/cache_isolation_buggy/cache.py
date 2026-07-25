"""Simple in-memory cache with tenant isolation.

BUGGY VERSION: Cache key does NOT include tenant_id, causing
data leakage between tenants. Different tenants with the same
resource_id will overwrite each other's data.
"""


class TenantCache:
    """Cache that should isolate data by tenant."""

    def __init__(self):
        self._store = {}

    def get(self, tenant_id, resource_id):
        """Get a cached value for a tenant and resource."""
        key = self._make_key(tenant_id, resource_id)
        return self._store.get(key)

    def set(self, tenant_id, resource_id, value):
        """Set a cached value for a tenant and resource."""
        key = self._make_key(tenant_id, resource_id)
        self._store[key] = value

    def delete(self, tenant_id, resource_id):
        """Delete a cached value."""
        key = self._make_key(tenant_id, resource_id)
        self._store.pop(key, None)

    def _make_key(self, tenant_id, resource_id):
        """Generate cache key.

        BUG: Ignores tenant_id. Key is only based on resource_id,
        so tenant-a and tenant-b with the same resource_id collide.
        FIX: return f"{tenant_id}:{resource_id}"
        """
        return resource_id

    def clear(self):
        """Clear all cached data."""
        self._store.clear()

    def size(self):
        """Return number of cached entries."""
        return len(self._store)
