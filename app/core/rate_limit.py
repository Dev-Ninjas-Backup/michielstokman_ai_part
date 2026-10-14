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


def get_client_ip(request: Request) -> str:
    """Extract real client IP considering reverse proxy headers."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    cf_ip = request.headers.get("cf-connecting-ip")
    if cf_ip:
        return cf_ip.strip()
    return request.client.host if request.client else "unknown"


def rate_limit_ai_search(request: Request) -> None:
    """Generous rate limit for semantic search: 60 queries per minute per IP."""
    ip = get_client_ip(request)
    enforce_rate_limit(f"ai-search:{ip}", max_requests=60, window_seconds=60)


def rate_limit_public_ai(request: Request) -> None:
    """Public AI rate limiter: 60 requests per 10 minutes per IP."""
    ip = get_client_ip(request)
    enforce_rate_limit(f"public-ai:{ip}", max_requests=60, window_seconds=600)
