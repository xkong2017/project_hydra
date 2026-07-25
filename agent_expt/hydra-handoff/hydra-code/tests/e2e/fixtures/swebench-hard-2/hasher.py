"""Content hasher with caching.

BUGGY: Cache key is based on file size only, not content.
If two files have the same size, the cache returns the wrong hash.
FIX: Include content in the cache key, or hash more than just size.
"""

import hashlib

_cache = {}


def compute_hash(data: bytes) -> str:
    """Compute SHA-256 hash of data, with caching."""
    size = len(data)
    if size in _cache:
        return _cache[size]

    result = hashlib.sha256(data).hexdigest()
    _cache[size] = result
    return result


def clear_cache():
    """Clear the internal cache."""
    _cache.clear()


def cache_size():
    """Return number of cached entries."""
    return len(_cache)
