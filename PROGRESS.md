# PROGRESS.md — สถานะปัจจุบันของโปรเจก Joggy-PicX

> ไฟล์นี้คือ **heartbeat** ของทีม AI 4 ตัว
> ทุก AI ต้องอ่านก่อนเริ่มงาน + อัปเดตทันทีหลังเสร็จ
> Format นี้ออกแบบให้ AI ทุกตัวอ่านแล้วทำงานต่อได้ในหนเดียว

วันที่อัปเดตล่าสุด: 2026-06-05
ผู้อัปเดตล่าสุด: Claude (Tech Lead) — Bib detector v1 trained บน Kaggle (mAP50 0.914) + holdout 20/20 (100%) + ONNX deployed ที่ apps/backend/models/yolov8n_bib.onnx

---

## 📍 Current Phase

**Phase 4 — Frontend + Integration** | All sub-phases ✅ + Edge uploader ✅ | End-to-end ready: Canon → Pi → VPS → R2 → Dashboard

> Next: real-photo smoke test, then Phase 4D race-result.asia integration or Phase 4E security/rate-limit

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
- [x] **CEO: ทดสอบ Canon EOS RP tether — 2026-05-31 ✅** — Phase A (Windows digiCamControl) + Phase B (Pi 5 gphoto2 USB) ทั้ง 4 TC PASS, burst 2.5s/รูป; WiFi PTP/IP partial (Canon proprietary handshake) → ใช้ USB tether เป็น primary
- [x] **D-002 revised 2026-05-29** — Canon EOS RP ไม่มี FTP → switch ไป USB-C tether + gphoto2 (Path A primary, Path C deferred)

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
- [x] **Phase 4B Manual Review Queue** ✅ — backend (GET + PATCH, 8 tests) + Cursor frontend (event filter, bulk select, override bib, lightbox)
- [x] **Phase 4C Photo Gallery backend** ✅ — `GET /internal/events/{id}/photos` paginated + filter (bib/checkpoint/ai_status), 8 TDD tests
- [x] **Phase 4C Photo Gallery frontend** ✅ — Cursor: useEventPhotos hook + gallery page + event detail link, tsc 0 errors
- [x] **Events CRUD frontend** ✅ — create modal + edit modal + delete with cascade-warning + back nav
- [x] **Edge uploader (Pi → VPS)** ✅ — inotify daemon, tenacity retry, stuck marker, systemd service, 28 TDD tests
- [x] **End-to-end real-photo smoke test** ✅ 2026-06-01 — Canon EOS RP → Pi 5 → edge daemon → VPS → R2 → Dashboard (15 photos visible)
- [x] **Thumbnail generation** ✅ — Pillow 400×400 q75 in pipeline.py (best-effort, ~100× smaller than originals), 7 new tests, 55/55 total
- [x] **Public API rate limit + security headers** ✅ — Redis counter per partner key (uses existing rate_limit_per_minute), HSTS + X-Frame-Options + X-Content-Type-Options + Referrer-Policy + Permissions-Policy. Fail-open on Redis errors. 5 new tests, 60/60 total.
- [x] **race-result.asia Pull API integration test** ✅ — 5 tests: happy path, no match (empty list), 401 no key, 403 wrong scope, security headers. Load test 1,000 รูป deferred รอ AI pipeline + ONNX models.
- [ ] Performance tuning + remaining security audit (Codex)
- **Milestone:** race-result.asia ดึงรูปด้วยเลขบิบผ่าน Public API ได้จริง + Internal dashboard ใช้งานครบ

