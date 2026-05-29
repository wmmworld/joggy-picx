# Phase 4B — Manual Review Queue Design

**Date:** 2026-05-29  
**Author:** Claude (Tech Lead)  
**Status:** Approved

---

## Goal

Build the Manual Review Queue feature — a full-stack UI that lets Internal Users (admin/staff) review photos flagged by the AI pipeline as low-confidence, approve or reject them, and optionally override the bib number.

---

## Architecture

**Approach:** Frontend-only refresh (Approach 1)

Backend exposes 2 new endpoints under `/internal`. Frontend uses TanStack Query with optimistic updates. No polling or WebSocket — staff reviews photos after an event ends, not in real-time.

---

## Scope Decisions

- **Filter by event** — staff selects an event first; see only that event's pending queue
- **Thumbnail preview** — backend returns R2 signed URLs per item (presign is CPU-only, < 50ms for 150 items)
- **Actions:** approve (keep AI bib), approve + override bib, reject; plus bulk approve/reject (no bulk override)
- **Load all at once** — max 200 items per event; client-side sort/filter; no pagination (bulk select across pages is too complex)

---

## Backend

### New endpoints — `apps/backend/joggy/api/internal.py`

#### `GET /internal/review-queue?event_id=<uuid>`

**Auth:** Supabase JWT (same as all `/internal` endpoints)  
**Scope check:** admin sees all; staff must have event in `event_scope`  
**Returns:** list of pending/in_review items for the event, sorted by `created_at` DESC

**Response schema (`ReviewQueueItemOut`):**
```python
class ReviewQueueItemOut(BaseModel):
    queue_id: uuid.UUID
    photo_id: uuid.UUID
    reason: str               # "low_ocr_conf" | "no_bib"
    bib_number: str | None    # AI's best guess (Photo.bib_number_nullable)
    bib_confidence: float     # 0.0–1.0 (Photo.bib_confidence)
    thumbnail_url: str        # R2 signed URL, expires 1h
    checkpoint_name: str | None
    created_at: datetime
```

**Query joins:** `review_queue` → `photos` → `checkpoints` (LEFT JOIN)  
**Filter:** `review_queue.status IN ('pending', 'in_review')`

#### `PATCH /internal/review-queue/{queue_id}`

**Auth:** Supabase JWT  
**Scope check:** same as GET  
**Body (`ReviewAction`):**
```python
class ReviewAction(BaseModel):
    action: Literal["approve", "reject"]
    decision_bib: str | None = None   # override bib; ignored if action == "reject"
```

**Side effects (single transaction):**
1. `ReviewQueue.status → approved | rejected`
2. `ReviewQueue.decision_bib = decision_bib` (if approve + override)
3. `ReviewQueue.resolved_at = now()`
4. `Photo.ai_review_status → manual_approved | manual_rejected`
5. `Photo.bib_number_nullable = decision_bib` (if approve + override)
6. `AuditLog(actor_kind=internal_user, action="review_approved"|"review_rejected", target_kind="photo")`

**Error responses:**
- `404` — queue item not found, or event not found
- `403` — staff lacks scope for this event
- `409` — item already resolved (status ≠ pending/in_review)
- `422` — invalid UUID or action value

### New schemas — `apps/backend/joggy/api/schemas.py`

Add `ReviewQueueItemOut` and `ReviewAction` (see above).

### Tests — `apps/backend/tests/api/test_review_queue.py`

TDD pattern (matching existing test style):
- `test_list_review_queue_returns_pending_items`
- `test_list_review_queue_403_wrong_event_scope`
- `test_approve_sets_manual_approved_status`
- `test_approve_with_override_bib_updates_photo`
- `test_reject_sets_manual_rejected_status`
- `test_patch_already_resolved_returns_409`

---

## Frontend

### Files

