# H3: Shared Mutable State Across Instances

**Bug**: A connection pool uses a class-level variable for tracking active connections, causing all instances to share the same pool. Different pools interfere with each other.

**Source**: `connection_pool.py` — `_active_connections` is a class variable
**Test**: `test_connection_pool.py` — verifies pool isolation

**Expected fix**: Move `_active_connections` from class-level to instance-level (self).
