# Phase 2 Day 5 — Design Spec

**Date:** 2026-05-29
**Author:** Claude (Tech Lead)
**Status:** Approved by CEO

---

## Overview

Phase 2 Day 5 ครอบคลุม 4 งานที่รันพร้อมกันได้ (Approach A — Full Parallel):

| # | งาน | ทำโดย | ไฟล์หลัก |
|---|-----|--------|----------|
| 1 | DELETE /erasure full implementation | Claude | `public.py`, `tasks.py`, `queue.py`, `worker/db.py` |
| 2 | Event Create Modal | Cursor | `components/events/CreateEventModal.tsx`, `events/page.tsx` |
| 3 | Manual Review Queue UI Skeleton | Cursor | `app/(internal)/dashboard/review/page.tsx` |
| 4 | Integration Smoke Test | Claude | `tools/smoke_test.py` |

---

## 1. DELETE /erasure — Full Implementation

### Endpoint

```
DELETE /v1/public/erasure?event_id=<uuid>&bib=<str>&reason=<optional_str>
Auth: X-API-Key: <partner_key>   scope required: erasure:write
Response: 202 Accepted
```

Auth + scope check ใส่แล้วจาก Day 4 review. งานที่เหลือคือ implement body.

### Request Flow

1. Validate `event_id` เป็น valid UUID
2. Check event exists (ถ้าไม่มี → 404)
3. INSERT `ErasureRequest`:
   - `event_id`, `bib_number = bib`
   - `requested_by_partner_api_key_id = claims.key_id`
   - `reason` (optional)
   - `sla_deadline = now + 24h`
   - `status = ErasureStatus.pending`
4. `enqueue_process_erasure(str(er.id))` → RQ job
5. INSERT `AuditLog` (actor=partner, action="erasure_requested")
6. Return:
   ```json
   {
     "status": "accepted",
     "erasure_id": "<uuid>",
     "sla_deadline": "<ISO datetime>",
     "sla_hours": 24
   }
   ```

### Worker Task — `process_erasure(erasure_id: str)`

ไฟล์: `apps/backend/joggy/worker/tasks.py`

```
1. Load ErasureRequest → set status = processing, flush
2. Query Photos WHERE event_id + bib_number_nullable = bib AND id NOT already deleted
3. Collect photo_ids, r2_key_original[], r2_key_thumbnail[]
4. DELETE FaceEmbeddings WHERE photo_id IN photo_ids  (biometric data — ต้องลบก่อน)
5. For each R2 key: r2.delete_object(key)  — ignore errors ถ้า key ไม่มีใน R2 แล้ว
6. DELETE Photo rows WHERE id IN photo_ids
7. Set ErasureRequest status = completed, completed_at = now()
8. INSERT AuditLog (actor=system, action="erasure_completed", context={"photos_deleted": count})
9. Return {"erasure_id": erasure_id, "photos_deleted": count, "status": "completed"}

Error handling: wrap ทุกอย่างใน try/except → set status=failed, log exception → re-raise ให้ RQ จับ
```

### Worker DB Pattern

ไฟล์ใหม่: `apps/backend/joggy/worker/db.py`

RQ worker เป็น sync context — ใช้ `asyncio.run()` + async SQLAlchemy engine (asyncpg) ที่มีอยู่แล้ว ไม่ต้องเพิ่ม dependency ใหม่:

```python
# worker/db.py
@asynccontextmanager
async def worker_db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(get_settings().database_url)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await engine.dispose()

# tasks.py pattern
def process_erasure(erasure_id: str) -> dict:
    return asyncio.run(_process_erasure_async(erasure_id))

async def _process_erasure_async(erasure_id: str) -> dict:
    async with worker_db_session() as db:
        ...
```

### Queue

`apps/backend/joggy/worker/queue.py` — เพิ่ม `enqueue_process_erasure(erasure_id: str) -> str`:
- `job_timeout=300`, `result_ttl=86400`, `failure_ttl=604800`

---

## 2. Event Create Modal (Cursor)

### Files

- **New:** `apps/frontend/components/events/CreateEventModal.tsx`
- **Modified:** `apps/frontend/app/(internal)/dashboard/events/page.tsx`

### Form Fields

| Field | Input | Validation |
|-------|-------|------------|
| ชื่องาน (`name`) | text | required, 1–255 chars |
| Organizer ID (`organizer_id`) | text (UUID format) | required |
| วันเริ่ม (`start_at`) | datetime-local | required |
| วันสิ้นสุด (`end_at`) | datetime-local | required, > start_at |
| Allowed Origins (JSON) | textarea | optional |

