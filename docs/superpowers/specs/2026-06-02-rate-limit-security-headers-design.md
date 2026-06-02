# Rate Limit + Security Headers Design

**Date:** 2026-06-02
**Author:** Claude (Tech Lead)
**Status:** Approved

---

## Goal

Add two production-readiness layers to the Public API before partners start using it:

1. **Rate limiting** — enforce the existing `PartnerApiKey.rate_limit_per_minute` value (DB column already exists, never enforced). Prevents abuse, runaway loops, accidental DDoS.
2. **HTTP security headers** — basic OWASP hygiene (HSTS, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy).

Out of scope: CSP (API-only backend), CSRF (token-based auth not cookie), full OWASP audit, penetration testing.

---

## Architecture

### Rate Limiting

Redis counter per `(api_key_id, minute_window)`. Reuses existing Redis (port 6380, already used for RQ queue).

```
Request → verify_partner_api_key()  (existing — extracts key_id + rate_limit)
       → check_rate_limit(key_id, limit=rate_limit_per_minute)
            window = int(time.time() // 60)
            redis_key = f"rl:{key_id}:{window}"
            count = redis.INCR(redis_key)
            if count == 1: redis.EXPIRE(redis_key, 60)
            if count > limit: raise HTTPException 429
       → endpoint handler
```

**Key properties:**
- 60-second sliding-bucket (simple, not strictly sliding window — accepts brief boundary spikes)
- Counter expires automatically after 60s (no cleanup needed)
- Fail-open if Redis unavailable: log WARNING, allow request (don't block partners when ops is broken)
- Applied **only** to `/v1/public/*` endpoints (partner-facing). Internal API + Ingest API not rate limited.

### Security Headers

Single Starlette `BaseHTTPMiddleware` added to `joggy/main.py` middleware stack. Adds 5 headers to every response unconditionally.

---

## Components

### `apps/backend/joggy/middleware/rate_limit.py` (new)

```python
"""Redis-backed rate limit for partner API endpoints."""
from __future__ import annotations

import logging
import time

import redis.asyncio as redis_async
from fastapi import HTTPException, Request, Response, status

from joggy.core.config import get_settings

logger = logging.getLogger(__name__)

_client: redis_async.Redis | None = None


def _get_client() -> redis_async.Redis:
    """Lazy singleton Redis client (re-uses RQ queue's Redis)."""
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
    Sets X-RateLimit-* headers on every successful check.
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
        retry_after = reset_at - int(time.time())
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
```

### `apps/backend/joggy/middleware/partner_key.py` (modify)

Add `request: Request, response: Response` to dependency signature and call `check_rate_limit()` after the existing auth checks. Final signature:

```python
async def verify_partner_api_key(
    request: Request,
    response: Response,
    api_key: str = Depends(api_key_header),
    db: AsyncSession = Depends(get_db),
) -> PartnerKeyClaims:
    # ... existing logic to find partner_key + verify argon2 ...

    # NEW: enforce rate limit
    await check_rate_limit(
        key_id=str(partner_key.id),
        limit_per_minute=partner_key.rate_limit_per_minute,
        response=response,
    )

    # ... existing last_used_at update + return claims ...
```

This is the single chokepoint — all `/v1/public/*` endpoints already depend on `verify_partner_api_key`, so they all get rate limiting automatically.

### `apps/backend/joggy/main.py` (modify — add middleware)

```python
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

_SECURITY_HEADERS = {
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        for name, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        return response


app.add_middleware(SecurityHeadersMiddleware)
```

Added after CORS middleware. `.setdefault()` so a route can override if needed.

### `apps/backend/joggy/core/config.py` (verify)

Already has `redis_url`. No change needed.

---

## Data Flow — Rate Limit Example

```
Partner sends GET /v1/public/photos?bib=1234 (X-API-Key: jp_abc...)
  ↓
verify_partner_api_key:
  ├─ argon2 verify → partner_key (id=K, rate_limit=60)
  ├─ partner_key.revoked_at IS NULL → OK
  ├─ check_rate_limit(K, 60, response):
  │    window = floor(now / 60) = 27_812_345
  │    INCR rl:K:27812345 → 42
  │    response.headers["X-RateLimit-Remaining"] = "18"
  │    42 <= 60 → continue
  ├─ partner_key.last_used_at = now()
  └─ return claims
  ↓
endpoint runs, returns 200 OK with rate limit headers

— vs over limit —

61st request within same minute:
  ↓
INCR rl:K:27812345 → 61
  ↓
61 > 60 → raise 429 with Retry-After header
```

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Under limit | 2xx + `X-RateLimit-*` headers, counter incremented |
| At limit (exact count) | 2xx + `X-RateLimit-Remaining: 0` (last allowed request) |
| Over limit | 429 + `Retry-After` + `X-RateLimit-*` headers |
| Redis down | Fail-open: log WARNING, request proceeds (don't break partners when ops is broken) |
| Redis slow (>1s) | Fail-open (caught by generic except — same path as down) |

Fail-open is intentional. Rate limiting is a courtesy guardrail, not a security boundary — auth (argon2 + revoke check) is the security boundary, and that doesn't depend on Redis.

---

## Testing

### `apps/backend/tests/middleware/test_rate_limit.py` (new — 4 tests)

Mock Redis client:

1. **under limit** — count returns 1, no exception, response headers include `Remaining=limit-1`
2. **at limit** — count returns `limit`, no exception, `Remaining=0`
3. **over limit** — count returns `limit+1`, raises `HTTPException(429)` with `Retry-After`
4. **redis down** — `_get_client().incr` raises, function returns without raising (fail-open)

### `apps/backend/tests/test_security_headers.py` (new — 1 test)

```python
async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
    response = await client.get("/health")
assert response.status_code == 200
for header in ("Strict-Transport-Security", "X-Content-Type-Options",
               "X-Frame-Options", "Referrer-Policy", "Permissions-Policy"):
    assert header in response.headers
```

### Integration sanity

Existing `tests/api/test_public_*.py` tests (if they exist) should continue to pass — rate limit fail-open means the existing mock-Redis-less tests don't break.

Total new tests: **5**. Full suite should remain green: ~60 tests.

---

## Configuration

No new env vars. Reuses `REDIS_URL` already in `.env`.

`PartnerApiKey.rate_limit_per_minute` default in DB is `60` per minute (already exists).

---

## Deployment Notes

- Production deploy must have Redis reachable from the FastAPI process (already true — RQ already needs Redis).
- Behind reverse proxy (Nginx/Caddy), HSTS only activates on HTTPS — that's correct; we don't want HSTS on local HTTP dev.
- Per-IP rate limiting NOT implemented — partner key is the primary identifier. If we add public unauthenticated endpoints later, add a separate IP-based limit.

---

## Out of Scope (Future Work)

- **Sliding-window algorithm** — current minute-bucket allows brief 2x spikes at the boundary. Acceptable for current scale; revisit if partners complain.
- **Per-endpoint rate limits** — currently global per-key. Could have stricter limit on `/erasure` later.
- **Rate limit dashboard** — viewing current usage in admin UI. Skipped until needed.
- **Quota (daily/monthly)** — only per-minute now. Add quota_per_month column later if needed for billing.
- **CSP header** — frontend Next.js handles its own CSP; backend is API-only.
- **CSRF tokens** — token-based auth (no cookies), not needed.
- **Full security audit** — schedule pre-launch, not part of this task.
