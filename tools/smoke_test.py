#!/usr/bin/env python3
# tools/smoke_test.py
"""
Joggy-PicX API auth smoke test.
Validates that all 3 auth paths (Ingest / Internal / Public) correctly
reject unauthenticated / unauthorized requests.

Usage:
    python tools/smoke_test.py                   # default: http://localhost:8000
    python tools/smoke_test.py http://myhost:8000

Exit code: 0 = all pass, 1 = any fail
Requires: httpx  (in [dependency-groups] dev)
"""
import sys

import httpx

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
results: list[bool] = []


def check(label: str, response: httpx.Response, expected: int) -> bool:
    ok = response.status_code == expected
    icon = "✅" if ok else "❌"
    print(f"  {icon}  {label}")
    if not ok:
        print(f"       got {response.status_code}, expected {expected}")
    results.append(ok)
    return ok


print(f"\nsmoke_test.py — Joggy-PicX API ({BASE_URL})")
print("─" * 56)

with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:

    # 1. Health check
    check("[1/7] GET /health → 200", client.get("/health"), 200)

    # 2. Ingest: no Authorization header → 403
    check(
        "[2/7] POST /ingest/photos (no token) → 403",
        client.post("/ingest/photos", data={"device_id": "x"}),
        403,
    )

    # 3. Internal: no Authorization header → 403
    check(
        "[3/7] GET /internal/events (no token) → 403",
        client.get("/internal/events"),
        403,
    )

    # 4. Public photos: no X-API-Key, no query params → 422 (FastAPI missing required params)
    check(
        "[4/7] GET /v1/public/photos (no key, no params) → 422",
        client.get("/v1/public/photos"),
        422,
    )

    # 5. Erasure: no X-API-Key, no query params → 422
    check(
        "[5/7] DELETE /v1/erasure (no key, no params) → 422",
        client.request("DELETE", "/v1/erasure"),
        422,
    )

    # 6. Public photos: valid params + INVALID key → 401
    check(
        "[6/7] GET /v1/public/photos (invalid key) → 401",
        client.get(
            "/v1/public/photos",
            params={"event_id": "00000000-0000-0000-0000-000000000000", "bib": "999"},
            headers={"X-API-Key": "invalid" + "0" * 58},
        ),
        401,
    )

    # 7. Internal: invalid JWT → 401
    check(
        "[7/7] GET /internal/events (invalid JWT) → 401",
        client.get("/internal/events", headers={"Authorization": "Bearer garbage.jwt.token"}),
        401,
    )

print("─" * 56)
passed = sum(results)
total = len(results)
emoji = "🎉" if passed == total else "⚠️ "
print(f"  {passed}/{total} passed  {emoji}\n")
sys.exit(0 if passed == total else 1)
