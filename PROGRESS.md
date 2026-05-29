# PROGRESS.md — สถานะปัจจุบันของโปรเจก Joggy-PicX

> ไฟล์นี้คือ **heartbeat** ของทีม AI 4 ตัว
> ทุก AI ต้องอ่านก่อนเริ่มงาน + อัปเดตทันทีหลังเสร็จ
> Format นี้ออกแบบให้ AI ทุกตัวอ่านแล้วทำงานต่อได้ในหนเดียว

วันที่อัปเดตล่าสุด: 2026-05-29
ผู้อัปเดตล่าสุด: Claude (Tech Lead) — Phase 4B Task 3: PATCH /internal/review-queue/{id} ✅ (8/8 tests pass, 40/40 total)

---

## 📍 Current Phase

**Phase 4B — Manual Review Queue** | Backend ✅ (GET + PATCH, 8/8 tests) | Frontend prompt ready → Cursor executes

> Phase 2 ✅ ปิดแล้ว (backend + migration + smoke test 7/7) — server start + smoke test ผ่านแล้ว

เป้าหมาย Phase นี้: Public API คืน photos by bib + Internal dashboard login ได้ + Pi อัปรูปด้วย event_token ได้

Phase 1 (✅ ปิดแล้ว):
- [x] เอกสารหลัก 7 ไฟล์ + CONTEXT.md + ADR ครบ 7 ฉบับ + Grill 10/10
- [x] System boundary realigned + D-017/D-018/D-019/D-020/D-021
- [x] docs/schema.md (Mermaid ER 11 tables)
- [x] docs/canon-ftp-test.md (Canon FTP test plan)
- [x] Monorepo skeleton + Docker Compose + CI/CD (Codex)
- [x] apps/frontend/ Next.js 15 scaffold (Cursor)
- [x] Dependency research + D-021 ONNX-unified (Antigravity + Claude)
- [x] CEO: ตั้ง Supabase project + enable pgvector + ตั้ง Cloudflare R2
- [ ] CEO: ทดสอบ Canon FTP (ยังค้าง — ทำ parallel กับ Phase 2 ได้)

Milestone Day 3 (✅ เสร็จแล้ว):
- [x] FastAPI app structure + SQLModel models (Claude)
- [x] Alembic first migration + pgvector setup (Codex)
- [x] Supabase Auth login wire-up + protected routes (Cursor)
- [x] Event list + Event detail pages (Cursor — real API call)
- [x] Per-Event Upload Token middleware (Antigravity)

Milestone Day 4 (✅ เสร็จแล้ว):
- [x] Ingest API: POST /ingest/photos — MIME+size validate, sha256 dedup, R2 upload, RQ enqueue, AuditLog (Claude)
- [x] Public API: GET /v1/public/photos?bib=&event_id= + signed URLs (Antigravity + Claude review/fix)
- [x] Public API: DELETE /v1/erasure — auth ✅, scope check ✅, placeholder body (ยัง TODO ErasureRequest row)
- [x] Internal API: Events CRUD + Partner API Key issue/revoke (Codex + Claude review/fix)
- [x] R2 service + RQ worker queue skeleton (Claude)
- [x] Claude review Phase 2 Day 4 — แก้บัก 7 จุดใน Codex/Antigravity/Cursor output

Milestone Day 5 (✅ เสร็จแล้ว):
- [x] pytest-asyncio + test package structure (Claude)
- [x] DELETE /erasure full implementation — ErasureRequest row + RQ job + scope check + organizer check + idempotency (Claude)
- [x] Integration smoke test — 7-check auth coverage (Claude)
- [x] Cursor prompts เขียนแล้ว — Event Create Modal + Review Queue skeleton (ดู docs/cursor-tasks/phase2-day5-frontend.md)
- [x] Event Create Modal + form validation + apiPost integration (Cursor)

---

## 🚦 Active Tasks (กันชนงาน — ก่อนเริ่มงานให้ขีดชื่อตัวเองที่นี่)

| AI | Task | File / Area | Tier | Model | Started At | Note |
|---|---|---|---|---|---|---|
| — | — | — | — | — | — | ว่าง |

---

## 🔄 Active Handoff

> ใช้ส่วนนี้เมื่อ AI ตัวใดติด limit แล้วต้องการให้ตัวอื่นรับช่วงต่อ
> Format: ระบุ Task / Files / Checkpoint / Next steps / Decisions / Handoff to

_(ตอนนี้ว่าง — ไม่มี handoff ค้าง)_

---

## 🗺️ Milestones — Phase 1 → 5

### Phase 1 — Foundation (วันที่ 1–5) ✅
- [x] Architecture + ไฟล์เอกสารทั้งหมด (Claude)
- [x] Git repo + Docker Compose skeleton + Hetzner setup (Codex)
- [x] Dev environment + project structure (Cursor)
- [x] Parallel research + dependency check (Antigravity)
- [ ] Canon FTP test (Claude) — ยังค้าง, parallel กับ Phase 2
- **Milestone:** โปรเจกพร้อม + รูปจากกล้องเข้า R2 ได้

