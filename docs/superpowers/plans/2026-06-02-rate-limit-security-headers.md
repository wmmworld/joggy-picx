# Rate Limit + Security Headers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce existing `PartnerApiKey.rate_limit_per_minute` via Redis counter, and add 5 OWASP-basic HTTP security headers to all responses — production-readiness hardening for the Public API.

**Architecture:** Per-key Redis counter with 60s sliding-bucket window (fail-open on Redis errors) called from `verify_partner_api_key` dependency. Security headers via single Starlette middleware in `main.py`. No DB schema changes — `rate_limit_per_minute` column already exists.

**Tech Stack:** `redis.asyncio` (already in deps via `redis>=6.0`), Starlette `BaseHTTPMiddleware`, FastAPI dependency injection, pytest-asyncio.

---

## File Map

**Create:**
- `apps/backend/joggy/middleware/rate_limit.py` — `check_rate_limit()` + lazy Redis client
- `apps/backend/tests/middleware/__init__.py` — empty package marker
- `apps/backend/tests/middleware/test_rate_limit.py` — 4 unit tests (mock Redis)
- `apps/backend/tests/test_security_headers.py` — 1 integration test

**Modify:**
- `apps/backend/joggy/middleware/partner_key.py` — call `check_rate_limit()` after auth, accept `Request`+`Response` params
- `apps/backend/joggy/main.py` — add `SecurityHeadersMiddleware`

---

## Task 1: Rate limit module (TDD)

**Files:**
- Create: `apps/backend/joggy/middleware/rate_limit.py`
- Create: `apps/backend/tests/middleware/__init__.py`
- Create: `apps/backend/tests/middleware/test_rate_limit.py`

- [ ] **Step 1: Create empty test package marker**

```bash
mkdir -p apps/backend/tests/middleware
touch apps/backend/tests/middleware/__init__.py
```

(On Windows PowerShell: `New-Item -Path apps/backend/tests/middleware/__init__.py -ItemType File -Force`.)

- [ ] **Step 2: Write the failing tests**

Create `apps/backend/tests/middleware/test_rate_limit.py`:

```python
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
```

- [ ] **Step 3: Run to verify failure**

```bash
cd apps/backend
uv run pytest tests/middleware/test_rate_limit.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'joggy.middleware.rate_limit'`

- [ ] **Step 4: Implement `rate_limit.py`**

Create `apps/backend/joggy/middleware/rate_limit.py`:

```python
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
```

- [ ] **Step 5: Run tests — expect PASS**

```bash
uv run pytest tests/middleware/test_rate_limit.py -v
```

Expected: `4 passed`

- [ ] **Step 6: Commit**

```bash
git add apps/backend/joggy/middleware/rate_limit.py apps/backend/tests/middleware/__init__.py apps/backend/tests/middleware/test_rate_limit.py
git commit -m "feat(rate-limit): check_rate_limit() with Redis counter + 4 tests

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 2: Wire rate limit into `verify_partner_api_key`

**Files:**
- Modify: `apps/backend/joggy/middleware/partner_key.py`

- [ ] **Step 1: Read current `partner_key.py`**

```bash
cat apps/backend/joggy/middleware/partner_key.py
```

Note the current dependency signature:
```python
async def verify_partner_api_key(
    api_key: str = Depends(api_key_header),
    db: AsyncSession = Depends(get_db)
) -> PartnerKeyClaims:
```

- [ ] **Step 2: Add imports + extend signature**

Edit `apps/backend/joggy/middleware/partner_key.py`:

Change the top imports from:
```python
import uuid
from datetime import datetime, timezone
import argon2
from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import List

from joggy.db.models import PartnerApiKey
from joggy.db.session import get_db
```

to:
```python
import uuid
from datetime import datetime, timezone
import argon2
from fastapi import Depends, HTTPException, Response, status
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import List

