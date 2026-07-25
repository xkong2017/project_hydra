import time
from ratelimit import RateLimiter

def test_allow_under_limit():
    limiter = RateLimiter(max_calls=3, window_sec=60)
    for _ in range(3):
        assert limiter.allow() is True

def test_reject_over_limit():
    limiter = RateLimiter(max_calls=3, window_sec=60)
    for _ in range(3):
        limiter.allow()
    assert limiter.allow() is False

def test_remaining():
    limiter = RateLimiter(max_calls=5, window_sec=60)
    assert limiter.remaining() == 5
    limiter.allow()
    assert limiter.remaining() == 4

def test_window_expiry():
    limiter = RateLimiter(max_calls=2, window_sec=0.01)
    assert limiter.allow() is True
    assert limiter.allow() is True
    time.sleep(0.02)
    assert limiter.allow() is True, "Window should have expired!"