### Phase 2 — Backend + Pipeline (วันที่ 6–10)
- [x] FastAPI endpoints (Ingest + Public Bib Lookup + Erasure) + Queue (Claude)
- [x] Internal API: Events CRUD + Partner API Key issue/revoke (Codex)
- [x] Internal Dashboard: login + event list + event detail (Cursor)
- [x] Supabase Auth สำหรับ Internal User (admin/staff) + Per-Event Upload Token middleware (Antigravity)
- **Milestone:** Public API คืน photos by bib + Internal dashboard login ได้ + Pi อัปรูปด้วย event_token ได้

### Phase 3 — AI Pipeline (วันที่ 11–16)
- [x] AI service objects: BibDetector + BibOcr + FaceEmbedder (ONNX-only, D-021) (Claude — subagent-driven)
- [x] pipeline.py orchestrator + DB writes + Cross-checkpoint Re-ID (pgvector cosine) (Claude)
- [x] process_photo() wiring + lazy ONNX session singleton (Claude)
- [x] ONNX export scripts (tools/export/) + models/ placeholder (Claude)
- [ ] **Fine-tuned bib detection model** (YOLOv8 1-class) — blocker สำหรับ full e2e (ยังไม่มี dataset/training plan)
- [ ] Real-model validation: รัน pipeline กับ ONNX จริง + รูปนักวิ่งจริง (deferred — รอ model + รูป)
- [ ] Manual review queue UI — รับ/ปฏิเสธ (Cursor, Phase 4)
- **Milestone:** AI อ่าน bib + face re-ID ทำงาน — ⏳ backend พร้อม รอ validate กับ model จริง

### Phase 4 — Frontend + Integration (วันที่ 17–20)
- [ ] End-to-end integration + bugfix (Claude)
- [ ] Internal dashboard: photo gallery, manual review UI, organizer/event management (Cursor)
- [ ] race-result.asia integration test (Pull API + signed URL) + load test 1,000 รูป (Antigravity)
- [ ] Performance tuning + security check + Public API rate limit (Codex)
- **Milestone:** race-result.asia ดึงรูปด้วยเลขบิบผ่าน Public API ได้จริง + Internal dashboard ใช้งานครบ

### Phase 5 — Polish + First Real Test (วันที่ 21–25)
- [ ] Mobile auto-trigger + NTP + battery monitor (Claude)
- [ ] Security audit + final perf tuning (Codex)
- [ ] Mobile-responsive UI + final polish (Cursor)
- [ ] Stress test + parallel load test (Antigravity)
- **Milestone:** พร้อมทดสอบจริงในสนาม

---

## 📥 Backlog (สิ่งที่ยังไม่ได้ทำ — เรียงตามลำดับ)

### กลุ่ม Infrastructure (CEO ทำเอง)
- [ ] สั่ง Hetzner CPX11 + ตั้ง server
- [ ] ตั้ง Raspberry Pi 5 (OS + Python + vsftpd + watchdog)

### กลุ่ม Application (Phase 2)
- [ ] FastAPI app structure (Ingest + Internal API + Public API + Erasure API)
- [ ] Worker structure (RQ + AI pipeline)
- [ ] Supabase Auth flow สำหรับ Internal User เท่านั้น
- [x] Partner API Key issue/revoke flow
- [ ] Erasure API endpoint + 24h SLA job
- [ ] race-result.asia integration spec (Pull mode)

### กลุ่ม AI Pipeline (Phase 3)
- [x] YOLOv8-nano ONNX integration (BibDetector) ✅ — code พร้อม รอ fine-tuned model
- [x] PaddleOCR ONNX integration (BibOcr, digit-only 11-class) ✅
- [x] InsightFace integration + 512-dim vector pipeline (FaceEmbedder) ✅
- [x] Cross-checkpoint Re-ID logic (pgvector cosine, same-event) ✅
- [x] ONNX export scripts (tools/export/) ✅ — Task 8 (commit: ab38c3c)
- [ ] **Fine-tuned bib model** — yolov8n.pt default เป็น COCO 80-class (ไม่มี bib) → ต้อง train 1-class หรือหา public bib dataset
- [ ] Real-model validation (export model จริง + รูปนักวิ่ง + รัน worker) — รอ model พร้อม
- [ ] Manual review queue UI — รับ/ปฏิเสธ + override bib (Cursor, Phase 4)

### กลุ่ม Hardware
- [ ] Canon EOS RP FTP setup test
- [ ] Pi → Canon trigger (Motion mode)
- [ ] Dummy battery test (4–6 ชม.)
- [ ] NTP sync test

