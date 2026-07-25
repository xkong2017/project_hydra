# H4: Silent Exception Swallowing

**Bug**: A data processor catches all exceptions during processing and returns a default value, losing error context. Critical errors like `ValueError` from invalid data should propagate.

**Source**: `processor.py` — `process_record()` catches `Exception` too broadly
**Test**: `test_processor.py` — verifies that invalid data raises instead of producing wrong results

**Expected fix**: Use more specific exception handling or re-raise after logging.
