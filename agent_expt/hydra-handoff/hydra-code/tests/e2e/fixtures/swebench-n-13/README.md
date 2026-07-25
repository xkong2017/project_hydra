# N13: Incorrect Exception Chaining

**Bug**: A retry wrapper catches all exceptions and raises a new generic error, losing the original traceback.

**Fix**: Use `raise RetryError(msg) from original_exception`.
