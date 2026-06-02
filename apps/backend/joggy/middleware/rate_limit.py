"""Redis-backed rate limit for partner API endpoints.

Counter per (api_key_id, minute_window). Fail-open if Redis is unavailable:
the existing argon2 auth in verify_partner_api_key is the real security boundary;
rate limit is a courtesy guardrail.
"""
from __future__ import annotations

import logging
import time

import redis.asyncio as redis_async
from fastapi import HTTPException, Response, status

from joggy.core.config import get_settings

logger = logging.getLogger(__name__)

_client: redis_async.Redis | None = None


def _get_client() -> redis_async.Redis:
    """Lazy singleton Redis client (re-uses RQ queue's Redis instance)."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = redis_async.from_url(settings.redis_url, decode_responses=True)
    return _client


async def check_rate_limit(
    key_id: str,
    limit_per_minute: int,
    response: Response,
) -> None:
    """Increment counter for current minute window; raise 429 if over limit.

    Fail-open on Redis errors: log WARNING and allow the request through.
    On success (under or at limit), sets X-RateLimit-* headers.
    """
    window = int(time.time() // 60)
    redis_key = f"rl:{key_id}:{window}"
    reset_at = (window + 1) * 60  # epoch seconds when this window expires

    try:
        client = _get_client()
        count = await client.incr(redis_key)
        if count == 1:
            await client.expire(redis_key, 60)
    except Exception as e:
        logger.warning("Rate limit check failed (fail-open): %s", e)
        return  # don't block when Redis is broken

    remaining = max(0, limit_per_minute - count)
    response.headers["X-RateLimit-Limit"] = str(limit_per_minute)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-RateLimit-Reset"] = str(reset_at)

    if count > limit_per_minute:
        retry_after = max(1, reset_at - int(time.time()))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: {limit_per_minute} requests/minute",
            headers={
                "Retry-After": str(retry_after),
                "X-RateLimit-Limit": str(limit_per_minute),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(reset_at),
            },
        )
