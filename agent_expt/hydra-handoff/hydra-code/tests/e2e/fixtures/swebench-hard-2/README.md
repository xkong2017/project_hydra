# H2: Memoization Cache Staleness

**Bug**: A memoized computation caches results by output size only. When content changes but size stays the same, the stale cached result is returned.

**Source**: `hasher.py` — `compute_hash()` caches by file_size instead of file content
**Test**: `test_hasher.py` — verifies cache invalidation on content change

**Expected fix**: Include content (or content hash) in the cache key, not just size.
