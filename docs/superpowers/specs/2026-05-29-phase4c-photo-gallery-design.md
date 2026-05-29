# Phase 4C — Photo Gallery Design

**Date:** 2026-05-29  
**Author:** Claude (Tech Lead)  
**Status:** Approved

---

## Goal

Build a Photo Gallery page for the Internal Dashboard — staff can browse all photos in an event as a thumbnail grid, filter by bib number / checkpoint / AI status, and paginate through up to 1,000 photos per event.

---

## Scope Decisions

- **Route:** `/dashboard/events/[id]/photos` — dedicated page, not a tab in event detail
- **Layout:** 3–4 column grid (visual browsing), not a list
- **Filters:** bib search (partial match, debounced) + checkpoint dropdown + AI status dropdown
- **Pagination:** 24 items/page, URL query params persist state (page + filters)
- **No edit actions** — gallery is read-only; review/approve actions stay in the Review Queue page

---

## Architecture

Backend adds `GET /internal/events/{event_id}/photos` with query params for filtering and pagination. Frontend creates `useEventPhotos` TanStack Query hook + `photos/page.tsx`. Event detail page gets a link button to the gallery.

---

## Backend

### New endpoint — `apps/backend/joggy/api/internal.py`

```
GET /internal/events/{event_id}/photos
  ?page=1           (default 1, min 1)
  &per_page=24      (default 24, max 100)
  &bib=             (optional — partial ILIKE match on bib_number_nullable)
  &checkpoint_id=   (optional UUID — filter by checkpoint)
  &ai_status=       (optional — one of: auto|manual_pending|manual_approved|manual_rejected)
```

**Auth:** Supabase JWT (same as all `/internal` endpoints)  
**Scope check:** admin sees all; staff must have event in `event_scope` or `organizer_scope`

**Response schema (`EventPhotosOut`):**
```python
class PhotoItemOut(BaseModel):
    photo_id: uuid.UUID
    bib_number: str | None       # Photo.bib_number_nullable
    bib_confidence: float | None # 0.0–1.0 or None
    ai_review_status: str        # enum value string
    thumbnail_url: str | None    # R2 signed URL, expires 1h
    checkpoint_name: str | None
    captured_at: datetime | None

class EventPhotosOut(BaseModel):
    items: list[PhotoItemOut]
    total: int      # total matching records (for pagination UI)
    page: int
    per_page: int
    pages: int      # ceil(total / per_page)
```

**Query logic:**
```python
stmt = (
    select(Photo, Checkpoint)
    .outerjoin(Checkpoint, Checkpoint.id == Photo.checkpoint_id)
    .where(Photo.event_id == event_id)
)

# Optional filters
if bib:
    stmt = stmt.where(Photo.bib_number_nullable.ilike(f"%{bib}%"))
if checkpoint_id:
    stmt = stmt.where(Photo.checkpoint_id == checkpoint_id)
if ai_status:
    stmt = stmt.where(Photo.ai_review_status == AIReviewStatus(ai_status))

# Count total before pagination
total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()

# Paginate
stmt = stmt.order_by(Photo.created_at.desc()).offset((page-1)*per_page).limit(per_page)
```

**Signed URL:** use `r2_key_thumbnail` if present, fallback to `r2_key_original`.

**Validation errors (422):**
- `page < 1` or `per_page > 100`
- `ai_status` not in valid enum values
- `checkpoint_id` not a valid UUID

### New schemas — `apps/backend/joggy/api/schemas.py`

Add `PhotoItemOut` and `EventPhotosOut`.

### Tests — `apps/backend/tests/api/test_event_photos.py`

TDD pattern (6 tests):
- `test_list_event_photos_returns_paginated_items` — 200 with items + pagination metadata
- `test_list_event_photos_filter_by_bib` — bib filter reduces results
- `test_list_event_photos_filter_by_checkpoint` — checkpoint filter
- `test_list_event_photos_filter_by_ai_status` — ai_status filter
- `test_list_event_photos_403_wrong_scope` — staff without event scope gets 403
- `test_list_event_photos_total_count_correct` — total reflects filtered count, not all photos

