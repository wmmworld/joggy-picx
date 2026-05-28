# ADR-0006 — Multi-Partner Integration Architecture (Design-for-3, Build-1)

- **Status:** Accepted
- **Date:** 2026-05-28
- **Deciders:** CEO + Claude (Tech Lead)
- **Related:** [DECISIONS.md#D-017](../../DECISIONS.md), [DECISIONS.md#D-018](../../DECISIONS.md), [CONTEXT.md](../../CONTEXT.md), [ADR-0004 (PDPA)](0004-pdpa-retention-policy.md)

---

## 1. Context

Joggy-PicX **ไม่ใช่ระบบที่นักวิ่งใช้โดยตรง** — นักวิ่งดูรูปผ่านเว็บผลการแข่งขัน (External Partner) ที่ดึงรูปจาก Joggy-PicX ผ่าน API ด้วยเลขบิบ

**First-party Partner:** race-result.asia (CEO เป็นเจ้าของ)
**Future Partners:** หลายเจ้า (Joggy-PicX = service ขายให้ผู้จัดงานหลายราย)

Integration mode ที่ partner ต้องการอาจต่างกัน:
- **Pull** — partner ยิง API มาดึงรูป (realtime, partner control)
- **Push** — Joggy-PicX webhook ไปยัง partner (low-latency partner-side display)
- **Embed** — partner ฝัง JS widget (zero code, fastest TTM)

Constraint:
- Timeline 20-25 วันถึง first real test → ทำ 3 modes ครบ Phase 1 ไม่ทัน
- ต้อง enable race-result.asia integration ก่อน end of Phase 4
- Schema/architecture ต้อง forward-compatible

## 2. Decision

### 2.1 Multi-Tenant ตั้งแต่ Phase 1
ทุก resource ใน Joggy-PicX เป็น **Organizer-scoped** ตั้งแต่ต้น (ไม่ใช่ single-tenant ที่ refactor ทีหลัง):

- `Organizer` table มีตั้งแต่ Phase 1
- ทุก `Event` ต้อง belong to 1 Organizer
- ทุก `Photo` inherit organizer_id ผ่าน event_id
- Partner API Key scope = Organizer-level

### 2.2 Integration Mode — Design for 3, Build 1

| Mode | Phase | Note |
|---|---|---|
| **Pull** (`pull`) | **Phase 2 (Build)** | Default mode, race-result.asia ใช้ตัวนี้ |
| **Push** (`push`) | Phase 5+ (Reserved) | Schema เผื่อแต่ไม่ implement |
| **Embed** (`embed`) | Phase 5+ (Reserved) | Schema เผื่อแต่ไม่ implement |

Schema ที่ reserve:
```sql
CREATE TABLE organizers (
  id UUID PRIMARY KEY,
  name TEXT NOT NULL,
  contact_email TEXT,
  integration_mode TEXT NOT NULL DEFAULT 'pull'
    CHECK (integration_mode IN ('pull', 'push', 'embed')),
  pull_config JSONB,        -- rate limit, allowed_origins
  push_config JSONB,        -- webhook url, secret, retry policy (Phase 5+)
  embed_config JSONB,       -- allowed_domains, theme overrides (Phase 5+)
  created_at TIMESTAMP DEFAULT now(),
  ...
);

CREATE TABLE partner_api_keys (
  id UUID PRIMARY KEY,
  organizer_id UUID NOT NULL REFERENCES organizers(id),
  key_hash TEXT NOT NULL UNIQUE,
  scopes TEXT[] NOT NULL,    -- ['public:photos:read']
  revoked_at TIMESTAMP,
  ...
);
```

### 2.3 Pull API Contract (Phase 2)

```
GET /v1/public/photos
  ?bib=<bib_number>
  &event_id=<event_id>
  [&cursor=<cursor>]
  [&limit=<n>]

Headers:
  Authorization: Bearer <partner_api_key>

Response 200:
{
  "bib": "42",
  "event_id": "evt_xxx",
  "photos": [
    {
      "id": "photo_abc",
      "url": "https://r2.joggy/...signed?expire=3600",
      "thumbnail_url": "...",
      "checkpoint": "CP-3",
      "captured_at": "2026-05-28T10:23:00+07:00",
      "confidence": 0.92,
      "ai_review_status": "auto" | "manual_pending" | "manual_approved"
    }
  ],
  "next_cursor": "..."
}

Errors:
  401  Invalid/revoked API key
  403  API key has no access to this event/organizer
  404  Event not found
  429  Rate limit exceeded
```

### 2.4 Right to Erasure API (Phase 2)

```
DELETE /v1/erasure
Body: { "bib": "42", "event_id": "evt_xxx", "reason": "user_request" }
Headers: Authorization: Bearer <partner_api_key>

→ enqueue erasure job, return 202 Accepted
→ ภายใน 24 ชม. ลบรูป + embedding + anonymize metadata
```

## 3. Alternatives Considered

### Option B — Build 2A + 2B from Phase 1
- ✅ Push ready สำหรับ partner เจ้าที่ 2
- ❌ Webhook complexity (subscription, HMAC, retry, dead letter) เกิน scope Phase 1-4

### Option C — Build all 3 from Phase 1
- ✅ Future-proof
- ❌ Embed widget = JS SDK + CDN + iframe sandbox = ~5-7 วันงานเพิ่ม
- ❌ ไม่ทัน timeline 20-25 วัน

### Option D — Build only Pull, no schema reservation
- ✅ ง่ายสุด
- ❌ ต้อง refactor schema เมื่อเพิ่ม mode → migration เจ็บ

## 4. Consequences

### Positive
- Phase 1-4 focus ที่ Pull mode + race-result.asia integration
- Schema reserve `integration_mode` ตั้งแต่ต้น → ขยาย mode ใหม่ไม่ต้อง breaking migration
- Multi-tenant ตั้งแต่แรก → ไม่ต้อง refactor "single tenant → multi" ทีหลัง
- Partner onboarding ใหม่ในอนาคต = สร้าง Organizer + issue API key + ตั้ง integration_mode

### Negative / Tradeoffs ที่ต้องรับ
- Schema มี column ที่ "ยังไม่ใช้" (push_config, embed_config) — overhead เล็กน้อย
- Pull mode = partner ต้อง poll → load บน Joggy-PicX สูงกว่า push เล็กน้อย
  - **Mitigation:** Cache response 30 วินาที ต่อ (bib, event_id), partner ส่วนใหญ่ on-demand lookup
- Multi-tenant complexity ตั้งแต่ Phase 1 — ทุก query ต้องใส่ organizer_id filter
  - **Mitigation:** Middleware ฉีด `organizer_id` จาก API key อัตโนมัติ + Supabase RLS เป็น defense in depth

### Reversibility
- เพิ่ม mode = ไม่ breaking
- ลบ partner = soft delete + revoke key
- เปลี่ยน Pull → Push สำหรับ partner เดิม = update `integration_mode` + ตั้ง webhook (ทำได้)

## 5. Rules ที่ตามมาจาก decision นี้

1. ทุก resource ที่ photo/event-related ต้องมี `organizer_id` (direct หรือ inherited)
2. Partner API Key ห้ามไม่มี scope — ต้องระบุ explicit (`public:photos:read`, `erasure:write`, ...)
3. Pull endpoint **ทุกตัว** ต้องมี rate limit per-key + per-IP
4. Signed URL ของรูปต้องมี expire ≤1 ชม.
5. Public endpoint ต้อง log ทุก request: `(api_key_id, organizer_id, bib, event_id, ip, ua, status, latency)`
6. ห้ามมี endpoint ที่ return rüรูปทั้งหมดของ event โดยไม่กรอง `bib` — ป้องกัน scraping
7. CORS allow เฉพาะ `allowed_origins` ที่ organizer ตั้งไว้
8. Phase 5+ จะเพิ่ม push/embed → schema migration จะเป็น additive เท่านั้น (เพิ่ม table/column ใหม่)
