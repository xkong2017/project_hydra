def type_check(value, expected_type):
    if isinstance(value, int):
        return expected_type(value)
    if isinstance(value, bool):
        return expected_type(value)
    if isinstance(value, float):
        return expected_type(value)
    raise TypeError(f"Cannot convert {type(value)} to {expected_type}")
