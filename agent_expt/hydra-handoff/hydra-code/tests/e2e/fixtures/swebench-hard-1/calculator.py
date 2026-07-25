"""Calculator with operation factory.

BUGGY: Lambda functions in make_operations all capture the same loop variable.
FIX: Capture loop variable by value using default argument.
"""


def make_operations():
    """Return a list of (name, operation) tuples.

    Each operation should apply the corresponding arithmetic function
    to its argument. Operations: add1, add2, ..., mul1, mul2, ...
    """
    operations = []
    for name in ["add", "sub", "mul", "div"]:
        for i in range(1, 4):
            # BUG: lambda captures name and i by reference, not by value.
            # When the lambda is later called, name and i have their final
            # loop values ("div" and 3), so all lambdas do the same thing.
            operations.append((f"{name}{i}", lambda x: apply_op(name, i, x)))
    return operations


def apply_op(op_name, val, x):
    """Apply the named operation with parameter val to x."""
    if op_name == "add":
        return x + val
    elif op_name == "sub":
        return x - val
    elif op_name == "mul":
        return x * val
    elif op_name == "div":
        return x / val if val != 0 else float("inf")
    raise ValueError(f"Unknown operation: {op_name}")
