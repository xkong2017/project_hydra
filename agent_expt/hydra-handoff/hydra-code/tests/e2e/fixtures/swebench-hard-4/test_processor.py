"""Tests for data processor error handling."""
import pytest
from processor import process_record, batch_process


def test_valid_record():
    """A valid JSON record should be processed correctly."""
    result = process_record(
        '{"id": 1, "name": "Alice", "amount": 100.0, "timestamp": "2024-01-15T10:30:00"}'
    )
    assert result is not None
    assert result["id"] == 1
    assert result["name"] == "Alice"
    assert result["amount"] == 100.0


def test_missing_id_raises():
    """Missing required field 'id' should raise KeyError, not return None."""
    record = '{"name": "Bob", "amount": 50.0, "timestamp": "2024-01-15T10:30:00"}'
    with pytest.raises((KeyError, ValueError, TypeError)):
        process_record(record)


def test_invalid_amount_raises():
    """Invalid amount (non-numeric) should raise ValueError, not return None."""
    record = '{"id": 3, "name": "Charlie", "amount": "not-a-number", "timestamp": "2024-01-15T10:30:00"}'
    with pytest.raises((ValueError, TypeError)):
        process_record(record)


def test_malformed_json_returns_none():
    """Truly malformed JSON should return None."""
    result = process_record("{this is not json}")
    assert result is None


def test_missing_timestamp_raises():
    """Missing timestamp should raise, not return None."""
    record = '{"id": 4, "name": "Diana", "amount": 75.0}'
    with pytest.raises((KeyError, ValueError)):
        process_record(record)


def test_empty_name():
    """Empty name should be handled correctly."""
    result = process_record(
        '{"id": 5, "name": "   ", "amount": 25.0, "timestamp": "2024-01-15T10:30:00"}'
    )
    # Empty name after strip is allowed - this is a data issue not a processing error
    assert result is not None
    assert result["name"] == ""


def test_batch_processing_preserves_errors():
    """batch_process should raise on invalid data, not silently return None."""
    records = [
        '{"id": 1, "name": "Alice", "amount": 100.0, "timestamp": "2024-01-15T10:30:00"}',
        '{"id": 2, "name": "Bob", "amount": "bad", "timestamp": "2024-01-15T10:30:00"}',
    ]
    with pytest.raises((ValueError, TypeError)):
        batch_process(records)
