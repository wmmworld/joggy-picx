# DECISIONS.md — บันทึก Architectural Decisions ของโปรเจก Joggy-PicX

> Lightweight ADR log สำหรับ decision ระดับโปรเจกที่ AI ทุกตัวต้องรู้
> Decision ที่ "Hard-to-Reverse + Surprising + Real-tradeoff" — ทำ ADR แยกใน `docs/adr/`
> ไฟล์นี้รวมเฉพาะ decision สำคัญที่ใช้ตัดสินใจในระดับ architecture

Format ของแต่ละ Decision:
- **Status:** Accepted / Superseded / Proposed
- **Date:** ISO date
- **Context:** ทำไมต้องตัดสินใจ
- **Decision:** เลือกอะไร
- **Alternatives Considered:** ที่ไม่เลือก + เหตุผล
- **Consequences:** ผลตามมา (positive + negative)

---

## D-001 — Hetzner CPX11 (All-in-One Docker Compose) แทน Railway / Fly.io

- **Status:** Accepted
- **Date:** 2026-05-28
- **Context:** ต้องเลือก hosting สำหรับ backend ที่รัน FastAPI + Redis + AI Worker + Nginx ด้วยงบ < $7/เดือน
- **Decision:** ใช้ Hetzner CPX11 (2 vCPU, 2GB RAM, ~$5.50/เดือน) และรันทุก service ใน Docker Compose เดียวบน 1 VPS
- **Alternatives Considered:**
  - Railway — UX ดี แต่ price-per-resource แพงเกินงบ
  - Fly.io — ฟรี tier น้อยลง + cold start สำหรับ AI worker
  - DigitalOcean droplet — แพงกว่า Hetzner ที่ spec ใกล้กัน
  - AWS / GCP — overkill + ค่า egress
- **Consequences:**
  - ✅ ราคาดีสุดในระดับ spec นี้
  - ✅ Deploy ง่าย / debug ง่าย / control ได้เต็มที่
  - ⚠️ ไม่มี auto-scaling (แต่ scale 1,000 รูป/งาน รับได้)
  - ⚠️ ต้อง manage server เอง (security, update)
  - ⚠️ Single point of failure — ถ้า VPS ดับ ระบบล่มทั้งหมด

---

## D-002 — Raspberry Pi 5 เป็น Edge Ingestion (REQUIREMENT ไม่ใช่ Optional)

- **Status:** Accepted
- **Date:** 2026-05-28
- **Context:** Canon EOS RP รองรับ WiFi FTP เท่านั้น และไม่สามารถ FTP ข้าม WAN หรือใช้ HTTPS โดยตรงไปยัง R2/VPS ได้
- **Decision:** ใช้ Raspberry Pi 5 เป็น edge gateway: รับ FTP จาก Canon ภายใน LAN → Python watchdog upload ขึ้น R2
- **Alternatives Considered:**
  - ส่ง FTP ไปยัง VPS ตรง — ไม่ work เพราะ Canon FTP ไม่ผ่าน WAN ที่มี NAT/Firewall มาตรฐาน
  - ใช้ SD card swap manual — ไม่ realtime
  - ใช้ Canon Connect app บนมือถือ — ไม่ scale ถ้ามีหลายกล้อง
- **Consequences:**
  - ✅ FTP จาก Canon ทำงานได้จริงในสนาม
  - ✅ Pi ทำ motion detection (YOLO) สำหรับ auto-trigger ได้ด้วย
  - ⚠️ ต้องพก Pi + dummy battery ไปสนาม
  - ⚠️ Pi เป็น potential point of failure (มี backup plan: SD card swap)

---

## D-003 — pgvector ใน Supabase (ก่อน) → Qdrant (ทีหลังถ้าจำเป็น)

- **Status:** Accepted
- **Date:** 2026-05-28
- **Context:** ต้องเก็บ face embedding 512-dim สำหรับ Cross-Checkpoint Re-ID และค้นหาด้วย cosine similarity
- **Decision:** เริ่มด้วย pgvector ภายใน Supabase free tier ก่อน; ย้ายไป Qdrant เมื่อมี vector > 100K
- **Alternatives Considered:**
  - Qdrant ตั้งแต่แรก — เพิ่ม infra อีกตัว เกินจำเป็นที่ scale ~1,000 vector
  - Pinecone — มี free tier แต่ vendor lock-in + egress fee
  - FAISS ใน memory — ไม่ persist + reload ทุกครั้ง slow
