# Cursor Task: Phase 4C — Photo Gallery UI

## Context

Project: Joggy-PicX — Internal Dashboard for running event photo management.
Working directory: `apps/frontend/`
Stack: Next.js 15 App Router, TypeScript strict, TanStack Query v5, Tailwind CSS v4.

Backend API is live:
```
GET /internal/events/{event_id}/photos
  ?page=1&per_page=24&bib=&checkpoint_id=&ai_status=

Response: {
  items: PhotoItem[],
  total: number,
  page: number,
  per_page: number,
  pages: number
}
```

Auth pattern: use `apiGet` helper from `lib/api.ts` which auto-injects Supabase JWT.

Existing hooks:
- `hooks/useEvents.ts` — `useEvents()` — event list
- `hooks/useEventDetail.ts` — `useEventDetail(eventId)` — event detail including checkpoints
- `hooks/useReviewQueue.ts` — reference for hook pattern

## API Types

```typescript
type PhotoItem = {
  photo_id: string
  bib_number: string | null
  bib_confidence: number | null  // 0.0–1.0 or null
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
```

## Task A: Create `hooks/useEventPhotos.ts`

```typescript
"use client"
import { useQuery } from "@tanstack/react-query"
import { apiGet } from "../lib/api"

export type PhotoItem = {
  photo_id: string
  bib_number: string | null
  bib_confidence: number | null
  ai_review_status: "auto" | "manual_pending" | "manual_approved" | "manual_rejected"
  thumbnail_url: string | null
  checkpoint_name: string | null
  captured_at: string | null
}

export type EventPhotosResponse = {
  items: PhotoItem[]
  total: number
  page: number
  per_page: number
  pages: number
}

export type PhotoFilters = {
  page?: number
  bib?: string
  checkpointId?: string
  aiStatus?: string
}

async function getEventPhotos(
  eventId: string,
  filters: PhotoFilters
): Promise<EventPhotosResponse> {
  const params = new URLSearchParams()
  params.set("page", String(filters.page || 1))
  params.set("per_page", "24")
  if (filters.bib) params.set("bib", filters.bib)
  if (filters.checkpointId) params.set("checkpoint_id", filters.checkpointId)
  if (filters.aiStatus) params.set("ai_status", filters.aiStatus)

  const result = await apiGet<EventPhotosResponse>(
    `/internal/events/${eventId}/photos?${params.toString()}`
  )
  if (!result.success) throw new Error(result.error || "Failed to fetch photos")
  return result.data!
}

export function useEventPhotos(eventId: string | null, filters: PhotoFilters = {}) {
  return useQuery({
    queryKey: ["event-photos", eventId, filters],
    queryFn: () => getEventPhotos(eventId!, filters),
    enabled: !!eventId,
    staleTime: 30 * 1000,
  })
}
```

## Task B: Create `app/(internal)/dashboard/events/[id]/photos/page.tsx`

Full gallery page for browsing event photos.

### URL State

Use Next.js `useSearchParams` + `useRouter` + `useParams` to persist filter state in URL.

- `page` (default `"1"`)
- `bib` (default `""`)
- `checkpoint_id` (default `""`)
- `ai_status` (default `""`)

When any filter changes, call `router.push` with updated search params and reset `page` to `1`.

### Layout

```
[← กลับ Event Detail]
h1: "ภาพถ่าย"  subtext: (loaded from useEventDetail event.name)

Filter bar:
  [🔍 input: ค้นหาบิบ...]  [select: Checkpoint ▼]  [select: AI Status ▼]  [ล้าง filter button]

Stats: "แสดง X–Y จาก Z รูป"

Grid: 3 cols on mobile, 4 cols on md+

Pagination bar (at bottom)
```

### Filter bar details

- **Bib input**: `<input type="text" placeholder="ค้นหาบิบ...">` — debounce 300ms using `useEffect` + `setTimeout`
- **Checkpoint select**: `<select>` populated from `useEventDetail(eventId).data?.checkpoints` — first option is "ทุกจุด" (value `""`)
- **AI Status select**: `<select>` with hardcoded options:
  - `""` → "สถานะทั้งหมด"
  - `"auto"` → "✅ AI อนุมัติ"
  - `"manual_pending"` → "⏳ รอตรวจสอบ"
  - `"manual_approved"` → "✓ Staff อนุมัติ"
  - `"manual_rejected"` → "✗ Staff ปฏิเสธ"
