# CONTEXT.md — Glossary ของโดเมน Joggy-PicX

> เอกสารนี้คือ **glossary กลาง** ของ project ใช้ตั้งศัพท์ให้ AI ทุกตัวเรียกสิ่งเดียวกันด้วยชื่อเดียวกัน
> ห้ามใส่ implementation detail / decision / spec ในไฟล์นี้ — ใช้สำหรับ terminology เท่านั้น
> ทุกครั้งที่มี term ใหม่ที่ resolve แล้วระหว่าง grill session → เพิ่มในไฟล์นี้ทันที

---

## 1. ขอบเขตของระบบ (System Boundary)

**Joggy-PicX = ระบบปิด (closed/internal system) สำหรับผู้จัดงานเท่านั้น**

- **ใน boundary:** ingestion, AI processing, storage, photo metadata, admin dashboard, partner-facing API
- **นอก boundary:** เว็บผลการแข่งขัน (เช่น race-result.asia) — เป็น **External Partner** ที่ดึงรูปผ่าน API
- **นักวิ่ง (runner) ไม่ใช่ user ของระบบนี้** — ดูรูปผ่าน external partner เท่านั้น

---

## 2. Roles (ผู้ใช้ระบบ)

### Internal User
- ผู้ใช้ที่ login เข้า Joggy-PicX dashboard ได้
- มี 2 subtype:
  - **Admin** — ผู้ดูแลระบบ (สร้าง event, สร้าง user, จัดการ organizer, จัดการรูป)
  - **Staff** — ผู้ใช้ที่ admin สร้างให้ (จำกัด scope: review queue, จัดการรูปเฉพาะ event)
- Login ผ่าน email/password + 2FA
- ทุก Internal User ถูก provision โดย admin เท่านั้น — **ไม่มี self-signup**

### Photographer
- ทีมช่างภาพของผู้จัด — เป็นใครก็ได้ ไม่ register account
- ใช้ **Per-Event Upload Token** ใส่ใน Pi + กล้อง + mobile app ตลอด event
- Token หมดอายุเมื่อ event จบ + ลบจากระบบ
- ไม่ login dashboard, ไม่ดูรูปอื่น — ทำได้แค่ upload

### Runner (นักวิ่ง)
- **ไม่ใช่ user ของ Joggy-PicX**
- ดูรูปตัวเองผ่านเว็บของ External Partner (เช่น race-result.asia) โดยใส่ Bib Number
- Consent ของนักวิ่ง = ฝั่ง partner รับผิดชอบ ไม่ใช่ Joggy-PicX

### CEO
- เจ้าของโปรเจก + super-admin
- รับ feedback + ตัดสินใจขั้นสุดท้าย
- เป็นเจ้าของ race-result.asia (first-party partner)

---

## 3. Organizer & Event Concepts

### Organizer (= Partner)
- ผู้จัดงานวิ่ง / เจ้าของเว็บผลการแข่งขัน
- 1 Organizer มีหลาย Event ได้
- มี **Partner API Key** ของตัวเอง (1 ชุด/organizer) สำหรับเรียก Public Bib Lookup API
- มี `integration_mode` ใน schema: `pull` | `push` | `embed` (Phase 1 ทำแค่ `pull`)
- ตัวอย่าง: **race-result.asia** = first-party organizer (CEO เป็นเจ้าของ)

### Event
- งานวิ่ง 1 ครั้ง (เช่น "Bangkok Marathon 2026")
- belongs to 1 Organizer
- มี `start_at`, `end_at`, `checkpoints[]`, `event_token`
- หลัง `end_at` + 30 วัน → trigger retention cleanup ของรูป

### Checkpoint
- จุดถ่ายรูปในงาน (เช่น "CP-1 km5", "Finish line")
- belongs to 1 Event
- มี location (optional GPS) + name

---

## 4. Auth / Token / Key (3 ชุดที่แยกกัน)

### Internal User Credential
- Email + password + 2FA สำหรับ Internal User login dashboard
- คุมโดย Supabase Auth

### Per-Event Upload Token
- Token ที่ admin สร้างต่อ event สำหรับทีม photographer
- Scope: **POST /ingest เฉพาะ event นี้** เท่านั้น
- หมดอายุอัตโนมัติเมื่อ event จบ
- มีหลาย device ใช้ token เดียวกันได้ (Pi + กล้อง + mobile app)
- Audit log จับคู่ token + device_id

### Partner API Key
- Key ที่ admin สร้างต่อ Organizer สำหรับเรียก Public Bib Lookup API
- Scope: **GET /v1/public/photos** ของ event ที่เป็นของ organizer นั้นเท่านั้น
- Rate limit ต่อ key
- Revoke ได้