- **Consequences:**
  - ✅ ไม่ต้องเพิ่ม infra
  - ✅ Query รวม metadata + vector ใน SQL เดียว
  - ⚠️ pgvector performance ตกที่ > 1M vector — ต้องมี migration plan
  - ✅ Migration ไป Qdrant ทำได้เพราะ embedding เก็บใน column แยก

---

## D-004 — CPU-only AI Inference (ก่อน) → GPU (ทีหลังถ้าจำเป็น)

- **Status:** Accepted
- **Date:** 2026-05-28
- **Context:** YOLOv8 + PaddleOCR + InsightFace ทำงานได้ทั้ง CPU และ GPU; งบ ~$6–7/เดือน ไม่พอ GPU instance
- **Decision:** เริ่มด้วย CPU-only บน Hetzner CPX11 (2 vCPU) และใช้ model นาโน (YOLOv8-nano, InsightFace buffalo_s)
- **Alternatives Considered:**
  - GPU instance (Hetzner GPU, Vast.ai) — เกินงบ
  - Cloud GPU on-demand (Modal, Banana) — pricing per inference, scale ไม่คุ้มที่ ~1,000 รูป/งาน
  - Edge AI บน Pi (ทุกอย่าง) — Pi 5 ทำได้บางส่วน แต่ InsightFace บน CPU ช้า + แบตหมดเร็ว
- **Consequences:**
  - ✅ ราคาในงบ
  - ⚠️ Latency สูงกว่า GPU (~2–5s/รูปสำหรับ pipeline เต็ม)
  - ✅ Throughput พอสำหรับ 1,000 รูป/4-6 ชม. (เฉลี่ย ~3 รูป/นาที, async queue รับได้)
  - ✅ Migration ไป GPU ทำได้โดยไม่กระทบ code (model interface เหมือนกัน)

---

## D-005 — Cloudflare R2 แทน AWS S3

- **Status:** Accepted
- **Date:** 2026-05-28
- **Context:** ต้องเก็บรูปต้นฉบับ + thumbnail ~1,000 รูป/งาน (รวม ~3–5 GB/งาน)
- **Decision:** Cloudflare R2 (S3-compatible) — ฟรี 10GB + ไม่มี egress fee
- **Alternatives Considered:**
  - AWS S3 — egress fee แพง ($0.09/GB) → dashboard ที่ serve รูป จะมีค่าแน่นอน
  - Backblaze B2 — ราคาถูก แต่มี egress fee
  - Local storage บน VPS — disk เต็มเร็ว + ไม่มี CDN
  - Supabase Storage — เกิน free tier ที่ ~1GB
- **Consequences:**
  - ✅ ฟรี 10GB + bandwidth ฟรีทั้งหมด
  - ✅ S3-compatible API → migrate ออกได้
  - ⚠️ ไม่มี image processing on-the-fly (ต้อง generate thumbnail เอง)
  - ⚠️ ต้องใช้ Cloudflare Images แยกถ้าต้องการ on-the-fly resize (มีค่าใช้จ่าย)

---

## D-006 — Redis + Python-RQ (Async Queue) แทน Sync Processing

- **Status:** Accepted
- **Date:** 2026-05-28
- **Context:** AI pipeline ใช้เวลา ~2–5s/รูป — sync processing ใน API request จะ timeout
- **Decision:** ใช้ Redis เป็น broker + Python-RQ เป็น worker — รับรูปเข้า queue ทันทีแล้ว process background
- **Alternatives Considered:**
  - Celery — feature เยอะเกินจำเป็น + setup ซับซ้อน
  - Dramatiq — ดีกว่า RQ ในแง่ performance แต่ ecosystem น้อยกว่า
  - Sync processing — UX แย่ + timeout
  - Cloud queue (SQS, Cloudflare Queues) — เพิ่ม dependency + ค่าใช้จ่าย
- **Consequences:**
  - ✅ Simple — RQ เรียนรู้ใน 1 ชั่วโมง
  - ✅ Redis ใช้ทั้ง cache + queue ได้ด้วย instance เดียว
  - ✅ Failure retry + dead letter queue ใน RQ
  - ⚠️ ไม่มี distributed worker pool (1 VPS = limit)

---

## D-007 — เอกสารเป็นภาษาไทย + Code เป็นอังกฤษ

