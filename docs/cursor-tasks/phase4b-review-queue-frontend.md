# Cursor Task: Phase 4B — Manual Review Queue UI

## Context

Project: Joggy-PicX — Internal Dashboard for running event photo management.
Working directory: `apps/frontend/`
Stack: Next.js 15 App Router, TypeScript strict, TanStack Query v5, Tailwind CSS v4, `@biomejs/biome` linter.

Backend APIs are already live:
- `GET /internal/review-queue?event_id=<uuid>` — returns list of ReviewQueueItem (max 200)
- `PATCH /internal/review-queue/<queue_id>` — approve/reject/override bib

Auth pattern: all internal API calls use `apiGet`/`apiPost` helpers from `lib/api.ts` which inject Supabase JWT automatically.

## API Response Types

```typescript
// GET /internal/review-queue?event_id=...
type ReviewQueueItem = {
  queue_id: string
  photo_id: string
  reason: "low_ocr_conf" | "no_bib"
  bib_number: string | null
  bib_confidence: number | null  // 0.0-1.0; null when no bib detected
  thumbnail_url: string | null   // null if no thumbnail generated yet
  checkpoint_name: string | null
  created_at: string
}

// PATCH /internal/review-queue/:queue_id body
type ReviewActionPayload = {
  action: "approve" | "reject"
  decision_bib?: string | null
}

// PATCH response
type ReviewActionResponse = {
  status: "approved" | "rejected"
  queue_id: string
}
```

## Task A: Add `apiPatch` helper to `lib/api.ts`

Add a `apiPatch<T, B>` function that is identical to `apiPost` but uses method `"PATCH"`. Place it after `apiPost`. Export it.

```typescript
export async function apiPatch<T, B = unknown>(
  endpoint: string,
  body?: B
): Promise<ApiResponse<T>> {
  try {
    const supabase = createClient();
    const {
      data: { session }
    } = await supabase.auth.getSession();

    if (!session) {
      return { success: false, error: "Unauthorized" };
    }

    const response = await fetch(`${BASE_URL}${endpoint}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${session.access_token}`
      },
      body: body ? JSON.stringify(body) : undefined
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      return {
        success: false,
        error: errorData.detail || `HTTP ${response.status}`
      };
    }

    const data = await response.json();
    return { success: true, data };
  } catch (error) {
    return {
      success: false,
      error: error instanceof Error ? error.message : "Unknown error"
    };
  }
}
```

## Task B: Create `hooks/useReviewQueue.ts`

Create `apps/frontend/hooks/useReviewQueue.ts`:

```typescript
"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPatch } from "../lib/api";

export type ReviewQueueItem = {
  queue_id: string;
  photo_id: string;
  reason: "low_ocr_conf" | "no_bib";
  bib_number: string | null;
  bib_confidence: number | null;
  thumbnail_url: string | null;
  checkpoint_name: string | null;
  created_at: string;
};

type ReviewActionPayload = {
  action: "approve" | "reject";
  decision_bib?: string | null;
};

async function getReviewQueue(eventId: string): Promise<ReviewQueueItem[]> {
  const result = await apiGet<ReviewQueueItem[]>(
    `/internal/review-queue?event_id=${eventId}`
  );
  if (!result.success) throw new Error(result.error || "Failed to fetch review queue");
  return result.data || [];
}

export function useReviewQueue(eventId: string | null) {
  return useQuery({
    queryKey: ["review-queue", eventId],
    queryFn: () => getReviewQueue(eventId!),
    enabled: !!eventId,
    staleTime: 30 * 1000,
    retry: 2,
  });
}

export function useResolveItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      queueId,
      payload,
    }: {
      queueId: string;
      payload: ReviewActionPayload;
    }) => {
      const result = await apiPatch<ReviewActionResponse>(
        `/internal/review-queue/${queueId}`,
        payload
      );
      if (!result.success) throw new Error(result.error || "Failed to resolve item");
      return result.data;
    },
  });
}

type ReviewActionResponse = {
  status: "approved" | "rejected";
  queue_id: string;
};
```

## Task C: Replace `app/(internal)/dashboard/review/page.tsx`

Replace the existing skeleton entirely with a full working page. Requirements:

### Layout

1. **Page header**: `"คิวตรวจสอบรูป"` (h1) + description `"รูปที่ AI confidence ต่ำ รอตรวจสอบจาก staff"`

2. **Event selector**: `<select>` dropdown that loads events using `useEvents()` hook (already at `hooks/useEvents.ts`). Show placeholder `"— เลือกงานวิ่ง —"` when no event selected. Option label format: `{event.name} ({event.start_at formatted as DD/MM/YYYY})`.

3. **Stats bar** (only when event selected and data loaded): `"N รูปรอตรวจสอบ"` badge showing `items.length`.

4. **Bulk action bar** (only when `selectedItems.size >= 1`):
   - `"☑ N รายการที่เลือก"` label
   - `[✓ Approve all]` green button — calls approve for all `selectedItems` queue_ids (no `decision_bib` override in bulk), using `Promise.all`
   - `[✗ Reject all]` red button — calls reject for all selected
   - After bulk action completes: remove all resolved items from `items` state, clear `selectedItems`