- **ล้าง filter**: show only when any filter is active — resets all filters + page to defaults

### Photo Card (inline component)

Each photo card in the grid:

```tsx
<div className="bg-white rounded-lg overflow-hidden shadow hover:shadow-md transition-shadow cursor-pointer">
  {/* Thumbnail */}
  <div className="aspect-square bg-slate-100 relative">
    {thumbnail_url ? (
      <img src={thumbnail_url} alt="photo" className="w-full h-full object-cover"
           onClick={() => setLightboxUrl(thumbnail_url)}
           onError={...fallback to 📷} />
    ) : (
      <div className="w-full h-full flex items-center justify-center text-4xl">📷</div>
    )}
  </div>
  {/* Info */}
  <div className="p-2 space-y-1">
    <div className="flex items-center justify-between">
      <span className="font-medium text-sm">{bib_number || "ไม่พบ"}</span>
      <ConfidenceBadge confidence={bib_confidence} />
    </div>
    <AIStatusBadge status={ai_review_status} />
    {checkpoint_name && <p className="text-xs text-slate-500">{checkpoint_name}</p>}
  </div>
</div>
```

**ConfidenceBadge**:
- `bib_confidence >= 0.70` → green (`bg-green-100 text-green-700`)
- `bib_confidence >= 0.50` → yellow (`bg-yellow-100 text-yellow-700`)
- `bib_confidence < 0.50` → red (`bg-red-100 text-red-700`)
- `null` → grey (`bg-slate-100 text-slate-500`)
- Display: `{Math.round(confidence * 100)}%` or `—`

**AIStatusBadge**:
- `auto` → small green badge "✅ AI"
- `manual_pending` → yellow "⏳ รอ"
- `manual_approved` → green "✓ อนุมัติ"
- `manual_rejected` → red "✗ ปฏิเสธ"

### Loading State

Show 8 skeleton cards (grey `animate-pulse` squares, same grid).

### Empty State

When `items.length === 0` after loading: "ไม่พบรูปภาพ" + show "ล้าง filter" button if filters active.

### Lightbox

Same pattern as Review Queue — `lightboxUrl: string | null` local state. Fixed overlay, `<img>`, backdrop click closes.

### Pagination Bar

```tsx
// Show: ← [1] [2] [3] ... [N] →
// Current page has different styling (bg-sky-600 text-white)
// Disable ← when page=1, disable → when page=pages
```

Simple approach: show at most 7 page buttons (first, last, current ±2, ellipsis if gap).

### State

Local React state only:
- `lightboxUrl: string | null`
- `bibInput: string` — raw input value (before debounce)

URL search params handle all other state (page, bib, checkpoint_id, ai_status).

## Task C: Add "ดูรูปภาพ" link in event detail page

File: `apps/frontend/app/(internal)/dashboard/events/[id]/page.tsx`

Add a link button near the top of the page (after the event name heading, before the checkpoints/stats section):

```tsx
import Link from "next/link"

// Inside the rendered event detail (after the event name/status):
<Link
  href={`/dashboard/events/${eventId}/photos`}
  className="inline-flex items-center gap-2 px-4 py-2 bg-sky-600 text-white rounded-lg hover:bg-sky-700 text-sm font-medium"
>
  📷 ดูรูปภาพ
</Link>
```

## TypeScript Requirements

- No `any` types
- All props and state must be explicitly typed
- Export `PhotoItem` and `EventPhotosResponse` types from `useEventPhotos.ts`

## Commit

After implementing Tasks A, B, and C:

```bash
git add apps/frontend/hooks/useEventPhotos.ts \
        apps/frontend/app/(internal)/dashboard/events/[id]/photos/page.tsx \
        apps/frontend/app/(internal)/dashboard/events/[id]/page.tsx
git commit -m "feat(frontend): Photo Gallery page — grid + filter + pagination + lightbox"
```