- **Status:** Accepted
- **Date:** 2026-05-28
- **Context:** CEO solo dev, ทีมเป็น AI 4 ตัวที่อ่านไทยได้, ต้องการ context ที่ชัดเจนทั้งโลคอลและสากล
- **Decision:** เอกสาร (.md) เป็นภาษาไทย; Code / Identifier / Commit / Log internal เป็นภาษาอังกฤษ; Error ให้ user เป็นภาษาไทย
- **Alternatives Considered:**
  - ทั้งหมดเป็นอังกฤษ — สูญเสีย nuance + CEO อ่านไทยเร็วกว่า
  - ทั้งหมดเป็นไทย — AI ตัวอื่น (เช่น Cursor, Antigravity) อาจ context ในไทยน้อยกว่า + code review tool ส่วนใหญ่อังกฤษ
- **Consequences:**
  - ✅ CEO อ่าน docs ได้เร็ว
  - ✅ Code/Commit เข้ากันได้กับ tooling สากล
  - ⚠️ AI ต้อง switch ภาษาเวลาเขียน comment vs code
  - ⚠️ ต้อง enforce consistency — มี checklist ใน [AGENTS.md](AGENTS.md)

---

## D-008 — สื่อสารกับ CEO เป็นภาษาไทยเสมอ

- **Status:** Accepted
- **Date:** 2026-05-28
- **Context:** CEO solo dev เป็นคนไทย + ต้องการรับ context เร็ว
- **Decision:** AI ทุกตัวสื่อสารกับ CEO เป็นภาษาไทย ยกเว้น code/tech terms
- **Alternatives Considered:** ไม่มี (ชัดเจนตั้งแต่แรก)
- **Consequences:**
  - ✅ ไม่ต้องแปลในใจ
  - ⚠️ AI ที่อ่อนไทย (เช่น บาง model rare) อาจตอบแปลก — Claude ตรวจ
  
---

## D-009 — Monorepo เดียวสำหรับทุก codebase (Backend / Frontend / Edge / Mobile)

- **Status:** Accepted
- **Date:** 2026-05-28
- **ADR:** [docs/adr/0001-monorepo-layout.md](docs/adr/0001-monorepo-layout.md)
- **Context:** Solo dev + AI 4 ตัว parallel ต้องการ context กลาง + sync types ข้าม backend/frontend
- **Decision:** Monorepo เดียวที่ root `Joggy-PicX/` พร้อมโครงสร้าง `apps/` + `packages/` + `infra/` + `docs/`
- **Alternatives Considered:**
  - Multi-repo 3 repo — sync types ยาก, handoff ระหว่าง AI ยาก
  - Hybrid (backend+edge รวม, frontend แยก) — ผสมข้อเสียของทั้งสอง
- **Consequences:**
  - ✅ AI 4 ตัวอ่าน context จากที่เดียว, PROGRESS.md กลาง
  - ✅ Shared types ใน `packages/shared/` generate จาก OpenAPI
  - ⚠️ CI ต้องตั้ง `paths:` filter ป้องกัน rebuild ที่ไม่จำเป็น
  - ⚠️ Python apps 2 ตัวใช้ pyproject.toml แยก

---

## D-010 — uv (Astral) เป็น Python Package Manager

- **Status:** Accepted
- **Date:** 2026-05-28
- **Context:** Python apps 2 ตัว (`apps/backend/`, `apps/edge/`) ใน monorepo ต้องการ deps reproducible + install เร็ว (AI 4 ตัว install บ่อย)
- **Decision:** ใช้ `uv` พร้อม workspace ที่ root `pyproject.toml`; แต่ละ app มี `pyproject.toml` แยก; lockfile กลางที่ root (`uv.lock`)
- **Alternatives Considered:**
  - Poetry — ช้ากว่า uv 10–100x + workspace support จำกัด
  - pip-tools — manual maintain, ไม่มี workspace
  - Conda/Mamba — overkill สำหรับ CPU-only
- **Consequences:**
  - ✅ Install เร็วมาก, lockfile reproducible ข้าม Windows/Linux/ARM
  - ✅ uv workspace รองรับ monorepo native
  - ⚠️ ใหม่กว่า Poetry — heavy deps (insightface) อาจต้อง workaround → mitigation: Dockerfile pre-built
  - ✅ Reversible — `pyproject.toml` มาตรฐาน PEP 621 เปลี่ยนกลับ Poetry/pip ได้

---

## D-011 — Frontend Stack Bundle (Next.js App Router + Tailwind v4 + shadcn/ui + TanStack Query + Zustand)