### กลุ่ม Polish
- [ ] Load test 1,000 รูป
- [ ] Security audit
- [ ] PDPA auto-delete cron
- [ ] Documentation final pass

---

## ✅ Done Log (เรียงจากใหม่ → เก่า)

### 2026-05-29 (Phase 4B — Manual Review Queue)
- [Claude] Cursor prompt: `docs/cursor-tasks/phase4b-review-queue-frontend.md` — full prompt for apiPatch + useReviewQueue + Review Queue page UI (commit: 5e0eeba)
- [Claude] fix(api): AuditLog action typo `"review_rejectd"` → `"review_rejected"` (commit: f1c4e91)
- [Claude] Task 3: `apps/backend/joggy/api/internal.py` — PATCH endpoint `resolve_review_queue`: load → idempotency 409 → photo+event scope check → approve/reject status transitions → optional bib override → AuditLog → commit (commit: fe8dcfe)
- [Claude] Task 3: `apps/backend/tests/api/test_review_queue.py` — 5 new PATCH tests: approve status, bib override, reject status, 409 already-resolved, 404 not-found; 8/8 review queue tests pass, 40/40 total suite pass
- [Claude] Task 2: `GET /internal/review-queue?event_id=` — JOIN ReviewQueue+Photo+Checkpoint, filter pending/in_review, max 200, R2 signed URLs; 3 tests (commit: a3bb705)
- [Claude] Task 1: `ReviewQueueItemOut` + `ReviewAction` schemas — nullable bib_confidence/thumbnail_url, blank decision_bib → None validator (commits: e6f0f08, e2776ce)

### 2026-05-29 (Phase 3 Task 8 — Export Scripts + Models Placeholder)
- [Claude] Task 8: `apps/backend/.gitignore` — excludes `models/*.onnx` + `models/buffalo_s/*.onnx`
- [Claude] Task 8: `apps/backend/models/.gitkeep` + `apps/backend/models/buffalo_s/.gitkeep` — directory placeholders
- [Claude] Task 8: `apps/backend/models/README.md` — table of 5 required ONNX files + InsightFace buffalo_s download instructions
- [Claude] Task 8: `tools/export/export_yolo.py` — YOLOv8n → ONNX export script (dev-only, requires ultralytics)
- [Claude] Task 8: `tools/export/export_ocr.py` — PP-OCRv4 det+rec → ONNX via paddle2onnx (dev-only)
- [Claude] Root `.gitignore` updated — negation rules added to allow `.gitkeep` / `README.md` in `apps/backend/models/` through the broad `models/` exclusion (commit: ab38c3c)

### 2026-05-29 (Phase 2 Day 5 — Erasure + Smoke Test + Migration)
- [Claude] Alembic migration แก้บัก 2 จุด: alembic.ini (ลบ Thai comment → UnicodeDecodeError บน Windows cp874, แก้ script_location เป็น relative path) + env.py (เปลี่ยน os.getenv() → get_settings().database_url ให้ pydantic-settings โหลด .env อัตโนมัติ)
- [Claude] Supabase Session Pooler debug: Direct connection (IPv6 only ไม่ได้บน Windows IPv4) → ใช้ Session Pooler aws-1-ap-southeast-1.pooler.supabase.com:5432 สำเร็จ
- [Claude] `uv run alembic upgrade head` ✅ — 0001_initial_schema สร้าง 11 tables ใน Supabase
- [Claude] Task 5: DELETE /erasure full implementation — scope check + UUID validate + event exists + organizer ownership check + idempotency (409) + ErasureRequest row + enqueue_process_erasure (503 on failure) + AuditLog(actor=partner) (commit: 0dae9bb)
- [Claude] Task 4: process_erasure worker — FaceEmbeddings→ReviewQueue→R2→Photo deletion order + idempotency guard + commit(processing) before R2 loop + _mark_failed exception safety (commit: a35c0f5)
- [Claude] Task 6: tools/smoke_test.py — 7-check standalone auth smoke test: health + ingest/internal/public no-auth + public/erasure no-params + public invalid-key + internal invalid-JWT (commit: 9582de8)
- [Claude] docs/cursor-tasks/phase2-day5-frontend.md — Cursor prompts for Event Create Modal + Review Queue skeleton (commit: c9622af)
- [Cursor] Event Create Modal + form validation + apiPost integration ✅

### 2026-05-29 (Task 3 — enqueue_process_erasure)
- [Claude] Task 3: Add `enqueue_process_erasure` to `worker/queue.py` using TDD — created failing test in `tests/worker/test_queue.py` (2 unit tests), implemented function in `joggy/worker/queue.py` following D-014 SLA pattern, committed as `d213ba2`

