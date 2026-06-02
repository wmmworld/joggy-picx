# CHANGELOG — Joggy-PicX

ทุก commit / decision สำคัญ / handoff ต้อง log ที่นี่
รูปแบบ: Keep a Changelog ([keepachangelog.com](https://keepachangelog.com))
Versioning: Semantic Versioning ([semver.org](https://semver.org))

หมวดที่ใช้ได้:
- **Added** — feature ใหม่
- **Changed** — เปลี่ยน behavior ที่มีอยู่
- **Deprecated** — feature ที่กำลังจะถูกลบ
- **Removed** — feature ที่ลบแล้ว
- **Fixed** — bug fix
- **Security** — แก้ vulnerability
- **Docs** — เอกสาร
- **Infra** — infrastructure / deployment / tooling
- **Handoff** — log การ handoff ระหว่าง AI

รูปแบบบรรทัด:
`- [<AI>] <category> — <สรุปสั้น> (file/path:line ถ้ามี)`

---

## [Unreleased]

### Added
- [Claude] Pull API integration tests (`tests/api/test_pull_api.py`): 5 contract tests covering race-result.asia Pull API — happy path (photos with signed URLs), no match (empty list 200), missing API key (401), wrong scope (403), security headers present. ASGITransport + dependency_overrides pattern. Load test 1,000 photos deferred until AI pipeline (ONNX models) is ready.
- [Claude] Rate limit on Public API: `apps/backend/joggy/middleware/rate_limit.py` — Redis counter per `(api_key_id, minute_window)`. Enforces existing `PartnerApiKey.rate_limit_per_minute` (default 60/min). Fail-open on Redis errors so partners aren't blocked when ops is broken. Sets `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` headers; returns 429 with `Retry-After` when over limit. Wired into `verify_partner_api_key` so all `/v1/public/*` endpoints are covered. 4 unit tests.
- [Claude] Security headers: `SecurityHeadersMiddleware` in `apps/backend/joggy/main.py` adds 5 OWASP-basic headers to every response — `Strict-Transport-Security` (HSTS 1 year, includeSubDomains), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy` disabling geolocation/microphone/camera. CSP not added (API-only backend; frontend handles its own). 1 integration test.
- [Claude] Thumbnail generation: `apps/backend/joggy/services/thumbnail.py` — pure `generate_thumbnail()` (Pillow 400×400 q75) + `ThumbnailError`. Wired into `pipeline.py` between R2 download and AI inference. Best-effort — failures log WARNING but don't break the AI pipeline. Photo Gallery already falls back to original when `r2_key_thumbnail` is NULL. Adds `Pillow>=10.4` dep + 5 unit tests + 2 pipeline integration tests (55/55 total).
- [Claude] Edge uploader (Pi 5): `apps/edge/joggy_edge/` package with:
  - `config.py` — EdgeSettings via pydantic-settings (.env loader, HttpUrl validation)
  - `uploader.py` — async `upload_file()` + `UploadOutcome` enum (UPLOADED/DUPLICATE/REJECTED/AUTH_FAILED) + `upload_with_retry()` with tenacity exponential backoff (5s→300s capped, `stop_never`) + stuck marker touch after N attempts
  - `watcher.py` — watchdog Observer + asyncio.Queue consumer loop + file move helpers (`uploaded/YYYY-MM-DD/`, `failed/`) + extension filter + size-stability check + startup_scan + `AuthRequired` exception
  - `__main__.py` — daemon entry with SIGTERM/SIGINT graceful shutdown + `asyncio.wait(FIRST_COMPLETED)` pattern; exit codes 0/1/2 for clean/auth-failed/crash
  - `infra/joggy-edge.service` — systemd unit (User=pi, EnvironmentFile, Restart=on-failure)
  - `.env.example` — config template with all required + optional fields documented
  - 28 TDD tests: 4 config + 10 uploader + 14 watcher
  - Full Pi deployment + dev smoke test guide in `apps/edge/README.md`
- [Cursor] Phase 4C: `apps/frontend/hooks/useEventPhotos.ts` — PhotoItem + EventPhotosResponse + PhotoFilters types + `getEventPhotos()` async function + `useEventPhotos(eventId, filters)` TanStack Query hook with URL search params support (page, bib, checkpointId, aiStatus), staleTime 30s
- [Cursor] Phase 4C: `apps/frontend/app/(internal)/dashboard/events/[id]/photos/page.tsx` — full photo gallery page: URL state management (useSearchParams, useRouter, useParams), filter bar (debounced bib input 300ms, checkpoint select from useEventDetail, AI status select, "ล้าง filter" button), photo grid (3 cols mobile / 4 cols md+), PhotoCard + ConfidenceBadge + AIStatusBadge inline components, pagination bar (← [1]...[N] →, max 7 buttons with ellipsis), lightbox modal (backdrop click to close), loading skeleton (8 cards), empty states ("ไม่พบรูปภาพ" + clear filter), stats bar (แสดง X–Y จาก Z รูป)
- [Cursor] Phase 4C: `apps/frontend/app/(internal)/dashboard/events/[id]/page.tsx` — added "📷 ดูรูปภาพ" Link button (sky-600, after event name/status, before timeline) → navigates to `/dashboard/events/{id}/photos`
- [Claude] Phase 4C Task 3: `docs/cursor-tasks/phase4c-photo-gallery-frontend.md` — Cursor prompt for Photo Gallery UI: `useEventPhotos` hook + gallery page (grid 3-4 cols, debounced bib filter, checkpoint + AI status dropdowns, URL state, lightbox, pagination bar 1-N) + "ดูรูปภาพ" link in event detail (commit: c1606ee)
- [Claude] Phase 4C Task 2: `GET /internal/events/{event_id}/photos` — paginated photo gallery endpoint with bib (ILIKE escape) + checkpoint_id + ai_status filters, `OUTER JOIN Checkpoint`, R2 signed URLs, `ORDER BY Photo.created_at DESC` + 8 TDD tests (paginated items, pagination metadata, no_checkpoint→None, invalid ai_status→422, event not found→404, per_page>100→422, combined filters, wildcard escape); full suite 48/48 ✅ (commits: 44311e2, 3355709)
- [Claude] Phase 4C Task 1: `PhotoItemOut` + `EventPhotosOut` Pydantic schemas — `ai_review_status: Literal[...]`, `bib_number/bib_confidence/thumbnail_url/checkpoint_name/captured_at` nullable, pagination `Field(ge=...)` constraints (commits: d5dbc65, 37d694a)
- [Cursor] Phase 4B: `apiPatch<T, B>` helper added to `apps/frontend/lib/api.ts` — identical to apiPost but uses PATCH method; auto JWT injection from Supabase
- [Cursor] Phase 4B: `apps/frontend/hooks/useReviewQueue.ts` — types (ReviewQueueItem, ReviewActionPayload, ReviewActionResponse) + `useReviewQueue(eventId)` query hook + `useResolveItem()` mutation hook for approve/reject actions
- [Cursor] Phase 4B: Full Review Queue page (`apps/frontend/app/(internal)/dashboard/review/page.tsx`) — event dropdown (useEvents), stats bar, bulk approve/reject (Promise.all), table (checkbox all, thumbnail + lightbox, bib override input, confidence badges, approve/reject buttons with loading state), optimistic updates (remove from items), toast notifications (auto-hide 3s), loading skeleton, empty states
- [Claude] Phase 4B: `docs/cursor-tasks/phase4b-review-queue-frontend.md` — Cursor prompt for Review Queue frontend: `apiPatch` helper + `useReviewQueue` hook + full page UI with bulk select, per-row approve/reject/override, optimistic update, lightbox, toast (commit: 5e0eeba)
- [Claude] Phase 4B Task 3: `PATCH /internal/review-queue/{queue_id}` — approve/reject endpoint with optional bib override; idempotency guard (409 if already resolved); AuditLog entry per action; `rq.status.value` in response; `datetime.now(timezone.utc)` for resolved_at (`apps/backend/joggy/api/internal.py`, commit: fe8dcfe)
- [Claude] Phase 4B Task 3: 5 PATCH tests in `apps/backend/tests/api/test_review_queue.py` — approve status, bib override, reject status, 409 already-resolved, 404 not-found; full suite 40/40 ✅
- [Claude] Phase 4B Task 2: `GET /internal/review-queue?event_id=` — JOIN ReviewQueue+Photo+Checkpoint, filter pending/in_review, ORDER BY created_at DESC LIMIT 200, R2 signed URLs; 3 TDD tests (commit: a3bb705)
- [Claude] Phase 4B Task 1: `ReviewQueueItemOut` + `ReviewAction` Pydantic schemas — bib_confidence/thumbnail_url nullable, blank decision_bib coerced to None (commits: e6f0f08, e2776ce)

### Fixed
- [Claude] Phase 4B: AuditLog action typo `"review_rejectd"` → `"review_rejected"` in `resolve_review_queue` (commit: f1c4e91)

- [Claude] Task 8: `tools/export/export_yolo.py` — dev-only script: YOLOv8n.pt → ONNX (imgsz=640, simplify, opset 17); outputs `apps/backend/models/yolov8n_bib.onnx`; includes tensor-name verification notes (requires `ultralytics`, not in pyproject.toml)
- [Claude] Task 8: `tools/export/export_ocr.py` — dev-only script: PP-OCRv4 det+rec → ONNX via `paddle2onnx`; det shape `[1,3,960,960]`, rec shape `[1,3,48,320]`, opset 11; outputs `apps/backend/models/ocr_det.onnx` + `ocr_rec.onnx`
- [Claude] Task 8: `apps/backend/models/README.md` — table of 5 required model files (sizes + sources) + InsightFace buffalo_s download instructions
- [Claude] Task 8: `apps/backend/models/.gitkeep` + `apps/backend/models/buffalo_s/.gitkeep` — git placeholders for model directories
- [Claude] Task 8: `apps/backend/.gitignore` — excludes `models/*.onnx` + `models/buffalo_s/*.onnx` (ONNX files baked into Docker image, not committed)

### Infra
- [Claude] Task 8: Root `.gitignore` — added negation rules (`!apps/backend/models/`, `!apps/backend/models/.gitkeep`, etc.) to allow placeholder + README files through the broad `models/` exclusion pattern (commit: ab38c3c)
- [Cursor] Manual Review Queue skeleton: `app/(internal)/dashboard/review/page.tsx` — static UI only (Phase 2), header + stats card (0 hardcoded) + disabled action buttons + table (empty state) + Phase 3 placeholder note (apps/frontend/)
- [Cursor] Enhanced main dashboard: nav cards (Events + Review Queue + Quick Actions) with Link navigation + pending badge + emoji icons (apps/frontend/app/(internal)/dashboard/page.tsx)
- [Cursor] Event Create Modal: `components/events/CreateEventModal.tsx` — form (name, organizer_id, start_at, end_at, allowed_origins), client-side validation (end_at > start_at), apiPost integration, loading state, inline error display, backdrop click + × button to close, auto-reset on isOpen change (Phase 2 Day 5)
- [Cursor] Added `EventCreatePayload` type to `hooks/useEvents.ts`
- [Cursor] Updated `events/page.tsx`: + สร้างงานใหม่ button, useQueryClient, invalidate ["events"] cache on success, mount CreateEventModal
- [Claude] `tools/smoke_test.py` — standalone 7-check auth smoke test: health + ingest/internal/public no-auth + public/erasure no-key + public invalid-key (401) + internal invalid-JWT (401); **7/7 passed ✅** against live Supabase DB (commit: 9582de8, fix: e897d32)
- [Claude] `apps/backend/joggy/worker/db.py` — async DB session context manager for sync RQ worker tasks; creates fresh engine per call (safe for forked workers); pool_size=5, max_overflow=10, pool_pre_ping=True (commit: a9af103)
- [Claude] `apps/backend/joggy/worker/tasks.py` — `process_erasure()` + `_process_erasure_async()`: Right to Erasure (D-014, SLA 24h); deletion order: FaceEmbeddings → ReviewQueue → R2 objects → Photo rows; idempotency guard; `processing` committed before R2 loop; `_mark_failed` exception safety; AuditLog(actor=system) (commits: bf33040, a35c0f5)
- [Claude] `apps/backend/joggy/api/public.py` — `request_erasure()` full implementation: scope check + UUID validate + event exists + organizer ownership check + idempotency (409) + ErasureRequest row (sla_deadline=now+24h) + enqueue_process_erasure (503 on Redis failure) + AuditLog(actor=partner) → 202 Accepted (commits: 6101307, 0dae9bb)
- [Claude] `docs/cursor-tasks/phase2-day5-frontend.md` — Cursor prompts: Event Create Modal (`CreateEventModal.tsx` + events page button) + Review Queue skeleton (`/dashboard/review` static page + dashboard nav link) (commit: c9622af)
- [Claude] Task 3: `enqueue_process_erasure()` function — RQ queue wrapper for Right-to-Erasure jobs (D-014 SLA 24h); added with TDD approach: 2 unit tests in `apps/backend/tests/worker/test_queue.py` covering job ID return + correct timeout values (300s/86400s/604800s); mirrors `enqueue_process_photo` pattern (commit: d213ba2)

### Infra
- [Claude] Task 2: pytest-asyncio + test package structure — เพิ่ม `pytest-asyncio>=0.23.0,<1.0.0` ใน dev dependencies + ตั้ง `[tool.pytest.ini_options]` with `asyncio_mode = "auto"` + `testpaths = ["tests"]` + สร้าง `apps/backend/tests/__init__.py` + `apps/backend/tests/worker/__init__.py` (commit: 88ff19f)

### Fixed
- [Claude] `apps/backend/alembic.ini` + `alembic/env.py` — แก้ UnicodeDecodeError (ลบ Thai comment ออกจาก .ini ที่ Windows อ่านด้วย cp874) + แก้ script_location เป็น relative path + เปลี่ยน `os.getenv()` → `get_settings().database_url` ให้ pydantic-settings โหลด .env อัตโนมัติ (commit: e897d32)
- [Claude] `tools/smoke_test.py` — แก้ expected status codes: 401 แทน 403 สำหรับ no-credentials requests + 401 แทน 422 เพราะ auth dependency run ก่อน param validation + แก้ erasure path `/v1/erasure` → `/v1/public/erasure` (commit: e897d32)
- [Claude] `apps/frontend/package.json` — `biome` → `@biomejs/biome: ^1.9.0` (package name ถูกต้อง) + เพิ่ม `@types/node`, `@types/react`, `@types/react-dom`
- [Claude] `apps/frontend/middleware.ts` — `request.cookies.getSetCookie()` → `request.cookies.getAll()` (method ไม่มีใน RequestCookies) + เพิ่ม explicit type ให้ `setAll` callback
- [Claude] `apps/frontend/next.config.ts` — ลบ `experimental: { appDir: true }` (removed ใน Next.js 13.4+, causes TS error ใน Next.js 15)
- [Claude] `apps/backend/joggy/api/internal.py` — `revoke_partner_api_key`: `func.now()` → `datetime.now(timezone.utc)` (SQL expression ไม่สามารถ assign ให้ ORM attribute ตรงๆ ได้); เพิ่ม `timezone` ใน imports (2026-05-28) — `revoke_partner_api_key`: `func.now()` → `datetime.now(timezone.utc)` (SQL expression ไม่สามารถ assign ให้ ORM attribute ตรงๆ ได้); เพิ่ม `timezone` ใน imports (2026-05-28)
- [Claude] `apps/backend/joggy/api/public.py` — `request_erasure`: uncomment `claims: PartnerKeyClaims = Depends(verify_partner_api_key)` ที่ถูก Antigravity comment out → ปิดช่องโหว่ erasure endpoint ไม่มี auth; เพิ่ม `erasure:write` scope check ในตัว handler (2026-05-28)
- [Claude] `apps/backend/joggy/api/public.py` — `get_photos_by_bib`: `checkpoint.kind` → `checkpoint.kind.value` เพื่อ return string แทน raw Enum object (2026-05-28)
- [Claude] `apps/backend/joggy/api/public.py` — ย้าย `from joggy.middleware.partner_key import ...` ขึ้นมาก่อน `router = APIRouter()` (ตาม Python convention) (2026-05-28)
- [Claude] `apps/frontend/lib/api.ts` — URL prefix `${BASE_URL}/api${endpoint}` → `${BASE_URL}${endpoint}` (backend mount ที่ `/internal`, `/ingest`, `/v1/public` ไม่ใช่ `/api/...` → ทุก API call 404) (2026-05-28)
- [Claude] `apps/frontend/hooks/useEvents.ts` — `Event.status` type `"upcoming"|"ongoing"|"completed"` → `"planned"|"active"|"completed"` ตรง backend `EventStatus` enum; เพิ่ม `created_at`, `retention_until`, `allowed_origins`, `checkpoints: CheckpointSummary[]` fields (2026-05-28)
- [Claude] `apps/frontend/hooks/useEventDetail.ts` — `Checkpoint.order` → `seq_order`; ลบ `location` (backend ไม่มี field นี้ มี `lat`/`lng` แทน); อัปเดต `EventDetail` type ตรง `EventOut` schema; ลบ `description`/`photo_count`/`pending_review` ที่ backend ยังไม่ return (2026-05-28)
- [Claude] `apps/frontend/app/(internal)/dashboard/events/page.tsx` — เปลี่ยน "จำนวนรูป"/"จุดถ่าย" columns ที่อ้าง `checkpoint_count` (field ที่ backend ไม่ return) → ใช้ backend `event.status` badge (planned/active/completed) + `event.checkpoints.length`; ลบ `getStatusBadge()` ที่ไม่ใช้แล้ว (2026-05-28)
- [Claude] `apps/frontend/app/(internal)/dashboard/events/[id]/page.tsx` — `a.order`/`cp.order` → `seq_order`; ลบ `cp.location` → แสดง `cp.kind` + lat/lng; ลบ `event.description`/`event.photo_count`/`event.pending_review`; ย่อ grid จาก 4 → 3 คอลัมน์ (2026-05-28)

### Added
- [Cursor] Created typed API client: `lib/api.ts` with `apiGet<T>()` + `apiPost<T, B>()` helpers + automatic Supabase JWT injection + BASE_URL from `NEXT_PUBLIC_API_URL` env var (apps/frontend/)
- [Cursor] Created custom hooks: `hooks/useEvents.ts` + `hooks/useEventDetail.ts` with exported query functions `getEvents()` + `getEvent(id)` + TanStack Query wrappers (apps/frontend/)
- [Cursor] Refactored event list page: table format with columns (ชื่องาน | Organizer | วันจัดงาน | สถานะ | จำนวนรูป | จุดถ่าย) + status badges + clickable links + loading/error/empty states (apps/frontend/app/(internal)/dashboard/events/page.tsx)
- [Cursor] Refactored event detail page: checkpoint visualization + status indicator + timeline metrics + back navigation + loading skeleton (apps/frontend/app/(internal)/dashboard/events/[id]/page.tsx)
- [Codex] Added Alembic migration skeleton for backend: `apps/backend/alembic.ini`, `apps/backend/alembic/env.py` (async engine + `DATABASE_URL`), and initial revision `apps/backend/alembic/versions/0001_initial_schema.py` (2026-05-28)
- [Codex] Added `apps/backend/joggy/api/schemas.py` for Internal API contracts: `EventCreate`, `EventOut`, `EventStatusUpdate`, `PartnerKeyCreate`, `PartnerKeyOut` (2026-05-28)

### Changed
- [Cursor] Updated frontend package.json: added `@supabase/supabase-js` + `@supabase/ssr` dependencies
- [Cursor] Updated `.env.example`: changed `NEXT_PUBLIC_API_BASE` → `NEXT_PUBLIC_API_URL` with localhost:8000 fallback for local dev
- [Cursor] Enhanced event list UI: converted from card grid to responsive table format + status badges (color-coded) + Thai date formatting + striped rows
- [Codex] Added monorepo skeleton: root `pyproject.toml` (uv workspace), `uv.lock` skeleton, Python packages for `apps/backend` and `apps/edge`, shared generated-types placeholder, root README, and baseline repo dotfiles (2026-05-28)
- [Codex] Updated `apps/backend/pyproject.toml` dependencies for Phase 2 backend schema stack: `sqlmodel`, `alembic`, `asyncpg`, `pgvector`, `boto3`, `argon2-cffi` (2026-05-28)
- [Codex] Implemented `apps/backend/joggy/api/internal.py` from skeleton to production endpoints: Events CRUD + Partner API Key issue/revoke, with `verify_internal_user` dependency enabled and staff scope checks (organizer/event) enforced (2026-05-28)

### Infra
- [Codex] Added infrastructure skeleton: `infra/docker-compose.yml` (nginx, fastapi, redis, worker, watchtower), Nginx config skeleton, Pi provisioning skeleton script, backend/worker Dockerfiles (CPU-only), and Hetzner CPX11 runbook `docs/hetzner-setup.md` (2026-05-28)
- [Claude] Fixed `infra/docker-compose.yml` — เพิ่ม `mem_limit: 1200m` ให้ worker service ตาม ADR-0003 Rule 1 (Codex ลืมใส่)
- [Codex] Added path-filtered GitHub Actions workflows per ADR-0005: `ci-backend.yml`, `ci-frontend.yml`, `ci-edge.yml`, `ci-shared.yml` (2026-05-28)

### Docs
- [Claude] สร้างเอกสารหลัก 7 ไฟล์เริ่มต้นของโปรเจก: `CLAUDE.md`, `AGENTS.md`, `.cursorrules`, `ARCHITECTURE.md`, `PROGRESS.md`, `DECISIONS.md`, `CHANGELOG.md` (2026-05-28)
- [Claude] บันทึก Decision 8 ข้อแรก (D-001 → D-008) ลง `DECISIONS.md` (2026-05-28)
- [Claude] เปิด Open Questions 10 ข้อ (Q1–Q10) รอผล grill session Phase 1 Day 1 (2026-05-28)
- [Claude] **Grill Q1 closed** → D-009: Monorepo เดียว + สร้าง [ADR-0001](docs/adr/0001-monorepo-layout.md) (2026-05-28)
- [Claude] เพิ่ม Section 7 (Repository Layout) ใน `ARCHITECTURE.md` (2026-05-28)
- [Claude] **Grill Q7 closed** → D-010: uv เป็น Python package manager + workspace (2026-05-28)
- [Claude] **Grill Q8 closed** → D-011: Frontend bundle (Next.js App Router + Tailwind v4 + shadcn/ui + TanStack Query + Zustand) + อัปเดต `.cursorrules` (2026-05-28)
- [Claude] **Grill Q3 closed** → D-012: Pi อัปโหลดผ่าน VPS (ไม่ตรง R2) + สร้าง [ADR-0002](docs/adr/0002-pi-uploads-via-vps.md) + อัปเดต data flow ใน `ARCHITECTURE.md` (2026-05-28)
- [Claude] **Grill Q4 closed** → D-013: Single AI worker process + สร้าง [ADR-0003](docs/adr/0003-single-ai-worker-process.md) (2026-05-28)
- [Claude] **Grill Q5 closed** → D-014: PDPA retention 30/7/forever-anon + opt-in 1 ปี + self-service erasure + สร้าง [ADR-0004](docs/adr/0004-pdpa-retention-policy.md) + อัปเดต `AGENTS.md` section 9 (2026-05-28)
- [Claude] **Grill Q2 closed** → D-015: Mobile app = Expo (React Native), defer to Phase 5 (2026-05-28)
- [Claude] **Grill Q6 closed** → D-016: CI/CD GHA + GHCR + Watchtower + สร้าง [ADR-0005](docs/adr/0005-cicd-pipeline.md) (2026-05-28)

### Changed — System Boundary Realignment (2026-05-28)
CEO clarify: Joggy-PicX = closed system, runner ไม่ใช่ user ของระบบ, ดูรูปผ่าน External Partner (race-result.asia + อนาคต multi-partner). กระทบเอกสารชุดใหญ่:
- [Claude] **สร้าง [CONTEXT.md](CONTEXT.md)** — Glossary กลาง: Internal User, Photographer, Runner (external), Organizer, Event, Per-Event Upload Token, Partner API Key, Integration Mode
- [Claude] **D-017 ใหม่:** Per-Event Upload Token (photographer ไม่ register account)
- [Claude] **D-018 ใหม่:** Multi-Partner Integration: Design-for-3, Build-1 (Pull mode Phase 2) + สร้าง [ADR-0006](docs/adr/0006-multi-partner-integration.md)
- [Claude] **Revise D-011:** Frontend scope = Internal Dashboard (admin/staff) เท่านั้น (ไม่ใช่ runner-facing)
- [Claude] **Revise D-014 / [ADR-0004](docs/adr/0004-pdpa-retention-policy.md):** Consent flow ย้ายไปฝั่ง partner; Right to Erasure ผ่าน Partner API; เพิ่มข้อ DPA per-organizer
- [Claude] **Revise D-015:** Mobile app = photographer-only ใช้ Per-Event Upload Token
- [Claude] **Revise ARCHITECTURE.md:** Section 1 (boundary), data flow diagram (Presentation+Integration Layer แยก 3 audience), section 3.4 (3 audiences แยก)
- [Claude] **Revise PROGRESS.md:** Phase 2 + Phase 4 milestone, Backlog Application section (เปลี่ยน schema list + เพิ่ม Erasure API + Partner integration)
- [Claude] **Revise AGENTS.md section 9:** ห้าม implement runner-facing consent/login/signup ใน Joggy-PicX
- [Claude] **Grill Q9 closed** → D-019: Internal User Auth = Supabase Auth + `app_users` + FastAPI middleware + บังคับ MFA (Auth ถูกแยกเป็น 3 mechanism: D-019 Internal, D-017 Photographer, D-018 Partner) (2026-05-28)
- [Claude] **Grill Q10 closed** → D-020: DB Schema Workflow = Mermaid ER + SQLModel + Alembic + Raw SQL + สร้าง [ADR-0007](docs/adr/0007-db-schema-workflow.md) (2026-05-28)
- [Claude] **Grill Session Phase 1 Day 1 จบครบ 10/10 คำถาม** — ปิด Open Questions ทั้งหมด, รวม decision ใหม่ 12 ข้อ (D-009 ถึง D-020), ADR 7 ไฟล์ (2026-05-28)

### Phase 1 Day 2 — Schema + Canon FTP Test + Frontend Scaffold (2026-05-28)
- [Claude] สร้าง [docs/schema.md](docs/schema.md) — Mermaid ER 11 tables + คำอธิบาย + indexes + workflow (D-020)
- [Claude] สร้าง [docs/canon-ftp-test.md](docs/canon-ftp-test.md) — test plan สำหรับ CEO ทดสอบ Canon EOS RP → Pi 5 FTP (gate ของ Phase 1)
- [Claude] อัปเดต [PROGRESS.md](PROGRESS.md) — เปลี่ยน Active Tasks ให้ Codex/Cursor/Antigravity รับ task ต่อ, Claude blocked รอผล Canon FTP test
- [Claude] เพิ่ม column **Tier + Model** ใน Active Tasks ของ PROGRESS.md (process tooling, ไม่กระทบ code/schema)
- [Claude] เพิ่ม section **4.3 Model Tier Guide** ใน AGENTS.md — A/B/C tier + rules ประหยัด token
- [Cursor] **Init `apps/frontend/`** — Next.js 15 App Router + Tailwind v4 + shadcn/ui base components (Button/Input/Card) + TanStack Query Provider + Zustand uiStore + `app/(internal)/login/page.tsx` + `app/(internal)/dashboard/page.tsx` + `biome.json` + `.env.example` — Tier C, claude-haiku-4-5 (apps/frontend/) (2026-05-28)
- [Antigravity] Docs — สร้าง `docs/dependency-check.md` ประเมินความเสี่ยงและขนาด RAM ของ AI Worker (YOLO, OCR, InsightFace) เสนอเปลี่ยนเป็น ONNX ทั้งหมดเพื่อคุม RAM ให้ต่ำกว่า 1200MB (2026-05-28)
- [Claude] **D-021 ใหม่:** ONNX-Unified Inference Pipeline — export YOLOv8-nano + PaddleOCR → ONNX, ใช้ `onnxruntime` เดียว; อัปเดต `ADR-0003` section 6 (RAM budget correction: 900MB → 500-800MB); ห้าม import torch/paddle ใน production worker (2026-05-28)

---

## [0.0.0] — 2026-05-28

โปรเจก kickoff — ยังไม่มี code commit
