"""Configuration merge utility.

Handles deep merging of nested dicts, list concatenation, and input immutability.
"""

import copy


def merge_config(defaults, user):
    """Merge user config into defaults (user values take precedence).

    Returns a new dict without mutating the inputs.
    """
    result = copy.deepcopy(defaults)
    for key, value in user.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_config(result[key], value)
        elif key in result and isinstance(result[key], list) and isinstance(value, list):
            result[key] = result[key] + value
        else:
            result[key] = value
    return result