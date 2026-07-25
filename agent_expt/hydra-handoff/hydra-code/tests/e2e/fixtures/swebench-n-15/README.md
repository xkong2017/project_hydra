# N15: Config Override Bug

**Bug**: Config defaults are not properly overridden by user-provided values.

**Fix**: Use dict.update or **kwargs merging.
