"""Unit tests for secret redaction."""

import pytest


@pytest.mark.unit
def test_redact_api_key():
    """TC-U13: API keys are redacted."""
    from hydra_code.utils import redact_secrets

    text = "key=sk-testsecret12345678901234567890ab"
    result = redact_secrets(text)
    assert "testsecret" not in result
    assert "[REDACTED]" in result


@pytest.mark.unit
def test_redact_github_token():
    """GitHub tokens are redacted."""
    from hydra_code.utils import redact_secrets

    text = "token=ghp_abcdefghijklmnopqrstuvwxyz0123456789"
    result = redact_secrets(text)
    assert "ghp_" not in result


@pytest.mark.unit
def test_redact_aws_secret():
    """AWS secrets are redacted."""
    from hydra_code.utils import redact_secrets

    text = "AWS_SECRET_ACCESS_KEY=fake-secret-value"
    result = redact_secrets(text)
    assert "fake-secret-value" not in result


@pytest.mark.unit
def test_normal_text_preserved():
    """Ordinary code strings are not corrupted."""
    from hydra_code.utils import redact_secrets

    text = "def foo(): return 42"
    result = redact_secrets(text)
    assert result == text


@pytest.mark.unit
def test_generate_run_id():
    """Run ID format is correct."""
    from hydra_code.utils import generate_run_id

    run_id = generate_run_id()
    parts = run_id.split("-")
    assert len(parts) == 2
    assert len(parts[1]) == 8


@pytest.mark.unit
def test_atomic_write_json():
    """Atomic JSON write creates valid file."""
    import json
    import tempfile
    from pathlib import Path

    from hydra_code.utils import atomic_write_json

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.json"
        atomic_write_json(path, {"key": "value"})
        data = json.loads(path.read_text())
        assert data["key"] == "value"


@pytest.mark.unit
def test_jaccard_similarity():
    """Jaccard similarity calculations."""
    from hydra_code.utils import jaccard_similarity

    assert jaccard_similarity({"a", "b"}, {"a", "b"}) == 1.0
    assert jaccard_similarity({"a"}, {"b"}) == 0.0
    assert 0.0 < jaccard_similarity({"a", "b"}, {"b", "c"}) < 1.0
    assert jaccard_similarity(set(), set()) == 1.0
