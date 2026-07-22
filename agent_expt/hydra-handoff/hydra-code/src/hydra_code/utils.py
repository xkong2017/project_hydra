"""Utility functions for HydraCode-6."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Common secret patterns for redaction
SECRET_PATTERNS = [
    re.compile(r"(sk-[A-Za-z0-9]{20,})"),
    re.compile(r"(ghp_[A-Za-z0-9]{36})"),
    re.compile(r"(gho_[A-Za-z0-9]{36})"),
    re.compile(r"(ghr_[A-Za-z0-9]{36})"),
    re.compile(r"(ghs_[A-Za-z0-9]{36})"),
    re.compile(r"(ghp_[A-Za-z0-9]{36})"),
    re.compile(r"(AWS_SECRET_ACCESS_KEY\s*=\s*)\S+"),
    re.compile(r"(API_KEY\s*[\:=]\s*)\S+"),
    re.compile(r"(PASSWORD\s*[\:=]\s*)\S+"),
    re.compile(r"(TOKEN\s*[\:=]\s*)['\"]?\S+['\"]?"),
]

REDACTED = "[REDACTED]"


def generate_run_id() -> str:
    """Generate a unique run identifier."""
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    short = hashlib.sha256((ts + os.urandom(8).hex()).encode()).hexdigest()[:8]
    return f"{ts}-{short}"


def timestamp_now() -> str:
    """Current UTC timestamp in ISO format."""
    return datetime.now(UTC).isoformat()


def atomic_write_json(path: Path, data: Any) -> None:
    """Write JSON atomically to avoid corrupt files on interruption."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, default=str)
            f.flush()
            os.fsync(f.fileno())
        Path(tmp_path).rename(path)
    except Exception:
        Path(tmp_path).unlink(missing_ok=True)
        raise


def atomic_write_text(path: Path, content: str) -> None:
    """Write text atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        Path(tmp_path).rename(path)
    except Exception:
        Path(tmp_path).unlink(missing_ok=True)
        raise


def redact_secrets(text: str) -> str:
    """Redact likely secrets from text output."""
    for pattern in SECRET_PATTERNS:
        text = pattern.sub(REDACTED, text)
    return text


def sha256_hash(content: bytes) -> str:
    """Compute SHA256 hash of content."""
    return hashlib.sha256(content).hexdigest()


def jaccard_similarity(a: set[str], b: set[str]) -> float:
    """Compute Jaccard similarity between two sets."""
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def parse_duration(seconds: float) -> str:
    """Format duration in human-readable form."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes}m {secs:.0f}s"
