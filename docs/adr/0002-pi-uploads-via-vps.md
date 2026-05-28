# ADR-0002 — Pi อัปโหลดผ่าน VPS (ไม่อัปตรงเข้า R2)

- **Status:** Accepted
- **Date:** 2026-05-28
- **Deciders:** CEO + Claude (Tech Lead)
- **Related:** [DECISIONS.md#D-012](../../DECISIONS.md), [ADR-0001](0001-monorepo-layout.md)

---

## 1. Context

ข้อมูลรูปจาก Canon EOS RP เข้าระบบผ่าน Raspberry Pi 5 (LAN FTP) แล้วต้องเดินทางต่อไปยัง Cloudflare R2 และ Supabase metadata

ปริมาณ data ต่องาน:
- ~1,000 รูป × ~5 MB = ~5 GB ขาเข้า
- Hetzner CPX11 bandwidth quota = 20 TB/เดือน → ใช้ <0.1% ต่องาน

Pi ทำงานในสนามจริง (กลางทาง, อาจหาย/โดนขโมย/แบตหมด)
VPS = single Hetzner CPX11 with Docker Compose all-in-one

## 2. Decision

**Path:** Pi → VPS (FastAPI `/ingest`) → R2 + enqueue job

- Pi ถือ **API key เฉพาะ ingestion endpoint** (scope จำกัด: `POST /ingest` เท่านั้น)
- API key หมุนทุก 30 วันผ่าน Ansible/provisioning script
- Pi → VPS ใช้ `multipart/form-data` + `Connection: keep-alive`
- FastAPI ใช้ `UploadFile` streaming → ไม่ buffer เต็มไฟล์เข้า RAM
- หลังรับครบ → FastAPI upload R2 + enqueue RQ job + return 200
- Pi มี **local SD-card buffer + retry queue** (SQLite) เก็บ failed upload ส่งซ้ำเมื่อ VPS reachable

## 3. Alternatives Considered

### Option A — Pi → R2 ตรง (boto3 บน Pi)
- ✅ Latency ต่ำสุด, รูปขึ้น cloud เร็ว
- ❌ **Security risk สูง:** Pi อยู่กลางสนาม ถ้า Pi หาย/โดนขโมย และ credential เป็น master key ของ bucket → ทั้ง bucket อ่าน/เขียน/ลบได้
- ❌ ต้อง R2 Event Notification → Cloudflare Worker → VPS webhook (เพิ่มจุดล้ม)
- ❌ Observability แย่ — log อยู่กระจาย Pi vs Cloudflare vs VPS

### Option C — Pi → VPS streaming proxy → R2 multipart
- ✅ Credential ปลอดภัย + ทำ AI pre-check ได้บน path
- ❌ Complex มาก — multipart streaming ฝั่ง upstream + downstream sync ยาก
- ❌ Error handling ตอน R2 fail กลางคัน buffer ที่ค้างต้อง cleanup

## 4. Consequences

### Positive
- **Security** — Pi ถือ key scope จำกัด, revoke ได้ทันทีเมื่อ Pi หาย
- **Single ingress point** — log, metric, rate limit, error ทั้งหมดที่ FastAPI ตัวเดียว
- **Pre-validation** — VPS ตรวจ size / MIME / duplicate hash / EXIF GPS ก่อนเปลือง R2 storage
- **Enqueue job ตรงเลย** — flow control ตรงไปตรงมา ไม่ต้อง webhook
- **VPS quota เหลือเฟือ** — ใช้ <0.1% ต่องาน

### Negative / Tradeoffs ที่ต้องรับ
- Latency +200ms/รูป (รับได้ในงาน ~3 รูป/นาที)
- VPS เป็น single point of failure ใน ingestion path
  - **Mitigation:** Pi local buffer (SQLite + SD-card) + retry queue
- VPS RAM 2GB → ต้องคุมจำนวน concurrent upload
  - **Mitigation:** Nginx `client_max_body_size`, FastAPI semaphore กำหนด ≤10 concurrent
- Bandwidth ใช้ 2 เท่า (เข้า VPS + ออกไป R2) — รับได้ที่ scale ปัจจุบัน

### Reversibility
- Hard-to-reverse ระดับกลาง — ถ้าจะย้ายเป็น Pi→R2 ตรงทีหลัง ต้อง:
  - สร้าง scoped IAM/credential บน R2
  - Setup R2 Event Notification → Worker → VPS
  - Refactor ingestion flow บน Pi
- **เพราะฉะนั้นเลือกตอนนี้ และ commit ไป Option B**

## 5. Rules ที่ตามมาจาก decision นี้

1. R2 credential **ห้ามอยู่บน Pi** — มีแค่บน VPS เท่านั้น
2. Pi ต้องมี **API key เฉพาะ ingestion** (1 endpoint, POST เท่านั้น, ไม่มี READ access)
3. FastAPI `/ingest` endpoint:
   - Rate limit ต่อ Pi (เผื่อ key leak)
   - Validate: file size ≤10 MB, MIME ∈ {jpeg, png, raw}, duplicate hash (sha256) ตรวจกับ DB
   - Stream → R2 → enqueue job → return 200 (อย่ารอ AI inference เสร็จ)
4. Pi uploader ต้อง:
   - มี local SQLite queue สำหรับ failed upload
   - Retry exponential backoff (1s, 2s, 4s, 8s, max 60s)
   - Log timestamp ของรูป (สำหรับ NTP cross-check)
5. API key rotation policy: ทุก 30 วัน, ผ่าน Ansible playbook (ยังไม่ implement ใน Phase 1)
