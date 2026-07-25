# N12: Mutable Default Argument

**Bug**: Function uses `[]` as default argument, accumulating state across calls.

**Fix**: Use `None` and create a new list each call.
