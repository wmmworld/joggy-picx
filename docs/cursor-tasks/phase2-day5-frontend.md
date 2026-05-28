# Cursor Tasks — Phase 2 Day 5 Frontend

**Prepared by:** Claude (Tech Lead)
**Date:** 2026-05-29
**Status:** Ready for Cursor to implement

รัน 2 tasks นี้ได้ทันที — independent, ไม่ depend กัน

---

## Task A: Event Create Modal

### Context

- Project: Joggy-PicX (marathon photo system). Internal dashboard for admin/staff only.
- Backend: FastAPI at http://localhost:8000. Internal API at `/internal/*`
- Auth: Supabase JWT injected automatically via `lib/api.ts` `apiPost()`
- POST `/internal/events` needs admin role — backend enforces, frontend shows button to all logged-in users for Phase 2.

### Backend Schema

**POST /internal/events body:**
```typescript
{
  organizer_id: string;   // UUID
  name: string;           // 1–255 chars
  start_at: string;       // ISO datetime string (UTC)
  end_at: string;         // ISO datetime string (UTC)
  allowed_origins?: object | null;
}
```

**Response (EventOut):**
```typescript
{
  id: string;
  organizer_id: string;
  name: string;
  start_at: string;
  end_at: string;
  status: "planned" | "active" | "completed";
  allowed_origins?: object | null;
  retention_until?: string | null;
  created_at: string;
  checkpoints: [];
}
```

### Files

1. **CREATE:** `apps/frontend/components/events/CreateEventModal.tsx`
2. **MODIFY:** `apps/frontend/app/(internal)/dashboard/events/page.tsx`

### CreateEventModal.tsx Requirements

**Props:**
```typescript
interface CreateEventModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}
```

**Form fields:**

| Field | Input Type | Validation |
|-------|-----------|------------|
| ชื่องาน (`name`) | text | required, 1–255 chars |
| Organizer ID (`organizer_id`) | text | required, placeholder "UUID ของ Organizer" |
| วันเริ่ม (`start_at`) | datetime-local | required |
| วันสิ้นสุด (`end_at`) | datetime-local | required, must be > start_at |
| Allowed Origins (JSON) | textarea | optional, placeholder `{"origins": ["https://example.com"]}` |

**Submit behavior:**
- `EventCreatePayload` type:
  ```typescript
  export type EventCreatePayload = {
    organizer_id: string;
    name: string;
    start_at: string;   // ISO string with "Z" suffix (UTC)
    end_at: string;     // ISO string with "Z" suffix (UTC)
    allowed_origins?: object | null;
  };
  ```
- Convert `datetime-local` value (e.g. `"2026-06-01T08:00"`) → ISO string with `"Z"` suffix: `value + ":00.000Z"`
- Call: `apiPost<EventOut, EventCreatePayload>("/internal/events", payload)`
- Import apiPost: `import { apiPost } from "@/lib/api"` (or adjust relative path)
- On success: call `onSuccess()` then `onClose()`
- On error: show error message inline in modal (do NOT close modal on error)

**UX Rules:**
- Submit button shows loading state (disabled + spinner text) during API call
- × button in top-right corner closes modal (calls `onClose`, resets form)
- Clicking outside backdrop closes modal (`onClick` on backdrop div)
- Reset all form state when modal closes (use `useEffect` on `isOpen`)
- Client-side validation: show inline error if `end_at <= start_at`

**Modal structure (no shadcn Dialog):**
```
<div> backdrop (fixed inset-0, bg-black/50, z-50)
  <div> card (bg-white, rounded-xl, shadow-xl, p-6, max-w-lg, mx-auto, mt-20)
    <h2> "สร้างงานวิ่งใหม่"
    <button × > (absolute top-4 right-4)
    <form>
      ...fields...
      <button type="submit"> "สร้างงาน" / loading state
    </form>
    {error && <p className="text-red-500 text-sm mt-2">{error}</p>}
  </div>
</div>
```

### events/page.tsx Modifications