5. **Table** with columns: ☐ checkbox | รูปภาพ | บิบ + override | สาเหตุ | จุดถ่าย | การจัดการ

6. **Empty state** (when event selected but `items.length === 0` and not loading): `"ไม่มีรูปรอตรวจสอบ ✓"` centered message.

7. **No event state** (when no event selected): `"กรุณาเลือกงานวิ่ง"` prompt centered.

### Table Row Details

Each row:

- **Checkbox**: selects item for bulk. `"Select all"` checkbox in `<thead>` — checks/unchecks all.

- **รูปภาพ column**: `<img>` 64×64px, `object-cover rounded`. Source: `thumbnail_url`. If `thumbnail_url` is `null` or image fails to load, show `📷` emoji placeholder centered in a 64×64 grey box. Click on image opens a **lightbox modal** — an overlay with backdrop (dark semi-transparent full-screen div), showing the full image centered, click backdrop to close.

- **บิบ column**:
  - Top: AI bib number with a confidence badge:
    - `bib_confidence >= 0.70`: green badge background
    - `0.50 <= bib_confidence < 0.70`: yellow badge background  
    - `bib_confidence < 0.50` or `null`: red badge background
    - Show `"ไม่พบ"` if `bib_number` is null
    - Show confidence as percentage, e.g. `"52%"`
  - Below: small text input `<input type="text" placeholder="แก้ไขบิบ (optional)" />` — stores in `overrideBibs[queue_id]` local state

- **สาเหตุ column**: small badge
  - `low_ocr_conf` → `"OCR ต่ำ"` yellow
  - `no_bib` → `"ไม่พบบิบ"` red

- **จุดถ่าย column**: `checkpoint_name` or `"—"`

- **การจัดการ column**:
  - `[✓]` green button — approve; if `overrideBibs[queue_id]` is non-empty, include `decision_bib`
  - `[✗]` red button — reject (no decision_bib)
  - Both show a small spinner `"..."` when `processingIds` contains this `queue_id`
  - Both disabled when `processingIds` contains this `queue_id`

### Behaviour

**Per-item approve:**
1. Add `queue_id` to `processingIds`
2. Call `PATCH /internal/review-queue/{queue_id}` with `{ action: "approve", decision_bib: overrideBibs[queue_id] || null }`
3. On success: remove item from `items` state, remove from `selectedItems`, show success toast `"อนุมัติแล้ว"`
4. On error: remove from `processingIds`, show error toast `"เกิดข้อผิดพลาด กรุณาลองใหม่"`
5. Remove from `processingIds` after completion

**Per-item reject:**
Same but `{ action: "reject" }`. Toast: `"ปฏิเสธแล้ว"`.

**Bulk approve:**
`Promise.all(selectedIds.map(id => resolveItem({queueId: id, payload: {action: "approve"}})))`. On settle: remove all from `items` and `selectedItems`. Toast: `"อนุมัติ N รายการแล้ว"`.

**Bulk reject:**
Same, toast: `"ปฏิเสธ N รายการแล้ว"`.

**Error handling:** On any per-item error, do NOT remove item from `items`. Toast stays 3 seconds.

### Loading States

- While fetching queue: show 3 skeleton rows — grey animated `animate-pulse` bars in each cell column
- While event list loading: show `"กำลังโหลด..."` as a disabled `<option>` in the dropdown

### State (local React `useState`)

```typescript
const [selectedEventId, setSelectedEventId] = useState<string | null>(null)
const [selectedItems, setSelectedItems] = useState<Set<string>>(new Set())
const [overrideBibs, setOverrideBibs] = useState<Record<string, string>>({})
const [lightboxUrl, setLightboxUrl] = useState<string | null>(null)
const [processingIds, setProcessingIds] = useState<Set<string>>(new Set())
const [items, setItems] = useState<ReviewQueueItem[]>([])
const [toast, setToast] = useState<{ message: string; type: "success" | "error" } | null>(null)
```

Initialize `items` from `useReviewQueue` data using `useEffect`:
```typescript
const { data: queueData, isLoading } = useReviewQueue(selectedEventId)
useEffect(() => {
  if (queueData) setItems(queueData)
}, [queueData])
```

### Toast

Simple fixed-position div, bottom-right corner, appears for 3 seconds then disappears:
```typescript
const showToast = (message: string, type: "success" | "error") => {
  setToast({ message, type })
  setTimeout(() => setToast(null), 3000)
}
```
Green background for success, red for error.

### TypeScript

All types explicit — no `any`. Use `ReviewQueueItem` from `hooks/useReviewQueue.ts`. Import `useEvents` from `hooks/useEvents.ts` for the event dropdown.

## Commit Instructions

After implementing Tasks A, B, and C:

```bash
git add apps/frontend/lib/api.ts \
        apps/frontend/hooks/useReviewQueue.ts \
        "apps/frontend/app/(internal)/dashboard/review/page.tsx"
git commit -m "feat(frontend): Review Queue UI — event filter + table + approve/reject/override"
```

## TypeScript Check

After implementing, verify 0 errors:
```bash
cd apps/frontend
npx tsc -p tsconfig.json --noEmit
```
