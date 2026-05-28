# PROGRESS.md — สถานะปัจจุบันของโปรเจก Joggy-PicX

> ไฟล์นี้คือ **heartbeat** ของทีม AI 4 ตัว
> ทุก AI ต้องอ่านก่อนเริ่มงาน + อัปเดตทันทีหลังเสร็จ
> Format นี้ออกแบบให้ AI ทุกตัวอ่านแล้วทำงานต่อได้ในหนเดียว

วันที่อัปเดตล่าสุด: 2026-05-29
ผู้อัปเดตล่าสุด: Claude (Tech Lead)

---

## 📍 Current Phase

**Phase 2 — Backend + Pipeline (วันที่ 6–10)** | วันที่: Day 4

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

Milestone Day 5 (ถัดไป):
- [x] pytest-asyncio + test package structure (Claude)
- [ ] DELETE /erasure full implementation — ErasureRequest row + RQ job (Claude/Antigravity)
- [ ] Event create/edit UI (Cursor — admin only)
- [ ] Manual review queue UI skeleton (Cursor)
- [ ] Integration smoke test — end-to-end ทุก auth path (Claude)

---

## 🚦 Active Tasks (กันชนงาน — ก่อนเริ่มงานให้ขีดชื่อตัวเองที่นี่)

| AI | Task | File / Area | Tier | Model | Started At | Note |
|---|---|---|---|---|---|---|
_(ทุก Day 4 task เสร็จครบแล้ว — ดู Done Log ด้านล่าง)_

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
- [ ] Cross-checkpoint Re-ID logic (Claude)
- [ ] YOLOv8 + PaddleOCR ONNX (Codex)
- [ ] Manual review queue UI (Cursor)
- [ ] InsightFace face embedding pipeline (Antigravity)
- **Milestone:** AI อ่าน bib + face re-ID ทำงาน

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
- [ ] YOLOv8-nano ONNX integration + model download
- [ ] PaddleOCR ONNX integration (Thai/English number)
- [ ] InsightFace integration + 512-dim vector pipeline
- [ ] Cross-checkpoint Re-ID logic
- [ ] Manual review queue UI
- [ ] ONNX export scripts (tools/export/)

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
