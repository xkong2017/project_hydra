# N18: Incomplete Input Validation

**Bug**: Email validator checks for `@` but doesn't validate domain format.

**Fix**: Add domain format validation (at least one dot, no spaces).