- **Status:** Accepted (scope revised 2026-05-28 — internal tool only)
- **Scope clarification (2026-05-28):** Frontend = **Admin/Staff Internal Dashboard** เท่านั้น (ไม่ใช่ public runner-facing) — ดู [CONTEXT.md](CONTEXT.md) และ [ADR-0006](docs/adr/0006-multi-partner-integration.md)
- **Date:** 2026-05-28
- **Context:** Frontend คือหน้าค้นรูปสำหรับนักวิ่งบนมือถือกลางสนาม (อาจ 3G/EDGE) + admin/photographer dashboard; ต้อง SEO friendly + perf ดี + ให้ AI ทุกตัวอ่านโค้ดได้
- **Decision:** Stack bundle ครบเซ็ต:
  - **Framework:** Next.js 15 (App Router, React Server Components)
  - **Language:** TypeScript strict mode
  - **Styling:** Tailwind CSS v4 (config ผ่าน CSS)
  - **Component lib:** shadcn/ui (Radix primitives + Tailwind, copy-paste model)
  - **Server state:** TanStack Query (photo gallery, infinite scroll, cache, retry)
  - **Client state:** Zustand (filter, modal, UI state)
  - **Form:** react-hook-form + zod
  - **Image:** `next/image` + R2 signed URL
- **Alternatives Considered:**
  - Pages Router — เก่ากว่า, ไม่มี RSC, bundle ใหญ่กว่า
  - Mantine/Chakra/MUI — vendor lock-in, customize ลึกยาก, bundle ใหญ่
  - Redux Toolkit — overkill สำหรับ scope นี้
  - CSS Modules / vanilla-extract — iterate ช้ากว่า Tailwind สำหรับ solo dev + AI
- **Consequences:**
  - ✅ Bundle เล็ก (RSC) → นักวิ่งกลางสนาม load เร็ว
  - ✅ shadcn/ui copy เข้า repo → AI อ่านโค้ดเองได้ 100%
  - ✅ TypeScript + zod + OpenAPI → end-to-end type safety
  - ⚠️ Tailwind v4 ใหม่ — doc/example อาจน้อย → mitigation: shadcn/ui support v4 แล้ว
  - ⚠️ shadcn/ui ต้องอัปเดต component manual (แลกกับ control เต็มที่)
  - ✅ ทุก library เปลี่ยนได้ทีหลังถ้าจำเป็น (state lib, form lib)

---

## D-012 — Pi อัปโหลดผ่าน VPS (ไม่ตรงเข้า R2)

- **Status:** Accepted
- **Date:** 2026-05-28
- **ADR:** [docs/adr/0002-pi-uploads-via-vps.md](docs/adr/0002-pi-uploads-via-vps.md)
- **Context:** Pi อยู่กลางสนาม อาจหาย/โดนขโมย → ห้ามถือ R2 master credential; VPS bandwidth quota เหลือเฟือ
- **Decision:** Pi → FastAPI `/ingest` (multipart streaming) → R2 + enqueue job
- **Alternatives Considered:**
  - Pi → R2 ตรง — security risk + observability แย่
  - Pi → VPS streaming proxy → R2 multipart — complex เกินจำเป็น
- **Consequences:**
  - ✅ Security: Pi key scope จำกัด, revoke ได้ทันที
  - ✅ Single ingress = log/metric/rate-limit ที่เดียว
  - ✅ Pre-validation บน path (size/MIME/duplicate hash)
  - ⚠️ Latency +200ms/รูป, VPS เป็น SPOF (mitigate ด้วย Pi local buffer + retry)
  - ⚠️ Bandwidth ใช้ 2 เท่า (in + out) — รับได้ที่ scale ปัจจุบัน

---

## D-013 — Single AI Worker Process (1 container, 1 RQ worker)

- **Status:** Accepted
- **Date:** 2026-05-28
- **ADR:** [docs/adr/0003-single-ai-worker-process.md](docs/adr/0003-single-ai-worker-process.md)
- **Context:** RAM 2GB ของ CPX11 รับ multi-worker ไม่ไหว (2× 900MB model = OOM); load จริงแค่ 3 รูป/นาที
- **Decision:** 1 RQ worker process ใน 1 container, model preload ตอน boot, mem_limit 1200MB
- **Alternatives Considered:**
  - Multi-worker / multi-container — RAM ชน 2GB
  - Process pool + dispatcher — overkill ที่ scale นี้
- **Consequences:**
  - ✅ RAM safe (~750MB buffer)
  - ✅ ดีบักง่าย, 1 log stream
  - ⚠️ Worker crash = queue ค้าง → mitigate ด้วย Docker restart + RQ retry
  - ⚠️ ถ้าจะเพิ่ม AI model ใหม่ ต้องวัด RAM ใหม่ก่อน
  - ✅ Migration path: อัป VPS เป็น CPX21 (4 vCPU/4GB) แล้ว scale ได้

