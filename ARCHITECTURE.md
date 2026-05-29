# ARCHITECTURE.md — Blueprint ระบบ Joggy-PicX

> สถานะ: Draft v0.1 (Phase 1 Day 1)
> เป้าหมาย: เอกสารกลางที่ AI ทุกตัวอ่านแล้วเห็นภาพระบบทั้งหมดในหน้าเดียว
> ทุก decision สำคัญที่ทำให้ design นี้เป็นแบบนี้ ดูที่ [DECISIONS.md](DECISIONS.md)

---

## 1. ภาพรวมระบบ

**Joggy-PicX** = ระบบปิด (closed/internal) สำหรับผู้จัดงานวิ่ง — ถ่ายรูป + process ด้วย AI + serve รูปผ่าน API ให้ External Partner

- **ระบบเป็น closed/internal** — runner (นักวิ่ง) **ไม่ใช่ user** ของ Joggy-PicX
- รูปถ่ายเข้าระบบได้ **3 ทาง** (Mobile / Mirrorless Manual / Mirrorless Auto-trigger)
- ระบบใช้ AI ทำ Bib OCR + Face Embedding + Cross-Checkpoint Re-ID
- **External Partner** (เช่น race-result.asia) ดึงรูปผ่าน Public API ด้วยเลขบิบ
- **Internal User** (Admin/Staff) ใช้ dashboard สำหรับ manual review + จัดการ event/organizer
- **Multi-partner ตั้งแต่แรก** (D-018) — race-result.asia เป็น first-party + รองรับ partner เจ้าอื่นในอนาคต
- **Scale เป้าหมาย:** ~1,000 รูป/งาน, ~1,000 นักวิ่ง/งาน, งบ cloud ~$6–7/เดือน

> Glossary ของ domain → [CONTEXT.md](CONTEXT.md)

---

## 2. Data Flow Diagram (Text-based)

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          INGESTION LAYER (3 paths)                       │
└──────────────────────────────────────────────────────────────────────────┘

  Path A: Mobile App                    Path B: Mirrorless (Manual)            Path C: Mirrorless (Auto-trigger)
  ─────────────────                     ───────────────────────────            ─────────────────────────────────
  iOS/Android                            Canon EOS RP                           Canon EOS RP + Pi sensor
       │                                      │                                       │
       │ AI on-device                         │ USB-C Tether (gphoto2)                │ USB-C Tether (gphoto2)
       │ (compress + tag)                     │ [หรือ WiFi PTP/IP backup]             │ + Pi YOLO motion trigger
       ▼                                      ▼                                       ▼
   HTTPS upload                       Raspberry Pi 5 (gphoto2 + watchdog) ◄────── Pi trigger camera shutter
                                      [⚠️ Canon EOS RP ไม่มี FTP — D-002 revised]
       │                                      │
       │                                      │ Python watchdog uploader
       │                                      ▼
       └──────────────┬─► FastAPI /ingest (VPS) ──► Cloudflare R2 (photos bucket) ──┐
                      │     (D-012: Pi ไม่อัปตรง R2)                                 │
                      │                                                              │
                      │ enqueue R2 key + metadata เข้า Redis queue                   │
                      ▼                                                              │
┌──────────────────────────────────────────────────────────────────────────┐         │
│                         PROCESSING LAYER (Hetzner CPX11)                 │         │
│                                                                          │         │
│   FastAPI (REST API) ──► Redis ──► Python-RQ Worker ──► AI Pipeline      │         │
│        │                                  │                              │         │
│        │                                  ▼                              │         │
│        │                          ┌───────────────────────┐              │         │
│        │                          │ 1. YOLOv8-nano detect │              │         │
│        │                          │    (bib + person)     │              │         │
│        │                          │ 2. PaddleOCR read bib │              │         │
│        │                          │ 3. InsightFace embed  │              │         │
│        │                          │    (512-dim vector)   │              │         │
│        │                          │ 4. Gender detect      │              │         │
│        │                          │ 5. Cross-checkpoint   │              │         │
│        │                          │    Re-ID match        │              │         │
│        │                          └───────────────────────┘              │         │
│        │                                  │                              │         │
│        │                                  ▼                              │         │
│        │                       ถ้า confidence ต่ำ → Manual Review Queue   │         │
│        ▼                                                                 │         │
│   Nginx (reverse proxy + rate limit)                                     │         │
└──────────────────────────────────────────────────────────────────────────┘         │
                      │                                                              │
                      │ INSERT/UPDATE metadata                                       │
                      ▼                                                              │
              ┌───────────────────────────┐                                          │
              │ Supabase (PostgreSQL +    │                                          │
              │ pgvector for face vec)    │                                          │
              └───────────────────────────┘                                          │
                      ▲                                                              │
                      │ Query (bib / face vector)                                    │
                      │                                                              │
