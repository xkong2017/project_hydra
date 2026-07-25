"""Data record processor.

BUGGY: process_record catches ALL exceptions and returns None, silently
swallowing errors that should propagate (ValueError, TypeError).
Valid records might fail and produce None without any indication.
FIX: Use specific exception handling; only catch expected errors.
"""

import json
from datetime import datetime


def process_record(record: str) -> dict | None:
    """Process a JSON record and return a normalized dict.

    Returns None if the record cannot be processed.
    """
    try:
        data = json.loads(record)
        result = {
            "id": data["id"],
            "name": data["name"].strip(),
            "amount": float(data["amount"]),
            "timestamp": datetime.fromisoformat(data["timestamp"]).isoformat(),
        }
        return result
    except Exception:
        return None


def batch_process(records: list[str]) -> list[dict | None]:
    """Process multiple records, skipping invalid ones."""
    return [process_record(r) for r in records]