### 2026-05-29 (Task 2 — pytest-asyncio setup)
- [Claude] Task 2: pytest-asyncio + test package structure — เพิ่ม pytest-asyncio ใน dev dependencies + ตั้ง asyncio_mode="auto" + สร้าง tests/__init__.py + tests/worker/__init__.py

### 2026-05-28 (Phase 2 Day 4 — Ingest + Public + Internal API + Review)
- [Claude] Review Phase 2 Day 4 output — แก้บัก 7 จุดใน 6 ไฟล์ (ดูรายละเอียดใน CHANGELOG.md)
- [Claude] สร้าง `joggy/api/ingest.py` — POST /ingest/photos: MIME+size validate → sha256 dedup → R2 upload → Photo row → RQ enqueue → AuditLog
- [Claude] สร้าง `joggy/services/r2.py` — upload_bytes / delete_object / signed_url / r2_key_original (boto3 Cloudflare R2)
- [Claude] สร้าง `joggy/worker/queue.py` + `tasks.py` — RQ single-queue (ADR-0003) + process_photo skeleton (Phase 3 TODO)
- [Antigravity] Implement `joggy/api/public.py` — GET /v1/public/photos (scope check + bib query + signed URLs, ⚠️ ไม่ return face_embedding)
- [Codex] Implement `joggy/api/internal.py` — Events CRUD + Partner API Key issue/revoke + `joggy/api/schemas.py`

### 2026-05-28 (Phase 2 Day 3 — Frontend completion)
- [Cursor] Event list + Event detail pages (Phase 2): table UI + custom hooks (useEvents, useEventDetail) + API wrapper (lib/api.ts) + TanStack Query integration + loading/error/empty states
- [Cursor] Added typed API client: lib/api.ts with apiGet<T>() + apiPost<T,B>() + automatic JWT injection from Supabase
- [Cursor] Created custom hooks: hooks/useEvents.ts + hooks/useEventDetail.ts with exported query functions getEvents() + getEvent(id)
- [Cursor] Refactored event pages to use custom hooks + improved UI (table format with status badges, Thai date formatting, responsive grid)
- [Cursor] Updated .env.example: NEXT_PUBLIC_API_URL with localhost:8000 fallback
- [Cursor] Marked Active Tasks complete: Day 3 milestone ✅
- [Antigravity] Implement Event Token issue/revoke (generate_event_token, POST/DELETE internal API) + Public API GET photos by bib (Phase 2 Day 4)
- [Antigravity] สร้าง FastAPI Middleware 3 ตัว (event_token, partner_key, internal_auth) พร้อม verify JWT/argon2
- [CEO] ตั้ง Supabase project + enable pgvector extension + ตั้ง Cloudflare R2 bucket
- [Antigravity] สร้าง docs/dependency-check.md — ประเมิน RAM + ARM64 compat + เสนอ D-021 ONNX-unified
- [Claude] D-021: ONNX-Unified Inference — อัปเดต ADR-0003 section 6 (RAM budget correction)
- [Codex] Init monorepo skeleton + Docker Compose + CI/CD workflows (4 ไฟล์)
- [Cursor] Init apps/frontend/ — Next.js 15 + Tailwind v4 + shadcn/ui + TanStack Query + Zustand
- [Claude] docs/schema.md (Mermaid ER 11 tables) + docs/canon-ftp-test.md
- [Claude] Grill session Phase 1 Day 1 — ปิด 10/10 Open Questions (D-009 → D-020)
- [Claude] System boundary realignment — CONTEXT.md + D-017/D-018 + revise ADR-0004/0006
- [Claude] สร้างเอกสารหลัก 7 ไฟล์ + ADR 7 ฉบับ
- [Codex] Alembic setup + initial schema migration: เพิ่ม SQLModel/Alembic/pgvector deps, สร้าง `alembic.ini`, `alembic/env.py` (async + DATABASE_URL), และ `0001_initial_schema.py` (vector extension + indexes + constraints + FK cascades)
- [Codex] Implement Internal API จริง: Events CRUD (`GET/POST/GET{id}/PATCH{id}`) + Partner API Key issue/revoke (`POST/DELETE`), เพิ่ม `joggy/api/schemas.py`, และเปิดใช้ `verify_internal_user` dependency ใน internal endpoints

---

## 📝 หมายเหตุการใช้ไฟล์นี้

1. **ก่อนเริ่มงาน** — อ่านส่วน Current Phase + Active Tasks + Active Handoff
2. **กำลังทำงาน** — เพิ่มชื่อตัวเองในตาราง Active Tasks
3. **เสร็จงาน** — ย้ายจาก Backlog → Done Log + ลบจาก Active Tasks + อัปเดต CHANGELOG.md
4. **ติด limit** — กรอก Active Handoff ครบ + commit/stash + แจ้งใน CHANGELOG
5. **อัปเดตเวลา** — ใช้รูปแบบ ISO `YYYY-MM-DD` (วันนี้ = 2026-05-28)