from joggy.db.models import PartnerApiKey
from joggy.db.session import get_db
from joggy.middleware.rate_limit import check_rate_limit
```

Change the function signature from:
```python
async def verify_partner_api_key(
    api_key: str = Depends(api_key_header),
    db: AsyncSession = Depends(get_db)
) -> PartnerKeyClaims:
```

to:
```python
async def verify_partner_api_key(
    response: Response,
    api_key: str = Depends(api_key_header),
    db: AsyncSession = Depends(get_db),
) -> PartnerKeyClaims:
```

- [ ] **Step 3: Insert `check_rate_limit` call after argon2 verify, before `last_used_at` update**

Find this section in `partner_key.py`:
```python
    # argon2 verify
    try:
        ph.verify(partner_key.key_hash, api_key)
    except argon2.exceptions.VerifyMismatchError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )

    # อัปเดต last_used_at — ใช้ Python datetime (ไม่ใช่ SQL func.now() ซึ่งเป็น expression)
    partner_key.last_used_at = datetime.now(timezone.utc)
```

Insert between argon2 verify and `last_used_at` update:

```python
    # argon2 verify
    try:
        ph.verify(partner_key.key_hash, api_key)
    except argon2.exceptions.VerifyMismatchError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )

    # Rate limit check (raises 429 if over limit; sets X-RateLimit-* headers)
    await check_rate_limit(
        key_id=str(partner_key.id),
        limit_per_minute=partner_key.rate_limit_per_minute,
        response=response,
    )

    # อัปเดต last_used_at — ใช้ Python datetime (ไม่ใช่ SQL func.now() ซึ่งเป็น expression)
    partner_key.last_used_at = datetime.now(timezone.utc)