- Add `import { useState } from "react"` if not already there
- Add `import { useQueryClient } from "@tanstack/react-query"`
- Add `import { CreateEventModal } from "@/components/events/CreateEventModal"` (adjust path)
- Add state: `const [isCreateOpen, setIsCreateOpen] = useState(false)`
- Add `const queryClient = useQueryClient()`
- Add "สร้างงานใหม่" button in the header section (next to page heading):
  ```tsx
  <button
    onClick={() => setIsCreateOpen(true)}
    className="bg-sky-600 text-white px-4 py-2 rounded hover:bg-sky-700 text-sm"
  >
    + สร้างงานใหม่
  </button>
  ```
- Mount modal:
  ```tsx
  <CreateEventModal
    isOpen={isCreateOpen}
    onClose={() => setIsCreateOpen(false)}
    onSuccess={() => queryClient.invalidateQueries({ queryKey: ["events"] })}
  />
  ```

### Type to Add (in `hooks/useEvents.ts` or a new types file)

```typescript
export type EventCreatePayload = {
  organizer_id: string;
  name: string;
  start_at: string;
  end_at: string;
  allowed_origins?: object | null;
};
```

---

## Task B: Manual Review Queue UI Skeleton

### Context

- Project: Joggy-PicX (marathon photo system). Internal dashboard only.
- Phase 2 scope: **STATIC skeleton only** — NO API calls, NO hooks, NO real data.
- Phase 3 will add actual data from backend.

### File to Create

`apps/frontend/app/(internal)/dashboard/review/page.tsx`

### Page Requirements

```tsx
"use client";

// Layout:
// - Header: "คิวตรวจสอบรูป" (h1)
// - Subtitle: "รูปที่ AI ประเมิน confidence ต่ำ รอการตรวจสอบจาก staff"
// - Stats card: "0 รูปรอตรวจสอบ" (hardcoded 0 for Phase 2)
// - Disabled action buttons in header area: "อนุมัติ" (green, disabled) + "ปฏิเสธ" (red, disabled)
//   to illustrate future functionality
// - Table:
//   Columns: รูปภาพ | เลขบิบ | งาน | AI Confidence | การจัดการ
//   Body: single row: "ยังไม่มีรูปรอตรวจสอบ ✓" colSpan={5}
// - Muted note below table:
//   "Phase 3: ระบบ AI จะส่งรูปที่ confidence ต่ำกว่า 80% มาที่นี่โดยอัตโนมัติ"
//
// Style: white card bg, shadow, rounded, Tailwind only
// NO API calls anywhere in this file
```

### dashboard/page.tsx Modification

In `apps/frontend/app/(internal)/dashboard/page.tsx` — add a card/link for "คิวตรวจสอบ":

```tsx
// Add a card linking to /dashboard/review
// Badge showing "0" items pending
// Example:
<Link href="/dashboard/review" className="...card styles...">
  <div className="flex justify-between items-center">
    <span>คิวตรวจสอบรูป</span>
    <span className="bg-gray-100 text-gray-600 text-xs px-2 py-1 rounded-full">0 รูป</span>
  </div>
  <p className="text-sm text-gray-500 mt-1">รูปที่ AI ประเมิน confidence ต่ำ</p>
</Link>
```

---

## Verification Steps (after Cursor delivers)

### Task A verification
- [ ] `CreateEventModal.tsx` exists and imports `apiPost` correctly
- [ ] `events/page.tsx` has "สร้างงานใหม่" button + modal mounted
- [ ] No TypeScript errors: `cd apps/frontend && npx tsc --noEmit`
- [ ] `end_at > start_at` validation present (inline error shown)
- [ ] Form resets when modal closes

### Task B verification
- [ ] `review/page.tsx` exists with no API calls
- [ ] Page renders without errors (static only)
- [ ] Dashboard page has link to `/dashboard/review`
- [ ] Table has correct 5 columns

---

_Claude Note: These tasks are frontend-only and do not touch backend. Backend endpoints for Tasks A+B are already implemented (Day 4+5)._