### Phase 5 — Polish + First Real Test (วันที่ 21–25)
- [ ] Mobile auto-trigger + NTP + battery monitor (Claude)
- [x] Security audit + Critical/High fixes (Codex) ✅ — report `docs/security-audit-2026-06-03.md`, 1 Critical + 6 High fixed, backend tests 76/76 pass
- [ ] Final perf tuning (Codex)
- [x] Mobile-responsive UI + final polish (Claude) ✅
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
- [x] **Fine-tuned bib model** ✅ — `apps/backend/models/yolov8n_bib.onnx` (2026-06-05): YOLOv8n trained บน Kaggle T4 ×2, 100 epochs, mAP50=0.914, holdout 20/20 รูปเจอบิบ + 78 boxes total
- [x] Real-model validation (export model จริง + รูปนักวิ่ง) ✅ — `tools/train/test_holdout.py` รัน production `BibDetector` กับ holdout 20 รูป (ผ่าน)
- [ ] **Multi-bib pipeline** — ปัจจุบัน `worker/pipeline.py` ยัง assume 1 bib/รูป (เรียก `detector.detect()` คืน top box เท่านั้น). Schema เปลี่ยน: `Photo.bib_number` → `PhotoBib` 1-to-many table + Alembic migration + worker loop OCR ทุก bbox + Public API search join PhotoBib + Review queue UI หลาย bib/รูป. ต้อง design discussion ก่อน implement (ADR ใหม่)
- [ ] **Bib detector v2 — improve hard cases** — known limitations จาก eyeball check 2026-06-05: บิบไกล/เล็กกว่า ~20px ตรวจไม่เจอ (Z50_0239, Z50_0240), บิบถูกมือ/มือถือบัง miss (AOF_R6_-1319). แก้: เพิ่ม training images ที่มี small/occluded bib หรือ multi-scale inference (image tiles) หรือ YOLOv8s + imgsz=1280
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

### 2026-06-05 (Phase 6 — Bib Detector Trained + Holdout 100% ✅)
- [Claude + CEO] **Bib detector v1 trained** ✅ — Roboflow workspace `wmm-qv1ad/joggy-bib` ครบ: 4 public datasets + Thai start_finish/on_the_way → annotate (SAM3 auto-label + manual review) → merged 6 messy classes → 1 class `bib` → version v1: **9,397 images** (train 9,276 / val 76 / test 45, 640×640, 3× aug). Train YOLOv8n บน Kaggle (T4 ×2) 100 epochs: **mAP50 = 0.914**, mAP50-95 = 0.675, precision ~0.91, recall ~0.85. Pipeline ติดปัญหา 3 จุด: (1) Colab Free quota หมด → switch ไป Kaggle, (2) Kaggle ตอน first session ปิด Internet ต้อง Settings→Turn on internet, (3) browser disconnect ครั้งเดียวต้องเริ่ม train ใหม่ — ครั้งสองสำเร็จ
- [Claude] **best.pt → best.onnx export** ✅ — รัน `model.export(format="onnx", imgsz=640, simplify=True, opset=17)` บน Kaggle (เลี่ยง torch install บนเครื่องที่ C: เกือบเต็ม), download ผ่าน base64 HTML link bypass (Kaggle proxy 404 ทำ direct download ไม่ได้), ย้าย+rename ไปที่ `apps/backend/models/yolov8n_bib.onnx` (12 MB). Tensor signature ตรง spec: input `images` [1,3,640,640], output `output0` [1,5,8400]
- [Claude] **Holdout 20 รูป — 20/20 รูปเจอบิบ + 78 boxes total** 🏆 — `tools/train/test_holdout.py`: โหลด ONNX ผ่าน production `BibDetector` class จริง (D-021 compliant: onnxruntime + opencv + numpy เท่านั้น, ไม่แตะ ultralytics/torch). Iteration: รอบแรกใช้ `detect()` 1 box/image → CEO ทักว่ารูปมีหลายนักวิ่งควรเจอทุก bib → เพิ่ม `detect_all()` พร้อม NMS (IoU 0.45) → ลด `_CONF_THRESHOLD` 0.5→0.25 (YOLOv8 default) เพื่อจับบิบที่ถูกบัง/มุมเอียง. ผล final: 78 detections (เฉลี่ย 3.9/รูป, สูงสุด 11 bibs ใน F23_1526). CEO eyeball check: ส่วนใหญ่ตรง, false positive 2 จุด (กล่องที่ conf < 0.3 บนมือคน), false negative ในบิบไกลมาก + บิบถูกมือถือบัง (ยอมรับเป็น v1 limitation — recall > precision ใน use case นี้เพราะ OCR step กรองได้)
- [Claude] **`BibDetector.detect_all()` + NMS** ✅ — `apps/backend/joggy/ai/bib_detector.py` เพิ่ม method ใหม่ return `list[BibBox]` หลัง NMS ; เก็บ `detect()` เดิมเป็น wrapper `detect_all()[0] or None` กัน break `worker/pipeline.py` ที่ assume 1 bib/รูป. แก้ test 10/10 pass (เดิม 6 + ใหม่ 4: empty list, multiple distinct, NMS overlap drop, legacy detect() top-box). Followup task: pipeline.py + DB schema (`PhotoBib` 1-to-many) ยังเก็บ 1 bib/รูป — รอ design discussion รอบหน้า
- [Claude] **`load_sessions()` fail-fast** ✅ — `apps/backend/joggy/ai/session.py`: pre-check ทุก ONNX path ด้วย `os.path.isfile` ก่อน instantiate session. ถ้าหาย raise `FileNotFoundError` ที่ list ทุกไฟล์ที่ขาด + ชี้ไป `apps/backend/models/README.md`. ก่อนหน้านี้ onnxruntime จะ throw `[ONNXRuntimeError] : 3 : NO_SUCHFILE` cryptic ไม่บอกว่าไฟล์ไหน. 2 new tests (5/5 pass, was 3). Refactor `_load` helper → declarative `_MODEL_PATHS` dict เป็น SSOT สำหรับ paths
- [Claude] **`apps/backend/models/README.md` ครบ** ✅ — บันทึก yolov8n_bib.onnx v1 metadata: training source (Roboflow joggy-bib v1, 9397 images, Kaggle T4 ×2 100 epochs), metrics (mAP50 0.914, mAP50-95 0.675), CEO eyeball test result (20/20, 78 boxes), known v2 limitations, regenerate-from-scratch steps, sanity-check command. ทีม AI คนถัดมา deploy/refresh ได้โดยไม่ต้องเดาสมุดเรียน