```

- [ ] **Step 4: Run full backend test suite — verify nothing regressed**

```bash
cd apps/backend
uv run pytest tests/ -v 2>&1 | tail -10
```

Expected: all existing tests still pass. Existing tests that hit `/v1/public/*` won't have a real Redis (it'll fall through fail-open) so they continue to work.

- [ ] **Step 5: Commit**

```bash
git add apps/backend/joggy/middleware/partner_key.py
git commit -m "feat(rate-limit): enforce rate_limit_per_minute in verify_partner_api_key

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 3: Security headers middleware

**Files:**
- Modify: `apps/backend/joggy/main.py`
- Create: `apps/backend/tests/test_security_headers.py`

- [ ] **Step 1: Write the failing test**

Create `apps/backend/tests/test_security_headers.py`:

```python
"""Verify SecurityHeadersMiddleware adds OWASP-basic headers to all responses."""
import pytest
from httpx import ASGITransport, AsyncClient

from joggy.main import app


_EXPECTED_HEADERS = {
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}


@pytest.mark.asyncio
async def test_security_headers_present_on_health():
    """All 5 OWASP headers present on /health."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    for name, expected_value in _EXPECTED_HEADERS.items():
        assert name in response.headers, f"Missing header: {name}"
        assert response.headers[name] == expected_value, (
            f"Header {name}: expected {expected_value!r}, got {response.headers[name]!r}"
        )
```

- [ ] **Step 2: Run to verify failure**

```bash
cd apps/backend
uv run pytest tests/test_security_headers.py -v
```

Expected: FAIL — `AssertionError: Missing header: Strict-Transport-Security`

- [ ] **Step 3: Add `SecurityHeadersMiddleware` to `main.py`**

Edit `apps/backend/joggy/main.py`. After the existing imports, add:

```python
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
```

After the `app = FastAPI(...)` block but **before** `app.add_middleware(CORSMiddleware, ...)`, add:

```python
# ── Security Headers ──────────────────────────────────────────────────────────

_SECURITY_HEADERS = {
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add OWASP-basic security headers to every response."""

    async def dispatch(self, request: StarletteRequest, call_next):
        response = await call_next(request)
        for name, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        return response


app.add_middleware(SecurityHeadersMiddleware)
```

> Middleware order matters in Starlette: the **last** `add_middleware()` call runs first (outermost). We want Security Headers to be outermost so it can stamp headers even on responses that go through CORS preflight. So `SecurityHeadersMiddleware` is added FIRST in code (before CORS) — that makes it execute LAST in the chain, which is fine because the headers it adds are response-level. Both orderings would work correctly here; keep it before CORS for clarity.

- [ ] **Step 4: Run test — expect PASS**

```bash
uv run pytest tests/test_security_headers.py -v
```

Expected: `1 passed`

- [ ] **Step 5: Run full backend suite — verify no regression**

```bash
uv run pytest tests/ -v 2>&1 | tail -5
```

Expected: previous tests still pass, plus the 4 rate-limit tests from Task 1 and the 1 new security headers test.

- [ ] **Step 6: Commit**

```bash
git add apps/backend/joggy/main.py apps/backend/tests/test_security_headers.py
git commit -m "feat(security): SecurityHeadersMiddleware — HSTS + 4 more OWASP basics

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 4: PROGRESS + CHANGELOG

**Files:**
- Modify: `PROGRESS.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Update PROGRESS.md header**

In `PROGRESS.md`, replace the last-update line:
```
วันที่อัปเดตล่าสุด: 2026-06-01
ผู้อัปเดตล่าสุด: Claude (Tech Lead) — Thumbnail generation ✅ — Pillow resize 400×400 in RQ worker, fast Photo Gallery loads (8 tests, 55/55 total)
```
with:
```
วันที่อัปเดตล่าสุด: 2026-06-02
ผู้อัปเดตล่าสุด: Claude (Tech Lead) — Rate limit + Security headers ✅ — Redis per-key counter (60/min default) + 5 OWASP headers, 5 new tests
```

- [ ] **Step 2: Mark Phase 4 line in PROGRESS.md**

In the Phase 4 milestone list, find the line:
```
- [ ] Performance tuning + security check + Public API rate limit (Codex)
```
Replace with:
```
- [x] **Public API rate limit + security headers** ✅ — Redis counter per partner key (uses existing rate_limit_per_minute), HSTS + X-Frame-Options + X-Content-Type-Options + Referrer-Policy + Permissions-Policy. Fail-open on Redis errors. 5 new tests.
- [ ] Performance tuning + remaining security audit (Codex)
```

- [ ] **Step 3: Update CHANGELOG.md**

In `CHANGELOG.md`, under `## [Unreleased]` > `### Added`, prepend (at top of the Added list):

```
- [Claude] Rate limit on Public API: `apps/backend/joggy/middleware/rate_limit.py` —
  Redis counter per `(api_key_id, minute_window)`. Enforces existing
  `PartnerApiKey.rate_limit_per_minute` (default 60/min). Fail-open on Redis
  errors so partners aren't blocked when ops is broken. Sets `X-RateLimit-Limit`,
  `X-RateLimit-Remaining`, `X-RateLimit-Reset` headers; returns 429 with
  `Retry-After` when over limit. Wired into `verify_partner_api_key` so all
  `/v1/public/*` endpoints are covered. 4 unit tests.
- [Claude] Security headers: `SecurityHeadersMiddleware` in
  `apps/backend/joggy/main.py` adds 5 OWASP-basic headers to every response —
  `Strict-Transport-Security` (HSTS 1 year, includeSubDomains),
  `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: strict-origin-when-cross-origin`,
  `Permissions-Policy` disabling geolocation/microphone/camera. CSP not added
  (API-only backend; frontend handles its own). 1 integration test.
```

- [ ] **Step 4: Commit**

```bash
git add PROGRESS.md CHANGELOG.md
git commit -m "docs: update PROGRESS + CHANGELOG for rate limit + security headers

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Done

After Task 4:
- 5 new tests (4 rate-limit + 1 security headers)
- 2 new files (`rate_limit.py`, `test_security_headers.py`)
- 2 new test infra files (`tests/middleware/__init__.py`, `tests/middleware/test_rate_limit.py`)
- 2 modified files (`partner_key.py`, `main.py`)
- PROGRESS + CHANGELOG updated
- Public API endpoints now enforce per-key rate limit and all responses carry security headers

Verify the final full suite count:
```bash
cd apps/backend
uv run pytest tests/ 2>&1 | tail -2
```

Expected: previous count + 5 = ~60 passing.
