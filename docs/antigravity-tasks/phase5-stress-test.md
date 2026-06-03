# Antigravity Task: Pre-Production Stress Test — Phase 5

## Mission

Stress test the Joggy-PicX backend before the first real marathon event.
We need to know:

1. **Can `/ingest/photos` handle a realistic burst?** Reference: at race start
   ~200 runners pass the start gate in 30 seconds → ~7 photos/second peak
   from a single Pi. We need to handle 3× that comfortably (~20 photos/second
   sustained for 1 minute).
2. **Can `/v1/public/photos` handle race-result.asia traffic?** When results
   are published, runners click a "see your photos" link. Realistic peak:
   100 RPS for the first 5 minutes after results, decaying afterwards.
3. **Does the rate limit actually trip when overrun?** (Codex just added
   `/ingest/photos` rate limit at 120 req/min per Event Token — verify it.)
4. **Where is the bottleneck?** Postgres? R2? Worker queue? Redis?

Working directory: `apps/backend/`
Stack: FastAPI + uvicorn + Supabase Postgres + Cloudflare R2 + Redis + RQ workers

---

## Output expected

**Three artifacts:**

1. **`tools/stress_test.py`** — Python script using `httpx.AsyncClient` (or
   `locust` if you prefer) that drives the three scenarios. Reusable so we
   can re-run before each future race. Configurable via CLI flags
   (`--scenario=ingest|public|all`, `--concurrency=N`, `--duration=Ns`,
   `--target-rps=N`).

2. **`docs/stress-test-2026-06-03.md`** — report with:
   - Test environment (dev laptop? VPS staging? — record it)
   - Per-scenario: target RPS, achieved RPS, p50/p95/p99 latency, error rate,
     429 count (rate-limit verification)
   - Bottleneck identified (with evidence: profiler output, RQ queue depth,
     Postgres slow log, etc.)
   - Recommendations grouped by effort
3. **Fix commits** for any blocker you find (Critical/High issues that block
   real-world readiness). Medium/Low → list in report, don't fix in this pass.

---

## In-scope scenarios

### Scenario A — `/ingest/photos` burst (Pi simulation)

Simulate 1 Pi uploading at peak rate:
- Generate 1,000 test JPEGs (each ~500KB realistic Canon RP size — or use
  one canonical sample file repeated with random sha256 salt to avoid dedup
  short-circuiting the test).
- Target: 20 req/sec sustained for 60 seconds (1,200 total)
- Auth: real Event Token from a test event you create at the start
- Expected outcome:
  - First ~120 req/min succeed (200 Created)
  - Subsequent req → 429 Too Many Requests with `Retry-After`
  - **No 5xx errors** under load (validates Codex's chunked-read fix doesn't
    OOM under burst)
  - p95 latency < 2s for accepted requests
  - Worker queue drains within 5 min (RQ depth check)

### Scenario B — `/v1/public/photos` query load (race-result.asia simulation)

Simulate partner traffic after a race:
- Pre-seed DB: insert 5,000 fake Photo rows for a test event with 10 fake bibs
  (each bib has ~100 photos at ~5 different checkpoints — realistic distribution)
- Issue a Partner API Key with `rate_limit_per_minute=10000` (so the test isn't
  rate-limited; we want to find real throughput ceiling)
- Target: 100 req/sec for 60 seconds (6,000 total queries with random bib)
- Expected outcome:
  - All requests → 200 OK
  - p95 latency < 500ms
  - R2 signed-URL generation does not become a bottleneck (each photo gets 1
    signed URL → 500 signed URLs/sec at peak)
  - Postgres query plan uses index on `(event_id, bib)` (verify with EXPLAIN)

### Scenario C — Rate-limit enforcement (security verification)

Verify Codex's `/ingest/photos` rate limit (H-002 fix from audit 2026-06-03):
- Same Event Token, fire 200 requests as fast as possible
- Expected:
  - First ~120 → 200 Created (or 409 dedup)
  - Subsequent → 429 with `Retry-After` and `X-RateLimit-Remaining: 0` headers
  - **Critical:** No request that should have been rate-limited actually
    succeeded (false-negative rate-limit = security bug)

---

## Out of scope (skip)

- AI pipeline performance — ONNX models not in place yet (Phase 6)
- Frontend load test — Next.js internal dashboard, not user-facing
- Distributed multi-Pi test — single-laptop driver is fine for MVP
- Long-duration soak test (4+ hours) — battery test already passed for that

---

## Process

1. Read `docs/security-audit-2026-06-03.md` (recent context — rate limit fixes you'll verify)
2. Read `PROGRESS.md` (where the project is)
3. Read `apps/backend/joggy/api/{ingest,public}.py` + `joggy/middleware/rate_limit.py`
   to understand current implementation
4. Survey existing tests in `apps/backend/tests/` for fixture patterns
5. Decide infrastructure: do you have a local backend running, or do you spin
   one up as part of the test? **Recommendation:** add a `conftest`-style
   "live server" mode that spawns uvicorn on a random port + uses test database
   (sqlite memory or test Postgres) + fakeredis + R2 mock (`moto` or stub).
   Don't hit real R2/Supabase in stress test.
6. Write `tools/stress_test.py` with the three scenarios
7. Run each scenario. Capture metrics.
8. Write the report.
9. If any scenario reveals a blocker (e.g., rate limit doesn't trip, OOM at
   500 req, signed URL generation 500ms), fix it with a regression test
   under `apps/backend/tests/load/` or similar.
10. Update PROGRESS.md + CHANGELOG.md
11. Hand back: report path + commit SHAs + summary table

---

## Acceptance criteria

- [ ] `tools/stress_test.py` exists and is runnable: `uv run python tools/stress_test.py --scenario=all`
- [ ] `docs/stress-test-2026-06-03.md` exists with metrics tables
- [ ] Scenario C explicitly proves rate limit fires (numeric evidence, not just
      "looked like it worked")
- [ ] No regression in `cd apps/backend && uv run pytest tests/ -v`
- [ ] PROGRESS + CHANGELOG updated

---

## Communication style

CEO is Thai-speaking, non-deep-technical. Summary in PROGRESS.md must be in Thai.
Technical report can be English.

ห้ามตกแต่ง numbers. ถ้า bottleneck เจอที่ R2 mock เพราะ mock เร็วไม่จริง — บอกตรงๆ
ในรายงานว่า "result reflects mock, real R2 may be slower". เกียรติของรายงานสำคัญกว่า
ตัวเลขสวยงาม.

---

## A note on infrastructure choice

If spinning up a full live-server test is too much work, fallback to **in-process
benchmark** using `TestClient(app)` with `asyncio.gather()` to fire concurrent
requests. This is less realistic but still finds:
- Lock contention in rate limit middleware
- N+1 query problems
- Sync code paths in async handlers

In-process is acceptable for this audit pass — record the limitation in the
report and recommend a real load test against staging VPS as a follow-up.