### Data Flow

```
Button "สร้างงานใหม่" (on events/page.tsx)
  → open modal (useState: isOpen)
  → fill form
  → client-side validate: end_at > start_at
  → apiPost<EventOut, EventCreatePayload>("/internal/events", payload)
  → success: close modal + queryClient.invalidateQueries(["events"])
  → error: show error message inline in modal (ไม่ปิด modal)
```

### UX Rules

- Submit button แสดง loading state ระหว่าง API call
- Close ด้วย × button หรือ click outside backdrop (`onBackdropClick`)
- Reset form เมื่อ modal ปิด
- Backend enforce admin-only (frontend แสดงปุ่มทุก user, Phase 2)

### Type Additions (useEvents.ts หรือ new file)

```typescript
export type EventCreatePayload = {
  organizer_id: string;
  name: string;
  start_at: string;   // ISO datetime string
  end_at: string;
  allowed_origins?: object | null;
};
```

---

## 3. Manual Review Queue Skeleton (Cursor)

### Files

- **New:** `apps/frontend/app/(internal)/dashboard/review/page.tsx`

### Layout

```
Header: "คิวตรวจสอบรูป"
Subtitle: "รูปที่ AI ประเมิน confidence ต่ำ รอการตรวจสอบจาก staff"

Stats card: "0 รูปรอตรวจสอบ" (static)

Table:
  Columns: รูปภาพ | เลขบิบ | งาน | AI Confidence | การจัดการ
  Body: empty state row → "ยังไม่มีรูปรอตรวจสอบ ✓"

Phase 3 note (muted text):
  "Phase 3: ระบบ AI จะส่งรูปที่ confidence ต่ำกว่า 80% มาที่นี่"
```

### Scope Boundary

- Phase 2: Static skeleton — ไม่มี API call ทั้งสิ้น
- Phase 3: เพิ่ม `useReviewQueue()` hook + approve/reject API calls
- Navigation: เพิ่ม link "คิวตรวจสอบ" ใน dashboard nav ถ้ามี sidebar component

---

## 4. Integration Smoke Test (Claude)

### File

`tools/smoke_test.py` — standalone Python script, ไม่ใช่ pytest

### Dependency

`httpx` — เพิ่มใน `pyproject.toml` optional `[dev]` group

### Tests (7 checks)

| # | Test | Expected |
|---|------|---------|
| 1 | `GET /health` | 200 + `{"status": "ok"}` |
| 2 | `POST /ingest/photos` (no Authorization) | 403 |
| 3 | `GET /internal/events` (no Authorization) | 403 |
| 4 | `GET /v1/public/photos` (no X-API-Key) | 422 (missing query param) or 403 |
| 5 | `DELETE /v1/erasure` (no X-API-Key) | 422 or 403 |
| 6 | `GET /v1/public/photos?event_id=...&bib=...` (invalid key) | 401 |
| 7 | `GET /internal/events` (invalid JWT `Bearer garbage`) | 401 |

### Output Format

```
smoke_test.py — Joggy-PicX API (http://localhost:8000)
──────────────────────────────────────────────────────
 ✅ [1/7] Health check
 ✅ [2/7] Ingest: no-auth → 403
 ✅ [3/7] Internal: no-auth → 403
 ✅ [4/7] Public photos: no-key → 422
 ✅ [5/7] Erasure: no-key → 422
 ✅ [6/7] Public photos: invalid-key → 401
 ✅ [7/7] Internal: invalid-jwt → 401
──────────────────────────────────────────────────────
 7/7 passed  🎉
```

Exit code 0 = all pass, exit code 1 = any fail.

---

## Constraints & Rules (from AGENTS.md)

- ห้าม return `face_embedding` ในทุก endpoint
- ห้าม implement runner-facing login/signup/dashboard
- ห้าม commit `.env` หรือ credential files
- Worker: ใช้ `onnxruntime` เท่านั้น (Phase 3) — ห้าม torch/paddle
- ErasureRequest: ต้องลบ FaceEmbedding **ก่อน** Photo (biometric data first)
- AuditLog: ทุก erasure action ต้อง log ครบ

---

## Out of Scope (Phase 2 Day 5)

- ErasureRequest list endpoint สำหรับ admin dashboard
- Organizer management UI (Phase 4)
- Actual bib-recognition AI (Phase 3)
- Mobile upload app (Phase 5)
