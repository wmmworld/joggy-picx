# Database Schema — Joggy-PicX

> Living document — Mermaid ER diagram + คำอธิบาย table ทั้งหมด
> Source of Truth = `apps/backend/joggy/db/models.py` (SQLModel) ตาม [ADR-0007](adr/0007-db-schema-workflow.md)
> ไฟล์นี้ใช้สำหรับ **overview + review** — AI ทุกตัวอ่านก่อน implement
> อัปเดตทุกครั้งที่ schema change (บังคับใน Phase exit checklist)

วันที่อัปเดตล่าสุด: 2026-05-28 (Phase 1 Day 2 — initial draft)

---

## 1. ER Diagram (Mermaid)

```mermaid
erDiagram
    organizers ||--o{ events : "has many"
    organizers ||--o{ partner_api_keys : "has many"
    organizers ||--o{ app_user_organizer_scope : "scoped staff"

    events ||--o{ checkpoints : "has many"
    events ||--o{ photos : "has many"
    events ||--o{ event_tokens : "has many"
    events ||--o{ consent_records : "tracks runners"
    events ||--o{ app_user_event_scope : "scoped staff"

    checkpoints ||--o{ photos : "tagged at"

    photos ||--o{ face_embeddings : "1..N faces detected"
    photos ||--o| review_queue : "if low confidence"
    photos ||--o{ audit_logs : "actions logged"

    event_tokens ||--o{ photos : "uploaded by"

    app_users ||--o{ app_user_organizer_scope : "limits to"
    app_users ||--o{ app_user_event_scope : "limits to"
    app_users ||--o{ audit_logs : "actor"

    consent_records ||--o| erasure_requests : "1..1 if requested"
    erasure_requests ||--o{ audit_logs : "tracked"

    organizers {
        UUID id PK
        TEXT name
        TEXT contact_email
        TEXT integration_mode "pull|push|embed"
        JSONB pull_config
        JSONB push_config "reserved Phase 5+"
        JSONB embed_config "reserved Phase 5+"
        TIMESTAMP created_at
    }

    events {
        UUID id PK
        UUID organizer_id FK
        TEXT name
        TIMESTAMP start_at
        TIMESTAMP end_at
        TEXT status "planned|active|completed|archived"
        JSONB allowed_origins
        TIMESTAMP retention_until "computed"
        TIMESTAMP created_at
    }

    checkpoints {
        UUID id PK
        UUID event_id FK
        TEXT name
        TEXT kind "start|km5|km10|finish|other"
        NUMERIC lat
        NUMERIC lng
        INT seq_order
    }

    photos {
        UUID id PK
        UUID event_id FK
        UUID checkpoint_id FK_nullable
        UUID uploaded_by_event_token_id FK
        TEXT device_id "Pi serial, mobile UUID"
        TEXT r2_key_original
        TEXT r2_key_thumbnail
        TEXT sha256
        TEXT mime_type
        INT width
        INT height
        TIMESTAMP captured_at
        TEXT bib_number_nullable
        NUMERIC bib_confidence
        TEXT gender_nullable
        NUMERIC gender_confidence
        TEXT ai_review_status "auto|manual_pending|manual_approved|manual_rejected"
        TIMESTAMP retention_until "computed"
        TIMESTAMP created_at
    }

    face_embeddings {
        UUID id PK
        UUID photo_id FK
        VECTOR_512 embedding "pgvector ivfflat"
        NUMERIC face_box_x
        NUMERIC face_box_y
        NUMERIC face_box_w
        NUMERIC face_box_h
        NUMERIC detection_confidence
        TIMESTAMP retention_until "event.end_at + 7d"
        TIMESTAMP created_at
    }

    review_queue {
        UUID id PK
        UUID photo_id FK
        TEXT reason "low_ocr_conf|no_bib|ambiguous_face|other"
        TEXT status "pending|in_review|approved|rejected"
        UUID assigned_to FK_nullable "app_users.id"
        TEXT decision_bib_nullable
        TEXT notes
        TIMESTAMP created_at
        TIMESTAMP resolved_at
    }

    event_tokens {
        UUID id PK
        UUID event_id FK
        TEXT token_hash UK "argon2 hash of plaintext"
        TEXT token_prefix "first 8 chars for display"
        TIMESTAMP expires_at "= event.end_at"
        TIMESTAMP revoked_at
        UUID issued_by_app_user_id FK
        TIMESTAMP created_at
    }

    partner_api_keys {
        UUID id PK
        UUID organizer_id FK
        TEXT key_hash UK
        TEXT key_prefix
        TEXT_ARRAY scopes "public:photos:read|erasure:write"
        INT rate_limit_per_minute
        TIMESTAMP revoked_at
        UUID issued_by_app_user_id FK
        TIMESTAMP last_used_at
        TIMESTAMP created_at
    }

    app_users {
        UUID id PK_FK "REFERENCES auth.users(id)"
        TEXT role "admin|staff"
        TEXT display_name
        BOOL mfa_enrolled
        UUID invited_by FK
        TIMESTAMP invited_at
        TIMESTAMP accepted_at
        TIMESTAMP last_login_at
        TIMESTAMP created_at
    }

    app_user_organizer_scope {
        UUID id PK
        UUID app_user_id FK
        UUID organizer_id FK
    }

    app_user_event_scope {
        UUID id PK
        UUID app_user_id FK
        UUID event_id FK
    }

    consent_records {
        UUID id PK
        UUID event_id FK
        TEXT bib_number
        TEXT partner_runner_external_id "id ของ runner ที่ partner-side"
        TEXT policy_version "version ของ consent text"
        BOOL opt_in_extended_retention
        TIMESTAMP consent_at
        TIMESTAMP received_at "received by Joggy-PicX"
    }

    erasure_requests {
        UUID id PK
        UUID event_id FK
        TEXT bib_number
        UUID requested_by_partner_api_key_id FK
        TEXT reason
        TEXT status "pending|processing|completed|failed"
        TIMESTAMP requested_at
        TIMESTAMP completed_at
        TIMESTAMP sla_deadline "= requested_at + 24h"
    }

    audit_logs {
        UUID id PK
        UUID actor_app_user_id FK_nullable
        UUID actor_partner_api_key_id FK_nullable
        UUID actor_event_token_id FK_nullable
        TEXT actor_kind "internal_user|partner|photographer|system"
        TEXT action "upload|delete|erasure|review_approve|key_revoke|..."
        TEXT target_kind "photo|event|organizer|face_embedding|..."
        UUID target_id_nullable
        JSONB context "ip, ua, scope, etc."
        TIMESTAMP created_at
    }
```

