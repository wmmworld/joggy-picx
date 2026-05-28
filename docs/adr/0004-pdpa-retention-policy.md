# ADR-0004 — Photo / Face Embedding Retention Policy (PDPA-Compliant)

- **Status:** Accepted
- **Date:** 2026-05-28
- **Deciders:** CEO + Claude (Tech Lead)
- **Related:** [DECISIONS.md#D-014](../../DECISIONS.md)
- **Legal basis:** พ.ร.บ. คุ้มครองข้อมูลส่วนบุคคล พ.ศ. 2562 (PDPA), มาตรา 30 (สิทธิของเจ้าของข้อมูล)

---

## 1. Context

ระบบ Joggy-PicX เก็บข้อมูลส่วนบุคคล 3 ประเภทที่อยู่ภายใต้ PDPA:

| Data Type | Category | ความเสี่ยง |
|---|---|---|
| รูปต้นฉบับ (R2) | Personal data | ระบุตัวตนได้, อาจมี GPS EXIF |
| Face embedding (pgvector 512-dim) | **Sensitive biometric data** | ใช้ระบุตัวบุคคลซ้ำได้, attack surface สูง |
| Metadata (bib, checkpoint time) | Quasi-identifier | anonymized แล้วเป็น analytics data |

ต้องสมดุล:
- **PDPA compliance** — มี retention ชัดเจน + auto-delete + right to erasure
- **Business value** — นักวิ่งดาวน์โหลดรูปได้ทันงาน + ค้นรูปย้อนหลังได้
- **Cost** — R2 ฟรี 10GB จำกัด

## 2. Decision

### Retention Policy (default)

| Data | Retention | Trigger | Notes |
|---|---|---|---|
| รูปต้นฉบับ (R2) | **30 วันหลังจบงาน** | `event.end_at + 30d` | ผู้ใช้ extend +30 วันได้ 1 ครั้งผ่าน dashboard |
| Thumbnail (R2) | 30 วันหลังจบงาน | เหมือนรูปต้นฉบับ | |
| **Face embedding** (pgvector) | **7 วันหลังจบงาน** | `event.end_at + 7d` | ลบเร็วกว่ารูป เพราะใช้แค่ตอน processing |
| Metadata (bib/time/checkpoint) | **เก็บถาวร — anonymized** | ลบ link `bib → identity` เมื่อรูปถูกลบ | ใช้เป็น analytics |
| Consent record | 5 ปีตามกฎหมาย | PDPA audit | log การ consent + revoke |
| Audit log (delete events) | 1 ปี | PDPA compliance | who, what, when, why |

### Consent Flow — **อยู่ฝั่ง External Partner ไม่ใช่ Joggy-PicX**

> **สำคัญ:** นักวิ่งไม่ login Joggy-PicX → ไม่มี consent UI ในระบบนี้
> Consent อยู่ฝั่ง partner (เช่น race-result.asia) ตอนนักวิ่งสมัครงาน

- Partner รับผิดชอบ:
  - แสดง consent screen ตอนนักวิ่งสมัครงาน
  - เก็บ consent record (PDPA audit ของ partner)
  - ส่ง consent flag มาที่ Joggy-PicX **ตอน create event** หรือ **ผ่าน per-runner registration API** (Phase 2+)
- Joggy-PicX รับผิดชอบ:
  - เก็บ retention metadata + enforce auto-delete
  - Provide audit log สำหรับ partner ดึง
  - Process erasure request ที่ partner ส่งมา

### Opt-in (Extended Retention)
- Partner ส่ง flag `opt_in_extended_retention=true` มาด้วยตอน register runner ใน event
- ถ้า opt-in → retention เปลี่ยนเป็น 365 วัน
- Default = false (30 วัน standard)

### Right to Erasure — **ผ่าน Partner API**

- นักวิ่งใช้สิทธิ์ผ่าน partner UI (race-result.asia เป็นต้น)
- Partner เรียก Joggy-PicX API:
  ```
  DELETE /v1/erasure
  Body: { bib: "42", event_id: "evt_xxx", reason: "user_request" }
  Headers: Authorization: Bearer <partner_api_key>
  ```
- Joggy-PicX ลบใน 24 ชม.:
  - รูปต้นฉบับ + thumbnail บน R2
  - Face embedding ใน pgvector
  - Anonymize link `bib → identity` (metadata เก็บไว้ไม่มี PII)
- ส่ง confirmation webhook กลับ partner เมื่อเสร็จ (Phase 5+; Phase 2 ใช้ polling status)

### Implementation
- **Cron jobs** (run บน VPS, ทุกวันเที่ยงคืน ICT):
  1. `delete_expired_photos` — ลบรูปที่เกิน retention จาก R2
  2. `delete_expired_face_embeddings` — ลบ embedding ที่เกิน retention
  3. `anonymize_expired_metadata` — แทน link bib→identity ด้วย hash
- **On-demand erasure queue** — RQ job process ลบใน 24 ชม. หลัง user request

## 3. Alternatives Considered

### Strict (รูป 14 วัน, face 24 ชม.)
- ✅ PDPA risk ต่ำสุด
- ❌ นักวิ่งบางคนยังไม่ทันดาวน์โหลด
- ❌ ขายรูปหลังงานไม่ทัน (business value)

### Lenient (รูป 90 วัน, face 30 วัน, no auto-delete)
- ✅ Business friendly
- ❌ PDPA audit ไม่ผ่าน — เก็บนานเกินจำเป็น
- ❌ R2 ฟรี tier เต็มไว

### No-tier (เก็บถาวรถ้า opt-in, ลบทันทีถ้า opt-out)
- ❌ Binary มากเกินไป — ผู้ใช้ทั่วไปไม่ opt-in → ลบทันทีไม่มีโอกาสดาวน์โหลด

## 4. Consequences

### Positive
- PDPA compliant — retention ชัดเจน + audit trail
- นักวิ่งมีเวลา 30 วันสบายๆ ดาวน์โหลด
- Face embedding สั้น → attack surface ต่ำถ้า DB leak
- Metadata anonymized = analytics data ใช้ปรับปรุงระบบได้

### Negative / Tradeoffs ที่ต้องรับ
- **Face embedding หาย 7 วัน** → จัดงานซ้ำ + ใช้ cross-event re-ID ไม่ได้ (ต้อง re-embed)
- Cron jobs 3 ตัว — ต้อง monitor + retry mechanism
- Audit log = พื้นที่ DB เพิ่ม (เล็กน้อย ~1KB/event)
- UI consent + erasure ต้องเขียนให้ user เข้าใจ — รับผิดชอบ Cursor

### Reversibility
- Retention period เพิ่มได้ → ทำได้ทันที (เปลี่ยนค่า config)
- Retention period ลดได้ → ทำได้ แต่ลบข้อมูลที่ user คาดว่ายังอยู่ = trust risk
- **เพราะฉะนั้นเลือก default ที่ "เผื่อนาน" + ให้สิทธิ์ลบเองได้**

## 5. Rules ที่ตามมาจาก decision นี้

1. ทุก table ที่มี personal data ต้องมี column `retention_until: TIMESTAMP`
2. Cron job `delete_expired_*` ห้าม fail silently — มี alert (email/Discord webhook) ถ้า error
3. Audit log ต้องบันทึก: `actor` (system/user), `action` (delete/anonymize/erase_request), `target_id`, `reason`, `timestamp`
4. Consent record ต้องเก็บ **version ของ policy text** ที่ user เห็นตอนกด — ถ้า policy เปลี่ยน user ต้อง re-consent
5. ห้ามมี endpoint ที่ return face embedding (พื้นที่ user) — ใช้ภายในระบบเท่านั้น
6. รูปและ embedding ลบจริง (hard delete) ไม่ใช่ soft delete (PDPA ต้อง "ลบจริง")
7. R2 lifecycle rule ตั้ง expiration เผื่อ cron พลาด → 35 วัน (5 วัน buffer)
8. ก่อน production ครั้งแรก ต้องมี:
   - Privacy Policy ของ Joggy-PicX (สำหรับ Internal User dashboard) เขียนตาม PDPA
   - **Data Processing Agreement (DPA) กับแต่ละ Organizer** — ระบุ role ว่า Joggy-PicX = "Data Processor", Organizer = "Data Controller"
   - Partner integration guide: วิธีส่ง consent flag, วิธีเรียก Erasure API
   - Audit log ที่ partner ดึงได้ (สำหรับ partner audit PDPA)
9. **Joggy-PicX ไม่มี consent UI สำหรับ runner** — ห้ามเพิ่ม Cursor: ดูข้อ 4 ของ Rules นี้