| File | Action |
|------|--------|
| `apps/frontend/app/(internal)/dashboard/review/page.tsx` | Replace skeleton with real UI |
| `apps/frontend/hooks/useReviewQueue.ts` | New TanStack Query hook |
| `apps/frontend/lib/api.ts` | Add `apiPatch<T, B>` helper |

### `apiPatch` helper — `lib/api.ts`

Same pattern as `apiPost` but method `"PATCH"`.

### `useReviewQueue` hook — `hooks/useReviewQueue.ts`

```typescript
// Types
export type ReviewQueueItem = {
  queue_id: string
  photo_id: string
  reason: "low_ocr_conf" | "no_bib"
  bib_number: string | null
  bib_confidence: number
  thumbnail_url: string
  checkpoint_name: string | null
  created_at: string
}

// Query key: ["review-queue", eventId]
// Endpoint: GET /internal/review-queue?event_id={eventId}
// Mutation: PATCH /internal/review-queue/{queue_id}
//   - Optimistic update: remove item from list immediately
//   - On error: rollback + toast
```

### `ReviewQueuePage` — `page.tsx`

**Layout:**
```
┌─ Event selector ──────────────────────────────────┐
│  [dropdown: เลือก event]   [N รูปรอตรวจสอบ]      │
└───────────────────────────────────────────────────┘

┌─ Bulk action bar (แสดงเมื่อ check ≥ 1 รายการ) ───┐
│  ☑ N รายการที่เลือก  [✓ Approve]  [✗ Reject]     │
└───────────────────────────────────────────────────┘

┌─ Table ───────────────────────────────────────────┐
│ ☐ │ thumbnail │ Bib + confidence │ reason │ action │
│   │ (click→   │ [override input] │        │ [✓][✗] │
│   │  modal)   │                  │        │        │
└───────────────────────────────────────────────────┘
```

**Table columns:**
1. Checkbox (select for bulk)
2. Thumbnail — 64×64px, click opens lightbox modal (full image)
3. Bib — AI bib number + confidence badge (color: green ≥ 70%, yellow 50–69%, red < 50%); override input field below
4. Reason — badge: "OCR ต่ำ" (low_ocr_conf) or "ไม่พบบิบ" (no_bib)
5. จุดถ่าย — checkpoint_name or "—"
6. Actions — [✓ Approve] [✗ Reject] buttons per row

**UX rules:**
- Override bib field: always visible per row; if filled + approve clicked → sends `decision_bib`
- Bulk approve: uses AI bib (no override); bulk reject: rejects all selected
- Bulk override bib: **not supported** — override is per-item only
- Optimistic update: row disappears immediately on action; toast confirms; rollback on error
- Loading: skeleton rows (3 rows with animated pulse)
- Empty state: "ไม่มีรูปรอตรวจสอบ ✓" (same as skeleton)
- Event not selected: prompt "กรุณาเลือกงานวิ่ง"

**State management (local React state):**
- `selectedEventId: string | null`
- `selectedItems: Set<string>` (queue_ids)
- `overrideBibs: Record<string, string>` (queue_id → override value)
- TanStack Query handles server state (no Zustand needed for this page)

---

## Data Flow

```
1. Page loads → fetch /internal/events (reuse existing useEvents hook)
2. Staff selects event → fetch /internal/review-queue?event_id=X
3. Staff fills override bib (optional) → local state
4. Staff clicks Approve/Reject per row:
   PATCH /internal/review-queue/{id} { action, decision_bib? }
   → optimistic: remove from list
   → on success: toast
   → on error: rollback + toast
5. Staff selects multiple → Bulk Approve/Reject
   → sequential PATCH calls (or parallel Promise.all)
   → optimistic: remove all selected from list
```

---

## Out of Scope

- Assign queue item to specific staff member (`ReviewQueue.assigned_to`) — Phase 5
- Filter by reason (low_ocr_conf vs no_bib) within queue — Phase 5
- Photo metadata (captured_at, device_id) display — Phase 5
- Re-queue after rejection — not needed