---

## 2. คำอธิบาย Table

### 2.1 Multi-Tenant Core

#### `organizers` — Partner / ผู้จัดงาน (D-018)
- 1 organizer มีหลาย event ได้
- `integration_mode`: Phase 2 ใช้ `pull` เท่านั้น; `push`/`embed` reserved Phase 5+
- `pull_config` JSONB ตัวอย่าง: `{"rate_limit_per_minute": 60, "allowed_origins": ["https://race-result.asia"]}`

#### `events` — งานวิ่ง 1 ครั้ง
- belongs to 1 organizer
- `retention_until` = computed column (`end_at + 30d` หรือ `+ 365d` ถ้า opt-in)
- `status`: `planned` (ก่อนเริ่ม) → `active` (กำลังจัด) → `completed` (จบ, รอ cleanup) → `archived` (ลบรูปแล้ว, เก็บ metadata anonymized)

#### `checkpoints` — จุดถ่ายรูปในงาน
- belongs to 1 event
- `kind` enum สำหรับ analytics, `seq_order` สำหรับ sort

### 2.2 Photo & AI Pipeline

#### `photos` — รูปต้นฉบับ (1 row = 1 รูป)
- ผูกกับ event + checkpoint + event_token + device_id
- `r2_key_*`: path ใน R2 bucket (เช่น `events/<event_id>/<photo_id>/original.jpg`)
- `bib_number_nullable` + `bib_confidence`: ผล OCR
- `ai_review_status` flow: AI ตัดสินใจ → ถ้า low confidence → `manual_pending` → human approve/reject
- `retention_until` = `event.end_at + 30d` (extend +30d ได้)

#### `face_embeddings` — Face vector (D-014, ลบเร็วกว่ารูป)
- 1 photo มีได้หลาย face (1..N)
- `embedding` = `vector(512)` ใน pgvector
- ต้องสร้าง index แบบ ivfflat ผ่าน **raw SQL ใน Alembic** (D-020):
  ```sql
  CREATE INDEX face_embeddings_embedding_idx
  ON face_embeddings USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);
  ```
- `retention_until` = `event.end_at + 7d` (สั้นกว่ารูป)

#### `review_queue` — Manual Review (Phase 3)
- Photo ที่ AI confidence ต่ำเข้าคิวนี้
- `assigned_to` → Internal User คนที่ดูแล
- `decision_bib_nullable` = bib ที่คนตัดสินใจ (override AI)

### 2.3 Auth (3 ชุดแยก) (D-017, D-018, D-019)

#### `app_users` — Internal User (D-019)
- FK ไปยัง `auth.users(id)` ของ Supabase Auth
- `role`: `admin` (full access) หรือ `staff` (scoped)
- `mfa_enrolled` บังคับเป็น true ก่อน access dashboard
- `invited_by` → ใครส่ง invite

#### `app_user_organizer_scope` / `app_user_event_scope` — Scope สำหรับ staff
- Many-to-many tables
- `staff` มี scope = list ของ organizer/event ที่เข้าถึงได้
- `admin` ไม่ต้องมี row ในตารางนี้ (= all access)

