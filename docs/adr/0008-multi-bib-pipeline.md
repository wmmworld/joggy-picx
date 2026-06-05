# ADR-0008 — Multi-Bib Pipeline: PhotoBib 1-to-Many Schema

- **Status:** Accepted
- **Date:** 2026-06-05
- **Deciders:** CEO + Claude (Tech Lead)
- **GitHub Issue:** [#1 Multi-bib pipeline](https://github.com/wmmworld/joggy-picx/issues/1)
- **Related:** [DECISIONS.md#D-021](../../DECISIONS.md), [ADR-0003](0003-single-ai-worker-process.md), [ADR-0007](0007-db-schema-workflow.md)

---

## 1. Context

`BibDetector.detect_all()` (commit e1ac2c5, 2026-06-05) คืน `list[BibBox]` พร้อม NMS แล้ว
แต่ระบบที่เหลือยัง assume **1 bib ต่อ 1 รูป**:

| Layer | ปัญหา |
|-------|-------|
| `Photo` model | มี `bib_number_nullable: str` และ `bib_confidence: float` — เก็บได้แค่ตัวเดียว |
| `worker/pipeline.py` | เรียก `detector.detect()` (legacy wrapper คืนแค่ top-1) |
| `GET /v1/public/photos?bib=` | WHERE `photo.bib_number = :bib` — join แค่ column เดียว |
| Review queue UI | แสดง 1 bib/รูป |

จากการ eyeball test holdout 20 รูป:
- ค่าเฉลี่ย **3.9 bibs/รูป**, สูงสุด 11 bibs ใน 1 รูป
- รูปที่ถ่ายที่ start/finish มีนักวิ่งหลายคนใน frame พร้อมกัน

ถ้าไม่แก้ → **นักวิ่งที่ไม่ใช่คนแรก (top-1 confidence) ค้นหารูปตัวเองไม่เจอ**

---

## 2. Decision

เพิ่ม table `photo_bibs` (**1-to-many**: 1 photo → N bibs) แทนการเก็บ bib ใน `Photo` โดยตรง

### 2.1 Schema Changes

```
Photo (เดิม)                    Photo (ใหม่)
────────────────────────        ────────────────────────
bib_number_nullable: str?  →    deprecated (เก็บไว้ backward-compat, NULL ทั้งหมด)
bib_confidence: float?     →    deprecated (เก็บไว้ backward-compat, NULL ทั้งหมด)

PhotoBib (NEW table)
────────────────────────
id:           UUID PK
photo_id:     UUID FK → photos.id  (index)
bib_number:   str  (index)
confidence:   float
bbox_x1:      int
bbox_y1:      int
bbox_x2:      int
bbox_y2:      int
created_at:   datetime
```

### 2.2 Worker Changes

```python
# BEFORE (pipeline.py)
bbox = detector.detect(img_bgr)                    # top-1 only
bib_result = ocr.read(img_bgr, bbox) if bbox else None
photo.bib_number_nullable = bib_result.number if bib_result else None

# AFTER
boxes = detector.detect_all(img_bgr)               # all bibs
for box in boxes:
    bib_result = ocr.read(img_bgr, box)
    if bib_result is not None:
        db.add(PhotoBib(
            photo_id=photo.id,
            bib_number=bib_result.number,
            confidence=bib_result.confidence,
            bbox_x1=box.x1, bbox_y1=box.y1,
            bbox_x2=box.x2, bbox_y2=box.y2,
        ))
```

### 2.3 Public API Changes

```python
# BEFORE
WHERE photos.bib_number_nullable = :bib

# AFTER
JOIN photo_bibs pb ON pb.photo_id = photos.id
WHERE pb.bib_number = :bib
```

### 2.4 ai_review_status Logic

| เงื่อนไข | Status |
|---------|--------|
| มี ≥1 PhotoBib ที่ confidence ≥ 0.8 | `auto` |
| มี PhotoBib แต่ confidence ต่ำทั้งหมด | `manual_pending` |
| ไม่มี PhotoBib เลย | `manual_pending` |

---

## 3. Alternatives Considered

### Option A — Array column: `bib_numbers: list[str]` ใน Photo (rejected)
- ✅ ไม่ต้องสร้าง table ใหม่
- ❌ PostgreSQL array column → ไม่มี index ที่ดี → `WHERE 'X' = ANY(bib_numbers)` ช้า
- ❌ ไม่เก็บ confidence/bbox ต่อ bib → ไม่มีข้อมูลสำหรับ Review queue UI

### Option B — JSON column: `bibs: jsonb` ใน Photo (rejected)
- ✅ Flexible schema
- ❌ GIN index ยุ่งยากกว่า B-tree index บน separate table
- ❌ Type safety หายใน SQLModel + FastAPI response schema
- ❌ OCR re-run ต้อง parse JSON ซับซ้อนกว่า

### Option C — Table `photo_bibs` 1-to-many (selected ✅)
- ✅ B-tree index บน `(bib_number, photo_id)` → fast lookup
- ✅ เก็บ confidence + bbox ต่อ bib → Review queue แสดง crop บิบเดิมได้
- ✅ JOIN กับ Public API query ตรงไปตรงมา
- ✅ Consistent กับ `FaceEmbedding` pattern (1-to-many photo → face)
- ⚠️ Migration เพิ่ม table ใหม่ + deprecate 2 columns เดิม

---

## 4. Migration Plan

### Phase A — Additive (non-breaking, safe deploy)
1. `alembic revision`: สร้าง `photo_bibs` table
2. `worker/pipeline.py`: เปลี่ยนเป็น loop `detect_all()` → insert `PhotoBib` rows
3. **ยังไม่แก้ Public API** — `bib_number_nullable` ยังอยู่

### Phase B — API Migration
4. แก้ `GET /v1/public/photos?bib=` → JOIN `photo_bibs`
5. แก้ Review queue UI → แสดง crop ต่อ `PhotoBib`
6. ทดสอบ end-to-end

### Phase C — Cleanup (หลัง production verify แล้ว)
7. `alembic revision`: DROP columns `bib_number_nullable`, `bib_confidence`
8. ลบ legacy `detector.detect()` wrapper (optional)

> ทำ Phase A+B ก่อน deploy → Phase C ค่อยทำหลัง 1 สัปดาห์ production stable

---

## 5. Consequences

### Positive
- นักวิ่งทุกคนในรูป (ไม่แค่คน confidence สูงสุด) ค้นหารูปตัวเองได้
- Review queue แสดง bbox crop ต่อ bib → ทีม review ตัดสินใจง่ายขึ้น
- รองรับรูป group photo ที่มีหลายร้อยคนใน frame (marathon finish line)
- Pattern สอดคล้องกับ `FaceEmbedding` ที่ทำอยู่แล้ว

### Negative / Tradeoffs
- Worker ช้าลงเล็กน้อย — OCR รัน N ครั้ง/รูป แทน 1 ครั้ง
  - **Mitigation:** YOLOv8-nano fast (~50ms/รูป), OCR digit-only 11-class (~30ms/crop)
  - คาด worst case 10 bibs × 80ms = 800ms/รูป (ยังอยู่ใน SLA 5s)
- `photo_bibs` table เพิ่ม storage ~100 bytes/bib × avg 4 bibs × 1M photos = ~400MB
  - **Acceptable** สำหรับ Hetzner CPX11 80GB disk
- 2 deprecated columns ใน `Photo` ต้องดูแล 1-2 sprint จนถึง Phase C cleanup
  - **Mitigation:** Add `# DEPRECATED — use photo_bibs table` comment ใน models.py

### Reversibility
- Phase A migration reversible (DROP TABLE photo_bibs)
- Phase B API change reversible (revert WHERE clause)
- Phase C คือ destructive → ทำหลัง production stable เท่านั้น

---

## 6. Implementation Checklist

> ใช้เป็น task list สำหรับ Claude เมื่อ implement

- [ ] **A1** — SQLModel: เพิ่ม `PhotoBib` class ใน `models.py` + deprecate comment บน `bib_number_nullable`/`bib_confidence`
- [ ] **A2** — Alembic: `alembic revision --autogenerate -m "add photo_bibs table"` + verify migration
- [ ] **A3** — Worker: `pipeline.py` เปลี่ยน `detector.detect()` → `detector.detect_all()` + loop insert `PhotoBib`
- [ ] **A4** — Tests: `test_pipeline.py` update ให้ assert PhotoBib rows แทน `bib_number_nullable`
- [ ] **B1** — Public API: `GET /v1/public/photos?bib=` แก้ query JOIN `photo_bibs`
- [ ] **B2** — Schemas: `PhotoItemOut` เพิ่ม `bibs: list[BibOut]` field
- [ ] **B3** — Review queue backend: ส่ง `bibs` list พร้อม bbox coords
- [ ] **B4** — Review queue frontend: แสดง crop ต่อ bib (Cursor prompt)
- [ ] **B5** — Integration test: POST ingest → rัน worker mock → assert PhotoBib rows + API return
- [ ] **C1** *(post-production)* — DROP `bib_number_nullable`, `bib_confidence` จาก `Photo`
- [ ] **C2** *(post-production)* — docs/schema.md อัปเดต Mermaid ER
