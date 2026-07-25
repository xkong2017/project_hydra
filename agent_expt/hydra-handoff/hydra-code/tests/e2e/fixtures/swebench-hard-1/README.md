# H1: Variable Scope in Loop Closures

**Bug**: A list of lambda functions is created in a loop, but all lambdas capture the loop variable by reference, not by value. Calling any lambda returns the same final value of the loop variable.

**Source**: `calculator.py` — `make_operations()` builds lambdas in a loop
**Test**: `test_calculator.py` — verifies each operation uses the correct captured value

**Expected fix**: Capture the loop variable by value (default argument or partial)
