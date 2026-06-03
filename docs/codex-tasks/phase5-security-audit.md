# Codex Task: Security Audit — Phase 5 (Pre-Production)

## Mission

Audit the Joggy-PicX backend for security weaknesses **before going to a real marathon event**. We have:
- 3 external surfaces (Ingest, Public Bib Lookup, Erasure) that take real traffic
- 1 internal surface (Internal Dashboard) behind Supabase Auth
- Hardware token (Per-Event Upload Token) used by Pi field devices
- Cloudflare R2 signed URLs returned to public clients

Working directory: `apps/backend/`
Stack: FastAPI, SQLModel, Supabase Postgres, Cloudflare R2, Redis (rate limit), argon2 token hash

---

## Output expected

**Two artifacts:**

1. **`docs/security-audit-2026-06-03.md`** — Markdown report with sections:
   - Executive summary (1 paragraph)
   - Findings table: severity (Critical/High/Medium/Low) × category × file:line × description × suggested fix
   - Recommendations grouped by effort (Quick wins / Sprint-worthy / Backlog)
   - Risk-accepted items (e.g., "fail-open on Redis is intentional — document it")

2. **One commit per Critical/High finding** — actual code fix + test. Medium/Low can be batched into a single "security hardening" commit or backlog-listed.

Do NOT just write a report — fix Critical + High items. Use TDD where it makes sense (add a regression test that fails first, then fix).

---

## In-scope surfaces

### A) `/ingest/photos` (Pi → VPS)
File: `apps/backend/joggy/api/ingest.py`
- Per-Event Upload Token (argon2 hashed, evt_ prefix, expires at event.end_at)
- MIME + size validation, sha256 dedup, R2 upload, RQ enqueue
- AuditLog write

### B) `/v1/public/photos?bib=&event_id=` (race-result.asia → VPS)
File: `apps/backend/joggy/api/public.py`
- Partner API Key auth (X-Api-Key header, argon2 hashed, scopes)
- Rate limit per `(api_key_id, minute_window)` via Redis
- Returns R2 signed URLs

### C) `/v1/public/erasure` (PDPA — partner-driven deletion)
File: `apps/backend/joggy/api/public.py`
- Same Partner API Key auth + scope check
- Idempotency on ErasureRequest row
- RQ job for cascade deletion (FaceEmbeddings → ReviewQueue → R2 → Photo)

### D) `/internal/*` (Admin/Staff dashboard)
File: `apps/backend/joggy/api/internal.py`
- Supabase JWT (HS256) verification → claims with role
- `_ensure_admin` / `_ensure_admin_or_staff` checks
- Events CRUD, Partner API Key issue/revoke, Event Token issue, Review Queue actions, Photo Gallery

### E) Middleware
Files: `apps/backend/joggy/middleware/{event_token,partner_key,internal_auth,rate_limit}.py`
- Token verification, claims parsing, rate limiting
- `main.py` SecurityHeadersMiddleware (HSTS, X-Frame-Options, etc.)

### F) Worker tasks
File: `apps/backend/joggy/worker/`
- process_photo (R2 download → thumbnail → AI → DB writes)
- process_erasure (cascade delete)

### G) Config + secrets
File: `apps/backend/joggy/core/config.py`
- `secret_key: str = "change-me-in-production"` ← default fallback, audit if this is ever used in prod
- R2 credentials, Supabase JWT secret, database URL

---

## Checklist — what to verify per category

### 1. Authentication & Authorization
- [ ] Every `/internal/*` route uses `Depends(get_current_claims)` and either `_ensure_admin` or `_ensure_admin_or_staff`
- [ ] Every `/v1/public/*` route uses `Depends(verify_partner_api_key)` with correct scope check
- [ ] `/ingest/photos` validates Event Token + token not expired + event_id matches token's event
- [ ] No route accidentally exposes admin-only data to staff (e.g., AuditLog list, secret_key)
- [ ] Supabase JWT verification rejects: expired tokens, wrong audience, wrong issuer, missing claims, wrong algorithm (alg=none attack)
- [ ] Argon2 verify uses constant-time comparison (default argon2-cffi does this)
- [ ] Token prefix check (`evt_`, `prtnr_`) is NOT used as auth — only as routing/lookup hint

### 2. Input validation
- [ ] All Pydantic schemas have appropriate `min_length`, `max_length`, `ge`, `le`, `pattern` where relevant
- [ ] UUID parameters use `UUID4` type (not `str`)
- [ ] Bib search input is validated/escaped — no SQL injection via SQLModel parameter binding (SQLModel is safe by default but check raw SQL)
- [ ] File uploads: MIME whitelist + magic-byte check (not just Content-Type header) + size cap enforced BEFORE reading full body into memory
- [ ] Pagination params: max page size capped (DOS protection)
- [ ] Date range filters: end_at > start_at validated

