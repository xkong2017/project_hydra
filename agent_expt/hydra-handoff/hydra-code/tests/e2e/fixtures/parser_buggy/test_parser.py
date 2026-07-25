"""Tests for JSON parser type correctness."""

import pytest
from parser import parse_amount, parse_record


def test_parse_amount_int_becomes_float():
    """Integer amounts should be returned as float."""
    result = parse_amount(100)
    assert isinstance(result, float), f"Expected float, got {type(result)}"
    assert result == 100.0


def test_parse_amount_float_stays_float():
    """Float amounts should remain float."""
    result = parse_amount(99.99)
    assert isinstance(result, float)
    assert result == 99.99


def test_parse_amount_string_int():
    """String integer should be parsed as float."""
    result = parse_amount("42")
    assert isinstance(result, float)
    assert result == 42.0


def test_parse_amount_string_float():
    """String float should be parsed as float."""
    result = parse_amount("3.14")
    assert isinstance(result, float)
    assert abs(result - 3.14) < 0.001


def test_parse_amount_zero():
    """Zero should be returned as float."""
    result = parse_amount(0)
    assert isinstance(result, float)
    assert result == 0.0


def test_parse_amount_negative():
    """Negative amounts should work."""
    result = parse_amount(-50)
    assert isinstance(result, float)
    assert result == -50.0


def test_parse_amount_invalid():
    """Invalid strings should raise ValueError."""
    with pytest.raises(ValueError):
        parse_amount("not-a-number")


def test_parse_record_converts_amount():
    """parse_record should convert amount to float."""
    record = parse_record('{"id": 1, "amount": 200}')
    assert isinstance(record["amount"], float)
    assert record["amount"] == 200.0


def test_parse_record_already_float():
    """parse_record should handle float amounts."""
    record = parse_record('{"id": 2, "amount": 19.99}')
    assert isinstance(record["amount"], float)