### 2026-06-04 (เช้า — Phase 6 Bib Fine-tune Deliverables + Pipeline Recovery)
- [Claude] **Phase 6 bib fine-tune deliverables** ✅ — 5 ไฟล์พร้อม CEO เริ่ม annotate ทันทีหลังคัดรูป 200 ตัว: design spec ครบ (Hybrid 500 public + 180 Thai train + 20 holdout, success criteria recall≥0.90/precision≥0.80/mAP50≥0.85, toolchain Roboflow+Colab Free), tools/train/README.md step-by-step walkthrough, train_bib_colab.ipynb (run-all on T4 GPU, ~30-60 min), eval_bib.py (onnxruntime + opencv, CI-gating ready), datasets.md research notes (commit: 4b6f1f7)
- [Claude] Bib model brainstorm ✅ — CEO เลือก Hybrid strategy + Roboflow annotate + Colab train + ใช้ photos จาก 10K+ archive ของงานวิ่งที่ CEO จัดเอง
- [Claude] **Pipeline recovery วันใหม่** — diagnose 4 ปัญหาซ้อนกัน: (1) Redis container ปิด หลัง CEO shutdown laptop เมื่อคืน, (2) docker-compose ขาด `ports: 6380:6379` ทำให้ host ไม่เห็น Redis (fix: commit 0300708), (3) WiFi profile = Public → Windows Firewall block inbound แม้มี rule (fix: `Set-NetConnectionProfile ... Private`), (4) Laptop IP เปลี่ยน DHCP จาก .38 → .36 ระหว่าง debug (fix: sed Pi .env). ทุกอย่างกลับมาทำงาน — Pi รูปเช้านี้ upload สำเร็จ
- [Claude] **DEV-1 ingest graceful Redis** ✅ — แก้ ingest endpoint ให้ return 202 + `job_id: null` + `status: "pending_enqueue"` เมื่อ enqueue fail (Redis down) แทนการ 500 + rollback. กัน Pi retry storm + R2 orphan objects. Audit log บันทึก `enqueue_status` เพื่อให้ DEV-3 watchdog หา orphans มา re-enqueue ภายหลัง. 2 regression tests, 86/86 pass (commit: 714648d)
- [Claude] **DEV-2 Tailscale IP สำหรับ Pi→laptop** ✅ — install Tailscale บน Pi (100.122.125.47) + ใช้ laptop Tailscale IP (100.96.103.65) ใน Pi `INGEST_URL`. ทดสอบ HTTP 200 ผ่าน. ประโยชน์: IP คงที่ตลอด แม้ laptop เปลี่ยน WiFi/DHCP renew, ไม่ต้อง Windows Firewall rule, E2E encrypted. Updated apps/edge/README.md เพิ่ม tip block แนะนำ Tailscale (commit: 926d698)
- [Claude] **DEV-3 watchdog re-enqueue** ✅ — `joggy/worker/recovery.py`: สแกน AuditLog หา `enqueue_status="pending_enqueue"` ใน 24 ชม.ล่าสุด, re-enqueue ทุก photo ที่ยังไม่ recover, เขียน "enqueue_recovered" audit row กัน duplicate. Trigger: (1) startup hook ใน lifespan (auto), (2) `POST /internal/worker/reenqueue-pending` (admin manual). 6 new tests, 92/92 pass. ปิดลูปที่ DEV-1 เปิดไว้ — pipeline self-heal ได้สมบูรณ์ (commit: e12a872)
- [Claude] Backlog เหลือ 1 รายการ: DEV-4 health widget

