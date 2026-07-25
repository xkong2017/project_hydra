# N16: Recursive Depth Limit

**Bug**: Recursive tree traversal has no depth limit, causing stack overflow on deep trees.

**Fix**: Add max_depth parameter with default.
