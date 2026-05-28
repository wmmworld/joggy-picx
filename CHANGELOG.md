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
- [Claude] `tools/smoke_test.py` — standalone 7-check auth smoke test: health + ingest/internal/public no-auth (403) + public/erasure no-params (422) + public invalid-key (401) + internal invalid-JWT (401); exit 0 = all pass (commit: 9582de8)
- [Claude] `apps/backend/joggy/worker/db.py` — async DB session context manager for sync RQ worker tasks; creates fresh engine per call (safe for forked workers); pool_size=5, max_overflow=10, pool_pre_ping=True (commit: a9af103)
- [Claude] `apps/backend/joggy/worker/tasks.py` — `process_erasure()` + `_process_erasure_async()`: Right to Erasure (D-014, SLA 24h); deletion order: FaceEmbeddings → ReviewQueue → R2 objects → Photo rows; idempotency guard; `processing` committed before R2 loop; `_mark_failed` exception safety; AuditLog(actor=system) (commits: bf33040, a35c0f5)
- [Claude] `apps/backend/joggy/api/public.py` — `request_erasure()` full implementation: scope check + UUID validate + event exists + organizer ownership check + idempotency (409) + ErasureRequest row (sla_deadline=now+24h) + enqueue_process_erasure (503 on Redis failure) + AuditLog(actor=partner) → 202 Accepted (commits: 6101307, 0dae9bb)
- [Claude] `docs/cursor-tasks/phase2-day5-frontend.md` — Cursor prompts: Event Create Modal (`CreateEventModal.tsx` + events page button) + Review Queue skeleton (`/dashboard/review` static page + dashboard nav link) (commit: c9622af)
- [Claude] Task 3: `enqueue_process_erasure()` function — RQ queue wrapper for Right-to-Erasure jobs (D-014 SLA 24h); added with TDD approach: 2 unit tests in `apps/backend/tests/worker/test_queue.py` covering job ID return + correct timeout values (300s/86400s/604800s); mirrors `enqueue_process_photo` pattern (commit: d213ba2)

### Infra
- [Claude] Task 2: pytest-asyncio + test package structure — เพิ่ม `pytest-asyncio>=0.23.0,<1.0.0` ใน dev dependencies + ตั้ง `[tool.pytest.ini_options]` with `asyncio_mode = "auto"` + `testpaths = ["tests"]` + สร้าง `apps/backend/tests/__init__.py` + `apps/backend/tests/worker/__init__.py` (commit: 88ff19f)

### Fixed
- [Claude] `apps/backend/joggy/api/internal.py` — `revoke_partner_api_key`: `func.now()` → `datetime.now(timezone.utc)` (SQL expression ไม่สามารถ assign ให้ ORM attribute ตรงๆ ได้); เพิ่ม `timezone` ใน imports (2026-05-28)
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
