from app.core.rate_limit import RateLimiter
from app.core.sanitize import sanitize_html
from app.core.exceptions import TooManyRequestsError
import pytest


def test_rate_limiter_blocks_after_limit():
    limiter = RateLimiter()
    limiter.hit("ip:login", limit=2, window_seconds=60)
    limiter.hit("ip:login", limit=2, window_seconds=60)
    with pytest.raises(TooManyRequestsError):
        limiter.hit("ip:login", limit=2, window_seconds=60)


def test_sanitize_html_strips_scripts():
    dirty = '<p>Hello</p><script>alert("x")</script><a href="javascript:alert(1)">x</a>'
    clean = sanitize_html(dirty)
    assert clean is not None
    assert "<script>" not in clean
    assert "javascript:" not in clean
    assert "<p>Hello</p>" in clean
