# Security Audit - 2026-06-03

## Executive Summary

Pre-production backend audit found one Critical multi-tenant authorization issue and six High issues in upload hardening, ingest DoS protection, internal JWT validation, production secret posture, partner key privilege control, and erasure correctness. No runner-facing auth or consent UI was found, which matches the closed-system boundary. Redis rate-limit fail-open remains accepted for partner endpoints because auth is still enforced and field availability is more important than blocking partners during Redis incidents.

## Findings

| ID | Severity | Category | File:line | Description | Suggested fix | Status |
|---|---|---|---|---|---|---|
| C-001 | Critical | Authorization / multi-tenancy | `apps/backend/joggy/api/public.py:63` | `GET /v1/public/photos` filters by `event_id` and `bib` but does not verify that the event belongs to `claims.organizer_id`. A partner with a valid key could read another organizer's photos if they know an event UUID. | Load `Event`, enforce `event.organizer_id == claims.organizer_id`, then query photos. Add regression test for cross-organizer 403. | Fixed |
| H-001 | High | Upload validation / DoS | `apps/backend/joggy/api/ingest.py:63` | Upload validation trusts `UploadFile.content_type` and reads the entire body before enforcing the 25 MB cap. A spoofed text/binary payload can be stored as an image, and oversized bodies consume memory before rejection. | Read in bounded chunks, reject over-limit while streaming, verify JPEG/PNG magic bytes before upload, store canonical MIME. | Fixed |
| H-002 | High | Rate limiting / DoS | `apps/backend/joggy/api/ingest.py:60` | `/ingest/photos` has strong event-token auth but no rate limit. A leaked event token can flood R2/RQ during a race. | Apply Redis rate limit per event token id after auth, fail-open by design like partner API. | Fixed |
| H-003 | High | JWT validation | `apps/backend/joggy/middleware/internal_auth.py:42` | Supabase JWT validation checks signature, audience, and expiry, but does not require issuer. Missing issuer validation weakens token-boundary checks required by D-019. | Pass expected issuer (`<supabase_url>/auth/v1`) to HS256 and JWKS decode paths and require `sub`. Add issuer regression tests. | Fixed |
| H-004 | High | Secrets management | `apps/backend/joggy/core/config.py:21` | `SECRET_KEY` has a production-unsafe default and production startup does not fail if the default is used. | Add settings validation that rejects `APP_ENV=production` with default/blank/too-short `SECRET_KEY`. | Fixed |
| H-005 | High | Privilege control | `apps/backend/joggy/api/internal.py:333` | Staff with organizer scope can issue and revoke Partner API keys and choose arbitrary scopes, including `erasure:write`. This grants privacy-impacting external access beyond staff's expected dashboard duties. | Require admin role for partner key issue/revoke. Add staff regression tests. | Fixed |
| H-006 | High | PDPA erasure correctness | `apps/backend/joggy/worker/tasks.py:123` | `process_erasure` logs R2 delete failures but still deletes DB rows and marks the erasure completed. A failed R2 delete can leave original photos in storage with no DB record to retry. | Treat any R2 delete failure as job failure, keep DB transaction rolled back, mark request failed for visibility, and let RQ retry logic handle it. | Fixed |
| M-001 | Medium | Input validation | `apps/backend/joggy/api/public.py:40` | Public `event_id` is accepted as `str` and parsed manually. Query params also lack bib length/pattern limits. | Use `uuid.UUID` or `UUID4` where possible and add `Query(..., min_length, max_length, pattern=...)` for bib. | Backlog |
| M-002 | Medium | Body size / slow-loris | `infra/docker-compose.yml:17` | ASGI/server-level request size and slow-loris timeout settings are not configured in compose/nginx. Endpoint limits now help, but transport-level protection is still missing. | Add nginx `client_max_body_size`, request timeout settings, and uvicorn timeout/limit flags once deployment config is finalized. | Backlog |
| M-003 | Medium | Signed URL lifetime | `apps/backend/joggy/services/r2.py:66` | R2 signed URLs expire in 1 hour. This matches current integration notes, but leaked URLs remain useful for up to 1 hour. | Keep 1 hour for first race unless partner confirms shorter cache windows; revisit 15-30 minute URLs after integration test. | Risk accepted |
| M-004 | Medium | Dependency pinning | `apps/backend/pyproject.toml:13` | Several dependencies use lower bounds without explicit upper bounds (`sqlmodel`, `alembic`, `asyncpg`, `pgvector`, `boto3`, `argon2-cffi`, `pyjwt`). | Add upper bounds or lock-file based deploy policy; run `pip-audit` before production. | Backlog |
| L-001 | Low | CORS | `apps/backend/joggy/main.py:68` | Production CORS allowlist is empty. This is safe for public APIs but will block the Vercel dashboard until the production domain is added. | Add the final dashboard domain to allowlist before ship. | Backlog |
| L-002 | Low | Token prefix collision | `apps/backend/joggy/api/internal.py:612` | Event token prefix stores `evt_` plus only the first four random URL-safe characters. Collision risk is low at MVP scale but higher than intended. | Increase event-token display prefix length to at least 12 characters in a future migration-free change. | Backlog |
| L-003 | Low | Pi env permissions | `tools/setup_pi.sh:215` | Pi `.env` is generated with default umask permissions and may be more readable than needed. | Add `chmod 600 "$ENV_FILE"` after writing. | Backlog |

