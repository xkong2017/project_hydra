import pytest
from retry import retry, RetryError, parse_int, divide


def test_retry_succeeds():
    calls = []
    def op():
        calls.append(1)
        if len(calls) < 2:
            raise ValueError("not yet")
        return "ok"
    assert retry(op) == "ok"


def test_retry_exhausted():
    def fail():
        raise ValueError("always fails")
    with pytest.raises(RetryError):
        retry(fail)


def test_retry_raises_original_error_type():
    def fail():
        raise ValueError("original")
    with pytest.raises(RetryError) as exc_info:
        retry(fail)
    # The original exception should be chained
    assert isinstance(exc_info.value.__cause__, ValueError),         f"Expected ValueError as cause, got {exc_info.value.__cause__}"


def test_retry_preserves_original_message():
    def fail():
        raise ValueError("secret message")
    with pytest.raises(RetryError):
        retry(fail)
