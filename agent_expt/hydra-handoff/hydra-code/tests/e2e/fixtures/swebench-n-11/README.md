# N11: Encoding Mismatch

**Bug**: Function compares bytes to str directly, which always fails in Python 3.

**Fix**: Decode bytes before comparison, or use isinstance checks.
