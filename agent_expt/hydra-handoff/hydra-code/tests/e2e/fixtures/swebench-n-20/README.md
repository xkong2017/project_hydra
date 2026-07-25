# N20: Incomplete Copy (Shallow Copy Bug)

**Bug**: Nested dict is copied with a shallow copy, so modifying nested values affects the original.

**Fix**: Use `copy.deepcopy()`.