#### `event_tokens` — Per-Event Upload Token (D-017)
- Photographer ใช้ token นี้สำหรับ POST `/ingest`
- `token_hash` = argon2 hash; เก็บแค่ `token_prefix` (8 ตัวอักษรแรก) สำหรับแสดงใน dashboard
- `expires_at` = `event.end_at` (auto-revoke)

#### `partner_api_keys` — Partner API Key (D-018)
- belongs to 1 organizer
- `scopes`: array เช่น `['public:photos:read', 'erasure:write']`
- `rate_limit_per_minute`: per-key
- `key_hash` + `key_prefix` (เหมือน event_tokens)

### 2.4 Compliance (D-014)

#### `consent_records` — Consent ที่ partner ส่งมา
- Partner สร้าง row นี้ผ่าน API ตอน register runner เข้า event
- `policy_version`: เก็บ version ของ consent text ที่ runner เห็น (PDPA audit)
- `partner_runner_external_id`: id ของ runner ใน partner's system (ไม่ใช่ PII)

#### `erasure_requests` — Right to Erasure (D-014)
- Partner POST `DELETE /v1/erasure` → สร้าง row → enqueue RQ job
- `sla_deadline` = `requested_at + 24h` (PDPA SLA)
- `status` flow: `pending` → `processing` → `completed` / `failed`

#### `audit_logs` — Audit Trail (D-014)
- Polymorphic actor: 1 row ระบุ 1 actor (internal/partner/photographer/system)
- `context` JSONB เก็บ `ip`, `ua`, `scope`, `event_id`, etc.
- Retention 1 ปี (cron cleanup)

---

## 3. Constraints / Indexes ที่สำคัญ

### 3.1 Multi-tenant safety
- **Application-level:** ทุก query ของ photo/event ต้อง filter ด้วย `organizer_id` (ผ่าน middleware)
- **Phase 3+ Defense in depth:** เปิด Postgres RLS — policy `organizer_id = current_setting('app.current_organizer_id')`

### 3.2 pgvector index (D-003)
```sql
-- raw SQL ใน Alembic migration (D-020)
CREATE EXTENSION IF NOT EXISTS vector;
CREATE INDEX face_embeddings_embedding_idx
  ON face_embeddings USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);

-- query สำหรับ Cross-Checkpoint Re-ID:
-- SELECT * FROM face_embeddings
-- WHERE photo_id <> :exclude_photo_id
-- ORDER BY embedding <=> :query_vector
-- LIMIT 10;
```

### 3.3 Retention indexes
```sql
CREATE INDEX photos_retention_until_idx ON photos(retention_until);
CREATE INDEX face_embeddings_retention_until_idx ON face_embeddings(retention_until);
-- Cron job query: SELECT id FROM photos WHERE retention_until < now()
```

### 3.4 Hash unique constraints
- `event_tokens.token_hash` UNIQUE
- `partner_api_keys.key_hash` UNIQUE
- `photos.sha256` UNIQUE within `event_id` (กัน duplicate upload)

### 3.5 Foreign Key Cascade
- `events.organizer_id` → `ON DELETE RESTRICT` (ห้ามลบ organizer ที่มี event)
- `photos.event_id` → `ON DELETE CASCADE` (ลบ event = ลบรูป)
- `face_embeddings.photo_id` → `ON DELETE CASCADE`
- `review_queue.photo_id` → `ON DELETE CASCADE`

---

## 4. การเปลี่ยนแปลง Schema (Workflow ตาม ADR-0007)

ทุกครั้งที่จะแก้ schema:

1. **แก้ Mermaid ใน section 1** ของไฟล์นี้
2. **แก้ `apps/backend/joggy/db/models.py`** (SQLModel)
3. **`alembic revision --autogenerate -m "<message>"`** + ตรวจ migration file + เพิ่ม raw SQL ถ้าจำเป็น
4. **Regenerate `packages/shared/types.ts`** ผ่าน `pnpm generate-types`
5. PR ต้องมี 4 diff ครบ + อัปเดตวันที่ที่ section บนสุด

---

## 5. Open Schema Questions (Phase 2 จะ resolve)

- [ ] Soft delete vs hard delete สำหรับ `events` — PDPA บอก hard delete สำหรับ personal data แต่ event metadata anonymized เก็บได้ → ใช้ "archive" flow
- [ ] Sharding/partition ของ `audit_logs` — ตอนนี้ scale เล็ก ไม่จำเป็น
- [ ] `consent_records` ต้อง encrypted at rest หรือไม่ — Supabase ทำ encrypted at rest อยู่แล้ว แต่ partner_runner_external_id อาจต้อง hash
- [ ] Versioning ของ `policy_version` text — เก็บ text เต็มที่ไหน (S3? table separate?)