---

## D-014 — PDPA Photo & Face Embedding Retention Policy

- **Status:** Accepted (consent flow revised 2026-05-28 — partner-side)
- **Revision (2026-05-28):** Consent UI **ย้ายไปฝั่ง partner** (เช่น race-result.asia) ตอนนักวิ่งสมัครงาน — Joggy-PicX ไม่มี consent UI สำหรับ runner เพราะ runner ไม่ login; ดู [ADR-0004](docs/adr/0004-pdpa-retention-policy.md) sect. Consent Flow
- **Date:** 2026-05-28
- **ADR:** [docs/adr/0004-pdpa-retention-policy.md](docs/adr/0004-pdpa-retention-policy.md)
- **Context:** Face embedding = sensitive biometric data; PDPA ม.30 บังคับ self-service erasure; ต้องสมดุล compliance + UX
- **Decision:**
  - รูปต้นฉบับ: 30 วันหลังจบงาน (extend +30 วันได้ 1 ครั้ง)
  - Face embedding: 7 วันหลังจบงาน (สั้นกว่ารูปเพราะใช้แค่ตอน processing)
  - Metadata: เก็บถาวร anonymized (ลบ link bib→identity เมื่อรูปถูกลบ)
  - Opt-in 1 ปี ผ่าน checkbox ตอนสมัคร
  - Right to Erasure self-service ใน dashboard (process ใน 24 ชม.)
- **Alternatives Considered:**
  - Strict (14 วัน / 24 ชม.) — UX แย่
  - Lenient (90 วัน / 30 วัน) — PDPA audit ไม่ผ่าน
- **Consequences:**
  - ✅ PDPA compliant + audit trail
  - ✅ Face embedding สั้น = attack surface ต่ำ
  - ⚠️ Cross-event re-ID ไม่ได้ (face หาย 7 วัน)
  - ⚠️ ต้องมี cron 3 ตัว + audit log + UI consent/erasure
  - ⚠️ R2 lifecycle rule ตั้ง 35 วัน buffer เผื่อ cron พลาด

---

## D-015 — Mobile App = Expo (React Native), defer to Phase 5

- **Status:** Accepted (scope revised 2026-05-28 — photographer-only, no account)
- **Revision (2026-05-28):** Mobile app สำหรับ **Photographer เท่านั้น** ใช้ **Per-Event Upload Token (D-017)** ไม่ register account — ไม่ใช่สำหรับนักวิ่ง
- **Date:** 2026-05-28
- **Context:** Path A (Mobile) สำหรับช่างภาพ (5-20 คน/งาน) — ใช้มือถือถ่ายเสริมกล้องมิเรอร์เลส; AI on-device เป็น nice-to-have
- **Decision:**
  - Stack: **Expo (React Native) + TypeScript**
  - Location: `apps/mobile/` (สร้างใน Phase 5)
  - AI on-device: `react-native-fast-tflite` รัน YOLOv8-nano สำหรับ bib pre-detect; OCR/face ส่ง VPS
  - Distribution: TestFlight + Expo dev build (Phase 5), App Store + Play Store (post-MVP)
- **Alternatives Considered:**
  - PWA — iOS Safari จำกัด (background upload ยาก, camera quality ต่ำกว่า)
  - Native (Swift+Kotlin) — codebase 3 ตัว, ทีม AI ไม่มี expertise
  - ตัดออก — เสีย flexibility ของช่างภาพ
- **Consequences:**
  - ✅ Cursor reuse TypeScript skill
  - ✅ Share `packages/shared/` กับ Next.js (API client, zod schema)
  - ✅ EAS Update OTA — แก้ bug ในงานได้ทันที
  - ⚠️ AI on-device จำกัดกว่า native — แต่พอใช้ pre-detect bib
  - ⚠️ Defer to Phase 5 — Phase 1-4 ไม่ touch mobile
- **Phase 1 action:** ไม่สร้าง code mobile, แต่ `packages/shared/` ต้องออกแบบให้ reuse ได้

---

## D-016 — CI/CD: GitHub Actions + GHCR + Watchtower

