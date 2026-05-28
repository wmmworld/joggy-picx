# ADR-0007 — DB Schema Workflow: Mermaid ER + SQLModel + Alembic + Raw SQL

- **Status:** Accepted
- **Date:** 2026-05-28
- **Deciders:** CEO + Claude (Tech Lead)
- **Related:** [DECISIONS.md#D-020](../../DECISIONS.md), [D-003 (Supabase + pgvector)](../../DECISIONS.md), [D-018 (Multi-partner)](../../DECISIONS.md)

---

## 1. Context

โปรเจก Joggy-PicX เป็น multi-tenant system ที่มี ~11 tables ใน Phase 2 + pgvector (D-003) + complex audit/compliance/erasure logic (D-014).

ทีม AI 4 ตัวต้องอ่าน schema ตรงกัน, review ก่อน code, และ maintain ให้ตรงตามจริง — workflow ต้องชัดเจน.

Constraint:
- pgvector ต้องใช้ raw SQL สร้าง index (`CREATE INDEX ... USING ivfflat`)
- Multi-tenant ต้อง enforce `organizer_id` ทุก query (app middleware + optional RLS)
- AI ต้องอ่าน schema ก่อน implement (ไม่ใช่ "เขียนแล้วค่อยรู้ schema")

## 2. Decision

ใช้ **Hybrid workflow 4 ขั้นตอน**:

### Step 1 — Mermaid ER Diagram ใน `docs/schema.md`
- Living document ที่ AI ทุกตัว review ได้
- GitHub renders Mermaid native → ไม่ต้อง tool พิเศษ
- ต้อง update ทุกครั้ง schema เปลี่ยน (ใน Phase exit checklist)

### Step 2 — SQLModel ORM ที่ `apps/backend/joggy/db/models.py`
- **Single Source of Truth** = code
- `SQLModel` = Pydantic + SQLAlchemy → type-safe + reuse กับ FastAPI request/response
- Multi-tenant: ทุก photo/event-related model มี `organizer_id` (direct หรือ inherited ผ่าน FK)

### Step 3 — Alembic Migration ที่ `apps/backend/alembic/versions/`
- `alembic revision --autogenerate -m "<message>"` สำหรับ schema change ทั่วไป
- เขียน raw SQL ใน migration file สำหรับ DB-specific:
  - `CREATE EXTENSION vector;`
  - `CREATE INDEX ... USING ivfflat (embedding vector_cosine_ops);`
  - RLS policies (Phase 3 — defense in depth)
  - Trigger สำหรับ audit log auto-fill
- ทุก migration ต้อง reversible (มี `downgrade()`)

### Step 4 — Shared Types ที่ `packages/shared/types.ts`
- Generate อัตโนมัติจาก FastAPI OpenAPI spec (`openapi-typescript` หรือ `orval`)
- Frontend (Cursor) ใช้ types เหล่านี้ — type-safe end-to-end
- ห้ามเขียน types มือใน frontend ที่ duplicate กับ backend

## 3. Workflow Lifecycle

```
   เริ่มทำ schema change
        │
        ▼
   1. แก้ Mermaid ER ใน docs/schema.md (preview ผ่าน GitHub)
        │
        ▼ (review with team)
   2. แก้ SQLModel ใน apps/backend/joggy/db/models.py
        │
        ▼
   3. alembic revision --autogenerate
        │ (ตรวจ migration file + เพิ่ม raw SQL ถ้าจำเป็น)
        ▼
   4. รัน alembic upgrade head ใน dev
        │
        ▼
   5. uvicorn เปิด FastAPI → openapi.json อัปเดต
        │
        ▼
   6. pnpm run generate-types (regenerate packages/shared/types.ts)
        │
        ▼
   7. Frontend ใช้ types ใหม่ได้ทันที
        │
        ▼
   8. PR ต้องมี: schema.md diff + models.py diff + migration file + types diff
```

## 4. Alternatives Considered

### Option A — ER → Raw SQL → ORM reflect
- ✅ Diagram-first
- ❌ ORM reflect drift จาก SQL เมื่อ schema เปลี่ยน
- ❌ Maintain 3 sources (diagram + SQL + ORM)

### Option B — Code-first (SQLModel + Alembic) only
- ✅ Single source
- ❌ ไม่มี overview สำหรับ AI ตัวอื่นอ่านก่อน implement

### Option C — Migration-first (raw SQL only)
- ✅ Control DB-specific เต็มที่
- ❌ ต้องเขียน Pydantic types ซ้ำสำหรับ FastAPI
- ❌ Type safety หาย

## 5. Consequences

### Positive
- AI ทุกตัวอ่าน Mermaid ER ก่อน implement → ไม่งง schema
- Type safety end-to-end (DB ↔ FastAPI ↔ Frontend)
- DB-specific feature (pgvector, RLS) ใช้ได้เต็มที่ผ่าน raw SQL ใน migration
- Migration reversible เสมอ → safe rollback

### Negative / Tradeoffs ที่ต้องรับ
- Mermaid อาจ drift จาก code
  - **Mitigation:** Phase exit checklist ต้อง verify diagram = code
  - **Future:** เขียน script generate Mermaid จาก SQLModel (Phase 5+)
- SQLModel ใหม่กว่า SQLAlchemy plain
  - **Mitigation:** Fallback ไป SQLAlchemy ได้ทุก feature (SQLModel เป็น wrapper บาง)
- Workflow มี 4 ขั้นตอน → onboarding ใหม่อาจสับสน
  - **Mitigation:** เขียน runbook ใน `docs/dev-workflow.md` (Phase 2)

### Reversibility
- เปลี่ยน ORM (SQLModel → SQLAlchemy plain) = refactor 1 file `models.py` + import statement
- เลิก Mermaid = ลบ docs/schema.md
- เปลี่ยน Alembic = export schema ออกได้ทุกเมื่อ

## 6. Rules ที่ตามมาจาก decision นี้

1. ทุก schema change PR **ต้อง** มี 4 ไฟล์ change: `docs/schema.md`, `models.py`, migration file, `types.ts`
2. Migration ที่มี raw SQL ต้องมี comment อธิบาย "why raw SQL จำเป็น"
3. ห้าม `op.execute("DROP TABLE ...")` โดยไม่มี backup script ก่อนหน้า
4. Migration หลัง production แล้วต้อง forward-only (ใช้ new migration to fix, ไม่ revert)
5. Multi-tenant model ทุกตัวต้องมี `organizer_id` column (หรือ FK ที่ inherit ได้)
6. ทุก table ที่มี personal data ต้องมี `retention_until: TIMESTAMP` (ดู ADR-0004)
7. `packages/shared/types.ts` regenerate ผ่าน `pnpm generate-types` — ห้ามแก้มือ
8. ก่อน close phase ต้อง verify Mermaid = SQLModel = migration (manual sync check)