---

## 5. Photo & Pipeline

### Photo
- รูปต้นฉบับ 1 รูป ที่อัปขึ้นระบบ
- มี `event_id`, `checkpoint_id`, `captured_at`, `device_id`
- มี `original_url` (R2) + `thumbnail_url` (R2)
- มี retention metadata (`retention_until`)

### Bib Number
- เลขประจำตัวนักวิ่งในงาน — string (อาจมี prefix เช่น "A123")
- ผูกกับ Photo ผ่าน AI Pipeline (OCR + optional Re-ID)

### Face Embedding
- 512-dim vector จาก InsightFace สำหรับ Cross-Checkpoint Re-ID
- เก็บใน pgvector
- Retention 7 วันหลัง event จบ (D-014)

### AI Pipeline
- กระบวนการประมวลผลรูป 1 รูป:
  1. YOLOv8-nano detect (bib + person box)
  2. PaddleOCR อ่าน bib
  3. InsightFace embed face → vector
  4. Gender detect
  5. Cross-Checkpoint Re-ID match
- รัน async ผ่าน Redis + Python-RQ

### Cross-Checkpoint Re-ID
- เทคนิคจับคู่รูปข้าม checkpoint ด้วย face vector
- ใช้เมื่อ OCR อ่าน bib ไม่ออกที่ checkpoint หนึ่ง แต่อ่านได้ที่อีก checkpoint
- Cosine similarity > 0.85 ถือว่า match

### Manual Review Queue
- คิวของรูปที่ AI confidence ต่ำ → Internal User ตรวจสอบ + approve/reject

---

## 6. Integration Modes (Partner ↔ Joggy-PicX)

### Pull Mode (`pull`)
- Partner เรียก **Public Bib Lookup API** ของ Joggy-PicX
- `GET /v1/public/photos?bib=42&event_id=...` พร้อม Partner API Key
- Response: list ของ signed URL (expire ~1 ชม.)
- **Phase 1: implement mode นี้เป็น default**

### Push Mode (`push`) — Reserved
- Joggy-PicX ยิง webhook ไปยัง partner เมื่อรูปใหม่ process เสร็จ
- ต้องมี webhook subscription + HMAC signature + retry queue
- Phase 5+

### Embed Mode (`embed`) — Reserved
- Joggy-PicX provide JS SDK + iframe widget
- Partner แค่ฝัง snippet ในหน้าเว็บผลการแข่งขัน
- Phase 5+

---

## 7. PDPA Terms

### Consent
- ความยินยอมของนักวิ่งให้เก็บรูป + face embedding
- **เก็บฝั่ง partner** (race-result.asia) ตอนนักวิ่งสมัครงาน — ไม่ใช่ใน Joggy-PicX
- Partner ส่ง consent flag มาตอน create event (per-event basis)

### Right to Erasure
- สิทธิ์ของนักวิ่งในการลบข้อมูล (PDPA ม.30)
- นักวิ่งใช้สิทธิ์ผ่าน partner → partner เรียก Joggy-PicX API `DELETE /v1/erasure?bib=X&event_id=Y`
- Joggy-PicX ลบรูป + embedding + anonymize metadata ใน 24 ชม.

### Retention Cleanup
- Cron job ลบข้อมูลที่เกิน retention period (ดู D-014)

---

## 8. คำที่ไม่ใช้แล้ว / สับสนง่าย

| ❌ ห้ามใช้ | ✅ ใช้แทน | เหตุผล |
|---|---|---|
| "นักวิ่ง dashboard" | "External partner integration" | นักวิ่งไม่ login Joggy-PicX |
| "Runner login" | (ไม่มี) | Runner ไม่ใช่ user ของระบบนี้ |
| "User signup" | "Admin provision Internal User" | ไม่มี self-signup |
| "Photographer account" | "Per-event Upload Token" | Photographer ไม่ register |
| "Race results" / "ผลการแข่ง" (ในระบบ Joggy-PicX) | External system — partner รับผิดชอบ | Joggy-PicX ไม่เก็บผลการแข่งขัน |
| "Public consent UI" (ใน Joggy-PicX) | "Partner-side consent" | Consent อยู่ฝั่ง partner |

---

## 9. Update Policy

- เพิ่ม term ใหม่ทุกครั้งที่ resolve ใน grill session
- ถ้าเปลี่ยน meaning ของ term เดิม → mark **superseded** ในส่วน 8 + อธิบายเหตุผลใน DECISIONS.md
- ห้ามมี implementation/code ใน CONTEXT.md