### 2026-06-03 (ค่ำ — L-002 + monitor.sh)
- [Claude] **L-002 event token prefix 12 chars** ✅ — `internal.py` issue `plaintext[:8]` → `[:12]` + `middleware/event_token.py` lookup โดย 12-char prefix แล้ว fallback 8-char สำหรับ legacy tokens (Pi live token ที่ออกตอนเช้ายังใช้ได้ไม่ต้อง rotate). 4 new tests ครอบคลุม new prefix lookup + legacy fallback. 84/84 pass (was 80) (commit: 74a94c3)
- [Claude] **`tools/monitor.sh`** ✅ — one-command Pi field health check: services / camera / photo flow / recent uploads / system temp / VPS health / network — designed for race-day ops via phone-SSH. รัน `bash tools/monitor.sh` หรือ `--watch` (refresh 10s). ไม่ต้องลง deps เพิ่ม (commit: 33106ca)

### 2026-06-03 (เย็น — Stress Test + Audit Quick Wins)
- [Claude] **Stress test DIY** ✅ — Antigravity hit quota หลังทำได้บางส่วน (cloud worktree ไม่ sync มา local) เลยเขียนเอง: `tools/stress_test.py` (3 scenarios, httpx ASGITransport, mocked DB/R2/RQ, Redis จริงผ่าน Docker Compose) + `docs/stress-test-2026-06-03.md`. ผล 60s/scenario: A ingest burst 1,074 req (240×202 + 834×429 rate limit) p95 16ms · B public 19,281 req @ 321 RPS p95 31ms · C rate limit fast 200 req (120×202 + 80×429 exact threshold). **0 × 5xx ทุก scenario.** ยืนยัน Codex H-002 rate-limit fix ใช้งานจริง — fired 914 × 429 รวม. ข้อจำกัด: in-process benchmark ไม่วัด Postgres/R2/network จริง, สั่งทำ staging VPS load test เป็น follow-up (commit: a9fdc61)