## Recommendations By Effort

### Quick Wins

- Keep the Critical/High regression tests in the backend suite.
- Add final Vercel dashboard origin to production CORS before the first field event.
- Add `chmod 600` for Pi `.env` in `tools/setup_pi.sh`.

### Sprint-Worthy

- Add nginx body-size and timeout controls around `/ingest/photos`.
- Convert public query params to typed UUID and bounded bib fields.
- Add explicit dependency upper bounds or make lock-file deployment mandatory.

### Backlog

- Shorten signed URL TTL after partner cache behavior is measured.
- Increase token display prefix length to reduce operational collision risk.
- Add periodic security dependency audit (`pip-audit`) to CI once network policy is set.

## Risk-Accepted Items

- Redis rate limiting remains fail-open. Authentication still runs before rate limiting, and field-event availability is more important than denying valid partners or Pi devices during a Redis outage.
- 1-hour R2 signed URLs remain accepted for the first production test because the pull integration expects partner-side caching and no runner logs into Joggy-PicX directly.
- Backend serves API only, so CSP is not added in FastAPI; the Next.js dashboard should own frontend CSP later.

## Verification Notes

- Full backend test command: `cd apps/backend && uv run pytest tests/ -v` - 76 passed, 68 warnings.
- Dependency freshness command: `uv pip list --outdated` - completed. Outdated packages reported: `boto3` 1.43.17 -> 1.43.21, `botocore` 1.43.17 -> 1.43.21, `idna` 3.17 -> 3.18, `mypy` 1.20.2 -> 2.1.0, `pillow` 11.3.0 -> 12.2.0, `pydantic-core` 2.46.4 -> 2.47.0, `pytest` 8.4.2 -> 9.0.3, `pytest-asyncio` 0.26.0 -> 1.4.0, `python-multipart` 0.0.29 -> 0.0.30, `redis` 6.4.0 -> 8.0.0, `starlette` 1.2.0 -> 1.2.1.
- `pip-audit` is not installed in the current environment, so CVE scanning is not completed in this pass.

## Fix Commits

- C-001: `90a4816` - `fix(security): scope public photos by organizer`
- H-001: `0b4133f` - `fix(security): validate ingest image bytes`
- H-002: `08b627c` - `fix(security): rate limit ingest uploads`
- H-003: `c7f4059` - `fix(security): require Supabase JWT issuer`
- H-004: `fcd0419` - `fix(security): reject default production secret`
- H-005: `d1ba9fe` - `fix(security): restrict partner key management`
- H-006: `048fce4` - `fix(security): fail erasure on R2 delete errors`
