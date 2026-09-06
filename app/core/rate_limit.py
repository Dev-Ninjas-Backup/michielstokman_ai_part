"""In-process sliding-window rate limiter for public AI endpoints."""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

_hits: dict[str, deque[float]] = defaultdict(deque)


def enforce_rate_limit(key: str, *, max_requests: int, window_seconds: int) -> None:
    now = time.monotonic()
    bucket = _hits[key]
    cutoff = now - window_seconds
    while bucket and bucket[0] < cutoff:
        bucket.popleft()
    if len(bucket) >= max_requests:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please wait before trying again.",
        )
    bucket.append(now)


def rate_limit_public_ai(request: Request) -> None:
    host = request.client.host if request.client else "unknown"
    enforce_rate_limit(f"public-ai:{host}", max_requests=20, window_seconds=3600)