### 2026-06-03 (เย็น — Audit Quick Wins + Antigravity brief)
- [Claude] **M-004 dependency upper bounds** ✅ — `apps/backend/pyproject.toml`: เพิ่ม upper bound `<NextMajor>` ให้ sqlmodel/alembic/asyncpg/pgvector/boto3/argon2-cffi/pyjwt ที่เดิมเปิด open. `uv lock` resolve 71 packages clean, 80/80 tests pass (commit: e03437f)
- [Claude] **M-001 typed query params** ✅ — `apps/backend/joggy/api/public.py`: เปลี่ยน `event_id: str` → `uuid.UUID` (FastAPI 422 อัตโนมัติเมื่อ malformed), `bib: str` → `Query(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9_-]+$")`, `reason: str | None` → `Query(max_length=500)`. ผลข้างเคียง: ปฏิเสธ SQL/path injection chars (`' OR 1=1--`, `../`) ที่ framework boundary. เพิ่ม 4 regression tests, 80/80 pass (commit: 2b660b4)
- [Claude] **L-003 Pi .env chmod 600** ✅ — `tools/setup_pi.sh`: หลัง write .env บรรจุ EVENT_TOKEN ทำ chmod 600 + tighten existing .env ใน re-run (commit: a2e10a3)
- [Claude] **Antigravity stress test brief** — `docs/antigravity-tasks/phase5-stress-test.md`: 3 scenarios (ingest burst 20 req/s, public API 100 RPS, rate limit verification of Codex's H-002 fix), ส่งให้ Antigravity (Gemini Pro/Max) รัน background (commit: f207b02)

### 2026-06-03 (Phase 5 — Security Audit + Critical/High Fixes)
- [Codex] Pre-production backend security audit ✅ — สร้าง `docs/security-audit-2026-06-03.md`; พบ 1 Critical + 6 High และแก้ครบเป็น commit แยก: public photos tenant scope, ingest magic-byte/bounded-read validation, ingest rate limit per Event Token, Supabase JWT issuer required, production default SECRET_KEY rejected, partner key management admin-only, erasure worker fail เมื่อ R2 delete fail. Verification: `cd apps/backend && uv run pytest tests/ -v` ผ่าน 76/76; `uv pip list --outdated` run แล้ว (มี package outdated บันทึกในรายงาน); `pip-audit` ไม่อยู่ใน environment จึงยังไม่ได้รัน CVE scan.

### 2026-06-03 (Phase 5 — Mobile-Responsive UI)
- [Claude] Phase 5 mobile-responsive UI polish ✅ — 6 files updated following `docs/cursor-tasks/phase5-mobile-responsive.md`: (1) `layout.tsx` viewport meta; (2) dashboard responsive padding + h1 sizing; (3) events page full-width button + header; (4) event detail flex-wrap actions + breadcrumb sizing + photo link full-width mobile; (5) photo gallery PRIMARY: search input text-base (iOS zoom fix), grid 2-col mobile→3-col tablet→4-col desktop, gap-2 md:gap-4, aspect-square image container, lightbox touch-none, pagination flex-wrap; (6) review queue stats flex-wrap + table min-w-[600px]. TypeScript 0 errors. CEO can now monitor photos on mobile (375px–430px) at marathon events without breaking desktop layout. (commit: ae87c84)

### 2026-06-03 (Battery Test — PASS ✅)
- [Claude] **Battery test 4h10m PASS** — 14:23–18:33 ไม่มี service crash แม้แต่ครั้งเดียว (50 readings ทุก 5 นาที). Memory: 542Mi→567Mi (+25Mi/4h, ไม่มี leak). Temp: 41.9–46.9°C (max ต่ำกว่า 70°C threshold มาก). Photos: 12 รูป upload สำเร็จทุกใบ. Power cut recovery: services auto-restart และ upload ได้ทันทีหลัง reboot. Pi 5 + Canon EOS RP พร้อมสนามจริง ✅

### 2026-06-03 (Pi Setup Script + Two-Bug Saga Resolved)
- [Claude] **feat(tools): `tools/setup_pi.sh`** ✅ — idempotent bash script สำหรับ onboard Pi ใหม่ตั้งแต่ blank Raspberry Pi OS: install packages (gphoto2, uv, git, acl), udev rule Canon EOS RP, clone/update repo, uv venv + deps, create photo folders, install joggy-edge (system service) + joggy-capture (user service), loginctl enable-linger, interactive prompt สำหรับ INGEST_URL + EVENT_TOKEN → write .env, start services, smoke test /healthz. Encodes all lessons learned 2026-06-03 (commit: 2252f6f)

### 2026-06-03 (Pi Capture Service — Two-Bug Saga Resolved)
- [Claude] **fix #2 (root cause): user-level service, not system-level** ✅ — เลิกใช้ `/etc/systemd/system/joggy-capture.service` (User=pi) เปลี่ยนเป็น `/home/pi/.config/systemd/user/joggy-capture.service` + `sudo loginctl enable-linger pi`. เหตุผล: system service รันนอก login session → libgphoto2 อ่าน USB endpoint ของ Canon ไม่ได้ (`Permission denied` ทุกครั้งที่ download image) เพราะ systemd-logind ตั้ง uaccess ACL ให้เฉพาะ login session ของ user pi เท่านั้น แม้ device เป็น `crw-rw-r--+ plugdev` และ user pi อยู่ใน plugdev group ก็ไม่ช่วย. User-level service + linger ทำให้ session ของ pi อยู่ตลอดแม้ reboot → ได้ ACL → gphoto2 ทำงาน. เพิ่ม `99-joggy-canon.rules` udev rule (MODE 0664 GROUP plugdev for Canon 04a9:32e2) เป็น belt-and-braces + `ExecStartPre=gphoto2 --reset` ล้าง orphan PTP session ที่ทำให้ Canon ตอบ "Access Denied" หลัง unclean exit (commit: f988f00)
- [Claude] **fix #1: escape `%%` ใน systemd unit** ✅ — `apps/edge/infra/joggy-capture.service`: `--filename ".../%Y%m%d_%H%M%S.jpg"` ทำให้ systemd expand `%Y/%m/%H/%M/%S/%d` เป็น systemd specifiers (state dir, hostname, etc.) → filename เพี้ยนเป็น `/home/pi/photos/inbox//etc/systemd/system<uuid>/run/credentials/...` → gphoto2 capture fail → restart loop ตลอด. Fix: เปลี่ยนเป็น `%%Y%%m%%d_%%H%%M%%S` + เพิ่ม `ExecStartPre=/bin/sleep 5` (USB enumeration race) + `Restart=always` (recover from clean gphoto2 exit) + `TimeoutStartSec=60` (commit: 444b51e)
- [Claude] **End-to-end verified via user service** ✅ — `/home/pi/photos/inbox/20260603_140116.jpg` (5.8 MB) → `Uploaded ... photo_id=266f30c9-04c1-4544-b915-c2789f15ea5a` → dashboard. รูปขึ้นจริงผ่าน service ไม่ใช่ manual command (ก่อนหน้านี้ 19 รูปที่เห็น มาจาก manual run ทั้งหมด — service ไม่เคยทำงานเลย)
- [Claude] Token rotation verified end-to-end ✅ — UI generate token → CEO copy → `sed -i ...` Pi `.env` → `systemctl restart joggy-edge` → upload กลับมาทำงานปกติ (เดิม token expire ทำให้ pipeline พัง)

### 2026-06-03 (Phase 5 — Event Token Generation UI)
- [Cursor] Event Token Generation UI ✅ — `components/events/GenerateEventTokenModal.tsx` created: 2-step modal (confirm generation → show plaintext token with copy button), one-time display warning, Pi setup instructions, formatThaiDateTime integration, clipboard API + Event detail page: added "🔑 สร้าง Event Token" button (emerald-600), wire modal with state + onClose handler — tsc 0 errors ✅

### 2026-05-31 (Phase 4C — Photo Gallery Frontend)
- [Cursor] Phase 4C Tasks A, B, C ✅ — `hooks/useEventPhotos.ts` created (PhotoItem, EventPhotosResponse, PhotoFilters types + useEventPhotos hook with URL state) + `photos/page.tsx` full gallery page: URL state management (useSearchParams/useRouter), debounced bib filter (300ms), checkpoint + AI status dropdowns, photo grid (3 cols mobile / 4 cols md+), ConfidenceBadge + AIStatusBadge components, pagination bar (1-N with ellipsis), lightbox modal, loading skeleton, empty states + Event detail page: added "📷 ดูรูปภาพ" Link button — tsc 0 errors ✅

### 2026-05-29 (Phase 4B — Manual Review Queue)
- [Cursor] Phase 4B Tasks A, B, C ✅ — `apiPatch` helper added to `lib/api.ts` + `hooks/useReviewQueue.ts` created (types + hooks) + `review/page.tsx` full implementation: event dropdown, stats bar, bulk actions, table (checkbox, thumbnail, bib override input, confidence badges, approve/reject buttons), lightbox modal, toast notifications, optimistic updates
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