---

## Frontend

### Files

| File | Action |
|------|--------|
| `apps/frontend/hooks/useEventPhotos.ts` | Create — TanStack Query hook |
| `apps/frontend/app/(internal)/dashboard/events/[id]/photos/page.tsx` | Create — gallery page |
| `apps/frontend/app/(internal)/dashboard/events/[id]/page.tsx` | Modify — add "ดูรูปภาพ" link button |

### `useEventPhotos` hook — `hooks/useEventPhotos.ts`

```typescript
type PhotoItem = {
  photo_id: string
  bib_number: string | null
  bib_confidence: number | null
  ai_review_status: "auto" | "manual_pending" | "manual_approved" | "manual_rejected"
  thumbnail_url: string | null
  checkpoint_name: string | null
  captured_at: string | null
}

type EventPhotosResponse = {
  items: PhotoItem[]
  total: number
  page: number
  per_page: number
  pages: number
}

// Query key: ["event-photos", eventId, { page, bib, checkpointId, aiStatus }]
// Endpoint: GET /internal/events/{eventId}/photos?page=&per_page=24&bib=&checkpoint_id=&ai_status=
// staleTime: 30s
```

### Photo Gallery page — `photos/page.tsx`

**URL state (via Next.js searchParams):**
- `page` (default 1)
- `bib` (default "")
- `checkpoint_id` (default "")
- `ai_status` (default "")

All filter changes update the URL → `router.push` with new params → page resets to 1.

**Layout:**
```
← Back to event detail   "ภาพถ่าย — [event name]"
[total] รูปทั้งหมด

[🔍 ค้นหาบิบ...]  [Checkpoint ▼]  [AI Status ▼]  [ล้าง filter]

[Grid 3-4 cols of PhotoCard]

[Pagination bar: ← 1 [2] 3 ... N →  showing X–Y of Z]
```

**PhotoCard component (inline in page.tsx):**
- `<img>` 64×64 (or aspect-ratio square) thumbnail — click opens lightbox
- Bib number or "ไม่พบ"
- Confidence badge (green ≥ 70% / yellow 50–69% / red < 50% / grey if null)
- AI status badge:
  - `auto` → "✅ AI"  (green)
  - `manual_pending` → "⏳ รอ"  (yellow)
  - `manual_approved` → "✓ อนุมัติ"  (green)
  - `manual_rejected` → "✗ ปฏิเสธ"  (red)
- Checkpoint name (small, muted)

**Lightbox:** same pattern as Review Queue — fixed overlay, backdrop click closes.

**Filter bar:**
- Bib: `<input type="text">` debounced 300ms
- Checkpoint: `<select>` populated from `useEventDetail` (existing hook at `hooks/useEventDetail.ts`)
- AI Status: `<select>` with hardcoded options

**Loading state:** 8 skeleton cards (grey animated pulse, same grid layout)

**Empty state:** "ไม่พบรูปภาพ" + "ล้าง filter" button

### Event detail page — add link button

In `apps/frontend/app/(internal)/dashboard/events/[id]/page.tsx`, add a link button near the top:

```tsx
<Link href={`/dashboard/events/${event.id}/photos`}
  className="...button styles..."
>
  📷 ดูรูปภาพ
</Link>
```

---

## Data Flow

```
1. Staff clicks "ดูรูปภาพ" from event detail
2. Navigates to /dashboard/events/[id]/photos
3. Fetches GET /internal/events/{id}/photos?page=1&per_page=24
4. Shows grid of 24 photos with pagination
5. Staff types bib "123" → debounce 300ms → refetch with &bib=123
6. Staff selects checkpoint → refetch with &checkpoint_id=...
7. Click page 2 → URL updates → refetch with &page=2
8. Click photo → lightbox opens (full-size image or thumbnail)
```

---

## Out of Scope

- Edit photo metadata (bib override, status change) — stay in Review Queue
- Delete photos — Phase 5+ with PDPA workflow
- Download photos — Phase 5+
- Sort by (confidence, captured_at, bib) — Phase 5 (C option deferred)
- Date range filter — Phase 5 (C option deferred)
