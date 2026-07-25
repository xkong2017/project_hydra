# N19: Incorrect Operator Precedence

**Bug**: Boolean expression `a and b or c` is evaluated as `(a and b) or c` but intended as `a and (b or c)`.

**Fix**: Add explicit parentheses.
