"""Simple process-local rate limiter for sensitive endpoints."""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Request

from app.core.exceptions import TooManyRequestsError


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def hit(self, key: str, *, limit: int, window_seconds: int) -> None:
        now = time.monotonic()
        bucket = self._hits[key]
        cutoff = now - window_seconds
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= limit:
            raise TooManyRequestsError(
                f"Too many requests. Try again in {window_seconds} seconds."
            )
        bucket.append(now)


limiter = RateLimiter()


def client_key(request: Request, suffix: str) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    ip = (forwarded.split(",")[0].strip() if forwarded else None) or (
        request.client.host if request.client else "unknown"
    )
    return f"{ip}:{suffix}"
