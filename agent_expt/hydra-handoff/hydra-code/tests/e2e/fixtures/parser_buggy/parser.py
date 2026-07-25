"""JSON-like data parser.

BUGGY VERSION: parse_amount returns int for integer values
instead of always returning float.
"""

import json


def parse_amount(value):
    """Parse a monetary amount from a string or number.

    Returns:
        float: The parsed amount.

    BUG: Returns int when value has no decimal point.
    FIX: Replace bare returns with return float(...).
    """
    if isinstance(value, str):
        value = value.strip()

    if isinstance(value, int):
        return value  # BUG: returns int, should be return float(value)

    if isinstance(value, float):
        return value

    # String parsing
    try:
        num = json.loads(value)
        if isinstance(num, int):
            return num  # BUG: returns int, should be return float(num)
        return num
    except (json.JSONDecodeError, TypeError):
        raise ValueError(f"Cannot parse amount: {value!r}")


def parse_record(record_str):
    """Parse a JSON record string into a dict with float amounts."""
    data = json.loads(record_str)
    if "amount" in data:
        data["amount"] = parse_amount(data["amount"])
    return data
