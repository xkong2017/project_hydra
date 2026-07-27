import pytest
from source import type_check

def test_int_to_float():
    assert type_check(42, float) == 42.0

def test_bool_preserved():
    result = type_check(True, int)
    assert result == 1

def test_type_error():
    with pytest.raises(TypeError):
        type_check("hello", float)