- **Status:** Accepted
- **Date:** 2026-05-28
- **ADR:** [docs/adr/0005-cicd-pipeline.md](docs/adr/0005-cicd-pipeline.md)
- **Context:** Monorepo 3 apps, งบ cloud จำกัด, ต้องการ zero-touch deploy + workflow ที่ AI อ่านได้
- **Decision:**
  - **CI:** GitHub Actions free tier + path-filtered workflows
  - **Registry:** GHCR (ฟรี private)
  - **Frontend deploy:** Vercel auto
  - **Backend/Worker deploy:** Watchtower poll ทุก 5 นาที + label-enable + rolling restart
  - **Edge deploy:** Manual ผ่าน Ansible playbook (ก่อนแต่ละงาน)
- **Alternatives Considered:**
  - Self-hosted runner — กิน RAM VPS, security risk
  - Manual SSH deploy — human error
  - Self-host CI (Drone/Gitea) — overkill
- **Consequences:**
  - ✅ ฟรีทั้งหมด, zero-touch backend deploy
  - ✅ Workflows checked in repo → AI ทุกตัวอ่าน + debug ได้
  - ⚠️ GHA 2k นาที — ถ้าเกินอัป Pro ($4/mo, 3k นาที)
  - ⚠️ Watchtower delay สูงสุด 5 นาที — acceptable
  - ⚠️ Edge deploy manual + checklist ก่อนงาน

---

## D-017 — Per-Event Upload Token (Photographer ไม่ลงทะเบียน account)

- **Status:** Accepted
- **Date:** 2026-05-28
- **Context:** ทีม photographer เป็นใครก็ได้ในทีมผู้จัด — ไม่ register account; ต้องมี mechanism กันคนนอก upload + audit
- **Decision:**
  - Admin สร้าง event → generate `event_token` (เช่น `evt_2026marathon_xK9p2`)
  - Token scope: **POST /ingest เฉพาะ event นี้** เท่านั้น (ไม่มี read scope, ไม่ access event อื่น)
  - Token หมดอายุอัตโนมัติเมื่อ `event.end_at` ผ่าน → soft revoke, ลบหลัง 30 วัน
  - หลาย device ใช้ token เดียวกันได้ (Pi + กล้อง + mobile app)
  - Audit log: `(event_token_id, device_id, photo_id, ip, ts)`
- **Alternatives Considered:**
  - Per-device token — Admin register Pi/กล้องทุกตัว → overhead สูง
  - Static shared token — revoke ยาก, security risk
  - LAN-only (ไม่มี auth) — ไม่ผ่าน security baseline
- **Consequences:**
  - ✅ Photographer ไม่ต้อง register
  - ✅ Revoke ทั้ง event ได้ทันที (ถ้า token leak)
  - ⚠️ ถ้า token leak ระหว่าง event → คนนอกอัป photo ได้ → mitigation: rate limit, IP allowlist optional, file content validation
  - ⚠️ ต้องมี UI ใน admin dashboard สำหรับ regenerate token (Phase 2)

---

## D-018 — Multi-Partner Integration: Design-for-3, Build-1 (Pull mode Phase 2)

- **Status:** Accepted
- **Date:** 2026-05-28
- **ADR:** [docs/adr/0006-multi-partner-integration.md](docs/adr/0006-multi-partner-integration.md)
- **Context:** Joggy-PicX เป็น closed system; runner ดูรูปผ่าน External Partner (race-result.asia first-party + อนาคต multi-partner); 3 modes ที่ partner อาจต้องการ: pull/push/embed
- **Decision:**
  - Multi-tenant ตั้งแต่ Phase 1 (concept `Organizer`)
  - Schema reserve `integration_mode ENUM('pull', 'push', 'embed')` ใน Organizer
  - **Phase 2: Build Pull mode เท่านั้น** (race-result.asia ใช้ตัวนี้)
  - Push + Embed mode → Phase 5+
  - Partner API Key scope = Organizer-level, มีหลาย scope (`public:photos:read`, `erasure:write`)
- **Alternatives Considered:**
  - Build 2A+2B จาก Phase 1 — webhook complexity เกิน scope
  - Build all 3 — embed widget = +5-7 วัน, ไม่ทัน timeline
  - Build only Pull no schema reservation — refactor pain ทีหลัง
- **Consequences:**
  - ✅ Forward-compatible — เพิ่ม mode ใหม่ = additive migration
  - ✅ race-result.asia integration ทัน Phase 4
  - ⚠️ Schema มี column ที่ยังไม่ใช้
  - ⚠️ Pull mode = partner ต้อง poll → cache 30s + signed URL expire 1 ชม.

---

## D-019 — Internal User Auth: Supabase Auth + app_users + FastAPI Middleware

