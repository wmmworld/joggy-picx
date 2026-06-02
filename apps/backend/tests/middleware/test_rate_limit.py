"""Tests for Redis-backed rate limit on partner API."""
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException, Response


@pytest.fixture
def fresh_response():
    """A bare Response with mutable headers."""
    return Response()


@pytest.mark.asyncio
async def test_under_limit_sets_headers_no_exception(fresh_response):
    from joggy.middleware.rate_limit import check_rate_limit

    fake_client = AsyncMock()
    fake_client.incr.return_value = 1
    fake_client.expire.return_value = True

    with patch("joggy.middleware.rate_limit._get_client", return_value=fake_client):
        await check_rate_limit(
            key_id="key-1",
            limit_per_minute=60,
            response=fresh_response,
        )

    assert fresh_response.headers["X-RateLimit-Limit"] == "60"
    assert fresh_response.headers["X-RateLimit-Remaining"] == "59"
    assert "X-RateLimit-Reset" in fresh_response.headers
    fake_client.incr.assert_called_once()
    fake_client.expire.assert_called_once()


@pytest.mark.asyncio
async def test_at_exact_limit_allowed_remaining_zero(fresh_response):
    """When count == limit, the request is still allowed (Remaining: 0)."""
    from joggy.middleware.rate_limit import check_rate_limit

    fake_client = AsyncMock()
    fake_client.incr.return_value = 60  # exactly at limit

    with patch("joggy.middleware.rate_limit._get_client", return_value=fake_client):
        await check_rate_limit(
            key_id="key-1",
            limit_per_minute=60,
            response=fresh_response,
        )

    assert fresh_response.headers["X-RateLimit-Remaining"] == "0"


@pytest.mark.asyncio
async def test_over_limit_raises_429_with_retry_after(fresh_response):
    from joggy.middleware.rate_limit import check_rate_limit

    fake_client = AsyncMock()
    fake_client.incr.return_value = 61  # one over

    with patch("joggy.middleware.rate_limit._get_client", return_value=fake_client):
        with pytest.raises(HTTPException) as exc_info:
            await check_rate_limit(
                key_id="key-1",
                limit_per_minute=60,
                response=fresh_response,
            )

    assert exc_info.value.status_code == 429
    assert "Rate limit exceeded" in exc_info.value.detail
    assert "Retry-After" in exc_info.value.headers
    assert exc_info.value.headers["X-RateLimit-Remaining"] == "0"


@pytest.mark.asyncio
async def test_redis_down_fails_open(fresh_response):
    """If Redis errors out, allow the request through and log a warning."""
    from joggy.middleware.rate_limit import check_rate_limit

    fake_client = AsyncMock()
    fake_client.incr.side_effect = RuntimeError("redis is down")

    with patch("joggy.middleware.rate_limit._get_client", return_value=fake_client):
        # Should NOT raise — fail-open
        await check_rate_limit(
            key_id="key-1",
            limit_per_minute=60,
            response=fresh_response,
        )

    # Headers NOT set when Redis fails (we couldn't read the counter)
    assert "X-RateLimit-Remaining" not in fresh_response.headers
