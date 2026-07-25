# H5: Incomplete Proxy Delegation

**Bug**: A read-only dict wrapper delegates `__getitem__`, `__contains__`, and `keys()` to the inner dict, but does NOT delegate `get()`, `values()`, or `items()`. These fall through to the default `dict` behavior which accesses a DIFFERENT dict (the wrapper's own empty `__dict__` instead of the wrapped data).

**Source**: `proxy_dict.py` — `ReadOnlyDict` missing delegation methods
**Test**: `test_proxy_dict.py` — verifies all read operations work

**Expected fix**: Delegate `get()`, `values()`, `items()` to the inner dict.