- **Status:** Accepted
- **Date:** 2026-05-28
- **Context:** Joggy-PicX = closed system → auth ใช้กับ **Internal User เท่านั้น** (admin + staff); ไม่มี self-signup, ต้อง MFA, ต้องมี invitation flow
- **Decision:**
  - **Identity provider:** Supabase Auth (email/password + TOTP MFA + invitation)
  - **App-level role:** ตาราง `app_users` (FK → `auth.users.id`) ระบุ `role` ('admin' | 'staff') + `scoped_organizer_ids[]` + `scoped_event_ids[]`
  - **Authorization:** FastAPI middleware verify JWT → lookup `app_users` → ตรวจ scope ต่อ request
  - **MFA enforcement:** บังคับ `mfa_enrolled=true` ก่อน access dashboard
  - **Invitation flow:** Admin ใช้ Supabase `admin.inviteUserByEmail()` → Staff ตั้ง password + setup TOTP wizard
  - **Defense in depth:** Supabase RLS เป็น last line (อาจเปิดทีหลัง — Phase 3)
- **Alternatives Considered:**
  - Auth.js (NextAuth) — 2 systems, ไม่ใช้ Supabase ที่เลือกแล้ว
  - Clerk — vendor lock-in, paid เมื่อโต
  - Build from scratch — security risk + time sink
- **Consequences:**
  - ✅ Free tier เพียงพอ (50k MAU + MFA + invitation built-in)
  - ✅ Reuse D-003 (Supabase) — ไม่เพิ่ม dependency
  - ✅ Role/scope logic ใน app-level → AI ทุกตัวอ่าน Python ได้ (RLS เป็น secondary)
  - ⚠️ Onboarding step เพิ่ม (MFA setup ก่อนใช้งาน) → mitigate ด้วย wizard
  - ⚠️ ต้องเขียน invitation UI + email template เอง (Supabase ส่ง email ให้)

---

## D-020 — DB Schema Workflow: Mermaid ER + SQLModel + Alembic + Raw SQL

- **Status:** Accepted
- **Date:** 2026-05-28
- **ADR:** [docs/adr/0007-db-schema-workflow.md](docs/adr/0007-db-schema-workflow.md)
- **Context:** Multi-tenant schema ~11 tables + pgvector + audit/erasure logic; AI 4 ตัวต้องอ่าน schema ตรงกันก่อน implement
- **Decision:**
  - `docs/schema.md` — Mermaid ER (overview สำหรับ review)
  - `apps/backend/joggy/db/models.py` — SQLModel (SSOT)
  - `apps/backend/alembic/versions/` — Alembic + raw SQL สำหรับ pgvector/RLS/trigger
  - `packages/shared/types.ts` — Generated จาก FastAPI OpenAPI
  - Every schema change PR ต้องมี 4 ไฟล์ diff ครบ
- **Alternatives Considered:**
  - Code-first only — ไม่มี overview สำหรับ review
  - Migration-first raw SQL — ต้องเขียน types ซ้ำ
  - ER → SQL → reflect — drift ระหว่าง 3 sources
- **Consequences:**
  - ✅ AI อ่าน Mermaid ก่อน implement → schema clarity
  - ✅ Type safety end-to-end (DB → FastAPI → Frontend)
  - ✅ pgvector/RLS/trigger ใช้ได้ผ่าน raw SQL
  - ⚠️ Mermaid drift risk — phase exit checklist + future auto-gen script
  - ⚠️ 4-step workflow — เขียน runbook ใน `docs/dev-workflow.md`

---

## D-021 — ONNX-Unified Inference Pipeline (AI Worker)

- **Status:** Accepted
- **Date:** 2026-05-28
- **Supersedes:** RAM budget assumption ใน [ADR-0003](docs/adr/0003-single-ai-worker-process.md)
- **Research basis:** [docs/dependency-check.md](docs/dependency-check.md) (Antigravity, 2026-05-28)
- **Context:** Antigravity พบว่า ADR-0003 ประมาณ RAM ผิด — การโหลด 3 frameworks พร้อมกัน (PyTorch สำหรับ YOLO + PaddlePaddle สำหรับ OCR + ONNXRuntime สำหรับ InsightFace) ใช้ **1,100–1,900 MB** จริง ทะลุ `mem_limit: 1200m` ที่ตั้งไว้ใน docker-compose
- **Decision:** Export ทุก AI model เป็น **ONNX format** ก่อน Phase 3 → ใช้ `onnxruntime` เป็น inference engine เดียวในทั้ง production worker
  - YOLOv8-nano → `.onnx` ผ่าน `model.export(format='onnx')` (Ultralytics built-in, 1 คำสั่ง)
  - PaddleOCR → `.onnx` ผ่าน `paddle2onnx` tool (official จาก PaddlePaddle team)
  - InsightFace `buffalo_s` → เป็น ONNX อยู่แล้ว ✅ ไม่ต้อง export
  - Production worker: `import onnxruntime` เท่านั้น — **ห้าม `import torch` หรือ `import paddle`**
  - Dev/export environment: ใช้ torch + paddle ได้เพื่อทำ export script (ไม่ใช่ production)