### 3. Rate limiting & DoS
- [ ] Rate limit covers ALL public endpoints (not just /v1/public/photos)
- [ ] Rate limit also protects `/ingest/photos` (per Event Token, separate from Partner key limit)
- [ ] `/internal/*` rate-limited per admin user (low priority — internal, but consider)
- [ ] Redis fail-open is intentional and documented (it is — verify this in audit report)
- [ ] Body size limit set at ASGI level (uvicorn `--limit-request-size` or middleware) — not just per-endpoint
- [ ] Slow-loris protection (uvicorn timeout settings)

### 4. Secrets management
- [ ] `core/config.py` `secret_key="change-me-in-production"` default — verify pydantic-settings refuses to start in prod without override, or remove default entirely
- [ ] No secrets in logs (search for `logger.*` calls that include token/password/key variables)
- [ ] No secrets in error messages returned to clients (look for f-string in HTTPException details)
- [ ] R2 credentials, Supabase JWT secret only read from env, never from code
- [ ] `.env.example` does not contain real values

### 5. R2 / signed URL
- [ ] Signed URL expiry: how long? (must be short enough to not leak access for hours)
- [ ] Bucket NOT publicly listable
- [ ] Photos URL signed per-request (not cached)
- [ ] r2_key never reveals user info (UUID-based is fine, sequential IDs would be a leak)
- [ ] Erasure flow actually deletes from R2 (cascade order: DB rows referencing R2 keys before R2 objects)

### 6. CORS + headers
- [ ] CORS allowlist explicit (no `*`)
- [ ] `main.py` line 70 TODO: production frontend URL — verify allowlist before ship
- [ ] SecurityHeadersMiddleware verifies CSP if any HTML is ever served (probably API-only — OK)
- [ ] HSTS header present (already done)
- [ ] No reflected user input in headers (header injection)

### 7. PDPA / privacy
- [ ] DELETE /erasure works idempotently
- [ ] AuditLog written on every privacy-sensitive action (erasure, token issue, etc.)
- [ ] No photo data leaks via error messages or stack traces in 500 responses
- [ ] No PII in logs (face embeddings are numeric — OK, but check)
- [ ] AuditLog itself: who can read it? (Should be admin only)

### 8. Worker / RQ jobs
- [ ] process_erasure marks photo for deletion BEFORE attempting R2 delete (so DB is consistent if R2 fails)
- [ ] No SSRF risk: worker doesn't fetch arbitrary URLs based on client input
- [ ] ONNX model loading: not loading user-controlled paths

### 9. Dependency hygiene
- [ ] Run `uv pip list --outdated` and call out any with known CVEs (pip-audit if available)
- [ ] Pinned versions in pyproject.toml (no unbounded `>=`)

### 10. Deployment posture (advisory — note in report, no code fix)
- [ ] CHANGELOG entries match commit history (audit trail integrity)
- [ ] Pi `.env` permissions (mode 600 owned by pi:pi) — note in setup_pi.sh review
- [ ] Joggy edge daemon: token leaked in logs? Check `apps/edge/joggy_edge/uploader.py` log statements

---

## Out of scope (skip)

- Infrastructure security (Hetzner VPS hardening, fail2ban, etc.) — CEO handles
- Frontend XSS (Next.js + React escape by default, and dashboard is internal-only)
- Cryptographic primitive review (argon2 / HS256 are industry standard, don't reinvent)
- AI model adversarial inputs (Phase 6+)

---

## Process

1. Read this brief
2. Read PROGRESS.md + DECISIONS.md + ARCHITECTURE.md (project context)
3. Survey in-scope files (use grep/glob freely)
4. **Write the report first** (`docs/security-audit-2026-06-03.md`) with all findings categorized
5. Triage: which findings are Critical/High?
6. Fix Critical + High items with TDD where it makes sense (one commit per fix, message: `fix(security): <category> — <one-line>`)
7. Update PROGRESS.md + CHANGELOG.md (Security category)
8. Hand back: report path + list of commit SHAs

---

## Acceptance criteria

- [ ] Audit report exists at `docs/security-audit-2026-06-03.md`
- [ ] All Critical findings have a fix commit + regression test
- [ ] All High findings have either a fix commit or an explicit "accept-risk" note in the report
- [ ] `cd apps/backend && uv run pytest tests/ -v` still passes (no regressions)
- [ ] PROGRESS.md + CHANGELOG.md updated

---

## Communication style

CEO is Thai-speaking, non-deep-technical. Final summary in PROGRESS.md should be in Thai.
Technical findings in the audit report can be English (industry-standard).

ห้ามตื่นเต้นหรือ embellish — รายงานเป็น factual ตามที่เจอจริง. ถ้าไม่มี Critical = บอกตรงๆ ว่า "no Critical found, here is the High list".