┌──────────────────────────────────────────────────────────────────────────┐         │
│            PRESENTATION + INTEGRATION LAYER                              │         │
│                                                                          │         │
│  A) Internal Dashboard (Next.js / Vercel)                                │         │
│     ↑ login email/password + 2FA                                         │         │
│     Admin / Staff (Internal User เท่านั้น — ไม่ใช่ runner)                   │         │
│     - manual review queue, จัดการ event/organizer/user                    │         │
│                                                                          │         │
│  B) Public API for Partners ◄───────────────────────────────────────────┼─────────┘
│     ↑ Authorization: Bearer <partner_api_key>  (per-Organizer scope)     │
│     GET  /v1/public/photos?bib=&event_id=  → signed URL (expire 1h)      │
│     DELETE /v1/erasure                     → enqueue erasure job         │
│     External Partner: race-result.asia + อื่น ๆ                           │
│     (partner แสดงรูปให้ runner ค้นด้วยเลขบิบในเว็บของตัวเอง)                  │
│                                                                          │
│  C) Photographer Upload (Phase 1 = Pi; Phase 5 = Mobile app)             │
│     ↑ Authorization: Bearer <event_token>  (per-Event scope, POST only)  │
│     Photographer ไม่มี account — ใช้ Per-Event Upload Token (D-017)         │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Layer Breakdown

### 3.1 Edge / Ingestion Layer

| Component | Role | Note |
|---|---|---|
| **Canon EOS RP** | Mirrorless camera | WiFi FTP เท่านั้น (จำกัด: ข้าม WAN ไม่ได้) |
| **Raspberry Pi 5** | Edge ingestion gateway | REQUIREMENT ไม่ใช่ optional |
| **gphoto2 (บน Pi)** | รับรูปจาก Canon ผ่าน USB tether หรือ WiFi PTP/IP | Path A: USB-C; Path C: WiFi PTP/IP [D-002 revised] |
| **Python watchdog uploader (บน Pi)** | Hook script จาก gphoto2 → upload R2 | Async, retry, queue-based |
| **Mobile app (iOS/Android)** | ถ่ายรูป + AI on-device + upload | ไม่ผ่าน Pi |

### 3.2 Storage Layer

| Component | Role | Tier |
|---|---|---|
| **Cloudflare R2** | Object storage (รูปต้นฉบับ + thumbnail) | Free 10GB, ไม่มี egress fee |
| **Supabase PostgreSQL** | Metadata + user data | Free 500MB |
| **Supabase pgvector** | Face embedding (512-dim) | extension ของ Postgres |

### 3.3 Compute / Processing Layer (Hetzner CPX11 ~$5.50/เดือน)

| Service | Role |
|---|---|
| **Nginx** | Reverse proxy + rate limit + TLS termination |
| **FastAPI** | REST API + auth + business logic |
| **Redis** | Queue broker (สำหรับ Python-RQ) |
| **Python-RQ Worker** | Async job processor |
| **AI Worker** | YOLOv8 + PaddleOCR + InsightFace (CPU-only) |
| **vsftpd** | (Optional) ถ้า Pi ส่งตรงเข้า VPS แทน R2 — ไม่ใช้ default flow |

ทั้งหมดรันใน Docker Compose all-in-one (1 VPS, container แยก, network ภายใน)

### 3.4 Presentation + Integration Layer

| Component | Role | Audience | Tier |
|---|---|---|---|
| **Next.js Internal Dashboard** | Admin/Staff tool: review, manage events/organizers/users | Internal User เท่านั้น | Vercel free tier |
| **Public API (FastAPI)** | Partner-facing endpoint: `/v1/public/photos`, `/v1/erasure` | External Partner (race-result.asia + อื่น ๆ) | บน VPS |
| **Photographer Mobile App** | Upload-only (Phase 5) | Photographer (no account) | Expo / EAS Update |
| **Supabase Auth** | Auth สำหรับ Internal User เท่านั้น | Internal User | Free tier |

> Runner (นักวิ่ง) ไม่ใช่ user ของ Joggy-PicX — ดูรูปผ่าน partner ด้วยเลขบิบ

---

## 4. ฟีเจอร์ AI Pipeline

### 4.1 Bib OCR
- Input: รูปต้นฉบับ
- Step 1: YOLOv8-nano detect bib box (bounding box)
- Step 2: Crop bib region → PaddleOCR อ่านตัวเลข
- Output: `bib_number` + `bib_confidence`
- Fallback: ถ้า confidence < threshold → ส่ง Manual Review Queue

### 4.2 Gender Detection
- Run บน person bounding box จาก YOLO
- Output: `gender` (`male` / `female` / `unknown`) + `confidence`
- ใช้สำหรับ filter ใน dashboard

### 4.3 Face Embedding (InsightFace)
- Detect face → align → embed เป็น 512-dim vector
- เก็บใน Supabase pgvector
- ใช้สำหรับ Cross-Checkpoint Re-ID + Face Search