- **Alternatives Considered:**
  - เดินหน้า multi-framework (ADR-0003 เดิม) แล้วรอ OOM จริง — risk สูงในภาคสนาม
  - อัปเกรด VPS เป็น CPX21 (4 vCPU/4 GB) — เสียเงินเกินจำเป็นก่อนรู้ปัญหา ONNX
  - TorchScript / TensorRT — TorchScript ไม่ลด RAM มาก, TRT ต้องการ GPU
- **Consequences:**
  - ✅ Single inference framework overhead ≈ **100–200 MB** (แทน 3 frameworks ≈ 1,100–1,900 MB)
  - ✅ 3 ONNX models combined ≈ **500–800 MB** → ปลอดภัยใต้ `mem_limit: 1200m` ✅
  - ✅ Docker image เล็กลงมาก (ไม่ต้องติดตั้ง torch 2 GB + paddlepaddle)
  - ✅ ARM64 compatibility ดีขึ้น (onnxruntime มี wheel บน aarch64 ปกติ)
  - ⚠️ ต้องสร้าง export scripts + ทดสอบ accuracy ก่อน Phase 3 เริ่ม
  - ⚠️ Preprocessing code (array format, normalization) อาจต้องปรับเล็กน้อยเพื่อ ONNX session API
  - ⚠️ ต้องเก็บ ONNX model files ใน repo หรือ artifact store — ตัดสินใจ Phase 3

---

## 🟡 Open Questions (ยังไม่ตัดสินใจ — รอผล grill session)

> เหล่านี้คือ decision ที่ต้องชัดก่อนจบ Phase 1 Day 1

| # | Question | Owner | Status |
|---|---|---|---|
| ~~Q1~~ | ~~Repository layout~~ → **Resolved: D-009 (Monorepo)** | Claude + CEO | ✅ Closed 2026-05-28 |
| ~~Q2~~ | ~~Mobile app stack~~ → **Resolved: D-015 (Expo, defer Phase 5)** | Cursor + CEO | ✅ Closed 2026-05-28 |
| ~~Q3~~ | ~~Pi → R2 path~~ → **Resolved: D-012 (ผ่าน VPS)** | Claude + CEO | ✅ Closed 2026-05-28 |
| ~~Q4~~ | ~~AI Worker process model~~ → **Resolved: D-013 (Single worker)** | Claude + CEO | ✅ Closed 2026-05-28 |
| ~~Q5~~ | ~~Photo retention~~ → **Resolved: D-014 (30/7/forever-anon + opt-in 1y + self-service erasure)** | Claude + CEO | ✅ Closed 2026-05-28 |
| ~~Q6~~ | ~~CI/CD~~ → **Resolved: D-016 (GHA + GHCR + Watchtower)** | Codex + CEO | ✅ Closed 2026-05-28 |
| ~~Q7~~ | ~~Package manager (Python)~~ → **Resolved: D-010 (uv)** | Claude + CEO | ✅ Closed 2026-05-28 |
| ~~Q8~~ | ~~Frontend stack confirm~~ → **Resolved: D-011 (Bundle accepted)** | Cursor + CEO | ✅ Closed 2026-05-28 |
| ~~Q9~~ | ~~Authentication scope~~ → **Resolved: D-019 (Supabase Auth สำหรับ Internal User เท่านั้น) + D-017 (Event Token สำหรับ Photographer) + D-018 (Partner API Key สำหรับ External Partner)** | Antigravity + CEO | ✅ Closed 2026-05-28 |
| ~~Q10~~ | ~~DB schema first cut~~ → **Resolved: D-020 (Mermaid ER + SQLModel + Alembic + Raw SQL hybrid)** | Codex + CEO | ✅ Closed 2026-05-28 |

ผล grill session จะอัปเดตคำตอบของแต่ละข้อ + เปลี่ยน status เป็น Accepted + ย้ายขึ้นไปเป็น D-XXX