### 4.4 Cross-Checkpoint Re-ID
- Scenario: นักวิ่งคนหนึ่งถ่ายติดที่ checkpoint A (bib ถูกบัง) + checkpoint B (เห็น bib)
- วิธี:
  1. รูปจุด B อ่าน bib สำเร็จ → ได้ `bib_number` + `face_vector_B`
  2. รูปจุด A อ่าน bib ไม่ได้ แต่มี `face_vector_A`
  3. Query: `face_vector_A` cosine similarity `face_vector_B` > 0.85 → match
  4. Assign `bib_number` ให้รูปจุด A ด้วย
- ผลลัพธ์: นักวิ่งค้นรูปจุด A ได้ทั้งที่ AI อ่าน bib ไม่ออก

### 4.5 Manual Review Queue
- รูปที่ AI confidence ต่ำ → ส่งเข้า queue
- Admin/staff review ผ่าน UI
- รับ/ปฏิเสธ → update DB

---

## 5. Tech Stack & Rationale

| Layer | Choice | เหตุผล | Decision Ref |
|---|---|---|---|
| VPS | Hetzner CPX11 (~$5.50/เดือน) | ราคาดีสุด, RAM 2GB พอสำหรับ CPU AI | [DECISIONS.md#D-001] |
| Container | Docker Compose all-in-one | Solo dev, deploy ง่าย, debug ง่าย | [DECISIONS.md#D-001] |
| Storage | Cloudflare R2 | ฟรี 10GB + ไม่มี egress fee | [DECISIONS.md#D-005] |
| DB | Supabase free tier | Postgres + pgvector + Auth + free | [DECISIONS.md#D-003] |
| Vector DB | pgvector (ภายใน Postgres) | ไม่ต้อง infra เพิ่ม, scale พอสำหรับ ~1,000 vector | [DECISIONS.md#D-003] |
| Queue | Redis + Python-RQ | Lightweight, Python-native | [DECISIONS.md#D-006] |
| API | FastAPI | Async, type-hint, OpenAPI auto | — |
| Frontend | Next.js (App Router) + Vercel | Free tier, SSR, image optimization | — |
| Edge | Raspberry Pi 5 + vsftpd + Python watchdog | Canon FTP ข้าม WAN ไม่ได้ → ต้องมี LAN gateway | [DECISIONS.md#D-002] |
| AI | YOLOv8-nano + PaddleOCR + InsightFace | CPU-only เริ่ม, ค่อยอัปเป็น GPU ถ้าจำเป็น | [DECISIONS.md#D-004] |

---

## 6. ความเสี่ยงด้าน Architecture

| # | ความเสี่ยง | Mitigation |
|---|---|---|
| R1 | Canon FTP ข้าม WAN ไม่ได้ | Pi เป็น REQUIREMENT |
| R2 | Bib OCR accuracy ต่ำในสนามจริง | Fallback ไป Face Re-ID + Manual Review |
| R3 | InsightFace dependency บน Linux | Pin version + Dockerfile ที่ test แล้ว |
| R4 | กล้อง/Pi แบตหมดกลางงาน | Dummy battery + UPS portable |
| R5 | NTP sync ผิด → re-ID พัง | Pi sync NTP + log timestamp ทุก device |
| R6 | PDPA — face embedding | Consent flow + auto-delete หลัง 30 วัน |
| R7 | Hetzner outage | Backup R2 (รูป) + Supabase auto-backup (metadata) |
| R8 | Cloudflare R2 quota เต็ม | Monitor + cleanup รูป >30 วัน |

---

## 7. Repository Layout (D-009 / ADR-0001)

```
Joggy-PicX/
├── apps/
│   ├── backend/      # FastAPI + Worker (Python)
│   ├── frontend/     # Next.js (TypeScript)
│   └── edge/         # Pi watchdog uploader (Python)
├── packages/
│   └── shared/       # OpenAPI types + constants
├── infra/
│   ├── docker-compose.yml
│   ├── nginx/
│   └── pi/           # Pi provisioning scripts
├── docs/
│   ├── adr/          # Architecture Decision Records
│   └── ...
├── .github/workflows/  # CI/CD (path-filtered)
└── (root docs)         # CLAUDE.md, AGENTS.md, ARCHITECTURE.md, ...
```

ดูเหตุผลเต็มที่ [ADR-0001](docs/adr/0001-monorepo-layout.md)

---

## 8. ส่วนที่ยังไม่ตัดสินใจ (Open Questions)

ดู [DECISIONS.md](DECISIONS.md) ส่วน "Open Questions" สำหรับรายการเต็ม

ที่ควรชัดก่อนเริ่ม Phase 1 Day 1:
- [ ] Repository layout — monorepo หรือ multi-repo
- [ ] Mobile app stack — Native, Expo, หรือ PWA
- [ ] Pi → R2 path — Pi upload ตรงไป R2 หรือผ่าน VPS
- [ ] AI Worker process model — separate container หรือ ใน FastAPI worker
- [ ] Photo retention policy — รูปเก็บกี่วัน, ใครลบได้บ้าง
- [ ] CI/CD — GitHub Actions free tier พอหรือไม่
